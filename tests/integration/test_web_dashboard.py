"""Operator auth, actual single-writer commands and participant information boundary."""
import asyncio
import json
from pathlib import Path

import httpx
import pytest

from maicon_sim.config.loader import load_scenario
from maicon_sim.core.engine import MatchEngine
from maicon_sim.server.app import create_apps
from maicon_sim.server.runtime import EngineRuntime
from maicon_sim.server.web import DashboardManager, create_dashboard
from maicon_sim.sensors.gateway import SensorGateway

PASSWORD = 'test-only-dashboard-password-123456'


class Processes:
    def __init__(self, *args):
        self.started = self.closed = False
    def start(self): self.started = True
    def check(self): pass
    def close(self): self.closed = True


@pytest.fixture(params=['smoke_six', 'reference_stadium'])
def harness(tmp_path, request):
    config = load_scenario(f'examples/scenario_{request.param}.yaml')
    engine = MatchEngine(config)
    gateway = SensorGateway(config)
    public, admin = create_apps(engine, gateway, admin_token='test-supervisor')
    manager = DashboardManager(public.state.service, tmp_path, process_factory=Processes)
    manager.public_url = 'http://127.0.0.1:8000'
    runtime = EngineRuntime(engine, gateway, on_tick=manager.on_tick).start()
    app = create_dashboard(manager, PASSWORD)
    yield engine, gateway, manager, app, public, tmp_path
    manager.close()
    runtime.close()
    gateway.close()


def test_operator_auth_assets_and_participant_boundary(harness):
    engine, gateway, manager, app, public, root = harness
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://dashboard') as c:
            for path in ('/', '/api/state', '/assets/app.js', '/api/camera/B-1.jpg',
                         '/api/textures/facility_RADAR.png', '/api/arena-floor.png'):
                assert (await c.get(path)).status_code == (303 if path == '/' else 401)
            assert (await c.get('/api/state', auth=('admin', 'wrong'))).status_code == 401
            c.auth = ('admin', PASSWORD)
            home = await c.get('/')
            assert home.status_code == 200 and '가상 경기장' in home.text
            assert 'change-password' not in home.text and 'password-form' not in home.text
            assert 'id="logout"' not in home.text
            assert "frame-ancestors 'none'" in home.headers['content-security-policy']
            assert home.headers['cache-control'] == 'no-store'
            for asset in ('app.js', 'arena-map.js', 'world.js', 'vendor/three.module.min.js', 'vendor/three.core.min.js'):
                assert (await c.get('/assets/' + asset)).status_code == 200
            assert (await c.get('/assets/%2e%2e/%2e%2e/cli.py')).status_code == 404
            state = (await c.get('/api/state')).json()
            assert len(state['robots']) == 6 and state['phase'] == 'waiting'
            assert set(state['facility_signals'].values()) == {'idle'}
            assert len(state['facility_signals']) == 6
            for asset in state['visual_assets'].values():
                texture = await c.get(asset['url'])
                assert texture.status_code == 200 and texture.content.startswith(b'\x89PNG')
            floor = await c.get(state['arena']['floor_url'])
            assert floor.status_code == 200 and floor.content.startswith(b'\x89PNG')
            assert (await c.get('/api/textures/unknown.png')).status_code == 404
            assert 'mission_code' not in json.dumps(state) and 'test-supervisor' not in json.dumps(state)
            assert (await c.get('/api/camera/B-1.jpg')).status_code == 503
            assert (await c.get('/api/camera/B-1.jpg?match_id=previous')).status_code == 409
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=public), base_url='http://participant') as c:
            assert (await c.get('/api/state', auth=('admin', PASSWORD))).status_code == 404
            assert (await c.get('/api/textures/facility_RADAR.png', auth=('admin', PASSWORD))).status_code == 404
    asyncio.run(run())


def test_operator_csrf_and_invalid_commands_do_not_start_match(harness):
    engine, gateway, manager, app, public, root = harness
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://dashboard', auth=('admin', PASSWORD)) as c:
            assert (await c.post('/api/command', json={'action': 'ready'})).status_code == 403
            h = {'X-Maicon-Operator': '1'}
            assert (await c.post('/api/command', headers={**h, 'Origin':'https://elsewhere.invalid'}, json={'action':'ready'})).status_code == 403
            for body in ({'action':'start'}, {'action':'shutdown'}, {'action':'ready','policy':'truth'}, {'action':'ready','path':'/secret'}):
                assert (await c.post('/api/command', headers=h, json=body)).status_code in (409,422)
            assert engine.phase == 'waiting'
    asyncio.run(run())


