"""Controller resilience with the real LLMPort, queue/HTTP service and world core."""
import asyncio
import copy
import json
import math
from pathlib import Path
import time

import httpx
import pytest

from maicon_sim.config.loader import load_scenario
from maicon_sim.core.engine import MatchEngine
from maicon_sim.policies.controller import TeamController
from maicon_sim.sdk.http_port import HTTPPort
from maicon_sim.server.app import create_apps
from maicon_sim.server.runtime import EngineRuntime
from maicon_sim.sensors.gateway import SensorGateway

pytestmark = pytest.mark.integration


class DelayedLLM:
    """Actual async LLMPort implementation used by the controller, not planner sleep."""
    mock = True
    def __init__(self, delay_s=5., outcome="valid"):
        self.delay_s, self.outcome = delay_s, outcome
        self.parse_calls = 0
        self.finished = asyncio.Event()
    async def parse_order(self, text, allowed_schema=None, deadline=None):
        self.parse_calls += 1
        try:
            await asyncio.sleep(self.delay_s)
            if self.outcome == "invalid":
                return '{"target": broken-json'
            return {"target": "RED_RADAR", "search_sectors": ["CM", "R-S1"], "base": "RED_SUPPLY_DEPOT"}
        finally:
            self.finished.set()
    async def rank_threat(self, evidence, deadline=None):
        return ["R-1", "R-2", "R-3"]


class ControllerHarness:
    def __init__(self, *, policy="baseline", llm=None, llm_timeout_s=6., output=None):
        self.config = load_scenario(Path(__file__).resolve().parents[2] / "examples/scenario_smoke_six.yaml")
        self.engine = MatchEngine(self.config)
        self.gateway = SensorGateway(self.config)
        self.engine.request("enter_ready")
        self.gateway.update(self.engine)
        self.public, self.admin = create_apps(self.engine, self.gateway)
        self.client = httpx.AsyncClient(base_url="http://participant.test", transport=httpx.ASGITransport(app=self.public))
        self.port = HTTPPort("http://participant.test", "SIMB0001", client=self.client)
        self.controller = TeamController(self.port, "B-1", policy, llm=llm, llm_timeout_s=llm_timeout_s, output=output)
        self.keep_running = True
        self.pump = None

    async def command(self, kind, payload=None):
        return await asyncio.wait_for(asyncio.wrap_future(self.engine.enqueue(kind, payload=payload)), 3.)

    async def operation(self, callback):
        return await asyncio.wait_for(asyncio.wrap_future(self.pump.submit_operation(callback)), 3.)

    async def start(self):
        self.pump = EngineRuntime(self.engine, self.gateway).start()
        await self.controller.initialize()
        await self.command("start")
        self.controller.start()
        return self

    async def close(self):
        await self.controller.close()
        self.keep_running = False
        if self.pump:
            self.pump.close()
        await self.public.state.service.close()
        await self.client.aclose()
        self.gateway.close()


