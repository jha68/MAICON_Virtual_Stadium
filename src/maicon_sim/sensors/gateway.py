"""Single public projection for sensor data, with bounded delay queues."""
from __future__ import annotations
import copy
import hashlib
import io
import math
import threading
from collections import defaultdict
from datetime import datetime,timedelta
import numpy as np
from PIL import Image
from .odometry import OdometryModel
from .imu import ImuModel
from .lidar import scan
from .semantic import semantic_candidates,apply_noise
from ..core.geometry2d import pose_values
from ..core.geometry3d import canonical_solids
from ..backends.two_d import TwoDBackend

class SensorUnavailable(Exception):
    def __init__(self,status,detail):self.status=status;self.status_code=status;self.detail=detail;super().__init__(detail)

def make_rng(seed,slot,sensor,noise='measurement'):
    digest=hashlib.sha256(f'{seed}/{slot}/{sensor}/{noise}'.encode()).digest()
    return np.random.default_rng(int.from_bytes(digest[:16],'big'))

def encode_jpeg(frame,quality=90):
    data=np.asarray(frame['data'])
    image=Image.fromarray(data[...,::-1] if frame.get('encoding','bgr8')=='bgr8' else data)
    output=io.BytesIO();image.save(output,format='JPEG',quality=quality)
    return output.getvalue()

def scene_snapshot(engine):
    """Detached render geometry, without scores, reports or actuator bookkeeping."""
    def pose(value):
        x,y,yaw=pose_values(value)
        return {'x_m':x,'y_m':y,'yaw_rad':yaw}
    return {'robots':{s:{'pose':pose(r.pose),'pan':r.pan,'tilt':r.tilt,'hp':r.hp,'ammo':r.ammo}
                      for s,r in engine.robots.items()},
            'boxes':[{'box_id':b['box_id'],'pose':pose(b['pose']),'size_m':list(b['size_m'])}
                     for b in engine.boxes],
            'phase':engine.phase,'paused':engine.paused,'sim_tick':engine.sim_tick,
            'match_elapsed_ticks':engine.match_elapsed_ticks,
            'reporting_elapsed_ticks':engine.reporting_elapsed_ticks}

