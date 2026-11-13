"""Bounded HTTPS pull relay for this operator app; no general TCP forwarding.

Oracle retains TLS and an authenticated fallback. A Codex worker fetches jobs
over ordinary HTTPS and can forward them only to its fixed loopback dashboard.
"""
import argparse
import asyncio
import base64
import hmac
import json
from pathlib import Path
import re
import secrets
import time
import zlib

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response

PREFIX = '/_codex_bridge'
REQUEST_LIMIT = 1024 * 1024
RESPONSE_LIMIT = 8 * 1024 * 1024
ENVELOPE_LIMIT = 4 * 1024 * 1024
LEASE_SECONDS = 20
HOP = {'connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization',
       'te', 'trailer', 'transfer-encoding', 'upgrade', 'content-length', 'content-encoding',
       'x-maicon-compute'}


def clean_headers(items):
    items = list(items)
    blocked = HOP | {v.strip().lower() for k, value in items if k.lower() == 'connection' for v in value.split(',')}
    result = []
    for name, value in items:
        if name.lower() in blocked:
            continue
        if not re.fullmatch(r'[A-Za-z0-9!#$%&\'*+.^_`|~-]{1,128}', name) or '\r' in value or '\n' in value or len(value) > 8192:
            raise HTTPException(422, 'Invalid relay header')
        result.append((name, value))
    if len(result) > 100:
        raise HTTPException(422, 'Too many relay headers')
    return result


def target_url(origin, path, query):
    if not path.startswith('/') or any(c in path + query for c in '\r\n#') or len(path) + len(query) > 8192:
        raise ValueError('Invalid operator request path')
    return origin.rstrip('/') + path + ('?' + query if query else '')


async def read_body(request, limit):
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > limit:
            raise HTTPException(413, 'Relay payload too large')
    return bytes(body)


def decode_response(payload):
    status = payload.get('status')
    if type(status) is not int or not 200 <= status <= 599:
        raise ValueError('Invalid response status')
    compressed = base64.b64decode(payload['body'], validate=True)
    decoder = zlib.decompressobj()
    body = decoder.decompress(compressed, RESPONSE_LIMIT + 1)
    if len(body) > RESPONSE_LIMIT or not decoder.eof or decoder.unused_data:
        raise ValueError('Invalid or oversized response body')
    headers = clean_headers(payload.get('headers', []))
    return status, headers, body


def operator_response(status, headers, body, origin):
    response = Response(body, status_code=status)
    response.raw_headers = [(k.lower().encode('latin1'), v.encode('latin1')) for k, v in clean_headers(headers)]
    response.headers['Content-Length'] = str(len(body))
    response.headers['X-Maicon-Compute'] = origin
    return response


