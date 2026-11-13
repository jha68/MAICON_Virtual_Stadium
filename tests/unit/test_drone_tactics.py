from copy import deepcopy
import math

import numpy as np
import pytest

from maicon_sim.perception.overhead import OverheadProjection
from maicon_sim.policies.planning import FREE, OCCUPIED, OccupancyGrid
from maicon_sim.policies.tactics import TacticalNavigator
from maicon_sim.policies.baseline import ParticipantPolicy


def camera():
    return {'position_world_m': [2., 2., 3.], 'look_at_world_m': [2., 2., 0.],
            'up_world': [0., 1., 0.], 'width_px': 800, 'height_px': 800, 'hfov_deg': 90.}


def drone(tick=100, point=(2., 2.), camp='RED'):
    return {'status': 'available', 'visual': {'captured_tick': tick, 'navigation': {
        'source': 'calibrated_overhead_pixels', 'robots': [{'position_xy_m': list(point), 'camp': camp, 'uncertainty_m': .18}],
        'obstacles': []}}}


def test_calibrated_projection_rejects_unknown_outside_and_parallel_rays():
    p = OverheadProjection(camera())
    assert p.intersect([[399.5, 399.5]], .4)[0] == pytest.approx([2., 2.])
    assert p.intersect([[499.5, 399.5]], 0)[0] == pytest.approx([2.75, 2.])
    assert p.intersect([[399.5, 299.5]], 0)[0] == pytest.approx([2., 2.75])
    assert p.intersect([[-1., 0.]], 0) is None
    assert p.intersect([[math.nan, 0.]], 0) is None
    assert p.intersect([[400., 400.]], 4.) is None
    with pytest.raises(ValueError):
        OverheadProjection({**camera(), 'up_world': [0., 0., 1.]})


def test_anonymous_drone_body_forces_a_detour_without_writing_lidar_map():
    grid = OccupancyGrid(4., 4.)
    grid.cells[:] = FREE
    before = grid.cells.copy()
    navigator = TacticalNavigator('BLUE')
    hazards, opponents, captured = navigator.navigation(drone(), 100, (1., 2., 0.), grid)
    assert opponents == [(2., 2.)] and captured == 100
    path = grid.astar(grid.cell(1., 2.), grid.cell(3., 2.), hazards)
    assert path and all(math.dist(grid.center(c), (2., 2.)) > .54 for c in path)
    assert np.array_equal(before, grid.cells)
    assert not navigator.navigation(drone(), 251, (1., 2., 0.), grid)[0]
    assert not navigator.navigation({**drone(), 'status': 'disabled'}, 100, (1., 2., 0.), grid)[0]
    assert navigator.navigation(drone(110), 100, (1., 2., 0.), grid)[2] is None


def test_drone_box_blocks_path_and_loss_keeps_local_scan_obstacle():
    grid = OccupancyGrid(4., 4.)
    grid.cells[:] = FREE
    grid.set_cell(grid.cell(1., 1.), OCCUPIED)
    grid.cells[30:51, 30:51] = -1
    d = drone()
    d['visual']['navigation']['robots'] = []
    d['visual']['navigation']['obstacles'] = [{'polygon_xy_m': [[1.8, 1.8], [2.2, 1.8], [2.2, 2.2], [1.8, 2.2]]}]
    nav = TacticalNavigator('BLUE')
    hazards, _, _ = nav.navigation(d, 100, (1., 2., 0.), grid)
    assert grid.cell(2., 2.) in hazards
    assert grid.astar(grid.cell(1., 2.), grid.cell(3., 2.), hazards)
    # Actual local free-space evidence overrides an uncertain overhead halo.
    grid.cells[39:42, 30:51] = FREE
    cleared, _, _ = nav.navigation(d, 100, (1., 2., 0.), grid)
    assert grid.cell(2., 2.) not in cleared
    assert not nav.navigation({'status': 'unavailable'}, 101, None, grid)[0]
    assert grid.cells[grid.cell(1., 1.)[1], grid.cell(1., 1.)[0]] == OCCUPIED


