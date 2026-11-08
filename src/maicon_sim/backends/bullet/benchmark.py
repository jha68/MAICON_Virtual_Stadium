"""Reproducible CPU sensing profiles; measured throughput is not a guarantee."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import queue
import resource
import threading
import time
import numpy as np
from PIL import Image

from .backend import BulletBackend
from maicon_sim.core.engine import MatchEngine
from maicon_sim.sensors.gateway import SensorGateway
from maicon_sim.perception.synthetic_template import SyntheticTemplateDetector
from maicon_sim.evaluation.metrics import machine
from maicon_sim.evaluation.recorder import lock_hash, implementation_hash


class BoundedFrameRecorder:
    """Latest/drop recording with bounded RAM and content-addressed frame reuse."""
    def __init__(self,out,capacity=4,writer_delay_s=0.):
        self.root=Path(out);self.root.mkdir(parents=True,exist_ok=True)
        self.queue=queue.Queue(maxsize=capacity);self.capacity=capacity;self.writer_delay_s=writer_delay_s
        self.dropped=0;self.written=0;self.queue_peak=0;self.error=None;self._stop=object()
        self.worker=threading.Thread(target=self._run,name='maicon-frame-recorder',daemon=True);self.worker.start()
    def submit(self,frame):
        # Frames are immutable, so at most capacity+1 RGB buffers are retained.
        try:self.queue.put_nowait(frame);self.queue_peak=max(self.queue_peak,self.queue.qsize())
        except queue.Full:self.dropped+=1
    def _run(self):
        try:
            with (self.root/'frames.jsonl').open('w') as index:
                while True:
                    frame=self.queue.get()
                    if frame is self._stop:break
                    if self.writer_delay_s:time.sleep(self.writer_delay_s)
                    data=np.asarray(frame['data']);digest=hashlib.sha256(data.tobytes()).hexdigest();path=self.root/(digest+'.png')
                    if not path.exists():Image.fromarray(data[...,::-1]).save(path)
                    index.write(json.dumps({'camera_id':frame['camera_id'],'captured_tick':frame['captured_tick'],
                        'sequence':frame['sequence'],'file':path.name,'pixels_sha256':digest})+'\n');self.written+=1
        except BaseException as exc:self.error=f'{type(exc).__name__}: {exc}'
    def close(self):
        if not self.worker.is_alive():
            if self.error:raise RuntimeError('recording failed: '+self.error)
            return
        self.queue.put(self._stop,timeout=30);self.worker.join(30)
        if self.worker.is_alive():raise RuntimeError('recording worker failed to close')
        if self.error:raise RuntimeError('recording failed: '+self.error)
    @property
    def metrics(self):
        return {'recorded_frames':self.written,'record_dropped':self.dropped,
                'record_queue_peak':self.queue_peak,'record_queue_capacity':self.capacity,
                'recording_policy':'bounded_drop_new_content_addressed_frames'}


def benchmark_profile(config,out,*,duration_s=300,camera_count=6,inference_hz=0,record=False):
    """Full simulated duration, real core/sensors and optional image-only work.

    This is offline lockstep throughput. Identical static snapshots reuse exact
    RGB/depth buffers; metadata states cache counts. No1x realtime claim follows.
    """
    if duration_s<=0 or duration_s*100!=int(duration_s*100):raise ValueError('duration must be a positive10ms multiple')
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    code_hash=implementation_hash()
    engine=MatchEngine(config);engine.request('enter_ready')
    for slot in engine.robots:engine.request('ready',slot)
    engine.request('start')
    recorder=BoundedFrameRecorder(out/'recorded') if record else None
    detector=SyntheticTemplateDetector() if inference_hz else None
    steps=[];inference=[];inference_frames=0;started=time.monotonic()
    try:
        with BulletBackend(config) as backend:
            gateway=SensorGateway(config,backend);gateway.camera_slots=set(list(engine.robots)[:camera_count])
            gateway.update(engine)
            ticks=int(duration_s*100)
            for tick in range(1,ticks+1):
                t=time.monotonic();engine.step();gateway.update(engine);steps.append(time.monotonic()-t)
                if tick%10==0:
                    for slot in sorted(gateway.camera_slots):
                        frame=gateway.get_frame(slot)
                        if recorder is not None:recorder.submit(frame)
                        if detector is not None and tick%int(100/inference_hz)==0:
                            t=time.monotonic();detector.detect(frame['data']);inference.append(time.monotonic()-t);inference_frames+=1
            measured=backend.metrics
            measured['renderer_metadata']=backend.metadata
            counts={f'{slot}/{sensor}':value for (slot,sensor),value in gateway.counts.items()}
    finally:
        if recorder is not None:recorder.close()
    wall=time.monotonic()-started
    def summary(values):return {'count':len(values),**{f'p{q}_ms':float(np.percentile(values,q)*1000) if values else 0. for q in (50,95,99)}}
    result={'schema_version':'1.0','profile':f'camera{camera_count}'+('_rgb_inference_record' if record else ''),
        'environment':machine(),'seed':config.scenario['seed'],'hashes':config.hashes,
        'dependency_lock_hash':lock_hash(),'implementation_tree_hash':code_hash,
        'clock_mode':'offline_lockstep','duration_sim_s':duration_s,'wall_duration_s':wall,'real_time_factor':duration_s/wall,
        'scene_policy':'idle_static_cache_counts_recorded','camera_count':camera_count,'camera_hz':config.rules['sensors']['camera_hz'],
        'drone_hz':1,'resolution':[640,480],'inference_hz':inference_hz,'inference_frames':inference_frames,
        'step_latency':summary(steps),'inference_latency':summary(inference),'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        'sensor_counts':counts,**measured,**(recorder.metrics if recorder else {})}
    (out/'metrics.json').write_text(json.dumps(result,indent=2)+'\n')
    return result
