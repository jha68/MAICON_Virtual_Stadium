"""Participant projection and credential logging checks over real TCP."""
import asyncio
import inspect
import json
import logging
import types
import httpx
import pytest
from maicon_sim.config.loader import LoadedConfig, load_scenario
from maicon_sim.core.engine import MatchEngine
from maicon_sim.core.types import RobotTruth
from maicon_sim.evaluation.realtime import LocalServers
from maicon_sim.sdk.http_port import HTTPPort
from maicon_sim.sensors.gateway import SensorGateway
from maicon_sim.server.app import create_apps
from maicon_sim.server.runtime import EngineRuntime


def assert_public(value, path=()):
    forbidden = {'true_pose','truth_pose','ammo','ammo_remaining','score','scores',
                 'inventory','ground_truth','expected_m1','face_id','source_face_id',
                 'segmentation_id','instance_id','object_id','box_id','robots'}
    if isinstance(value, dict):
        assert not forbidden.intersection(value), path
        if 'hp' in value:
            assert path and path[-1] == 'state', path
            assert set(value).issubset({'hp','hp_max','battery_pct','sequence','captured_tick','received_tick'})
        for key, item in value.items():
            assert_public(item, (*path, key))
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            assert_public(item, (*path, index))


def assert_http_sdk_has_no_truth(port):
    pending, visited = [port], set()
    privileged = (MatchEngine, RobotTruth, SensorGateway, LoadedConfig)
    while pending:
        value = pending.pop()
        if id(value) in visited:
            continue
        visited.add(id(value))
        assert not isinstance(value, privileged), type(value)
        if isinstance(value, (str, bytes, int, float, bool, type(None), type, types.ModuleType)) or inspect.isroutine(value):
            continue
        if isinstance(value, dict):
            pending.extend(value.values())
        elif isinstance(value, (list, tuple, set, frozenset)):
            pending.extend(value)
        elif hasattr(value, '__dict__'):
            pending.extend(vars(value).values())
        assert len(visited) < 10000, 'unexpected unbounded participant object graph'


@pytest.mark.integration
def test_ISO_001_007_socket_public_DTO_SDK_graph_and_redacted_logs(caplog, capsys):
    caplog.set_level(logging.INFO)
    config=load_scenario('examples/scenario_smoke_six.yaml')
    engine=MatchEngine(config)
    engine.request('enter_ready')
    gateway=SensorGateway(config)
    token='socket-log-test-administrator-secret'
    public,admin=create_apps(engine,gateway,admin_token=token)
    async def case(servers):
        async with HTTPPort(servers.public_url,'SIMB0001') as port, httpx.AsyncClient(trust_env=False) as raw:
            responses={
                'session':await port.session(), 'map_prior':await port.map_prior(),
                'calibration':await port.calibration(), 'me':await port.get_me(),
                'ready':await port.ready(),
            }
            auth={'Authorization':'Bearer '+token}
            result=await raw.post(servers.admin_url+'/admin/start',headers=auth)
            assert result.status_code==200
            responses['order']=await port.await_order(0)
            responses['target']=await port.await_target(0)
            responses['observations']=await port.latest_observations()
            responses['cmd_vel']=await port.command_velocity(0,0)
            responses['gimbal']=await port.command_gimbal(0,0)
            responses['fire']=await port.fire()
            responses['oled']=await port.oled(0,'public test')
            responses['m1']=await port.submit_m1({'base':'RED_SUPPLY_DEPOT'})
            responses['m3']=await port.submit_m3({'sectors':[{'sector':'CM','objects':[]}]})
            for code, status in (('bad code',422),('NOPE0001',401)):
                response=await raw.get(servers.public_url+'/api/report/me',params={'mission_code':code})
                assert response.status_code==status
                responses[code]=response.json()
            response=await raw.post(servers.public_url+'/api/report/detection',json={'mission_code':'SIMB0001','sectors':'invalid'})
            assert response.status_code==422
            responses['malformed']=response.json()
            response=await raw.get(servers.admin_url+'/admin/snapshot',headers={'Authorization':'Bearer invalid'})
            assert response.status_code==401
            assert (await raw.post(servers.admin_url+'/admin/finish',headers=auth)).status_code==200
            responses['m6']=await port.submit_m6(['R-1','R-2','R-3'])
            assert_public(responses)
            assert_public(port.cache.observations)
            assert_http_sdk_has_no_truth(port)
            assert all('mission_code' not in item for item in port.transcript)
    try:
        with EngineRuntime(engine,gateway), LocalServers(public,admin) as servers:
            assert all(server.config.access_log is False for server in servers.servers)
            asyncio.run(case(servers))
        captured=capsys.readouterr()
        logs=caplog.text+captured.out+captured.err+json.dumps(engine.journal)
        for agent in config.scenario['agents']:
            assert agent['mission_code'].lower() not in logs.lower()
        assert token not in logs
        assert '[REDACTED]' in caplog.text
    finally:
        gateway.close()


@pytest.mark.integration
def test_API_015_socket_cancel_100_cleans_waiters_and_tasks(caplog):
    engine=MatchEngine(load_scenario('examples/scenario_smoke_six.yaml'))
    engine.request('enter_ready')
    public,admin=create_apps(engine)
    async def case(servers):
        async with httpx.AsyncClient(base_url=servers.public_url,trust_env=False,timeout=130) as client:
            for _ in range(100):
                task=asyncio.create_task(client.get('/api/report/order',params={'mission_code':'SIMB0001','wait':120}))
                deadline=asyncio.get_running_loop().time()+1
                while public.state.service.waiters.active!=1:
                    assert asyncio.get_running_loop().time()<deadline
                    await asyncio.sleep(.001)
                task.cancel()
                await asyncio.gather(task,return_exceptions=True)
                while public.state.service.waiters.active:
                    assert asyncio.get_running_loop().time()<deadline
                    await asyncio.sleep(.001)
            deadline=asyncio.get_running_loop().time()+1
            while public.state.service.pending:
                assert asyncio.get_running_loop().time()<deadline
                await asyncio.sleep(.001)
            assert public.state.service.waiters.active==0
    with EngineRuntime(engine), LocalServers(public,admin) as servers:
        asyncio.run(case(servers))
    assert 'Exception in ASGI application' not in caplog.text
