"""The public own-match bridge distinguishes resume from a fresh start."""
import asyncio
import time
import httpx
import pytest
from maicon_sim.config.loader import load_scenario
from maicon_sim.core.engine import MatchEngine
from maicon_sim.sensors.gateway import SensorGateway
from maicon_sim.server.app import create_apps
from maicon_sim.server.runtime import EngineRuntime


@pytest.mark.integration
@pytest.mark.contract
def test_TIME_009_HTTP_own_match_publishes_resume_after_pause():
    config=load_scenario('examples/scenario_smoke_six.yaml')
    engine=MatchEngine(config)
    gateway=SensorGateway(config)
    public,admin=create_apps(engine,gateway,admin_token='resume-contract-only')
    runtime=EngineRuntime(engine,gateway).start()
    async def exercise():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=public),base_url='http://test') as participant,\
                   httpx.AsyncClient(transport=httpx.ASGITransport(app=admin),base_url='http://test') as supervisor:
            auth={'Authorization':'Bearer resume-contract-only'}
            async def command(name):
                result=await supervisor.post('/admin/'+name,headers=auth)
                assert result.status_code==200,result.text
            async def published(expected):
                deadline=time.monotonic()+2
                while time.monotonic()<deadline:
                    result=await participant.get('/sim/robot/v1/match',params={'mission_code':'SIMB0001'})
                    if result.status_code==200 and result.json()['cmd']==expected:
                        return result.json()
                    await asyncio.sleep(.02)
                raise AssertionError(f'own-match wire did not publish {expected}')
            await command('ready-phase')
            await published('standby')
            assert (await participant.post('/api/report/ready',json={'mission_code':'SIMB0001'})).status_code==200
            await command('start')
            started=await published('start')
            await command('pause')
            paused=await published('pause')
            match_ticks=engine.match_elapsed_ticks
            await asyncio.sleep(.05)
            assert engine.match_elapsed_ticks==match_ticks
            await command('resume')
            resumed=await published('resume')
            assert started['captured_tick']<paused['captured_tick']<resumed['captured_tick']
            assert engine.match_elapsed_ticks>match_ticks
            me=await participant.get('/api/report/me',params={'mission_code':'SIMB0001'})
            assert me.json()['phase']=='running'
            await command('finish')
            await published('report')
            await command('shutdown')
            await published('stop')
            assert runtime.failure is None
    try:asyncio.run(exercise())
    finally:runtime.close();gateway.close()
