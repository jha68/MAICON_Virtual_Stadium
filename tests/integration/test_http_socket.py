"""Actual socket transport and six independent participant interpreters."""
import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
import pytest
import uvicorn
from maicon_sim.config.loader import load_scenario
from maicon_sim.core.engine import MatchEngine
from maicon_sim.server.app import create_apps
from maicon_sim.server.runtime import EngineRuntime

CHILD = r'''
import json,os,time,urllib.request,urllib.parse
base=os.environ['MAICON_SIM_PUBLIC_URL'];code=os.environ['MAICON_SIM_MISSION_CODE']
def request(path,body=None,**params):
 if body is None:
  params['mission_code']=code
  req=urllib.request.Request(base+path+'?'+urllib.parse.urlencode(params))
 else:
  body=dict(body,mission_code=code)
  req=urllib.request.Request(base+path,data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=130) as result:return json.load(result)
me=request('/api/report/me');request('/api/report/ready',{})
order=request('/api/report/order',wait=120)
assert order['accepted']
print(json.dumps({'started':me['slot'],'camp':me['camp']}),flush=True)
submitted=False
while True:
 me=request('/api/report/me')
 if me['phase']=='running': request('/sim/robot/v1/cmd_vel',{'linear_x_mps':0,'angular_z_rps':0})
 if me['phase']=='reporting' and not submitted:
  enemy='R' if me['camp']=='BLUE' else 'B'
  result=request('/api/report/situation',{'ranking':[enemy+'-'+str(i) for i in (1,2,3)]})
  assert result['accepted'];submitted=True
 if me['phase']=='finished':break
 time.sleep(.05)
print(json.dumps({'slot':me['slot'],'finished':True,'submitted':submitted}),flush=True)
'''


@pytest.mark.integration
@pytest.mark.e2e
def test_E2E_001_six_processes_actual_HTTP_and_last_M6_ACK(tmp_path):
    engine=MatchEngine(load_scenario('examples/scenario_smoke_six.yaml'))
    engine.request('enter_ready')
    public,_=create_apps(engine,admin_token='unshared-test-admin')
    listener=socket.socket()
    listener.bind(('127.0.0.1',0));listener.listen(128)
    port=listener.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(public,host='127.0.0.1',port=port,log_level='error',access_log=False))
    thread=threading.Thread(target=lambda:server.run(sockets=[listener]),daemon=True)
    children=[]
    with EngineRuntime(engine) as runtime:
        thread.start()
        try:
            deadline=time.monotonic()+5
            while not server.started and time.monotonic()<deadline:time.sleep(.01)
            assert server.started
            for camp in ('B','R'):
                for index in (1,2,3):
                    # The child's working directory and environment contain no truth path or admin token.
                    output=tmp_path/f'{camp}-{index}';output.mkdir()
                    env={'PATH':os.environ['PATH'],'MAICON_SIM_MISSION_CODE':f'SIM{camp}000{index}',
                         'MAICON_SIM_PUBLIC_URL':f'http://127.0.0.1:{port}','PYTHONNOUSERSITE':'1'}
                    children.append(subprocess.Popen([sys.executable,'-u','-c',CHILD],cwd=output,
                        env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True))
            deadline=time.monotonic()+10
            while not all(robot.ready for robot in engine.robots.values()) and time.monotonic()<deadline:
                time.sleep(.01)
            assert all(robot.ready for robot in engine.robots.values())
            engine.enqueue('start').result(timeout=2)
            started=[json.loads(child.stdout.readline()) for child in children]
            assert {item['started'] for item in started}==set(engine.robots)
            time.sleep(.3)
            engine.enqueue('finish').result(timeout=2)
            results=[]
            for child in children:
                stdout,stderr=child.communicate(timeout=5)
                assert child.returncode==0,stderr
                results.append(json.loads(stdout.strip()))
            assert all(item['finished'] and item['submitted'] for item in results)
            assert engine.phase=='finished' and len(engine.submitted_m6)==6
            assert runtime.failure is None
        finally:
            for child in children:
                if child.poll() is None:child.terminate()
            for child in children:
                try:child.wait(timeout=2)
                except subprocess.TimeoutExpired:child.kill();child.wait()
            server.should_exit=True;thread.join(timeout=5);listener.close()