def test_capture_time_pose_excludes_only_our_body_not_a_teammate():
    grid = OccupancyGrid(4., 4.)
    d = drone(point=(1., 2.), camp='BLUE')
    d['visual']['navigation']['robots'].append({'position_xy_m': [2., 2.], 'camp': 'BLUE'})
    hazards, opponents, _ = TacticalNavigator('BLUE').navigation(d, 100, (1., 2., 0.), grid)
    assert not opponents and grid.cell(1., 2.) not in hazards and grid.cell(2., 2.) in hazards
    # No pose at capture time means no anonymous body is silently called self.
    hazards, _, _ = TacticalNavigator('BLUE').navigation(d, 100, None, grid)
    assert grid.cell(1., 2.) in hazards


def scan(tick=100):
    return {'captured_tick': tick, 'ranges_m': [2.] * 360, 'angle_min_rad': -math.pi,
            'angle_increment_rad': math.pi/180}


def test_evasion_requires_observed_threat_and_fresh_rear_scan():
    grid = OccupancyGrid(4., 4.)
    grid.cells[:] = FREE
    nav = TacticalNavigator('BLUE')
    obs = {'state': {'hp': 4, 'captured_tick': 90}, 'scan': scan()}
    assert nav.evade((2., 2., 0.), obs, {}, 100, grid, set(), []) is None
    assert nav.evade((2., 2., 0.), obs, {}, 100, grid, set(), [(2.8, 2.)]) == (-.12, 0.)
    for bad in (None, .4, math.inf):
        blocked = deepcopy(obs)
        blocked['scan']['ranges_m'][0] = bad
        assert nav.evade((2., 2., 0.), blocked, {}, 100, grid, set(), [(2.8, 2.)]) == (0., 0.)
    assert nav.evade((2., 2., 0.), obs, {}, 121, grid, set(), [(2.8, 2.)]) == (0., 0.)
    obs['state'].update(hp=3, captured_tick=100)
    assert nav.evade((2., 2., 0.), obs, {}, 100, grid, set(), []) == (-.12, 0.)
    obs['scan'] = scan(251)
    assert nav.evade((2., 2., 0.), obs, {}, 251, grid, set(), []) is None


def test_front_camera_enemy_can_trigger_evasion_but_friend_or_old_frame_cannot():
    grid = OccupancyGrid(4., 4.)
    grid.cells[:] = FREE
    visual = {'captured_tick': 100, 'detections': [{'kind': 'ugv', 'range_m': .7,
              'marker_readout': {'camp': 'RED', 'confidence': .9}}]}
    nav = TacticalNavigator('BLUE')
    assert nav.evade((2., 2., 0.), {'scan': scan()}, visual, 100, grid, set(), []) == (-.12, 0.)
    visual['detections'][0]['marker_readout']['camp'] = 'BLUE'
    assert nav.evade((2., 2., 0.), {'scan': scan()}, visual, 100, grid, set(), []) is None
    visual['detections'][0]['marker_readout']['camp'] = 'RED'
    assert nav.evade((2., 2., 0.), {'scan': scan(131)}, visual, 131, grid, set(), []) is None


def test_policy_uses_drone_for_navigation_and_search_never_for_direct_fire():
    prior = {'bounds': {'width_m': 4., 'height_m': 4.}, 'nominal_starts': [
        {'slot': 'B-1', 'pose': {'x_m': 1., 'y_m': 2., 'yaw_rad': 0.}}], 'bases': [], 'sectors': []}
    policy = ParticipantPolicy(prior, {}, 'B-1')
    obs = {'match': {'cmd': 'start'}, 'odom': {'captured_tick': 100, 'sequence': 100,
           'local_pose': {'x_m': 0., 'y_m': 0., 'yaw_rad': 0.}}, 'drone': drone(point=(2., 2.8))}
    decision = policy.compute(obs, {'phase': 'running'})
    assert decision.diagnostics['navigation']['source'] == 'lidar_and_public_drone'
    assert decision.diagnostics['navigation']['anonymous_opponents'] == 1
    assert not decision.fire
    # Pause/report paths take priority over drone navigation and evasion.
    assert policy.compute({**obs, 'match': {'cmd': 'pause'}}, {'phase': 'running'}).velocity == (0., 0.)
    obs['drone']['status'] = 'unavailable'
    assert policy.compute(obs, {'phase': 'running'}).diagnostics['navigation']['source'] == 'lidar'
