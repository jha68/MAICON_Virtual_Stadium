"""Full-duration 10-seed 2D performance evidence with explicit reuse support."""
import json
import os
from pathlib import Path

import pytest

from maicon_sim.config.loader import load_scenario
from maicon_sim.evaluation.batch import batch
from maicon_sim.evaluation.replay import verify_files
from maicon_sim.evaluation.metrics import write_json, machine


@pytest.mark.performance
def test_PERF_001_ten_seed_full_2d_episodes(tmp_path):
    # Reuse only completed, checksum-verified runs explicitly selected by caller.
    selected = os.environ.get("MAICON_BATCH_EVIDENCE")
    if selected:
        root = Path(selected)
    else:
        root = tmp_path / "batch10"
        batch(load_scenario("examples/scenario_smoke_six.yaml"), range(10), root, workers=2)
    measurements = []
    for seed in range(10):
        run = root / f"seed-{seed:04d}"
        manifest = verify_files(run)
        result = json.loads((run / "result.json").read_text())
        metrics = json.loads((run / "summary/metrics.json").read_text())
        assert manifest["seed"] == result["seed"] == seed
        assert result["backend"] == "2d" and result["clock_mode"] == "accelerated"
        assert result["final_match_ms"] == 300000 and result["final_report_ms"] == 30000
        assert all(score["total"] == 20 for score in result["scores"].values())
        assert metrics["ticks_skipped"] == 0 and metrics["wall_s"] > 0
        assert set(metrics["tick_ms"]) == {"p50", "p95", "p99"}
        measurements.append({"seed": seed, "run_id": manifest["run_id"], "wall_s": metrics["wall_s"],
                             "tick_ms": metrics["tick_ms"], "real_time_factor": metrics["real_time_factor"]})
    write_json("artifacts/performance/core10.json", {"test_id":"PERF-001", "environment": machine(),
               "duration_match_ms":300000, "concurrent_benchmark_load": True,
               "reuse_explicitly_selected": bool(selected), "runs": measurements})
