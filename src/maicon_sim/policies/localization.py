"""Conservative scan registration against the public rectangular arena boundary.

This is a bounded correction to nominal-start odometry, not general SLAM. Only
long, straight returns near two orthogonal known walls can update the map frame;
short box faces, absent returns and ambiguous observations leave it unchanged.
"""
from __future__ import annotations

import math

import numpy as np

from .planning import wrap


def _rotation(angle):
    c, s = math.cos(angle), math.sin(angle)
    return np.array([[c, -s], [s, c]])


def _axis_angle(angle):
    """An unoriented line angle lives modulo pi."""
    return (angle + math.pi/2) % math.pi - math.pi/2


def _weighted_median(values, weights):
    order = np.argsort(values)
    values, weights = np.asarray(values)[order], np.asarray(weights)[order]
    return float(values[np.searchsorted(np.cumsum(weights), weights.sum()/2)])


class PublicWallLocalizer:
    def __init__(self, bounds, max_translation_m=.25, max_yaw_rad=.15):
        self.width = float(bounds.get("width_m", 0.))
        self.height = float(bounds.get("height_m", 0.))
        self.max_translation_m = float(max_translation_m)
        self.max_yaw_rad = float(max_yaw_rad)
        self.correction = (0., 0., 0.)
        self.diagnostics = {"accepted": False, "reason": "not_observed"}
        self._last_stamp = None

    def apply(self, pose):
        tx, ty, theta = self.correction
        xy = _rotation(theta) @ np.asarray(pose[:2], dtype=float) + [tx, ty]
        return float(xy[0]), float(xy[1]), wrap(float(pose[2])+theta)

    def _segments(self, body_points, valid, pose):
        world = body_points @ _rotation(pose[2]).T + np.asarray(pose[:2])
        gate = self.max_translation_m + .35
        distances = np.column_stack((abs(world[:, 0]), abs(world[:, 0]-self.width),
                                     abs(world[:, 1]), abs(world[:, 1]-self.height)))
        labels = np.argmin(distances, axis=1)
        close = distances[np.arange(len(world)), labels] <= gate
        inside = ((world[:, 0] >= -gate) & (world[:, 0] <= self.width+gate)
                  & (world[:, 1] >= -gate) & (world[:, 1] <= self.height+gate))
        labels[~(valid & close & inside)] = -1
        groups = []
        current = []
        for index, label in enumerate(labels):
            if current and (label != labels[current[-1]] or
                            np.linalg.norm(world[index]-world[current[-1]]) > .25):
                groups.append(current)
                current = []
            if label >= 0:
                current.append(index)
        if current:
            groups.append(current)
        # The first/last rays can be adjacent in a full-circle scan.
        if len(groups) > 1 and groups[0][0] == 0 and groups[-1][-1] == len(labels)-1:
            if labels[0] == labels[-1] and np.linalg.norm(world[0]-world[-1]) <= .25:
                groups[0] = groups[-1]+groups[0]
                groups.pop()
        result = []
        for group in groups:
            if len(group) < 5:
                continue
            points = world[group]
            centered = points-points.mean(axis=0)
            _, _, vectors = np.linalg.svd(centered, full_matrices=False)
            tangent, normal = vectors[0], vectors[1]
            span = float(np.ptp(centered @ tangent))
            residual = float(np.sqrt(np.mean((centered @ normal)**2)))
            # Official fixture boxes have 0.4m faces. Requiring a much longer
            # contiguous line avoids treating those faces as the arena wall.
            if span < .65 or residual > .025:
                continue
            label = int(labels[group[0]])
            expected_angle = math.pi/2 if label < 2 else 0.
            yaw_delta = _axis_angle(expected_angle-math.atan2(tangent[1], tangent[0]))
            if abs(yaw_delta) > self.max_yaw_rad:
                continue
            result.append({"label": label, "indices": group, "weight": span,
                           "yaw_delta": yaw_delta, "residual_m": residual})
        return result

    def update(self, pose, scan, lidar_origin_body_m=(0., 0.)):
        """Return corrected pose; retain the previous transform on weak evidence.

        ``pose`` must be the *uncorrected* nominal-start/odometry estimate at
        this scan's capture time. ``correction`` is a persistent SE(2) transform
        (tx, ty, yaw_delta) mapping that odometry map frame into the public map.
        """
        corrected = self.apply(pose)
        self.diagnostics = {"accepted": False, "reason": "insufficient_wall_support"}
        if self.width <= 0 or self.height <= 0:
            self.diagnostics["reason"] = "public_bounds_unavailable"
            return corrected
        if not isinstance(scan, dict):
            self.diagnostics["reason"] = "scan_unavailable"
            return corrected
        stamp = scan.get("captured_tick", scan.get("sequence"))
        if stamp is not None and self._last_stamp is not None and stamp <= self._last_stamp:
            self.diagnostics["reason"] = "old_scan"
            return corrected
        if stamp is not None:
            self._last_stamp = stamp
        ranges = scan.get("ranges_m", [])
        if len(ranges) < 10:
            return corrected
        distances = np.asarray([float(v) if v is not None else np.nan for v in ranges])
        valid = np.isfinite(distances) & (distances > scan.get("range_min_m", .01))
        valid &= distances <= scan.get("range_max_m", math.inf)
        angles = scan.get("angle_min_rad", -math.pi)+np.arange(len(ranges))*scan.get("angle_increment_rad", 2*math.pi/len(ranges))
        body_points = np.column_stack((np.cos(angles), np.sin(angles))) * np.where(valid, distances, 0.)[:, None]
        body_points += np.asarray(lidar_origin_body_m[:2])
        segments = self._segments(body_points, valid, corrected)
        if not {0, 1}.issubset({int(s["label"] >= 2) for s in segments}):
            return corrected
        yaw_delta = _weighted_median([s["yaw_delta"] for s in segments], [s["weight"] for s in segments])
        if any(abs(_axis_angle(s["yaw_delta"]-yaw_delta)) > .035 for s in segments):
            self.diagnostics["reason"] = "inconsistent_wall_directions"
            return corrected
        projected = body_points @ _rotation(corrected[2]+yaw_delta).T + np.asarray(corrected[:2])
        dx_values, dx_weights, dy_values, dy_weights = [], [], [], []
        for segment in segments:
            label = segment["label"]
            points = projected[segment["indices"]]
            if label < 2:
                dx_values.append((0. if label == 0 else self.width)-float(np.median(points[:, 0])))
                dx_weights.append(segment["weight"])
            else:
                dy_values.append((0. if label == 2 else self.height)-float(np.median(points[:, 1])))
                dy_weights.append(segment["weight"])
        dx, dy = _weighted_median(dx_values, dx_weights), _weighted_median(dy_values, dy_weights)
        if math.hypot(dx, dy) > self.max_translation_m:
            self.diagnostics["reason"] = "correction_exceeds_bound"
            return corrected
        residuals = []
        for segment in segments:
            points = projected[segment["indices"]]+[dx, dy]
            label = segment["label"]
            residuals.extend((points[:, 0]-(0. if label == 0 else self.width)) if label < 2
                             else (points[:, 1]-(0. if label == 2 else self.height)))
        residual = float(np.sqrt(np.mean(np.asarray(residuals)**2)))
        if residual > .035:
            self.diagnostics["reason"] = "inconsistent_wall_positions"
            return corrected
        next_pose = (corrected[0]+dx, corrected[1]+dy, wrap(corrected[2]+yaw_delta))
        if not (0. < next_pose[0] < self.width and 0. < next_pose[1] < self.height):
            self.diagnostics["reason"] = "pose_outside_public_bounds"
            return corrected
        # Compose a map-frame rigid correction, so future odometry translations
        # are rotated consistently with the corrected heading.
        theta = wrap(next_pose[2]-float(pose[2]))
        translation = np.asarray(next_pose[:2])-_rotation(theta) @ np.asarray(pose[:2])
        self.correction = float(translation[0]), float(translation[1]), theta
        self.diagnostics = {"accepted": True, "reason": "orthogonal_public_walls",
                            "segments": len(segments), "inliers": len(residuals),
                            "residual_m": residual, "translation_step_m": math.hypot(dx, dy),
                            "yaw_step_rad": yaw_delta}
        return next_pose
