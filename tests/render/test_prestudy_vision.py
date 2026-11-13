"""Actual rendered PDF panels, including distractors and closed-loop M2."""
from copy import deepcopy

import numpy as np
import pytest

from maicon_sim.backends.bullet.backend import BulletBackend
from maicon_sim.config.loader import load_scenario
from maicon_sim.core.engine import MatchEngine
from maicon_sim.core.geometry3d import R_BO
from maicon_sim.evaluation.runner import calibration
from maicon_sim.perception.combat import CombatVisionDetector
from maicon_sim.perception.reference_images import ReferenceImageDetector
from maicon_sim.policies.baseline import GimbalEstimate
from maicon_sim.policies.combat import CombatPolicy

pytestmark = pytest.mark.render


def arrange(config, asset):
    face = {'side':'west', 'kind':asset['kind'], 'asset_id':asset['asset_id']}
    if asset['kind'] == 'object': face['object_class'] = asset['label']
    if asset['kind'] == 'facility': face['facility_code'] = 'RED_'+asset['label']
    config.scenario['boxes'] = [{'box_id':'trial', 'sector_id':'R-S2',
        'pose':{'x_m':4., 'y_m':2.5, 'yaw_rad':0.}, 'size_m':[.4,.4,.4], 'faces':[face]}]


@pytest.fixture(scope='module')
def detector():
    config = load_scenario('examples/scenario_reference_stadium.yaml')
    return ReferenceImageDetector(calibration(config))


@pytest.mark.parametrize('asset_id', [
    'facility_COMMS', 'facility_RADAR', 'facility_OUTPOST', 'object_ammo_box',
    'object_drum', 'object_military_truck', 'object_missile', 'object_mortar', 'object_tank',
    'decoy_barrier', 'decoy_field_position', 'decoy_ruined_building', 'decoy_urban_tree'])
def test_public_pdf_panels_recognized_and_decoys_excluded(asset_id, detector):
    config = load_scenario('examples/scenario_reference_stadium.yaml')
    asset = next(a for a in config.assets['assets'] if a['asset_id'] == asset_id)
    arrange(config, asset)
    with BulletBackend(config) as backend:
        image = backend.capture_pose(np.array([2.7,2.5,.23]), R_BO)['data']
    found = detector.detect(image)
    if asset['kind'] == 'decoy':
        assert found == []
    else:
        assert len(found) == 1 and found[0]['class_probs'] == {asset['label']:1.}
        if asset['kind'] == 'facility':
            assert 'aim_point_px' in found[0]
            assert not found[0].get('destroyed_observation')


def test_pdf_radar_closed_loop_accelerated_gimbal_laser_and_red_hit_feedback():
    config = load_scenario('examples/scenario_reference_stadium.yaml')
    arrange(config, next(a for a in config.assets['assets'] if a['asset_id'] == 'facility_RADAR'))
    start = {'x_m':2.7, 'y_m':2.5, 'yaw_rad':0.}
    config.scenario['agents'][0]['start_pose'] = deepcopy(start)
    engine = MatchEngine(config)
    engine.request('enter_ready'); engine.request('ready','B-1'); engine.request('start')
    calib = calibration(config)
    detector = CombatVisionDetector(calib)
    policy = CombatPolicy('B-1', {'sectors':config.arena['sectors']})
    estimate = GimbalEstimate(acceleration_gain=10)
    fired, decisions = [], []
    with BulletBackend(config) as backend:
        for tick in range(900):
            if tick % 10 == 0:
                backend.sync_scene(engine.snapshot())
                visual = detector.process(backend.capture_rgb('B-1/front',tick))
                estimate.update(tick)
                action = policy.update({'combat':visual, 'state':{'hp':4,'captured_tick':tick}}, calib,
                    target='RED_RADAR', gimbal={'pan':estimate.pan,'tilt':estimate.tilt}, pose=(2.7,2.5,0.))
                decisions.append(action.state)
                if action.gimbal:
                    pan,tilt,speed,acc = action.gimbal
                    result = engine.request('gimbal','B-1',dict(pan=pan,tilt=tilt,speed=speed,acc=acc))
                    estimate.accepted(pan,tilt,speed,tick,acc)
                    policy.acknowledge_gimbal(action.gimbal,result,tick)
                if action.fire:
                    result = engine.request('fire','B-1')
                    policy.acknowledge_fire(result,tick); fired.append(result['message'])
            engine.step()
            if 'RED_RADAR' in engine.destroyed_facilities: break
        assert fired == ['fired'], decisions
        assert 'RED_RADAR' in engine.destroyed_facilities, decisions
        assert engine.robots['B-1'].ammo == 7
        backend.sync_scene(engine.snapshot())
        after = detector.detect(backend.capture_rgb('B-1/front',engine.sim_tick)['data'])
        assert any(d.get('destroyed_observation') for d in after)
