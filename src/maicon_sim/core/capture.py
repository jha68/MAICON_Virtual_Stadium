"""Sensor timestamp / arrival arbitration, with explicit SIM transport assumptions."""
from __future__ import annotations

import hashlib

from .geometry2d import footprint, segment_intersects_polygon, wrap_angle
from .types import Pose2


def crossing_fraction(before, after, segment, geometry):
    """Locate a footprint's first rising edge inside a 10ms motion interval."""
    length, width = geometry['footprint_length_m'], geometry['footprint_width_m']
    def blocked(fraction):
        pose = Pose2(before.x_m + (after.x_m-before.x_m)*fraction,
                     before.y_m + (after.y_m-before.y_m)*fraction,
                     before.yaw_rad + wrap_angle(after.yaw_rad-before.yaw_rad)*fraction)
        return segment_intersects_polygon(segment, footprint(pose, length, width))
    if blocked(0.):
        return None
    if not blocked(1.):
        return None
    low, high = 0., 1.
    for _ in range(24):
        middle = (low+high)/2
        if blocked(middle):
            high = middle
        else:
            low = middle
    return high


def event_nonce(seed, base, detected_ms):
    # Only an exact arrival tie needs a deterministic SIM fallback; never base_id order.
    return hashlib.sha256(f'{seed}/{base}/{detected_ms:.6f}'.encode()).hexdigest()


def select_capture(events, tolerance_ms=10.):
    if not events:
        return None
    earliest = min(event['detected_ms'] for event in events)
    tied = [event for event in events if event['detected_ms']-earliest <= tolerance_ms+1e-9]
    return min(tied, key=lambda event: (event['arrived_ms'], event['nonce']))