def test_operator_lifecycle_saves_result_and_clears_next_match(harness):
    engine, gateway, manager, app, public, root = harness
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://dashboard', auth=('admin', PASSWORD)) as c:
            async def command(action):
                return await c.post('/api/command', headers={'X-Maicon-Operator':'1','Origin':'http://dashboard'}, json={'action':action})
            assert (await command('ready')).status_code == 200
            old_children = manager.children
            assert old_children.started
            assert (await command('start')).status_code == 409
            for slot in engine.robots:
                await manager.service.submit('ready', slot)
            assert (await command('start')).status_code == 200
            assert (await command('reset')).status_code == 409
            assert (await command('pause')).status_code == 200
            assert engine.paused
            assert (await command('resume')).status_code == 200
            assert not engine.paused
            assert (await command('finish')).status_code == 200
            assert engine.phase == 'reporting'
            await manager.service.submit('stop')
            old_match = engine.match_id
            assert (await c.get('/api/result')).status_code == 200
            assert (await command('reset')).status_code == 200
            assert engine.match_id != old_match and engine.phase == 'waiting'
            assert not any(r.ready for r in engine.robots.values())
            assert old_children.closed and manager.children is None
            saved = json.loads((root/'private/results'/(old_match+'.json')).read_text())
            assert {v['total'] for v in saved['scores'].values()} == {20}
    asyncio.run(run())


def test_web_password_required():
    with pytest.raises(ValueError): create_dashboard(None, 'short')


def test_team_policies_manual_fire_reports_and_drone_permissions(harness):
    engine, gateway, manager, app, public, root = harness
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://dashboard', auth=('admin', PASSWORD)) as c:
            h = {'X-Maicon-Operator':'1','Origin':'http://dashboard'}
            assert (await c.post('/api/command', headers=h, json={'action':'ready', 'policy':'patrol'})).status_code == 422
            assert (await c.post('/api/command', headers=h, json={'action':'ready'})).status_code == 200
            snap = (await c.get('/api/state')).json()
            assert set(snap['participant_policies'].values()) == {'mission'}
            assert snap['m1_mode'] == 'direct_order' and snap['m6_mode'] == 'mock'
            assert (await c.get('/api/drone/B-1.jpg')).status_code == 409
            for slot in engine.robots: await manager.service.submit('ready', slot)
            assert (await c.post('/api/command',headers=h,json={'action':'start'})).status_code == 200
            body = {'match_id':engine.match_id,'command':'fire'}
            assert (await c.post('/api/control/B-1',json=body)).status_code == 403
            assert (await c.post('/api/control/B-1',headers={**h,'Origin':'https://unrelated.invalid'},json=body)).status_code == 403
            assert (await c.post('/api/control/B-1',headers=h,json={**body,'match_id':'old'})).status_code == 409
            assert (await c.post('/api/control/B-1',headers=h,json=body)).json()['message'] == 'fired'
            assert engine.robots['B-1'].ammo == 7
            assert (await c.post('/api/control/B-1',headers=h,json={**body,'command':'release'})).status_code == 200
            assert (await c.get('/api/participant/B-1')).json()['match_id'] == engine.match_id
            await manager.service.submit('m1','B-1',{'base':'RED_MAINTENANCE'})
            state = (await c.get('/api/state')).json()
            assert state['reports']['B-1']['m1']['base'] == 'RED_MAINTENANCE'
            assert state['manual_interventions'] == 1 and state['m6_mode'] == 'mock'
            await manager.service.submit('stop')
            assert (await c.get('/api/result')).json()['operator_interventions'] == 1
    asyncio.run(run())


def test_operator_artwork_changes_when_supervisor_reconfigures(harness):
    engine, gateway, manager, app, public, root = harness
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://dashboard', auth=('admin', PASSWORD)) as c:
            original = engine.config.scenario['scenario_id']
            target = 'smoke_six' if original == 'reference_stadium' else 'reference_stadium'
            first_texture = (await c.get('/api/textures/facility_RADAR.png')).content
            first_floor = (await c.get('/api/arena-floor.png')).content
            await manager.service.submit('stop')
            await manager.service.submit('configure', payload={'config': load_scenario(f'examples/scenario_{target}.yaml')})
            state = (await c.get('/api/state')).json()
            assert state['scenario_id'] == target
            assert len(state['boxes']) == (20 if target == 'reference_stadium' else 7)
            assert (await c.get('/api/textures/facility_RADAR.png')).content != first_texture
            assert (await c.get('/api/arena-floor.png')).content != first_floor
    asyncio.run(run())


def test_operator_can_cancel_preparation(harness):
    engine, gateway, manager, app, public, root = harness
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://dashboard', auth=('admin', PASSWORD)) as c:
            h = {'X-Maicon-Operator': '1'}
            assert (await c.post('/api/command', headers=h, json={'action':'ready'})).status_code == 200
            children = manager.children
            assert (await c.post('/api/command', headers=h, json={'action':'reset'})).status_code == 200
            assert engine.phase == 'waiting' and children.closed
    asyncio.run(run())


def test_serve_sigterm_exits_cleanly(tmp_path):
    import subprocess
    import sys
    import time
    log = tmp_path / 'serve.log'
    with log.open('w') as output:
        child = subprocess.Popen([sys.executable, '-m', 'maicon_sim', 'serve', '--example', 'smoke_six',
                                  '--backend', '2d', '--public-port', '0', '--admin-port', '0',
                                  '--out', str(tmp_path/'run')], stdout=output, stderr=output)
        try:
            deadline = time.monotonic() + 15
            while 'Realtime APIs active' not in log.read_text() and time.monotonic() < deadline:
                assert child.poll() is None, log.read_text()
                time.sleep(.05)
            assert 'Realtime APIs active' in log.read_text(), log.read_text()
            child.terminate()
            assert child.wait(timeout=15) == 0, log.read_text()
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=10)
