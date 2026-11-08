"""Explicit seed sweeps and policy comparison groups."""
import copy
import json
from pathlib import Path
import statistics

from maicon_sim.config.loader import canonical_hash
from .metrics import write_json


def seeded(config, seed):
    config = copy.deepcopy(config)
    config.scenario["seed"] = seed
    config.hashes["scenario_hash"] = canonical_hash(config.scenario)
    return config


def _run_seed(args):
    from .runner import run_episode
    config, seed, out, backend = args
    result, path = run_episode(seeded(config, seed), backend=backend, out=Path(out) / f"seed-{seed:04d}")
    totals = [s["total"] for s in result["scores"].values()]
    manifest = json.loads((path / "run_manifest.json").read_text())
    return {"seed": seed, "split": "selection" if seed < 20 else "holdout",
            "oracle": manifest["oracle"], "sensor_mode": manifest["sensor_mode"],
            "scores": totals, "mean": statistics.mean(totals), "result_path": str(path / "result.json"),
            "metrics": result["metrics"]}


def batch(config, seeds, out, backend="2d", workers=1):
    out = Path(out)
    arguments = [(config, seed, out, backend) for seed in seeds]
    if workers == 1:
        rows = [_run_seed(args) for args in arguments]
    else:
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(max_workers=workers) as pool:
            rows = list(pool.map(_run_seed, arguments))
    all_scores = sorted(x for row in rows for x in row["scores"])
    is_oracle = any(row["oracle"] for row in rows)
    summary = {"backend": backend, "sensor_mode": "rgb" if backend == "3d" else "semantic", "oracle": is_oracle,
               "candidate_leaderboard_eligible": not is_oracle,
               "runs": rows, "workers": workers, "mean": statistics.mean(all_scores), "median": statistics.median(all_scores),
               "minimum": min(all_scores), "lower_10_percent": all_scores[max(0, int(len(all_scores) * .1)-1)]}
    write_json(out / "batch_summary.json", summary)
    return summary