class SensorGateway:
    """Cadenced measurements. World objects are never returned to participants."""
    def __init__(self,config,backend=None):
        self.config=config;self.backend=backend or TwoDBackend(config)
        self.capabilities=dict(getattr(self.backend,'capabilities',{'rgb':True,'semantic':False,'lidar':True,'depth':False}))
        self.noise=config.sensors['noise_profiles'][config.scenario['noise_profile']]
        self.counts=defaultdict(int);self.dropped=0;self.generated=0;self._last_backend_dropped=0;self._store={};self._pending={};self._rng={};self._odom={};self._imu={}
        self._lock=threading.RLock();self._drone_lock=threading.RLock();self._session=None;self._last_engine=None;self._last_tick=None;self._geom_key=None;self._sem_cache={};self._sem_posekeys={};self._lidar_cache={};self._dropouts={}
        self._drone_pending=None;self._drone_latest=None;self._drone_cache={};self._drone_last_capture=-100000;self._drone_gate={};self._drone_disabled=False;self._current_engine=None
        self._epoch=datetime.fromisoformat(config.scenario['epoch_kst']);self._phase='waiting';self._destroyed=set();self._slots={a['slot'] for a in config.scenario['agents']};self.camera_slots=set(self._slots);self._admitted=set()
    def reconfigure(self,config,backend=None):
        old=self.backend
        replacement=backend or type(old)(config)
        old.close()
        self.__init__(config,replacement)
    def _record(self,kind,slot,channel,value):
        if self._current_engine is not None and hasattr(self._current_engine,'record'):
            payload={'source_id':slot+'/'+channel,'sequence':value.get('sequence',0),'captured_tick':value.get('captured_tick',self._last_tick),'received_tick':value.get('received_tick',self._last_tick)}
            self._current_engine.record(kind,payload=payload,category='measurement',actor=slot)
    def rng(self,slot,channel,kind='measurement'):
        key=(slot,channel,kind)
        if key not in self._rng:self._rng[key]=make_rng(self.config.scenario['seed'],*key)
        return self._rng[key]
    def _stamp(self,slot,channel,tick):
        self.counts[slot,channel]+=1;self.generated+=1
        return {'sequence':self.counts[slot,channel],'captured_tick':tick,'received_tick':tick}
    def _dropout(self,slot,channel,tick):
        aliases={'semantic':'camera','scan':'lidar'}
        return max(self._dropouts.get((slot,channel),-1),self._dropouts.get((slot,aliases.get(channel,channel)),-1))>tick
    def _deliver(self,key,value,tick,delay=0,drop_p=0):
        if self._dropout(key[0],key[1],tick):
            self.dropped+=1;self._record('sensor_dropped',key[0],key[1],value);return
        if drop_p and self.rng(key[0],key[1],'transport').random()<drop_p:
            self.dropped+=1;self._record('sensor_dropped',key[0],key[1],value);return
        if delay:
            value['received_tick']=tick+delay
            # At most delay/period +1 items per source; overwrite same capture key is impossible.
            self._pending.setdefault(key,[]).append((tick+delay,value))
        else:
            self._store[key]=value
            self._record('sensor_delivered',key[0],key[1],value)
    def _flush(self,tick):
        for key,queue in list(self._pending.items()):
            ready=[(t,v) for t,v in queue if t<=tick]
            if ready:
                if self._dropout(key[0],key[1],tick):
                    for _,value in ready:
                        self.dropped+=1;self._record('sensor_dropped',key[0],key[1],value)
                else:
                    self._store[key]=ready[-1][1]
                    for _,value in ready:self._record('sensor_delivered',key[0],key[1],value)
            left=[(t,v) for t,v in queue if t>tick]
            if left:self._pending[key]=left
            else:del self._pending[key]
    def update(self,engine):
        if self.config is not engine.config:self.reconfigure(engine.config)
        with self._lock:
            self._current_engine=engine
            tick=engine.sim_tick
            if self._session!=engine.match_id:
                if self._session is not None and hasattr(self.backend,'reset_session'):self.backend.reset_session()
                self._store.clear();self._pending.clear();self._rng.clear();self._odom.clear();self._imu.clear();self._sem_cache.clear();self._lidar_cache.clear();self._drone_cache.clear();self._drone_gate.clear();self._drone_latest=None;self._drone_pending=None;self._drone_disabled=False;self.counts.clear();self._drone_last_capture=-100000;self._session=engine.match_id;self._last_tick=None;self._geom_key=None
            if tick==self._last_tick:return
            self._last_tick=tick;self._last_engine=engine;self._phase=engine.phase
            backend_dropped=int(getattr(self.backend,'dropped',0))+int(getattr(self.backend,'completed_dropped',0))
            delta=max(0,backend_dropped-self._last_backend_dropped)
            if delta:
                self.dropped+=delta
                if hasattr(engine,'record'):
                    payload={'source_id':'renderer','dropped_count':delta,'total_dropped':backend_dropped,'captured_tick':tick,'received_tick':tick}
                    engine.record('sensor_dropped',payload=payload,category='measurement',actor='sensor')
                    engine.record('render_overload',payload=payload,category='measurement',actor='sensor')
            self._last_backend_dropped=backend_dropped
            self._destroyed=set(getattr(engine,'destroyed_facilities',getattr(engine,'destroyed',set())))
            self._admitted={s for s,r in engine.robots.items() if r.admitted}
            self._dropouts=dict(getattr(engine,'sensor_dropouts',{}))
            self._flush(tick)
            if self._drone_pending is not None and self._drone_pending[2]<=tick:
                self._drone_latest=self._drone_pending;self._drone_pending=None
            if getattr(self.backend,'asynchronous',False):
                for frame in self.backend.poll_completed():
                    frame=dict(frame);frame['received_tick']=tick
                    camera_id=frame['camera_id']
                    if camera_id=='main':
                        self._drone_pending=(encode_jpeg(frame,self.config.sensors['render']['jpeg_quality']),frame['captured_tick'],tick+self.noise.get('drone_delay_ms',0)//10)
                    else:
                        key=(camera_id.split('/')[0],'camera')
                        self._deliver(key,frame,tick,self.noise.get('camera_delay_ms',0)//10,self.noise.get('camera_drop_p',0))
            robots=engine.robots;boxes=getattr(engine,'boxes',self.config.scenario['boxes']);bounds=self.config.arena['bounds'];sensors=self.config.sensors;rules=self.config.rules['sensors']
            # The renderer consumes geometry only when a frame is captured.
            # Native GUI previews still receive every update; headless scenes
            # need neither full engine checkpoints nor100Hz deep copies.
            camera_due=self.capabilities['rgb'] and self.camera_slots and tick%(100//rules['camera_hz'])==0
            if camera_due or tick%100==0 or not getattr(self.backend,'headless',True):
                self.backend.sync_scene(scene_snapshot(engine))
            geom_key=(tuple((s,*pose_values(r.pose)) for s,r in sorted(robots.items())),tuple((b['box_id'],*pose_values(b['pose']),*b['size_m'],repr(b['faces'])) for b in boxes))
            if geom_key!=self._geom_key:
                self._geom_key=geom_key;self._sem_cache.clear();self._lidar_cache.clear()
            solids=None
            cmd=getattr(engine,'cmd',None) or getattr(engine,'match_command',None) or ('pause' if engine.paused else {'waiting':'standby','ready':'standby','running':'start','reporting':'report','finished':'stop','idle':'idle'}.get(engine.phase,'idle'))
            for slot,r in sorted(robots.items()):
                if slot not in self._odom:
                    self._odom[slot]=OdometryModel(r.initial_pose,self.noise,self.rng(slot,'odom'))
                    self._imu[slot]=ImuModel(r.initial_pose,self.noise,self.rng(slot,'imu'))
                channel_hz={'state':rules['state_hz'],'match':rules['state_hz'],'odom':rules['odom_hz'],'imu':rules['imu_hz'],'scan':rules['lidar_hz']}
                if self.capabilities['semantic']:channel_hz['semantic']=rules['camera_hz']
                if self.capabilities['rgb']:channel_hz['camera']=rules['camera_hz']
                for channel,hz in channel_hz.items():
                    if (channel=='camera' and slot not in self.camera_slots) or tick%(100//hz)!=0 or self._dropout(slot,channel,tick):continue
                    stamp=self._stamp(slot,channel,tick)
                    if channel=='state':value={'hp':r.hp,'hp_max':self.config.rules['robot']['hp_max'],'battery_pct':float(r.battery_pct)}
                    elif channel=='match':value={'mode':self.config.scenario['mode'],'cmd':cmd}
                    elif channel=='odom':value=self._odom[slot].measure(r.pose,tick,r.v,r.omega)
                    elif channel=='imu':value=self._imu[slot].measure(r.pose,tick,r.v,r.omega)
                    elif channel=='scan':
                        if slot in self._lidar_cache and self.config.scenario['noise_profile']=='ideal':value=self._lidar_cache[slot]
                        else:
                            if solids is None:solids=canonical_solids(robots,boxes,bounds,sensors['geometry'])
                            value=scan(robots,solids,slot,sensors['lidar'],self.noise,self.rng(slot,'scan'))
                            if self.config.scenario['noise_profile']=='ideal':self._lidar_cache[slot]=value
                    elif channel=='semantic':
                        if slot not in self._sem_cache or self._sem_posekeys.get(slot)!=(r.pan,r.tilt):
                            if solids is None:solids=canonical_solids(robots,boxes,bounds,sensors['geometry'])
                            self._sem_cache[slot]=semantic_candidates(robots,boxes,bounds,sensors,slot,solids=solids)
                            self._sem_posekeys[slot]=(r.pan,r.tilt)
                        value={'camera_id':slot+'/front','width_px':sensors['front_camera']['width_px'],'height_px':sensors['front_camera']['height_px'],
                               'detections':apply_noise(self._sem_cache[slot],self.noise,self.rng(slot,'semantic'))}
                    else:
                        if getattr(self.backend,'asynchronous',False):
                            self.backend.request_capture(slot+'/front',tick)
                            self._record('sensor_captured',slot,channel,stamp)
                            continue
                        value=dict(self.backend.capture_rgb(slot+'/front',tick));value.pop('sequence',None);value.pop('captured_tick',None);value.pop('received_tick',None)
                    value={**value,**stamp}
                    self._record('sensor_captured',slot,channel,value)
                    delay=self.noise.get('camera_delay_ms',0)//10 if channel in ('semantic','camera') else 0
                    drop=self.noise.get('camera_drop_p',0) if channel in ('semantic','camera') else 0
                    self._deliver((slot,channel),value,tick,delay,drop)
            if tick%100==0 and not self._dropout('all','drone',tick):
                if getattr(self.backend,'asynchronous',False):
                    self.backend.request_capture('main',tick)
                else:
                    frame=self.backend.capture_drone(tick)
                    value=(encode_jpeg(frame,sensors['render']['jpeg_quality']),frame['captured_tick'],tick+self.noise.get('drone_delay_ms',0)//10)
                    if value[2]<=tick:self._drone_latest=value
                    else:self._drone_pending=value
                self._drone_last_capture=tick
            self._flush(tick)
    def get(self,slot,channel):
        # Each stored envelope is immutable after publication. Taking the object
        # reference is atomic under CPython; copy/encode outside the writer lock
        # so a slow semantic projection cannot stall an HTTP control event loop.
        if slot not in self._slots:raise SensorUnavailable(409,'Robot is not assigned')
        if channel=='semantic' and not self.capabilities['semantic']:raise SensorUnavailable(409,'Semantic capability is unavailable in camera-only mode')
        if channel=='camera' and not self.capabilities['rgb']:raise SensorUnavailable(503,'2D front RGB is unavailable')
        value=self._store.get((slot,channel))
        if value is None:raise SensorUnavailable(503,'Sensor frame is not available')
        if channel=='camera':
            return encode_jpeg(value,self.config.sensors['render']['jpeg_quality']),{'X-Sim-Captured-Tick':str(value['captured_tick']),'X-Sim-Received-Tick':str(value['received_tick']),'X-Sim-Sequence':str(value['sequence'])}
        return copy.deepcopy(value)
    def get_frame(self,slot):
        value=self._store.get((slot,'camera'))
        if value is None:raise SensorUnavailable(503,'Camera frame is not available')
        return copy.deepcopy(value)
    def drone(self,engine,slot,camera=None,test_mode=False):
        with self._drone_lock:
            return self._get_drone(slot,camera,test_mode)
    def get_drone(self,slot,camera=None,test_mode=False):
        with self._drone_lock:return self._get_drone(slot,camera,test_mode)
    def _get_drone(self,slot,camera,test_mode):
        if camera is not None and camera not in ('main','test1','test2'):raise SensorUnavailable(422,'Unknown camera')
        test=bool(test_mode and camera is not None)
        if not test and (self._phase!='running' or slot not in self._admitted):raise SensorUnavailable(409,'Drone is only available to assigned running teams')
        camp='BLUE' if slot.startswith('B') else 'RED';destroyed=sum(code.startswith(camp+'_') for code in self._destroyed)
        if not test and destroyed>=3:raise SensorUnavailable(403,'All camp facilities are destroyed')
        interval=100 if test else self.config.rules['sensors']['drone_intervals_ms'][destroyed]//10
        tick=self._last_tick or 0;key=('test',camera) if test else ('camp',camp)
        latest=None if self._dropout(slot,'drone',tick) else self._drone_latest
        if (latest is not None and latest[2]<=tick
            and (key not in self._drone_cache or latest[1]>self._drone_cache[key][1])
            and (key not in self._drone_cache or tick-self._drone_gate[key]>=interval)):
            self._drone_cache[key]=(latest[0],latest[1]);self._drone_gate[key]=tick
        if key not in self._drone_cache:raise SensorUnavailable(503,'No normal drone frame is available')
        data,captured=self._drone_cache[key]
        headers={'X-Captured-At':(self._epoch+timedelta(milliseconds=captured*10)).isoformat(timespec='milliseconds'),
                 'X-Frame-Interval-S':str(interval/100),'X-Camera':camera if test else 'main','X-Test-Mode':'on' if test else 'off'}
        if not test:headers.update({'X-Camp':camp,'X-Destroyed':str(destroyed)})
        return data,headers
    def export_state(self):
        """JSON-safe private checkpoint, including noise streams and in-flight transport.

        Rendering connections and live processes are recreated; stored public frame
        bytes, sequence/timestamps, models and RNG streams are retained exactly.
        """
        with self._lock:
            fields=('_store','_pending','_session','_last_tick','_dropouts','_drone_pending',
                    '_drone_latest','_drone_cache','_drone_gate','_drone_last_capture',
                    '_drone_disabled','_phase','_destroyed','_slots','_admitted','camera_slots',
                    'dropped','generated','_last_backend_dropped')
            state={key:copy.deepcopy(getattr(self,key)) for key in fields}
            state['counts']=dict(self.counts)
            state['rng']={key:copy.deepcopy(rng.bit_generator.state) for key,rng in self._rng.items()}
            state['odom']={slot:{k:copy.deepcopy(v) for k,v in model.__dict__.items() if k!='rng'} for slot,model in self._odom.items()}
            state['imu']={slot:{k:copy.deepcopy(v) for k,v in model.__dict__.items() if k!='rng'} for slot,model in self._imu.items()}
            return _checkpoint_pack(state)
    def restore_state(self,state):
        with self._lock:
            state=_checkpoint_unpack(state)
            rng_states=state.pop('rng');odom=state.pop('odom');imu=state.pop('imu');counts=state.pop('counts')
            for key,value in state.items():setattr(self,key,value)
            self.counts=defaultdict(int,counts);self._rng={}
            for key,value in rng_states.items():
                generator=self.rng(*key);generator.bit_generator.state=value
            self._odom={};self._imu={}
            for slot,value in odom.items():
                model=OdometryModel.__new__(OdometryModel);model.__dict__.update(value);model.rng=self.rng(slot,'odom');self._odom[slot]=model
            for slot,value in imu.items():
                model=ImuModel.__new__(ImuModel);model.__dict__.update(value);model.rng=self.rng(slot,'imu');self._imu[slot]=model
            self._geom_key=None;self._sem_cache.clear();self._lidar_cache.clear();self._last_engine=None;self._current_engine=None
            if hasattr(self.backend,'reset_session'):self.backend.reset_session()
    def close(self):self.backend.close()


def _checkpoint_pack(value):
    import base64
    if isinstance(value,np.ndarray):return {'__sensor_array__':value.tolist(),'dtype':str(value.dtype)}
    if isinstance(value,np.generic):return value.item()
    if isinstance(value,bytes):return {'__sensor_bytes__':base64.b64encode(value).decode('ascii')}
    if isinstance(value,dict):return {'__sensor_dict__':[[_checkpoint_pack(k),_checkpoint_pack(v)] for k,v in value.items()]}
    if isinstance(value,tuple):return {'__sensor_tuple__':[_checkpoint_pack(v) for v in value]}
    if isinstance(value,set):return {'__sensor_set__':[_checkpoint_pack(v) for v in sorted(value)]}
    if isinstance(value,list):return [_checkpoint_pack(v) for v in value]
    return value


def _checkpoint_unpack(value):
    import base64
    if isinstance(value,dict):
        if '__sensor_array__' in value:return np.asarray(value['__sensor_array__'],dtype=value['dtype'])
        if '__sensor_bytes__' in value:return base64.b64decode(value['__sensor_bytes__'])
        if '__sensor_dict__' in value:return {_checkpoint_unpack(k):_checkpoint_unpack(v) for k,v in value['__sensor_dict__']}
        if '__sensor_tuple__' in value:return tuple(_checkpoint_unpack(v) for v in value['__sensor_tuple__'])
        if '__sensor_set__' in value:return set(_checkpoint_unpack(v) for v in value['__sensor_set__'])
    if isinstance(value,list):return [_checkpoint_unpack(v) for v in value]
    return value

