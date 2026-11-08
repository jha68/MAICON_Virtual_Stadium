"""Hand-calculated rule and boundary acceptance cases (no render oracle)."""
from copy import deepcopy
from dataclasses import replace
from itertools import permutations
import json
import pytest
from maicon_sim.config.loader import load_scenario
from maicon_sim.core.engine import MatchEngine, EngineError
from maicon_sim.core.types import SLOTS, OBJECT_CLASSES, Pose2
from maicon_sim.core.rules import normalize_m1, normalize_m3, normalize_m6
from maicon_sim.core.scoring import (score_m1, score_m3, score_m6, finalize_scores,
                                     inventory_from_boxes, risk_numerator, accepted_rankings)

pytestmark = pytest.mark.unit

@pytest.fixture
def config():
    return load_scenario('examples/scenario_smoke_six.yaml')

@pytest.fixture
def engine(config):
    return MatchEngine(config)


def start(e, slots=SLOTS):
    e.request('enter_ready')
    for s in slots:
        e.request('ready', s)
    e.request('start')
    return e


def report_for_inventory(inventory, sectors=('R-S1', 'R-S2', 'R-S3', 'CM')):
    return {'sectors': [{'sector': s, 'objects': [{'type': c, 'count': n} for c, n in inventory[s].items() if n]} for s in sectors]}


def assert_error(status, fn):
    with pytest.raises(EngineError) as error:
        fn()
    assert error.value.status == status


def test_RULE_001_full_idle_episode(engine):
    start(engine)
    engine.step(33000)
    assert engine.phase == 'finished'
    assert engine.match_elapsed_ticks == 30000
    assert engine.reporting_elapsed_ticks == 3000
    for score in engine.scores.values():
        assert score == {'m1': 0, 'm2': 0, 'm3': 0, 'm4': 15, 'm5': 0, 'm6': 0, 'alliance_bonus': 5, 'total': 20}


def test_RULE_002_complete_m1(engine):
    expected = engine.orders['B-1']['expected_m1']
    assert score_m1(expected, expected) == 10

@pytest.mark.parametrize('field,points', [('target', 3), ('search_sectors', 3), ('base', 4)])
def test_RULE_003_partial_m1(engine, field, points):
    expected = engine.orders['B-1']['expected_m1']
    assert score_m1({field: expected[field]}, expected) == points


def test_RULE_004_sector_set(engine):
    ex = engine.orders['B-1']['expected_m1']
    assert score_m1({'search_sectors': list(reversed(ex['search_sectors']))}, ex) == 3
    assert score_m1({'search_sectors': ex['search_sectors'] + ['R-S2']}, ex) == 0


def test_RULE_005_replacement_m1(engine):
    start(engine)
    ex = engine.orders['B-1']['expected_m1']
    engine.request('m1', 'B-1', ex)
    ack = engine.request('m1', 'B-1', {'base': ex['base']})
    assert ack['received'] == {'target': None, 'search_sectors': None, 'base': ex['base']}
    assert score_m1(engine.reports['B-1']['m1'], ex) == 4


def test_RULE_006_complete_m3(engine):
    assert score_m3(report_for_inventory(engine.inventory), engine.inventory, 'BLUE') == 30


def test_RULE_007_one_wrong_count(engine):
    report = report_for_inventory(engine.inventory)
    report['sectors'][0]['objects'][0]['count'] += 1
    assert score_m3(report, engine.inventory, 'BLUE') == 23


def test_RULE_008_empty_vs_missing(engine):
    inventory = deepcopy(engine.inventory)
    inventory['R-S3'] = {c: 0 for c in OBJECT_CLASSES}
    assert score_m3({'sectors': [{'sector': 'R-S3', 'objects': []}]}, inventory, 'BLUE') == 7
    assert score_m3({'sectors': [{'sector': 'R-S2', 'objects': []}]}, inventory, 'BLUE') == 0


