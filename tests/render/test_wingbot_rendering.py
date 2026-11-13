import math
import numpy as np
import pytest

from maicon_sim.backends.bullet.backend import BulletBackend
from maicon_sim.config.loader import load_scenario
from maicon_sim.core.engine import MatchEngine
from maicon_sim.core.geometry3d import laser_transform, camera_transform, receiver_primitives
from maicon_sim.core.types import Pose2
from maicon_sim.evaluation.runner import calibration
from maicon_sim.perception.combat import CombatVisionDetector

pytestmark=pytest.mark.render


def setup():
    c=load_scenario('examples/scenario_reference_stadium.yaml');c.scenario['boxes']=[]
    e=MatchEngine(c)
    for i,r in enumerate(e.robots.values()):r.pose=Pose2(12+i,12,0)
    return c,e


def test_rendered_lens_and_domes_match_physics_through_gimbal_extremes():
    c,e=setup();g=c.sensors['geometry'];r=e.robots['B-1'];r.pose=Pose2(3,2.5,.7)
    with BulletBackend(c) as b:
        for pan,tilt in [(0,0),(100,100),(-100,-100),(55,-70)]:
            r.pan,r.tilt=pan,tilt;b.sync_scene(e.snapshot())
            for lens,expected in [('laser_lens',laser_transform(r.pose,pan,tilt,g)[0]),
                                  ('camera_lens',camera_transform(r.pose,pan,tilt,g)[0])]:
                pos,_=b.p.getBasePositionAndOrientation(b.scene.registry['B-1/'+lens],physicsClientId=b.client)
                np.testing.assert_allclose(pos,expected,atol=1e-9)
            for receiver in receiver_primitives({'B-1':r},[],g):
                index=receiver.geometry_id.rsplit('/',1)[1]
                pos,_=b.p.getBasePositionAndOrientation(b.scene.registry['B-1/receiver'+index],physicsClientId=b.client)
                np.testing.assert_allclose(pos,receiver.center,atol=1e-9)


def test_image_only_identification_for_both_camps_and_headlights_do_not_license_fire():
    c,e=setup();detector=CombatVisionDetector(calibration(c),robot_only=True)
    with BulletBackend(c) as b:
        for slot in e.robots:
            for i,r in enumerate(e.robots.values()):r.pose=Pose2(12+i,12,0)
            observer='R-1' if slot.startswith('B') else 'B-1'
            e.robots[observer].pose=Pose2(2.2,2.5,0);e.robots[slot].pose=Pose2(3,2.5,math.pi)
            b.sync_scene(e.snapshot());image=b.capture_rgb(observer+'/front',0)['data']
            detections=detector.detect(image)
            target=[d for d in detections if d.get('marker_readout',{}).get('band_count')==int(slot[-1]) and
                    d['marker_readout']['camp']==('BLUE' if slot[0]=='B' else 'RED')]
            assert target and 'aim_point_px' in target[0],(slot,detections)
        # Last target R-3: remove only its white dome surfaces. White lamps stay.
        for i in [0,1]:b.p.changeVisualShape(b.scene.registry[f'R-3/receiver{i}'],-1,rgbaColor=[.08,.08,.08,1],physicsClientId=b.client)
        b._cache.clear()
        detections=detector.detect(b.capture_rgb('B-1/front',1)['data'])
        assert any(d.get('marker_readout',{}).get('band_count')==3 for d in detections)
        assert all('aim_point_px' not in d for d in detections)
