import copy
import json
from pathlib import Path
import numpy as np
import pytest
from maicon_sim.config.loader import load_scenario
from maicon_sim.core.engine import MatchEngine
from maicon_sim.core.types import Pose2
from maicon_sim.core.geometry3d import Primitive,canonical_solids
from maicon_sim.sensors.gateway import SensorGateway,SensorUnavailable
from maicon_sim.sensors.semantic import visible_rectangle,apply_noise
from maicon_sim.sensors.odometry import OdometryModel
from maicon_sim.sensors.imu import ImuModel
from maicon_sim.sensors.lidar import scan

ROOT=Path(__file__).resolve().parents[2]
@pytest.fixture
def setup():
    config=load_scenario(ROOT/'examples/scenario_smoke_six.yaml')
    engine=MatchEngine(config);gateway=SensorGateway(config)
    yield config,engine,gateway
    gateway.close()

def start(engine):
    engine.request('enter_ready',None)
    for s in engine.robots:engine.request('ready',s)
    engine.request('start',None)

def test_D2_cadence_closed_and_open_intervals(setup):
    c,e,g=setup
    for tick in range(101):e.sim_tick=tick;g.update(e)
    assert g.counts['B-1','semantic']==11
    assert g.counts['B-1','odom']==21
    assert g.counts['B-1','imu']==21
    assert g.counts['B-1','state']==3
    # Removing the initial tick gives 10,20,20,2 as required by RENDER-010.
    assert g.get('B-1','state')['captured_tick']==100

def test_ISO_001_ISO_003_sensor_dtos(setup):
    c,e,g=setup;g.update(e)
    forbidden={'ammo','face_id','box_id','sector','score','segmentation','true_pose','world_pose','destroyed','expected_m1'}
    def visit(value):
        if isinstance(value,dict):
            assert not forbidden.intersection(value)
            for child in value.values():visit(child)
        elif isinstance(value,list):
            for child in value:visit(child)
    for channel in ('state','match','odom','imu','scan','semantic'):visit(g.get('B-1',channel))
    assert g.capabilities['rgb'] is False and g.capabilities['semantic'] is True
    with pytest.raises(SensorUnavailable) as exc:g.get('B-1','camera')
    assert exc.value.status==503

def test_ISO_008_hidden_hp_ammo_do_not_change_dto(setup):
    c,e,g=setup;g.update(e);before=g.get('B-1','semantic')
    e.robots['R-1'].hp=0;e.robots['R-1'].ammo=0
    # Same geometry + same capture tick in a fresh gateway produces exactly equal observation.
    h=SensorGateway(c);h.update(e)
    assert h.get('B-1','semantic')==before
    h.close()

def test_T3D17_stationary_imu_gravity(setup):
    c,e,g=setup;g.update(e)
    assert g.get('B-1','imu')['linear_acceleration_mps2']==[0.,0.,9.80665]
    assert g.get('B-1','odom')['local_pose']==dict(x_m=0.,y_m=0.,yaw_rad=0.)

def test_imu_actual_yaw_rate_radians():
    i=ImuModel(Pose2(0,0,0),{},np.random.default_rng(0))
    i.measure(Pose2(0,0,0),0,0,1)
    value=i.measure(Pose2(0,0,.05),5,0,1)
    assert value['angular_velocity_rps'][2]==pytest.approx(1)

def test_D2_S03_GEO_011_occlusion_and_backface():
    origin=np.array([0.,0.,0.]);R=np.eye(3)
    rect=(np.array([0.,0.,2.]),np.array([0.,0.,-1.]),np.array([1.,0.,0.]),np.array([0.,1.,0.]),.2,.2)
    assert visible_rectangle(origin,R,{},rect,[]) is not None
    blocker=Primitive('wall','obb',np.array([0.,0.,1.]),np.array([1.,1.,.1]),np.eye(3))
    assert visible_rectangle(origin,R,{},rect,[blocker]) is None
    away=(rect[0],-rect[1],*rect[2:])
    assert visible_rectangle(origin,R,{},away,[]) is None

