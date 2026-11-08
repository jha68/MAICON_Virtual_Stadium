"""One episode coordinator. All movement/scoring remains in MatchEngine."""
import copy
import time
import uuid
from pathlib import Path

from maicon_sim.config.loader import validate_schema
from maicon_sim.core.engine import MatchEngine
from maicon_sim.sensors.gateway import SensorGateway, SensorUnavailable

from .metrics import file_hash, machine, percentiles, write_json
from .recorder import Recorder, lock_hash


CHANNELS = ("state", "match", "odom", "imu", "scan", "semantic", "camera")


def public_observations(gateway, slot, recorder=None):
    values = {}
    for channel in CHANNELS:
        try:
            value = gateway.get_frame(slot) if channel == "camera" and hasattr(gateway, "get_frame") else gateway.get(slot, channel)
        except (SensorUnavailable, KeyError):
            continue
        if isinstance(value, tuple):
            # Transport JPEG is decoded before being handed to vision callbacks.
            from PIL import Image
            import io
            import numpy as np
            blob, headers = value
            value = {"data": np.asarray(Image.open(io.BytesIO(blob)).convert("RGB"))[..., ::-1].copy(),
                     "sequence": int(headers.get("X-Sim-Sequence", 0)),
                     "captured_tick": int(headers.get("X-Sim-Captured-Tick", 0)),
                     "received_tick": int(headers.get("X-Sim-Received-Tick", 0)), "encoding": "bgr8"}
        values["rgb" if channel == "camera" else channel] = value
        if recorder:
            recorder.observation(slot, channel, value)
    return values


def calibration(config):
    return {"front_camera": copy.deepcopy(config.sensors["front_camera"]),
            "gimbal_pivot_m": config.sensors["geometry"]["gimbal_pivot_m"],
            "camera_offset_gimbal_m": config.sensors["geometry"]["camera_offset_gimbal_m"],
            "pan_deg_per_unit": .5, "tilt_deg_per_unit": .15,
            "lidar": copy.deepcopy(config.sensors["lidar"])}


def build_backend(config, backend, root, headless=True, resolved_assets=None):
    # Asset generation has no import-time Bullet dependency, even for core-only installs.
    from maicon_sim.backends.bullet.asset_builder import resolve_assets, load_resolved_assets
    if resolved_assets:
        assets = load_resolved_assets(resolved_assets, config.assets)
    else:
        assets = resolve_assets(config.assets, Path(root) / "private/assets", base_dir=config.path.parent)
    scene = None
    if backend == "3d":
        from maicon_sim.backends.bullet.backend import BulletBackend
        scene = BulletBackend(config, assets, headless=headless)
    return scene, assets


def apply_decision(engine, slot, decision, policy):
    for kind, payload in decision.reports.items():
        if payload is not None:
            try:
                response = engine.request(kind, slot, payload)
                policy.acknowledge_report(kind, response)
            except Exception as exc:
                if getattr(exc, "status", None) not in (409,):
                    raise
    velocity = getattr(decision, "velocity", None)
    if velocity is not None:
        engine.request("cmd_vel", slot, {"linear_x_mps": velocity[0], "angular_z_rps": velocity[1]})
    gimbal = getattr(decision, "gimbal", None)
    if gimbal is not None:
        response = engine.request("gimbal", slot, dict(zip(("pan", "tilt", "speed", "acc"), gimbal)))
        policy.acknowledge_gimbal(gimbal, response, engine.sim_tick)
    if getattr(decision, "fire", False):
        engine.request("fire", slot, {})