def test_RULE_009_zero_normalization(engine):
    empty = {'sectors': [{'sector': 'R-S3', 'objects': []}]}
    for cls in ('TANK', 'DRUM'):
        raw = {'sectors': [{'sector': 'R-S3', 'objects': [{'type': cls, 'count': 0}]}]}
        assert normalize_m3(raw) == empty
    assert_error(422, lambda: normalize_m3({'sectors': [{'sector': 'R-S3', 'objects': [{'type': 'unknown', 'count': 0}]}]}))


def test_RULE_010_own_sector(engine):
    assert score_m3(report_for_inventory(engine.inventory, ('B-S1',)), engine.inventory, 'BLUE') == 0


def test_RULE_011_m3_replacement(engine):
    start(engine)
    engine.request('m3', 'B-1', report_for_inventory(engine.inventory))
    engine.request('m3', 'B-1', report_for_inventory(engine.inventory, ('R-S1',)))
    assert score_m3(engine.reports['B-1']['m3'], engine.inventory, 'BLUE') == 7


def test_RULE_012_independent_missions(engine):
    start(engine)
    engine.request('m1', 'B-1', {'search_sectors': ['B-S1'], 'base': 'RED_COMMAND_POST'})
    engine.request('m3', 'B-1', report_for_inventory(engine.inventory))
    engine.match_elapsed_ticks = 24000
    engine._deadlines()
    assert engine.request('target', 'B-1')['order']['objective'] == 'RED_MAINTENANCE'
    assert score_m3(engine.reports['B-1']['m3'], engine.inventory, 'BLUE') == 30


def test_RULE_013_assignment_owner(engine):
    start(engine)
    engine.destroy_facility('RED_RADAR', actor='R-1')
    engine.request('finish')
    scores = engine._base_scores()
    assert scores['B-1']['m2'] == 10
    assert scores['B-2']['m2'] == 0


def test_RULE_014_alliance_targets(engine):
    start(engine)
    for code in ('RED_RADAR', 'RED_COMMS', 'RED_OUTPOST'):
        engine.destroy_facility(code)
    engine.request('finish')
    assert [engine._base_scores()[s]['m2'] for s in ('B-1', 'B-2', 'B-3')] == [15] * 3


def test_RULE_015_destroy_idempotent(engine):
    start(engine)
    assert engine.destroy_facility('RED_RADAR')
    assert not engine.destroy_facility('RED_RADAR')
    assert len(engine.destroyed) == 1

@pytest.mark.parametrize('hp,points', [(4,15),(3,12),(2,8),(1,3),(0,0)])
def test_RULE_016_hp_score(engine, hp, points):
    start(engine)
    engine.robots['B-1'].hp = hp
    engine.request('finish')
    assert engine._base_scores()['B-1']['m4'] == points


def test_RULE_017_friendly_fire(engine):
    start(engine)
    assert engine.apply_hit('B-2', 'B-1')
    engine.request('finish')
    scores = engine._base_scores()
    assert scores['B-2']['m4'] == 12
    assert scores['B-1']['m4'] == 15


def test_RULE_018_capture_assigned_camp(engine):
    start(engine)
    engine.match_elapsed_ticks = 24000
    engine._deadlines()
    blocked = dict(engine.base_blocked)
    blocked['RED_MAINTENANCE'] = True
    engine._capture_edges(blocked)
    assert engine.phase == 'reporting'
    assert [engine._base_scores()[s]['m5'] for s in SLOTS] == [10, 10, 10, 0, 0, 0]


def test_RULE_019_self_camp_intrusion(engine):
    start(engine)
    engine.match_elapsed_ticks = 24000
    engine._deadlines()
    engine.robots['B-2'].pose = Pose2(.6, 2.5, 0)
    engine._capture_edges(engine._blocked_bases())
    assert engine.capture_camp == 'RED'


