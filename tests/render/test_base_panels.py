"""M5 artwork is visible to real robot RGB on both walls, not just the UI."""
import math

import numpy as np
import pytest

from maicon_sim.backends.arena_art import base_panels
from maicon_sim.config.loader import load_scenario

pytestmark = pytest.mark.render


def test_six_m5_panels_are_textured_and_face_the_entry_zones():
    pytest.importorskip('pybullet')
    from maicon_sim.backends.bullet.backend import BulletBackend
    config = load_scenario('examples/scenario_reference_stadium.yaml')
    placements = base_panels(config.arena, config.assets)
    assert len(placements) == 6
    assert {p['asset_id'] for p in placements} == {'base_COMMAND_POST', 'base_MAINTENANCE', 'base_SUPPLY_DEPOT'}
    with BulletBackend(config) as backend:
        for tick, panel in enumerate(placements):
            west = panel['normal'][0] > 0
            snapshot = backend.snapshot
            snapshot['robots']['B-1']['pose'] = {
                'x_m': panel['center'][0] + (.85 if west else -.85),
                'y_m': panel['center'][1], 'yaw_rad': math.pi if west else 0.}
            backend.sync_scene(snapshot)
            frame = backend.capture_rgb('B-1/front', tick)
            mask = backend.private_capture('B-1/front')['segmentation'] == backend.scene.registry['base/'+panel['base_id']]
            assert mask.sum() > 1000, panel
            # A blank coloured mesh would satisfy visibility but not this check.
            assert np.std(frame['data'][mask].mean(axis=1)) > 15, panel


def test_m5_art_does_not_enter_m2_m3_template_matching():
    pytest.importorskip('cv2')
    from maicon_sim.perception.reference_images import ReferenceImageDetector
    templates = ReferenceImageDetector().templates
    assert len(templates) == 13
    assert all(t[0] in ('facility', 'object', 'decoy') for t in templates)