def make_result(engine, config, run_id, backend, clock, wall_s, gateway):
    scores = engine.scores
    if callable(scores):
        scores = scores()
    exact = 0
    # Exact-sector evidence is scored by the shared scorer, not inferred from total alone.
    for score in scores.values():
        val = score["m3"]
        exact += max((n for n in range(5) if any(7*a + 9*b == val and a+b == n for a in range(4) for b in range(2))), default=0)
    events = getattr(engine, "journal", [])
    metrics = {"m3_exact_sectors": exact,
               "report_rejections": getattr(engine, "report_rejections", 0),
               "collision_events": getattr(engine, "collision_events", 0),
               "frame_drops": int(getattr(gateway, "dropped", 0)),
               "pose_error_rmse_m": None,
               "real_time_factor": engine.sim_tick * .01 / max(wall_s, 1e-9)}
    reason = getattr(engine, "end_reason", "timeout") or "timeout"
    return {"schema_version": "1.0", "run_id": run_id, "scenario_id": config.scenario["scenario_id"],
            "seed": config.scenario["seed"], "backend": backend, "clock_mode": clock,
            "rule_profile_hash": config.hashes["rule_profile_hash"], "scenario_hash": config.hashes["scenario_hash"],
            "asset_manifest_hash": config.hashes["asset_manifest_hash"], "dependency_lock_hash": lock_hash(),
            "end_reason": reason, "final_match_ms": engine.match_elapsed_ticks * 10,
            "final_report_ms": engine.reporting_elapsed_ticks * 10, "scores": scores, "metrics": metrics}


