"""Run an isolated, bounded benchmark beside an idle deployment using its image.

This host-side script never stops the production container, reads its environment,
or emits credentials. Public output contains only numeric resource measurements.
"""
import argparse
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import time

from resource_usage import cgroup_counters, cpu_times, memory_info


PROBE = '''import base64,json,pathlib,urllib.request
p=pathlib.Path('/data/web.password').read_text().strip()
r=urllib.request.Request('http://127.0.0.1:8080/api/state',headers={'Authorization':'Basic '+base64.b64encode(('admin:'+p).encode()).decode()})
s=json.load(urllib.request.urlopen(r,timeout=5))
print(json.dumps({k:s[k] for k in ('match_id','phase','paused','sim_tick','match_elapsed_ticks','performance')}))'''


def command(args, **kwargs):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=15, **kwargs).stdout.strip()


def production_info():
    lines = command(['docker', 'inspect', '--format', '{{.Id}}\n{{.Image}}\n{{.State.Pid}}\n{{.State.Running}}',
                     'maicon-sim']).splitlines()
    if len(lines) != 4 or lines[3] != 'true':
        raise RuntimeError('Production server is not running')
    return {'id': lines[0], 'image': lines[1], 'pid': int(lines[2])}


def production_state():
    return json.loads(command(['docker', 'exec', 'maicon-sim', '/app/.venv/bin/python', '-c', PROBE]))


def production_group(pid):
    for line in (Path('/proc') / str(pid) / 'cgroup').read_text().splitlines():
        if line.startswith('0::'):
            return Path('/sys/fs/cgroup') / line[3:].lstrip('/')
    return None


def host_sample(group):
    memory = memory_info()
    return {'at': time.monotonic(), 'cpu': cpu_times(), 'ram_total_bytes': memory['MemTotal'],
            'ram_available_bytes': memory['MemAvailable'],
            'production': cgroup_counters(group) if group is not None else None}


def summarize_host(samples, logical_cpus):
    a, b = samples[0], samples[-1]
    duration = b['at'] - a['at']
    total = b['cpu'][0] - a['cpu'][0]
    result = {'duration_s': duration,
              'cpu_busy_pct': (1 - (b['cpu'][1] - a['cpu'][1]) / total) * 100 if total else None,
              'cpu_steal_pct': (b['cpu'][2] - a['cpu'][2]) / total * 100 if total else None,
              'logical_cpus': logical_cpus, 'ram_total_bytes': a['ram_total_bytes'],
              'ram_used_peak_bytes': max(s['ram_total_bytes'] - s['ram_available_bytes'] for s in samples)}
    if a['production'] and b['production'] and duration:
        result['production_container'] = {
            'average_cpu_cores': max(0., b['production']['cpu_seconds'] - a['production']['cpu_seconds']) / duration,
            'memory_peak_bytes': max(s['production']['memory_bytes'] for s in samples if s['production'])}
    return result


def gpu_info():
    if shutil.which('nvidia-smi'):
        try:
            lines = command(['nvidia-smi', '--query-gpu=name,utilization.gpu,memory.used,memory.total',
                             '--format=csv,noheader,nounits']).splitlines()
            return {'nvidia_smi_available': True, 'devices': [
                {'name': v[0].strip(), 'usage_pct': float(v[1]), 'memory_used_mib': float(v[2]),
                 'memory_total_mib': float(v[3])} for v in (line.split(',') for line in lines)]}
        except (ValueError, subprocess.SubprocessError):
            return {'nvidia_smi_available': True, 'query_succeeded': False}
    return {'nvidia_smi_available': False, 'nvidia_device_detected': Path('/dev/nvidiactl').exists(),
            'drm_device_count': len(list(Path('/sys/class/drm').glob('card[0-9]')))}