@pytest.mark.slow
@pytest.mark.integration
def test_API_014_socket_longpoll_uses_120_wall_seconds():
    import httpx
    engine=MatchEngine(load_scenario('examples/scenario_smoke_six.yaml'))
    engine.request('enter_ready')
    public,_=create_apps(engine)
    listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(128)
    port=listener.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(public,host='127.0.0.1',port=port,log_level='error',access_log=False))
    thread=threading.Thread(target=lambda:server.run(sockets=[listener]),daemon=True)
    with EngineRuntime(engine) as runtime:
        thread.start()
        try:
            deadline=time.monotonic()+5
            while not server.started and time.monotonic()<deadline:time.sleep(.01)
            assert server.started
            before=time.monotonic()
            response=httpx.get(f'http://127.0.0.1:{port}/api/report/order',
                params={'mission_code':'SIMB0001','wait':120},timeout=130,trust_env=False)
            elapsed=time.monotonic()-before
            assert response.status_code==200 and response.json()['accepted'] is False
            assert 120<=elapsed<123
            assert public.state.service.waiters.active==0
            assert runtime.failure is None
        finally:
            server.should_exit=True;thread.join(timeout=5);listener.close()


@pytest.mark.integration
def test_API_011_socket_latest_snapshot_repairs_late_commit():
    import asyncio
    from maicon_sim.sdk.http_port import HTTPPort
    from maicon_sim.sdk.report_worker import ReportWorker
    config=load_scenario('examples/scenario_smoke_six.yaml')
    config.scenario['events'].append({'event_id':'network-late-A','clock':'sim','at_ms':0,
        'kind':'http_delay','parameters':{'slot':'B-1','path':'/api/report/detection',
        'duration_ms':200,'stage':'before_ingress','match_occurrence':1,'drop_response_after_commit':False}})
    engine=MatchEngine(config);engine.request('enter_ready');engine.request('ready','B-1');engine.request('start')
    public,_=create_apps(engine)
    listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(128)
    port=listener.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(public,host='127.0.0.1',port=port,log_level='error',access_log=False))
    thread=threading.Thread(target=lambda:server.run(sockets=[listener]),daemon=True)
    def report(count):return {'sectors':[{'sector':'R-S1','objects':[{'type':'TANK','count':count}]}]}
    async def case():
        async with HTTPPort(f'http://127.0.0.1:{port}','SIMB0001') as participant:
            worker=ReportWorker(participant,'m3',timeout_s=.03)
            worker.update(report(1));assert await worker.flush_once() is None
            assert worker.errors[-1]['kind']=='TimeoutError'
            worker.timeout_s=1
            worker.update(report(2));assert (await worker.flush_once())['accepted']
            assert engine.reports['B-1']['m3']['sectors'][0]['objects'][0]['count']==2
            await asyncio.sleep(.25)
            assert engine.reports['B-1']['m3']['sectors'][0]['objects'][0]['count']==1
            assert (await worker.flush_once())['accepted']
            assert engine.reports['B-1']['m3']['sectors'][0]['objects'][0]['count']==2
            await worker.close()
    with EngineRuntime(engine) as runtime:
        thread.start()
        try:
            deadline=time.monotonic()+5
            while not server.started and time.monotonic()<deadline:time.sleep(.01)
            assert server.started
            asyncio.run(case())
            assert runtime.failure is None
        finally:
            server.should_exit=True;thread.join(timeout=5);listener.close()


