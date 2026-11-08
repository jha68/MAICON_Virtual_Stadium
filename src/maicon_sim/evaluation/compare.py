"""Compare canonical core outputs without comparing renderer pixels."""
import json
from pathlib import Path

from .metrics import digest


def read_events(root):
    path = Path(root) / "private/events.jsonl"
    events = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    manifest = Path(root) / "run_manifest.json"
    checkpoint = json.loads(manifest.read_text()).get("checkpoint") if manifest.exists() else None
    first = checkpoint["event_seq"] + 1 if checkpoint else 1
    for i, event in enumerate(events, first):
        if event.get("event_seq") != i:
            raise ValueError(f"Non-contiguous event_seq at line {i}")
    return events


def core_event(event):
    return {k: v for k, v in event.items() if k not in ("run_id", "match_id", "event_seq", "wall_timestamp", "wall_time_s")}


def compare(left, right, mode="core"):
    left, right = Path(left), Path(right)
    a, b = (json.loads((p / "result.json").read_text()) for p in (left, right))
    keys = ("scores", "end_reason", "final_match_ms", "final_report_ms")
    for key in keys:
        if a[key] != b[key]:
            return {"equal": False, "difference": key, "expected": a[key], "actual": b[key]}
    if mode == "core":
        checkpoint = json.loads((right / "run_manifest.json").read_text()).get("checkpoint")
        minimum_seq = checkpoint["event_seq"] if checkpoint else 0
        raw_a, raw_b = ([e for e in read_events(p) if e["category"] == "derived" and e["event_seq"] > minimum_seq] for p in (left, right))
        ea, eb = ([core_event(e) for e in rows] for rows in (raw_a, raw_b))
        for i, (x, y) in enumerate(zip(ea, eb)):
            if x != y:
                return {"equal": False, "difference": "derived_event", "index": i, "event_seq": raw_a[i]["event_seq"],
                        "actual_event_seq": raw_b[i]["event_seq"], "expected": x, "actual": y}
        if len(ea) != len(eb):
            return {"equal": False, "difference": "derived_event_count", "expected": len(ea), "actual": len(eb)}
    else:
        ea, eb = a["scores"], b["scores"]
    return {"equal": True, "mode": mode, "core_hash": digest(ea)}
