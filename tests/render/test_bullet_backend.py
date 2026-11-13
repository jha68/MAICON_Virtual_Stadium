"""Actual DIRECT/TinyRenderer acceptance, no rendering skips or oracle detector."""
from __future__ import annotations
import copy
import hashlib
import math
import time
from pathlib import Path

import numpy as np
import pytest
from PIL import Image,ImageDraw

from maicon_sim.config.loader import load_scenario
from maicon_sim.core.geometry3d import R_BO,camera_transform,project_points,rotation_z
from maicon_sim.backends.bullet.backend import BulletBackend
from maicon_sim.backends.bullet.render_worker import AsyncBulletBackend
from maicon_sim.backends.bullet.asset_builder import OBJECT_LABELS
from maicon_sim.backends.bullet.projection import apply_fog,fog_path_lengths
from maicon_sim.perception.synthetic_template import SyntheticTemplateDetector

pytestmark=pytest.mark.render

@pytest.fixture
def config():
    return load_scenario('examples/scenario_perception_gallery.yaml')


def test_RENDER_001_ISO_002_T3D12_direct_bgr_private_boundary(config):
    """RENDER-001, ISO-002, T3D-12."""
    with BulletBackend(config) as backend:
        frame=backend.capture_rgb('B-1/front',0)
        assert frame['data'].shape==(480,640,3) and frame['data'].dtype==np.uint8
        assert frame['data'].std()>5
        assert set(frame)=={'sequence','captured_tick','received_tick','camera_id','width_px','height_px','encoding','data'}
        private=backend.private_capture('B-1/front')
        assert 'segmentation' in private and 'depth_m' in private
        assert len(private['face_body_ids'])==14
        assert not any(word in frame for word in ('segmentation','depth_m','face_id','hp','ammo','score'))
        assert backend.capture_drone(0)['data'].shape==(1024,1280,3)


def test_RENDER_002_T3D01_T3D02_T3D03_T3D04_projection_pan_tilt(config):
    """T3D-01..04, RENDER-002/003/006 numerical branch."""
    k=config.sensors['front_camera']
    pixels,depth=project_points([[0,0,1],[.1,0,1],[0,.1,1],[.5,0,2]],np.zeros(3),np.eye(3),k)
    np.testing.assert_allclose(pixels,[[319.5,239.5],[351.5,239.5],[319.5,271.5],[399.5,239.5]],atol=1e-6)
    for pan,tilt in ((20,0),(0,20)):
        _,R=camera_transform({'x_m':0,'y_m':0,'yaw_rad':0},pan,tilt,config.sensors['geometry'])
        forward=R[:,2]
        if pan:assert math.atan2(forward[1],forward[0])==pytest.approx(math.radians(-10),abs=1e-9)
        else:assert math.asin(forward[2])==pytest.approx(math.radians(3),abs=1e-9)


def test_RENDER_003_004_T3D05_metric_depth_plane_and_landmark(config):
    """T3D-05 and RENDER-003/004 actual depth/landmark pixels."""
    config.sensors['render'].update(ambient=1.,diffuse=0.)
    with BulletBackend(config) as backend:
        plane=backend.scene._box('_depth_plane',[.01,.6,.6],[3.01,1.,.8],[1,1,1,1])
        frame=backend.capture_pose([1.,1.,.8],R_BO,tick=0)
        private=backend.private_capture('_fixture')
        assert private['depth_m'][240,320]==pytest.approx(2.,abs=.001)
        # A distinct red landmark .5m optical-right at2m, near plane front.
        backend.scene._sphere('_landmark',.018,[2.99,.5,.8],[1,0,0,1]);backend._cache.clear()
        frame=backend.capture_pose([1.,1.,.8],R_BO,tick=1)
        bgr=frame['data'];red=(bgr[...,2]>230)&(bgr[...,1]<20)&(bgr[...,0]<20)
        ys,xs=np.nonzero(red)
        assert len(xs)>0
        assert np.mean(xs)==pytest.approx(399.5,abs=2)
        assert np.mean(ys)==pytest.approx(239.5,abs=2)


