"""Participant-side time alignment and planar surface evidence.

Only public camera/odom/LiDAR/calibration data enter these helpers. Entity IDs,
simulator poses, segmentation, and evaluator annotations are never inputs.
"""
from __future__ import annotations

from bisect import bisect_left
from collections import defaultdict
import copy
from dataclasses import dataclass
import math
import threading

import numpy as np

from .planning import inside_polygon, wrap
from .localization import PublicWallLocalizer


class ObservationHistory:
    """Bounded, capture-time ordered odometry and scan history.

    Holding the newest observation is allowed only within one odometry period.
    Missing old poses are rejected rather than using today's pose for an old RGB.
    """
    def __init__(self, capacity=512, max_pose_gap_ticks=20, max_extrapolation_ticks=5):
        self.capacity = capacity
        self.max_pose_gap_ticks = max_pose_gap_ticks
        self.max_extrapolation_ticks = max_extrapolation_ticks
        self.frames = defaultdict(list)
        self._lock = threading.RLock()

    def add(self, observations):
        for channel in ("odom", "scan"):
            frame = observations.get(channel)
            if not isinstance(frame, dict) or type(frame.get("captured_tick")) is not int:
                continue
            tick = frame["captured_tick"]
            item = (tick, copy.deepcopy(frame))
            with self._lock:
                samples = self.frames[channel]
                index = bisect_left([item[0] for item in samples], tick)
                if index < len(samples) and samples[index][0] == tick:
                    samples[index] = item
                else:
                    samples.insert(index, item)
                del samples[:-self.capacity]

    def pose_at(self, tick, nominal_start):
        with self._lock:
            samples = list(self.frames["odom"])
        if not samples or nominal_start is None:
            return None
        index = bisect_left([item[0] for item in samples], tick)
        if index < len(samples) and samples[index][0] == tick:
            local = self._local(samples[index][1])
        elif 0 < index < len(samples):
            left, right = samples[index-1], samples[index]
            if right[0]-left[0] > self.max_pose_gap_ticks:
                return None
            a, b = self._local(left[1]), self._local(right[1])
            if a is None or b is None:
                return None
            fraction = (tick-left[0])/(right[0]-left[0])
            local = (a[0]+fraction*(b[0]-a[0]), a[1]+fraction*(b[1]-a[1]), wrap(a[2]+fraction*wrap(b[2]-a[2])))
        else:
            nearest = samples[0] if index == 0 else samples[-1]
            if abs(tick-nearest[0]) > self.max_extrapolation_ticks:
                return None
            local = self._local(nearest[1])
            # A short endpoint hold is preferable to extrapolating an unknown
            # command across a device lock or abrupt stop.
        if local is None:
            return None
        x, y, yaw = nominal_start
        c, s = math.cos(yaw), math.sin(yaw)
        return (x+c*local[0]-s*local[1], y+s*local[0]+c*local[1], wrap(yaw+local[2]))

    @staticmethod
    def _local(frame):
        value = frame.get("local_pose", frame.get("pose", {}))
        if not all(type(value.get(k)) in (int, float) and math.isfinite(value[k]) for k in ("x_m", "y_m", "yaw_rad")):
            return None
        return tuple(value[k] for k in ("x_m", "y_m", "yaw_rad"))

    def scan_at(self, tick, max_age_ticks=10):
        with self._lock:
            samples = list(self.frames["scan"])
        if not samples:
            return None
        nearest = min(samples, key=lambda item: (abs(item[0]-tick), item[0] > tick))
        return nearest[1] if abs(nearest[0]-tick) <= max_age_ticks else None


class GimbalHistory:
    """Capture-time gimbal rate estimates from accepted public commands."""
    def __init__(self, capacity=256):
        self.capacity = capacity
        self.commands = [(0, 0., 0., 0., 0., 90., True)]
        self._lock = threading.RLock()

    def _sample(self, tick):
        with self._lock:
            commands = [command for command in self.commands if command[0] <= tick]
        if not commands:
            return None
        at, pan, tilt, target_pan, target_tilt, speed, certain = commands[-1]
        dt = (tick-at)*.01
        values = []
        for current, target, unit in ((pan, target_pan, .5), (tilt, target_tilt, .15)):
            maximum = speed*dt/unit
            values.append(current+max(-maximum, min(maximum, target-current)))
        return tuple(values), certain

    def at(self, tick):
        value = self._sample(tick)
        return value[0] if value and value[1] else None

    def command(self, pan, tilt, speed, tick):
        with self._lock:
            if self.commands and tick < self.commands[-1][0]:
                return
            current = self._sample(tick)
            position = current[0] if current else (0., 0.)
            self.commands.append((tick, *position, pan, tilt, speed, True))
            del self.commands[:-self.capacity]

    def cancel(self, tick):
        with self._lock:
            if self.commands and tick < self.commands[-1][0]:
                return
            value = self._sample(tick)
            position = value[0] if value else (0., 0.)
            self.commands.append((tick, *position, *position, 90., False))
            del self.commands[:-self.capacity]


def _rotation(yaw):
    c, s = math.cos(yaw), math.sin(yaw)
    return np.array([[c, -s], [s, c]])


