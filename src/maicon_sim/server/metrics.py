"""Bounded, credential-free HTTP timing diagnostics."""
import threading
import time
from collections import Counter, deque
import numpy as np


class HTTPMetrics:
    def __init__(self, capacity=20000):
        self.lock = threading.Lock()
        self.samples = deque(maxlen=capacity)
        self.count = 0
        self.statuses = Counter()

    def record(self, route, status, elapsed):
        longpoll = route.endswith(("/order", "/target"))
        with self.lock:
            self.count += 1
            self.statuses[str(status)] += 1
            self.samples.append((longpoll, elapsed))

    @property
    def snapshot(self):
        with self.lock:
            samples, count, statuses = list(self.samples), self.count, dict(self.statuses)
        result = {"requests_total": count, "statuses": statuses,
                  "retained_samples": len(samples)}
        for name, longpoll in (("ordinary", False), ("longpoll", True)):
            values = [elapsed for is_wait, elapsed in samples if is_wait == longpoll]
            result[name] = {"sample_count": len(values), **{
                f"p{q}_s": float(np.percentile(values, q)) if values else 0.0 for q in (50, 95, 99)}}
        return result


class HTTPMetricsMiddleware:
    def __init__(self, app, metrics):
        self.app, self.metrics = app, metrics

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        before, status = time.monotonic(), 499
        async def measured_send(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)
        try:
            await self.app(scope, receive, measured_send)
        finally:
            # Only the registered route template is inspected; query strings,
            # headers, body, and unknown attacker-controlled paths are omitted.
            route = getattr(scope.get("route"), "path", "<unmatched>")
            self.metrics.record(route, status, time.monotonic()-before)
