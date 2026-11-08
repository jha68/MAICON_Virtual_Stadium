import math
from types import SimpleNamespace
import numpy as np
import pytest
from maicon_sim.core.types import Pose2,RobotTruth
from maicon_sim.core.geometry2d import obb_corners,sat_intersects,convex_hull,segment_intersects_polygon,point_in_polygon,polygon_area
from maicon_sim.core.planar_motion import integrate_twist,move_robots
from maicon_sim.core.geometry3d import (camera_transform,project_points,ray_obb,ray_sphere,ray_rectangle,Primitive,raycast,laser_transform,canonical_solids,laser_contacts)

@pytest.mark.unit
@pytest.mark.parametrize('pose,v,w,dt,expected',[
 (Pose2(1,1,0),.2,0,1,(1.2,1,0)),
 (Pose2(1,1,0),0,1,1,(1,1,1)),
 (Pose2(1,1,0),.2,1,1,(1+.2*math.sin(1),1+.2*(1-math.cos(1)),1)),
 (Pose2(1,1,math.pi-.01),0,1,.02,(1,1,-math.pi+.01)),
 (Pose2(1,1,0),0,math.pi/2,1,(1,1,math.pi/2)),
 (Pose2(1,1,0),.2,.5,2,(1+.4*math.sin(1),1+.4*(1-math.cos(1)),1))],ids=['D2-K01-GEO-001','D2-K02','D2-K03','D2-K04','GEO-002','GEO-003'])
def test_constant_twist(pose,v,w,dt,expected):
    actual=integrate_twist(pose,v,w,dt)
    np.testing.assert_allclose([actual.x_m,actual.y_m,actual.yaw_rad],expected,atol=1e-9)

@pytest.mark.parametrize('bad',[(float('nan'),0),(1,float('inf'))])
def test_reject_nonfinite_twist(bad):
    with pytest.raises(ValueError):integrate_twist(Pose2(1,1,0),*bad,.01)

def robot(slot,x,y,yaw=0,v=0,w=0):
    p=Pose2(x,y,yaw);return RobotTruth(slot,'BLUE',p,p,v=v,omega=w)

def test_D2_C01_thin_wall_swept():
    robots={'A':robot('A',.7,1,v=.6)}
    wall=[{'box_id':'wall','pose':dict(x_m=1,y_m=1,yaw_rad=0),'size_m':[.02,2,.4]}]
    for _ in range(100):robots['A'].pose=move_robots(robots,wall,dict(width_m=3,height_m=3),{})['A']
    assert robots['A'].pose.x_m < .875
    assert not sat_intersects(obb_corners(robots['A'].pose),obb_corners(wall[0]['pose'],.02,2))

def test_D2_C02_GEO_007_simultaneous_symmetry():
    a={'A':robot('A',.7,1,v=.6),'B':robot('B',1.3,1,math.pi,v=.6)}
    b={'B':robot('B',.7,1,v=.6),'A':robot('A',1.3,1,math.pi,v=.6)}
    for _ in range(70):
        for robots in (a,b):
            for s,p in move_robots(robots,[],dict(width_m=2,height_m=2),{}).items():robots[s].pose=p
    assert a['A'].pose==b['B'].pose and a['B'].pose==b['A'].pose
    assert a['A'].pose.x_m < a['B'].pose.x_m-.23
    assert not sat_intersects(obb_corners(a['A'].pose),obb_corners(a['B'].pose))

def test_D2_C03_collision_chain_no_penetration():
    robots={str(i):robot(str(i),.6+i*.25,1,v=.6) for i in range(3)}
    boxes=[dict(box_id='wall',pose=dict(x_m=1.35,y_m=1,yaw_rad=0),size_m=[.02,2,.4])]
    for _ in range(100):
        for s,p in move_robots(robots,boxes,dict(width_m=3,height_m=3),{}).items():robots[s].pose=p
    footprints=[obb_corners(r.pose) for r in robots.values()]
    for i,a in enumerate(footprints):
        for b in footprints[i+1:]:assert not sat_intersects(a,b,touching=False)
    for p in footprints:assert not sat_intersects(p,obb_corners(boxes[0]['pose'],.02,2),touching=False)