@pytest.mark.parametrize('side', ['east','west','north','south'])
def test_RENDER_005_008_T3D06_uv_and_color_quadrants(config,tmp_path,side):
    """T3D-06, RENDER-005/008: all four U/V directions and BGR."""
    config.sensors['render'].update(ambient=1.,diffuse=0.)
    image=Image.new('RGB',(128,128));d=ImageDraw.Draw(image)
    d.rectangle((0,0,63,63),fill=(255,0,0));d.rectangle((64,0,127,63),fill=(0,255,0))
    d.rectangle((0,64,63,127),fill=(0,0,255));d.rectangle((64,64,127,127),fill=(255,255,0))
    path=tmp_path/'quad.png';image.save(path)
    from maicon_sim.core.geometry3d import FACE_AXES
    normal,u,v,_,_=FACE_AXES[side];normal=np.array(normal);u=np.array(u);v=np.array(v)
    # Above all scenario boxes; no unrelated visual collider can hide the patch.
    center=np.array([3.,2.5,1.1]);origin=center+normal*1.
    rotation=np.column_stack([u,-v,-normal])
    with BulletBackend(config) as backend:
        backend.scene._quad('_quad',center,u,v,.6,.6,texture=path)
        frame=backend.capture_pose(origin,rotation)
        data=frame['data']
        np.testing.assert_allclose(data[200,280],[0,0,255],atol=2)
        np.testing.assert_allclose(data[200,360],[0,255,0],atol=2)
        np.testing.assert_allclose(data[280,280],[255,0,0],atol=2)
        np.testing.assert_allclose(data[280,360],[0,255,255],atol=2)


@pytest.mark.parametrize('label',OBJECT_LABELS)
def test_actual_rendered_rgb_gallery(config,label):
    """VISION-001: all six actual front-facing rendered fixture classes."""
    face=config.scenario['boxes'][0]['faces'][0]
    assert face['side']=='east'
    face.update(asset_id='object_'+label,object_class=label)
    with BulletBackend(config) as backend:
        frame=backend.capture_rgb('B-1/front',0)
        detections=SyntheticTemplateDetector().detect(frame['data'])
        assert len(detections)==1,detections
        assert max(detections[0]['class_probs'],key=detections[0]['class_probs'].get)==label


def test_RENDER_007_T3D07_T3D08_full_partial_occlusion_keeps_private_inventory(config):
    """T3D-07/08 and RENDER-007: visible mask changes, inventory doesn't."""
    with BulletBackend(config) as backend:
        backend.capture_rgb('B-1/front',0)
        target=backend.scene.faces['box_B1/east']
        original=backend.private_capture('B-1/front')['segmentation']
        full=np.count_nonzero(original==target);assert full>100
        obstacle=backend.scene._box('_occluder',[.03,.25,.25],[2.18,4.2,.23],[.2,.2,.2,1])
        backend._cache.clear();backend.capture_rgb('B-1/front',1)
        hidden=backend.private_capture('B-1/front')['segmentation']
        assert np.count_nonzero(hidden==target)==0
        backend.p.resetBasePositionAndOrientation(obstacle,[2.18,4.45,.23],[0,0,0,1],physicsClientId=backend.client)
        backend._cache.clear();backend.capture_rgb('B-1/front',2)
        partial=np.count_nonzero(backend.private_capture('B-1/front')['segmentation']==target)
        assert 0<partial<full
        assert len(config.scenario['boxes'][0]['faces'])==2 and len(backend.scene.faces)==14


def test_RENDER_020_T3D14_scene_sync_no_dynamics_hash_and_close(config):
    """RENDER-020, T3D-14/18."""
    with BulletBackend(config) as backend:
        snapshot=copy.deepcopy(backend.snapshot);snapshot['robots']['B-1']['pose']['x_m']=2.4
        before=copy.deepcopy(snapshot);backend.sync_scene(snapshot)
        assert snapshot==before
        chassis=backend.scene.registry['B-1/chassis']
        position,_=backend.p.getBasePositionAndOrientation(chassis,physicsClientId=backend.client)
        assert position[0]==pytest.approx(2.4,abs=1e-12)
        a=backend.capture_rgb('B-1/front',10);b=backend.capture_rgb('B-1/front',20)
        assert hashlib.sha256(a['data']).digest()==hashlib.sha256(b['data']).digest()
        assert a['captured_tick']==10 and b['captured_tick']==20
        assert backend.cache_hits>=1
    assert backend.closed
    backend.close()  # explicitly idempotent


def test_reopen_ten_connections(config):
    """B3-01 connection/body ownership reset without leaking bodies."""
    counts=[]
    for _ in range(10):
        with BulletBackend(config) as backend:
            counts.append(backend.p.getNumBodies(physicsClientId=backend.client))
            assert backend.capture_rgb('B-1/front',0)['data'].std()>5
    assert len(set(counts))==1


