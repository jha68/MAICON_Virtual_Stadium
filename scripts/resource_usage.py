"""Linux resource measurements without command lines, environment or credentials."""
from collections import defaultdict
import os
from pathlib import Path
import time


def memory_info():
    return {k: int(v.split()[0]) * 1024 for k, v in
            (line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())}


def cpu_times():
    values = list(map(int, Path('/proc/stat').read_text().splitlines()[0].split()[1:9]))
    return sum(values), values[3] + values[4], values[7]


def cgroup_counters(root=Path('/sys/fs/cgroup')):
    try:
        values = dict(line.split() for line in (root / 'cpu.stat').read_text().splitlines())
        quota, period = (root / 'cpu.max').read_text().split()
        limit = (root / 'memory.max').read_text().strip()
        return {'cpu_seconds': int(values['usage_usec']) / 1e6,
                'cpu_quota_cores': None if quota == 'max' else int(quota) / int(period),
                'memory_bytes': int((root / 'memory.current').read_text()),
                'memory_limit_bytes': None if limit == 'max' else int(limit),
                'throttled_seconds': int(values.get('throttled_usec', 0)) / 1e6}
    except (OSError, ValueError, KeyError):
        return None


def process_data(pid, root_pid):
    directory = Path('/proc') / str(pid)
    fields = (directory / 'stat').read_text().rsplit(')', 1)[1].split()
    args = (directory / 'cmdline').read_bytes().decode(errors='replace').split('\0')
    role = 'core_api' if pid == root_pid else 'support'
    if 'agent' in args and '--slot' in args:
        slot = args[args.index('--slot') + 1]
        if slot in ('B-1', 'B-2', 'B-3', 'R-1', 'R-2', 'R-3'):
            role = 'participant_' + slot
    elif any('spawn_main' in value for value in args):
        role = 'renderer'
    pss = None
    try:
        for line in (directory / 'smaps_rollup').read_text().splitlines():
            if line.startswith('Pss:'):
                pss = int(line.split()[1]) * 1024
                break
    except OSError:
        pass
    return {'pid': pid, 'ppid': int(fields[1]), 'start': int(fields[19]), 'role': role,
            'cpu_seconds': (int(fields[11]) + int(fields[12])) / os.sysconf('SC_CLK_TCK'),
            'rss_bytes': int(fields[21]) * os.sysconf('SC_PAGE_SIZE'), 'pss_bytes': pss,
            'threads': int(fields[17])}


def process_tree(root_pid):
    parents = {}
    for directory in Path('/proc').iterdir():
        if directory.name.isdigit():
            try:
                fields = (directory / 'stat').read_text().rsplit(')', 1)[1].split()
                parents[int(directory.name)] = int(fields[1])
            except (OSError, ValueError, IndexError):
                pass
    selected = {root_pid}
    while True:
        expanded = selected | {pid for pid, parent in parents.items() if parent in selected}
        if expanded == selected:
            rows = []
            for pid in selected:
                try:
                    rows.append(process_data(pid, root_pid))
                except (OSError, ValueError, IndexError):
                    pass
            return rows
        selected = expanded


class ProcessSampler:
    def __init__(self, root_pid):
        self.root_pid = root_pid
        self.samples = []

    def sample(self):
        self.samples.append({'at': time.monotonic(), 'container': cgroup_counters(),
                             'processes': process_tree(self.root_pid)})

    def summary(self):
        if len(self.samples) < 2:
            return {'samples': len(self.samples)}
        first, last = self.samples[0], self.samples[-1]
        duration = last['at'] - first['at']
        groups = defaultdict(lambda: {'cpu_seconds': 0., 'peak_rss_bytes': 0,
                                     'peak_pss_bytes': 0, 'peak_threads': 0})
        previous = {(r['pid'], r['start']): r for r in first['processes']}
        for sample in self.samples:
            for row in sample['processes']:
                group = groups[row['role']]
                group['peak_rss_bytes'] = max(group['peak_rss_bytes'], row['rss_bytes'])
                group['peak_pss_bytes'] = max(group['peak_pss_bytes'], row['pss_bytes'] or 0)
                group['peak_threads'] = max(group['peak_threads'], row['threads'])
                key = row['pid'], row['start']
                if key in previous:
                    group['cpu_seconds'] += max(0., row['cpu_seconds'] - previous[key]['cpu_seconds'])
                previous[key] = row
        for row in groups.values():
            row['average_cpu_cores'] = row['cpu_seconds'] / duration
        result = {'samples': len(self.samples), 'duration_s': duration, 'process_roles': dict(groups),
                  'cpu_units': '1.0 core =100% of one logical CPU;2.0 cores =200%'}
        a, b = first['container'], last['container']
        if a and b:
            cores = max(0., b['cpu_seconds'] - a['cpu_seconds']) / duration
            result['container'] = {'average_cpu_cores': cores, 'cpu_quota_cores': b['cpu_quota_cores'],
                'quota_used_pct': cores / b['cpu_quota_cores'] * 100 if b['cpu_quota_cores'] else None,
                'memory_peak_bytes': max(s['container']['memory_bytes'] for s in self.samples if s['container']),
                'memory_limit_bytes': b['memory_limit_bytes'],
                'throttled_seconds': max(0., b['throttled_seconds'] - a['throttled_seconds'])}
        return result
