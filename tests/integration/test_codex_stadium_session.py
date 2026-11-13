import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_published_credentials_create_private_files_without_printing_values(tmp_path):
    settings = json.loads((ROOT/'deploy/codex/session.json').read_text())
    credentials = {**settings, 'password':'test-only-operator-password', 'token':'test-only-worker-token-'*3}
    env = {'PATH':os.environ['PATH'], 'MAICON_RELAY_CREDENTIALS_JSON':json.dumps(credentials)}
    command = [sys.executable, str(ROOT/'deploy/codex/prepare_session.py'), '--from-environment', '--out', str(tmp_path/'private')]
    result = subprocess.run(command, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    for value in (credentials['password'], credentials['token']):
        assert value not in result.stdout+result.stderr
    for name in ('credentials.json', 'web.password'):
        assert (tmp_path/'private'/name).stat().st_mode & 0o777 == 0o600
    assert json.loads((tmp_path/'private/credentials.json').read_text()) == credentials
    credentials['password'] = 'test-only-replacement-password'
    env['MAICON_RELAY_CREDENTIALS_JSON'] = json.dumps(credentials)
    result = subprocess.run(command, env=env, capture_output=True, text=True)
    assert result.returncode != 0
    assert 'test-only-operator-password' in (tmp_path/'private/web.password').read_text()
    assert credentials['password'] not in result.stdout+result.stderr


def test_codex_launcher_uses_reference_map_mock_llm_and_revision(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location('serve_session_test', ROOT/'deploy/codex/serve_session.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    password = tmp_path/'web.password'
    password.write_text('test-only-operator-password\n'); password.chmod(0o600)
    monkeypatch.setattr(sys, 'argv', ['serve_session.py','--session-dir',str(tmp_path)])
    monkeypatch.setattr(module.os, 'environ', {'MAICON_RELAY_CREDENTIALS_JSON':'must not reach participants','MAICON_LLM_PROVIDER':'external'})
    monkeypatch.setattr(module.os, 'sched_setaffinity', lambda *args:None)
    captured = {}
    def launch(executable, args):
        captured.update(args=args, env=dict(module.os.environ))
        raise SystemExit(0)
    monkeypatch.setattr(module.os, 'execv', launch)
    with pytest.raises(SystemExit): module.main()
    assert captured['args'][captured['args'].index('--example')+1] == 'reference_stadium'
    assert captured['env']['MAICON_LLM_PROVIDER'] == 'fixture'
    assert 'MAICON_RELAY_CREDENTIALS_JSON' not in captured['env']
    assert len(captured['env']['MAICON_BUILD_REVISION']) == 40
