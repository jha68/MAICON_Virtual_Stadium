"""Fixed match missions: public assignments, independent survey and actual M5."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from maicon_sim.config.loader import load_scenario
from maicon_sim.core.engine import MatchEngine
from maicon_sim.policies.baseline import ParticipantPolicy
from maicon_sim.policies.mission import MissionSurvey
from maicon_sim.policies.planning import FREE, OccupancyGrid, inside_polygon
from maicon_sim.policies.scripted import base_goal, nominal_pose

SLOTS = ('B-1', 'B-2', 'B-3', 'R-1', 'R-2', 'R-3')


@pytest.fixture
def config():
    return load_scenario('examples/scenario_reference_stadium.yaml')


def test_all_six_receive_structured_orders_at_start_and_m5_only_at_four_minutes(config):
    engine = MatchEngine(config)
    engine.request('enter_ready')
    for slot in SLOTS:
        engine.request('ready', slot)
        assert not engine.request('order', slot)['accepted']
    engine.request('start')
    for slot in SLOTS:
        order = engine.request('order', slot)['order']
        assert {k: order[k] for k in ('target', 'search_sectors', 'base')} == engine.orders[slot]['expected_m1']
        assert engine.reports[slot]['m1'] is None
        assert not engine.request('target', slot)['accepted']
    # Evaluator fixture advances to either side of the official 240 s boundary.
    engine.match_elapsed_ticks = 23998
    engine.step()
    assert not engine.target_published
    engine.step()
    assert engine.match_elapsed_ticks == 24000 and engine.target_published
    for slot in SLOTS:
        assert engine.request('target', slot)['order']['objective'] == config.scenario['objectives_by_camp'][engine.robots[slot].camp]


@pytest.mark.parametrize('slot', SLOTS)
def test_each_robot_surveys_all_opposing_sectors_and_center(config, slot):
    public_map = config.public_map_prior()
    survey = MissionSurvey(public_map, slot)
    grid = OccupancyGrid(6.12, 5.)
    grid.cells[:] = FREE
    expected = {'CM', *[f"{'R' if slot.startswith('B') else 'B'}-S{i}" for i in (1, 2, 3)]}
    assert set(survey.required) == expected
    pose, tick = (*survey.departure, 0.), 0
    assert {name for name, _ in survey.vantages[:4]} == expected
    reached = set()
    # Perfect navigation fixture: verify route scheduling, not physical reachability.
    for _ in range(8):
        goal = survey.goal(pose, tick, grid)
        assert inside_polygon(goal, survey.sectors[survey.active_sector]['polygon_xy_m'])
        reached.add(survey.active_sector)
        pose, tick = (*goal, 0.), tick+1
        survey.goal(pose, tick, grid)
        assert survey.sweeping
        tick += 651
    assert reached == expected and survey.visited == expected


@pytest.mark.parametrize('slot', SLOTS)
def test_m2_uses_direct_target_m3_ignores_subset_and_m5_ignores_early_base(config, slot):
    public_map = config.public_map_prior()
    policy = ParticipantPolicy(public_map, {}, slot)
    enemy = 'RED' if slot.startswith('B') else 'BLUE'
    assignment = {'target': enemy+'_COMMS', 'search_sectors': ['CM'], 'base': enemy+'_SUPPLY_DEPOT',
                  'tactical_command': 'Contradictory free text is never parsed'}
    captured_targets = []
    def combat(*args, **kwargs):
        captured_targets.append(args[3])
        return SimpleNamespace(state='search', diagnostics={}, hold=False, gimbal=None, fire=False)
    policy.combat.update = combat
    obs = {'odom': {'captured_tick': 100, 'local_pose': {'x_m': 0., 'y_m': 0., 'yaw_rad': 0.}},
           'match': {'cmd': 'start'}}
    order = {'accepted': True, 'order': deepcopy(assignment)}
    first = policy.compute(obs, {'phase': 'running'}, order)
    assert captured_targets == [enemy+'_COMMS'] and 'm1' not in first.reports
    assert len(first.diagnostics['missions']['m3_required_sectors']) == 4
    assert first.diagnostics['missions']['m5_objective'] is None
    assert policy.goal != base_goal(public_map, assignment['base'])
    actual = enemy+'_MAINTENANCE'
    second = policy.compute(obs, {'phase': 'running'}, order, {'accepted': True, 'order': {'objective': actual}})
    assert second.diagnostics['missions']['m5_objective'] == actual
    assert policy.goal == base_goal(public_map, actual)
    report = policy.compute({}, {'phase': 'reporting'})
    assert report.reports == {'m6': {'ranking': [f'{enemy[0]}-{i}' for i in (1, 2, 3)]}}
    assert report.diagnostics['m6_mode'] == 'mock'


@pytest.mark.parametrize('option,value', [('--policy','patrol'), ('--policy','idle'), ('--llm-provider','openai-compatible')])
def test_agent_cli_rejects_removed_modes(option, value):
    from maicon_sim.cli import parser
    with pytest.raises(SystemExit) as error:
        parser().parse_args(['agent', '--slot', 'B-1', '--server', 'http://localhost:8000', option, value])
    assert error.value.code == 2


def test_unreachable_goal_retries_are_bounded_but_new_goal_is_immediate(config):
    policy = ParticipantPolicy(config.public_map_prior(), {}, 'B-1')
    calls = []
    policy.grid.astar = lambda *args: calls.append(args) or []
    pose = nominal_pose(config.public_map_prior(), 'B-1')
    for tick in range(50):
        assert policy._navigate(pose, tick, (3., 2.), False) == (0., 0.)
    assert len(calls) == 1
    policy._navigate(pose, 50, (3., 2.), False)
    assert len(calls) == 2
    policy._navigate(pose, 51, (3., 3.), False)
    assert len(calls) == 3