def test_RULE_020_nonobjective(engine):
    start(engine)
    engine.match_elapsed_ticks = 24000
    engine._deadlines()
    blocked = dict(engine.base_blocked)
    blocked['RED_COMMAND_POST'] = True
    engine._capture_edges(blocked)
    assert engine.phase == 'running'

@pytest.mark.parametrize('ranking,expected', [(['R-1','R-2','R-3'],15),(['R-1','R-3','R-2'],10),(['R-2','R-1','R-3'],5),(['R-3','R-2','R-1'],5),(['R-2','R-3','R-1'],0),(['R-3','R-1','R-2'],0),(['R-1'],10),(['R-1','R-2'],10),(['R-2','R-1'],0)])
def test_RULE_021_m6_tiers(ranking, expected):
    assert score_m6(ranking, {'R-1': 3, 'R-2': 2, 'R-3': 1}) == expected


def test_RULE_022_exact_integer_ties():
    risks = dict(zip(('R-1','R-2','R-3'), [risk_numerator(4,0,0),risk_numerator(0,8,0),risk_numerator(0,0,30)]))
    assert len(accepted_rankings(risks)) == 6
    for ranking in permutations(risks):
        assert score_m6(ranking, risks) == 15


def test_RULE_023_freeze(engine):
    start(engine)
    engine.request('finish')
    frozen = deepcopy(engine.frozen)
    assert not engine.destroy_facility('RED_RADAR')
    assert not engine.apply_hit('B-1')
    assert engine.frozen == frozen
    assert_error(409, lambda: engine.request('m3', 'B-1', report_for_inventory(engine.inventory)))


def test_RULE_024_golden_scorer():
    rows = [(10,15,30,15,10,15),(7,15,14,12,10,10),(4,15,9,8,10,5),(10,10,21,12,0,15),(6,0,14,15,0,5),(0,0,30,3,0,0)]
    base = {s: {f'm{i+1}': v for i,v in enumerate(row)} for s,row in zip(SLOTS,rows)}
    scores = finalize_scores(base, set(SLOTS))
    assert [scores[s]['total'] for s in SLOTS] == [100,73,56,68,40,33]
    assert sum(scores[s]['total'] for s in SLOTS[:3]) == 229
    assert sum(scores[s]['total'] for s in SLOTS[3:]) == 141


def test_RULE_025_start_failure(engine):
    start(engine)
    engine.request('start_failure', 'B-1')
    assert_error(409, lambda: engine.request('m1','B-1',{'base':'RED_MAINTENANCE'}))
    engine.request('finish')
    engine.request('stop')
    assert engine.scores['B-1']['total'] == 0
    assert engine.scores['B-2']['total'] == 15  # BLUE loses alliance sum 30 to RED 45


def test_TIME_001_order_publication(engine):
    assert not engine.request('order','B-1')['accepted']
    start(engine)
    order = engine.request('order','B-1')
    assert order['accepted']
    engine.step(3)
    assert order == engine.request('order','B-1')


def test_TIME_002_objective_boundary(engine):
    start(engine)
    engine.match_elapsed_ticks = 23999
    assert not engine.request('target','B-1')['accepted']
    engine.step()
    assert engine.request('target','B-1')['accepted']


def test_TIME_003_deadline_report(engine):
    start(engine)
    engine.match_elapsed_ticks = 29999
    engine.request('m3','B-1',{'sectors':[{'sector':'CM','objects':[]}]})
    engine.step()
    assert_error(409, lambda: engine.request('m3','B-1',report_for_inventory(engine.inventory)))
    assert engine.reports['B-1']['m3']['sectors'][0]['objects'] == []


def test_TIME_004_capture_endpoint(engine):
    start(engine)
    engine.match_elapsed_ticks = 24499
    engine._deadlines()
    engine.base_blocked['RED_MAINTENANCE'] = False
    engine.robots['R-2'].pose = Pose2(5.52,2.5,math_pi())
    engine.step()
    assert engine.phase == 'reporting' and engine.match_elapsed_ticks == 24500
    assert engine.request('fire','B-1')['message'] == 'locked'
    assert engine.request('m6','B-1',{'ranking':['R-1','R-2','R-3']})['accepted']