def test_D2_C04_GEO_005_rotating_corner_blocked():
    r=robot('A',1,1,v=0,w=3)
    wall=[dict(box_id='wall',pose=dict(x_m=1.16,y_m=1,yaw_rad=0),size_m=[.02,2,.4])]
    robots={'A':r}
    for _ in range(40):r.pose=move_robots(robots,wall,dict(width_m=3,height_m=3),{})['A']
    assert r.pose.yaw_rad<math.pi/4
    assert not sat_intersects(obb_corners(r.pose),obb_corners(wall[0]['pose'],.02,2))

def test_GEO_008_40cm_corridor():
    robots={'A':robot('A',1,1,v=.3)}
    boxes=[dict(box_id=str(i),pose=dict(x_m=2,y_m=y,yaw_rad=0),size_m=[3,.2,.4]) for i,y in enumerate((.7,1.3))]
    for _ in range(100):robots['A'].pose=move_robots(robots,boxes,dict(width_m=4,height_m=2),{})['A']
    assert robots['A'].pose.x_m==pytest.approx(1.3,abs=1e-9)

def test_segment_footprint_trigger():
    poly=obb_corners(Pose2(1,1,math.pi/4))
    assert segment_intersects_polygon([[1,0],[1,2]],poly)
    assert not segment_intersects_polygon([[2,0],[2,2]],poly)

def test_convex_hull_and_sat():
    p=np.array([[0,0],[1,0],[1,1],[0,1],[.5,.5],[0,0]])
    hull=convex_hull(p)
    assert len(hull)==4 and polygon_area(hull)==1
    assert point_in_polygon([0,0],hull) and not point_in_polygon([0,0],hull,strict=True)
    assert not sat_intersects(hull,hull+2)
    assert sat_intersects(hull,hull+1,padding=1e-6)

@pytest.mark.parametrize('point,expected',[
 ([0,0,1],[319.5,239.5]),([.1,0,1],[351.5,239.5]),([0,.1,1],[319.5,271.5]),([.5,0,2],[399.5,239.5])],ids=['D2-S01','T3D-02x','T3D-02y','RENDER-003'])
def test_optical_projection(point,expected):
    xy,z=project_points([point],[0,0,0],np.eye(3),{})
    np.testing.assert_allclose(xy[0],expected,atol=1e-6)

def test_D2_S02_T3D03_GEO_004_pan_right():
    origin,R=camera_transform(Pose2(1,1,0),20,0)
    direction=R[:,2]
    assert math.atan2(direction[1],direction[0])==pytest.approx(-math.radians(10),abs=1e-9)

def test_T3D04_tilt_up():
    origin,R=camera_transform(Pose2(1,1,0),0,20)
    direction=R[:,2]
    assert math.asin(direction[2])==pytest.approx(math.radians(3),abs=1e-9)

def test_ray_shapes_and_tie_occluder_first():
    assert ray_obb(np.array([0,0,0]),np.array([1,0,0]),np.array([2,0,0]),[1,1,1])==1
    assert ray_sphere(np.array([0,0,0]),np.array([1,0,0]),np.array([2,0,0]),1)==1
    assert ray_rectangle(np.array([0,0,0]),np.array([1,0,0]),np.array([2,0,0]),[0,1,0],[0,0,1],1,1)==2
    shapes=[Primitive('receiver','sphere',np.array([2,0,0]),radius=1,receiver=True),Primitive('occluder','obb',np.array([2,0,0]),[1,1,1],np.eye(3))]
    assert raycast([0,0,0],[1,0,0],shapes).geometry_id=='occluder'
    assert ray_obb([0,2,0],[1,0,0],[2,0,0],[1,1,1]) is None