def test_RENDER_018_T3D16_fog_identity_volume_and_contrast(config):
    """FOG-001/002, T3D-16, RENDER-018: photometry only."""
    k={'width_px':3,'height_px':1,'fx_px':1000.,'fy_px':1000.,'cx_px':1.,'cy_px':0.,'near_m':.02,'far_m':10.}
    rgb=np.array([[[0,0,0],[100,100,100],[255,255,255]]],np.uint8);depth=np.full((1,3),3.)
    render=copy.deepcopy(config.sensors['render']);render.update(fog_enabled=True,fog_density_per_m=0.)
    assert np.array_equal(apply_fog(rgb,depth,np.zeros(3),np.eye(3),k,render),rgb)
    render.update(fog_model='volume',fog_volume_world_aabb_m=[[-1,-1,1],[1,1,2]],fog_density_per_m=.8)
    path=fog_path_lengths(depth,np.zeros(3),np.eye(3),k,render['fog_volume_world_aabb_m'])
    np.testing.assert_allclose(path,np.ones((1,3)),atol=1e-6)
    output=apply_fog(rgb,depth,np.zeros(3),np.eye(3),k,render)
    assert output.std()<rgb.std()
    depth_front=np.full((1,3),.5)
    assert np.array_equal(apply_fog(rgb,depth_front,np.zeros(3),np.eye(3),k,render),rgb)


def test_RENDER_011_T3D15_bounded_async_worker_delay_and_generation_reset(config):
    """T3D-15/18, RENDER-011: caller does not await500ms rendering."""
    with AsyncBulletBackend(config,render_delay_s=.5) as backend:
        snapshot={'robots':{a['slot']:{'pose':a['start_pose'],'pan':0.,'tilt':0.} for a in config.scenario['agents']}}
        backend.sync_scene(snapshot)
        started=time.monotonic()
        for tick in range(30):backend.request_capture('B-1/front',tick)
        assert time.monotonic()-started<.2
        assert backend.pending_count<=1 and backend.dropped>=28
        # Discard pending and in-flight results of previous generation.
        backend.reset_session(snapshot)
        backend.request_capture('B-1/front',100)
        deadline=time.monotonic()+3
        frames=[]
        while time.monotonic()<deadline and not frames:
            time.sleep(.02);frames=backend.poll_completed()
        assert frames and all(frame['captured_tick']==100 for frame in frames)
        assert backend.last_error is None
    assert not backend._thread.is_alive()


def test_RENDER_006_combined_pan_tilt_actual_landmark(config):
    config.sensors['render'].update(ambient=1.,diffuse=0.)
    with BulletBackend(config) as backend:
        snapshot=copy.deepcopy(backend.snapshot)
        snapshot['robots']['B-1'].update(pose={'x_m':1.,'y_m':1.4,'yaw_rad':0.},pan=20.,tilt=20.)
        backend.sync_scene(snapshot)
        robot=snapshot['robots']['B-1'];origin,R=camera_transform(robot['pose'],20.,20.,config.sensors['geometry'])
        point=origin+R@np.array([.5,0,2.])
        backend.scene._sphere('_red_landmark',.018,point,[1,0,0,1]);backend._cache.clear()
        frame=backend.capture_rgb('B-1/front',1);bgr=frame['data']
        ys,xs=np.nonzero((bgr[...,2]>240)&(bgr[...,1]<15)&(bgr[...,0]<15))
        assert len(xs)>0
        assert np.mean(xs)==pytest.approx(399.5,abs=2)
        assert np.mean(ys)==pytest.approx(239.5,abs=2)


def test_RENDER_009_rgb_own_body_occludes(config):
    # Explicit calibration fixture moves the optical origin behind the chassis.
    # Default forward camera need not see its own solid at its limited tilt.
    config.sensors['geometry']['camera_offset_gimbal_m']=[-.22,0,0]
    with BulletBackend(config) as backend:
        snapshot=copy.deepcopy(backend.snapshot);snapshot['robots']['B-1']['tilt']=-100.
        backend.sync_scene(snapshot);backend.capture_rgb('B-1/front',0)
        mask=backend.private_capture('B-1/front')['segmentation']
        own_ids=[body for name,body in backend.scene.registry.items() if name.startswith('B-1/')]
        assert np.isin(mask,own_ids).sum()>100
        # A pixel really belongs to self mesh; no semantic overlay was composited.
        assert any((mask==backend.scene.registry['B-1/'+part]).any() for part in ('chassis','mast'))