def math_pi():
    return 3.141592653589793


def test_TIME_005_report_deadline(engine):
    start(engine)
    engine.request('finish')
    engine.reporting_elapsed_ticks = 2999
    engine.request('m6','B-1',{'ranking':['R-1']})
    engine.step()
    assert_error(409,lambda:engine.request('m6','B-2',{'ranking':['R-1']}))


def submit_five(e):
    for s in SLOTS[:-1]:
        opponent = 'R' if s.startswith('B') else 'B'
        e.request('m6',s,{'ranking':[f'{opponent}-1',f'{opponent}-2',f'{opponent}-3']})


def test_TIME_006_invalid_final_report(engine):
    start(engine); engine.request('finish'); submit_five(engine)
    assert_error(422,lambda:engine.request('m6','R-3',{'ranking':[]}))
    assert engine.phase == 'reporting' and len(engine.submitted_m6) == 5


def test_TIME_007_final_ack_then_finish(engine):
    start(engine); engine.request('finish'); submit_five(engine)
    ack = engine.request('m6','R-3',{'ranking':['B-1','B-2','B-3']})
    assert ack['accepted'] and engine.phase == 'finished'
    assert_error(409,lambda:engine.request('m6','B-1',{'ranking':['R-1']}))


def test_TIME_008_resubmit_count(engine):
    start(engine); engine.request('finish'); submit_five(engine)
    engine.request('m6','B-1',{'ranking':['R-2']})
    assert len(engine.submitted_m6) == 5 and engine.phase == 'reporting'


def test_TIME_009_pause_clock_and_reports(engine):
    start(engine); engine.match_elapsed_ticks = engine.robot_effect_ticks = 10000
    engine.request('pause'); engine.step(1000)
    assert engine.match_elapsed_ticks == engine.robot_effect_ticks == 10000
    assert engine.sim_tick == 1000 and engine.request('me','B-1')['phase'] == 'running'
    assert engine.request('m1','B-1',{'base':'RED_MAINTENANCE'})['accepted']
    engine.request('resume')


def test_TIME_010_cancel_actions(engine):
    start(engine)
    engine.request('cmd_vel','B-1',{'linear_x_mps':.6,'angular_z_rps':0})
    engine.request('fire','B-1'); engine.request('gimbal','B-1',{'pan':100,'tilt':0,'speed':10,'acc':20})
    engine.request('pause'); engine.step(5); engine.request('resume')
    r=engine.robots['B-1']
    assert r.v == r.omega == 0 and r.target_pan == r.pan and r.laser_until <= engine.robot_effect_ticks


def contact_fixture(engine, monkeypatch):
    start(engine)
    engine.robots['B-1'].laser_until=100000
    import maicon_sim.core.geometry3d as geometry
    contacts={('B-1','R-1')}
    monkeypatch.setattr(geometry,'laser_contacts',lambda *args: set(contacts))
    return contacts


def test_TIME_011_dwell_boundary(engine, monkeypatch):
    contact_fixture(engine,monkeypatch)
    engine.step(199); assert engine.robots['R-1'].hp == 4
    engine.step(); assert engine.robots['R-1'].hp == 3


def test_TIME_012_dwell_gap(engine, monkeypatch):
    contacts=contact_fixture(engine,monkeypatch)
    engine.step(100); contacts.clear(); engine.step(); contacts.add(('B-1','R-1')); engine.step(100)
    assert engine.robots['R-1'].hp == 4


def test_TIME_013_emitters_separate(engine, monkeypatch):
    contacts=contact_fixture(engine,monkeypatch)
    engine.robots['B-2'].laser_until=100000
    engine.step(100); contacts.clear(); contacts.add(('B-2','R-1')); engine.step(100)
    assert engine.robots['R-1'].hp == 4


