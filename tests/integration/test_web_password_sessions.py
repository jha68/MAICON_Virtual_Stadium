import asyncio
import httpx
import pytest
from fastapi import FastAPI
from maicon_sim.server.web_auth import install_auth, COOKIE


def app(password, path=None):
    result = FastAPI()
    install_auth(result, password, path)
    @result.get('/api/private')
    async def private(): return {'ok': True}
    return result


def test_password_only_session_change_persists_and_revokes_old_cookie(tmp_path):
    path = tmp_path/'web.password'
    path.write_text('old-secret-12345\n')
    application = app('old-secret-12345', path)
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url='https://web') as c:
            headers = {'X-Maicon-Operator': '1', 'Origin': 'https://web'}
            home = await c.get('/')
            assert home.status_code == 303 and home.headers['location'] == '/login'
            page = await c.get('/login')
            assert page.status_code == 200 and 'type="password"' in page.text
            assert 'username' not in page.text and 'WWW-Authenticate' not in home.headers
            assert (await c.get('/api/private')).status_code == 401
            assert (await c.post('/auth/login', json={'password':'wrong'}, headers=headers)).status_code == 401
            response = await c.post('/auth/login', json={'password':'old-secret-12345'}, headers=headers)
            assert response.status_code == 200
            assert 'HttpOnly' in response.headers['set-cookie'] and 'Secure' in response.headers['set-cookie']
            assert 'SameSite=strict' in response.headers['set-cookie']
            old_cookie = c.cookies.get(COOKIE)
            assert (await c.get('/api/private')).status_code == 200
            assert (await c.post('/auth/password', headers=headers, json={'current_password':'wrong','new_password':'NewPass1234'})).status_code == 422
            assert (await c.post('/auth/password', headers=headers, json={'current_password':'old-secret-12345','new_password':'123456789'})).status_code == 422
            response = await c.post('/auth/password', headers=headers, json={'current_password':'old-secret-12345','new_password':'NewPass123'})
            assert response.status_code == 200 and path.read_text().strip() == 'NewPass123'
            assert path.stat().st_mode & 0o777 == 0o600
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url='https://web', cookies={COOKIE:old_cookie}) as other:
                assert (await other.get('/api/private')).status_code == 401
            assert (await c.get('/api/private')).status_code == 200
            assert (await c.post('/auth/logout', headers=headers)).status_code == 200
            assert (await c.get('/api/private')).status_code == 401
        restarted = app(path.read_text().strip())
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=restarted), base_url='https://web') as c:
            assert (await c.post('/auth/login', headers=headers, json={'password':'NewPass123'})).status_code == 200
    asyncio.run(run())


def test_tampered_cookie_cross_origin_and_login_throttle():
    application = app('TenChars12')
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url='http://web', cookies={COOKIE:'999.bad.signature'}) as c:
            assert (await c.get('/api/private')).status_code == 401
            assert (await c.post('/auth/login', headers={'X-Maicon-Operator':'1','Origin':'https://elsewhere'},json={'password':'TenChars12'})).status_code == 403
            for _ in range(5):
                assert (await c.post('/auth/login', headers={'X-Maicon-Operator':'1'},json={'password':'wrong'})).status_code == 401
            assert (await c.post('/auth/login', headers={'X-Maicon-Operator':'1'},json={'password':'TenChars12'})).status_code == 429
    asyncio.run(run())


def test_minimum_password_length():
    with pytest.raises(ValueError): app('123456789')
    app('1234567890')
