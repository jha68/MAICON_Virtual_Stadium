"""Exercise the actual deployment shell's failure/rollback paths, without SSH."""
import json
import os
from pathlib import Path
import subprocess

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / 'deploy/oracle/deploy.sh'
IMAGE = 'ghcr.io/jha68/maicon_virtual_stadium@sha256:' + 'a' * 64


@pytest.mark.parametrize('failure', ['', 'pull', 'run', 'health', 'rename', 'permissions'])
def test_deploy_success_or_restores_previous_container(tmp_path, failure):
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
 assert a[a.index('--user')+1]==str(os.getuid())+':'+str(os.getgid())
 if '--rm' in a: sys.exit(1 if fail=='permissions' else 0)
 if fail=='run': sys.exit(1)
 s['maicon-sim']='new-running';save()
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
    result = subprocess.run(['bash', str(SCRIPT), IMAGE], env=env, capture_output=True, text=True)
    state = json.loads(state_path.read_text())
    if not failure:
        assert result.returncode == 0, result.stderr
        assert state == {'maicon-sim': 'new-running', 'maicon-sim-previous': 'old-stopped'}
        assert (data_dir / 'deployed-image.txt').read_text().strip() == IMAGE
    else:
        assert result.returncode != 0
        assert state == {'maicon-sim': 'old-running'}, result.stderr
        assert not (data_dir / 'deployed-image.txt').exists()


def test_deploy_rejects_mutable_image_tag():
    result = subprocess.run(['bash', str(SCRIPT), 'ghcr.io/example/sim:latest'], capture_output=True, text=True)
    assert result.returncode == 2
    assert 'immutable' in result.stderr