class PublicControllerFixturePort:
    """Stamped public sensor fixture; isolates controller/LLM scheduling from rendering.

    This is not a socket test. Real HTTP, six-process concurrency and physical
    sensors are covered separately; no speed or world-physics claim is made here.
    """
    def __init__(self):
        self.started = time.monotonic()
        self.commands = []
        self.reports = {}
        self.target_waiters = 0
        self.target_event = asyncio.Event()
    async def session(self):
        return {"slot": "B-1", "camp": "BLUE", "match_id": "controller-llm-0001", "episode_index": 1,
                "capabilities": {"rgb": False, "semantic": True, "lidar": True, "depth": False}}
    async def map_prior(self):
        return {"bounds": {"width_m": 3., "height_m": 3.}, "bases": [], "sectors": [],
                "nominal_starts": [{"slot": "B-1", "pose": {"x_m": .4, "y_m": 1.5, "yaw_rad": 0.}}]}
    async def calibration(self):
        return {"front_camera": {"fx_px": 320., "cx_px": 319.5}}
    async def get_me(self):
        return {"slot": "B-1", "camp": "BLUE", "phase": "running", "ready": True}
    async def ready(self):
        return {"accepted": True}
    async def await_order(self, wait_s=120):
        return {"accepted": True, "order": {"tactical_command": "상대 레이더시설을 타격하고 첫째 탐색구역과 중앙을 정찰하며 상대 군수보급소를 후속 거점으로 설정하라."}}
    async def await_target(self, wait_s=120):
        self.target_waiters += 1
        try:
            await asyncio.wait_for(self.target_event.wait(), wait_s)
            return {"accepted": False, "reason": "not published"}
        finally:
            self.target_waiters -= 1
    async def latest_observations(self):
        tick = int((time.monotonic() - self.started) * 100)
        stamp = {"sequence": tick, "captured_tick": tick, "received_tick": tick}
        return {"state": {**stamp, "hp": 4, "hp_max": 4, "battery_pct": 100.},
                "match": {**stamp, "mode": "mission", "cmd": "start"},
                "odom": {**stamp, "local_pose": {"x_m": 0., "y_m": 0., "yaw_rad": 0.}},
                "semantic": {**stamp, "detections": []},
                "scan": {**stamp, "ranges_m": [.1] * 36, "angle_min_rad": -math.pi,
                         "angle_increment_rad": 2 * math.pi / 36, "range_max_m": 8.}}
    async def command_velocity(self, v, w):
        self.commands.append((time.monotonic(), v, w))
        return {"accepted": True}
    async def command_gimbal(self, *args):
        return {"message": "ok"}
    async def submit_m1(self, value):
        self.reports["m1"] = value
        return {"accepted": True, "received": value}
    async def submit_m3(self, value):
        self.reports["m3"] = value
        return {"accepted": True, "received": value}
    async def submit_m6(self, value):
        self.reports["m6"] = value
        return {"accepted": True, "received": value}
    async def close(self):
        pass


@pytest.mark.parametrize("outcome,timeout_s", [("valid", 6.), ("invalid", 6.), ("timeout", 5.)])
def test_E2E_008_009_actual_llm_delay_invalid_timeout_and_longpoll_preserve_control(outcome, timeout_s, tmp_path):
    async def run():
        llm = DelayedLLM(6. if outcome == "timeout" else 5., outcome)
        port = PublicControllerFixturePort()
        controller = TeamController(port, "B-1", llm=llm, llm_timeout_s=timeout_s, output=tmp_path)
        await controller.initialize()
        controller.start()
        try:
            # The actual LLMPort call waits five wall seconds while target wait120
            # remains pending. This measures controller concurrency in isolation.
            start = time.monotonic()
            while not llm.finished.is_set() and time.monotonic() - start < 7.:
                await asyncio.sleep(.05)
            await asyncio.sleep(.3)
            assert llm.parse_calls == 1
            assert time.monotonic() - start >= 5.
            assert len(controller.control_times) >= 40
            gaps = [b - a for a, b in zip(controller.control_times, controller.control_times[1:])]
            assert max(gaps, default=0.) < .5
            assert port.target_waiters == 1
            assert not controller.done.is_set()
            if outcome == "valid":
                for _ in range(20):
                    if port.reports.get("m1") is not None:
                        break
                    await asyncio.sleep(.05)
                assert port.reports["m1"]["target"] == "RED_RADAR"
                assert controller.llm_completed == 1
            else:
                assert any(e["source"] == "llm_interpretation" for e in controller.errors)
                assert port.reports.get("m1") is None
                assert controller.llm_completed == 0
        finally:
            await controller.close()
        assert port.target_waiters == 0
    asyncio.run(run())


def test_E2E_012_hp_zero_device_lock_does_not_prevent_m6(tmp_path):
    async def run():
        h = ControllerHarness(output=tmp_path)
        await h.start()
        try:
            # Evaluator-only construction of a legitimate HP0 physical-lock state.
            def inject_hit():
                h.engine.robots["B-1"].hp = 1
                h.engine.apply_hit("B-1")
            await h.operation(inject_hit)
            assert h.engine.robots["B-1"].hp == 0
            assert h.engine.robots["B-1"].drive_locked_until > h.engine.robot_effect_ticks
            await h.command("finish")
            await asyncio.wait_for(h.controller.done.wait(), 3.)
            assert h.engine.phase == "finished"
            assert h.engine.reports["B-1"]["m6"] is not None
            assert h.engine.robots["B-1"].hp == 0
            assert h.controller.report_workers["m6"].acknowledged_revision is not None
        finally:
            await h.close()
    asyncio.run(run())