def measure(args, result):
    info = production_info()
    state = production_state()
    group = production_group(info['pid'])
    result.update(architecture=platform.machine(), logical_cpus=os.cpu_count(),
                  image_id=info['image'], gpu=gpu_info(), production_initial_phase=state['phase'])
    samples = [host_sample(group)]
    result['host'] = summarize_host(samples, os.cpu_count())
    if state['phase'] != 'waiting':
        result['mode'] = 'observe_existing_match'
        begin = time.monotonic()
        initial = state
        while time.monotonic() - begin < args.seconds:
            time.sleep(1)
            samples.append(host_sample(group))
            state = production_state()
            if state['match_id'] != initial['match_id'] or production_info()['id'] != info['id']:
                result['status'] = 'aborted_session_changed'
                break
        else:
            result['status'] = 'completed'
        result['observed'] = {'wall_s': time.monotonic() - begin, 'initial_phase': initial['phase'],
                              'final_phase': state['phase'], 'paused': state['paused'],
                              'simulated_s': (state['match_elapsed_ticks'] - initial['match_elapsed_ticks']) / 100,
                              'performance': state['performance']}
        result['host'] = summarize_host(samples, os.cpu_count())
        return

    # Leave spare RAM for the running website and OS. Never borrow its credentials.
    available = memory_info()['MemAvailable']
    if available < 5 * 2**30:
        result['status'] = 'skipped_low_available_memory'
        return
    name = 'maicon-measure-' + args.run_id
    target = Path(args.output).resolve().parent
    target.mkdir(mode=0o700, parents=True, exist_ok=True)
    workload = target / 'workload'
    workload.mkdir(mode=0o700)
    scripts = Path(__file__).resolve().parent
    cpu_budget = min(2, len(os.sched_getaffinity(0)))
    memory_limit = 6 if available >= 8 * 2**30 else 4
    result.update(mode='isolated_baseline', benchmark_cpu_budget=cpu_budget,
                  benchmark_memory_limit_gib=memory_limit,
                  caveat='Production website remains running; benchmark has lower CPU scheduling priority.')
    try:
        command(['docker', 'run', '-d', '--name', name, '--network', 'none',
                 '--cpus', str(cpu_budget), '--cpu-shares', '128', '--memory', str(memory_limit) + 'g',
                 '--memory-swap', str(memory_limit) + 'g', '--user', f'{os.getuid()}:{os.getgid()}',
                 '--mount', f'type=bind,src={scripts},dst=/measure,readonly',
                 '--mount', f'type=bind,src={workload},dst=/measure-output',
                 '--env', 'MAICON_LLM_PROVIDER=fixture', '--entrypoint', '/app/.venv/bin/python',
                 info['image'], '/measure/profile_realtime_cpu.py', '--policy', 'baseline',
                 '--cpus', str(cpu_budget), '--seconds', str(args.seconds), '--no-profile',
                 '--sample-resources', '--out', '/measure-output/run'])
        deadline = time.monotonic() + args.seconds + 150
        while time.monotonic() < deadline:
            time.sleep(1)
            samples.append(host_sample(group))
            current = production_state()
            if current['phase'] != 'waiting' or production_info()['id'] != info['id']:
                result['status'] = 'aborted_production_activity'
                break
            running = command(['docker', 'inspect', '--format', '{{.State.Running}} {{.State.ExitCode}}', name]).split()
            if running[0] == 'false':
                result['exit_code'] = int(running[1])
                result['status'] = 'completed' if int(running[1]) == 0 else 'benchmark_failed'
                break
        else:
            result['status'] = 'benchmark_timeout'
        log = subprocess.run(['docker', 'logs', name], capture_output=True, timeout=10)
        fd = os.open(target / 'private-workload.log', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as handle:
            handle.write(log.stdout + log.stderr)
        metrics = workload / 'run' / 'metrics.json'
        if result['status'] == 'completed' and metrics.exists():
            raw = json.loads(metrics.read_text())
            result['benchmark'] = {key: raw[key] for key in
                ('environment', 'scenario_seed', 'policy', 'cpu_affinity', 'profiled', 'wall_s', 'simulated_s',
                 'real_time_factor', 'frame_drops', 'runtime', 'renderer', 'movement_m', 'resources')}
        elif result['status'] == 'completed':
            result['status'] = 'metrics_missing'
    finally:
        # Only this run's container is eligible for removal; production is untouched.
        subprocess.run(['docker', 'rm', '-f', name], capture_output=True, timeout=20)
        result['host'] = summarize_host(samples, os.cpu_count())
        result['production_final_phase'] = production_state()['phase']


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--seconds', type=int, default=60)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[0-9]{1,20}', args.run_id) or not 10 <= args.seconds <= 120:
        parser.error('Expected a numeric run ID and duration10..120 seconds')
    result = {'schema_version': 1, 'source': 'production_Oracle_VM', 'run_id': args.run_id,
              'cpu_units': 'CPU cores, e.g.1.0 =100% of one CPU;2.0 =200%', 'status': 'started'}
    try:
        measure(args, result)
    except Exception as error:
        result.update(status='measurement_error', error_type=type(error).__name__)
    path = Path(args.output)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as handle:
        json.dump(result, handle, indent=2)
        handle.write('\n')
    print('Measurement report saved; status=' + result['status'])


if __name__ == '__main__':
    main()
