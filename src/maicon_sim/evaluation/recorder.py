"""Streaming journals and isolated public/private run artifacts."""
import copy
import csv
import json
import subprocess
import sys
import hashlib
import queue
import threading
from pathlib import Path

from .metrics import canonical, digest, file_hash, machine, write_json


class FrameWriter:
    """Bounded recording; disk/encoder work never runs in the engine thread."""
    def __init__(self, capacity=16, offline=False):
        self.queue = queue.Queue(maxsize=capacity)
        self.dropped = 0
        self.written = 0
        self.peak = 0
        self.error = None
        self.offline = offline
        self.thread = threading.Thread(target=self._run, name="maicon-public-recorder", daemon=True)
        self.thread.start()

    def submit(self, path, data):
        if self.error:
            self.dropped += 1
            return False
        try:
            if self.offline:
                self.queue.put((path, data), timeout=30)
            else:
                self.queue.put_nowait((path, data))
            self.peak = max(self.peak, self.queue.qsize())
            return True
        except queue.Full:
            self.dropped += 1
            return False

    def _run(self):
        try:
            from PIL import Image
            while True:
                job = self.queue.get()
                if job is None:
                    break
                path, data = job
                if not path.exists():
                    path.parent.mkdir(parents=True, exist_ok=True)
                    Image.fromarray(data[..., ::-1]).save(path)
                self.written += 1
        except Exception as exc:
            self.error = type(exc).__name__

    def close(self):
        if self.thread.is_alive():
            try:
                self.queue.put(None, timeout=10)
            except queue.Full:
                self.error = "writer_shutdown_timeout"
            self.thread.join(timeout=10)
            if self.thread.is_alive():
                self.error = "writer_shutdown_timeout"

    @property
    def metrics(self):
        return {"record_frames_written": self.written, "record_frames_dropped": self.dropped,
                "record_queue_peak": self.peak, "record_queue_capacity": self.queue.maxsize,
                "record_error": self.error}


def source_commit():
    root = Path(__file__).resolve().parents[3]
    if not (root / ".git").exists():
        return "installed-distribution-no-vcs"
    try:
        r = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True)
    except FileNotFoundError:
        return "git-unavailable"
    return r.stdout.strip() if r.returncode == 0 else "unborn-working-tree"


def lock_hash():
    # Wheel installations carry the exact build lock in resources.
    from importlib.resources import files
    for p in (Path(__file__).resolve().parents[3] / "uv.lock", Path(str(files("maicon_sim") / "resources" / "uv.lock"))):
        if p.is_file():
            return file_hash(p)
    return "not-available"


def implementation_hash():
    package = Path(__file__).resolve().parents[1]
    return digest({str(p.relative_to(package)): file_hash(p) for p in sorted(package.rglob("*"))
                   if p.is_file() and (p.suffix in (".py", ".json", ".yaml") or p.name == "uv.lock")})


