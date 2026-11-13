"""Overload must not compress the final mission window into a burst of ticks."""
from types import SimpleNamespace

import pytest

from maicon_sim.server.runtime import EngineRuntime


def test_overload_preserves_every_tick_without_repaying_unbounded_clock_debt(monkeypatch):
    now = [100.]
    ticks = []
    def step():
        ticks.append(now[0])
        now[0] += .3 if len(ticks) == 1 else .0001
    engine = SimpleNamespace(step=step, robots={})
    runtime = EngineRuntime(engine)
    class Stop:
        def is_set(self): return len(ticks) >= 100
        def set(self): pass
        def wait(self, seconds): now[0] += seconds
    runtime._stop = Stop()
    monkeypatch.setattr('maicon_sim.server.runtime.time.monotonic', lambda: now[0])
    runtime._run()
    assert runtime.failure is None and runtime.tick_count == 100
    assert runtime.max_lag_s == pytest.approx(.29)  # CPU delay remains visible in diagnostics.
    assert runtime.elapsed_s >= 1.0899
    assert ticks[26]-ticks[1] >= .049  # No 30-tick instant catch-up after the stall.
