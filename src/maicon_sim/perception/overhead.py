"""Pixel-only overhead SIM model; requires a published camera calibration.

Colour/height/size priors describe the synthetic fixture, not trained real-world
perception. No segmentation, entity IDs, poses or annotations enter this module.
"""
import math

import numpy as np


class OverheadProjection:
    def __init__(self, camera):
        self.width, self.height = camera['width_px'], camera['height_px']
        self.origin = np.asarray(camera['position_world_m'], dtype=float)
        forward = np.asarray(camera['look_at_world_m'], dtype=float) - self.origin
        length = np.linalg.norm(forward)
        if not np.isfinite(length) or length < 1e-8:
            raise ValueError('invalid overhead camera direction')
        forward /= length
        right = np.cross(forward, camera['up_world'])
        length = np.linalg.norm(right)
        if not np.isfinite(length) or length < 1e-8:
            raise ValueError('invalid overhead camera up vector')
        right /= length
        down = np.cross(forward, right)
        self.rotation = np.column_stack((right, down, forward))
        self.fx = self.width / (2 * math.tan(math.radians(camera['hfov_deg']) / 2))
        if not np.isfinite(self.rotation).all() or not math.isfinite(self.fx) or self.fx <= 0:
            raise ValueError('invalid overhead calibration')

    def intersect(self, pixels, height_m):
        pixels = np.asarray(pixels, dtype=float).reshape(-1, 2)
        if not np.isfinite(pixels).all() or np.any(pixels < 0) or np.any(pixels >= [self.width, self.height]):
            return None
        rays = np.column_stack(((pixels[:, 0]-(self.width-1)/2)/self.fx,
                                (pixels[:, 1]-(self.height-1)/2)/self.fx, np.ones(len(pixels)))) @ self.rotation.T
        if np.any(np.abs(rays[:, 2]) < 1e-8):
            return None
        distances = (height_m-self.origin[2])/rays[:, 2]
        if np.any(distances <= 0):
            return None
        return (self.origin + distances[:, None]*rays)[:, :2]


class OverheadPixelDetector:
    """Conservative rectangular box tops and coloured UGV bodies, no call signs.

    A top-down body colour cannot reveal band count, HP, ammo, receiver position,
    or heading sign. Ambiguous candidates remain anonymous navigation hazards.
    """
    def __init__(self, camera):
        import cv2
        self.cv2 = cv2
        self.projection = OverheadProjection(camera)

    def detect(self, bgr):
        cv2, projection = self.cv2, self.projection
        if bgr.shape != (projection.height, projection.width, 3) or bgr.dtype != np.uint8:
            raise ValueError('overhead frame differs from its calibration')
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        detections = []
        masks = [('obstacle', None, (hsv[..., 1] > 15) & (hsv[..., 1] < 70) & (hsv[..., 2] > 45) & (hsv[..., 2] < 95), .4),
                 ('ugv', 'BLUE', (hsv[..., 0] > 100) & (hsv[..., 0] < 130) & (hsv[..., 1] > 140) & (hsv[..., 2] > 45), .13),
                 ('ugv', 'RED', ((hsv[..., 0] < 9) | (hsv[..., 0] > 173)) & (hsv[..., 1] > 140) & (hsv[..., 2] > 45), .13)]
        for kind, camp, mask, height in masks:
            if kind == 'obstacle':
                mask = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
            if kind == 'ugv':
                mask = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)))
            contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for contour in contours:
                area = cv2.contourArea(contour)
                if area < (150 if kind == 'obstacle' else 25):
                    continue
                rectangle = cv2.minAreaRect(contour)
                pixels = cv2.boxPoints(rectangle)
                points = projection.intersect(pixels, height)
                if points is None:
                    continue
                sides = np.linalg.norm(points-np.roll(points, 1, axis=0), axis=1)
                long, short = float(max(sides)), float(min(sides))
                fill = area / max(1., rectangle[1][0]*rectangle[1][1])
                if kind == 'obstacle':
                    if not (.32 <= short <= long <= 1. and fill > .6):
                        continue
                    outline = cv2.approxPolyDP(contour, 7., True).reshape(-1, 2)
                    if not 4 <= len(outline) <= 16:
                        continue
                    detections.append({'kind': kind, 'confidence': .8, 'surface_polygon_px': outline.tolist(),
                                       'projection_plane_z_m': height})
                elif .07 <= short <= long <= .36 and long >= .12 and fill > .4:
                    x, y, w, h = cv2.boundingRect(contour)
                    detections.append({'kind': kind, 'confidence': .8, 'camp_observation': camp,
                                       'bbox_xyxy_px': [x, y, x+w, y+h],
                                       'navigation_point_px': list(rectangle[0]), 'projection_plane_z_m': height,
                                       'view_model': 'overhead'})
        return detections
