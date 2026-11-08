"""Image-only contour/template reference for generated fixture artwork.

This detector has no access to scenario entities, segmentation, original face
IDs or render annotations. Its public synthetic training templates are generated
locally from fixed vectors. It is a pipeline check, not a competition model.
"""
from __future__ import annotations

from typing import Any
import numpy as np

from maicon_sim.backends.bullet.asset_builder import OBJECT_LABELS, synthetic_image


def _corners(points: np.ndarray) -> np.ndarray:
    pts = np.asarray(points, dtype=np.float32).reshape(4, 2)
    center = pts.mean(axis=0)
    angle = np.arctan2(pts[:, 1] - center[1], pts[:, 0] - center[0])
    pts = pts[np.argsort(angle)]
    return np.roll(pts, -int(np.argmin(pts.sum(axis=1))), axis=0)


def _iou(a: list[float], b: list[float]) -> float:
    w = max(0., min(a[2], b[2])-max(a[0], b[0]))
    h = max(0., min(a[3], b[3])-max(a[1], b[1]))
    intersection = w*h
    return intersection / max(1e-12, (a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-intersection)


class SyntheticTemplateDetector:
    def __init__(self, threshold: float = .75, min_area_px: float = 256., nms_iou: float = .5):
        import cv2
        self.cv2 = cv2
        self.threshold = float(threshold)
        self.min_area_px = float(min_area_px)
        self.nms_iou = float(nms_iou)
        self.templates: dict[str, np.ndarray] = {}
        for label in OBJECT_LABELS:
            pixels = np.asarray(synthetic_image(label).convert('L'))[16:496, 16:496]
            self.templates[label] = cv2.resize(pixels, (128, 128), interpolation=cv2.INTER_AREA)

    def detect(self, bgr: np.ndarray) -> list[dict[str, Any]]:
        cv2 = self.cv2
        if bgr.dtype != np.uint8 or bgr.ndim != 3 or bgr.shape[2] != 3:
            raise ValueError('VisionCallback expects uint8 HxWx3 BGR pixels')
        gray = cv2.cvtColor(np.ascontiguousarray(bgr), cv2.COLOR_BGR2GRAY)
        otsu, _ = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
        # Detect the common black border, not the illuminated gray wall/floor.
        _, dark = cv2.threshold(gray, min(80., float(otsu)), 255, cv2.THRESH_BINARY_INV)
        contours, _ = cv2.findContours(dark, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        candidates: list[dict[str, Any]] = []
        destination = np.float32([[0, 0], [127, 0], [127, 127], [0, 127]])
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < self.min_area_px: continue
            corners = cv2.approxPolyDP(contour, .025*cv2.arcLength(contour, True), True)
            if len(corners) != 4 or not cv2.isContourConvex(corners): continue
            corners = _corners(corners)
            edges = np.roll(corners, -1, axis=0)-corners
            lengths = np.linalg.norm(edges, axis=1)
            if min(lengths) < 4: continue
            cosines = np.sum(edges*np.roll(-edges, 1, axis=0), axis=1)/(lengths*np.roll(lengths, 1))
            if np.any(np.abs(cosines) > .85): continue
            warp = cv2.warpPerspective(gray, cv2.getPerspectiveTransform(corners, destination), (128,128))
            scores = []
            for template in self.templates.values():
                scores.append(max(float(cv2.matchTemplate(warp, np.rot90(template, k).copy(), cv2.TM_CCOEFF_NORMED)[0,0]) for k in range(4)))
            maximum = max(scores)
            if maximum < self.threshold: continue
            probabilities = np.exp((np.asarray(scores)-maximum)/.1)
            probabilities /= probabilities.sum()
            x,y,w,h = cv2.boundingRect(corners)
            bbox = [float(x), float(y), float(min(x+w,bgr.shape[1])), float(min(y+h,bgr.shape[0]))]
            candidates.append({'kind':'object', 'bbox_xyxy_px':bbox,
                'class_probs':dict(zip(self.templates, map(float, probabilities))),
                'confidence':float(maximum)})
        selected: list[dict[str, Any]] = []
        for candidate in sorted(candidates, key=lambda a:(-a['confidence'],a['bbox_xyxy_px'])):
            if all(_iou(candidate['bbox_xyxy_px'], old['bbox_xyxy_px']) <= self.nms_iou for old in selected):
                selected.append(candidate)
        return selected

    __call__ = detect

    def process(self, frame: dict[str, Any]) -> dict[str, Any]:
        data = frame['data']
        return {k:frame[k] for k in ('sequence','captured_tick','received_tick','camera_id','width_px','height_px')} | {'detections':self.detect(data)}
