"""Command-line entry points documented by the delivered implementation plan."""
from __future__ import annotations

import argparse
import importlib.metadata
from importlib.resources import files
import json
import os
from pathlib import Path
import sys


def parser():
    p = argparse.ArgumentParser(prog="maicon-sim", description="Shared-core MAICON 2D/3D simulator (synthetic SIM profiles)")
    p.add_argument("--version", action="version", version="maicon-sim 0.1.0")
    subs = p.add_subparsers(dest="command", required=True)
    doctor = subs.add_parser("doctor", help="Check installed tools and headless backend")
    doctor.add_argument("--backend", choices=("2d", "3d"), default="2d")
    doctor.add_argument("--headless", action="store_true")
    val = subs.add_parser("validate", help="Validate schema, references and geometry")
    scenario_args(val)
    val.add_argument("--backend", choices=("2d", "3d"))
    assets = subs.add_parser("assets", help="Resolve synthetic or checksum-verified imported images")
    asset_sub = assets.add_subparsers(dest="asset_command", required=True)
    build = asset_sub.add_parser("build")
    build.add_argument("--manifest", required=True)
    build.add_argument("--out", required=True)
    run = subs.add_parser("run", help="Run an entire match and write evaluator artifacts")
    scenario_args(run)
    run.add_argument("--backend", choices=("2d", "3d"), default="2d")
    run.add_argument("--clock", choices=("accelerated", "realtime"), default="accelerated")
    run.add_argument("--headless", action="store_true")
    run.add_argument("--viewer", action="store_true")
    run.add_argument("--out")
    run.add_argument("--record-frames", action="store_true")
    run.add_argument("--resolved-assets")
    run.add_argument("--abort-on-overload", action="store_true")
    serve = subs.add_parser("serve", help="Serve realtime public and loopback supervisor APIs")
    scenario_args(serve)
    serve.add_argument("--backend", choices=("2d", "3d"), default="2d")
    serve.add_argument("--clock", choices=("realtime", "accelerated"), default="realtime")
    serve.add_argument("--public-port", type=int, default=8000)
    serve.add_argument("--admin-port", type=int, default=8001)
    serve.add_argument("--out", default="artifacts/server")
    serve.add_argument("--web-port", type=int, help="Loopback operator dashboard; requires MAICON_WEB_PASSWORD_FILE")
    agent = subs.add_parser("agent", help="Run one public-port participant process")
    agent.add_argument("--slot", required=True, choices=("B-1", "B-2", "B-3", "R-1", "R-2", "R-3"))
    agent.add_argument("--policy", choices=("idle", "baseline", "patrol", "blocker", "capture_runner"), default="baseline")
    agent.add_argument("--server", required=True)
    agent.add_argument("--out", default=".")
    agent.add_argument("--llm-provider", choices=("fixture", "json-http", "openai-compatible"))
    agent.add_argument("--llm-endpoint")
    agent.add_argument("--llm-model")
    agent.add_argument("--llm-key-env", help="Environment variable name, never a credential value")
    agent.add_argument("--llm-timeout-s", type=float, default=5.)
    agent.add_argument("--camera-calibration", default=os.environ.get("MAICON_CAMERA_CALIBRATION"))
    agent.add_argument("--vision-stress-seed", type=int, default=None)
    calibrate = subs.add_parser("calibrate-camera", help="Fit measured checkerboard images; writes a new camera JSON")
    calibrate.add_argument("--images", nargs="+", required=True)
    calibrate.add_argument("--board-cols", type=int, required=True)
    calibrate.add_argument("--board-rows", type=int, required=True)
    calibrate.add_argument("--square-size-m", type=float, required=True)
    calibrate.add_argument("--out", required=True)
    augment = subs.add_parser("augment-image", help="Deterministic photometric stress image, outside source assets")
    augment.add_argument("--image", required=True)
    augment.add_argument("--out", required=True)
    augment.add_argument("--seed", type=int, required=True)
    augment.add_argument("--brightness", type=float, default=.9)
    augment.add_argument("--blur-sigma", type=float, default=.5)
    augment.add_argument("--noise-sigma", type=float, default=2.)
    replay = subs.add_parser("replay", help="Verify checksums and re-inject recorded inputs")
    replay.add_argument("--run", required=True)
    replay.add_argument("--backend", choices=("2d", "3d"), default="2d")
    replay.add_argument("--verify", action="store_true")
    replay.add_argument("--mode", choices=("core", "observations"), default="core")
    replay.add_argument("--out", required=True)
    replay.add_argument("--checkpoint-tick", type=int, help="Resume from a recorded offline core+sensor checkpoint")
    comp = subs.add_parser("compare", help="Compare scores and canonical core journals")
    comp.add_argument("--left", required=True)
    comp.add_argument("--right", required=True)
    comp.add_argument("--mode", choices=("core", "scores"), default="core")
    batch = subs.add_parser("batch", help="Run explicit seeds without mixing oracle and RGB groups")
    scenario_args(batch)
    batch.add_argument("--backend", choices=("2d", "3d"), default="2d")
    batch.add_argument("--seeds", default="0:20")
    batch.add_argument("--out", required=True)
    batch.add_argument("--workers", type=int, choices=range(1, 9), default=1)
    generate = subs.add_parser("generate", help="Materialize randomized, validated, connected layouts")
    generate.add_argument("--template", required=True)
    generate.add_argument("--seed", type=int, required=True)
    generate.add_argument("--count", type=int, default=1)
    generate.add_argument("--out", required=True)
    generate.add_argument("--layout-mode", choices=("competition", "stress"), default="competition",
                          help="Mirror M2 facility pairs (default) or place independently for asymmetric stress tests")
    benchmark = subs.add_parser("benchmark", help="Measure actual throughput; never skip ticks")
    scenario_args(benchmark)
    benchmark.add_argument("--backend", choices=("2d", "3d"), default="2d")
    benchmark.add_argument("--duration-s", type=float, default=300)
    benchmark.add_argument("--camera-count", type=int, choices=range(1, 7), default=6)
    benchmark.add_argument("--out", required=True)
    dataset = subs.add_parser("dataset", help="Export private evaluator RGB/depth/masks/annotations")
    scenario_args(dataset)
    dataset.add_argument("--out", required=True)
    return p


