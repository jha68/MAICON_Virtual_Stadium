"""Real HTTP and isolated participant subprocess coordination."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
import secrets
import signal
import socket
import subprocess
import sys
import threading
import time

import uvicorn

from maicon_sim.core.engine import MatchEngine
from maicon_sim.config.loader import validate_schema
from maicon_sim.sensors.gateway import SensorGateway
from maicon_sim.server.app import create_apps
from maicon_sim.server.runtime import EngineRuntime
from .metrics import machine, write_json, file_hash
from .recorder import Recorder


class LocalServers:
    """Bound sockets avoid race-prone ephemeral-port discovery."""
    def __init__(self, public, admin, public_port=0, admin_port=0, extra=()):
        self.apps = (public, admin, *(app for app, _ in extra))
        self.ports = []
        self.servers = []
        self.threads = []
        self.sockets = []
        for app, port in zip(self.apps, (public_port, admin_port, *(port for _, port in extra))):
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("127.0.0.1", port))
            sock.listen(128)
            self.sockets.append(sock)
            self.ports.append(sock.getsockname()[1])
            server = uvicorn.Server(uvicorn.Config(app, log_level="error", access_log=False,
                                                 timeout_graceful_shutdown=2, lifespan="off"))
            self.servers.append(server)
            self.threads.append(threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True))

    def start(self):
        for thread in self.threads:
            thread.start()
        deadline = time.monotonic()+10
        while not all(s.started for s in self.servers):
            if time.monotonic() >= deadline or not all(t.is_alive() for t in self.threads):
                raise RuntimeError("local API server did not start")
            time.sleep(.01)
        return self

    @property
    def public_url(self):
        return f"http://127.0.0.1:{self.ports[0]}"

    @property
    def admin_url(self):
        return f"http://127.0.0.1:{self.ports[1]}"

    def close(self):
        service = getattr(self.apps[0].state, "service", None)
        if service and hasattr(service, "close_threadsafe"):
            service.close_threadsafe()
        for server in self.servers:
            server.should_exit = True
        for thread in self.threads:
            thread.join(timeout=5)
        for sock in self.sockets:
            sock.close()

    def __enter__(self):
        return self.start()

    def __exit__(self, *_):
        self.close()


class ParticipantProcesses:
    """Each child gets one credential/public directory, with at most three restarts."""
    def __init__(self, config, server, root, engine):
        self.config, self.server, self.root, self.engine = config, server, Path(root).resolve(), engine
        self.children = {}
        self.logs = {}
        self.restarts = {}
        self.failures = []
        self.pids = {}

    def launch(self, agent):
        slot = agent["slot"]
        directory = self.root / "public" / slot
        directory.mkdir(parents=True, exist_ok=True)
        if slot not in self.logs:
            self.logs[slot] = (directory / "process.log").open("ab")
        # Do not inherit admin tokens, truth paths, provider credentials or parent cwd.
        env = {"PATH": os.environ.get("PATH", ""), "LANG": "C.UTF-8", "PYTHONUNBUFFERED": "1",
               "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1",
               "MAICON_SIM_MISSION_CODE": agent["mission_code"]}
        # Forward only opt-in camera configuration; unrelated parent secrets
        # and evaluator bindings remain outside participant processes.
        if os.environ.get("MAICON_CAMERA_CALIBRATION"):
            env["MAICON_CAMERA_CALIBRATION"] = str(Path(os.environ["MAICON_CAMERA_CALIBRATION"]).resolve())
        args = [sys.executable, "-m", "maicon_sim", "agent", "--slot", slot,
                "--server", self.server, "--out", "."]
        child = subprocess.Popen(args, cwd=directory, env=env, stdout=self.logs[slot], stderr=self.logs[slot])
        self.children[slot] = child
        self.pids.setdefault(slot, []).append(child.pid)

    def start(self):
        for agent in self.config.scenario["agents"]:
            self.restarts[agent["slot"]] = 0
            self.launch(agent)

    def check(self):
        for agent in self.config.scenario["agents"]:
            slot = agent["slot"]
            status = self.children[slot].poll()
            if status is not None and status != 0 and self.engine.phase != "finished":
                if self.restarts[slot] < 3:
                    self.restarts[slot] += 1
                    self.launch(agent)
                elif not any(f["slot"] == slot for f in self.failures):
                    self.failures.append({"slot": slot, "exit_code": status, "restarts": 3})

    def close(self):
        # Give finished-state polling children time to flush their own public logs.
        deadline = time.monotonic()+3
        for child in self.children.values():
            if child.poll() is None:
                try:
                    child.wait(timeout=max(.01, deadline-time.monotonic()))
                except subprocess.TimeoutExpired:
                    child.terminate()
        for child in self.children.values():
            if child.poll() is None:
                try:
                    child.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=2)
        for stream in self.logs.values():
            stream.close()


def start_scene(config, backend, root, headless, resolved_assets=None):
    from .runner import build_backend
    if backend == "3d":
        from maicon_sim.backends.bullet.asset_builder import resolve_assets, load_resolved_assets
        from maicon_sim.backends.bullet.render_worker import AsyncBulletBackend
        assets = load_resolved_assets(resolved_assets, config.assets) if resolved_assets else resolve_assets(config.assets, Path(root) / "private/assets", base_dir=config.path.parent)
        return AsyncBulletBackend(config, assets, headless=headless), assets
    return build_backend(config, backend, root, headless, resolved_assets)


def run_realtime(config, *, backend="2d", out=None, headless=True, viewer=False,
                 record_frames=False, resolved_assets=None, abort_on_overload=False):
    from .runner import public_observations, make_result
    import uuid
    run_id = f"{config.scenario['scenario_id']}-{uuid.uuid4().hex[:10]}"
    root = Path(out or Path("artifacts/runs") / run_id).resolve()
    recorder = Recorder(root, config, run_id, backend, "realtime", record_frames)
    scene = runtime = servers = children = None
    window = None
    started = time.monotonic()
    try:
        scene, assets = start_scene(config, backend, root, headless, resolved_assets)
        engine = MatchEngine(config, event_sink=recorder.event, retain_journal=False)
        gateway = SensorGateway(config, scene)
        token = secrets.token_urlsafe(32)
        public, admin = create_apps(engine, gateway, token)
        def observe(e):
            if e.sim_tick % 10 == 0:
                for slot in e.robots:
                    public_observations(gateway, slot, recorder)
        runtime = EngineRuntime(engine, gateway, on_tick=observe).start()
        servers = LocalServers(public, admin).start()
        engine.enqueue("enter_ready").result(timeout=10)
        children = ParticipantProcesses(config, servers.public_url, root, engine)
        children.start()
        ready_deadline = time.monotonic()+10
        while time.monotonic() < ready_deadline:
            if runtime.failure:
                raise runtime.failure
            if all(r.ready for r in engine.robots.values()):
                break
            children.check()
            time.sleep(.02)
        engine.enqueue("start").result(timeout=10)
        if viewer:
            from maicon_sim.viewer.pygame_viewer import PygameViewer
            window = PygameViewer(config, clock_mode="realtime", gateway=gateway)
        while engine.phase != "finished":
            if runtime.failure:
                raise runtime.failure
            if engine.sim_tick * 10 >= config.scenario["max_sim_ms"]:
                write_json(root / "private/last_snapshot.json", engine.snapshot())
                raise RuntimeError("max_sim_ms reached")
            if abort_on_overload and runtime.overloaded:
                raise RuntimeError("realtime rendering profile overloaded")
            children.check()
            if window:
                window.draw(engine.snapshot())
                for action in window.poll():
                    if action.get("kind") in ("match_pause", "match_resume"):
                        engine.enqueue("pause" if action["kind"] == "match_pause" else "resume")
                    elif action.get("kind") == "debug_pause":
                        if action["paused"]:
                            runtime.debug_paused.set()
                        else:
                            runtime.debug_paused.clear()
                    elif action.get("kind") == "step":
                        runtime.step_once()
                    elif action.get("kind") == "close":
                        window.close()
                        window = None
                        break
            time.sleep(.02)
        children.close()
        runtime.close()
        result = make_result(engine, config, run_id, backend, "realtime", time.monotonic()-started, gateway)
        result["asset_manifest_hash"] = file_hash(assets.manifest_path)
        validate_schema(result, "run_result", "result.json")
        metrics = {**runtime.metrics, "environment": machine(), "participants": children.pids,
                   "restarts": children.restarts, "participant_failures": children.failures,
                   "http": public.state.service.http_metrics, "ingress_queue_peak": engine.queue_peak,
                   "ticks_skipped": 0, "backend": backend}
        recorder.finish(result, metrics, gateway.capabilities, {"asset_manifest_hash": result["asset_manifest_hash"]})
        if result["end_reason"] == "no_eligible":
            raise RuntimeError("no participant became ready")
        return result, root
    finally:
        if runtime:
            runtime.close()
        if children:
            children.close()
        if servers:
            servers.close()
        if window:
            window.close()
        if scene:
            scene.close()
        recorder.close()


def serve(config, backend, public_port, admin_port, out, web_port=None):
    password = None
    if web_port is not None:
        password_file = os.environ.get('MAICON_WEB_PASSWORD_FILE')
        if not password_file:
            raise ValueError('MAICON_WEB_PASSWORD_FILE is required for the operator dashboard')
        password = Path(password_file).read_text().strip()
        if len(password) < 10:
            raise ValueError('Dashboard password must contain at least 10 characters')
    root = Path(out).resolve()
    root.mkdir(parents=True, exist_ok=True)
    scene, assets = start_scene(config, backend, root, True)
    engine = MatchEngine(config, retain_journal=web_port is None)
    gateway = SensorGateway(config, scene)
    token = secrets.token_urlsafe(32)
    token_path = root / "private" / "admin.token"
    token_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(token_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(token)
    public, admin = create_apps(engine, gateway, token)
    manager = None
    extra = ()
    if web_port is not None:
        from maicon_sim.server.web import DashboardManager, create_dashboard
        manager = DashboardManager(public.state.service, root)
        extra = ((create_dashboard(manager, password), web_port),)
    runtime = EngineRuntime(engine, gateway, on_tick=manager.on_tick if manager else None)
    previous_term = None
    if threading.current_thread() is threading.main_thread():
        previous_term = signal.signal(signal.SIGTERM, lambda *_: setattr(public.state.service, 'shutdown_requested', True))
    try:
        with runtime, LocalServers(public, admin, public_port, admin_port, extra=extra) as servers:
            if manager:
                manager.public_url = servers.public_url
            print(f"Realtime APIs active. Supervisor credential file: {token_path}", flush=True)
            while not public.state.service.shutdown_requested:
                if runtime.failure:
                    raise runtime.failure
                if manager:
                    manager.maintain()
                time.sleep(.05)
    finally:
        if previous_term is not None:
            signal.signal(signal.SIGTERM, previous_term)
        if manager:
            manager.close()
        runtime.close()
        if scene:
            scene.close()
    return {"stopped": True}
