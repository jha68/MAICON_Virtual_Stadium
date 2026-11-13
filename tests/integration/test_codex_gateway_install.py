"""A failed gateway handoff must preserve the production simulator and route."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize('fail_reload', [False, True])
@pytest.mark.parametrize('live_phase', [None, 'ready', 'running', 'reporting'])
def test_gateway_handoff_or_restores_existing_caddy_without_stopping_simulator(tmp_path, monkeypatch, fail_reload, live_phase):
    path = Path(__file__).resolve().parents[2]/'deploy/codex/install_gateway.py'
    spec = importlib.util.spec_from_file_location('codex_install',path)
    module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    source, data = tmp_path/'source',tmp_path/'data'
    source.mkdir();(data/'proxy').mkdir(parents=True)
    (source/'session.json').write_text(json.dumps({'session_id':'a'*32,'domain':'maicon.example.com'}))
    (source/'cloud_relay.py').write_text('# fixture')
    (source/'session-cert.pem').write_text('public certificate fixture')
    (data/'web.password').write_text('unchanged-secret-password\n')
    original = 'maicon.example.com {\n  reverse_proxy 127.0.0.1:8080\n}\n'
    config = data/'proxy/Caddyfile';config.write_text(original)
    calls=[];failed=False
    def run(args,check=True):
        nonlocal failed
        calls.append(args)
        output=''
        if args[:3]==['docker','inspect','--format']:output='sha256:'+'a'*64
        if args[:3]==['docker','container','inspect']:return SimpleNamespace(returncode=0 if live_phase else 1,stdout='')
        if args[0]=='openssl':Path(args[args.index('-out')+1]).write_bytes(b'ciphertext only')
        if 'reload' in args and fail_reload and not failed:
            failed=True
            raise RuntimeError('injected Caddy reload failure')
        if args[0]=='curl':output='HTTP/2 200\r\nx-maicon-compute: oracle-backup\r\n'
        return SimpleNamespace(returncode=0,stdout=output)
    monkeypatch.setattr(module,'run',run)
    def request(path,headers):
        if path.endswith('/status'):return 200,{},b'{"compute":"oracle-backup"}'
        return 200,{'X-Maicon-Compute':'oracle-backup'},json.dumps({'phase':live_phase or 'waiting','robots':{str(i):{} for i in range(6)}}).encode()
    monkeypatch.setattr(module,'request',request)
    if fail_reload or live_phase:
        with pytest.raises(RuntimeError):module.install(source,data,source)
        assert config.read_text()==original and not (data/'codex-bridge/enabled').exists()
    else:
        module.install(source,data,source)
        assert 'reverse_proxy 127.0.0.1:18090' in config.read_text()
        assert (data/'codex-bridge/enabled').exists()
        assert json.loads((source/'setup-status.json').read_text())['password_changed'] is False
    assert (data/'web.password').read_text()=='unchanged-secret-password\n'
    assert not any(args[:2] in (['docker','stop'],['docker','rm']) and 'maicon-sim' in args for args in calls)
    if live_phase:
        assert not any(args[:2] == ['docker','stop'] for args in calls)
    assert not list((data/'codex-bridge').rglob('bootstrap-*.json'))