def scenario_args(p):
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--scenario", help="Scenario YAML path")
    group.add_argument("--example", choices=("reference_stadium", "smoke_six", "perception_gallery", "pause_and_drone_faults"), help="Packaged example, works outside the checkout")


def scenario_path(args):
    if args.scenario:
        return Path(args.scenario)
    return Path(str(files("maicon_sim") / "resources" / "examples" / f"scenario_{args.example}.yaml"))


def doctor(backend):
    import numpy as np
    from fastapi import FastAPI
    from pydantic import BaseModel
    from maicon_sim.config.loader import load_scenario
    class Spike(BaseModel):
        ready: bool
    assert Spike(ready=True).ready and FastAPI().openapi()["openapi"]
    load_scenario(Path(str(files("maicon_sim") / "resources/examples/scenario_smoke_six.yaml")), backend="2d")
    checks = ["numpy_pydantic_fastapi", "packaged_schema_examples"]
    packages = ["numpy", "pydantic", "fastapi", "Pillow"]
    if backend == "3d":
        import pybullet as pb
        for _ in range(10):
            cid = pb.connect(pb.DIRECT)
            try:
                visual = pb.createVisualShape(pb.GEOM_BOX, halfExtents=[.2]*3, rgbaColor=[.2,.6,.8,1], physicsClientId=cid)
                pb.createMultiBody(baseMass=0, baseVisualShapeIndex=visual, physicsClientId=cid)
                result = pb.getCameraImage(64, 48, viewMatrix=pb.computeViewMatrix([1,1,1],[0,0,0],[0,0,1]), renderer=pb.ER_TINY_RENDERER, physicsClientId=cid)
                pixels = np.asarray(result[2], dtype=np.uint8).reshape(48, 64, 4)
                assert pixels[:,:,:3].std() > 0
            finally:
                pb.disconnect(cid)
        import cv2
        assert cv2.cvtColor(np.zeros((8,8,3), np.uint8), cv2.COLOR_BGR2GRAY).shape == (8,8)
        checks += ["bullet_direct_10_reopens", "opencv_numpy_abi"]
        packages += ["pybullet", "opencv-python-headless"]
    from maicon_sim.evaluation.metrics import machine
    return {"status": "passed", "backend": backend, "checks": checks, "environment": machine(),
            "versions": {name: importlib.metadata.version(name) for name in packages}}


