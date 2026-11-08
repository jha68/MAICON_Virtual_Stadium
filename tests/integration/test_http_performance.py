"""A bounded actual-socket concurrency measurement, separate from correctness scores."""
import hashlib
import json
import os
import platform
import resource
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import httpx
import numpy as np
import pytest
import uvicorn
from maicon_sim import __version__
from maicon_sim.config.loader import canonical_hash, load_scenario
from maicon_sim.core.engine import MatchEngine
from maicon_sim.server.app import create_apps
from maicon_sim.server.runtime import EngineRuntime
from maicon_sim.evaluation.recorder import source_commit as implementation_commit


@pytest.mark.performance
@pytest.mark.integration
def test_PERF_004_socket_longpolls_me_reports_and_control():
    config=load_scenario('examples/scenario_smoke_six.yaml')
    config.rules['timing']['objective_publish_ms']=2500
    engine=MatchEngine(config);engine.request('enter_ready')
    for slot in engine.robots:engine.request('ready',slot)
    public,_=create_apps(engine)
    listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(128)
    port=listener.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(public,host='127.0.0.1',port=port,log_level='error',access_log=False))
    thread=threading.Thread(target=lambda:server.run(sockets=[listener]),daemon=True)
    timings=[];controls=[];statuses=[];max_waiters=0
    with EngineRuntime(engine) as runtime:
        thread.start()
        try:
            deadline=time.monotonic()+5
            while not server.started and time.monotonic()<deadline:time.sleep(.01)
            assert server.started
            with httpx.Client(base_url=f'http://127.0.0.1:{port}',timeout=130,trust_env=False) as client,ThreadPoolExecutor(max_workers=24) as pool:
                def request(method,path,**kwargs):
                    before=time.monotonic();response=client.request(method,path,**kwargs)
                    elapsed=time.monotonic()-before
                    timings.append({'path':path,'latency_s':elapsed,'longpoll':path.endswith(('/order','/target'))})
                    statuses.append(response.status_code)
                    return response
                waits=[pool.submit(request,'GET','/api/report/'+kind,params={'mission_code':f'SIM{camp}000{i}','wait':120})
                    for camp in ('B','R') for i in (1,2,3) for kind in ('order','target')]
                deadline=time.monotonic()+3
                while public.state.service.waiters.active<12 and time.monotonic()<deadline:time.sleep(.001)
                assert public.state.service.waiters.active==12
                max_waiters=12
                beginning=time.monotonic();next_me=beginning;next_control=beginning;started=False;revision=0
                jobs=[]
                while time.monotonic()-beginning<4:
                    now=time.monotonic()
                    max_waiters=max(max_waiters,public.state.service.waiters.active)
                    if not started and now-beginning>=1:
                        engine.enqueue('start').result(timeout=2);started=True
                    if now>=next_me:
                        for camp in ('B','R'):
                            for index in (1,2,3):
                                code=f'SIM{camp}000{index}'
                                jobs.append(pool.submit(request,'GET','/api/report/me',params={'mission_code':code}))
                                if started:
                                    jobs.append(pool.submit(request,'POST','/api/report/detection',json={'mission_code':code,
                                        'sectors':[{'sector':'CM','objects':[{'type':'TANK','count':revision}]}]}))
                        revision+=1;next_me+=1
                    if now>=next_control:
                        response=request('POST','/sim/robot/v1/cmd_vel',json={'mission_code':'SIMB0001','linear_x_mps':0,'angular_z_rps':0})
                        assert response.status_code==200
                        controls.append(time.monotonic());next_control+=.1
                    time.sleep(.001)
                assert all(job.result(timeout=3).status_code==200 for job in jobs)
                assert all(wait.result(timeout=3).json()['accepted'] for wait in waits)
                assert set(statuses)=={200}
                gaps=np.diff(controls)
                assert len(controls)>=35 and float(gaps.max())<.5
                ordinary=[item['latency_s'] for item in timings if not item['longpoll']]
                longpoll=[item['latency_s'] for item in timings if item['longpoll']]
                def quantiles(values):
                    return {f'p{q}_s':float(np.percentile(values,q)) for q in (50,95,99)}
                report={'benchmark':'PERF-004','profile':'SIM-PERF004-short-publication',
                    'description':'12 prepublication waits; six me clients at 1Hz, changed M3 after start, control ingress at 10Hz',
                    'phase_schedule':{'ready_wall_s':1,'running_wall_s':3,'objective_publish_match_ms':2500},
                    'backend':'2d','clock_mode':'realtime','camera_count':0,'seed':config.scenario['seed'],
                    'reference_source_commit':config.rules['source_commit'],
                    'source_commit':implementation_commit(),
                    'simulator_version':__version__,
                    'dependency_lock_hash':hashlib.sha256(Path('uv.lock').read_bytes()).hexdigest(),
                    'rule_profile_hash':canonical_hash(config.rules),
                    'source_rule_profile_hash':config.hashes['rule_profile_hash'],
                    'scenario_hash':config.hashes['scenario_hash'],
                    'environment':{'os':platform.platform(),'python':platform.python_version(),'logical_cpus':os.cpu_count(),
                        'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss},
                    'max_active_waiters':max_waiters,'ingress_queue_peak':engine.queue_peak,
                    'ordinary_requests':{'count':len(ordinary),**quantiles(ordinary)},
                    'longpoll_requests':{'count':len(longpoll),**quantiles(longpoll)},
                    'control_requests':len(controls),'control_max_interval_s':float(gaps.max()),
                    'server_http':public.state.service.http_metrics,
                    'timeout_count':0,'runtime':runtime.metrics,'passed':True}
                output=Path('artifacts/performance/http_concurrency.json');output.parent.mkdir(parents=True,exist_ok=True)
                output.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
                assert runtime.failure is None
        finally:
            public.state.service.close_threadsafe()
            server.should_exit=True;thread.join(timeout=5);listener.close()