class Gateway:
    def __init__(self, token, session_id, domain, password, fallback='http://127.0.0.1:8080', *, client=None):
        if len(token) < 32 or len(password) < 10 or not re.fullmatch(r'[a-f0-9]{32}', session_id):
            raise ValueError('Invalid relay credentials')
        if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9.-]*\.[a-zA-Z]{2,}', domain):
            raise ValueError('Invalid operator domain')
        self.token, self.session_id, self.domain, self.password = token, session_id, domain, password
        self.fallback = fallback
        self.client = client or httpx.AsyncClient(trust_env=False, timeout=40, follow_redirects=False)
        self.jobs = asyncio.Queue(maxsize=64)
        self.pending = {}
        self.route_lock = asyncio.Lock()
        self.last_seen = -1e10
        self.activated = False

    def authenticate(self, request):
        supplied = request.headers.get('authorization', '').encode()
        if not hmac.compare_digest(supplied, ('Bearer ' + self.token).encode()):
            raise HTTPException(403, 'Relay authentication required')

    def active(self):
        if time.monotonic() - self.last_seen >= LEASE_SECONDS:
            self.activated = False
        return self.activated

    async def heartbeat(self):
        async with self.route_lock:
            self.active()
            if not self.activated:
                try:
                    response = await self.client.get(self.fallback + '/api/state',
                        headers={'Host': self.domain}, auth=('admin', self.password), timeout=5)
                    response.raise_for_status()
                    self.activated = response.json().get('phase') in ('waiting', 'finished')
                except (httpx.HTTPError, ValueError):
                    self.activated = False
            self.last_seen = time.monotonic()
        return {'compute': 'codex-cloud' if self.active() else 'oracle-backup'}

    async def forward(self, request, body):
        headers = clean_headers(request.headers.items())
        headers = [(k, v) for k, v in headers if k.lower() not in
                   ('host', 'cookie', 'x-forwarded-for', 'x-forwarded-proto', 'x-forwarded-host', 'forwarded')]
        headers.extend([('Host', self.domain), ('X-Forwarded-Proto', 'https'),
                        ('Cookie', request.headers.get('cookie', '')),
                        ('X-Forwarded-For', request.client.host if request.client else 'unknown')])
        path = request.scope['raw_path'].decode('ascii')
        query = request.scope['query_string'].decode('ascii')
        if not self.active():
            response = await self.client.request(request.method, target_url(self.fallback, path, query),
                                                 headers=headers, content=body)
            return operator_response(response.status_code, response.headers.multi_items(), response.content, 'oracle-backup')
        if len(self.pending) >= 64:
            raise HTTPException(503, 'Codex relay is busy')
        job_id = secrets.token_hex(16)
        future = asyncio.get_running_loop().create_future()
        job = {'id': job_id, 'method': request.method, 'path': path, 'query': query,
               'headers': headers, 'body': base64.b64encode(body).decode()}
        self.pending[job_id] = future
        try:
            self.jobs.put_nowait(job)
            status, result_headers, result_body = await asyncio.wait_for(asyncio.shield(future), 30)
            return operator_response(status, result_headers, result_body, 'codex-cloud')
        except asyncio.TimeoutError:
            raise HTTPException(504, 'Codex operator request timed out') from None
        finally:
            self.pending.pop(job_id, None)
            if not future.done():
                future.cancel()


def create_gateway(gateway):
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.gateway = gateway

    @app.post(PREFIX + '/heartbeat')
    async def heartbeat(request: Request):
        gateway.authenticate(request)
        try:
            body = json.loads(await read_body(request, 1024))
        except ValueError:
            raise HTTPException(422, 'Invalid relay heartbeat') from None
        if body != {'session_id': gateway.session_id}:
            raise HTTPException(409, 'Relay session changed')
        return await gateway.heartbeat()

    @app.get(PREFIX + '/next')
    async def next_job(request: Request):
        gateway.authenticate(request)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                job = await asyncio.wait_for(gateway.jobs.get(), deadline - time.monotonic())
            except asyncio.TimeoutError:
                break
            if job['id'] in gateway.pending:
                return {'job': job}
        return {'job': None}

    @app.post(PREFIX + '/result/{job_id}')
    async def result(job_id: str, request: Request):
        gateway.authenticate(request)
        future = gateway.pending.get(job_id)
        if future is None:
            raise HTTPException(409, 'Operator request has expired')
        if future.done():
            return {'accepted': True}
        try:
            value = decode_response(json.loads(await read_body(request, ENVELOPE_LIMIT)))
        except (ValueError, KeyError, TypeError, zlib.error):
            raise HTTPException(422, 'Invalid relay response') from None
        if gateway.pending.get(job_id) is not future or future.done():
            raise HTTPException(409, 'Operator request has expired')
        future.set_result(value)
        return {'accepted': True}

    @app.get(PREFIX + '/status')
    async def status(request: Request):
        gateway.authenticate(request)
        return {'compute': 'codex-cloud' if gateway.active() else 'oracle-backup',
                'pending': len(gateway.pending), 'session_id': gateway.session_id}

    @app.api_route('/{path:path}', methods=['GET', 'HEAD', 'POST'])
    async def operator(path: str, request: Request):
        if path.startswith('_codex_bridge'):
            raise HTTPException(404)
        body = await read_body(request, REQUEST_LIMIT)
        if request.method == 'POST':
            async with gateway.route_lock:
                return await gateway.forward(request, body)
        return await gateway.forward(request, body)

    return app