@pytest.mark.integration
def test_API_012_018_twelve_socket_waits_and_six_concurrent_reports():
    from concurrent.futures import ThreadPoolExecutor
    import httpx
    config=load_scenario('examples/scenario_smoke_six.yaml')
    config.rules['timing']['objective_publish_ms']=500  # Explicit short scheduling fixture.
    engine=MatchEngine(config);engine.request('enter_ready')
    for slot in engine.robots:engine.request('ready',slot)
    public,_=create_apps(engine)
    listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(128)
    port=listener.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(public,host='127.0.0.1',port=port,log_level='error',access_log=False))
    thread=threading.Thread(target=lambda:server.run(sockets=[listener]),daemon=True)
    with EngineRuntime(engine) as runtime:
        thread.start()
        try:
            deadline=time.monotonic()+5
            while not server.started and time.monotonic()<deadline:time.sleep(.01)
            assert server.started
            with httpx.Client(base_url=f'http://127.0.0.1:{port}',timeout=130,trust_env=False) as client,ThreadPoolExecutor(max_workers=16) as pool:
                waits=[pool.submit(client.get,'/api/report/'+kind,params={'mission_code':f'SIM{camp}000{i}','wait':120})
                    for camp in ('B','R') for i in (1,2,3) for kind in ('order','target')]
                deadline=time.monotonic()+3
                while public.state.service.waiters.active<12 and time.monotonic()<deadline:time.sleep(.01)
                assert public.state.service.waiters.active==12
                tick=engine.sim_tick
                response=client.post('/sim/robot/v1/cmd_vel',json={'mission_code':'SIMB0001','linear_x_mps':0,'angular_z_rps':0})
                assert response.status_code==200 and engine.sim_tick>tick
                engine.enqueue('start').result(timeout=2)
                reports=[pool.submit(client.post,'/api/report/detection',json={'mission_code':f'SIM{camp}000{i}',
                    'sectors':[{'sector':'CM','objects':[]}]}) for camp in ('B','R') for i in (1,2,3)]
                assert all(f.result(timeout=3).status_code==200 for f in reports)
                assert all(f.result(timeout=3).json()['accepted'] for f in waits)
                inputs=[e for e in engine.journal if e['kind']=='http_request_ingress' and e['payload']['kind']=='m3']
                assert len(inputs)==6 and len({e['actor'] for e in inputs})==6
                seq=[e['payload']['ingress_seq'] for e in inputs]
                assert seq==sorted(seq) and len(set(seq))==6
                assert public.state.service.waiters.active==0
                assert runtime.failure is None
        finally:
            server.should_exit=True;thread.join(timeout=5);listener.close()


@pytest.mark.integration
def test_API_010_socket_response_loss_keeps_committed_report():
    import asyncio
    from maicon_sim.sdk.http_port import HTTPPort
    config=load_scenario('examples/scenario_smoke_six.yaml')
    config.scenario['events'].append({'event_id':'lost-ACK','clock':'sim','at_ms':0,
        'kind':'http_delay','parameters':{'slot':'B-1','path':'/api/report/interpretation',
        'duration_ms':0,'stage':'after_commit','match_occurrence':1,'drop_response_after_commit':True}})
    engine=MatchEngine(config);engine.request('enter_ready');engine.request('ready','B-1');engine.request('start')
    public,_=create_apps(engine)
    listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(128)
    port=listener.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(public,host='127.0.0.1',port=port,log_level='error',access_log=False))
    thread=threading.Thread(target=lambda:server.run(sockets=[listener]),daemon=True)
    async def case():
        async with HTTPPort(f'http://127.0.0.1:{port}','SIMB0001') as participant:
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(participant.submit_m1({'target':'RED_RADAR'}),.05)
            assert engine.reports['B-1']['m1']['target']=='RED_RADAR'
            response=await participant.submit_m1({'target':'RED_RADAR'})
            assert response['accepted']
            assert engine.reports['B-1']['m1']['target']=='RED_RADAR'
    with EngineRuntime(engine) as runtime:
        thread.start()
        try:
            deadline=time.monotonic()+5
            while not server.started and time.monotonic()<deadline:time.sleep(.01)
            assert server.started
            asyncio.run(case())
            assert runtime.failure is None
        finally:
            server.should_exit=True;thread.join(timeout=5);listener.close()