def test_RENDER_016_lidar_distance_and_null(setup):
    c,e,g=setup
    e.robots['B-1'].pose=Pose2(1,1,0)
    profile=dict(c.sensors['lidar']);profile['ray_count']=4;profile['angle_min_rad']=0
    wall=Primitive('wall','obb',np.array([2.1,1,.145]),np.array([.1,1,1]),np.eye(3),owner='wall')
    value=scan(e.robots,[wall],'B-1',profile,{},np.random.default_rng(0))
    assert value['ranges_m'][0]==pytest.approx(1,abs=1e-5)
    assert value['ranges_m'][2] is None
    assert 'Infinity' not in json.dumps(value)

def test_odom_accumulates_drift_and_local_origin():
    o=OdometryModel(Pose2(10,20,np.pi/2),{'odom_linear_scale':1.02,'odom_yaw_bias_rps':.005},np.random.default_rng(0))
    o.measure(Pose2(10,20,np.pi/2),0,.2,0)
    value=o.measure(Pose2(10,20.1,np.pi/2),5,.2,0)
    assert value['local_pose']['x_m']==pytest.approx(.102)
    assert abs(value['local_pose']['y_m'])<1e-12
    assert value['local_pose']['yaw_rad']==pytest.approx(.00025)

def test_D2_P02_RENDER_017_reproducible_noise_independent_streams(setup):
    c,e,g=setup;c.scenario['noise_profile']='stress_v1'
    a=SensorGateway(c);b=SensorGateway(c)
    for tick in range(51):e.sim_tick=tick;a.update(e);b.update(e)
    for channel in ('odom','imu','scan','semantic'):assert a.get('B-1',channel)==b.get('B-1',channel)
    # A camera stream's extra draws cannot alter odometry randomness.
    a.rng('B-1','semantic').random(10000)
    e.sim_tick=55;a.update(e);b.update(e)
    assert a.get('B-1','odom')==b.get('B-1','odom')
    a.close();b.close()

def test_stress_confusion_changes_maximum_label():
    candidate={'kind':'object','label':'tank','bbox_xyxy_px':[10,10,30,30]}
    result=apply_noise([candidate],{'semantic_wrong_class_p':1},np.random.default_rng(2))
    assert max(result[0]['class_probs'],key=result[0]['class_probs'].get)!='tank'
    assert sum(result[0]['class_probs'].values())==pytest.approx(1)

def test_dropouts_do_not_retimestamp_stale_frame(setup):
    c,e,g=setup;g.update(e);old=g.get('B-1','semantic')
    e.sensor_dropouts['B-1','camera']=100
    for tick in range(1,31):e.sim_tick=tick;g.update(e)
    assert g.get('B-1','semantic')==old
    assert g.counts['B-1','semantic']==1

def test_D2_S05_RENDER_012_RENDER_013_drone_cache_and_gate(setup):
    c,e,g=setup;start(e);g.update(e)
    first,headers=g.drone(e,'B-1')
    e.destroyed.add('BLUE_RADAR')
    for tick in range(1,151):e.sim_tick=tick;g.update(e)
    second,h2=g.drone(e,'B-1')
    assert second==first and h2['X-Captured-At']==headers['X-Captured-At']
    assert h2['X-Frame-Interval-S']=='2.0'
    e.sim_tick=200;g.update(e);_,h3=g.drone(e,'B-1')
    assert h3['X-Captured-At']!=headers['X-Captured-At']
    e.destroyed.update(('BLUE_COMMS','BLUE_OUTPOST'));e.sim_tick=201;g.update(e)
    with pytest.raises(SensorUnavailable) as exc:g.drone(e,'B-1')
    assert exc.value.status==403
    # Opponent still has intact facilities; delivery remains normal.
    assert g.drone(e,'R-1')[1]['X-Frame-Interval-S']=='1.0'

def test_RENDER_014_RENDER_015_drone_phase_and_test_camera(setup):
    c,e,g=setup;g.update(e)
    with pytest.raises(SensorUnavailable) as exc:g.drone(e,'B-1')
    assert exc.value.status==409
    data,headers=g.drone(e,'B-1',camera='test1',test_mode=True)
    assert data[:2]==b'\xff\xd8' and headers['X-Test-Mode']=='on' and 'X-Camp' not in headers

def test_reset_clears_previous_frames(setup):
    c,e,g=setup;g.update(e)
    e.request('reset',None);g.update(e)
    assert g.get('B-1','odom')['local_pose']==dict(x_m=0.,y_m=0.,yaw_rad=0.)
    assert len(g._pending)==0

