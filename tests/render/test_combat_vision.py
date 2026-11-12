"""Actual public RGB cues; evaluator truth is used only to build/check fixtures."""
import copy
import math

import numpy as np
import pytest

from maicon_sim.backends.bullet.backend import BulletBackend
from maicon_sim.backends.bullet.scene import HP_LED_COLORS
from maicon_sim.config.loader import load_scenario
from maicon_sim.perception.combat import CombatVisionDetector


pytestmark=pytest.mark.render


@pytest.mark.parametrize('label',['RADAR','COMMS','OUTPOST'])
def test_public_rgb_facility_class_and_visible_receiver_aim(label):
    config=load_scenario('examples/scenario_perception_gallery.yaml')
    # Bring a public fixture facility to the face the camera sees.
    for face in config.scenario['boxes'][0]['faces']:
        face['side']={'east':'west','west':'east'}[face['side']]
        if face['kind']=='facility':
            face['facility_code']='BLUE_'+label
            face['asset_id']='facility_'+label
    with BulletBackend(config) as backend:
        frame=backend.capture_rgb('B-1/front',0)
        detections=CombatVisionDetector({'front_camera':config.sensors['front_camera']}).process(frame)
        facilities=[d for d in detections['detections'] if d['kind']=='facility']
        assert len(facilities)==1,facilities
        target=facilities[0]
        assert max(target['class_probs'],key=target['class_probs'].get)==label
        assert target['aim_point_px'][0]==pytest.approx(320.,abs=2.)
        assert 155<target['aim_point_px'][1]<180
        assert .4<target['range_m']<.9
        assert not any(key in target for key in ('box_id','facility_code','pose','depth_m','segmentation'))
        assert detections['captured_tick']==frame['captured_tick']


def robot_scene(config,backend,hp,ammo,slot='R-1'):
    snapshot=copy.deepcopy(backend.snapshot)
    snapshot['robots']['B-1'].update(pose={'x_m':2.8,'y_m':3.3,'yaw_rad':0.})
    snapshot['robots'][slot].update(pose={'x_m':4.,'y_m':3.3,'yaw_rad':math.pi},hp=hp,ammo=ammo)
    backend.sync_scene(snapshot)


@pytest.mark.parametrize('hp',[4,3,2,1,0])
def test_public_rgb_marker_receiver_and_official_hp_led_colour(hp):
    config=load_scenario('examples/scenario_smoke_six.yaml')
    with BulletBackend(config) as backend:
        chassis=backend.scene.registry['R-1/chassis']
        before=backend.p.getVisualShapeData(chassis,physicsClientId=backend.client)[0][7]
        robot_scene(config,backend,hp,5)
        after=backend.p.getVisualShapeData(chassis,physicsClientId=backend.client)[0][7]
        assert before==after
        for led in backend.scene.hp_led_parts['R-1']:
            assert backend.p.getVisualShapeData(led,physicsClientId=backend.client)[0][7]==pytest.approx(HP_LED_COLORS[hp])
        frame=backend.capture_rgb('B-1/front',10)
        detections=CombatVisionDetector({'front_camera':config.sensors['front_camera']}).process(frame)
        targets=[d for d in detections['detections'] if d['kind']=='ugv' and d.get('marker_readout',{}).get('camp')=='RED']
        target=next(d for d in targets if d['marker_readout']['band_count']==1)
        assert target['aim_confidence']>=.8
        assert target['visual_state']['hp']==hp
        assert target['visual_state']['ammo']==5
        assert target['aim_point_px'][1]==pytest.approx(258.5,abs=3)
        assert not any(key in target for key in ('robot_id','slot','pose','hp','ammo','segmentation'))


@pytest.mark.parametrize('ammo',[0,3,8])
def test_public_rgb_ammunition_requires_visible_entire_panel(ammo):
    config=load_scenario('examples/scenario_smoke_six.yaml')
    with BulletBackend(config) as backend:
        robot_scene(config,backend,4,ammo)
        frame=backend.capture_rgb('B-1/front',10)
        detector=CombatVisionDetector({'front_camera':config.sensors['front_camera']})
        target=next(d for d in detector.process(frame)['detections'] if d['kind']=='ugv' and d.get('aim_point_px'))
        assert target['visual_state']['ammo']==ammo
        hidden=dict(frame);hidden['data']=frame['data'].copy()
        # An opaque patch over the panel must not be interpreted as empty ammo.
        hidden['data'][263:272,295:345]=[80,80,80]
        target=next(d for d in detector.process(hidden)['detections'] if d['kind']=='ugv' and d.get('aim_point_px'))
        assert target['visual_state']['ammo'] is None


def test_blank_image_does_not_invent_target_or_call_sign():
    image=np.full((480,640,3),127,np.uint8)
    assert CombatVisionDetector().detect(image)==[]


@pytest.mark.parametrize('slot',['R-1','R-2','R-3'])
def test_public_rgb_does_not_assign_wrong_id_to_partial_marker(slot):
    config=load_scenario('examples/scenario_smoke_six.yaml')
    with BulletBackend(config) as backend:
        robot_scene(config,backend,4,5,slot)
        frame=backend.capture_rgb('B-1/front',10)
        targets=[d for d in CombatVisionDetector().process(frame)['detections']
                 if d['kind']=='ugv' and d.get('aim_point_px')]
        assert len(targets)==1
        if slot=='R-3':
            # The mast hides the lowest stripe from this front fixture pose.
            # Treating the remaining two stripes asR-2 would contaminate M6.
            assert targets[0].get('marker_unresolved')
            assert 'marker_readout' not in targets[0]
        else:
            assert targets[0]['marker_readout']['band_count']==int(slot[-1])