def test_T3D05_depth_rgb_mask_boundaries_one_pixel(config):
    config.sensors['render'].update(ambient=1.,diffuse=0.)
    with BulletBackend(config) as backend:
        plane=backend.scene._box('_precision_plane',[.01,.3,.3],[3.01,1.,.8],[1,0,0,1])
        frame=backend.capture_pose([1,1,.8],R_BO)
        private=backend.private_capture('_fixture');mask=private['segmentation']==plane
        bgr=frame['data'];red=(bgr[...,2]>240)&(bgr[...,1]<15)&(bgr[...,0]<15)
        assert np.array_equal(mask,red)
        ys,xs=np.nonzero(mask)
        # Optical corners(±.3,±.3,2) -> [271.5,191.5]..[367.5,287.5].
        assert abs(xs.min()-271.5)<=1 and abs(xs.max()-367.5)<=1
        assert abs(ys.min()-191.5)<=1 and abs(ys.max()-287.5)<=1
        assert private['depth_m'][240,320]==pytest.approx(2.,abs=.001)


def test_RENDER_011_T3D15_core_heartbeat_during_500ms_renderer(config):
    from maicon_sim.core.engine import MatchEngine
    from maicon_sim.sensors.gateway import SensorGateway
    with AsyncBulletBackend(config,render_delay_s=.5) as backend:
        engine=MatchEngine(config);gateway=SensorGateway(config,backend);gateway.camera_slots={'B-1'}
        engine.request('enter_ready')
        for slot in engine.robots:engine.request('ready',slot)
        engine.request('start')
        gateway.update(engine)  # initialize sensor models before timing
        started=time.monotonic();heartbeats=[]
        for tick in range(100):
            target=started+tick*.01
            remaining=target-time.monotonic()
            if remaining>0:time.sleep(remaining)
            if tick%10==0:
                engine.request('cmd_vel','B-1',{'linear_x_mps':0.,'angular_z_rps':0.})
                heartbeats.append(time.monotonic())
            engine.step();gateway.update(engine)
        elapsed=time.monotonic()-started
        assert engine.sim_tick==100 and engine.match_elapsed_ticks==100
        assert elapsed<1.5
        assert max(np.diff(heartbeats))<.5
        assert engine.robots['B-1'].last_velocity_received_tick>=90
        assert backend.pending_count<=2  # one front and one drone, bounded by camera count
        assert backend.last_error is None


def test_T3D18_restart_same_scene_new_session_discards_frames(config):
    from maicon_sim.core.engine import MatchEngine
    from maicon_sim.sensors.gateway import SensorGateway
    engine=MatchEngine(config);engine.request('enter_ready')
    with BulletBackend(config) as backend:
        gateway=SensorGateway(config,backend);gateway.camera_slots={'B-1'}
        gateway.update(engine);first=gateway.get_frame('B-1')
        count=backend.p.getNumBodies(physicsClientId=backend.client)
        # Construct, initialize and close two real participant lifecycles.
        import asyncio
        from maicon_sim.policies.controller import TeamController
        from maicon_sim.sdk.in_process_port import InProcessPort
        async def restart_participant():
            controller=TeamController(InProcessPort(engine,'B-1',gateway),'B-1','mission')
            await controller.initialize()
            assert controller.session_identity['match_id']==engine.match_id
            await controller.close()
        for _ in range(2):
            asyncio.run(restart_participant())
            assert gateway.get_frame('B-1')['captured_tick']==first['captured_tick']
            assert backend.p.getNumBodies(physicsClientId=backend.client)==count
        old=engine.match_id;engine.request('reset')
        assert engine.match_id!=old
        gateway.update(engine)
        fresh=gateway.get_frame('B-1')
        assert fresh['sequence']==1 and fresh['captured_tick']==engine.sim_tick
        assert backend.p.getNumBodies(physicsClientId=backend.client)==count


def test_RENDER_016_canonical_solid_and_bullet_proxy_distance(config):
    """Debug Bullet rays agree with shared analytic solids, never decide scores."""
    from types import SimpleNamespace
    from maicon_sim.core.geometry3d import canonical_solids,raycast
    robots={a['slot']:SimpleNamespace(pose=a['start_pose']) for a in config.scenario['agents']}
    shapes=canonical_solids(robots,config.scenario['boxes'],config.arena['bounds'],config.sensors['geometry'])
    rays=[{'origin':[2.5,4.2,.3],'direction':[-1,0,0],'max_distance':5},
          {'origin':[3.,1.4,.145],'direction':[0,-1,0],'max_distance':5}]
    with BulletBackend(config) as backend:
        hits=backend.raycast_batch(rays)
        for request,hit in zip(rays,hits):
            analytic=raycast(request['origin'],request['direction'],shapes,max_distance=request['max_distance'])
            assert analytic is not None and hit['body_id']>=0
            assert hit['fraction']*request['max_distance']==pytest.approx(analytic.distance,abs=1e-6)