def test_TIME_014_laser_expiry(engine):
    start(engine)
    assert engine.request('fire','B-1')['message']=='fired'
    engine.step(499); assert engine.robots['B-1'].laser_until > engine.robot_effect_ticks
    engine.step(); assert engine.robots['B-1'].laser_until == engine.robot_effect_ticks
    engine.step(499); assert engine.request('fire','B-1')['message']=='reloading'
    engine.step(); assert engine.request('fire','B-1')['message']=='fired'


def test_TIME_015_ammo_eight(engine):
    start(engine)
    for _ in range(8):
        assert engine.request('fire','B-1')['message']=='fired'
        engine.step(1000)
    assert engine.request('fire','B-1')['message']=='empty'


def test_TIME_016_invulnerability_no_accumulation(engine,monkeypatch):
    contact_fixture(engine,monkeypatch)
    engine.step(200); assert engine.robots['R-1'].hp==3
    engine.step(1199); assert engine.robots['R-1'].hp==3
    engine.step(); assert engine.robots['R-1'].hp==2


def test_TIME_017_hp_zero_recovers_controls(engine):
    start(engine); engine.robots['B-1'].hp=1; engine.apply_hit('B-1')
    assert engine.request('fire','B-1')['message']=='locked'
    assert engine.robots['B-1'].hp==0
    engine.step(1000)
    assert engine.request('fire','B-1')['message']=='fired'


def test_TIME_018_hp_zero_rehit(engine):
    start(engine); engine.robots['B-1'].hp=0
    assert engine.apply_hit('B-1')
    assert engine.robots['B-1'].hp==0 and engine.robots['B-1'].drive_locked_until==1000


def test_TIME_019_watchdog(engine):
    start(engine)
    engine.robots['B-1'].pose=Pose2(.4,3.2,0)
    engine.request('cmd_vel','B-1',{'linear_x_mps':.6,'angular_z_rps':0})
    engine.step(50); x=engine.robots['B-1'].pose.x_m
    assert x==pytest.approx(.7,abs=1e-9)
    engine.step(20); assert engine.robots['B-1'].pose.x_m==x


def test_TIME_020_prepublish_blocked_requires_new_edge(engine):
    start(engine)
    engine.robots['R-2'].pose=Pose2(5.52,2.5,0)
    engine._capture_edges(engine._blocked_bases())
    engine.match_elapsed_ticks=23999; engine.step()
    assert engine.phase=='running'
    engine.robots['R-2'].pose=Pose2(5.72,2.5,0); engine.step()
    engine.robots['R-2'].pose=Pose2(5.52,2.5,0); engine.step()
    assert engine.phase=='reporting' and engine.capture_camp=='BLUE'


def test_TIME_021_simultaneous_capture_stable_order(engine):
    start(engine); engine.match_elapsed_ticks=24000; engine._deadlines()
    blocked=dict(engine.base_blocked)
    blocked['BLUE_MAINTENANCE']=blocked['RED_MAINTENANCE']=True
    engine._capture_edges(blocked)
    assert engine.capture_camp=='RED'


def test_TIME_022_deadline_before_geometry(engine):
    start(engine); engine.match_elapsed_ticks=29999
    engine.robots['R-2'].pose=Pose2(5.52,2.5,0)
    engine.step()
    assert engine.phase=='reporting' and engine.end_reason=='timeout' and engine.capture_camp is None


def test_TIME_023_publish_before_geometry(engine):
    start(engine); engine.match_elapsed_ticks=23999
    engine.robots['R-2'].pose=Pose2(5.52,2.5,0)
    engine.step()
    assert engine.target_published and engine.phase=='reporting' and engine.capture_camp=='BLUE'


def test_TIME_024_empty_eligible(engine):
    engine.request('enter_ready'); engine.request('start')
    assert engine.phase=='finished' and engine.end_reason=='no_eligible'
    assert all(s['total']==0 for s in engine.scores.values())


