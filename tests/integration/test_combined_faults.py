"""Admission isolation and a recorded composite fault run over real local HTTP."""
import asyncio
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import time
from types import SimpleNamespace

import httpx
import pytest

from maicon_sim.config.loader import canonical_hash, load_scenario, validate_schema
from maicon_sim.core.engine import MatchEngine
from maicon_sim.evaluation.compare import compare, read_events
from maicon_sim.evaluation.metrics import file_hash, write_json
from maicon_sim.evaluation.recorder import Recorder
from maicon_sim.evaluation.realtime import LocalServers, ParticipantProcesses
from maicon_sim.evaluation.replay import load_recorded_config, replay_inputs, verify_files
from maicon_sim.evaluation.runner import build_backend, make_result, run_episode
from maicon_sim.sdk.http_port import HTTPPort, PortError
from maicon_sim.sdk.report_worker import ReportWorker
from maicon_sim.server.app import create_apps
from maicon_sim.server.runtime import EngineRuntime
from maicon_sim.sensors.gateway import SensorGateway

pytestmark = pytest.mark.integration


def until(predicate, timeout=6.):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(.01)
    raise AssertionError("composite fixture did not reach expected state")


@pytest.mark.parametrize("failure", ["not_ready", "start_failure"])
def test_E2E_003_one_ineligible_team_does_not_block_other_five(failure):
    config = load_scenario('examples/scenario_smoke_six.yaml')
    config.rules['timing'].update(match_ms=1000, objective_publish_ms=800, report_ms=1000)
    engine = MatchEngine(config)
    engine.request('enter_ready')
    public, _ = create_apps(engine)
    runtime = EngineRuntime(engine).start()
    async def exercise():
        client = httpx.AsyncClient(base_url='http://participant.test', transport=httpx.ASGITransport(app=public))
        ports = {a['slot']: HTTPPort('http://participant.test', a['mission_code'], client=client) for a in config.scenario['agents']}
        excluded = 'B-3'
        try:
            for slot, port in ports.items():
                if slot != excluded or failure == 'start_failure':
                    assert (await port.ready())['accepted']
            await asyncio.wrap_future(engine.enqueue('start'))
            if failure == 'start_failure':
                await asyncio.wrap_future(engine.enqueue('start_failure', excluded))
            assert excluded not in engine.eligible
            assert len(engine.eligible) == 5
            with pytest.raises(PortError) as rejected:
                await ports[excluded].submit_m1({'base': 'RED_SUPPLY_DEPOT'})
            assert rejected.value.status == 409
            accepted = await ports['B-1'].submit_m1({'base': 'RED_SUPPLY_DEPOT'})
            assert accepted['accepted']
            deadline = time.monotonic() + 3.
            while engine.phase == 'running' and time.monotonic() < deadline:
                await asyncio.sleep(.01)
            assert engine.phase == 'reporting'
            responses = []
            for slot in sorted(engine.eligible):
                enemy = 'R' if slot.startswith('B') else 'B'
                responses.append(await ports[slot].submit_m6([f'{enemy}-{n}' for n in (1, 2, 3)]))
            assert all(r['accepted'] and 'received' in r for r in responses)
            assert engine.phase == 'finished'
            assert engine.submitted_m6 == engine.eligible
            assert len(engine.submitted_m6) == 5
            assert all(value == 0 for value in engine.scores[excluded].values())
            assert all(engine.scores[slot]['total'] > 0 for slot in engine.eligible)
            assert runtime.failure is None
        finally:
            await public.state.service.close()
            await client.aclose()
    try:
        asyncio.run(exercise())
    finally:
        runtime.close()


