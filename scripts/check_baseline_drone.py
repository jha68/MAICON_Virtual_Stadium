"""Six-process drone integration on a disposable local 3D dashboard only.

The known test password check prevents accidental use of production credentials.
Run after check_web_ui.cjs, with its test server still running and reset to waiting.
"""
import argparse
import json
from pathlib import Path
import time
from urllib.parse import urlsplit

import httpx

SLOTS = ('B-1', 'B-2', 'B-3', 'R-1', 'R-2', 'R-3')


def observed_navigation(episodes_dir, match_id):
    """Read public participant evidence; one-second UI sampling can miss plans.

    Only the disposable server's current match is considered. This is the
    participant's own transcript, not evaluator poses or private scene truth.
    """
    found = {}
    for slot in SLOTS:
        path = Path(episodes_dir)/match_id/'public'/slot/'participant.jsonl'
        if not path.is_file():
            continue
        for line in path.read_text().splitlines():
            try:
                record = json.loads(line)
            except ValueError:  # The last line may still be being written.
                continue
            diagnostic = record.get('diagnostics', {})
            nav = diagnostic.get('navigation', {})
            tick, captured = record.get('observed_tick'), nav.get('drone_capture_tick')
            if (record.get('match_id') == match_id and record.get('slot') == slot
                    and record.get('phase') == 'running'
                    and nav.get('source') == 'lidar_and_public_drone'
                    and type(tick) is int and type(captured) is int and 0 <= tick-captured <= 150):
                found[slot] = {k: diagnostic.get(k) for k in ('drone', 'navigation', 'drone_search_cue', 'evasion')}
                break
    return found


def check(base, password_file, episodes_dir=None):
    url = urlsplit(base)
    if url.scheme != 'http' or url.hostname != '127.0.0.1' or url.path or url.username or url.password:
        raise ValueError('Use a disposable loopback HTTP dashboard')
    password = Path(password_file).read_text().strip()
    if password != 'test-only-browser-password-0123456789':
        raise ValueError('This test requires the browser fixture password')
    with httpx.Client(base_url=base, auth=('admin', password),
                      headers={'X-Maicon-Operator': '1', 'Origin': base}, trust_env=False, timeout=30) as client:
        def state():
            response = client.get('/api/state')
            response.raise_for_status()
            return response.json()

        def command(action):
            response = client.post('/api/command', json={
                'action': action})
            response.raise_for_status()

        initial = state()
        assert initial['phase'] == 'waiting' and initial['scenario_id'] == 'reference_stadium'
        assert initial['m1_mode'] == 'direct_order' and initial['m6_mode'] == 'mock'
        command('ready')
        deadline = time.monotonic()+90
        while not all(r['ready'] for r in state()['robots'].values()):
            if time.monotonic() > deadline:
                raise RuntimeError('Six baseline participants did not become ready')
            time.sleep(.5)
        command('start')
        statuses = {}
        deadline = time.monotonic()+45
        while time.monotonic() < deadline:
            if episodes_dir:
                statuses.update(observed_navigation(episodes_dir, initial['match_id']))
            for slot in SLOTS:
                response = client.get('/api/participant/'+slot)
                response.raise_for_status()
                diagnostics = response.json().get('diagnostics', {})
                if diagnostics.get('navigation', {}).get('source') == 'lidar_and_public_drone':
                    statuses[slot] = {k: diagnostics.get(k) for k in ('drone', 'navigation', 'drone_search_cue', 'evasion')}
            if len(statuses) == 6:
                break
            time.sleep(1)
        assert len(statuses) == 6, 'Not all participants used calibrated public drone frames'
        assert state()['manual_interventions'] == 0
        command('finish')
        deadline = time.monotonic()+45
        while state()['phase'] != 'finished':
            if time.monotonic() > deadline:
                raise RuntimeError('Local final reports did not finish')
            time.sleep(.5)
        evidence = {'status': 'passed', 'participants': statuses, 'manual_interventions': 0, 'm1_mode': 'direct_order', 'm6_mode': 'mock'}
        Path('artifacts/six-baseline-drone-evidence.json').write_text(json.dumps(evidence, indent=2))
        print('Six real baseline processes used calibrated public drone navigation; M1 mock, local match finished.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', default='http://127.0.0.1:18080')
    parser.add_argument('--password-file', required=True)
    parser.add_argument('--episodes-dir', help='Disposable server public transcript directory')
    args = parser.parse_args()
    check(args.base, args.password_file, args.episodes_dir)
