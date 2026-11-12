"""Authenticated relay, browser isolation, bounded payloads and safe cutover."""
import asyncio
import base64
import time
import zlib

import httpx
import pytest

from maicon_sim.server.cloud_relay import (Gateway, PREFIX, RESPONSE_LIMIT, create_gateway,
                                          decode_response, relay_worker, target_url)

TOKEN = 'test-relay-token-with-more-than-thirty-two-characters'
SESSION = 'a' * 32
HEADERS = {'Authorization': 'Bearer ' + TOKEN}


def gateway(handler):
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return Gateway(TOKEN, SESSION, 'maicon.example.com', 'current-password-123', client=client)


def test_fallback_does_not_share_browser_sessions_or_change_password():
    async def fallback(request):
        if request.url.path == '/auth/login':
            return httpx.Response(200, json={'accepted':True}, headers={'Set-Cookie':'operator=valid; Path=/'})
        accepted = request.headers.get('cookie') == 'operator=valid'
        return httpx.Response(200 if accepted else 401, json={'accepted':accepted})
    async def run():
        g = gateway(fallback)
        transport = httpx.ASGITransport(app=create_gateway(g))
        try:
            async with httpx.AsyncClient(transport=transport, base_url='https://maicon.example.com') as first:
                assert (await first.post('/auth/login',json={'password':'current-password-123'})).status_code == 200
                response = await first.get('/api/state')
                assert response.status_code == 200 and response.headers['X-Maicon-Compute']=='oracle-backup'
            async with httpx.AsyncClient(transport=transport, base_url='https://maicon.example.com') as other:
                assert (await other.get('/api/state')).status_code == 401
        finally:
            await g.client.aclose()
    asyncio.run(run())


@pytest.mark.parametrize('phase,expected', [('running',False),('ready',False),('reporting',False),
                                          ('waiting',True),('finished',True)])
def test_cutover_waits_for_an_existing_match(phase, expected):
    async def fallback(request):
        assert request.headers['authorization'].startswith('Basic ')
        return httpx.Response(200,json={'phase':phase})
    async def run():
        g = gateway(fallback)
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_gateway(g)),base_url='https://maicon.example.com') as c:
                assert (await c.get(PREFIX+'/status')).status_code == 403
                assert (await c.post(PREFIX+'/heartbeat',headers=HEADERS,json={'session_id':'b'*32})).status_code == 409
                response = await c.post(PREFIX+'/heartbeat',headers=HEADERS,json={'session_id':SESSION})
                assert response.status_code == 200 and g.active() == expected
        finally:
            await g.client.aclose()
    asyncio.run(run())


def test_relay_preserves_user_headers_and_response_cookies_without_repeating_commands():
    async def fallback(request):
        raise AssertionError('An active worker must receive the request')
    async def run():
        g = gateway(fallback)
        g.activated, g.last_seen = True, time.monotonic()
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_gateway(g)),base_url='https://maicon.example.com') as c:
                pending = asyncio.create_task(c.post('/api/command',headers={'X-Maicon-Operator':'1'},json={'action':'ready'}))
                response = await c.get(PREFIX+'/next',headers=HEADERS)
                job = response.json()['job']
                assert job['path']=='/api/command' and job['method']=='POST'
                headers = {k.lower():v for k,v in job['headers']}
                assert headers['x-maicon-operator']=='1' and headers['x-forwarded-proto']=='https'
                assert headers['host']=='maicon.example.com' and headers['cookie']==''
                payload = {'status':200,'headers':[['Set-Cookie','a=one'],['Set-Cookie','b=two'],['Content-Type','application/json']],
                           'body':base64.b64encode(zlib.compress(b'{"accepted":true}')).decode()}
                assert (await c.post(PREFIX+'/result/'+job['id'],headers=HEADERS,json=payload)).status_code==200
                result = await pending
                assert result.json()=={'accepted':True} and result.headers['X-Maicon-Compute']=='codex-cloud'
                assert result.headers.get_list('set-cookie')==['a=one','b=two']
                assert not g.pending
                assert (await c.post(PREFIX+'/result/'+job['id'],headers=HEADERS,json=payload)).status_code==409
        finally:
            await g.client.aclose()
    asyncio.run(run())


def test_worker_paths_cannot_change_the_loopback_origin_and_bodies_are_bounded():
    url = target_url('http://127.0.0.1:18080','//evil.example/path','x=1')
    assert httpx.URL(url).host=='127.0.0.1'
    with pytest.raises(ValueError):
        target_url('http://127.0.0.1:18080','https://evil.example/','')
    bomb = base64.b64encode(zlib.compress(b'x'*(RESPONSE_LIMIT+1))).decode()
    with pytest.raises(ValueError):
        decode_response({'status':200,'headers':[],'body':bomb})


def test_actual_worker_keeps_operator_auth_and_sessions_separate(monkeypatch):
    from fastapi import FastAPI
    from maicon_sim.server.web_auth import install_auth
    from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
    operator = FastAPI()
    install_auth(operator,'current-password-123')
    @operator.get('/api/state')
    async def state(): return {'phase':'waiting','robots':{}}
    async def fallback(request): return httpx.Response(200,json={'phase':'finished'})
    async def run():
        g = gateway(fallback)
        app=create_gateway(g)
        original=httpx.AsyncClient
        def client(**kwargs):
            transport = httpx.ASGITransport(app=app if 'base_url' in kwargs else ProxyHeadersMiddleware(operator))
            return original(transport=transport,**kwargs)
        monkeypatch.setattr(httpx,'AsyncClient',client)
        task=asyncio.create_task(relay_worker({'token':TOKEN,'session_id':SESSION,
                                             'domain':'maicon.example.com','password':'current-password-123'},slots=2))
        try:
            for _ in range(100):
                if g.active():break
                await asyncio.sleep(.01)
            assert g.active()
            async with original(transport=httpx.ASGITransport(app=app),base_url='https://maicon.example.com') as first:
                assert (await first.get('/api/state')).status_code==401
                response=await first.post('/auth/login',json={'password':'current-password-123'},
                                          headers={'X-Maicon-Operator':'1','Origin':'https://maicon.example.com'})
                assert response.status_code==200 and 'Secure' in response.headers['set-cookie']
                assert (await first.get('/api/state')).status_code==200
            async with original(transport=httpx.ASGITransport(app=app),base_url='https://maicon.example.com') as other:
                assert (await other.get('/api/state')).status_code==401
        finally:
            task.cancel()
            await asyncio.gather(task,return_exceptions=True)
            await g.client.aclose()
    asyncio.run(run())