def run_episode(config, *, backend="2d", clock="accelerated", out=None, headless=True,
                viewer=False, record_frames=False, resolved_assets=None, replay_events=None,
                abort_on_overload=False, duration_s=None, camera_count=6, oracle=False, checkpoint=None):
    # Internal evaluator fixtures may deliberately alter a loaded configuration.
    # Provenance must describe the actual values, not the original template.
    from maicon_sim.config.loader import canonical_hash
    for name, field in (("scenario", "scenario_hash"), ("rules", "rule_profile_hash"), ("arena", "arena_hash"),
                        ("assets", "asset_manifest_hash"), ("sensors", "sensor_profile_hash")):
        if name == "scenario" and replay_events is not None:
            # The recorded hash identifies the original scenario; replay bundles
            # replace credentials with local synthetic codes by design.
            continue
        config.hashes[field] = canonical_hash(getattr(config, name))
    if clock == "realtime" and replay_events is None:
        from .realtime import run_realtime
        return run_realtime(config, backend=backend, out=out, headless=headless, viewer=viewer,
                            record_frames=record_frames, resolved_assets=resolved_assets,
                            abort_on_overload=abort_on_overload)
    run_id = f"{config.scenario['scenario_id']}-{uuid.uuid4().hex[:10]}"
    root = Path(out or Path("artifacts/runs") / run_id)
    oracle = oracle or any(e["kind"] in ("robot_command", "robot_state_correction", "drone_facility_destroyed") for e in config.scenario.get("events", []))
    recorder = Recorder(root, config, run_id, backend, clock, record_frames, oracle=oracle)
    scene = None
    window = None
    started = time.perf_counter()
    tick_times = []
    try:
        scene, assets = build_backend(config, backend, root, headless, resolved_assets)
        engine = MatchEngine(config, event_sink=None if checkpoint else recorder.event, retain_journal=False)
        if replay_events is not None:
            engine.begin_replay()
        gateway = SensorGateway(config, scene)
        checkpoint_meta = None
        if checkpoint:
            from .checkpoints import restore_checkpoint
            checkpoint_meta = restore_checkpoint(checkpoint, engine, gateway, config)
            engine.event_sink = recorder.event
        if hasattr(gateway, "camera_slots"):
            gateway.camera_slots = set(list(engine.robots)[:camera_count])
        if viewer:
            from maicon_sim.viewer.pygame_viewer import PygameViewer
            window = PygameViewer(config, clock_mode=clock, gateway=gateway)
        if not checkpoint:
            gateway.update(engine)
        if replay_events is None:
            from maicon_sim.policies.baseline import ParticipantPolicy
            policies = {a["slot"]: ParticipantPolicy(config.public_map_prior(), calibration(config), a["slot"], a["policy"])
                        for a in config.scenario["agents"]}
            engine.request("enter_ready", None, {})
            engine.step()
            gateway.update(engine)
            for slot in policies:
                public_observations(gateway, slot, recorder)
                engine.request("ready", slot, {})
            engine.request("start", None, {})
        else:
            policies = {}
        by_tick = {}
        for event in replay_events or []:
            if checkpoint_meta and event["event_seq"] <= checkpoint_meta["event_seq"]:
                continue
            by_tick.setdefault(event["sim_tick"], []).append(event)
        max_ticks = config.scenario["max_sim_ms"] // 10
        debug_paused, single_step, view_speed = False, False, 1.
        view_history = []
        viewed_snapshot = None
        while engine.phase != "finished":
            if window:
                for action in window.poll():
                    kind = action["kind"]
                    if kind == "close":
                        window.close()
                        window = None
                        debug_paused = False
                        break
                    if kind == "debug_pause":
                        debug_paused = action["paused"]
                    elif kind == "step":
                        single_step = True
                    elif kind in ("match_pause", "match_resume"):
                        engine.request("pause" if kind == "match_pause" else "resume", None, {})
                    elif kind == "speed":
                        view_speed = action["factor"]
                    elif kind == "event_seek" and view_history:
                        viewed_snapshot = view_history[action["index"] % len(view_history)]
                if window and debug_paused and not single_step:
                    window.draw(viewed_snapshot or engine.snapshot())
                    time.sleep(.01)
                    continue
                single_step = False
            if engine.sim_tick >= max_ticks:
                write_json(root / "private/last_snapshot.json", engine.snapshot())
                raise RuntimeError(f"max_sim_ms reached at tick {engine.sim_tick}; check event clocks")
            if duration_s is not None and engine.sim_tick >= int(duration_s * 100):
                engine.request("finish", None, {})
                # Finish report window honestly instead of claiming a full 300s benchmark.
                duration_s = None
            if replay_events is not None:
                for event in by_tick.get(engine.sim_tick, []):
                    try:
                        engine.replay_input(event)
                    except Exception as exc:
                        if not hasattr(exc, "status"):
                            raise
                if engine.sim_tick % 10 == 0:
                    for slot in engine.robots:
                        public_observations(gateway, slot, recorder)
            elif engine.sim_tick % 10 == 0:
                for slot, policy in policies.items():
                    observations = public_observations(gateway, slot, recorder)
                    decision = policy.compute(observations, engine.request("me", slot, {}),
                                              engine.request("order", slot, {}), engine.request("target", slot, {}))
                    apply_decision(engine, slot, decision, policy)
            t0 = time.perf_counter()
            engine.step()
            gateway.update(engine)
            if engine.sim_tick % 5000 == 0 and (backend == "2d" or record_frames):
                from .checkpoints import save_checkpoint
                save_checkpoint(root / "private/checkpoints" / f"tick-{engine.sim_tick:08d}.json", engine, gateway, config)
            tick_times.append((time.perf_counter() - t0) * 1000)
            if window and engine.sim_tick % 3 == 0:
                snapshot = engine.snapshot()
                if not view_history or snapshot["phase"] != view_history[-1]["phase"] or engine.sim_tick % 100 == 0:
                    view_history.append(snapshot)
                    view_history[:] = view_history[-1000:]
                window.draw(snapshot)
                time.sleep(.03 / view_speed)
        for slot in engine.robots:
            public_observations(gateway, slot, recorder)
        wall = time.perf_counter() - started
        result = make_result(engine, config, run_id, backend, clock, wall, gateway)
        # Resolved PNG hashes are part of run provenance, not the source manifest placeholders.
        result["asset_manifest_hash"] = file_hash(assets.manifest_path)
        validate_schema(result, "run_result", "result.json")
        metrics = {"environment": machine(), "tick_ms": percentiles(tick_times), "wall_s": wall,
                   "real_time_factor": result["metrics"]["real_time_factor"],
                   "camera_count": camera_count, "resolution": [config.sensors["front_camera"]["width_px"], config.sensors["front_camera"]["height_px"]],
                   "clock_mode": clock, "ticks_skipped": 0, "backend": backend,
                   "frame_drops": getattr(gateway, "dropped", 0), "sensor_samples": {str(k): v for k, v in getattr(gateway, "counts", {}).items()}}
        if scene and hasattr(scene, "metrics"):
            metrics["renderer"] = scene.metrics
        recorder.finish(result, metrics, gateway.capabilities,
                        {"asset_manifest_hash": result["asset_manifest_hash"], "resolved_assets": "private/assets/resolved_manifest.yaml",
                         "checkpoint": checkpoint_meta,
                         "controller_kind": "scripted_fixture" if oracle else "participant_policy",
                         "sensor_checkpoints": "offline_full" if backend == "2d" or record_frames else "not_recorded_RGB_disabled"})
        return result, root
    finally:
        recorder.close()
        if window:
            window.close()
        if scene:
            scene.close()