def test_TIME_025_practice_effect_clock(config):
    config.scenario['mode']='practice'
    e=MatchEngine(config)
    assert e.request('fire','B-1')['message']=='fired'
    e.step(1000)
    assert e.robot_effect_ticks==1000 and e.robots['B-1'].ammo==8
    assert e.request('fire','B-1')['message']=='fired'


def test_CORE_checkpoint_preserves_effects(engine,monkeypatch):
    contact_fixture(engine,monkeypatch)
    engine.step(123)
    state=json.loads(json.dumps(engine.export_state()))
    engine.step(100)
    expected=engine.export_state()
    restored=MatchEngine(engine.config)
    restored.restore_state(state)
    restored.step(100)
    assert restored.export_state()==expected


def test_CORE_queue_reset_cancels_old_session(engine):
    first=engine.enqueue('reset')
    second=engine.enqueue('ready','B-1')
    engine.step()
    assert first.result()['match_id'].endswith('0002')
    assert_error(409,second.result)


def test_RULE_024_engine_golden_six_team_fixture(engine):
    """Evaluator-only hand-authored snapshot, not participant truth access."""
    start(engine)
    # M1 10,7,4,10,6,0 and M3 30,14,9,21,14,30.
    fields = [('target','search_sectors','base'),('target','base'),('base',),
              ('target','search_sectors','base'),('target','search_sectors'),()]
    sectors = [('R-S1','R-S2','R-S3','CM'),('R-S1','R-S2'),('CM',),
               ('B-S1','B-S2','B-S3'),('B-S1','B-S2'),('B-S1','B-S2','B-S3','CM')]
    for slot, names, ss in zip(SLOTS, fields, sectors):
        expected = engine.orders[slot]['expected_m1']
        if names:
            engine.request('m1', slot, {k: expected[k] for k in names})
        engine.request('m3', slot, report_for_inventory(engine.inventory, ss))
    for slot,hp,ammo in zip(SLOTS,(4,3,2,3,4,1),(4,2,6,4,2,6)):
        engine.robots[slot].hp=hp
        engine.robots[slot].ammo=ammo
    for code in ('RED_RADAR','RED_COMMS','RED_OUTPOST','BLUE_RADAR'):
        engine.destroy_facility(code)
    engine.capture_camp='BLUE'
    engine.request('finish')
    rankings=[['R-3','R-1','R-2'],['R-3','R-2','R-1'],['R-2','R-1','R-3'],
              ['B-1','B-3','B-2'],['B-2','B-3','B-1'],['B-3','B-2','B-1']]
    for slot,ranking in zip(SLOTS,rankings):
        assert engine.request('m6',slot,{'ranking':ranking})['accepted']
    assert engine.phase=='finished'
    assert [engine.scores[s]['total'] for s in SLOTS]==[100,73,56,68,40,33]


def test_CORE_replay_scheduled_inputs_once(config):
    config.scenario['events']=[
        {'event_id':'motion','clock':'sim','at_ms':10,'kind':'robot_command',
         'parameters':{'slot':'B-1','linear_x_mps':.05,'angular_z_rps':0.,'duration_ms':100}},
        {'event_id':'pause','clock':'sim','at_ms':150,'kind':'pause','parameters':{}},
        {'event_id':'resume','clock':'sim','at_ms':200,'kind':'resume','parameters':{}},
        {'event_id':'destroy','clock':'sim','at_ms':300,'kind':'drone_facility_destroyed','parameters':{'facility_code':'BLUE_RADAR'}}]
    original=start(MatchEngine(config))
    original.step(50)
    original.request('stop')
    inputs=[deepcopy(e) for e in original.journal if e['category']=='input']
    replay=MatchEngine(config)
    replay.begin_replay()
    for event in inputs:
        replay.step(event['sim_tick']-replay.sim_tick)
        replay.replay_input(event)
    assert replay.journal==original.journal
    assert replay.export_state()==original.export_state()