def execute(args):
    from maicon_sim.evaluation.metrics import write_json
    if args.command == "doctor":
        return doctor(args.backend)
    if args.command == "assets":
        from maicon_sim.backends.bullet.asset_builder import resolve_assets
        resolved = resolve_assets(args.manifest, args.out)
        return {"manifest": str(resolved.manifest_path), "assets": len(resolved.manifest["assets"])}
    if args.command == "agent":
        import asyncio
        from maicon_sim.policies.controller import run_agent
        code = os.environ.get("MAICON_SIM_MISSION_CODE")
        if not code:
            raise ValueError("MAICON_SIM_MISSION_CODE must be supplied in the environment")
        options = {name: value for name, value in (("provider", args.llm_provider), ("endpoint", args.llm_endpoint),
                   ("model", args.llm_model), ("key_env", args.llm_key_env), ("timeout_s", args.llm_timeout_s)) if value is not None}
        return asyncio.run(run_agent(args.server, args.slot, args.policy, code, args.out, llm_options=options,
                                     camera_calibration=args.camera_calibration, vision_stress_seed=args.vision_stress_seed))
    if args.command == "calibrate-camera":
        import glob
        from maicon_sim.perception.calibration import calibrate_camera
        paths = sorted({path for pattern in args.images for path in glob.glob(pattern)})
        return calibrate_camera(paths, (args.board_cols, args.board_rows), args.square_size_m, args.out)
    if args.command == "augment-image":
        from PIL import Image
        import numpy as np
        from maicon_sim.perception.augmentation import augment_image
        target = Path(args.out)
        if target.exists():
            raise ValueError("output already exists; choose a new image path")
        image = np.asarray(Image.open(args.image).convert("RGB"))[..., ::-1].copy()
        result = augment_image(image, args.seed, brightness=args.brightness, blur_sigma=args.blur_sigma, noise_sigma=args.noise_sigma)
        target.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(result[..., ::-1]).save(target)
        return {"image": str(target), "seed": args.seed}
    if args.command == "generate":
        from maicon_sim.evaluation.generate import generate
        if args.count < 1 or args.seed < 0:
            raise ValueError("seed must be nonnegative and count positive")
        return {"scenarios": generate(args.template, args.seed, args.count, args.out, layout_mode=args.layout_mode)}
    if args.command == "compare":
        from maicon_sim.evaluation.compare import compare
        result = compare(args.left, args.right, args.mode)
        if not result["equal"]:
            raise VerificationError(json.dumps(result, ensure_ascii=False))
        return result
    if args.command == "replay":
        from maicon_sim.evaluation.replay import replay_inputs, load_recorded_config, replay_observations
        if args.mode == "observations":
            result = replay_observations(args.run, lambda *_: None)
            write_json(Path(args.out) / "observations_replay.json", result)
            return result
        from maicon_sim.evaluation.runner import run_episode
        checkpoint = Path(args.run) / "private/checkpoints" / f"tick-{args.checkpoint_tick:08d}.json" if args.checkpoint_tick is not None else None
        result, path = run_episode(load_recorded_config(args.run), backend=args.backend, out=args.out, replay_events=replay_inputs(args.run), checkpoint=checkpoint)
        if args.verify:
            from maicon_sim.evaluation.compare import compare
            verification = compare(args.run, path)
            write_json(path / "summary/replay_verification.json", verification)
            if not verification["equal"]:
                raise VerificationError(json.dumps(verification, ensure_ascii=False))
        return {"result": str(path / "result.json"), "verified": args.verify}
    from maicon_sim.config.loader import load_scenario
    config = load_scenario(scenario_path(args), backend=getattr(args, "backend", None))
    if args.command == "dataset":
        from maicon_sim.evaluation.dataset import export_dataset
        return export_dataset(config, args.out)
    if args.command == "validate":
        return {"valid": True, "scenario_id": config.scenario["scenario_id"], "hashes": config.hashes, "warnings": config.warnings}
    if args.command == "serve":
        if args.clock != "realtime":
            raise ValueError("External HTTP participants require realtime clock; accelerated HTTP is unsupported")
        from maicon_sim.evaluation.realtime import serve
        return serve(config, args.backend, args.public_port, args.admin_port, args.out, web_port=args.web_port)
    if args.command == "batch":
        from maicon_sim.evaluation.batch import batch
        try:
            if ":" in args.seeds:
                lo, hi = map(int, args.seeds.split(":"))
                seeds = list(range(lo, hi))
            else:
                seeds = list(map(int, args.seeds.split(",")))
            if not seeds or min(seeds) < 0:
                raise ValueError
        except ValueError:
            raise ValueError("--seeds must be nonnegative start:stop or comma-separated integers")
        summary = batch(config, seeds, args.out, args.backend, args.workers)
        return {"runs": len(summary["runs"]), "mean": summary["mean"], "summary": str(Path(args.out) / "batch_summary.json")}
    from maicon_sim.evaluation.runner import run_episode
    if args.command == "benchmark":
        if args.duration_s <= 0:
            raise ValueError("--duration-s must be positive")
        result, path = run_episode(config, backend=args.backend, out=args.out, duration_s=args.duration_s, camera_count=args.camera_count)
    else:
        result, path = run_episode(config, backend=args.backend, clock=args.clock, out=args.out, headless=not args.viewer,
                                   viewer=args.viewer, record_frames=args.record_frames, resolved_assets=args.resolved_assets,
                                   abort_on_overload=args.abort_on_overload)
    return {"result": str(path / "result.json"), "scores": {s: v["total"] for s, v in result["scores"].items()}, "end_reason": result["end_reason"]}


class VerificationError(RuntimeError):
    pass


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        value = execute(args)
        if value is not None:
            print(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except KeyboardInterrupt:
        return 130
    except VerificationError as exc:
        print(f"Verification failed: {exc}", file=sys.stderr)
        return 4
    except (ValueError, FileNotFoundError) as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        # Do not echo arbitrary external exception strings (URLs may contain codes).
        import traceback
        from maicon_sim.evaluation.metrics import write_json
        diagnostic = Path(getattr(args, "out", None) or "artifacts/diagnostics") / "private/error.json"
        frames = [{"file": f.filename, "line": f.lineno, "function": f.name} for f in traceback.extract_tb(exc.__traceback__)]
        try:
            write_json(diagnostic, {"exception_type": type(exc).__name__, "frames": frames,
                                    "note": "Exception values omitted to avoid credential-bearing URLs or request bodies."})
            print(f"Runtime error ({type(exc).__name__}); diagnostic: {diagnostic}", file=sys.stderr)
        except OSError:
            print(f"Runtime error ({type(exc).__name__}); diagnostic output is not writable", file=sys.stderr)
        return 3
