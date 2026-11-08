"""Re-execute recorded inputs; compare effects rather than injecting effects."""
from copy import deepcopy
import json
from pathlib import Path
import pytest
from maicon_sim.config.loader import load_scenario
from maicon_sim.evaluation.runner import run_episode
from maicon_sim.evaluation.replay import replay_inputs, load_recorded_config, verify_files
from maicon_sim.evaluation.compare import compare, read_events


def short_scheduled_fixture():
    c=load_scenario('examples/scenario_smoke_six.yaml')
    c.scenario['scenario_id']='replay_contract_short_explicit_fixture'
    c.rules['timing'].update({'match_ms':500,'objective_publish_ms':200,'report_ms':100})
    c.scenario['events']=[
        {'event_id':'script','clock':'sim','at_ms':20,'kind':'robot_command',
         'parameters':{'slot':'B-1','linear_x_mps':.05,'angular_z_rps':0.,'duration_ms':100}},
        {'event_id':'pause','clock':'sim','at_ms':150,'kind':'pause','parameters':{}},
        {'event_id':'resume','clock':'sim','at_ms':250,'kind':'resume','parameters':{}},
        {'event_id':'adjudication','clock':'match','at_ms':300,'kind':'robot_state_correction',
         'parameters':{'slot':'R-1','hp':3,'ammo':6}},
        {'event_id':'report-delay','clock':'sim','at_ms':50,'kind':'http_delay',
         'parameters':{'slot':'B-1','path':'/api/report/detection','duration_ms':20,'stage':'before_ingress',
                       'match_occurrence':1,'drop_response_after_commit':False}}]
    from maicon_sim.config.loader import canonical_hash
    c.hashes['scenario_hash']=canonical_hash(c.scenario)
    c.hashes['rule_profile_hash']=canonical_hash(c.rules)
    return c


@pytest.mark.integration
def test_REPLAY_001_004_scheduled_actions_reexecute_identical_effects(tmp_path):
    config=short_scheduled_fixture()
    _,original=run_episode(config,out=tmp_path/'original',backend='2d')
    inputs=replay_inputs(original)
    assert any(e['payload']['kind']=='scheduled_event' for e in inputs)
    assert any(e['kind']=='robot_command' for e in inputs)
    _,replayed=run_episode(load_recorded_config(original),out=tmp_path/'replayed',backend='2d',replay_events=inputs)
    checked=compare(original,replayed,mode='core')
    assert checked['equal'],checked
    original_effects=[e for e in read_events(original) if e['category']=='derived']
    replay_effects=[e for e in read_events(replayed) if e['category']=='derived']
    assert len(original_effects)==len(replay_effects)
    assert sum(e['kind']=='robot_state_corrected' for e in replay_effects)==1
    assert sum(e['kind']=='paused' for e in replay_effects)==1
    assert sum(e['kind']=='resumed' for e in replay_effects)==1
    assert json.loads((original/'result.json').read_text())['final_match_ms']==500


@pytest.mark.integration
@pytest.mark.parametrize('damage',['alter','truncate'])
def test_REPLAY_008_corrupted_journal_is_rejected(tmp_path,damage):
    _,root=run_episode(short_scheduled_fixture(),out=tmp_path/'original',backend='2d')
    verify_files(root)
    path=root/'private/events.jsonl'
    lines=path.read_text().splitlines()
    if damage=='alter':
        line=json.loads(lines[1]);line['sim_tick']+=1;lines[1]=json.dumps(line)
    else:lines.pop(len(lines)//2)
    path.write_text('\n'.join(lines)+'\n')
    with pytest.raises(ValueError,match='checksum|sequence|event_seq'):
        verify_files(root)


@pytest.mark.integration
def test_REPLAY_005_private_file_checkpoint_resumes_sensor_and_core(tmp_path):
    from maicon_sim.core.engine import MatchEngine
    from maicon_sim.sensors.gateway import SensorGateway
    from maicon_sim.evaluation.checkpoints import save_checkpoint,restore_checkpoint,read_checkpoint
    from maicon_sim.core.events import canonical
    config=short_scheduled_fixture()
    config.scenario['noise_profile']='stress_v1'
    original=MatchEngine(config);gateway=SensorGateway(config)
    original.request('enter_ready')
    for slot in original.robots:original.request('ready',slot)
    original.request('start')
    gateway.update(original)
    for _ in range(35):original.step();gateway.update(original)
    metadata=save_checkpoint(tmp_path/'private/checkpoint-00000035.json',original,gateway)
    path=Path(metadata['path'])
    resumed=MatchEngine(config);other=SensorGateway(config)
    try:
        assert restore_checkpoint(path,resumed,other)['sim_tick']==35
        assert original.export_state()==resumed.export_state()
        for _ in range(30):
            original.step();gateway.update(original)
            resumed.step();other.update(resumed)
            for slot in original.robots:
                for channel in ('state','match','odom','imu','scan','semantic'):
                    assert canonical(gateway.get(slot,channel))==canonical(other.get(slot,channel))
        assert original.export_state()==resumed.export_state()
        bad=json.loads(path.read_text());bad['core_state']['robots']['B-1']['ammo']=0
        path.write_text(json.dumps(bad))
        with pytest.raises(ValueError,match='checksum'):read_checkpoint(path,config)
    finally:gateway.close();other.close()
