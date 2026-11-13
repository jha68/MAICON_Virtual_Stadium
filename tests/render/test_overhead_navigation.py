import math

import numpy as np
import pytest

from maicon_sim.config.loader import load_scenario
from maicon_sim.core.engine import MatchEngine
from maicon_sim.perception.drone import DroneObserver
from maicon_sim.policies.planning import inside_polygon

pytestmark = pytest.mark.render


def test_public_drone_jpeg_yields_box_and_body_estimates_without_private_data():
    cv2 = pytest.importorskip('cv2')
    pytest.importorskip('pybullet')
    from maicon_sim.backends.bullet.backend import BulletBackend
    config = load_scenario('examples/scenario_reference_stadium.yaml')
    engine = MatchEngine(config)
    calibration = {'capture_clock_epoch': config.scenario['epoch_kst'], 'drone_camera': config.sensors['drone']}
    observer = DroneObserver(calibration)
    with_backend = BulletBackend(config)
    try:
        with_backend.sync_scene(engine.snapshot())
        frame = with_backend.capture_drone(0)
        blob = cv2.imencode('.jpg', frame['data'], [cv2.IMWRITE_JPEG_QUALITY, 90])[1].tobytes()
        observer.process(blob, {'X-Captured-At': config.scenario['epoch_kst'], 'X-Frame-Interval-S': '1'}, 0)
        visual = observer.observation(0)['visual']
        nav = visual['navigation']
        # Test oracle is used only below, after inference over the public JPEG.
        assert len(nav['obstacles']) >= 8
        assert sum(any(inside_polygon((b['pose']['x_m'], b['pose']['y_m']), o['polygon_xy_m']) for o in nav['obstacles']) for b in engine.boxes) >= 18
        # Every inferred polygon covers real box-top area; floor stripes do not become walls.
        assert all(any(inside_polygon((b['pose']['x_m'], b['pose']['y_m']), o['polygon_xy_m']) for b in engine.boxes) for o in nav['obstacles'])
        assert len(nav['robots']) >= 4
        for estimate in nav['robots']:
            candidates = [r.pose for r in engine.robots.values() if r.camp == estimate['camp']]
            assert min(math.dist(estimate['position_xy_m'], (p.x_m, p.y_m)) for p in candidates) < .25
        assert all('marker_readout' not in item and 'aim_point_px' not in item and 'visual_state' not in item for item in visual['detections'])
        # Timestamps must survive transport, and disabled service drops hazards.
        observer.process(blob, {'X-Captured-At': config.scenario['epoch_kst']}, 100)
        assert observer.observation(100)['visual']['captured_tick'] == 0
        observer.unavailable(403)
        assert observer.observation(101)['visual'] is None
    finally:
        with_backend.close()