def test_GEO_009_D2_S04_face_inventory_manifest_sector(setup):
    from maicon_sim.core.scoring import inventory_from_boxes
    c,e,g=setup
    box=next(b for b in e.boxes if b['box_id']=='box_R1')
    box['faces'].append(dict(side='north',asset_id='object_tank',kind='object',object_class='tank'))
    inventory=inventory_from_boxes(e.boxes)
    assert inventory['R-S1']['TANK']==2
    # The camera stands in a different declared sector; truth attribution remains manifest based.
    e.robots['B-1'].pose=Pose2(3.06,4.2,0)
    g.update(e)
    assert inventory_from_boxes(e.boxes)['R-S1']['TANK']==2
    encoded=json.dumps(g.get('B-1','semantic'))
    assert 'box_R1' not in encoded and 'face_id' not in encoded and 'sector' not in encoded

def test_drone_dropout_repeats_last_good_bytes(setup):
    c,e,g=setup;start(e);g.update(e);data,headers=g.drone(e,'B-1')
    e.sensor_dropouts['B-1','drone']=250
    for tick in range(1,201):e.sim_tick=tick;g.update(e)
    repeated,h2=g.drone(e,'B-1')
    assert repeated==data and h2['X-Captured-At']==headers['X-Captured-At']

def test_pending_camera_delivery_is_suppressed_during_dropout(setup):
    c,e,g=setup;c.scenario['noise_profile']='stress_v1';g=SensorGateway(c)
    g.update(e)
    assert ('B-1','semantic') in g._pending
    e.sensor_dropouts['B-1','camera']=100
    e.sim_tick=10;g.update(e)
    with pytest.raises(SensorUnavailable):g.get('B-1','semantic')
    assert g.dropped>=1
    g.close()

@pytest.mark.render
def test_T3D_09_RENDER_010_actual_rgb_sensor_cadence(setup):
    from maicon_sim.backends.bullet.backend import BulletBackend
    c,e,_=setup
    backend=BulletBackend(c);gateway=SensorGateway(c,backend);gateway.camera_slots={'B-1'}
    try:
        for tick in range(101):e.sim_tick=tick;gateway.update(e)
        assert gateway.counts['B-1','camera']==11
        assert gateway.counts['B-1','odom']==21
        assert gateway.counts['B-1','imu']==21
        assert gateway.counts['B-1','state']==3
        assert gateway.counts['B-2','camera']==0
        frame=gateway.get_frame('B-1')
        assert frame['data'].shape==(480,640,3) and frame['data'].dtype==np.uint8
        assert frame['captured_tick']==100 and frame['received_tick']==100
        assert gateway.capabilities['semantic'] is False
        with pytest.raises(SensorUnavailable) as exc:gateway.get('B-1','semantic')
        assert exc.value.status==409
    finally:gateway.close()

def test_RENDER_009_lidar_other_robot_mast_self_excluded(setup):
    c,e,g=setup
    e.robots['B-1'].pose=Pose2(1,1,0)
    e.robots['R-1'].pose=Pose2(2,1,0)
    profile=dict(c.sensors['lidar']);profile['angle_min_rad']=0;profile['ray_count']=4
    solids=canonical_solids({'B-1':e.robots['B-1'],'R-1':e.robots['R-1']},[],c.arena['bounds'],c.sensors['geometry'])
    result=scan(e.robots,solids,'B-1',profile,{},np.random.default_rng(0))
    # LiDAR z=.145 is above chassis top.13; other mast starts.13.
    assert result['ranges_m'][0]==pytest.approx(.935,abs=1e-9)
    assert min(x for x in result['ranges_m'] if x is not None)>.3

def test_stale_drone_repeat_does_not_extend_new_frame_gate(setup):
    c,e,g=setup;start(e);g.update(e);_,initial=g.drone(e,'B-1')
    e.sensor_dropouts['all','drone']=300
    for tick in range(1,251):e.sim_tick=tick;g.update(e)
    _,stale=g.drone(e,'B-1')
    assert stale['X-Captured-At']==initial['X-Captured-At']
    assert g._drone_gate['camp','BLUE']==0
    e.sim_tick=300;g.update(e)
    _,fresh=g.drone(e,'B-1')
    assert fresh['X-Captured-At']!=initial['X-Captured-At']

