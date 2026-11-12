"""Resource measurements and protection of an existing production match."""
import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def measurement(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / 'scripts'))
    return importlib.import_module('oracle_measure'), importlib.import_module('resource_usage')


def test_cgroup_quota_and_memory_units(measurement, tmp_path):
    _, usage = measurement
    (tmp_path / 'cpu.stat').write_text('usage_usec 2500000\nthrottled_usec 120000\n')
    (tmp_path / 'cpu.max').write_text('200000 100000\n')
    (tmp_path / 'memory.current').write_text('1048576\n')
    (tmp_path / 'memory.max').write_text('4294967296\n')
    value = usage.cgroup_counters(tmp_path)
    assert value['cpu_seconds'] == 2.5 and value['cpu_quota_cores'] == 2
    assert value['memory_bytes'] == 2**20 and value['memory_limit_bytes'] == 4 * 2**30
    assert value['throttled_seconds'] == .12


def test_process_sampler_measures_actual_current_process(measurement):
    _, usage = measurement
    import os
    sampler = usage.ProcessSampler(os.getpid())
    sampler.sample()
    sum(i * i for i in range(10000))
    sampler.sample()
    data = sampler.summary()
    assert data['samples'] == 2 and data['duration_s'] > 0
    assert data['process_roles']['core_api']['peak_rss_bytes'] > 0
    assert 'cmdline' not in json.dumps(data) and 'environment' not in json.dumps(data)


def test_existing_match_is_observed_without_launch_or_stop(measurement, monkeypatch):
    host, _ = measurement
    monkeypatch.setattr(host, 'production_info', lambda: {'id':'original', 'image':'sha256:original', 'pid':1})
    snapshots = iter([{'phase':'running','match_id':'one','match_elapsed_ticks':0,'paused':False,'performance':{}},
                      {'phase':'running','match_id':'one','match_elapsed_ticks':1000,'paused':False,'performance':{}}])
    monkeypatch.setattr(host, 'production_state', lambda: next(snapshots))
    monkeypatch.setattr(host, 'production_group', lambda pid: None)
    monkeypatch.setattr(host, 'gpu_info', lambda: {'nvidia_device_detected':False})
    monkeypatch.setattr(host, 'host_sample', lambda group: {})
    monkeypatch.setattr(host, 'summarize_host', lambda samples, count: {'samples':len(samples)})
    clock = iter([0., 0., 11., 11.])
    monkeypatch.setattr(host.time, 'monotonic', lambda: next(clock))
    monkeypatch.setattr(host.time, 'sleep', lambda seconds: None)
    def forbidden_command(*args, **kwargs):
        raise AssertionError('An active production match must not be changed')
    monkeypatch.setattr(host, 'command', forbidden_command)
    result = {}
    host.measure(SimpleNamespace(seconds=10), result)
    assert result['status'] == 'completed' and result['mode'] == 'observe_existing_match'


@pytest.mark.parametrize('initial_phase', ['waiting', 'finished'])
def test_isolated_benchmark_aborts_and_removes_only_own_container(measurement, monkeypatch, tmp_path, initial_phase):
    host, _ = measurement
    monkeypatch.setattr(host, 'production_info', lambda: {'id':'original', 'image':'sha256:original', 'pid':1})
    states = iter([{'phase':initial_phase}, {'phase':'running'}, {'phase':'running'}])
    monkeypatch.setattr(host, 'production_state', lambda: next(states))
    monkeypatch.setattr(host, 'production_group', lambda pid: None)
    monkeypatch.setattr(host, 'gpu_info', lambda: {})
    monkeypatch.setattr(host, 'host_sample', lambda group: {})
    monkeypatch.setattr(host, 'summarize_host', lambda samples, count: {})
    monkeypatch.setattr(host, 'memory_info', lambda: {'MemAvailable':10 * 2**30})
    monkeypatch.setattr(host.time, 'sleep', lambda seconds: None)
    calls = []
    monkeypatch.setattr(host, 'command', lambda args, **kwargs: calls.append(args) or 'created')
    def fake_run(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(stdout=b'', stderr=b'')
    monkeypatch.setattr(host.subprocess, 'run', fake_run)
    result = {}
    host.measure(SimpleNamespace(seconds=10, run_id='12345', output=str(tmp_path/'result.json')), result)
    assert result['status'] == 'aborted_production_activity'
    create = next(args for args in calls if args[:2] == ['docker','run'])
    assert create[create.index('--network') + 1] == 'none'
    assert create[create.index('--cpu-shares') + 1] == '128'
    assert [args for args in calls if args[:2] == ['docker','rm']] == [['docker','rm','-f','maicon-measure-12345']]
    assert not any(args[:2] in (['docker','stop'], ['docker','restart']) for args in calls)