def test_CORRECTION_001_before_freeze(config):
    config.scenario['events']=[{'event_id':'judge','clock':'match','at_ms':10,
        'kind':'robot_state_correction','parameters':{'slot':'R-1','hp':2,'ammo':3}}]
    e=start(MatchEngine(config))
    e.step(2)
    assert e.robots['R-1'].hp==2 and e.robots['R-1'].ammo==3
    e.request('finish')
    assert e.frozen['robots']['R-1']=={'hp':2,'ammo':3}


def test_CORRECTION_002_after_freeze_rejected(engine):
    start(engine); engine.request('finish')
    frozen=deepcopy(engine.frozen)
    engine.request('fault',payload={'fault_id':'robot_state_correction','at_tick':0,'scope':'R-1','parameters':{'hp':0,'ammo':0}})
    engine.step()
    assert engine.frozen==frozen and engine.robots['R-1'].hp==4
    assert any(e['kind']=='event_rejected' and e['payload']['status']==409 for e in engine.journal)

@pytest.mark.parametrize('payload', [{'slot':'R-1'}, {'slot':'R-1','hp':True}, {'slot':'R-1','hp':1.0},
    {'slot':'R-1','hp':-1}, {'slot':'R-1','hp':5}, {'slot':'R-1','ammo':9}, {'slot':'R-1','hp':1,'pose':{}}, {'slot':'nobody','hp':1}])
def test_CORRECTION_003_strict_private_only(engine,payload):
    start(engine)
    assert_error(422,lambda:engine.request('fault',payload={'fault_id':'robot_state_correction','parameters':payload}))
    assert_error(404,lambda:engine.request('robot_state_correction','B-1',payload))


def test_LASER_receiver_side_switch_does_not_merge_dwell(engine,monkeypatch):
    contacts=contact_fixture(engine,monkeypatch)
    contacts.clear();contacts.add(('B-1','R-1/receiver/0'))
    engine.step(100)
    contacts.clear();contacts.add(('B-1','R-1/receiver/1'))
    engine.step(100)
    assert engine.robots['R-1'].hp==4
    engine.step(100)
    assert engine.robots['R-1'].hp==3


def test_LASER_same_boundary_two_receivers_one_hit(engine,monkeypatch):
    contacts=contact_fixture(engine,monkeypatch)
    engine.robots['B-2'].laser_until=100000
    contacts.clear();contacts.update({('B-1','R-1/receiver/0'),('B-2','R-1/receiver/1')})
    engine.step(200)
    assert engine.robots['R-1'].hp==3
    assert sum(event['kind']=='hit_applied' for event in engine.journal)==1


def test_CORE_queue_category_priority_before_ingress_fifo(engine):
    start(engine)
    action=engine.enqueue('fire','B-1')
    report=engine.enqueue('m1','B-1',{'base':'RED_SUPPLY_DEPOT'})
    engine.step()
    assert action.result()['message']=='fired' and report.result()['accepted']
    applied=[e['payload']['kind'] for e in engine.journal if e['category']=='input'][-2:]
    assert applied==['m1','fire']
    # A same-boundary supervisor finish closes M1 first, even when M1 entered
    # the HTTP ingress queue before the supervisor command was scheduled.
    stale=engine.enqueue('m1','B-1',{'base':'RED_MAINTENANCE'})
    finish=engine.enqueue('finish')
    engine.step()
    assert finish.result()['accepted']
    assert_error(409,stale.result)
    assert engine.frozen['reports']['B-1']['m1']['base']=='RED_SUPPLY_DEPOT'


