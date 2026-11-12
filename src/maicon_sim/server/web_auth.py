"""Password-only operator sessions; no credentials appear in URLs or scripts."""
import base64
from collections import OrderedDict
import hashlib
import hmac
from importlib.resources import files
import os
from pathlib import Path
import secrets
import time

from fastapi import Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

COOKIE = 'maicon_operator'
SESSION_SECONDS = 12 * 3600


def install_auth(app, password, password_path=None):
    if len(password) < 10:
        raise ValueError('Dashboard password must contain at least 10 characters')
    signing_key = secrets.token_bytes(32)
    failures = OrderedDict()
    resources = files('maicon_sim').joinpath('resources/web')

    def correct(value):
        return isinstance(value, str) and hmac.compare_digest(value.encode(), password.encode())

    def signed(value):
        return hmac.new(signing_key, value.encode(), hashlib.sha256).hexdigest()

    def authenticated(request):
        token = request.cookies.get(COOKIE, '')
        try:
            timestamp, nonce, signature = token.split('.')
            age = time.time() - int(timestamp)
            if 0 <= age < SESSION_SECONDS and hmac.compare_digest(signature, signed(timestamp + '.' + nonce)):
                return True
        except (ValueError, TypeError):
            pass
        # Compatibility for internal deployment health probes. There is no
        # WWW-Authenticate challenge, so browsers never display an ID prompt.
        header = request.headers.get('authorization', '')
        if header.startswith('Basic '):
            peer = request.client.host if request.client else 'unknown'
            now = time.monotonic()
            attempts = [stamp for stamp in failures.get(peer, []) if now-stamp < 60]
            if len(attempts) >= 5:
                return False
            try:
                user, value = base64.b64decode(header[6:], validate=True).decode().split(':', 1)
                if user == 'admin' and correct(value):
                    failures.pop(peer, None)
                    return True
            except (ValueError, UnicodeError):
                pass
            failures[peer] = attempts + [now]
            failures.move_to_end(peer)
            while len(failures) > 1024:
                failures.popitem(last=False)
        return False

    def cookie(response, request):
        value = str(int(time.time())) + '.' + secrets.token_hex(16)
        response.set_cookie(COOKIE, value + '.' + signed(value), max_age=SESSION_SECONDS,
                            httponly=True, secure=request.url.scheme == 'https', samesite='strict', path='/')
        return response

    def same_origin(request):
        from urllib.parse import urlsplit
        origin = request.headers.get('origin')
        return request.headers.get('x-maicon-operator') == '1' and (not origin or urlsplit(origin).netloc.lower() == request.headers.get('host', '').lower())

    @app.middleware('http')
    async def guard(request, call_next):
        public = request.url.path in ('/login', '/auth/login', '/auth/login.js', '/auth/login.css')
        if not public and not authenticated(request):
            if request.url.path == '/':
                return RedirectResponse('/login', status_code=303)
            return JSONResponse({'detail': '로그인이 필요합니다.'}, status_code=401)
        return await call_next(request)

    @app.get('/login')
    async def login_page():
        return FileResponse(str(resources.joinpath('login.html')))

    @app.get('/auth/login.js')
    async def login_script():
        return FileResponse(str(resources.joinpath('login.js')))

    @app.get('/auth/login.css')
    async def login_style():
        return FileResponse(str(resources.joinpath('login.css')))

    @app.post('/auth/login')
    async def login(request: Request):
        if not same_origin(request):
            return JSONResponse({'detail': '허용되지 않은 요청입니다.'}, status_code=403)
        peer = request.client.host if request.client else 'unknown'
        try:
            value = (await request.json()).get('password')
        except (ValueError, AttributeError):
            value = None
        now = time.monotonic()
        attempts = [stamp for stamp in failures.get(peer, []) if now-stamp < 60]
        if len(attempts) >= 5:
            return JSONResponse({'detail': '잠시 후 다시 시도하세요.'}, status_code=429, headers={'Retry-After': '60'})
        if not correct(value):
            failures[peer] = attempts + [now]
            failures.move_to_end(peer)
            while len(failures) > 1024:
                failures.popitem(last=False)
            return JSONResponse({'detail': '비밀번호를 확인해 주세요.'}, status_code=401)
        failures.pop(peer, None)
        return cookie(JSONResponse({'accepted': True}), request)

    @app.post('/auth/logout')
    async def logout(request: Request):
        if not same_origin(request):
            return JSONResponse({'detail': '허용되지 않은 요청입니다.'}, status_code=403)
        response = JSONResponse({'accepted': True})
        response.delete_cookie(COOKIE, path='/')
        return response

    @app.post('/auth/password')
    async def change_password(request: Request):
        nonlocal password, signing_key
        if not same_origin(request):
            return JSONResponse({'detail': '허용되지 않은 요청입니다.'}, status_code=403)
        try:
            body = await request.json()
            value = body.get('new_password')
            valid = (correct(body.get('current_password')) and isinstance(value, str) and 10 <= len(value) <= 256
                     and value == value.strip() and '\n' not in value and '\r' not in value)
        except (ValueError, AttributeError):
            valid = False
        if not valid:
            return JSONResponse({'detail': '현재 비밀번호와 새 비밀번호(10자 이상)를 확인해 주세요.'}, status_code=422)
        if password_path:
            path = Path(password_path)
            temporary = path.with_name(path.name + '.' + secrets.token_hex(8))
            try:
                descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(descriptor, 'w') as handle:
                    handle.write(value + '\n')
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)
        password = value
        signing_key = secrets.token_bytes(32)
        return cookie(JSONResponse({'accepted': True}), request)