class Recorder:
    def __init__(self, root, config, run_id, backend, clock, record_frames=False, oracle=False):
        self.root = Path(root).resolve()
        if any((self.root / name).exists() for name in ("run_manifest.json", "result.json", "private/events.jsonl", "private/config.json")):
            raise ValueError(f"Output already contains a run: {self.root}; choose a new --out")
        for name in ("private", "summary", "public"):
            (self.root / name).mkdir(parents=True, exist_ok=True)
        self.events_file = (self.root / "private/events.jsonl").open("w")
        self.public_files = {}
        self.last_observation = {}
        self.event_count = 0
        self.config = config
        self.run_id = run_id
        self.backend = backend
        self.clock = clock
        self.record_frames = record_frames
        self.oracle = oracle
        self.implementation_hash = implementation_hash()
        self.frame_writer = None
        bundle = {name: copy.deepcopy(getattr(config, name)) for name in ("scenario", "rules", "arena", "assets", "sensors")}
        # Replay is slot based, not credential based. Do not persist real mission codes.
        for n, agent in enumerate(bundle["scenario"]["agents"], 1):
            agent["mission_code"] = f"REPL{n:04d}"
        bundle["hashes"] = config.hashes
        write_json(self.root / "private/config.json", bundle)

    def event(self, value):
        value = {**value, "run_id": self.run_id}
        self.events_file.write(canonical(value) + "\n")
        self.event_count += 1
        if self.event_count % 100 == 0:
            self.events_file.flush()

    def observation(self, slot, channel, value):
        key = (slot, channel)
        if isinstance(value, dict):
            serial = {k: v for k, v in value.items() if k != "data"}
            signature = (value.get("sequence"), value.get("captured_tick"), digest(serial))
            if self.last_observation.get(key) == signature:
                return
            self.last_observation[key] = signature
            p = self.root / "public" / slot
            p.mkdir(parents=True, exist_ok=True)
            if slot not in self.public_files:
                self.public_files[slot] = (p / "observations.jsonl").open("w")
            if "data" in value and self.record_frames:
                import numpy as np
                data = np.asarray(value["data"])
                pixel_hash = hashlib.sha256(data.tobytes()).hexdigest()
                frame_name = f"frames/{pixel_hash}.png"
                if self.frame_writer is None:
                    self.frame_writer = FrameWriter(offline=self.clock == "accelerated")
                if self.frame_writer.submit(p / frame_name, data):
                    serial["frame_file"] = frame_name
                    serial["frame_pixels_sha256"] = pixel_hash
                else:
                    serial["recording_dropped"] = True
            self.public_files[slot].write(canonical({"channel": channel, "value": serial}) + "\n")

    def finish(self, result, metrics, capabilities, extra=None):
        self.close()
        if self.frame_writer:
            metrics.update(self.frame_writer.metrics)
        write_json(self.root / "result.json", result)
        write_json(self.root / "summary/metrics.json", metrics)
        with (self.root / "score_summary.csv").open("w", newline="") as f:
            names = ["slot", "m1", "m2", "m3", "m4", "m5", "m6", "alliance_bonus", "total"]
            writer = csv.DictWriter(f, fieldnames=names)
            writer.writeheader()
            for slot, score in result["scores"].items():
                writer.writerow({"slot": slot, **score})
        hashes = self.config.hashes
        manifest = {"schema_version": "1.0", "run_id": self.run_id, "source_commit": source_commit(),
                    "reference_source_commit": self.config.rules["source_commit"],
                    "replay_bundle_credentials": "redacted_to_local_synthetic_codes",
                    "implementation_tree_hash": self.implementation_hash,
                    "implementation_changed_during_run": implementation_hash() != self.implementation_hash,
                    **hashes, "seed": self.config.scenario["seed"], "backend": self.backend,
                    "backend_mode": self.backend, "clock_mode": self.clock,
                    "sensor_mode": "rgb" if self.backend == "3d" else "semantic", "oracle": self.oracle,
                    "capabilities": capabilities, "dependency_lock_hash": lock_hash(),
                    "software_version": "0.1.0", "environment": machine(), "command_line": sys.argv,
                    "assumption_ids": self.config.rules["assumption_ids"] + self.config.sensors["assumption_ids"],
                    "sensor_profile_id": self.config.sensors["profile_id"],
                    "noise_profile": self.config.scenario["noise_profile"],
                    "render_profile": self.config.sensors["render"],
                    "record_frames": self.record_frames, "event_count": self.event_count,
                    "files": {str(p.relative_to(self.root)): file_hash(p) for p in sorted(self.root.rglob("*")) if p.is_file() and p.name != "run_manifest.json"}}
        if extra:
            manifest.update(extra)
        write_json(self.root / "run_manifest.json", manifest)
        return manifest

    def close(self):
        if self.frame_writer:
            self.frame_writer.close()
        if not self.events_file.closed:
            self.events_file.close()
        for f in self.public_files.values():
            if not f.closed:
                f.close()