def test_E2E_006_restart_same_match_preserves_committed_report(tmp_path):
    async def run():
        h = ControllerHarness(output=tmp_path / "first")
        await h.start()
        try:
            for _ in range(50):
                if h.engine.reports["B-1"]["m1"] is not None:
                    break
                await asyncio.sleep(.05)
            stored = copy.deepcopy(h.engine.reports["B-1"]["m1"])
            match_id = h.engine.match_id
            await h.controller.close()
            new_client = httpx.AsyncClient(base_url="http://participant.test", transport=httpx.ASGITransport(app=h.public))
            new_port = HTTPPort("http://participant.test", "SIMB0001", client=new_client)
            h.controller = TeamController(new_port, "B-1", output=tmp_path / "restarted")
            await h.controller.initialize()
            assert h.controller.session_identity["match_id"] == match_id
            assert h.engine.robots["B-1"].ready
            assert h.engine.reports["B-1"]["m1"] == stored
            h.controller.start()
            await asyncio.sleep(.3)
            await h.command("finish")
            await asyncio.wait_for(h.controller.done.wait(), 3.)
            await new_client.aclose()
        finally:
            await h.close()
    asyncio.run(run())


def test_E2E_007_reset_reused_code_new_camp_clears_policy_evidence(tmp_path):
    async def run():
        h = ControllerHarness(output=tmp_path)
        await h.start()
        try:
            old_match = h.engine.match_id
            h.controller.policy.tracker.observe((1., 2.), 0., {"tank": 1.}, 10, "R-S1")
            h.controller.policy.sent_m6 = True
            h.controller.policy.ranking_override = ["R-3", "R-2", "R-1"]
            # Move an existing authenticated team to the opposite slot for the next
            # match, preserving valid 6-slot configuration and unique mission codes.
            next_config = copy.deepcopy(h.config)
            agents = next_config.scenario["agents"]
            blue = next(a for a in agents if a["slot"] == "B-1")
            red = next(a for a in agents if a["slot"] == "R-3")
            blue["mission_code"], red["mission_code"] = red["mission_code"], blue["mission_code"]
            await h.command("reset", payload={"config": next_config})
            await h.command("enter_ready")
            for _ in range(60):
                if h.controller.session_identity.get("match_id") != old_match:
                    break
                await asyncio.sleep(.05)
            assert h.controller.session_identity["match_id"] != old_match
            assert h.controller.slot == "R-3"
            assert h.controller.policy.camp == "RED"
            assert not h.controller.policy.tracker.tracks
            assert h.controller.policy.ranking_override is None
            assert not h.controller.policy.sent_m6
            assert h.controller.order == {} and h.controller.target == {}
            assert h.controller.policy.start == pytest.approx((5.72, .8, math.pi))
            assert h.controller.report_workers["m1"].latest is None
        finally:
            await h.close()
    asyncio.run(run())



def test_PERF_005_virtual_10fps_input_2fps_inference_exact_drop_accounting():
    """5-second source timeline, 2Hz completions, latest queue1; no wall sleeps."""
    import queue
    import threading
    from maicon_sim.policies.inference import LatestInference
    entered = queue.Queue()
    completion = threading.Semaphore(0)
    def callback(frame):
        entered.put(frame["sequence"])
        assert completion.acquire(timeout=3.)
        return frame
    worker = LatestInference(callback)
    try:
        worker.submit({"sequence": 0, "captured_tick": 0})
        assert entered.get(timeout=3.) == 0
        previous = 0
        # Each source index is 0.1s. A completion is allowed every0.5s;
        # source frame0 and the final queue drain follow the same convention.
        for boundary in range(5, 51, 5):
            for index in range(previous + 1, boundary):
                worker.submit({"sequence": index, "captured_tick": index * 10})
                assert worker.queue.qsize() <= 1
            completion.release()
            assert entered.get(timeout=3.) == boundary - 1
            previous = boundary - 1
        completion.release()  # final frame49 completes at virtual5.5s
        worker.close()
        stats = worker.stats()
        assert stats == {"submitted": 50, "processed": 11, "dropped": 39,
                         "errors": 0, "in_flight": 0, "pending": 0,
                         "max_queue_size": 1}
        assert worker.latest["sequence"] == 49
        assert worker.latest["captured_tick"] == 490
        assert stats["submitted"] == sum(stats[k] for k in ("processed", "dropped", "errors", "in_flight", "pending"))
    finally:
        completion.release()
        worker.close()


