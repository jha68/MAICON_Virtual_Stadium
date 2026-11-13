"""CPU-only 3D sensing over the shared planar engine's immutable snapshots.

Bullet never integrates simulation dynamics and has no scoring authority.
"""
from __future__ import annotations
import copy
import hashlib
import json
from importlib.metadata import version
import math
from pathlib import Path
import tempfile
import threading
import time
from collections import defaultdict
import numpy as np

from maicon_sim.core.geometry3d import camera_transform
from .asset_builder import ResolvedAssets,resolve_assets,load_resolved_assets
from .projection import projection_matrix,metric_depth,apply_fog
from .scene import BulletScene


class BulletBackend:
    capabilities={'rgb':True,'semantic':False,'lidar':True,'depth':False}
    asynchronous=False

    def __init__(self,config,resolved_assets=None,headless=True):
        import pybullet as p
        self._bullet_version=version('pybullet')
        self.p=p;self.config=config;self.owner=threading.get_ident();self.closed=False
        self.headless=bool(headless);self._gui_hud_id=-1;self._last_gui_hud=None
        self._temporary=None;self._sequence=defaultdict(int);self._cache={};self._private={};self._scene_key=None
        self.latencies=[];self.render_latencies=[];self.capture_count=0;self.cache_hits=0
        if resolved_assets is None:
            self._temporary=tempfile.TemporaryDirectory(prefix='maicon-render-assets-')
            resolved_assets=resolve_assets(config.assets,self._temporary.name,base_dir=config.path.parent)
        elif isinstance(resolved_assets,(str,Path)):
            resolved_assets=load_resolved_assets(resolved_assets,config.assets)
        self.assets=resolved_assets
        self.client=p.connect(p.DIRECT if headless else p.GUI)
        if self.client<0:raise RuntimeError('PyBullet connection failed; use --headless without a display')
        try:
            if not self.headless:
                # Software OpenGL must not redraw188bodies after every creation.
                p.configureDebugVisualizer(p.COV_ENABLE_RENDERING,0,physicsClientId=self.client)
                # Native preview panes otherwise obscure half of a software GUI.
                # Orbit/zoom remain mouse controlled; companion observer has panels.
                p.configureDebugVisualizer(p.COV_ENABLE_GUI,0,physicsClientId=self.client)
            self.scene=BulletScene(p,self.client,config,self.assets)
            self.scene.validate()
            self._body_count=p.getNumBodies(physicsClientId=self.client)
            self.snapshot={'robots':{a['slot']:{'pose':copy.deepcopy(a['start_pose']),'pan':0.,'tilt':0.,'hp':4,'ammo':8} for a in config.scenario['agents']},'boxes':copy.deepcopy(config.scenario['boxes'])}
            self.sync_scene(self.snapshot)
            if not self.headless:
                bounds=config.arena['bounds']
                p.resetDebugVisualizerCamera(cameraDistance=max(bounds['width_m'],bounds['height_m']),
                    cameraYaw=45,cameraPitch=-55,
                    cameraTargetPosition=[bounds['width_m']/2,bounds['height_m']/2,0],physicsClientId=self.client)
                p.configureDebugVisualizer(p.COV_ENABLE_RENDERING,1,physicsClientId=self.client)
        except BaseException:
            p.disconnect(self.client)
            if self._temporary:self._temporary.cleanup()
            raise

    @property
    def metadata(self):
        return {'renderer':'PyBullet DIRECT/TinyRenderer' if self.headless else 'PyBullet GUI/TinyRenderer',
            'connection_mode':'DIRECT' if self.headless else 'GUI','api_version':self.p.getAPIVersion(),
            'package_version':self._bullet_version,
            'body_count':self.p.getNumBodies(physicsClientId=self.client) if not self.closed else self._body_count,
            'registry_count':len(self.scene.registry),
            'fidelity':'SIM-3D-FIDELITY/shared_planar','fog_model':self.config.sensors['render'].get('fog_model','full_scene'),
            'fog_volume_world_aabb_m':self.config.sensors['render'].get('fog_volume_world_aabb_m'),
            'identical_scene_render_cache':True,'cache_hits':self.cache_hits,'captures':self.capture_count}

    @property
    def metrics(self):
        def summary(values):
            return {'count':len(values),**{f'p{q}':float(np.percentile(values,q)*1000) if values else 0. for q in (50,95,99)}}
        return {'render_latency_ms':summary(self.render_latencies),'capture_latency_ms':summary(self.latencies),
            'captures':self.capture_count,'cache_hits':self.cache_hits,'cached_scene_reuse':True}

    def _assert_owner(self):
        if self.closed:raise RuntimeError('Bullet backend is closed')
        if threading.get_ident()!=self.owner:raise RuntimeError('Bullet connection must be used only by its owning worker')

    def reset_session(self,snapshot=None):
        self._assert_owner();self._sequence.clear();self._cache.clear();self._private.clear();self._scene_key=None
        if snapshot is not None:self.sync_scene(snapshot)

    def sync_scene(self,snapshot):
        self._assert_owner()
        if not self.headless:
            phase=snapshot.get('phase','waiting');tick=int(snapshot.get('sim_tick',0))
            signature=(phase,bool(snapshot.get('paused',False)),tick//20)
            if signature!=self._last_gui_hud:
                self._last_gui_hud=signature
                match=int(snapshot.get('match_elapsed_ticks',0))*.01
                report=int(snapshot.get('reporting_elapsed_ticks',0))*.01
                pause=' PAUSED' if snapshot.get('paused') else ''
                text=f'OBSERVER  {phase}{pause}  sim {tick*.01:.2f}s  match {match:.2f}s  report {report:.2f}s'
                bounds=self.config.arena['bounds']
                self._gui_hud_id=self.p.addUserDebugText(text,[.1,bounds['height_m']-.1,.8],
                    textColorRGB=[1,1,1],textSize=1.2,lifeTime=0,replaceItemUniqueId=self._gui_hud_id,physicsClientId=self.client)
        # Capture no mutable engine references. Tick fields do not change geometry.
        robots={slot:{k:copy.deepcopy(value[k]) for k in ('pose','pan','tilt','hp','ammo') if k in value} for slot,value in snapshot['robots'].items()}
        boxes=copy.deepcopy(snapshot.get('boxes',self.config.scenario['boxes']))
        current={'robots':robots,'boxes':boxes,
                 'destroyed':copy.deepcopy(snapshot.get('destroyed',[])),
                 'facility_signals':copy.deepcopy(snapshot.get('facility_signals',{}))}
        key=hashlib.sha256(json.dumps(current,sort_keys=True,allow_nan=False).encode()).digest()
        self.snapshot=current
        if key!=self._scene_key:
            self.scene.sync(current);self._scene_key=key;self._cache.clear();self._private.clear()

    def _capture(self,camera_id,tick,origin,rotation,intrinsics):
        self._assert_owner();p=self.p;c=self.client
        self._sequence[camera_id]+=1;self.capture_count+=1
        key=(camera_id,tuple(np.asarray(origin)),tuple(np.asarray(rotation).flat),json.dumps(intrinsics,sort_keys=True),json.dumps(self.config.sensors['render'],sort_keys=True))
        started=time.monotonic()
        if key in self._cache:
            rgb,depth,segmentation=self._cache[key];self.cache_hits+=1
        else:
            render=self.config.sensors['render'];origin=np.asarray(origin);rotation=np.asarray(rotation)
            view=p.computeViewMatrix(origin.tolist(),(origin+rotation[:,2]).tolist(),(-rotation[:,1]).tolist())
            image=p.getCameraImage(intrinsics['width_px'],intrinsics['height_px'],view,projection_matrix(intrinsics),
                renderer=p.ER_TINY_RENDERER,flags=p.ER_SEGMENTATION_MASK_OBJECT_AND_LINKINDEX,
                lightDirection=render['light_direction_world'],lightAmbientCoeff=render['ambient'],
                lightDiffuseCoeff=render['diffuse'],lightSpecularCoeff=0,shadow=0,physicsClientId=c)
            rgba=np.asarray(image[2],dtype=np.uint8).reshape(intrinsics['height_px'],intrinsics['width_px'],4)
            depth=metric_depth(np.asarray(image[3]).reshape(intrinsics['height_px'],intrinsics['width_px']),intrinsics['near_m'],intrinsics['far_m'])
            segmentation=np.asarray(image[4],dtype=np.int32).reshape(intrinsics['height_px'],intrinsics['width_px'])
            rgb=apply_fog(rgba[...,:3],depth,origin,rotation,intrinsics,render)
            self._cache[key]=(rgb,depth,segmentation)
            self.render_latencies.append(time.monotonic()-started)
            if len(self.render_latencies)>10000:self.render_latencies=self.render_latencies[-10000:]
        self.latencies.append(time.monotonic()-started)
        # Latency history is bounded; episodes do not accumulate RGB arrays.
        if len(self.latencies)>10000:self.latencies=self.latencies[-10000:]
        self._private[camera_id]={'depth_m':depth,'invalid_mask':segmentation<0,'segmentation':segmentation,
            'face_body_ids':dict(self.scene.faces),'captured_tick':int(tick)}
        data=np.ascontiguousarray(rgb[...,::-1]);data.flags.writeable=False
        return {'sequence':self._sequence[camera_id],'captured_tick':int(tick),'received_tick':int(tick),
            'camera_id':camera_id,'width_px':int(intrinsics['width_px']),'height_px':int(intrinsics['height_px']),
            'encoding':'bgr8','data':data}

    def capture_rgb(self,camera_id,tick):
        slot=camera_id.split('/')[0]
        if slot not in self.snapshot['robots']:raise ValueError('unknown own camera slot')
        robot=self.snapshot['robots'][slot]
        origin,rotation=camera_transform(robot['pose'],robot.get('pan',0),robot.get('tilt',0),self.config.sensors['geometry'])
        return self._capture(slot+'/front',tick,origin,rotation,self.config.sensors['front_camera'])

    def capture_drone(self,tick):
        d=self.config.sensors['drone'];origin=np.array(d['position_world_m'],dtype=float)
        forward=np.array(d['look_at_world_m'])-origin;forward/=np.linalg.norm(forward)
        right=np.cross(forward,np.array(d['up_world'],dtype=float));right/=np.linalg.norm(right)
        down=np.cross(forward,right);rotation=np.column_stack((right,down,forward))
        fx=d['width_px']/(2*math.tan(math.radians(d['hfov_deg'])/2))
        k={'width_px':d['width_px'],'height_px':d['height_px'],'fx_px':fx,'fy_px':fx,
           'cx_px':(d['width_px']-1)/2,'cy_px':(d['height_px']-1)/2,'near_m':d['near_m'],'far_m':d['far_m']}
        return self._capture('main',tick,origin,rotation,k)

    def capture_pose(self,origin,rotation,intrinsics=None,tick=0,camera_id='_fixture'):
        """Evaluator fixture camera; not a public API endpoint."""
        return self._capture(camera_id,tick,origin,rotation,intrinsics or self.config.sensors['front_camera'])

    def private_capture(self,camera_id):
        self._assert_owner()
        return copy.deepcopy(self._private[camera_id])

    def raycast_batch(self,rays):
        self._assert_owner();origins=[];ends=[]
        for ray in rays:
            origin=np.asarray(ray['origin'] if isinstance(ray,dict) else ray[0]);direction=np.asarray(ray['direction'] if isinstance(ray,dict) else ray[1]);maximum=ray.get('max_distance',10) if isinstance(ray,dict) else (ray[2] if len(ray)>2 else 10)
            direction=direction/np.linalg.norm(direction);origins.append(origin.tolist());ends.append((origin+direction*maximum).tolist())
        reverse={body:key for key,body in self.scene.registry.items()}
        result=self.p.rayTestBatch(origins,ends,physicsClientId=self.client)
        return [{'body_id':hit[0],'geometry_id':reverse.get(hit[0]),'fraction':hit[2],
                 'position':hit[3],'normal':hit[4]} for hit in result]

    def close(self):
        if self.closed:return
        self._assert_owner();self.p.disconnect(self.client);self.closed=True;self._cache.clear();self._private.clear()
        if self._temporary:self._temporary.cleanup()

    def __enter__(self):return self
    def __exit__(self,*args):self.close()
