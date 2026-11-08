"""Measured runtime metrics with explicit machine and clock metadata."""
import hashlib
import json
import platform
import resource
import os
from pathlib import Path

import numpy as np


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def percentiles(values):
    return dict(zip(("p50", "p95", "p99"), map(float, np.percentile(values, (50, 95, 99))))) if values else {"p50": 0., "p95": 0., "p99": 0.}


def machine():
    cpu = platform.processor()
    info = Path("/proc/cpuinfo")
    if info.exists():
        for line in info.read_text().splitlines():
            if line.startswith("model name"):
                cpu = line.split(":", 1)[1].strip()
                break
    return {"os": platform.platform(), "python": platform.python_version(), "cpu": cpu,
            "logical_cpus": os.cpu_count(), "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "gpu_required": False}


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n")
