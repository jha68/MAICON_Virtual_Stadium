"""Public-map waypoint policies, with no direct world mutation."""
from __future__ import annotations

import math


def base_goal(public_map: dict, objective: str | None):
    for base in public_map.get("bases", []):
        if base.get("code") == objective:
            polygon = base["polygon_xy_m"]
            return tuple(sum(p[i] for p in polygon) / len(polygon) for i in (0, 1))
    return None


def nominal_pose(public_map: dict, slot: str):
    starts = public_map.get("nominal_starts", [])
    if isinstance(starts, dict):
        value = starts.get(slot, {})
        value = value.get("pose", value)
    else:
        value = next((s.get("pose", s.get("nominal_start_pose", {})) for s in starts if s.get("slot") == slot), {})
    if not value:
        # A missing nominal prior is not replaced with a privileged actual pose.
        return None
    return value["x_m"], value["y_m"], value["yaw_rad"]


class WaypointPolicy:
    def __init__(self, public_map: dict, slot: str, name: str):
        self.name, self.public_map, self.slot = name, public_map, slot
        self.index = 0
        # Defaults are publicly derived sector centroids, never hidden box positions.
        camp_prefix = "R-" if slot.startswith("B") else "B-"
        self.points = []
        for sector in public_map.get("sectors", []):
            if sector["sector_id"].startswith(camp_prefix) or sector["sector_id"] == "CM":
                polygon = sector["polygon_xy_m"]
                self.points.append(tuple(sum(p[i] for p in polygon) / len(polygon) for i in (0, 1)))
        self.arrived_tick = None

    def goal(self, pose, tick, target):
        objective = target.get("order", {}).get("objective") if target and target.get("accepted") else None
        if self.name == "capture_runner":
            return base_goal(self.public_map, objective)
        if not self.points:
            return None
        point = self.points[self.index % len(self.points)]
        if math.dist(pose[:2], point) < .08:
            if self.name == "blocker":
                self.arrived_tick = self.arrived_tick or tick
                if tick - self.arrived_tick < 500:
                    return point
                self.arrived_tick = None
            self.index += 1
            point = self.points[self.index % len(self.points)]
        return point
