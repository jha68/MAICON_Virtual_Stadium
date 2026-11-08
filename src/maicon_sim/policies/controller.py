"""Concurrent participant lifecycle: polling/inference/reporting never own drive timing."""
from __future__ import annotations

import asyncio
from importlib import resources
import json
from pathlib import Path
import time

from .baseline import ParticipantPolicy, PolicyDecision
from .inference import LatestInference


class TeamController:
    def __init__(self, port, slot: str, policy: str = "baseline", *, output=None, llm=None, llm_timeout_s=5., allow_fixture_fallback=False, required_sensor_timeout_s=5.):
        self.port, self.slot, self.policy_name = port, slot, policy
        self.output = Path(output) if output else None
        self.policy = None
        self._configured_llm = llm
        self.llm = llm
        self.llm_timeout_s = llm_timeout_s
        self.allow_fixture_fallback = allow_fixture_fallback
        self.required_sensor_timeout_s = required_sensor_timeout_s
        self._sensors_ready = False
        self.llm_calls = 0
        self.llm_completed = 0
        self.observations, self.me, self.order, self.target = {}, {}, {}, {}
        self.session_identity = {}
        self.decision = PolicyDecision()
        self.tasks = []
        self.report_workers = {}
        self.inference = None
        self.done = asyncio.Event()
        self.closed = False
        self.errors = []
        self.control_times = []
        self._last_rgb_sequence = None
        self._generation = 0
        self._planner_job = None
        self._last_session_check = 0.
        self._transcript = None
        self._last_transcript_sequence = None

    def _error(self, source, error):
        # Exceptions may contain URLs with mission_code; only safe categories persist.
        self.errors.append({"source": source, "kind": type(error).__name__, "status": getattr(error, "status", None)})
        self.errors[:] = self.errors[-100:]

    async def _initialize_session(self, identity):
        self._sensors_ready = False
        from maicon_sim.sdk.report_worker import ReportWorker
        public_map, calibration = await asyncio.gather(self.port.map_prior(), self.port.calibration())
        for worker in self.report_workers.values():
            await worker.close()
        if self.inference:
            self.inference.close()
            self.inference = None
        self._generation += 1
        self.slot = identity["slot"]
        self.policy = ParticipantPolicy(public_map, calibration, self.slot, self.policy_name)
        self.policy.use_inline_fixture = False
        from maicon_sim.sdk.llm import FixtureLLM
        self.llm = self._configured_llm or FixtureLLM(identity.get("camp", self.policy.camp))
        self.policy.llm_provider = getattr(self.llm, "model_name", type(self.llm).__name__)
        self.policy.llm_mock = bool(getattr(self.llm, "mock", False))
        self.session_identity = identity
        self.observations, self.order, self.target = {}, {}, {}
        self.decision = PolicyDecision()
        self._last_rgb_sequence = None
        self.report_workers = {kind: ReportWorker(self.port, kind).start() for kind in ("m1", "m3", "m6")}
        if identity.get("capabilities", {}).get("rgb") and self.policy_name == "baseline":
            def initialize_detector():
                from maicon_sim.perception.synthetic_template import SyntheticTemplateDetector
                return SyntheticTemplateDetector()
            detector = await asyncio.to_thread(initialize_detector)
            self.inference = LatestInference(detector.process)
        await self._acquire_required_observations()

    def _missing_required_observations(self, observations):
        missing = []
        state = observations.get("state")
        if not isinstance(state, dict) or not all(k in state for k in ("hp", "hp_max", "battery_pct")):
            missing.append("state")
        odom = observations.get("odom")
        local = odom.get("local_pose") if isinstance(odom, dict) else None
        if not isinstance(local, dict) or not all(k in local for k in ("x_m", "y_m", "yaw_rad")):
            missing.append("odom")
        scan = observations.get("scan")
        if not isinstance(scan, dict) or not isinstance(scan.get("ranges_m"), (list, tuple)) or not scan["ranges_m"]:
            missing.append("scan")
        if self.policy_name == "baseline" and self.session_identity.get("capabilities", {}).get("rgb"):
            rgb = observations.get("rgb")
            pixels = rgb.get("data") if isinstance(rgb, dict) else None
            intrinsics = self.policy.calibration.get("front_camera", {})
            expected = (intrinsics.get("height_px", 480), intrinsics.get("width_px", 640), 3)
            if pixels is None or getattr(pixels, "shape", None) != expected or str(getattr(pixels, "dtype", "")) != "uint8":
                missing.append("rgb")
        return missing

    async def _acquire_required_observations(self):
        deadline = time.monotonic() + self.required_sensor_timeout_s
        missing = ["state", "odom", "scan"]
        while not self.closed:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError("required participant sensor frames unavailable: " + ", ".join(missing))
            try:
                observations = await asyncio.wait_for(self.port.latest_observations(), remaining)
            except asyncio.TimeoutError:
                raise RuntimeError("required participant sensor frames unavailable: " + ", ".join(missing)) from None
            missing = self._missing_required_observations(observations)
            if not missing:
                self.observations = observations
                self._sensors_ready = True
                return
            await asyncio.sleep(min(.05, max(0., deadline - time.monotonic())))
        raise RuntimeError("participant closed during sensor initialization")

    async def initialize(self):
        identity = await self.port.session()
        if identity.get("slot") != self.slot:
            raise ValueError("participant session slot does not match assigned slot")
        await self._initialize_session(identity)
        self.me = await self.port.get_me()
        if self.output:
            self.output.mkdir(parents=True, exist_ok=True)
            self._transcript = (self.output / "participant.jsonl").open("a", encoding="utf-8")
        if self.me.get("phase") == "ready" and not self.me.get("ready"):
            result = await self.port.ready()
            if not result.get("accepted"):
                raise RuntimeError("server did not accept ready")
        return self

    async def _poll_state(self):
        while not self.closed and not self.done.is_set():
            try:
                # Handshake deliberately precedes guarded requests: after reset
                # an old session header must not prevent discovering the new ID.
                if time.monotonic() - self._last_session_check >= 1.:
                    identity = await self.port.session()
                    self._last_session_check = time.monotonic()
                    if identity.get("match_id") != self.session_identity.get("match_id"):
                        await self._initialize_session(identity)
                self.me = await self.port.get_me()
                if self.me.get("phase") == "finished":
                    self.decision = PolicyDecision()
                    self.done.set()
                    return
                if self.me.get("phase") != "running":
                    self.decision = PolicyDecision()
            except Exception as error:
                self._error("state", error)
                self.decision = PolicyDecision()
                if getattr(error, "status", None) == 401:
                    self.done.set()
            await asyncio.sleep(.1)

    async def _ready(self):
        while not self.closed and not self.done.is_set():
            try:
                if self._sensors_ready and self.me.get("phase") == "ready" and not self.me.get("ready"):
                    await self.port.ready()
            except Exception as error:
                self._error("ready", error)
            await asyncio.sleep(2.)

    async def _poll_observations(self):
        while not self.closed and not self.done.is_set():
            try:
                generation = self._generation
                observations = await self.port.latest_observations()
                if generation != self._generation:
                    continue
                rgb = observations.get("rgb")
                if self.inference and rgb:
                    sequence = rgb.get("sequence", rgb.get("captured_tick"))
                    if sequence != self._last_rgb_sequence:
                        public_frame = dict(rgb)
                        public_frame.setdefault("camera_id", self.slot + "/front")
                        public_frame.setdefault("width_px", rgb["data"].shape[1])
                        public_frame.setdefault("height_px", rgb["data"].shape[0])
                        self.inference.submit(public_frame)
                        self._last_rgb_sequence = sequence
                    if self.inference.latest is not None:
                        observations["semantic"] = self.inference.latest
                    # RGB remains in the observation cache for caller recording;
                    # planning consumes the independent worker's detections only.
                    observations = dict(observations)
                    observations.pop("rgb", None)
                self.observations = observations
            except Exception as error:
                self._error("observations", error)
            await asyncio.sleep(.08)

    async def _await_mission(self, kind):
        while not self.closed and not self.done.is_set():
            try:
                generation = self._generation
                response = await getattr(self.port, "await_" + kind)(wait_s=120)
                if generation != self._generation:
                    continue
                if response.get("accepted"):
                    setattr(self, kind, response)
                    while generation == self._generation and not self.closed and not self.done.is_set():
                        await asyncio.sleep(.1)
                else:
                    await asyncio.sleep(.2)
            except Exception as error:
                self._error(kind, error)
                await asyncio.sleep(.2)

    @staticmethod
    def _interpretation_schema():
        # LLMs receive the report shape, never authentication or hidden answers.
        schema = json.loads(resources.files("maicon_sim.resources").joinpath("schemas/m1.normalized.schema.json").read_text())
        schema["properties"].pop("mission_code", None)
        schema["required"] = []
        return schema

    @staticmethod
    def _validate_interpretation(value):
        from jsonschema import Draft202012Validator
        schema = TeamController._interpretation_schema()
        if not isinstance(value, dict):
            raise ValueError("LLM interpretation must be a JSON object")
        normalized = dict(value)
        for name in ("target", "base"):
            if isinstance(normalized.get(name), str):
                normalized[name] = normalized[name].upper()
        if isinstance(normalized.get("search_sectors"), list):
            normalized["search_sectors"] = [v.upper() if isinstance(v, str) else v for v in normalized["search_sectors"]]
            if len(set(normalized["search_sectors"])) != len(normalized["search_sectors"]):
                raise ValueError("LLM interpretation contains duplicate sectors")
        if not Draft202012Validator(schema).is_valid(normalized):
            raise ValueError("LLM interpretation violates public report schema")
        return normalized

    async def _interpret_orders(self):
        handled = None
        while not self.closed and not self.done.is_set():
            token = (self._generation, self.order.get("order", {}).get("tactical_command"))
            if self.policy_name != "baseline" or not self.order.get("accepted") or token == handled:
                await asyncio.sleep(.05)
                continue
            generation, text = token
            handled = token
            self.llm_calls += 1
            try:
                value = await asyncio.wait_for(self.llm.parse_order(text, allowed_schema=self._interpretation_schema(), deadline=time.monotonic() + self.llm_timeout_s), self.llm_timeout_s)
                value = await asyncio.to_thread(self._validate_interpretation, value)
                if generation == self._generation:
                    self.policy.m1_interpretation = value
                    self.llm_completed += 1
            except asyncio.CancelledError:
                raise
            except Exception as error:
                self._error("llm_interpretation", error)
                if self.allow_fixture_fallback and generation == self._generation:
                    from .baseline import fixture_interpret_order
                    self.policy.m1_interpretation = fixture_interpret_order(text, self.slot)
            await asyncio.sleep(.05)

    async def _rank_evidence(self):
        while not self.closed and not self.done.is_set():
            if self.policy_name == "baseline" and self.me.get("phase") == "running":
                generation = self._generation
                try:
                    prefix = "R" if self.slot.startswith("B") else "B"
                    allowed = {f"{prefix}-{i}" for i in (1, 2, 3)}
                    evidence = {"self_slot": self.slot, "camp": self.policy.camp, "opposing_slots": sorted(allowed),
                                "observed_markers": dict(self.policy.marker_evidence),
                                "confidence": "low", "missing_fields": ["opponent_hp", "opponent_ammo", "opponent_m3"]}
                    ranking = await asyncio.wait_for(self.llm.rank_threat(evidence, deadline=time.monotonic() + self.llm_timeout_s), self.llm_timeout_s)
                    if not isinstance(ranking, (list, tuple)) or len(ranking) != 3 or any(not isinstance(s, str) for s in ranking):
                        raise ValueError("LLM ranking must contain three opposing slots")
                    ranking = [s.upper() for s in ranking]
                    if set(ranking) != allowed:
                        raise ValueError("LLM ranking must contain three unique opposing slots")
                    if generation == self._generation:
                        self.policy.ranking_override = ranking
                        self.policy.rank_confidence = ("low: mock LLM deterministic fallback; no hidden opponent state" if getattr(self.llm, "mock", False)
                                                       else "low: provider ranking from observed markers; opponent HP/ammo/M3 unknown")
                except asyncio.CancelledError:
                    raise
                except Exception as error:
                    self._error("llm_ranking", error)
            await asyncio.sleep(2.)

    async def _heartbeat(self):
        next_at = time.monotonic()
        while not self.closed and not self.done.is_set():
            try:
                phase = self.me.get("phase")
                match_cmd = self.observations.get("match", {}).get("cmd")
                velocity = self.decision.velocity if phase == "running" and match_cmd != "pause" else (0., 0.)
                await self.port.command_velocity(*velocity)
                self.control_times.append(time.monotonic())
                self.control_times[:] = self.control_times[-10000:]
            except Exception as error:
                self._error("control", error)
            next_at += .1
            # A slow network never causes a burst of stale catch-up commands.
            if next_at < time.monotonic():
                next_at = time.monotonic()
            await asyncio.sleep(max(0., next_at - time.monotonic()))

    async def _compute_step(self):
        """Compute in a worker thread so A*/RGB work cannot block the heartbeat."""
        generation = self._generation
        decision = await asyncio.to_thread(self.policy.compute, dict(self.observations), dict(self.me), dict(self.order), dict(self.target))
        if generation != self._generation:
            return
        self.decision = decision
        tick = self.policy.observation_tick(self.observations)
        if decision.gimbal:
            try:
                response = await self.port.command_gimbal(*decision.gimbal)
                self.policy.acknowledge_gimbal(decision.gimbal, response, tick)
            except Exception as error:
                self._error("gimbal", error)
        if self.report_workers["m6"].acknowledged_revision is not None:
            self.policy.sent_m6 = True
        for kind, payload in decision.reports.items():
            self.report_workers[kind].update(payload, created_tick=tick, session_id=self.session_identity.get("match_id", ""))
        if self._transcript and tick != self._last_transcript_sequence:
            record = {"slot": self.slot, "match_id": self.session_identity.get("match_id"), "observed_tick": tick,
                      "phase": self.me.get("phase"), "velocity": list(decision.velocity), "reports": decision.reports,
                      "diagnostics": decision.diagnostics}
            self._transcript.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            self._transcript.flush()
            self._last_transcript_sequence = tick

    async def step(self):
        """Bounded controller step: schedule work and return without waiting for AI."""
        if self._planner_job is None or self._planner_job.done():
            if self._planner_job is not None:
                try:
                    self._planner_job.result()
                except Exception as error:
                    self._error("policy", error)
                    self.decision = PolicyDecision()
            self._planner_job = asyncio.create_task(self._compute_step())
        await asyncio.sleep(0)

    async def _plan(self):
        while not self.closed and not self.done.is_set():
            try:
                await self.step()
            except Exception as error:
                self._error("policy", error)
                self.decision = PolicyDecision()
            await asyncio.sleep(.08)

    def start(self):
        self.tasks = [asyncio.create_task(coro) for coro in (
            self._poll_state(), self._ready(), self._poll_observations(), self._await_mission("order"),
            self._await_mission("target"), self._interpret_orders(), self._rank_evidence(), self._heartbeat(), self._plan())]
        return self

    async def run(self):
        if self.policy is None:
            await self.initialize()
        self.start()
        await self.done.wait()

    async def close(self):
        if self.closed:
            return
        self.closed = True
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        if self._planner_job:
            self._planner_job.cancel()
            await asyncio.gather(self._planner_job, return_exceptions=True)
        try:
            await asyncio.wait_for(self.port.command_velocity(0., 0.), timeout=1.)
        except Exception:
            pass
        for worker in self.report_workers.values():
            await worker.close()
        if self.inference:
            self.inference.close()
        if self._transcript:
            self._transcript.close()
        if self.output:
            gaps = [b - a for a, b in zip(self.control_times, self.control_times[1:])]
            metrics = {"slot": self.slot, "policy": self.policy_name, "control_commands": len(self.control_times),
                       "maximum_control_gap_s": max(gaps, default=0.), "errors": self.errors,
                       "inference_processed": self.inference.processed if self.inference else 0,
                       "inference_dropped": self.inference.dropped if self.inference else 0,
                       "inference_metrics": self.inference.stats() if self.inference else None,
                       "oracle": False, "llm_calls": self.llm_calls, "llm_completed": self.llm_completed,
                       "llm_mock": bool(getattr(self.llm, "mock", False)), "fixture_fallback_allowed": self.allow_fixture_fallback}
            (self.output / "participant_metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
        await self.port.close()


async def run_agent(server: str, slot: str, policy: str, mission_code: str, output=None, max_wall_s: float = 700.):
    from maicon_sim.sdk.http_port import HTTPPort
    controller = TeamController(HTTPPort(server, mission_code), slot, policy, output=output)
    try:
        await asyncio.wait_for(controller.run(), timeout=max_wall_s)
        return 0
    finally:
        await controller.close()