def certain_sector(point, sectors, uncertainty_m=.04):
    """Withhold a sector when the uncertainty disc crosses any boundary."""
    def segment_distance(p, a, b):
        p, a, b = np.asarray(p), np.asarray(a), np.asarray(b)
        length = float(np.dot(b-a, b-a))
        t = 0. if length == 0 else float(np.clip(np.dot(p-a, b-a)/length, 0., 1.))
        return float(np.linalg.norm(p-a-t*(b-a)))
    candidates = []
    for sector in sectors:
        polygon = sector["polygon_xy_m"]
        if inside_polygon(point, polygon):
            distance = min(segment_distance(point, a, b) for a, b in zip(polygon, polygon[1:]+polygon[:1]))
            if distance > uncertainty_m:
                candidates.append(sector["sector_id"])
    return candidates[0] if len(candidates) == 1 else None


@dataclass(frozen=True)
class SurfaceEstimate:
    position: tuple[float, float]
    normal_rad: float
    extent: tuple[tuple[float, float], tuple[float, float]]
    sigma_m: float


def estimate_surface(detection, camera_pose, scan_pose, scan, calibration, pan=0., tilt=0.):
    """Intersect a calibrated camera bearing with a measured LiDAR face plane.

    Fits a contiguous planar LiDAR segment and uses its midpoint as the physical
    surface centre. A surface normal does not rotate with the viewing bearing.
    No depth or segmentation image is used.
    """
    camera = calibration.get("front_camera", calibration.get("intrinsics", {}))
    fx, fy = camera.get("fx_px", 320.), camera.get("fy_px", 320.)
    cx, cy = camera.get("cx_px", 319.5), camera.get("cy_px", 239.5)
    bbox = detection.get("bbox_xyxy_px", [])
    if len(bbox) != 4 or fx <= 0 or fy <= 0:
        return None
    pixel = (bbox[0]+bbox[2])/2
    vertical = (bbox[1]+bbox[3])/2
    yaw, pitch = -math.radians(.5*pan), -math.radians(.15*tilt)
    cp, sp = math.cos(pitch), math.sin(pitch)
    # Optical (right, down, forward) -> body (forward, left, up).
    ray = np.array([1., -(pixel-cx)/fx, -(vertical-cy)/fy])
    ray = np.array([cp*ray[0]+sp*ray[2], ray[1], -sp*ray[0]+cp*ray[2]])
    ray[:2] = _rotation(yaw)@ray[:2]
    direction = _rotation(camera_pose[2])@ray[:2]
    if np.linalg.norm(direction) < 1e-6:
        return None
    direction /= np.linalg.norm(direction)
    pivot = np.asarray(calibration.get("gimbal_pivot_m", [.02, 0., .23]))
    offset = np.asarray(calibration.get("camera_offset_gimbal_m", [.025, 0., 0.]))
    offset = np.array([cp*offset[0]+sp*offset[2], offset[1], -sp*offset[0]+cp*offset[2]])
    origin = np.array(camera_pose[:2])+_rotation(camera_pose[2])@(pivot[:2]+_rotation(yaw)@offset[:2])
    lidar_origin = np.asarray(calibration.get("lidar", {}).get("origin_body_m", [0., 0., 0.]))[:2]
    scan_origin = np.array(scan_pose[:2])+_rotation(scan_pose[2])@lidar_origin
    ranges = scan.get("ranges_m", [])
    if not ranges:
        return None
    increment = scan.get("angle_increment_rad", 2*math.pi/len(ranges))
    minimum = scan.get("angle_min_rad", -math.pi)
    if increment <= 0:
        return None
    bearing = wrap(math.atan2(direction[1], direction[0])-scan_pose[2])
    angles = minimum+np.arange(len(ranges))*increment
    offsets = np.arctan2(np.sin(angles-bearing), np.cos(angles-bearing))
    index = int(np.argmin(np.abs(offsets)))
    def point(i):
        if not 0 <= i < len(ranges):
            return None
        distance = ranges[i]
        if type(distance) not in (int, float) or not math.isfinite(distance) or distance <= 0:
            return None
        return scan_origin+_rotation(scan_pose[2])@np.array([math.cos(angles[i])*distance, math.sin(angles[i])*distance])
    if point(index) is None:
        return None
    # Start at the image-centre ray, then grow one plane. Fitting the entire
    # image width initially can mix two sides of a cube at an oblique view.
    indices = list(range(max(0, index-1), min(len(ranges), index+2)))
    points = [(i, point(i)) for i in indices]
    points = [(i, p) for i, p in points if p is not None]
    if len(points) < 3:
        return None
    # A foreground/background jump must not be averaged into a false plane.
    center_point = point(index)
    points = [(i, p) for i, p in points if np.linalg.norm(p-center_point) < .5]
    if len(points) < 3:
        return None
    cloud = np.array([p for _, p in points])
    center = np.mean(cloud, axis=0)
    _, values, vectors = np.linalg.svd(cloud-center, full_matrices=False)
    normal, tangent = vectors[-1], vectors[0]
    if np.max(np.abs((cloud-center)@normal)) > .015 or values[0] < .025:
        return None
    # Extend along the fitted face until its geometric corner/occluder. This
    # provides stable physical extents as the view angle changes.
    left, right = min(i for i, _ in points), max(i for i, _ in points)
    for step in (-1, 1):
        edge = left if step < 0 else right
        previous = point(edge)
        for i in range(edge+step, edge+step*61, step):
            p = point(i)
            if p is None or np.linalg.norm(p-previous) > .15 or abs(np.dot(p-center, normal)) > .02:
                break
            points.append((i, p)); previous = p
    cloud = np.array([p for _, p in points])
    if np.dot(normal, origin-center) < 0:
        normal = -normal
    denom = float(np.dot(normal, direction))
    if abs(denom) < .15:
        return None
    distance = float(np.dot(normal, center-origin)/denom)
    if distance <= 0:
        return None
    hit = origin+distance*direction
    projection = (cloud-center)@tangent
    lo, hi = projection.min(), projection.max()
    along = float(np.dot(hit-center, tangent))
    if not lo-.08 <= along <= hi+.08:
        return None
    extent = (center+lo*tangent, center+hi*tangent)
    midpoint = (extent[0]+extent[1])/2
    sigma = max(.015, float(np.sqrt(np.mean(((cloud-center)@normal)**2)))+.015)
    return SurfaceEstimate(tuple(map(float, midpoint)), math.atan2(normal[1], normal[0]),
                           tuple(tuple(map(float, p)) for p in extent), sigma)


