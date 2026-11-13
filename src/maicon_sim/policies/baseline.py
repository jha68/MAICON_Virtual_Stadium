"""Small public-sensor baseline, not an oracle or a competition-ready strategy.

All positions are estimates composed from a nominal public start and local odometry.
The Korean fixture interpreter is a replaceable integration stub, not LLM evidence.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
import re

from .planning import FREE, OCCUPIED, UNKNOWN, OccupancyGrid, follow_waypoint, inside_polygon, wrap
from .scripted import WaypointPolicy, base_goal, nominal_pose
from .tracking import ObjectTracker


@dataclass(frozen=True)
class PolicyDecision:
    velocity: tuple[float, float] = (0., 0.)
    gimbal: tuple[float, float, float, float] | None = None
    reports: dict = field(default_factory=dict)
    diagnostics: dict = field(default_factory=dict)
    fire: bool = False


def fixture_interpret_order(text: str, slot: str) -> dict:
    """Deterministic text-only fixture adapter. Does not read expected_m1."""
    opposing = "RED" if slot.startswith("B") else "BLUE"
    prefix = "R" if slot.startswith("B") else "B"
    target = next((code for name, code in (("레이더시설", "RADAR"), ("통신시설", "COMMS"), ("감시초소", "OUTPOST")) if name in text), None)
    base = next((code for name, code in (("군수보급소", "SUPPLY_DEPOT"), ("정비소", "MAINTENANCE"), ("작전지휘소", "COMMAND_POST")) if name in text), None)
    sectors = re.findall(r"[BR]-S[123]|\bCM\b", text.upper())
    for name, number in (("첫째", 1), ("둘째", 2), ("셋째", 3)):
        if name in text:
            sectors.append(f"{prefix}-S{number}")
    if "중앙" in text:
        sectors.append("CM")
    result = {}
    if target:
        result["target"] = f"{opposing}_{target}"
    if sectors:
        result["search_sectors"] = sorted(set(sectors))
    if base:
        result["base"] = f"{opposing}_{base}"
    return result


class GimbalEstimate:
    """Rate-model estimate from accepted commands, deliberately no truth feedback."""
    def __init__(self):
        self.pan = self.tilt = 0.
        self.target_pan = self.target_tilt = 0.
        self.speed = 90.
        self.last_tick = 0
        self.settled_tick = 0
        self.certain = True

    def update(self, tick: int):
        dt = max(0, tick - self.last_tick) * .01
        for name, unit in (("pan", .5), ("tilt", .15)):
            current, target = getattr(self, name), getattr(self, "target_" + name)
            maximum = self.speed * dt / unit
            setattr(self, name, current + max(-maximum, min(maximum, target - current)))
        self.last_tick = tick

    def accepted(self, pan, tilt, speed, tick):
        self.update(tick)
        travel_s = max(abs(pan - self.pan) * .5, abs(tilt - self.tilt) * .15) / speed
        self.target_pan, self.target_tilt, self.speed = pan, tilt, speed
        self.settled_tick = tick + math.ceil((travel_s + .1) * 100)
        self.certain = True

    def cancel(self, tick):
        self.update(tick)
        self.target_pan, self.target_tilt = self.pan, self.tilt
        self.certain = False
        self.settled_tick = math.inf

    def settled(self, captured_tick):
        return self.certain and captured_tick >= self.settled_tick


class ParticipantPolicy:
    """Synchronous public-only policy usable by accelerated and HTTP runners."""

    def __init__(self, public_map: dict, calibration: dict, slot: str, policy: str = "baseline"):
        if policy not in ("idle", "baseline", "patrol", "blocker", "capture_runner"):
            raise ValueError(f"unknown participant policy {policy!r}")
        self.public_map, self.calibration, self.slot, self.policy = public_map, calibration, slot, policy
        self.camp = "BLUE" if slot.startswith("B") else "RED"
        bounds = public_map.get("bounds", {})
        self.grid = OccupancyGrid(bounds.get("width_m", 6.12), bounds.get("height_m", 5.))
        self.tracker, self.gimbal = ObjectTracker(), GimbalEstimate()
        from .combat import CombatPolicy
        from .threat import ThreatEstimator
        from .observations import ObservationHistory, GimbalHistory, SurfaceMapper
        self.combat = CombatPolicy(slot, public_map)
        self.threat = ThreatEstimator(self.camp)
        self.history, self.gimbal_history = ObservationHistory(), GimbalHistory()
        self.surface_mapper = SurfaceMapper(public_map, calibration, slot)
        self._grid_correction = (0., 0., 0.)
        self.start = nominal_pose(public_map, slot)
        self.waypoints = WaypointPolicy(public_map, slot, policy)
        self.last_sequence = {}
        self.last_reports = {}
        self.last_report_tick = {}
        self.sent_m6 = False
        self.goal = None
        self.path = []
        self.last_plan_tick = -1000
        self.last_frontier_tick = -1000
        self.last_gimbal_tick = -1000
        self.scan_index = 0
        self.last_phase = None
        self.target_objective = None
        self.rank_confidence = "low: deterministic fallback; no opponent state observed"
        self.marker_evidence = {}
        self._rgb_detector = None
        self._last_rgb_sequence = None
        self.m1_interpretation = None
        self.use_inline_fixture = True
        self.ranking_override = None
        self.llm_provider = "fixture_text_stub"
        self.llm_mock = True
        self.last_diagnostics = {}

    def reset(self, public_map: dict | None = None, calibration: dict | None = None):
        self.__init__(public_map or self.public_map, calibration or self.calibration, self.slot, self.policy)

    @staticmethod
    def observation_tick(observations):
        return max((int(v.get("received_tick", v.get("captured_tick", 0))) for v in observations.values() if isinstance(v, dict)), default=0)

    def world_estimate(self, odom):
        if not self.start or not odom:
            return None
        pose = odom.get("local_pose", odom.get("pose", {}))
        if not all(k in pose for k in ("x_m", "y_m", "yaw_rad")):
            return None
        x, y, yaw = self.start
        dx, dy = pose["x_m"], pose["y_m"]
        raw = (x + math.cos(yaw) * dx - math.sin(yaw) * dy,
               y + math.sin(yaw) * dx + math.cos(yaw) * dy,
               wrap(yaw + pose["yaw_rad"]))
        return self.surface_mapper.localizer.apply(raw)

    def _new(self, channel, frame):
        if not frame:
            return False
        sequence = frame.get("sequence", frame.get("captured_tick"))
        if sequence is None or sequence == self.last_sequence.get(channel):
            return False
        self.last_sequence[channel] = sequence
        return True

    def _sector(self, point):
        return next((s["sector_id"] for s in self.public_map.get("sectors", []) if inside_polygon(point, s["polygon_xy_m"])), None)

    def _coverage(self):
        # Coverage is based on mapped cells, separately from a submitted zero count.
        import numpy as np
        for sector in self.public_map.get("sectors", []):
            polygon = sector["polygon_xy_m"]
            xs, ys = [p[0] for p in polygon], [p[1] for p in polygon]
            a, b = self.grid.cell(min(xs), min(ys)), self.grid.cell(max(xs), max(ys))
            sample = self.grid.cells[max(0, a[1]):min(self.grid.cells.shape[0], b[1]), max(0, a[0]):min(self.grid.cells.shape[1], b[0])]
            if sample.size and np.mean(sample != UNKNOWN) >= .8:
                # LiDAR coverage does not prove all printed faces were seen. Keep
                # partial visual coverage unless an explicit image survey fixture
                # marks the sector complete through ObjectTracker.mark_coverage.
                self.tracker.mark_coverage(sector["sector_id"], complete=False)

    def _report(self, kind, payload, tick, force=False):
        if not payload or (kind == "m3" and not payload.get("sectors")):
            return None
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        # Periodic latest-snapshot repair covers unknown-outcome stale commits.
        if force or canonical != self.last_reports.get(kind) or tick - self.last_report_tick.get(kind, -1000) >= 200:
            self.last_reports[kind], self.last_report_tick[kind] = canonical, tick
            return payload
        return None

    def acknowledge_report(self, kind, response):
        if kind == "m6" and response.get("accepted") and response.get("received"):
            self.sent_m6 = True

    def acknowledge_gimbal(self, command, response, tick):
        if response.get("message") == "ok":
            self.gimbal.accepted(*command[:3], tick)
            self.gimbal_history.command(*command[:3], tick)
        elif response.get("message") == "locked":
            self.gimbal.cancel(tick)
            self.gimbal_history.cancel(tick)
        self.combat.acknowledge_gimbal(command, response, tick)

    def acknowledge_fire(self, response, tick):
        self.combat.acknowledge_fire(response, tick)

    def cancel_motion(self, tick):
        self.gimbal.cancel(tick)
        self.gimbal_history.cancel(tick)
        self.combat.cancel(tick)

    def _navigate(self, pose, tick, goal, target_active):
        if goal is None:
            return 0., 0.
        start, endpoint = self.grid.cell(*pose[:2]), self.grid.cell(*goal)
        forbidden = set()
        if target_active:
            # After objective publication avoid self-capture of the opposite goal.
            for base in self.public_map.get("bases", []):
                if base.get("camp") == self.camp:
                    polygon = base["polygon_xy_m"]
                    xs, ys = [p[0] for p in polygon], [p[1] for p in polygon]
                    a, b = self.grid.cell(min(xs), min(ys)), self.grid.cell(max(xs), max(ys))
                    forbidden.update((x, y) for x in range(a[0], b[0] + 1) for y in range(a[1], b[1] + 1))
            # A robot initially inside its own strip must be allowed to leave it.
            forbidden.discard(start)
        if goal != self.goal or tick - self.last_plan_tick >= 50 or not self.path:
            self.path = self.grid.astar(start, endpoint, forbidden)
            self.goal, self.last_plan_tick = goal, tick
        while self.path and math.dist(pose[:2], self.grid.center(self.path[0])) < .08:
            self.path.pop(0)
        if not self.path:
            return 0., 0.
        waypoint = self.grid.center(self.path[0])
        # Newly inflated obstacles invalidate the next segment immediately.
        cell = self.path[0]
        if self.grid.inflated()[cell[1], cell[0]]:
            self.path = []
            return 0., 0.
        return follow_waypoint(pose, waypoint)

    def compute(self, observations: dict, me: dict, order: dict | None = None, target: dict | None = None) -> PolicyDecision:
        self.history.add(observations)
        tick = self.observation_tick(observations)
        phase = me.get("phase", "idle")
        cmd = observations.get("match", {}).get("cmd", "")
        self.gimbal.update(tick)
        reports = {}
        diagnostics = {"pose_source": "public_wall_registration_plus_local_odom", "rank_confidence": self.rank_confidence,
                       "llm_provider": self.llm_provider, "llm_mock": self.llm_mock, "oracle": False}
        if self.policy == "idle":
            return PolicyDecision(diagnostics=diagnostics)
        if phase == "reporting":
            if not self.sent_m6:
                reports["m6"] = {"ranking": list(self.ranking_override or self.threat.ranking(tick))}
            return PolicyDecision(reports=reports, diagnostics=diagnostics)
        if phase != "running" or cmd == "pause":
            if self.last_phase == "running":
                self.cancel_motion(tick)
            self.last_phase = phase
            return PolicyDecision(diagnostics=diagnostics)
        self.last_phase = phase
        if self.policy == "baseline" and order and order.get("accepted"):
            value = self.m1_interpretation or (fixture_interpret_order(order.get("order", {}).get("tactical_command", ""), self.slot) if self.use_inline_fixture else {})
            candidate = self._report("m1", value, tick)
            if candidate:
                reports["m1"] = candidate
        scan = observations.get("scan", {})
        raw_scan_pose = self.history.pose_at(scan.get("captured_tick", tick), self.start)
        if self.policy == "baseline":
            self.surface_mapper.correct_pose(raw_scan_pose, scan)
        correction = self.surface_mapper.localizer.correction
        if math.dist(correction[:2], self._grid_correction[:2]) > .02 or abs(wrap(correction[2]-self._grid_correction[2])) > .01:
            bounds = self.public_map.get("bounds", {})
            self.grid = OccupancyGrid(bounds.get("width_m", 6.12), bounds.get("height_m", 5.))
            self.path = []
            self._grid_correction = correction
        pose = self.world_estimate(observations.get("odom"))
        if pose is None:
            diagnostics["motion_blocked"] = "local odometry or nominal prior unavailable"
            return PolicyDecision(reports=reports, diagnostics=diagnostics)
        if self._new("scan", scan):
            scan_pose = self.surface_mapper.localizer.apply(raw_scan_pose) if raw_scan_pose else None
            if scan_pose is not None:
                self.grid.update_scan(scan_pose, scan)
        semantic = observations.get("semantic", {})
        rgb = observations.get("rgb")
        if self.policy == "baseline" and not semantic and isinstance(rgb, dict) and "data" in rgb:
            sequence = rgb.get("sequence", rgb.get("captured_tick"))
            if sequence != self._last_rgb_sequence:
                if self._rgb_detector is None:
                    from maicon_sim.perception.combat import CombatVisionDetector
                    self._rgb_detector = CombatVisionDetector(self.calibration)
                public_frame = dict(rgb)
                public_frame.setdefault("camera_id", self.slot + "/front")
                public_frame.setdefault("width_px", rgb["data"].shape[1])
                public_frame.setdefault("height_px", rgb["data"].shape[0])
                public_frame.setdefault("received_tick", rgb.get("captured_tick", 0))
                public_frame.setdefault("sequence", rgb.get("captured_tick", 0))
                semantic = self._rgb_detector.process(public_frame)
                self._last_rgb_sequence = sequence
                diagnostics["perception"] = "RGB synthetic_template; no semantic oracle"
        if self.policy == "baseline" and self._new("semantic", semantic):
            self.threat.observe(semantic)
            diagnostics.update(self.surface_mapper.observe(semantic, self.history, self.gimbal_history, self.tracker))
            for detection in semantic.get("detections", []):
                marker = detection.get("marker_readout", {})
                if marker.get("confidence", 0) >= .75 and marker.get("camp") != self.camp and marker.get("band_count") in (1, 2, 3):
                    self.marker_evidence[f"{marker['camp'][0]}-{marker['band_count']}"] = semantic.get("captured_tick", tick)
            if tick % 100 == 0:
                self._coverage()
            candidate = self._report("m3", self.tracker.report(), tick)
            if candidate:
                reports["m3"] = candidate
        objective = target.get("order", {}).get("objective") if target and target.get("accepted") else None
        if objective != self.target_objective:
            self.path = []
            self.target_objective = objective
        if objective:
            goal = base_goal(self.public_map, objective)
        elif self.policy in ("patrol", "blocker", "capture_runner"):
            goal = self.waypoints.goal(pose, tick, target)
        else:
            if tick - self.last_frontier_tick >= 200 or self.goal is None or math.dist(pose[:2], self.goal) < .1:
                prefix = "R-" if self.camp == "BLUE" else "B-"
                sectors = [s for s in self.public_map.get("sectors", []) if s["sector_id"].startswith(prefix) or s["sector_id"] == "CM"]
                self.goal = self.grid.frontier(pose, sectors)
                self.last_frontier_tick = tick
            goal = self.goal
        velocity = self._navigate(pose, tick, goal, bool(objective))
        # Immediate front clearance check is independent of slow A*/inference.
        ranges = scan.get("ranges_m", [])
        if velocity[0] > 0 and ranges:
            amin = scan.get("angle_min_rad", -math.pi)
            ainc = scan.get("angle_increment_rad", 2 * math.pi / len(ranges))
            clearances = [r for i, r in enumerate(ranges) if r is not None and abs(wrap(amin + i * ainc)) < math.radians(25)]
            if clearances and min(clearances) < .23:
                velocity = (0., 0.)
                self.path = []
                diagnostics["motion_blocked"] = "front scan clearance"
        gimbal = None
        if self.policy == "baseline" and tick - self.last_gimbal_tick >= 200:
            pan = (-40., 0., 40., 0.)[self.scan_index % 4]
            self.scan_index += 1
            self.last_gimbal_tick = tick
            gimbal = (pan, 0., 30., 20.)
        diagnostics["tracks"] = len(self.tracker.tracks)
        diagnostics["coverage"] = dict(self.tracker.coverage)
        fire = False
        if self.policy == "baseline":
            interpretation = self.m1_interpretation or (fixture_interpret_order(order.get("order", {}).get("tactical_command", ""), self.slot) if order and self.use_inline_fixture else {})
            combat_observations = {**observations, "semantic": semantic}
            capture_tick = semantic.get("captured_tick")
            capture_angles = self.gimbal_history.at(capture_tick) if type(capture_tick) is int else None
            capture_pose = self.history.pose_at(capture_tick, self.start) if type(capture_tick) is int else None
            capture_pose = self.surface_mapper.localizer.apply(capture_pose) if capture_pose else None
            action = self.combat.update(combat_observations, self.calibration, observations.get("state"),
                                        interpretation.get("target"), phase=phase, cmd=cmd,
                                        objective=objective, gimbal={"pan": self.gimbal.pan, "tilt": self.gimbal.tilt},
                                        pose=capture_pose, capture_gimbal=capture_angles)
            diagnostics["combat"] = {"state": action.state, **action.diagnostics}
            if action.hold:
                velocity = (0., 0.)
                gimbal = action.gimbal
            elif action.gimbal is not None:
                gimbal = action.gimbal
            fire = action.fire
        return PolicyDecision(velocity, gimbal, reports, diagnostics, fire)
