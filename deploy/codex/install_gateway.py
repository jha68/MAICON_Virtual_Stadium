"""Stage the HTTPS gateway without stopping the production simulator."""
import argparse
import base64
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import time
import urllib.request


NAME = 'maicon-codex-relay'


def run(args, check=True):
    return subprocess.run(args, check=check, capture_output=True, text=True, timeout=30)


def private_write(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as handle:
        handle.write(value)


def request(path, headers):
    request = urllib.request.Request('http://127.0.0.1:18090' + path, headers=headers)
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=5) as response:
        return response.status, response.headers, response.read()


def install(source, data, result_dir):
    settings = json.loads((source/'session.json').read_text())
    session, domain = settings['session_id'], settings['domain']
    if not re.fullmatch(r'[a-f0-9]{32}', session) or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9.-]*\.[a-zA-Z]{2,}', domain):
        raise ValueError('Invalid deployment session')
    password = (data/'web.password').read_text().strip()
    if len(password) < 10:
        raise ValueError('Existing operator credential is invalid')
    image = run(['docker','inspect','--format','{{.Image}}','maicon-sim']).stdout.strip()
    if not re.fullmatch(r'sha256:[a-f0-9]{64}', image):
        raise ValueError('Expected the existing immutable image')
    root = data/'codex-bridge'
    session_dir = root/'sessions'/session
    session_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
    root.chmod(0o700)
    credentials_file = session_dir/'credentials.json'
    if credentials_file.exists():
        credentials = json.loads(credentials_file.read_text())
        if credentials['session_id'] != session or credentials['domain'] != domain:
            raise ValueError('Credential session mismatch')
    else:
        credentials = {**settings, 'token':secrets.token_urlsafe(48)}
        private_write(credentials_file, json.dumps(credentials))
    shutil.copyfile(source/'cloud_relay.py', root/'cloud_relay.py')
    # CMS AuthEnvelopedData uses AES-GCM and RSA-OAEP. Only the Codex session
    # private key can recover the operator password and relay control token.
    plaintext = session_dir/('bootstrap-'+secrets.token_hex(8)+'.json')
    try:
        private_write(plaintext, json.dumps({**credentials, 'password':password}))
        run(['openssl','cms','-encrypt','-aes-256-gcm','-binary','-in',str(plaintext),
             '-out',str(result_dir/'bootstrap.cms'),'-outform','DER','-recip',str(source/'session-cert.pem'),
             '-keyopt','rsa_padding_mode:oaep','-keyopt','rsa_oaep_md:sha256'])
    finally:
        plaintext.unlink(missing_ok=True)
    config = data/'proxy/Caddyfile'
    original = config.read_text()
    if domain not in original:
        raise ValueError('The configured operator domain is not present')
    needle, replacement = 'reverse_proxy 127.0.0.1:8080', 'reverse_proxy 127.0.0.1:18090'
    if original.count(needle) == 1:
        candidate = original.replace(needle, replacement, 1)
    elif original.count(replacement) == 1:
        candidate = original
    else:
        raise ValueError('Existing Caddy routing needs review; it was not changed')
    previous = False
    if run(['docker','container','inspect',NAME],check=False).returncode == 0:
        run(['docker','rm','-f',NAME+'-previous'],check=False)
        run(['docker','stop','--time','10',NAME])
        run(['docker','rename',NAME,NAME+'-previous'])
        previous = True
    changed = False
    try:
        run(['docker','run','-d','--name',NAME,'--restart','unless-stopped','--network','host',
             '--user',f'{os.getuid()}:{os.getgid()}',
             '--mount',f'type=bind,src={root},dst=/bridge,readonly',
             '--mount',f'type=bind,src={data/"web.password"},dst=/data/web.password,readonly',
             '--entrypoint','/app/.venv/bin/python',image,'/bridge/cloud_relay.py','--mode','gateway',
             '--credentials',f'/bridge/sessions/{session}/credentials.json','--password-file','/data/web.password'])
        for attempt in range(30):
            try:
                status, _, body = request('/_codex_bridge/status', {'Authorization':'Bearer '+credentials['token']})
                if status == 200 and json.loads(body)['compute'] == 'oracle-backup':
                    break
            except Exception:
                pass
            time.sleep(1)
        else:
            raise RuntimeError('Relay gateway did not become ready')
        auth = base64.b64encode(('admin:'+password).encode()).decode()
        status, headers, body = request('/api/state', {'Authorization':'Basic '+auth,'Host':domain})
        if status != 200 or len(json.loads(body)['robots']) != 6 or headers.get('X-Maicon-Compute') != 'oracle-backup':
            raise RuntimeError('Oracle fallback did not authenticate')
        next_config = config.with_name('Caddyfile.codex-next')
        next_config.write_text(candidate)
        run(['docker','exec','maicon-web-proxy','caddy','validate','--config','/etc/caddy/Caddyfile.codex-next','--adapter','caddyfile'])
        backup = session_dir/'Caddyfile.before'
        if not backup.exists():
            private_write(backup, original)
        os.replace(next_config, config)
        changed = True
        run(['docker','exec','maicon-web-proxy','caddy','reload','--config','/etc/caddy/Caddyfile','--adapter','caddyfile'])
        response = run(['curl','--fail','--silent','--max-time','10','--resolve',domain+':443:127.0.0.1',
                        '-D','-','https://'+domain+'/login'])
        if 'x-maicon-compute: oracle-backup' not in response.stdout.lower():
            raise RuntimeError('HTTPS did not reach the staged gateway')
        (root/'enabled').write_text(session+'\n')
        result = {'session_id':session,'domain':domain,'gateway_installed':True,
                  'oracle_fallback_healthy':True,'compute':'oracle-backup','password_changed':False}
        (result_dir/'setup-status.json').write_text(json.dumps(result,indent=2)+'\n')
        print('Gateway staged; Oracle fallback remains active until the Codex worker is verified.')
    except Exception:
        if changed:
            config.write_text(original)
            run(['docker','exec','maicon-web-proxy','caddy','reload','--config','/etc/caddy/Caddyfile','--adapter','caddyfile'],check=False)
        run(['docker','rm','-f',NAME],check=False)
        if previous:
            run(['docker','rename',NAME+'-previous',NAME],check=False)
            run(['docker','start',NAME],check=False)
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-dir', default=str(Path.home()/'maicon-data'))
    args = parser.parse_args()
    if os.getuid() == 0:
        raise SystemExit('Use the existing non-root deployment user')
    source = Path(__file__).resolve().parent
    install(source, Path(args.data_dir).resolve(), source)