def test_REPLAY_005_noisy_sensor_checkpoint_continuation(setup):
    c,e,_=setup;c.scenario['noise_profile']='stress_v1'
    continuous=SensorGateway(c)
    start(e)
    for tick in range(36):
        e.sim_tick=tick
        e.robots['B-1'].pose=Pose2(.4+.001*tick,4.2,.0001*tick)
        continuous.update(e)
    engine_state=json.loads(json.dumps(e.export_state()))
    sensor_state=json.loads(json.dumps(continuous.export_state()))
    restored_engine=MatchEngine(c);restored_engine.restore_state(engine_state)
    restored=SensorGateway(c);restored.restore_state(sensor_state)
    for tick in range(36,81):
        for engine,gateway in ((e,continuous),(restored_engine,restored)):
            engine.sim_tick=tick;engine.robots['B-1'].pose=Pose2(.4+.001*tick,4.2,.0001*tick);gateway.update(engine)
        for channel in ('state','match','odom','imu','scan','semantic'):
            assert restored.get('B-1',channel)==continuous.get('B-1',channel)
    assert dict(restored.counts)==dict(continuous.counts)
    assert restored.dropped==continuous.dropped
    continuous.close();restored.close()

def test_public_reads_do_not_wait_for_sensor_writer(setup):
    import threading,time
    c,e,g=setup;g.update(e)
    held=threading.Event();release=threading.Event()
    def writer():
        with g._lock:
            held.set();release.wait(2)
    thread=threading.Thread(target=writer);thread.start();assert held.wait(1)
    try:
        begin=time.monotonic();observation=g.get('B-1','scan');elapsed=time.monotonic()-begin
        assert len(observation['ranges_m'])==360
        assert elapsed<.1
    finally:release.set();thread.join(2)
    assert not thread.is_alive()

@pytest.mark.render
def test_T3D_10_actual_drone_delivery_gate(setup):
    from maicon_sim.backends.bullet.backend import BulletBackend
    c,e,_=setup;start(e);gateway=SensorGateway(c,BulletBackend(c));gateway.camera_slots=set()
    try:
        gateway.update(e);first,h0=gateway.drone(e,'B-1')
        e.destroyed.add('BLUE_RADAR')
        for tick in (100,150,199):
            e.sim_tick=tick;gateway.update(e);data,headers=gateway.drone(e,'B-1')
            assert data==first and headers['X-Captured-At']==h0['X-Captured-At']
            assert headers['X-Frame-Interval-S']=='2.0'
        e.sim_tick=200;gateway.update(e);_,h2=gateway.drone(e,'B-1')
        assert h2['X-Captured-At']!=h0['X-Captured-At']
        e.destroyed.update(('BLUE_COMMS','BLUE_OUTPOST'));e.sim_tick=201;gateway.update(e)
        with pytest.raises(SensorUnavailable) as exc:gateway.drone(e,'B-1')
        assert exc.value.status==403
    finally:gateway.close()

@pytest.mark.render
def test_T3D_11_analytic_laser_199_200_2d_3d_parity(setup):
    from maicon_sim.backends.bullet.backend import BulletBackend
    from maicon_sim.core.geometry3d import laser_transform
    c,_,_=setup
    outcomes=[]
    for backend_kind in ('2d','3d'):
        engine=MatchEngine(c);start(engine)
        gateway=SensorGateway(c,BulletBackend(c) if backend_kind=='3d' else None);gateway.camera_slots=set()
        try:
            robot=engine.robots['B-1'];target=np.array([1.479,4.2,.35]);lo,hi=-100.,100.
            for _ in range(60):
                mid=(lo+hi)/2;origin,direction=laser_transform(robot.pose,0,mid,c.sensors['geometry'])
                projected=origin[2]+(target[0]-origin[0])*direction[2]/direction[0]
                if projected<target[2]:lo=mid
                else:hi=mid
            robot.tilt=robot.target_tilt=(lo+hi)/2
            engine.request('fire','B-1')
            for _ in range(199):engine.step();gateway.update(engine)
            assert not engine.destroyed
            engine.step();gateway.update(engine)
            assert engine.destroyed=={'BLUE_RADAR'}
            engine.request('stop',None)
            events=[(v['kind'],v['sim_tick'],v['match_elapsed_ticks'],v['payload']) for v in engine.journal if v['kind'] in ('facility_destroyed','hit_applied','laser_fired')]
            outcomes.append((engine.result(),events,[r.hp for r in engine.robots.values()],[r.pose for r in engine.robots.values()]))
        finally:gateway.close()
    assert outcomes[0]==outcomes[1]
