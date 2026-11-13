"""Exercise the actual deployment shell's failure/rollback paths, without SSH."""
import json
import os
from pathlib import Path
import subprocess

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / 'deploy/oracle/deploy.sh'
IMAGE = 'ghcr.io/jha68/maicon_virtual_stadium@sha256:' + 'a' * 64


@pytest.mark.parametrize('failure', ['', 'pull', 'run', 'health', 'rename', 'permissions', 'phase_ready', 'phase_running', 'phase_reporting', 'phase_unknown', 'phase_unavailable'])
@pytest.mark.parametrize('domain', ['', 'maicon.example.com'])
def test_deploy_success_or_restores_previous_container(tmp_path, failure, domain):
    if failure.startswith('phase_') and not domain:
        pytest.skip('The production operator state guard requires the web deployment')
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    state_path = tmp_path / 'docker.json'
    state_path.write_text(json.dumps({'maicon-sim': 'old-running'}))
    docker = bin_dir / 'docker'
    docker.write_text('''#!/usr/bin/env python3
import json,os,sys
from pathlib import Path
p=Path(os.environ['FAKE_DOCKER_STATE']);s=json.loads(p.read_text());a=sys.argv[1:];fail=os.environ['FAKE_FAILURE']
def save(): p.write_text(json.dumps(s))
if a[0]=='pull': sys.exit(1 if fail=='pull' else 0)
if a[:2]==['container','inspect']: sys.exit(0 if a[-1] in s else 1)
if a[0]=='inspect': print('true' if s.get(a[-1],'').endswith('running') else 'false')
elif a[0]=='rm': s.pop(a[-1],None);save()
elif a[0]=='stop': s[a[-1]]=s[a[-1]].replace('running','stopped');save()
elif a[0]=='rename':
 if fail=='rename' and a[-1]=='maicon-sim-previous': sys.exit(1)
 s[a[-1]]=s.pop(a[-2]);save()
elif a[0]=='start': s[a[-1]]=s[a[-1]].replace('stopped','running');save()
elif a[0]=='run':
 if 'caddy:2.10.2' in a:
  if '--rm' not in a: s['maicon-web-proxy']='proxy-running';save()
  sys.exit(0)
 assert a[a.index('--user')+1]==str(os.getuid())+':'+str(os.getgid())
 if '--rm' in a: sys.exit(1 if fail=='permissions' else 0)
 if fail=='run': sys.exit(1)
 s['maicon-sim']='new-running';save()
elif a[0]=='exec' and '/api/state' in a[-1] and 'print(json.load' in a[-1]:
 if fail=='phase_unavailable': sys.exit(1)
 print(fail[6:] if fail.startswith('phase_') else 'finished')
elif a[0]=='logs': pass
''')
    docker.chmod(0o755)
    curl = bin_dir / 'curl'
    curl.write_text('''#!/usr/bin/env python3
import os,sys
if os.environ['FAKE_FAILURE']=='health': sys.exit(22)
print('{"slot":"B-1","capabilities":{"rgb":true}}')
''')
    curl.chmod(0o755)
    data_dir = tmp_path / 'persistent data'
    env = {**os.environ, 'PATH': str(bin_dir) + os.pathsep + os.environ['PATH'],
           'FAKE_DOCKER_STATE': str(state_path), 'FAKE_FAILURE': failure,
           'MAICON_DATA_DIR': str(data_dir), 'MAICON_HEALTH_ATTEMPTS': '1',
           'MAICON_HEALTH_INTERVAL': '0'}
    result = subprocess.run(['bash', str(SCRIPT), IMAGE, domain], env=env, capture_output=True, text=True)
    state = json.loads(state_path.read_text())
    if not failure:
        assert result.returncode == 0, result.stderr
        expected = {'maicon-sim': 'new-running', 'maicon-sim-previous': 'old-stopped'}
        if domain:
            expected['maicon-web-proxy'] = 'proxy-running'
            assert (data_dir/'proxy/Caddyfile').read_text().startswith(domain+' {')
        assert state == expected
        assert (data_dir / 'deployed-image.txt').read_text().strip() == IMAGE
    else:
        assert result.returncode != 0
        assert state == {'maicon-sim': 'old-running'}, result.stderr
        assert not (data_dir / 'deployed-image.txt').exists()


def test_deploy_rejects_mutable_image_tag():
    result = subprocess.run(['bash', str(SCRIPT), 'ghcr.io/example/sim:latest'], capture_output=True, text=True)
    assert result.returncode == 2
    assert 'immutable' in result.stderr


@pytest.mark.parametrize('change', ['none', 'legacy_images', 'missing_panels', 'wrong_revision'])
def test_deployed_image_health_accepts_latest_m5_map_and_rejects_stale_builds(monkeypatch, capsys, change):
    import io
    import urllib.request
    source = SCRIPT.read_text().split("<<'PYHEALTH'\n", 1)[1].split('\nPYHEALTH', 1)[0]
    state = {'scenario_id': 'reference_stadium', 'boxes': [None]*20,
             'facility_signals': {str(i): 'idle' for i in range(6)},
             'visual_assets': {str(i): {} for i in range(16)},
             'arena': {'base_panels': [None]*6}, 'llm_mode': 'mock', 'build_revision': 'a'*40}
    if change == 'legacy_images':
        state['visual_assets'] = {str(i): {} for i in range(13)}
    elif change == 'missing_panels':
        state['arena']['base_panels'] = []
    elif change == 'wrong_revision':
        state['build_revision'] = 'b'*40
    def response(request, timeout):
        return io.BytesIO(json.dumps(state).encode() if request.full_url.endswith('/api/state') else b'<html></html>')
    with monkeypatch.context() as patch:
        patch.setenv('MAICON_BUILD_REVISION', 'a'*40)
        patch.setattr(Path, 'read_text', lambda *args, **kwargs: 'test-only-health-password')
        patch.setattr(urllib.request, 'urlopen', response)
        if change == 'none':
            exec(compile(source, str(SCRIPT), 'exec'), {})
        else:
            with pytest.raises(AssertionError):
                exec(compile(source, str(SCRIPT), 'exec'), {})
    if change == 'none':
        evidence = json.loads(capsys.readouterr().out)
        assert evidence['images'] == 16 and evidence['base_panels'] == 6
