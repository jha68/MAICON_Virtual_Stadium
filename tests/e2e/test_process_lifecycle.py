"""Real participant executable lifecycle: no fake Popen or fabricated restarts."""
import json
import os
from pathlib import Path
import time
import pytest
from maicon_sim.config.loader import load_scenario
from maicon_sim.core.engine import MatchEngine
from maicon_sim.evaluation.realtime import LocalServers, ParticipantProcesses
from maicon_sim.server.app import create_apps
from maicon_sim.server.runtime import EngineRuntime
from maicon_sim.sensors.gateway import SensorGateway


def until(predicate, timeout=10., message='condition did not become true'):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        if predicate():return
        time.sleep(.02)
    raise AssertionError(message)


@pytest.mark.e2e
@pytest.mark.integration
def test_E2E_004_005_006_ISO_006_real_children_restart_limit_and_report_preservation(tmp_path):
    config=load_scenario('examples/scenario_smoke_six.yaml')
    engine=MatchEngine(config)
    engine.request('enter_ready')
    gateway=SensorGateway(config)
    public,admin=create_apps(engine,gateway,admin_token='test-only-admin-never-in-child')
    runtime=EngineRuntime(engine,gateway).start()
    processes=None
    servers=LocalServers(public,admin).start()
    try:
        processes=ParticipantProcesses(config,servers.public_url,tmp_path,engine)
        processes.start()
        until(lambda:all(r.ready for r in engine.robots.values()),timeout=15,
              message='all six genuine participant executables must reach ready')
        assert len(set(c.pid for c in processes.children.values()))==6
        # Normal launcher privacy applies to every real child, including restarts.
        allowed_env={'PATH','LANG','PYTHONUNBUFFERED','MAICON_SIM_MISSION_CODE'}
        for slot,child in processes.children.items():
            environment=(Path('/proc')/str(child.pid)/'environ').read_bytes().split(b'\0')
            names={item.split(b'=',1)[0].decode() for item in environment if item}
            assert names<=allowed_env
            assert (Path('/proc')/str(child.pid)/'cwd').resolve()==tmp_path/'public'/slot
            args=(Path('/proc')/str(child.pid)/'cmdline').read_bytes()
            assert b'private' not in args and b'admin' not in args
        engine.enqueue('start').result(timeout=3)
        payload={'base':'RED_SUPPLY_DEPOT'}
        engine.enqueue('m1','B-1',payload).result(timeout=3)
        stored=json.loads(json.dumps(engine.reports['B-1']['m1']))
        match_id=engine.match_id
        peers={s:child.pid for s,child in processes.children.items() if s!='B-1'}
        replacement_pids=[]
        for crash_index in range(4):
            victim=processes.children['B-1']
            prior_tick=engine.sim_tick
            victim.kill();victim.wait(timeout=3)
            processes.check()
            assert engine.match_id==match_id and engine.phase=='running'
            assert engine.reports['B-1']['m1']==stored
            assert all(processes.children[s].pid==pid and processes.children[s].poll() is None for s,pid in peers.items())
            if crash_index<3:
                replacement=processes.children['B-1']
                assert replacement.pid!=victim.pid
                replacement_pids.append(replacement.pid)
                assert processes.restarts['B-1']==crash_index+1
                # An actual HTTP request from the new interpreter establishes
                # that it restored the current running phase instead of merely spawning.
                until(lambda:any(e['sim_tick']>prior_tick and e['actor']=='B-1' and
                    e['kind']=='http_request_ingress' and e['payload']['kind']=='me'
                    for e in engine.journal),timeout=10,message='restarted child must read current server phase')
                assert replacement.poll() is None
            else:
                assert processes.children['B-1'].pid==victim.pid
                assert processes.restarts['B-1']==3
                assert len(processes.failures)==1 and processes.failures[0]['slot']=='B-1'
                assert processes.failures[0]['restarts']==3
                for _ in range(3):processes.check()
                assert len(processes.pids['B-1'])==4
        assert len(set(replacement_pids))==3
        assert engine.robots['B-1'].ready and engine.robots['B-1'].started
        assert runtime.failure is None
        engine.enqueue('stop').result(timeout=3)
        until(lambda:all(processes.children[s].poll() is not None for s in peers),timeout=10,
              message='surviving children must observe finished and exit')
        assert all(processes.children[s].returncode==0 for s in peers)
        (tmp_path/'lifecycle_evidence.json').write_text(json.dumps({'pids':processes.pids,
            'restarts':processes.restarts,'failures':processes.failures,'match_id':match_id,
            'stored_m1_preserved':True,'other_five_completed':True},indent=2))
    finally:
        if processes is not None:processes.close()
        servers.close();runtime.close();gateway.close()