class SurfaceMapper:
    def __init__(self, public_map, calibration, slot):
        self.public_map, self.calibration, self.slot = public_map, calibration, slot
        start = next((s["pose"] for s in public_map.get("nominal_starts", []) if s["slot"] == slot), None)
        self.nominal_start = tuple(start[k] for k in ("x_m", "y_m", "yaw_rad")) if start else None
        self.localizer = PublicWallLocalizer(public_map.get("bounds", {"width_m": 6.12, "height_m": 5.}))
        self._localized_scan_tick = None
        self._last_frame_tick = None
        self._wall_registered = False
        self._track_map_correction = (0., 0., 0.)

    def correct_pose(self, raw_pose, scan=None):
        if raw_pose is None:
            return None
        if scan is not None and scan.get("captured_tick") != self._localized_scan_tick:
            self.localizer.update(raw_pose, scan, self.calibration.get("lidar", {}).get("origin_body_m", [0., 0.])[:2])
            self._wall_registered = self._wall_registered or self.localizer.diagnostics.get("accepted", False)
            self._localized_scan_tick = scan.get("captured_tick")
        return self.localizer.apply(raw_pose)

    def observe(self, frame, history, gimbal, tracker):
        captured = frame.get("captured_tick")
        if type(captured) is not int:
            return {"mapped": 0, "reason": "missing_capture_time"}
        if self._last_frame_tick is not None and captured <= self._last_frame_tick:
            return {"mapped": 0, "reason": "old_camera_frame"}
        raw_pose = history.pose_at(captured, self.nominal_start)
        scan = history.scan_at(captured)
        angles = gimbal.at(captured)
        if raw_pose is None or scan is None or angles is None:
            return {"mapped": 0, "reason": "unsynchronized_public_sensors"}
        scan_pose = history.pose_at(scan["captured_tick"], self.nominal_start)
        if scan_pose is None:
            return {"mapped": 0, "reason": "scan_pose_unavailable"}
        self._last_frame_tick = captured
        self.correct_pose(scan_pose, scan)
        correction = self.localizer.correction
        if any(abs(a-b) > 1e-6 for a, b in zip(correction, self._track_map_correction)):
            previous = self._track_map_correction
            delta_yaw = wrap(correction[2]-previous[2])
            translation = np.array(correction[:2])-_rotation(delta_yaw)@np.array(previous[:2])
            tracker.transform_map(delta_yaw, translation,
                                  lambda p: certain_sector(p, self.public_map.get("sectors", []), .04))
            self._track_map_correction = correction
        pose, scan_pose = self.localizer.apply(raw_pose), self.localizer.apply(scan_pose)
        mapped, deferred = 0, 0
        for detection in frame.get("detections", []):
            if detection.get("kind") != "object":
                continue
            estimate = estimate_surface(detection, pose, scan_pose, scan, self.calibration, *angles)
            if estimate is None:
                deferred += 1
                continue
            # A nominal start is a prior, not a measured global pose. Keep a
            # wider boundary margin until public walls constrain the map frame.
            pose_uncertainty = .02 if self._wall_registered else .10
            sector = certain_sector(estimate.position, self.public_map.get("sectors", []),
                                    max(estimate.sigma_m*2, pose_uncertainty))
            identifier = tracker.observe(estimate.position, estimate.normal_rad, detection["class_probs"], captured,
                                         sector, detection.get("confidence", 1.), surface_extent=estimate.extent,
                                         position_sigma_m=estimate.sigma_m, sector_uncertain=sector is None)
            mapped += bool(identifier)
        return {"mapped": mapped, "deferred": deferred, "localization": dict(self.localizer.diagnostics)}
