"""Authenticated operator surface, separate from participant and admin wire APIs."""
from __future__ import annotations

import asyncio
from copy import deepcopy
import hmac
import threading
from importlib.resources import files
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from maicon_sim.core.types import SLOTS
from maicon_sim.sensors.gateway import SensorUnavailable


class DashboardManager:
    def __init__(self, service, root, process_factory=None):
        self.service, self.root = service, Path(root)
        self.public_url = None
        self.children = None
        self.operation = asyncio.Lock()
        self.closing = False
        self.completed = None
        self.saved = set()
        self.process_factory = process_factory
        self.save_lock = threading.Lock()

    def on_tick(self, engine):
        if engine.phase == 'finished' and (self.completed is None or self.completed[0] != engine.match_id):
            self.completed = (engine.match_id, engine.result())

    def maintain(self):
        if self.children and not self.closing:
            self.children.check()
        if self.completed and self.completed[0] not in self.saved:
            self.save_result(*self.completed)

    def save_result(self, match_id, result):
        from maicon_sim.evaluation.metrics import write_json
        with self.save_lock:
            write_json(self.root / 'private/results' / (match_id + '.json'), result)
            self.saved.add(match_id)

    def close(self):
        self.closing = True
        try:
            if self.children:
                self.children.close()
                self.children = None
        finally:
            self.closing = False

    async def command(self, action, policy='idle'):
        engine, service = self.service.engine, self.service
        async with self.operation:
            snap = await service.submit('snapshot')
            phase = snap['phase']
            if action == 'ready':
                if phase != 'waiting':
                    raise HTTPException(409, '세팅 단계에서 준비를 시작하세요.')
                await asyncio.to_thread(self.close)
                await service.submit('enter_ready')
                config = deepcopy(engine.config)
                for agent in config.scenario['agents']:
                    agent['policy'] = policy
                factory = self.process_factory
                if factory is None:
                    from maicon_sim.evaluation.realtime import ParticipantProcesses
                    factory = ParticipantProcesses
                children = factory(config, self.public_url, self.root / 'episodes' / snap['match_id'], engine)
                try:
                    await asyncio.to_thread(children.start)
                except Exception:
                    await asyncio.to_thread(children.close)
                    await service.submit('reset')
                    raise HTTPException(503, '참가팀 프로세스를 시작하지 못했습니다.') from None
                self.children = children
            elif action == 'start':
                if phase != 'ready' or not all(r['ready'] for r in snap['robots'].values()):
                    raise HTTPException(409, '여섯 팀의 준비 완료를 기다려주세요.')
                await service.submit('start')
            elif action in ('pause', 'resume', 'finish'):
                await service.submit(action)
            elif action == 'reset':
                if phase not in ('waiting', 'ready', 'finished'):
                    raise HTTPException(409, '진행 중인 경기를 종료한 뒤 초기화하세요.')
                if phase == 'finished':
                    self.save_result(snap['match_id'], await service.submit('result'))
                await asyncio.to_thread(self.close)
                await service.submit('reset')
            else:
                raise HTTPException(422, '지원하지 않는 조작입니다.')
            return {'accepted': True, 'action': action}


def create_dashboard(manager, password):
    if len(password) < 24:
        raise ValueError('Dashboard password is too short')
    basic = HTTPBasic()

    def authenticate(credentials: HTTPBasicCredentials = Depends(basic)):
        valid_user = hmac.compare_digest(credentials.username.encode(), b'admin')
        valid_password = hmac.compare_digest(credentials.password.encode(), password.encode())
        if not (valid_user and valid_password):
            raise HTTPException(401, '로그인이 필요합니다.', headers={'WWW-Authenticate': 'Basic realm="MAICON operator"'})

    app = FastAPI(title='MAICON operator', docs_url=None, redoc_url=None, openapi_url=None,
                  dependencies=[Depends(authenticate)])
    web_root = Path(str(files('maicon_sim') / 'resources/web'))

    @app.middleware('http')
    async def headers(request, call_next):
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        return response

    @app.get('/')
    async def index():
        return FileResponse(web_root / 'index.html')

    @app.get('/assets/{name:path}')
    async def asset(name: str):
        target = (web_root / name).resolve()
        if not target.is_relative_to(web_root.resolve()) or not target.is_file() or name == 'index.html':
            raise HTTPException(404)
        return FileResponse(target)

    @app.get('/api/state')
    async def state():
        snap = await manager.service.submit('snapshot')
        # This is evaluator truth behind operator auth, never a participant DTO.
        snap.pop('reports', None)
        snap['arena'] = {key: deepcopy(manager.service.engine.config.arena[key]) for key in ('bounds', 'sectors', 'bases')}
        snap['timing'] = deepcopy(manager.service.engine.config.rules['timing'])
        snap['capabilities'] = dict(manager.service.gateway.capabilities)
        runtime = getattr(manager.service.engine, '_runtime', None)
        snap['performance'] = {'max_lag_s': runtime.max_lag_s if runtime else 0,
                               'frame_drops': manager.service.gateway.dropped}
        return snap

    @app.post('/api/command')
    async def command(request: Request):
        # The custom header prevents cross-site form submissions. No CORS grants.
        if request.headers.get('x-maicon-operator') != '1':
            raise HTTPException(403, '운영자 요청 헤더가 필요합니다.')
        origin = request.headers.get('origin')
        if origin and urlsplit(origin).netloc.lower() != request.headers.get('host', '').lower():
            raise HTTPException(403, '다른 사이트의 조작 요청은 허용하지 않습니다.')
        body = await manager.service.body(request, {'action', 'policy'})
        if body.get('policy', 'idle') not in ('idle', 'patrol', 'baseline', 'blocker', 'capture_runner'):
            raise HTTPException(422, '알 수 없는 정책입니다.')
        if not isinstance(body.get('action'), str):
            raise HTTPException(422, '조작을 지정하세요.')
        return await manager.command(body['action'], body.get('policy', 'idle'))

    @app.get('/api/camera/{slot}.jpg')
    async def camera(slot: str, match_id: str | None = None):
        if slot not in SLOTS:
            raise HTTPException(404)
        current = manager.service.engine.match_id
        if match_id is not None and match_id != current:
            raise HTTPException(409, '경기가 변경됐습니다.')
        if manager.service.gateway._session != current:
            raise HTTPException(503, '새 경기의 프레임을 기다립니다.')
        try:
            blob, meta = await asyncio.to_thread(manager.service.gateway.get, slot, 'camera')
        except SensorUnavailable as exc:
            raise HTTPException(exc.status, exc.detail) from None
        if manager.service.engine.match_id != current:
            raise HTTPException(409, '경기가 변경됐습니다.')
        meta['X-Maicon-Match-ID'] = current
        return Response(blob, media_type='image/jpeg', headers=meta)

    @app.get('/api/result')
    async def result():
        value = await manager.service.submit('result')
        return value

    from maicon_sim.core.rules import EngineError
    from fastapi.responses import JSONResponse
    @app.exception_handler(EngineError)
    async def engine_error(request, error):
        return JSONResponse({'detail': str(error)}, status_code=error.status)

    return app
