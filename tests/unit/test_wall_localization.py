"""The localizer consumes measured ranges and a public rectangle, never boxes."""
import math

import numpy as np
import pytest

from maicon_sim.policies.localization import PublicWallLocalizer


BOUNDS = {"width_m": 6.12, "height_m": 5.}


def rectangle_scan(pose, tick=0, noise=0., origin=(0., 0.)):
    angles = np.linspace(-math.pi, math.pi, 360, endpoint=False)
    yaw = pose[2]
    center = np.array(pose[:2])+np.array([[math.cos(yaw), -math.sin(yaw)], [math.sin(yaw), math.cos(yaw)]])@origin
    ranges = []
    rng = np.random.default_rng(17)
    for angle in angles+yaw:
        direction = np.array([math.cos(angle), math.sin(angle)])
        distances = []
        for axis, bound in ((0, 0.), (0, BOUNDS["width_m"]), (1, 0.), (1, BOUNDS["height_m"])):
            if abs(direction[axis]) > 1e-10:
                d = (bound-center[axis])/direction[axis]
                if d > 0:
                    distances.append(d)
        ranges.append(min(distances)+rng.normal(0., noise))
    return {"captured_tick": tick, "angle_min_rad": -math.pi, "angle_increment_rad": 2*math.pi/360,
            "range_min_m": .05, "range_max_m": 8., "ranges_m": ranges}


@pytest.mark.parametrize("true_pose,estimate", [
    ((1.1, 1.3, .2), (1.21, 1.22, .27)),
    ((4.8, 3.8, -2.), (4.71, 3.91, -2.06)),
    ((.4, 4.2, 0.), (.48, 4.13, .08)),
])
def test_public_walls_correct_start_translation_and_yaw(true_pose, estimate):
    localizer = PublicWallLocalizer(BOUNDS)
    result = localizer.update(estimate, rectangle_scan(true_pose))
    assert localizer.diagnostics["accepted"], localizer.diagnostics
    assert result == pytest.approx(true_pose, abs=1e-7)
    assert localizer.apply(estimate) == pytest.approx(true_pose, abs=1e-7)


def test_lidar_mount_offset_and_noisy_returns_remain_accurate():
    true, estimate = (1.4, 3.1, -.5), (1.48, 3.04, -.44)
    origin = (.07, -.03)
    localizer = PublicWallLocalizer(BOUNDS)
    result = localizer.update(estimate, rectangle_scan(true, noise=.004, origin=origin), origin)
    assert localizer.diagnostics["accepted"]
    assert result == pytest.approx(true, abs=.01)


def test_persistent_map_rotation_corrects_subsequent_motion():
    true, estimate = (1.1, 1.3, .2), (1.21, 1.22, .27)
    localizer = PublicWallLocalizer(BOUNDS)
    localizer.update(estimate, rectangle_scan(true))
    local_forward = .7
    moved_estimate = (estimate[0]+local_forward*math.cos(estimate[2]), estimate[1]+local_forward*math.sin(estimate[2]), estimate[2])
    expected = (true[0]+local_forward*math.cos(true[2]), true[1]+local_forward*math.sin(true[2]), true[2])
    assert localizer.apply(moved_estimate) == pytest.approx(expected, abs=1e-7)


def test_short_box_like_segments_cannot_snap_pose_to_walls():
    # Four short, isolated planar patches near the rectangle boundary. They are
    # deliberately not long enough to be credible arena-wall support.
    pose = (3., 2.5, 0.)
    scan = rectangle_scan(pose)
    scan["ranges_m"] = [None]*360
    for center in (0, 90, 180, 270):
        for offset in range(-2, 3):
            index = (center+offset)%360
            angle = -math.pi+index*2*math.pi/360
            axis = 0 if center in (0, 180) else 1
            component = math.cos(angle) if axis == 0 else math.sin(angle)
            limit = BOUNDS["width_m"] if axis == 0 else BOUNDS["height_m"]
            plane = .2 if component < 0 else limit-.2
            scan["ranges_m"][index] = (plane-pose[axis])/component
    localizer = PublicWallLocalizer(BOUNDS)
    assert localizer.update(pose, scan) == pose
    assert not localizer.diagnostics["accepted"]


def test_one_wall_missing_data_and_old_scan_keep_previous_transform():
    true, estimate = (1.1, 1.3, .2), (1.21, 1.22, .27)
    localizer = PublicWallLocalizer(BOUNDS)
    localizer.update(estimate, rectangle_scan(true, tick=10))
    previous = localizer.correction
    # Replayed or out-of-order scans cannot change a fresh map registration.
    localizer.update(estimate, rectangle_scan((2., 2., .4), tick=9))
    assert localizer.diagnostics["reason"] == "old_scan"
    assert localizer.correction == previous
    no_returns = rectangle_scan(true, tick=11)
    no_returns["ranges_m"] = [None]*360
    localizer.update(estimate, no_returns)
    assert localizer.correction == previous
    one_wall = rectangle_scan(true, tick=12)
    one_wall["ranges_m"] = [d if 160 < i < 195 else None for i, d in enumerate(one_wall["ranges_m"])]
    localizer.update(estimate, one_wall)
    assert not localizer.diagnostics["accepted"]
    assert localizer.correction == previous


def test_large_correction_is_rejected_instead_of_teleporting_estimate():
    pose = (3., 2.5, 0.)
    estimate = (3.4, 2.5, 0.)
    localizer = PublicWallLocalizer(BOUNDS, max_translation_m=.25)
    result = localizer.update(estimate, rectangle_scan(pose))
    assert result == estimate
    assert not localizer.diagnostics["accepted"]


def test_public_gateway_scan_with_box_occlusions_corrects_nominal_start_error():
    from maicon_sim.config.loader import load_scenario
    from maicon_sim.core.engine import MatchEngine
    from maicon_sim.sensors.gateway import SensorGateway

    config = load_scenario("examples/scenario_smoke_six.yaml")
    engine = MatchEngine(config)
    gateway = SensorGateway(config)
    try:
        gateway.update(engine)
        localizer = PublicWallLocalizer(config.arena["bounds"])
        # Only measured public ranges enter the localizer, not box locations.
        result = localizer.update((.48, 4.13, .08), gateway.get("B-1", "scan"))
        assert localizer.diagnostics["accepted"]
        assert result == pytest.approx((.4, 4.2, 0.), abs=.01)
    finally:
        gateway.close()
