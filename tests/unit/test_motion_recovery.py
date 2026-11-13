import math

import pytest

from maicon_sim.policies.recovery import MotionRecovery


def scan(tick, distance=2.):
    return {'captured_tick': tick, 'ranges_m': [distance]*360,
            'angle_min_rad': -math.pi, 'angle_increment_rad': math.pi/180}


def test_stall_reverses_only_after_three_seconds_and_stops_at_two_seconds():
    r = MotionRecovery()
    pose, goal = (2., 2., 0.), (3., 2.)
    assert r.command(pose, goal, scan(0), 0) is None
    assert r.command(pose, goal, scan(299), 299) is None
    assert r.command(pose, goal, scan(300), 300) == (-.12, 0.)
    assert r.command((1.9, 2., 0.), goal, scan(400), 400) == (-.12, 0.)
    assert r.command((1.76, 2., 0.), goal, scan(500), 500) is None


@pytest.mark.parametrize('bad', [None, .4, math.inf, math.nan])
def test_missing_or_blocked_rear_sample_prevents_reversing(bad):
    r = MotionRecovery()
    r.command((2., 2., 0.), (3., 2.), scan(0), 0)
    s = scan(400)
    s['ranges_m'][0] = bad
    value = r.command((2., 2., 0.), (3., 2.), s, 400)
    assert value is None or value[0] == 0.


def test_stale_scan_active_aim_and_arrival_prevent_recovery():
    for kwargs in ({'holding': True}, {}):
        r = MotionRecovery()
        r.command((2., 2., 0.), (3., 2.), scan(0), 0)
        assert r.command((2., 2., 0.), (3., 2.), scan(0), 400, **kwargs) is None
    r = MotionRecovery()
    r.command((2., 2., 0.), (3., 2.), scan(0), 0)
    assert r.command((2., 2., 0.), (2.1, 2.), scan(400), 400) is None
    assert r.command((2., 2., 0.), (3., 2.), scan(800), 800, holding=True) is None


def test_blocked_rear_can_turn_towards_a_measured_gap_then_drive_briefly():
    r = MotionRecovery()
    pose, goal = (2., 2., 0.), (3., 2.)
    r.command(pose, goal, scan(0), 0)
    s = scan(300, .3)
    # A rear-left gap, while the reverse corridor is blocked.
    for i in range(15, 76):
        s['ranges_m'][i] = 1.
    assert r.command(pose, goal, s, 300) == (0., -.8)
    assert r.mode == 'turn'
    assert r.command((2., 2., r.heading), goal, scan(600), 600) == (.12, 0.)
    assert r.mode == 'forward'
    assert r.command((2.2, 2., r.heading), goal, scan(800), 800) is None


def test_turn_requires_full_scan_and_footprint_clearance():
    for s in (scan(300, .2), {**scan(300), 'ranges_m': [.3]*20}, {**scan(300), 'ranges_m': [None]+[.3]*359}):
        r = MotionRecovery()
        r.command((2., 2., 0.), (3., 2.), scan(0), 0)
        assert r.command((2., 2., 0.), (3., 2.), s, 300) is None