def test_CORE_process_lifecycle_is_logged_replayed_without_rule_changes(engine):
    start(engine)
    before=engine.snapshot()
    future=engine.enqueue('process_lifecycle','B-1',{'event':'restarted','generation':1,'exit_code':-9})
    engine.step()
    assert future.result()=={'accepted':True}
    event=[e for e in engine.journal if e['kind']=='process_lifecycle'][-1]
    assert event['category']=='input' and event['actor']=='B-1'
    assert engine.reports==before['reports'] and engine.robots['B-1'].ready
    replay=MatchEngine(engine.config)
    start(replay)
    replay.begin_replay()
    replay.replay_input(event)
    assert replay.journal[-1]['kind']=='process_lifecycle'
    assert replay.reports==before['reports']
    assert_error(422,lambda:engine.request('process_lifecycle','B-1',{'event':'unknown'}))
    assert_error(409,lambda:engine.request('process_lifecycle','unknown',{'event':'started'}))


@pytest.mark.parametrize('value',[float('nan'),float('inf'),float('-inf')])
def test_CORE_nonfinite_ingress_rejected_with_strict_replayable_journal(config,value):
    records=[]
    e=MatchEngine(config,event_sink=lambda event:records.append(json.dumps(event,allow_nan=False)))
    start(e)
    payload={'sectors':[{'sector':'CM','objects':[{'type':'TANK','count':value}]}]}
    assert_error(422,lambda:e.request('m3','B-1',payload))
    event=e.journal[-1]
    assert event['payload']['payload']=={}
    assert event['payload']['validation_error']['type']=='nonfinite'
    assert e.reports['B-1']['m3'] is None and e.report_rejections==1
    replay=MatchEngine(config);start(replay);replay.begin_replay()
    assert_error(422,lambda:replay.replay_input(event))
    assert e.journal[-1]==replay.journal[-1]
    assert replay.report_rejections==1 and len(records)>1


def test_CORE_queue_peak_measures_ingress_and_resets_session(engine):
    futures=[engine.enqueue('me','B-1') for _ in range(7)]
    assert engine.queue_peak==7
    engine.step()
    assert all(f.done() for f in futures) and engine.queue_peak==7
    engine.request('reset')
    assert engine.queue_peak==0


def test_CORE_queued_reset_publishes_new_tick_zero(engine):
    start(engine);engine.step(7)
    reset=engine.enqueue('reset')
    engine.step()
    assert reset.result()['match_id'].endswith('0002')
    assert engine.sim_tick==0
    engine.step()
    assert engine.sim_tick==1


def test_TIME_009_public_match_distinguishes_resume_and_preserves_checkpoint(engine):
    from maicon_sim.sensors.gateway import SensorGateway
    gateway=SensorGateway(engine.config)
    try:
        gateway.update(engine)
        assert gateway.get('B-1','match')['cmd']=='standby'
        start(engine)
        engine.step(50);gateway.update(engine)
        assert gateway.get('B-1','match')['cmd']=='start'
        engine.request('pause')
        engine.step(50);gateway.update(engine)
        assert gateway.get('B-1','match')['cmd']=='pause'
        assert engine.match_elapsed_ticks==50
        engine.request('resume')
        engine.step(50);gateway.update(engine)
        assert gateway.get('B-1','match')['cmd']=='resume'
        assert engine.snapshot()['match_command']=='resume'
        assert engine.match_elapsed_ticks==100
        checkpoint=json.loads(json.dumps(engine.export_state()))
        restored=MatchEngine(engine.config);restored.restore_state(checkpoint)
        assert restored.cmd=='resume'
        assert restored.export_state()==engine.export_state()
        engine.request('finish')
        assert engine.cmd=='report'
        engine.request('stop')
        assert engine.cmd=='stop'
        engine.request('reset')
        assert engine.cmd=='standby'
        # Backward compatibility for checkpoints written before command tracking.
        checkpoint.pop('_match_command')
        restored.restore_state(checkpoint)
        assert restored.cmd=='start'
        checkpoint['paused']=True
        restored.restore_state(checkpoint)
        assert restored.cmd=='pause'
    finally:gateway.close()
