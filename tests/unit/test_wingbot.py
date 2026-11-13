import math
import numpy as np
import pytest

from maicon_sim.config.loader import load_scenario
from maicon_sim.core.engine import MatchEngine
from maicon_sim.core.geometry3d import (body_transform, canonical_solids, gimbal_rotation,
    laser_transform, raycast, receiver_primitives)
from maicon_sim.core.robot_model import parts, primitive_mesh, wheel_speeds
from maicon_sim.core.types import Pose2


def arena():
    c=load_scenario('examples/scenario_reference_stadium.yaml')
    c.scenario['boxes']=[]
    e=MatchEngine(c)
    for i,r in enumerate(e.robots.values()):r.pose=Pose2(12+i,12,0)
    e.robots['B-1'].pose=Pose2(2,2.5,0)
    e.robots['R-1'].pose=Pose2(3,2.5,math.pi)
    return e


def aim(robot, point, g):
    # Evaluator-only geometric placement, never used by the participant.
    for _ in range(10):
        o,_=laser_transform(robot.pose,robot.pan,robot.tilt,g)
        _,R=body_transform(robot.pose);d=R.T@(point-o)
        robot.pan=-math.degrees(math.atan2(d[1],d[0]))/.5
        robot.tilt=math.degrees(math.atan2(d[2],np.linalg.norm(d[:2])))/.15
    robot.target_pan,robot.target_tilt=robot.pan,robot.tilt


def test_photo_envelope_and_lens_centres_are_shared():
    e=arena();g=e.config.sensors['geometry'];specs=parts(g)
    vertices=[]
    for p in specs:
        v=np.array(primitive_mesh(p)[0])
        if p['frame']=='gimbal':v+=g['gimbal_pivot_m']
        vertices.extend(v)
    vertices=np.array(vertices)
    assert np.ptp(vertices[:,0]) == pytest.approx(.23,abs=.001)
    assert np.ptp(vertices[:,1]) == pytest.approx(.25,abs=.001)
    assert vertices[:,2].max() == pytest.approx(.32)
    assert vertices[:,2].min() >= -1e-9
    lens=next(s for s in specs if s['name']=='laser_lens')
    robot=e.robots['B-1'];robot.pan=80;robot.tilt=-60
    o,d=laser_transform(robot.pose,robot.pan,robot.tilt,g)
    p,R=body_transform(robot.pose);G=gimbal_rotation(robot.pan,robot.tilt)
    np.testing.assert_allclose(o,p+R@(np.array(g['gimbal_pivot_m'])+G@lens['center']))
    np.testing.assert_allclose(d,R@G@np.array([1,0,0]))
    assert wheel_speeds(.6,0)==(.6,.6)
    assert wheel_speeds(0,3)==pytest.approx((-.3075,.3075))


def test_m4_exposed_dome_hits_but_backing_body_and_cover_do_not():
    e=arena();g=e.config.sensors['geometry']
    shapes=canonical_solids(e.robots,e.boxes,e.config.arena['bounds'],g)+receiver_primitives(e.robots,[],g)
    for receiver in [s for s in shapes if s.receiver and s.owner=='R-1']:
        n=receiver.normal
        hit=raycast(receiver.center+n*.2,-n,shapes,exclude_owner='B-1')
        assert hit.receiver and hit.geometry_id==receiver.geometry_id
        hit=raycast(receiver.center-n*.08,n,shapes,exclude_owner='B-1')
        assert not hit.receiver
    hit=raycast([2.5,2.5,.075],[1,0,0],shapes)
    assert not hit.receiver and hit.owner=='R-1'
    from maicon_sim.core.geometry3d import Primitive
    cover=Primitive('cover','obb',np.array([2.5,2.5,.2]),np.array([.03,.3,.2]),np.eye(3))
    receiver=next(s for s in shapes if s.receiver and s.owner=='R-1')
    origin=np.array([2,2.5,.28]);d=receiver.center+receiver.normal*.015-origin
    assert raycast(origin,d,shapes+[cover],exclude_owner='B-1').geometry_id=='cover'


def test_m4_requires_two_seconds_on_one_dome_and_obeys_emission_cycle():
    e=arena();g=e.config.sensors['geometry'];e.request('enter_ready')
    for slot in ['B-1','R-1']:e.request('ready',slot)
    e.request('start');robot=e.robots['B-1']
    targets=[s for s in receiver_primitives(e.robots,[],g) if s.owner=='R-1']
    def point(i):return targets[i].center+targets[i].normal*.016
    aim(robot,point(0),g)
    assert abs(robot.tilt)<100
    assert e.request('fire','B-1')['message']=='fired'
    e.step(100);assert e.robots['R-1'].hp==4
    aim(robot,point(1),g)
    e.step(100);assert e.robots['R-1'].hp==4
    e.step(100);assert e.robots['R-1'].hp==3
    assert robot.ammo==7
    assert e.request('fire','B-1')['message']=='reloading'
    e.step(200);assert robot.laser_until<=e.robot_effect_ticks
    assert e.request('fire','B-1')['message']=='reloading'
    e.step(500);assert e.request('fire','B-1')['message']=='fired'
