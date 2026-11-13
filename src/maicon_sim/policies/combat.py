"""Conservative aiming/fire state machine over public visual observations.

This is a synthetic reference policy, not a measured real-robot targeting model.
No simulator entity identifiers, opponent state, or evaluator poses are read.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math

from .planning import inside_polygon

_UNSPECIFIED = object()


@dataclass(frozen=True)
class CombatDecision:
    gimbal: tuple[float, float, float, float] | None = None
    fire: bool = False
    hold: bool = False
    state: str = "search"
    diagnostics: dict = field(default_factory=dict)


class CombatPolicy:
    """Track a designated facility first, then a visually identified opponent.

    Call ``acknowledge_fire(None, tick)`` for a timeout. That outcome stays
    unknown until a new own-state sample confirms that ammunition was consumed;
    the uncertain actuation is never automatically retried.
    """
    def __init__(self, slot, public_map=None, *, confidence=.75, alignment_px=3., settle_ticks=20, max_frame_age_ticks=30):
        self.slot = slot
        self.camp = "BLUE" if slot.startswith("B") else "RED"
        self.enemy = "RED" if self.camp == "BLUE" else "BLUE"
        self.public_map = public_map or {}
        self.confidence = confidence
        self.alignment_px = alignment_px
        self.settle_ticks = settle_ticks
        self.max_frame_age_ticks = max_frame_age_ticks
        self.reset()

    def reset(self):
        self.target_key = None
        self.aligned_since = None
        self.last_frame_tick = None
        self.last_gimbal_tick = -1000
        self.next_fire_tick = 0
        self.pending_fire = False
        self.unknown_outcome = False
        self.ammo_before_fire = None
        self.request_tick = None
        self.confirmed_fire_tick = None
        self.serviced_facilities = set()
        self.last_kind = None
        self._shot_target = None
        self._state_tick = -1
        self._empty = False
        self._facility_dwell_confirmed = False

    def cancel(self, tick=0):
        self.target_key = None
        self.aligned_since = None
        self.last_frame_tick = None
        # Pending/unknown actuation and its cooldown deliberately survive a
        # pause; a resumed controller must not repeat a request whose ACK was lost.

    def acknowledge_gimbal(self, command, response, tick):
        if response.get("message") != "ok":
            self.aligned_since = None

    def discard_unsent_fire(self, tick):
        """Release a dropped planner intent, never a dispatched/unknown shot.

        Call only before the service request is sent, e.g. if the controller's
        freshness guard invalidates the computed decision.
        """
        if self.pending_fire and not self.unknown_outcome:
            self.pending_fire = False
            self.request_tick = None
            self._shot_target = None
            self.next_fire_tick = min(self.next_fire_tick, tick)
            self.aligned_since = None

    def acknowledge_fire(self, response, tick):
        self.pending_fire = False
        if response is None:
            self.unknown_outcome = True
            return
        message = response.get("message")
        if message == "fired":
            self.confirmed_fire_tick = self.request_tick if self.request_tick is not None else tick
            self.next_fire_tick = max(self.next_fire_tick, self.confirmed_fire_tick + 1000)
            self.unknown_outcome = False
        elif message in ("locked", "reloading"):
            self.next_fire_tick = max(tick + 10, tick + math.ceil(max(0, response.get("left_ms", 0))/10))
            self.aligned_since = None
            self.request_tick = None
            self._shot_target = None
        elif message == "empty":
            self._empty = True
            self.next_fire_tick = math.inf
            self.request_tick = None
            self._shot_target = None
        else:
            self.unknown_outcome = True

    @staticmethod
    def _range(detection, observations, calibration, pan):
        value = detection.get("range_m")
        if isinstance(value, (int, float)) and math.isfinite(value) and .15 <= value <= 8:
            return float(value)
        scan = observations.get("scan", {})
        values = scan.get("ranges_m", [])
        aim = detection.get("aim_point_px")
        if not values or not aim:
            return None
        camera = calibration.get("front_camera", {})
        angle = -math.radians(.5 * pan) - math.atan((aim[0]-camera.get("cx_px", 319.5))/camera.get("fx_px", 320.))
        step = scan.get("angle_increment_rad", 2*math.pi/len(values))
        if not step:
            return None
        index = round((angle-scan.get("angle_min_rad", -math.pi))/step) % len(values)
        value = values[index]
        return float(value) if isinstance(value, (int, float)) and math.isfinite(value) and .15 <= value <= 8 else None

    def _facility_is_enemy(self, detection, distance, pose, pan, calibration):
        # An identical facility picture in our own camp must not be mistaken for
        # the assigned enemy facility. Use only the public map and estimated pose.
        readout = detection.get("camp_readout", {})
        if readout.get("confidence", 0) >= self.confidence:
            return readout.get("camp") == self.enemy
        if pose is None or distance is None:
            return False
        camera = calibration.get("front_camera", {})
        x = detection["aim_point_px"][0]
        bearing = pose[2] - math.radians(.5 * pan) - math.atan((x-camera.get("cx_px", 319.5))/camera.get("fx_px", 320.))
        point = (pose[0]+distance*math.cos(bearing), pose[1]+distance*math.sin(bearing))
        return any(s["sector_id"].startswith(self.enemy[0]+"-") and inside_polygon(point, s["polygon_xy_m"])
                   for s in self.public_map.get("sectors", []))

    def _candidate(self, detections, target, observations, calibration, pose, pan):
        facilities, opponents = [], []
        suffix = target.split("_", 1)[1] if isinstance(target, str) and target.startswith(self.enemy+"_") else None
        for detection in detections:
            if detection.get("confidence", 0) < self.confidence or detection.get("aim_confidence", detection.get("confidence", 0)) < self.confidence or not detection.get("aim_point_px"):
                continue
            distance = self._range(detection, observations, calibration, pan)
            if distance is None:
                continue
            if detection.get("kind") == "facility" and suffix and target not in self.serviced_facilities:
                probabilities = detection.get("class_probs", {})
                if probabilities.get(suffix, probabilities.get(target, 0)) >= self.confidence and self._facility_is_enemy(detection, distance, pose, pan, calibration):
                    facilities.append((target, detection, distance))
            elif detection.get("kind") == "ugv":
                marker = detection.get("marker_readout", {})
                if marker.get("camp") == self.enemy and marker.get("confidence", 0) >= self.confidence and marker.get("band_count") in (1, 2, 3):
                    opponents.append((f"{self.enemy[0]}-{marker['band_count']}", detection, distance))
        choices = facilities or opponents
        return min(choices, key=lambda item: (-item[1]["confidence"], item[2], item[0])) if choices else None

    @staticmethod
    def _occluded(candidate, detections):
        x, y = candidate["aim_point_px"]
        for detection in detections:
            if detection is candidate or detection.get("kind") != "ugv":
                continue
            box = detection.get("bbox_xyxy_px")
            if box and box[0]-3 <= x <= box[2]+3 and box[1]-3 <= y <= box[3]+3:
                return True
        return False

    def update(self, observations, calibration, state=None, target=None, *, phase="running", cmd="start", objective=None, gimbal=None, pose=None, capture_gimbal=_UNSPECIFIED):
        state = state or observations.get("state", {})
        gimbal = gimbal or observations.get("gimbal_estimate", {})
        pan, tilt = float(gimbal.get("pan", 0.)), float(gimbal.get("tilt", 0.))
        if capture_gimbal is None:
            self.cancel()
            return CombatDecision(state="uncertain_gimbal")
        capture_gimbal = (pan, tilt) if capture_gimbal is _UNSPECIFIED else capture_gimbal
        if isinstance(capture_gimbal, dict):
            capture_pan, capture_tilt = capture_gimbal["pan"], capture_gimbal["tilt"]
        else:
            capture_pan, capture_tilt = capture_gimbal
        now = max((int(value.get("received_tick", value.get("captured_tick", 0))) for value in observations.values() if isinstance(value, dict)), default=0)
        own_tick = state.get("captured_tick", state.get("sequence", -1))
        if own_tick > self._state_tick:
            self._state_tick = own_tick
            if self.unknown_outcome and self.ammo_before_fire is not None and state.get("ammo", self.ammo_before_fire) < self.ammo_before_fire:
                self.unknown_outcome = False
                self.confirmed_fire_tick = self.request_tick
        if phase != "running" or cmd not in ("start", "resume") or objective:
            self.cancel(now)
            return CombatDecision(state="inactive")
        frame = observations.get("combat", observations.get("semantic", {}))
        captured = frame.get("captured_tick")
        if not isinstance(captured, int) or now-captured > self.max_frame_age_ticks or captured > now:
            self.cancel(now)
            return CombatDecision(state="stale")
        detections = frame.get("detections", [])
        selected = self._candidate(detections, target, observations, calibration, pose, capture_pan)
        if selected is None:
            self.cancel(now)
            return CombatDecision(state="search")
        key, detection, distance = selected
        if self._occluded(detection, detections):
            self.cancel(now)
            return CombatDecision(hold=True, state="occluded")
        if key != self.target_key:
            self.target_key, self.aligned_since = key, None
        elif self.last_frame_tick is not None and (captured < self.last_frame_tick or captured-self.last_frame_tick > self.max_frame_age_ticks):
            self.aligned_since = None
        self.last_kind = detection["kind"]
        camera = calibration.get("front_camera", {})
        fx, fy = camera.get("fx_px", 320.), camera.get("fy_px", 320.)
        cx, cy = camera.get("cx_px", 319.5), camera.get("cy_px", 239.5)
        offset = calibration.get("laser_offset_camera_m", [0., 0., .02])
        aim_x, aim_y = detection["aim_point_px"]
        # A laser 2cm above the camera hits a target seen above the optical
        # centre, even when its axis is parallel to the optical axis.
        error_x = aim_x-(cx-fx*offset[1]/distance)
        error_y = aim_y-(cy-fy*offset[2]/distance)
        # Delayed pixels describe the gimbal at capture, not its latest pose.
        wanted_pan = capture_pan + math.degrees(math.atan(error_x/fx))/.5
        wanted_tilt = capture_tilt - math.degrees(math.atan(error_y/fy))/.15
        diagnostics = {"target": key, "range_m": distance, "error_px": [error_x, error_y], "oracle": False}
        if abs(wanted_pan) > 100 or abs(wanted_tilt) > 100:
            self.aligned_since = None
            return CombatDecision(state="unreachable", diagnostics=diagnostics)
        aligned = (abs(error_x) <= self.alignment_px and abs(error_y) <= self.alignment_px
                   and abs(pan-capture_pan)*.5 <= math.degrees(math.atan(self.alignment_px/fx))
                   and abs(tilt-capture_tilt)*.15 <= math.degrees(math.atan(self.alignment_px/fy)))
        if not aligned:
            self.aligned_since = None
            if captured == self.last_frame_tick:
                return CombatDecision(hold=True, state="aim", diagnostics=diagnostics)
            self.last_frame_tick = captured
            self.last_gimbal_tick = now
            return CombatDecision(gimbal=(wanted_pan, wanted_tilt, 60., 20.), hold=True, state="aim", diagnostics=diagnostics)
        if self.aligned_since is None:
            self.aligned_since = captured
        self.last_frame_tick = captured
        if self.confirmed_fire_tick is not None and self._shot_target == key and detection["kind"] == "facility":
            if captured <= self.confirmed_fire_tick+500 and captured-max(self.confirmed_fire_tick, self.aligned_since) >= 200:
                # An observed aligned dwell during this shot, not a secret hit
                # acknowledgement or alignment achieved after emission ended.
                self._facility_dwell_confirmed = True
            if self._facility_dwell_confirmed and now-self.confirmed_fire_tick >= 500:
                self.serviced_facilities.add(key)
                return CombatDecision(state="facility_attempt_complete", diagnostics=diagnostics)
        if self.pending_fire or self.unknown_outcome:
            return CombatDecision(hold=True, state="unknown" if self.unknown_outcome else "pending", diagnostics=diagnostics)
        if self._empty or state.get("ammo") == 0:
            return CombatDecision(state="empty", diagnostics=diagnostics)
        if now < self.next_fire_tick:
            return CombatDecision(hold=self.confirmed_fire_tick is not None and now-self.confirmed_fire_tick < 500, state="cooldown", diagnostics=diagnostics)
        if captured-self.aligned_since < self.settle_ticks:
            return CombatDecision(hold=True, state="settle", diagnostics=diagnostics)
        self.pending_fire = True
        self._facility_dwell_confirmed = False
        self.request_tick = now
        self.ammo_before_fire = state.get("ammo")
        self._shot_target = key
        self.next_fire_tick = now+1000
        return CombatDecision(fire=True, hold=True, state="fire", diagnostics=diagnostics)