def composite_config():
    config = load_scenario('examples/scenario_smoke_six.yaml')
    config.scenario['scenario_id'] = 'composite_stale_drone_pause_restart'
    config.scenario['seed'] = 41010
    config.rules['timing'].update(match_ms=1800, objective_publish_ms=1500, report_ms=300)
    config.scenario['events'] = [{
        'event_id': 'stale-A-delay', 'clock': 'sim', 'at_ms': 0, 'kind': 'http_delay',
        'parameters': {'slot': 'B-1', 'path': '/api/report/interpretation',
                       'duration_ms': 400, 'stage': 'before_ingress',
                       'match_occurrence': 1, 'drop_response_after_commit': False}}]
    config.hashes['scenario_hash'] = canonical_hash(config.scenario)
    config.hashes['rule_profile_hash'] = canonical_hash(config.rules)
    return config


@pytest.mark.e2e
def test_E2E_010_real_HTTP_composite_stale_drone_pause_process_restart_and_core_replay(tmp_path):
    """Fixed seed plus actual recorded ingress, not seed-only wall determinism."""
    config = composite_config()
    root = tmp_path / 'original'
    recorder = Recorder(root, config, 'combined-fixture', '2d', 'realtime')
    scene, assets = build_backend(config, '2d', root)
    engine = MatchEngine(config, event_sink=recorder.event)
    engine.request('enter_ready')
    gateway = SensorGateway(config, scene)
    public, admin = create_apps(engine, gateway)
    runtime = EngineRuntime(engine, gateway).start()
    servers = LocalServers(public, admin).start()
    children = ParticipantProcesses(SimpleNamespace(scenario={'agents': [config.scenario['agents'][0]]}),
                                     servers.public_url, root, engine)
    started = time.monotonic()
    evidence = {}
    try:
        children.start()
        until(lambda: engine.robots['B-1'].ready)
        engine.enqueue('start').result(timeout=3.)

        async def requests():
            async with HTTPPort(servers.public_url, 'SIMB0001') as participant:
                await participant.session()
                before, before_headers = await participant.drone()
                snapshot_hash = hashlib.sha256(before).hexdigest()
                # Relative sim-clock scheduling avoids a resume on a frozen match
                # clock. All three faults enter the actual single-writer journal.
                anchor = engine.sim_tick
                for name, at, kind, parameters in (
                    ('drone-stop', anchor + 1, 'sensor_dropout', {'slot': 'B-1', 'sensor': 'drone', 'duration_ms': 2000}),
                    ('pause', anchor + 20, 'pause', {}),
                    ('resume', anchor + 50, 'resume', {})):
                    engine.enqueue('fault', payload={'event_id': name, 'clock': 'sim', 'at_tick': at,
                                                    'kind': kind, 'parameters': parameters}).result(timeout=3.)
                worker = ReportWorker(participant, 'm1', timeout_s=.03)
                value_a = {'target': 'RED_RADAR'}
                value_b = {'base': 'RED_SUPPLY_DEPOT'}
                worker.update(value_a)
                assert await worker.flush_once() is None
                assert worker.errors[-1]['kind'] == 'TimeoutError'
                worker.timeout_s = 1.
                worker.update(value_b)
                assert (await worker.flush_once())['accepted']
                assert engine.reports['B-1']['m1']['base'] == 'RED_SUPPLY_DEPOT'
                # The timed-out request really commits late while HTTP phase is
                # still running (including pause); then latest-snapshot repair wins.
                deadline = time.monotonic() + 2.
                while engine.reports['B-1']['m1']['target'] != 'RED_RADAR' and time.monotonic() < deadline:
                    await asyncio.sleep(.01)
                assert engine.reports['B-1']['m1']['target'] == 'RED_RADAR'
                assert engine.reports['B-1']['m1']['base'] is None
                assert (await worker.flush_once())['accepted']
                repaired = deepcopy(engine.reports['B-1']['m1'])
                after, after_headers = await participant.drone()
                assert before == after
                assert before_headers['x-captured-at'] == after_headers['x-captured-at']
                recorder.observation('B-1', 'drone', {'sequence': 1, 'captured_tick': anchor,
                    'received_tick': engine.sim_tick, 'frame_sha256': snapshot_hash,
                    'captured_at': before_headers['x-captured-at'], 'repeated': True})
                original_pid = children.children['B-1'].pid
                prior_tick = engine.sim_tick
                children.children['B-1'].kill()
                children.children['B-1'].wait(timeout=3.)
                children.check()
                assert children.restarts['B-1'] == 1
                assert children.children['B-1'].pid != original_pid
                # OS restart is observed, then recorded as a no-adjudication input.
                await asyncio.wrap_future(engine.enqueue('process_lifecycle', 'B-1',
                    {'event': 'restarted', 'generation': 1, 'exit_code': -9}))
                deadline = time.monotonic() + 3.
                while not any(e['sim_tick'] > prior_tick and e['actor'] == 'B-1' and
                              e['kind'] == 'http_request_ingress' and e['payload']['kind'] == 'me'
                              for e in engine.journal) and time.monotonic() < deadline:
                    await asyncio.sleep(.01)
                assert any(e['sim_tick'] > prior_tick and e['actor'] == 'B-1' and
                           e['kind'] == 'http_request_ingress' and e['payload']['kind'] == 'me'
                           for e in engine.journal)
                assert children.children['B-1'].poll() is None
                assert engine.reports['B-1']['m1'] == repaired
                assert any(e['kind'] == 'paused' for e in engine.journal)
                deadline = time.monotonic() + 2.
                while not any(e['kind'] == 'resumed' for e in engine.journal) and time.monotonic() < deadline:
                    await asyncio.sleep(.01)
                assert not engine.paused
                assert any(e['kind'] == 'resumed' for e in engine.journal)
                evidence.update({'pid_changed': True, 'restarts': 1, 'latest_report_repaired': True,
                                 'repeated_drone_hash': snapshot_hash,
                                 'captured_at_preserved': True, 'fixed_seed': config.scenario['seed']})
                await worker.close()
                deadline = time.monotonic() + 5.
                while engine.phase != 'finished' and time.monotonic() < deadline:
                    await asyncio.sleep(.01)
                assert engine.phase == 'finished'
                with pytest.raises(PortError) as late:
                    await participant.submit_m1(value_a)
                assert late.value.status == 409
                assert engine.reports['B-1']['m1'] == repaired
        asyncio.run(requests())
        children.close()
        assert runtime.failure is None
        assert public.state.service.waiters.active == 0
        assert len(engine.journal) < 20000
        runtime.close()
        assert engine.scores['B-1']['total'] == 24
        assert all(engine.scores[s]['total'] == 0 for s in engine.robots if s != 'B-1')
        metrics = {'wall_s': time.monotonic() - started, 'ticks_skipped': 0, 'composite': evidence}
        result = make_result(engine, config, 'combined-fixture', '2d', 'realtime', metrics['wall_s'], gateway)
        result['asset_manifest_hash'] = file_hash(assets.manifest_path)
        validate_schema(result, 'run_result')
        write_json(root / 'summary/composite_evidence.json', evidence)
        recorder.finish(result, metrics, gateway.capabilities,
                        {'asset_manifest_hash': result['asset_manifest_hash'], 'resolved_assets': 'private/assets/resolved_manifest.yaml'})
        verify_files(root)
        inputs = replay_inputs(root)
        assert any(e['kind'] == 'process_lifecycle' for e in inputs)
        _, replayed = run_episode(load_recorded_config(root), backend='2d', clock='accelerated',
                                 out=tmp_path / 'replayed', replay_events=inputs)
        checked = compare(root, replayed, mode='core')
        assert checked['equal'], checked
        effects = read_events(replayed)
        assert sum(e['kind'] == 'paused' for e in effects) == 1
        assert sum(e['kind'] == 'resumed' for e in effects) == 1
        assert json.loads((replayed / 'result.json').read_text())['scores']['B-1']['total'] == 24
    finally:
        children.close()
        servers.close()
        runtime.close()
        recorder.close()
        gateway.close()
        if scene:
            scene.close()
