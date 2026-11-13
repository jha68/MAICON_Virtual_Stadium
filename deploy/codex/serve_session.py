"""Launch the authenticated simulator using the prepared private session files."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--session-dir', required=True)
    args = parser.parse_args()
    root = Path(args.session_dir).resolve()
    password = root/'web.password'
    if not password.is_file() or password.stat().st_mode & 0o077:
        raise ValueError('Prepare a private operator password file first')
    if len(password.read_text().strip()) < 10:
        raise ValueError('Invalid operator password file')
    os.sched_setaffinity(0, sorted(os.sched_getaffinity(0))[:4])
    for name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
        os.environ[name] = '1'
    os.environ['MAICON_WEB_PASSWORD_FILE'] = str(password)
    os.environ['MAICON_LLM_PROVIDER'] = 'fixture'
    os.environ.pop('MAICON_RELAY_CREDENTIALS_JSON', None)
    revision = subprocess.run(['git','-C',str(Path(__file__).resolve().parents[2]),'rev-parse','HEAD'],
                              text=True,capture_output=True)
    if revision.returncode == 0:
        os.environ['MAICON_BUILD_REVISION'] = revision.stdout.strip()
    run = root/('run-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+secrets.token_hex(4))
    (root/'current-run.json').write_text(json.dumps({'run':str(run),'pid':os.getpid()}))
    os.execv(sys.executable, [sys.executable,'-m','maicon_sim','serve','--example','reference_stadium','--backend','3d',
                            '--public-port','18000','--admin-port','18001','--web-port','18080','--out',str(run)])


if __name__ == '__main__':
    main()