def test_PERF_005_wall_10hz_source_2hz_callback_queue_and_accounting(tmp_path):
    """Measured public-frame backlog profile; OS overload can reduce both rates."""
    from maicon_sim.policies.inference import LatestInference
    callback_starts = []
    def callback(frame):
        callback_starts.append(time.monotonic())
        time.sleep(.5)
        return frame
    worker = LatestInference(callback)
    started = time.monotonic()
    source_times = []
    try:
        for sequence in range(50):
            source_times.append(time.monotonic())
            worker.submit({'sequence': sequence, 'captured_tick': sequence * 10})
            assert worker.queue.qsize() <= 1
            time.sleep(.1)
        deadline = time.monotonic() + 3.
        while (worker.latest is None or worker.latest['sequence'] != 49) and time.monotonic() < deadline:
            time.sleep(.01)
        worker.close()
        metrics = worker.stats()
        assert worker.latest['sequence'] == 49
        assert worker.latest['captured_tick'] == 490
        assert metrics['max_queue_size'] == 1
        assert metrics['submitted'] == 50
        assert metrics['processed'] >= 2 and metrics['dropped'] > 0
        assert metrics['submitted'] == sum(metrics[k] for k in ('processed', 'errors', 'dropped', 'pending', 'in_flight'))
        assert metrics['pending'] == 0 and metrics['in_flight'] == 0
        assert all(b - a >= .5 for a, b in zip(callback_starts, callback_starts[1:]))
        assert all(b - a >= .1 for a, b in zip(source_times, source_times[1:]))
        metrics.update({'requested_source_hz': 10., 'callback_processing_s': .5,
                        'wall_s': time.monotonic() - started,
                        'source_interval_s': [b - a for a, b in zip(source_times, source_times[1:])],
                        'callback_interval_s': [b - a for a, b in zip(callback_starts, callback_starts[1:])]})
        (tmp_path / 'inference_backlog_metrics.json').write_text(json.dumps(metrics, indent=2))
    finally:
        worker.close()


@pytest.mark.render
def test_ready_RGB_model_offloop_and_required_frames_precede_ready(monkeypatch):
    import threading
    import numpy as np
    from maicon_sim.perception import combat
    initialized = threading.Event()
    main_thread = threading.get_ident()
    class Detector:
        def __init__(self, calibration=None, *, robot_only=False):
            assert threading.get_ident() != main_thread
            initialized.set()
        def process(self, frame):
            return {"detections": []}
    monkeypatch.setattr(combat, 'CombatVisionDetector', Detector)
    class RGBPort(PublicControllerFixturePort):
        def __init__(self):
            super().__init__()
            self.observation_calls = 0
            self.ready_count = 0
        async def session(self):
            result = await super().session()
            result['capabilities'] = {'rgb': True, 'semantic': False, 'lidar': True, 'depth': False}
            return result
        async def get_me(self):
            return {'slot': 'B-1', 'camp': 'BLUE', 'phase': 'ready', 'ready': False}
        async def latest_observations(self):
            self.observation_calls += 1
            value = await super().latest_observations()
            if self.observation_calls < 3:
                value.pop('scan')
                return value
            value['rgb'] = {'data': np.full((480, 640, 3), 127, dtype=np.uint8),
                            'sequence': 1, 'captured_tick': 0, 'received_tick': 0}
            return value
        async def ready(self):
            assert initialized.is_set()
            assert self.observation_calls >= 3
            self.ready_count += 1
            return {'accepted': True}
    async def run():
        port = RGBPort()
        controller = TeamController(port, 'B-1', required_sensor_timeout_s=1.)
        try:
            await controller.initialize()
            assert port.ready_count == 1
            assert controller._sensors_ready
            assert controller.inference is not None
            assert controller.observations['rgb']['data'].shape == (480, 640, 3)
        finally:
            await controller.close()
    asyncio.run(run())


