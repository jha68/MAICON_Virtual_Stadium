"""Bounded latest-only rendering in an isolated Bullet-owning process.

PyBullet's C rendering may hold the GIL. A thread alone cannot guarantee command
heartbeats while a large image renders, hence the dedicated spawned process.
"""
from __future__ import annotations
import copy
from collections import OrderedDict
import multiprocessing
import threading
import time
from .backend import BulletBackend


def _render_process(connection,config,resolved_assets,headless):
    backend=None
    try:
        backend=BulletBackend(config,resolved_assets,headless)
        connection.send({'ready':True,'metrics':backend.metrics,'metadata':backend.metadata});generation=None
        while True:
            request=connection.recv()
            if request['kind']=='stop':break
            if request['generation']!=generation:
                backend.reset_session();generation=request['generation']
            if request['delay_s']:time.sleep(request['delay_s'])
            backend.sync_scene(request['snapshot'])
            camera_id=request['camera_id'];tick=request['tick']
            frame=backend.capture_drone(tick) if camera_id=='main' else backend.capture_rgb(camera_id,tick)
            connection.send({'generation':generation,'frame':frame,'metrics':backend.metrics,'metadata':backend.metadata})
    except (EOFError,BrokenPipeError):pass
    except BaseException as exc:
        try:connection.send({'error':f'{type(exc).__name__}: {exc}'})
        except (EOFError,BrokenPipeError,OSError):pass
    finally:
        if backend is not None:backend.close()
        connection.close()


class AsyncBulletBackend:
    asynchronous=True
    capabilities=BulletBackend.capabilities

    def __init__(self,config,resolved_assets=None,headless=True,render_delay_s=0.):
        self.config=config;self.resolved_assets=resolved_assets;self.headless=headless
        self.render_delay_s=render_delay_s;self.queue_peak=0;self.dropped=0;self.completed_dropped=0;self.last_error=None
        self._condition=threading.Condition();self._pending=OrderedDict();self._completed=OrderedDict()
        self._snapshot=None;self._closed=False;self._inflight=False;self._generation=0;self._latest_metrics={};self._latest_metadata={}
        context=multiprocessing.get_context('spawn')
        parent,child=context.Pipe(duplex=True);self._connection=parent
        self._process=context.Process(target=_render_process,args=(child,config,resolved_assets,headless),name='maicon-bullet-process',daemon=True)
        self._process.start();child.close()
        if not parent.poll(30):
            self._process.terminate();self._process.join(5);parent.close()
            raise RuntimeError('Bullet worker initialization timed out')
        ready=parent.recv()
        if ready.get('error'):
            self._process.join(5);parent.close();raise RuntimeError('Bullet worker initialization failed: '+ready['error'])
        self._latest_metrics=ready.get('metrics',{});self._latest_metadata=ready.get('metadata',{})
        self._thread=threading.Thread(target=self._run,name='maicon-render-broker',daemon=True);self._thread.start()

    @property
    def pending_count(self):
        with self._condition:return len(self._pending)

    @property
    def inflight_count(self):
        with self._condition:return int(self._inflight)

    @property
    def metadata(self):
        return {**self._latest_metadata,'renderer':('PyBullet DIRECT/TinyRenderer process' if self.headless else 'PyBullet GUI/TinyRenderer process'),'asynchronous':True,
                'queue_policy':'latest_only_per_camera','pending_count':self.pending_count,
                'dropped':self.dropped,'completed_dropped':self.completed_dropped,'last_error':self.last_error}

    @property
    def metrics(self):
        return {**self._latest_metrics,'render_queue_peak':self.queue_peak,'render_queue_capacity':'one_per_camera',
            'render_dropped':self.dropped,'completed_dropped':self.completed_dropped,'render_inflight_count':self.inflight_count}

    def sync_scene(self,snapshot):
        with self._condition:self._snapshot=copy.deepcopy(snapshot)

    def reset_session(self,snapshot=None):
        with self._condition:
            self._generation+=1;self._pending.clear();self._completed.clear();self._snapshot=copy.deepcopy(snapshot)
            self._condition.notify_all()

    def request_capture(self,camera_id,tick):
        with self._condition:
            if self._closed:raise RuntimeError('render worker closed')
            if self._snapshot is None:return
            if camera_id in self._pending:self.dropped+=1
            self._pending[camera_id]=(self._generation,int(tick),self._snapshot)
            self.queue_peak=max(self.queue_peak,len(self._pending));self._condition.notify()

    def poll_completed(self):
        with self._condition:
            result=list(self._completed.values());self._completed.clear();return result

    def _run(self):
        try:
            while True:
                with self._condition:
                    self._condition.wait_for(lambda:self._closed or bool(self._pending))
                    if self._closed:break
                    camera_id,(generation,tick,snapshot)=self._pending.popitem(last=False)
                    self._inflight=True
                self._connection.send({'kind':'capture','camera_id':camera_id,'generation':generation,
                    'tick':tick,'snapshot':snapshot,'delay_s':self.render_delay_s})
                response=self._connection.recv()
                if 'error' in response:raise RuntimeError(response['error'])
                with self._condition:
                    self._inflight=False
                    self._latest_metrics=response['metrics'];self._latest_metadata=response['metadata']
                    if generation==self._generation and not self._closed:
                        if camera_id in self._completed:self.completed_dropped+=1
                        self._completed[camera_id]=response['frame']
        except (EOFError,BrokenPipeError,OSError) as exc:
            if not self._closed:self.last_error=f'{type(exc).__name__}: {exc}'
        except BaseException as exc:self.last_error=f'{type(exc).__name__}: {exc}'
        finally:
            with self._condition:self._inflight=False
            try:self._connection.send({'kind':'stop'})
            except (EOFError,BrokenPipeError,OSError):pass

    def close(self):
        with self._condition:self._closed=True;self._pending.clear();self._completed.clear();self._condition.notify_all()
        self._thread.join(timeout=30)
        self._process.join(timeout=10)
        if self._process.is_alive():
            self._process.terminate();self._process.join(5)
            self.last_error=self.last_error or 'render worker required forced termination'
        self._connection.close()
        if self._thread.is_alive():raise RuntimeError('Bullet render broker did not terminate')

    def __enter__(self):return self
    def __exit__(self,*args):self.close()


RenderWorker=AsyncBulletBackend
