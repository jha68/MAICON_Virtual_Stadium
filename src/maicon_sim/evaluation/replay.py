"""Replay recorded inputs; derived events are never re-injected."""
import json
from pathlib import Path

from .compare import read_events
from .metrics import file_hash


def verify_files(root):
    root = Path(root).resolve()
    manifest = json.loads((root / "run_manifest.json").read_text())
    for name, expected in manifest["files"].items():
        path = (root / name).resolve()
        if not path.is_relative_to(root) or not path.is_file() or file_hash(path) != expected:
            raise ValueError(f"Artifact checksum mismatch: {name}")
    read_events(root)
    return manifest


def load_recorded_config(root):
    from maicon_sim.config.loader import LoadedConfig
    root = Path(root)
    data = json.loads((root / "private/config.json").read_text())
    return LoadedConfig(**data, path=root / "private/scenario.yaml")


def replay_inputs(root):
    verify_files(root)
    return [e for e in read_events(root) if e["category"] == "input"]


def replay_observations(root, callback):
    """Open-loop evaluation: callbacks cannot mutate the recorded world."""
    manifest = verify_files(root)
    count = 0
    for logfile in sorted((Path(root) / "public").glob("*/observations.jsonl")):
        for line in logfile.read_text().splitlines():
            entry = json.loads(line)
            value = entry["value"]
            if entry["channel"] == "camera":
                if not manifest["record_frames"] or "frame_file" not in value:
                    raise ValueError("RGB observation replay requires record_frames=true and recorded frame bytes")
                path = logfile.parent / value["frame_file"]
                if "frame_sha256" in value and file_hash(path) != value["frame_sha256"]:
                    raise ValueError("Recorded RGB checksum mismatch")
                from PIL import Image
                import numpy as np
                value["data"] = np.asarray(Image.open(path).convert("RGB"))[..., ::-1].copy()
                if "frame_pixels_sha256" in value:
                    import hashlib
                    if hashlib.sha256(value["data"].tobytes()).hexdigest() != value["frame_pixels_sha256"]:
                        raise ValueError("Recorded RGB pixel checksum mismatch")
            callback(logfile.parent.name, entry["channel"], value)
            count += 1
    return {"mode": "open_loop_observations", "count": count}
