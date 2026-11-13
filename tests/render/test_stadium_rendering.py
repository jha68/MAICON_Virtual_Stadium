"""PDF images and receiver LEDs really reach the CPU-rendered RGB frames."""
import numpy as np
import pytest

from maicon_sim.backends.bullet.backend import BulletBackend
from maicon_sim.config.loader import load_scenario
from maicon_sim.core.engine import MatchEngine
from maicon_sim.core.geometry3d import R_BO, receiver_primitives


pytestmark = pytest.mark.render


def test_reference_receivers_match_hit_geometry_and_invalidate_rgb_cache():
    config = load_scenario('examples/scenario_reference_stadium.yaml')
    engine = MatchEngine(config)
    with BulletBackend(config) as backend:
        backend.sync_scene(engine.snapshot())
        assert len(backend.scene.box_parts) == 20
        assert len(backend.scene.facility_parts) == 6
        targets = [p for p in receiver_primitives(engine.robots, engine.boxes, config.sensors['geometry'])
                   if p.owner not in engine.robots]
        for target in targets:
            body = backend.scene.registry[target.owner + '/receiver']
            position, _ = backend.p.getBasePositionAndOrientation(body, physicsClientId=backend.client)
            np.testing.assert_allclose(position, target.center, atol=1e-9)
            shape = backend.p.getVisualShapeData(body, physicsClientId=backend.client)[0]
            assert shape[3][0] == pytest.approx(target.radius)
        # Face BLUE_COMMS from the central aisle; keep the exact same camera pose.
        origin = [2.60, 4.17, .35]
        rotation = np.diag([-1., -1., 1.]) @ R_BO
        before = backend.capture_pose(origin, rotation)['data'].copy()
        receiving = engine.snapshot()
        receiving['facility_signals']['BLUE_COMMS'] = 'receiving'
        backend.sync_scene(receiving)
        np.testing.assert_array_equal(backend.capture_pose(origin, rotation, tick=1)['data'], before)
        snapshot = engine.snapshot()
        snapshot['destroyed'] = ['BLUE_COMMS']
        snapshot['facility_signals']['BLUE_COMMS'] = 'hit'
        backend.sync_scene(snapshot)
        after = backend.capture_pose(origin, rotation, tick=1)['data'].copy()
        changed = np.max(abs(before.astype(int)-after.astype(int)), axis=2) > 30
        assert changed.sum() > 20
        # Only the roof LED changes. Its shaded side can be darker than the
        # previously colour-changing spherical lens; require a red signal.
        colour = after.astype(float)
        assert np.any((colour[...,2] > 100) & (colour[...,2] > 3*colour[...,1]) &
                      (colour[...,2] > 3*colour[...,0]) & changed)
        backend.sync_scene(engine.snapshot())
        reset = backend.capture_pose(origin, rotation, tick=2)['data']
        np.testing.assert_array_equal(reset, before)
