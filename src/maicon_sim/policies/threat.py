"""Uncertain M6 estimates from visible cues only, never evaluator state DTOs."""
from __future__ import annotations

from dataclasses import dataclass, field
import math
import threading


@dataclass
class OpponentEvidence:
    hp: tuple[float, float] = (0., 4.)
    ammo: tuple[float, float] = (0., 8.)
    hp_tick: int | None = None
    ammo_tick: int | None = None
    last_seen_tick: int | None = None
    last_frame_tick: dict[str, int] = field(default_factory=dict)
    shot_visible: bool = False
    last_shot_event: str | None = None
    last_shot_tick: int | None = None
    hp_cues: int = 0
    ammo_cues: int = 0
    shot_cues: int = 0


class ThreatEstimator:
    """Identity-conditioned intervals with conservative unseen decay.

    Input is a public detection frame, e.g. CombatVisionDetector.process(rgb).
    Only marker_readout and visual_state are read. Raw hp/ammo/m3 fields on a
    detection are ignored; opponent M3 always remains unknown. A lock permits
    the controller's async rank worker to snapshot a planner's evolving tracks.
    """
    def __init__(self, camp="BLUE", *, identity_confidence=.75):
        if camp not in ("BLUE", "RED"):
            raise ValueError("camp must be BLUE or RED")
        self.camp = camp
        self.enemy = "RED" if camp == "BLUE" else "BLUE"
        self.identity_confidence = identity_confidence
        self.opponents = {f"{self.enemy[0]}-{i}": OpponentEvidence() for i in (1, 2, 3)}
        self._lock = threading.RLock()

    @staticmethod
    def _number(value):
        return type(value) in (int, float) and math.isfinite(value)

    def _interval(self, state, name, maximum):
        confidence = state.get(name + "_confidence", state.get("confidence", 0.))
        if not self._number(confidence) or not .5 <= confidence <= 1.:
            return None
        interval = state.get(name + "_interval")
        if interval is not None:
            if not isinstance(interval, (list, tuple)) or len(interval) != 2 or any(not self._number(v) for v in interval):
                return None
            lo, hi = interval
            if not 0 <= lo <= hi <= maximum:
                return None
        else:
            value = state.get(name)
            if type(value) is not int or not 0 <= value <= maximum:
                return None
            lo = hi = float(value)
        margin = 0. if confidence >= .9 else 1.
        return max(0., lo-margin), min(float(maximum), hi+margin)

    def observe(self, frame):
        with self._lock:
            self._observe(frame)

    def _observe(self, frame):
        if not isinstance(frame, dict):
            return
        tick = frame.get("captured_tick")
        if type(tick) is not int or tick < 0:
            return
        source = str(frame.get("camera_id", "front"))
        detections = frame.get("detections", [])
        if not isinstance(detections, (list, tuple)):
            return
        for detection in detections:
            if not isinstance(detection, dict) or detection.get("kind") != "ugv":
                continue
            marker = detection.get("marker_readout", {})
            if not isinstance(marker, dict):
                continue
            confidence, band = marker.get("confidence", 0.), marker.get("band_count")
            if marker.get("camp") != self.enemy or type(band) is not int or band not in (1, 2, 3) or not self._number(confidence) or confidence < self.identity_confidence:
                continue
            track = self.opponents[f"{self.enemy[0]}-{band}"]
            if tick <= track.last_frame_tick.get(source, -1):
                continue
            track.last_frame_tick[source] = tick
            if track.last_seen_tick is not None and tick < track.last_seen_tick:
                continue
            track.last_seen_tick = tick
            state = detection.get("visual_state", {})
            if not isinstance(state, dict):
                continue
            hp, ammo = self._interval(state, "hp", 4), self._interval(state, "ammo", 8)
            if hp is not None:
                track.hp, track.hp_tick = hp, tick
                track.hp_cues += 1
            if ammo is not None:
                track.ammo, track.ammo_tick = ammo, tick
                track.ammo_cues += 1
            if type(state.get("shot_visible")) is bool:
                visible = state["shot_visible"]
                event = state.get("shot_event_id")
                event = str(event)[:128] if isinstance(event, (str, int)) else None
                new_shot = visible and ((event is not None and event != track.last_shot_event) or (event is None and not track.shot_visible))
                if new_shot and (track.last_shot_tick is None or tick-track.last_shot_tick >= 1000):
                    track.shot_cues += 1
                    track.last_shot_tick = tick
                    if ammo is None:
                        current = self._aged(track.ammo, track.ammo_tick, tick, 8)
                        track.ammo = (max(0., current[0]-1), max(0., current[1]-1))
                        track.ammo_tick = tick
                    track.last_shot_event = event
                track.shot_visible = visible

    @staticmethod
    def _aged(interval, measured_tick, tick, maximum):
        if measured_tick is None:
            return 0., float(maximum)
        # A shot/hit may occur immediately after capture, then once per ten
        # seconds. Round up so the interval contains that boundary event too.
        decay = math.ceil(max(0, tick-measured_tick)/1000.)
        return max(0., interval[0]-decay), interval[1]

    def summary(self, tick):
        with self._lock:
            return self._summary(tick)

    def _summary(self, tick):
        if type(tick) is not int or tick < 0:
            raise ValueError("tick must be a nonnegative integer")
        opponents = {}
        for slot, track in self.opponents.items():
            hp = self._aged(track.hp, track.hp_tick, tick, 4)
            ammo = self._aged(track.ammo, track.ammo_tick, tick, 8)
            risk = [hp[0]/4+ammo[0]/8, hp[1]/4+ammo[1]/8+1.]
            opponents[slot] = {
                "hp_interval": list(hp), "ammo_interval": list(ammo), "m3_interval": [0, 30],
                "risk_interval": risk, "risk_expected": sum(risk)/2,
                "last_seen_tick": track.last_seen_tick,
                "age_s": None if track.last_seen_tick is None else max(0, tick-track.last_seen_tick)/100.,
                "cue_counts": {"hp_led": track.hp_cues, "ammo_led": track.ammo_cues, "shot_events": track.shot_cues},
            }
        ranking = sorted(opponents, key=lambda slot: (-opponents[slot]["risk_expected"], slot))
        overlaps = [[a, b] for i, a in enumerate(ranking) for b in ranking[i+1:]
                    if max(opponents[a]["risk_interval"][0], opponents[b]["risk_interval"][0]) <= min(opponents[a]["risk_interval"][1], opponents[b]["risk_interval"][1])]
        observed = any(t.hp_cues or t.ammo_cues or t.shot_cues for t in self.opponents.values())
        return {"camp": self.camp, "opposing_slots": sorted(self.opponents), "opponents": opponents,
                "estimated_ranking": ranking, "possible_ties": overlaps,
                "ranking_kind": "observed_estimate" if observed else "uninformed_fallback",
                "confidence": "low" if overlaps else "separated_intervals",
                "missing_fields": ["opponent_m3"], "source": "public_visual_cues", "oracle": False}

    def ranking(self, tick):
        return self.summary(tick)["estimated_ranking"]