def test_shared_laser_true_geometry_199_200_interval():
    """Physical analytic aim, not a fake contact or direct destruction event."""
    from pathlib import Path
    from maicon_sim.config.loader import load_scenario
    from maicon_sim.core.engine import MatchEngine
    c=load_scenario(Path(__file__).resolve().parents[2]/'examples/scenario_smoke_six.yaml')
    e=MatchEngine(c)
    e.request('enter_ready',None)
    for s in e.robots:e.request('ready',s)
    e.request('start',None)
    r=e.robots['B-1'];target=np.array([1.7-.2-.021,4.2,.35])
    lo,hi=-100.,100.
    for _ in range(60):
        mid=(lo+hi)/2;origin,direction=laser_transform(r.pose,0,mid,c.sensors['geometry'])
        z_at_target=origin[2]+(target[0]-origin[0])*direction[2]/direction[0]
        if z_at_target<target[2]:lo=mid
        else:hi=mid
    r.tilt=r.target_tilt=(lo+hi)/2
    assert ('B-1','BLUE_RADAR') in laser_contacts(e.robots,e.boxes,c.arena['bounds'],c.sensors)
    assert e.request('fire','B-1')['message']=='fired'
    for _ in range(199):e.step()
    assert 'BLUE_RADAR' not in e.destroyed
    e.step()
    assert 'BLUE_RADAR' in e.destroyed
    # The assigned target recipient is R-1, irrespective of who fired.
    assert e.robots['B-1'].ammo==7
    events=[x for x in e.journal if x['kind']=='facility_destroyed']
    assert len(events)==1 and events[0]['match_elapsed_ticks']==200

def test_laser_box_occlusion_blocks_receiver():
    from maicon_sim.core.geometry3d import receiver_primitives
    geometry={'receivers':[{'center_m':[0,.11,.16],'radius_m':.015}],
              'gimbal_pivot_m':[.02,0,.23],'laser_offset_gimbal_m':[.025,0,.02]}
    r=robot('A',.5,1);r.tilt=0
    robots={'A':r,'B':robot('B',2,1,math.pi/2)}
    # Place an opaque full-height wall between emitter and any receiver.
    box=dict(box_id='opaque',pose=dict(x_m=1.2,y_m=1,yaw_rad=0),size_m=[.1,1,.4],faces=[])
    assert laser_contacts(robots,[box],dict(width_m=3,height_m=3),geometry)==set()

def test_GEO_006_large_internal_twist_cannot_tunnel():
    # Core API caps commands at .6m/s; this tests the stronger integrator bound
    # under deliberately high direct test input spanning a wall in one tick.
    robots={'A':robot('A',.7,1,v=50)}
    boxes=[dict(box_id='thin',pose=dict(x_m=1,y_m=1,yaw_rad=0),size_m=[.02,1,.4])]
    result=move_robots(robots,boxes,dict(width_m=3,height_m=3),{})
    assert result['A'].x_m<.875
    assert not sat_intersects(obb_corners(result['A']),obb_corners(boxes[0]['pose'],.02,1))

def test_E2E_002_TIME_004_physical_capture_at_245_seconds():
    from pathlib import Path
    from maicon_sim.config.loader import load_scenario
    from maicon_sim.core.engine import MatchEngine
    c=load_scenario(Path(__file__).resolve().parents[2]/'examples/scenario_smoke_six.yaml')
    # Evaluator motion fixture: an explicit valid initial position, never teleport
    # after start. No capture/score is injected; only public cmd_vel heartbeats.
    c.scenario['agents'][0]['start_pose']=dict(x_m=5.005,y_m=2.5,yaw_rad=0.)
    e=MatchEngine(c,retain_journal=True)
    e.request('enter_ready',None)
    for slot in e.robots:e.request('ready',slot)
    e.request('start',None)
    for _ in range(24100):e.step()
    assert e.phase=='running' and e.target_published
    for i in range(410):
        if i%10==0:e.request('cmd_vel','B-1',{'linear_x_mps':.1,'angular_z_rps':0.})
        e.step()
        if e.phase=='reporting':break
    assert e.phase=='reporting'
    assert e.match_elapsed_ticks==24500
    assert e.capture_camp=='BLUE'
    assert e.robots['B-1'].pose.x_m==pytest.approx(5.405,abs=1e-9)
    assert e.robots['B-1'].v==0
    from maicon_sim.core.rules import EngineError
    with pytest.raises(EngineError) as exc:e.request('m1','B-1',{'base':'RED_SUPPLY_DEPOT'})
    assert exc.value.status==409
    for s in e.eligible:
        rank=['R-1','R-2','R-3'] if s.startswith('B') else ['B-1','B-2','B-3']
        assert e.request('m6',s,{'ranking':rank})['accepted'] is True
    assert e.phase=='finished' and e.reporting_elapsed_ticks==0
