from copy import deepcopy
import math

import pytest

from maicon_sim.config.loader import load_scenario
from maicon_sim.core.actuation import GimbalModel, servo_step
from maicon_sim.core.capture import crossing_fraction, select_capture
from maicon_sim.core.engine import MatchEngine
from maicon_sim.core.types import Pose2


def running():
    engine = MatchEngine(load_scenario('examples/scenario_reference_stadium.yaml'))
    engine.request('enter_ready')
    for slot in engine.robots:
        engine.request('ready', slot)
    engine.request('start')
    return engine


def test_acceleration_changes_trajectory_but_preserves_limits_and_final_position():
    fast, slow = GimbalModel(acceleration_gain=10), GimbalModel(acceleration_gain=10)
    fast.accepted(80, 40, 90, 0, acc=100)
    slow.accepted(80, 40, 90, 0, acc=2)
    fast.update(25); slow.update(25)
    assert 0 < slow.pan < fast.pan < 80
    assert abs(slow.pan_velocity) <= 5.01
    fast.update(2000); slow.update(2000)
    assert (fast.pan, fast.tilt) == (slow.pan, slow.tilt) == (80, 40)
    assert servo_step(0, 0, 10, 90, 200, .01) == pytest.approx((.01, 2.))
    assert servo_step(49.99, 90, -50, 90, 20, .01, limits=(-50,50)) == (50,0.)


def test_drive_ramp_watchdog_and_gimbal_checkpoint_use_same_dynamics():
    engine = running()
    engine.request('cmd_vel', 'B-1', {'linear_x_mps':.3, 'angular_z_rps':0.})
    engine.request('gimbal', 'B-1', {'pan':80, 'tilt':20, 'speed':90, 'acc':20})
    model = GimbalModel(acceleration_gain=10)
    model.accepted(80, 20, 90, 0, 20)
    engine.step(); model.update(1)
    robot = engine.robots['B-1']
    assert robot.v == pytest.approx(.008)
    assert (robot.pan, robot.tilt) == pytest.approx((model.pan, model.tilt))
    restored = running(); restored.restore_state(engine.export_state())
    for _ in range(80):
        engine.step(); restored.step()
    assert engine.export_state() == restored.export_state()
    assert robot.v == robot.command_v == 0
    engine.request('pause')
    assert robot.pan_velocity == robot.tilt_velocity == 0


def test_operator_lease_excludes_policy_and_records_non_autonomous_result():
    engine = running()
    result = engine.request('operator_control', 'B-1', {'command':'cmd_vel', 'parameters':{'linear_x_mps':.2, 'angular_z_rps':0}})
    assert result['accepted']
    assert engine.request('fire', 'B-1')['reason'] == 'operator_control'
    assert engine.request('cmd_vel', 'B-1', {'linear_x_mps':0., 'angular_z_rps':0.})['accepted'] is False
    assert engine.robots['B-1'].command_v == .2
    for _ in range(51): engine.step()
    assert engine.request('cmd_vel', 'B-1', {'linear_x_mps':0., 'angular_z_rps':0.})['accepted']
    engine.request('operator_control', 'B-1', {'command':'release'})
    assert engine.robots['B-1'].v == 0 and engine.manual_until == {}
    engine.request('stop')
    assert engine.result()['operator_interventions'] == 1


def test_sensor_interpolation_finds_sub_tick_edge():
    geometry = {'footprint_length_m':.23, 'footprint_width_m':.25}
    fraction = crossing_fraction(Pose2(.299, 0, 0), Pose2(.305, 0, 0), [[.42,-.3],[.42,.3]], geometry)
    assert fraction == pytest.approx(1., abs=1e-6)
    fraction = crossing_fraction(Pose2(.302, 0, 0), Pose2(.308, 0, 0), [[.42,-.3],[.42,.3]], geometry)
    assert fraction == pytest.approx(.5, abs=1e-6)


def test_capture_broad_phase_matches_exact_footprints_including_rotated_touch():
    from maicon_sim.core.geometry2d import footprint, segment_intersects_polygon
    engine = running()
    g = engine.config.sensors['geometry']
    length, width = g['footprint_length_m'], g['footprint_width_m']
    bases = engine.config.arena['bases']
    for base in bases:
        a, b = base['trigger_segment_xy_m']
        x, y = (a[0]+b[0])/2, (a[1]+b[1])/2
        for yaw in (0., math.pi/4, math.pi/2):
            radius = abs(math.cos(yaw))*length/2 + abs(math.sin(yaw))*width/2
            for gap in (-.1, 0., 1e-10, 1e-7, .01, 1.):
                engine.robots['B-1'].pose = Pose2(x-radius-gap, y, yaw)
                exact = {candidate['code']:any(segment_intersects_polygon(candidate['trigger_segment_xy_m'],
                            footprint(r.pose, length, width)) for r in engine.robots.values()) for candidate in bases}
                observed = engine._blocked_bases()
                assert observed == exact, (base['code'], yaw, gap)
                engine.base_blocked = observed


def test_sensor_tolerance_uses_arrival_not_base_name():
    events = [{'base':'BLUE_MAINTENANCE', 'detected_ms':100., 'arrived_ms':150., 'nonce':'a'},
              {'base':'RED_MAINTENANCE', 'detected_ms':105., 'arrived_ms':110., 'nonce':'z'}]
    assert select_capture(events)['base'] == 'RED_MAINTENANCE'
    events[1]['detected_ms'] = 111.
    assert select_capture(events)['base'] == 'BLUE_MAINTENANCE'


def test_cross_tick_capture_transport_and_pending_checkpoint():
    engine = running()
    engine.target_published = True
    engine.config.rules['capture']['latency_ms_by_base'] = {'BLUE_MAINTENANCE':30., 'RED_MAINTENANCE':0.}
    engine.sim_tick = 100
    blocked = {b['code']:False for b in engine.config.arena['bases']}
    engine.base_blocked = deepcopy(blocked)
    blocked['BLUE_MAINTENANCE'] = True
    engine._capture_edges(blocked)
    assert engine.capture_camp is None
    restored = running(); restored.restore_state(engine.export_state())
    restored.config.rules['capture'] = deepcopy(engine.config.rules['capture'])
    for current in (engine, restored):
        current.sim_tick = 101
        blocked = deepcopy(current.base_blocked); blocked['RED_MAINTENANCE'] = True
        current._capture_edges(blocked)
        current.sim_tick = 105; current._capture_edges(blocked)
        assert current.capture_camp == 'BLUE'
        assert current.phase == 'reporting'
    assert engine.export_state() == restored.export_state()
