"""Participant-generated evidence tracks. No simulator entity identifiers enter here."""
from __future__ import annotations

from dataclasses import dataclass, field
import math

from .planning import wrap

OBJECT_CLASSES = ("military_truck", "mortar", "tank", "missile", "ammo_box", "drum")


@dataclass
class EvidenceTrack:
    track_id: int
    position: tuple[float, float]
    normal_rad: float
    sector: str | None
    evidence: dict[str, float] = field(default_factory=dict)
    support: float = 0.
    observations: int = 0
    last_tick: int = 0
    contradictions: int = 0
    surface_extent: tuple | None = None
    position_sigma_m: float = .02

    @property
    def label(self):
        return max(sorted(self.evidence), key=self.evidence.get) if self.evidence else None


class ObjectTracker:
    def __init__(self):
        self.tracks: list[EvidenceTrack] = []
        self.next_id = 1
        self.bearing_only: list[dict] = []
        self.coverage: dict[str, str] = {}

    def observe(self, position, normal_rad: float, class_probs: dict, tick: int, sector: str | None = None, confidence: float = 1., *, surface_extent=None, position_sigma_m=.02, sector_uncertain=False) -> int:
        """Associate by position and surface orientation, never by texture or class."""
        def same_surface(track):
            if abs(wrap(track.normal_rad-normal_rad)) > math.radians(25):
                return False
            if track.surface_extent is None or surface_extent is None:
                return math.dist(track.position, position) <= .12
            normal = (math.cos(normal_rad), math.sin(normal_rad))
            tangent = (-normal[1], normal[0])
            delta = tuple(a-b for a, b in zip(track.position, position))
            if abs(sum(a*b for a, b in zip(delta, normal))) > max(.045, 2*(position_sigma_m+track.position_sigma_m)):
                return False
            old = sorted(sum(a*b for a, b in zip(p, tangent)) for p in track.surface_extent)
            new = sorted(sum(a*b for a, b in zip(p, tangent)) for p in surface_extent)
            # Shared plane alone is insufficient: adjacent distinct boxes can
            # have collinear faces. Require actual segment overlap.
            return min(old[1], new[1])-max(old[0], new[0]) >= .015
        candidates = [t for t in self.tracks if same_surface(t)]
        # Ambiguous association remains deferred rather than silently merging faces.
        if len(candidates) > 1:
            return 0
        if candidates:
            track = candidates[0]
            if tick < track.last_tick:
                return track.track_id
            weight = 1. / min(10, track.observations + 1)
            track.position = tuple((1. - weight) * a + weight * b for a, b in zip(track.position, position))
            track.normal_rad = wrap(track.normal_rad+weight*wrap(normal_rad-track.normal_rad))
        else:
            track = EvidenceTrack(self.next_id, tuple(position), normal_rad, sector)
            self.next_id += 1
            self.tracks.append(track)
        if surface_extent is not None:
            track.surface_extent = tuple(tuple(map(float, p)) for p in surface_extent)
            track.position_sigma_m = max(.001, float(position_sigma_m))
        # Exponential evidence permits correcting an early wrong classification.
        for label in OBJECT_CLASSES:
            track.evidence[label] = .8 * track.evidence.get(label, 0.) + max(0., float(class_probs.get(label, class_probs.get(label.upper(), 0.)))) * confidence
        track.support = .8 * track.support + confidence
        track.observations += 1
        track.last_tick, track.contradictions = tick, 0
        if sector_uncertain:
            track.sector = None
        elif sector:
            track.sector = sector
            self.coverage[sector] = self.coverage.get(sector, "partial")
        return track.track_id

    def contradict(self, track_id: int):
        """Repeated absence where an unobscured observation was expected can retract a FP."""
        for track in self.tracks:
            if track.track_id == track_id:
                track.support *= .5
                track.contradictions += 1
                if track.contradictions >= 3:
                    self.tracks.remove(track)
                break

    def transform_map(self, rotation_rad, translation, sector_for_position=None):
        """Move provisional tracks with a refined public map registration."""
        c, s = math.cos(rotation_rad), math.sin(rotation_rad)
        def transform(position):
            x, y = position
            return (c*x-s*y+translation[0], s*x+c*y+translation[1])
        for track in self.tracks:
            track.position = transform(track.position)
            track.normal_rad = wrap(track.normal_rad+rotation_rad)
            if track.surface_extent is not None:
                track.surface_extent = tuple(transform(p) for p in track.surface_extent)
            if sector_for_position is not None:
                track.sector = sector_for_position(track.position)

    def mark_coverage(self, sector: str, complete: bool = False):
        self.coverage[sector] = "complete" if complete else self.coverage.get(sector, "partial")

    def report(self) -> dict:
        inventories: dict[str, dict[str, int]] = {}
        for track in self.tracks:
            if track.sector and track.label and track.support >= .5:
                inventory = inventories.setdefault(track.sector, {})
                label = track.label.upper()
                inventory[label] = inventory.get(label, 0) + 1
        for sector, coverage in self.coverage.items():
            if coverage == "complete":
                inventories.setdefault(sector, {})
        return {"sectors": [{"sector": sector, "objects": [{"type": label, "count": count} for label, count in sorted(objects.items())]} for sector, objects in sorted(inventories.items())]}
