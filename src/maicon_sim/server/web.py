"""Authenticated operator surface, separate from participant and admin wire APIs."""
from __future__ import annotations

import asyncio
from copy import deepcopy
from functools import lru_cache
import hashlib
import hmac
import io
import json
import os
import threading
from importlib.resources import files
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response

from maicon_sim.core.types import SLOTS
from maicon_sim.sensors.gateway import SensorUnavailable

POLICIES = ('idle', 'patrol', 'baseline', 'blocker', 'capture_runner')


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
        self.policies = {}

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

    async def command(self, action, policy='idle', policies=None):
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
                    agent['policy'] = (policies or {}).get(agent['slot'], policy)
                self.policies = {a['slot']: a['policy'] for a in config.scenario['agents']}
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
    app = FastAPI(title='MAICON operator', docs_url=None, redoc_url=None, openapi_url=None)
    from .web_auth import install_auth
    install_auth(app, password)
    web_root = Path(str(files('maicon_sim') / 'resources/web'))
    @lru_cache(maxsize=32)
    def texture_bytes(generator, label, path, digest):
        if generator == 'import':
            data = Path(path).read_bytes()
            if hashlib.sha256(data).hexdigest() != digest:
                raise HTTPException(503, '경기장 이미지 검증에 실패했습니다.')
            from PIL import Image
            picture = Image.open(io.BytesIO(data)).convert('RGB')
        else:
            from maicon_sim.backends.bullet.asset_builder import synthetic_image
            picture = synthetic_image(label)
        output = io.BytesIO()
        picture.save(output, format='PNG')
        return output.getvalue()

    @lru_cache(maxsize=1)
    def floor_bytes(arena_json):
        from maicon_sim.backends.arena_art import arena_floor
        output = io.BytesIO()
        arena_floor(json.loads(arena_json)).save(output, format='PNG')
        return output.getvalue()

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
        config = manager.service.engine.config
        # This is evaluator truth behind operator auth, never a participant DTO.
        snap['participant_policies'] = dict(manager.policies)
        snap['llm_mode'] = 'mock' if os.environ.get('MAICON_LLM_PROVIDER', 'fixture') == 'fixture' else 'external'
        snap['build_revision'] = os.environ.get('MAICON_BUILD_REVISION', 'local')
        snap['profile_id'] = config.rules['profile_id']
        snap['scenario_hash'] = config.hashes['scenario_hash']
        snap['arena'] = {key: deepcopy(config.arena[key]) for key in ('arena_id', 'bounds', 'sectors', 'bases')}
        snap['arena']['floor_url'] = '/api/arena-floor.png'
        from maicon_sim.backends.arena_art import base_panels
        snap['arena']['base_panels'] = base_panels(config.arena, config.assets)
        snap['scenario_id'] = config.scenario['scenario_id']
        snap['visual_assets'] = {a['asset_id']: {'kind': a['kind'], 'label': a['label'],
                                               'url': '/api/textures/' + a['asset_id'] + '.png'}
                                 for a in config.assets['assets']}
        snap['render_geometry'] = {key: config.sensors['geometry'][key] for key in
                                   ('facility_receiver_z_m', 'facility_receiver_radius_m',
                                    'facility_receiver_offset_m', 'wall_thickness_m')}
        snap['timing'] = deepcopy(manager.service.engine.config.rules['timing'])
        snap['capabilities'] = dict(manager.service.gateway.capabilities)
        runtime = getattr(manager.service.engine, '_runtime', None)
        snap['performance'] = {'max_lag_s': runtime.max_lag_s if runtime else 0,
                               'frame_drops': manager.service.gateway.dropped}
        return snap

    @app.get('/api/arena-floor.png')
    def floor_texture():
        arena = manager.service.engine.config.arena
        return Response(floor_bytes(json.dumps(arena, sort_keys=True)), media_type='image/png')

    @app.get('/api/textures/{asset_id}.png')
    def face_texture(asset_id: str):
        config = manager.service.engine.config
        asset = next((a for a in config.assets['assets'] if a['asset_id'] == asset_id), None)
        if asset is None:
            raise HTTPException(404, '알 수 없는 경기장 이미지입니다.')
        root = (config.path.parent / config.scenario['assets_file']).parent
        path = str(root / asset['path']) if asset['path'] else None
        return Response(texture_bytes(asset['generator'], asset['label'], path, asset['sha256']), media_type='image/png')

    @app.post('/api/command')
    async def command(request: Request):
        # The custom header prevents cross-site form submissions. No CORS grants.
        if request.headers.get('x-maicon-operator') != '1':
            raise HTTPException(403, '운영자 요청 헤더가 필요합니다.')
        origin = request.headers.get('origin')
        if origin and urlsplit(origin).netloc.lower() != request.headers.get('host', '').lower():
            raise HTTPException(403, '다른 사이트의 조작 요청은 허용하지 않습니다.')
        body = await manager.service.body(request, {'action', 'policy', 'policies'})
        if body.get('policy', 'idle') not in POLICIES:
            raise HTTPException(422, '알 수 없는 정책입니다.')
        policies = body.get('policies', {})
        if not isinstance(policies, dict) or any(s not in SLOTS or p not in POLICIES for s,p in policies.items()):
            raise HTTPException(422, '팀별 정책을 확인하세요.')
        if not isinstance(body.get('action'), str):
            raise HTTPException(422, '조작을 지정하세요.')
        return await manager.command(body['action'], body.get('policy', 'idle'), policies)

    @app.post('/api/control/{slot}')
    async def control(slot: str, request: Request):
        if request.headers.get('x-maicon-operator') != '1':
            raise HTTPException(403)
        origin = request.headers.get('origin')
        if origin and urlsplit(origin).netloc.lower() != request.headers.get('host', '').lower():
            raise HTTPException(403)
        if slot not in SLOTS:
            raise HTTPException(404)
        body = await manager.service.body(request, {'command', 'parameters', 'match_id'})
        if body.get('match_id') != manager.service.engine.match_id:
            raise HTTPException(409, '경기가 변경됐습니다.')
        return await manager.service.submit('operator_control', slot,
                    {'command':body.get('command'), 'parameters':body.get('parameters', {})})

    @app.get('/api/participant/{slot}')
    async def participant_status(slot: str):
        if slot not in SLOTS:
            raise HTTPException(404)
        match = manager.service.engine.match_id
        path = manager.root / 'episodes' / match / 'public' / slot / 'participant.jsonl'
        def latest():
            try:
                with path.open('rb') as stream:
                    stream.seek(0,2)
                    stream.seek(max(0,stream.tell()-65536))
                    lines = stream.read().splitlines()
                for line in reversed(lines):
                    try:
                        value = json.loads(line)
                    except ValueError:
                        continue
                    if value.get('match_id') == match:
                        return value
            except OSError:
                pass
            return {'slot':slot, 'match_id':match, 'diagnostics':{}}
        return await asyncio.to_thread(latest)

    @app.get('/api/drone/{slot}.jpg')
    async def drone(slot: str):
        if slot not in SLOTS:
            raise HTTPException(404)
        try:
            blob, meta = await asyncio.to_thread(manager.service.gateway.get_drone, slot)
        except SensorUnavailable as exc:
            raise HTTPException(exc.status, exc.detail) from None
        return Response(blob, media_type='image/jpeg', headers=meta)

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