def test_ready_missing_required_sensor_times_out_without_POST_ready():
    class MissingScanPort(PublicControllerFixturePort):
        ready_count = 0
        async def get_me(self):
            return {'slot': 'B-1', 'camp': 'BLUE', 'phase': 'ready', 'ready': False}
        async def latest_observations(self):
            result = await super().latest_observations()
            result.pop('scan')
            return result
        async def ready(self):
            self.ready_count += 1
            return {'accepted': True}
    async def run():
        port = MissingScanPort()
        controller = TeamController(port, 'B-1', 'idle', required_sensor_timeout_s=.1)
        try:
            with pytest.raises(RuntimeError, match='required participant sensor frames unavailable: scan'):
                await controller.initialize()
            assert port.ready_count == 0
            assert not controller._sensors_ready
        finally:
            await controller.close()
    asyncio.run(run())


def test_reset_discards_inflight_old_order_and_observation_responses():
    class DelayedPort(PublicControllerFixturePort):
        def __init__(self):
            super().__init__()
            self.generation = 1
            self.order_started = asyncio.Event()
            self.release_order = asyncio.Event()
            self.second_order_started = asyncio.Event()
            self.release_new_order = asyncio.Event()
            self.old_scan_started = asyncio.Event()
            self.release_scan = asyncio.Event()
            self.new_scan_blocked = asyncio.Event()
            self.release_new_scan = asyncio.Event()
            self.order_calls = 0
            self.delay_scan_once = False
            self.hold_after_old = False
        async def session(self):
            value = await super().session()
            value['match_id'] = f'fixture-{self.generation}'
            return value
        async def await_order(self, wait_s=120):
            self.order_calls += 1
            if self.order_calls == 1:
                self.order_started.set()
                await self.release_order.wait()
                return {'accepted': True, 'order': {'tactical_command': 'old session order'}}
            self.second_order_started.set()
            await self.release_new_order.wait()
            return {'accepted': True, 'order': {'tactical_command': 'new session order'}}
        async def latest_observations(self):
            value = await super().latest_observations()
            value['state']['hp'] = 4 if self.generation == 1 else 3
            if self.delay_scan_once:
                self.delay_scan_once = False
                self.old_scan_started.set()
                await self.release_scan.wait()
                return value
            if self.hold_after_old:
                self.new_scan_blocked.set()
                await self.release_new_scan.wait()
            return value
    async def run():
        port = DelayedPort()
        controller = TeamController(port, 'B-1')
        await controller.initialize()
        port.delay_scan_once = True
        order_task = asyncio.create_task(controller._await_mission('order'))
        sensor_task = asyncio.create_task(controller._poll_observations())
        controller.tasks = [order_task, sensor_task]
        try:
            await asyncio.wait_for(port.order_started.wait(), 1.)
            await asyncio.wait_for(port.old_scan_started.wait(), 1.)
            port.generation = 2
            await controller._initialize_session(await port.session())
            assert controller.observations['state']['hp'] == 3
            port.hold_after_old = True
            port.release_scan.set()
            port.release_order.set()
            await asyncio.wait_for(port.second_order_started.wait(), 1.)
            await asyncio.wait_for(port.new_scan_blocked.wait(), 1.)
            assert controller.order == {}
            assert controller.observations['state']['hp'] == 3
            assert controller.session_identity['match_id'] == 'fixture-2'
            port.release_new_order.set()
            await asyncio.sleep(.01)
            assert controller.order['order']['tactical_command'] == 'new session order'
        finally:
            await controller.close()
    asyncio.run(run())
