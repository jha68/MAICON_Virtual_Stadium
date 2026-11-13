"""Geometry helpers derived only from the public map."""
from __future__ import annotations



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