async def relay_worker(credentials, origin='http://127.0.0.1:18080', slots=8):
    # The only remote target is this deployment's HTTPS domain. Browser jobs
    # cannot choose another target, protocol, port, filesystem path or command.
    domain = credentials['domain']
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9.-]*\.[a-zA-Z]{2,}', domain):
        raise ValueError('Invalid operator domain')
    if origin != 'http://127.0.0.1:18080':
        raise ValueError('Worker origin must be the loopback operator app')
    done = asyncio.Event()
    limits = httpx.Limits(max_connections=24, max_keepalive_connections=24)
    async with httpx.AsyncClient(trust_env=False, timeout=35, follow_redirects=False, limits=limits) as local, \
               httpx.AsyncClient(base_url='https://' + domain, timeout=25, follow_redirects=False,
                                headers={'Authorization': 'Bearer ' + credentials['token']}, limits=limits) as remote:
        async def beat():
            previous = None
            while not done.is_set():
                try:
                    health = await local.get(origin + '/api/state', auth=('admin', credentials['password']))
                    health.raise_for_status()
                    response = await remote.post(PREFIX + '/heartbeat', json={'session_id': credentials['session_id']})
                    if response.status_code in (403, 409):
                        done.set()
                        return
                    response.raise_for_status()
                    compute = response.json().get('compute')
                    if compute != previous:
                        print(json.dumps({'compute': compute}), flush=True)
                        previous = compute
                except httpx.ProxyError:
                    print('NETWORK_PROXY_REJECTED: apply the domain network configuration before restarting the worker.', flush=True)
                    done.set()
                    return
                except (httpx.HTTPError, ValueError):
                    pass
                await asyncio.sleep(2)

        async def slot():
            while not done.is_set():
                try:
                    response = await remote.get(PREFIX + '/next')
                    if response.status_code == 403:
                        done.set()
                        return
                    response.raise_for_status()
                    job = response.json().get('job')
                    if job is None:
                        continue
                    if job.get('method') not in ('GET', 'HEAD', 'POST') or not re.fullmatch(r'[a-f0-9]{32}', job['id']):
                        raise ValueError('Invalid operator job')
                    body = base64.b64decode(job['body'], validate=True)
                    if len(body) > REQUEST_LIMIT:
                        raise ValueError('Operator request too large')
                    # Health authentication is deliberately per-call above;
                    # browser requests must still supply their own valid cookie.
                    try:
                        result = await local.request(job['method'], target_url(origin, job['path'], job['query']),
                                                     headers=clean_headers(job['headers']), content=body)
                        payload = {'status': result.status_code, 'headers': clean_headers(result.headers.multi_items()),
                                   'body': base64.b64encode(zlib.compress(result.content, 3)).decode()}
                    except httpx.HTTPError:
                        payload = {'status': 503, 'headers': [('Content-Type', 'application/json')],
                                   'body': base64.b64encode(zlib.compress(b'{"detail":"Codex origin unavailable"}')).decode()}
                    # Re-submit an already computed response if transport fails;
                    # never repeat the original browser command.
                    for _ in range(3):
                        try:
                            accepted = await remote.post(PREFIX + '/result/' + job['id'], json=payload)
                            if accepted.status_code in (200, 409):
                                break
                        except httpx.ProxyError:
                            done.set()
                            return
                        except httpx.HTTPError:
                            pass
                        await asyncio.sleep(1)
                except httpx.ProxyError:
                    done.set()
                    return
                except (httpx.HTTPError, ValueError, KeyError, TypeError):
                    await asyncio.sleep(2)

        tasks = [asyncio.create_task(beat()), *(asyncio.create_task(slot()) for _ in range(slots))]
        try:
            await done.wait()
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['gateway', 'worker'], required=True)
    parser.add_argument('--credentials', required=True)
    parser.add_argument('--password-file')
    args = parser.parse_args()
    credentials_path = Path(args.credentials)
    if credentials_path.stat().st_mode & 0o077:
        raise ValueError('Relay credential file must have mode0600')
    credentials = json.loads(credentials_path.read_text())
    if args.mode == 'worker':
        asyncio.run(relay_worker(credentials))
    else:
        import uvicorn
        password = Path(args.password_file).read_text().strip()
        gateway = Gateway(credentials['token'], credentials['session_id'], credentials['domain'], password)
        uvicorn.run(create_gateway(gateway), host='127.0.0.1', port=18090, access_log=False, log_level='warning')


if __name__ == '__main__':
    main()
