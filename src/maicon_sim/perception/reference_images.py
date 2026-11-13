"""Image-only recognition of the supplied printed panels.

These public reference images are a closed-set baseline, not evidence of
generalisation to unseen competition artwork. No scenario/renderer data enter.
"""
from importlib.resources import files

import numpy as np

from .synthetic_template import _iou


class ReferenceImageDetector:
    def __init__(self, calibration=None):
        import cv2
        self.cv2, self.calibration = cv2, calibration or {}
        self.sift = cv2.SIFT_create(nfeatures=1200, contrastThreshold=.018, edgeThreshold=12)
        self.matcher = cv2.BFMatcher(cv2.NORM_L2)
        root = files('maicon_sim').joinpath('resources/examples/prestudy')
        self.templates = []
        for path in sorted(root.iterdir(), key=lambda p:p.name):
            if path.suffix != '.png':
                continue
            kind, label = path.stem.split('_', 1)
            # M5 wall artwork is not an M2 target or an M3 object report.
            if kind not in ('facility', 'object', 'decoy'):
                continue
            pixels = cv2.imdecode(np.frombuffer(path.read_bytes(), np.uint8), cv2.IMREAD_GRAYSCALE)
            pixels = cv2.resize(pixels, (256, 256))
            keypoints, descriptors = self.sift.detectAndCompute(pixels, None)
            self.templates.append((kind, label, keypoints, descriptors))

    def detect(self, bgr):
        cv2 = self.cv2
        if bgr.dtype != np.uint8 or bgr.ndim != 3 or bgr.shape[2] != 3:
            raise ValueError('uint8 BGR image required')
        gray = cv2.cvtColor(np.ascontiguousarray(bgr), cv2.COLOR_BGR2GRAY)
        points, descriptors = self.sift.detectAndCompute(gray, None)
        if descriptors is None or len(points) < 6:
            return []
        detections = []
        for kind, label, reference, template in self.templates:
            if template is None:
                continue
            pairs = self.matcher.knnMatch(descriptors, template, k=2)
            matches = [a for pair in pairs if len(pair) == 2 for a,b in [pair] if a.distance < .73*b.distance]
            for _ in range(6):
                if len(matches) < 6:
                    break
                source = np.float32([reference[m.trainIdx].pt for m in matches])
                target = np.float32([points[m.queryIdx].pt for m in matches])
                transform, mask = cv2.findHomography(source, target, cv2.RANSAC, 2.5)
                if transform is None or mask is None:
                    break
                keep = mask.ravel().astype(bool)
                used = int(keep.sum())
                if used < 6:
                    break
                confidence = min(.98, .65+.025*used)
                quad = cv2.perspectiveTransform(np.float32([[[0,0],[255,0],[255,255],[0,255]]]), transform)[0]
                matches = [m for m, good in zip(matches, keep) if not good]
                if not np.isfinite(quad).all() or not cv2.isContourConvex(quad):
                    continue
                area = abs(cv2.contourArea(quad))
                sides = np.linalg.norm(quad-np.roll(quad, 1, axis=0), axis=1)
                # Reject tiny, near-collinear and implausibly extrapolated fits.
                if area < 225 or area > gray.size*.8 or sides.min() < 10 or sides.max()/sides.min() > 5:
                    continue
                hull = cv2.convexHull(source[keep])
                if abs(cv2.contourArea(hull)) < 256*256*.045:
                    continue
                low, high = quad.min(axis=0), quad.max(axis=0)
                if low[0] < -3 or low[1] < -3 or high[0] > gray.shape[1]+3 or high[1] > gray.shape[0]+3:
                    continue
                box = [float(max(0,low[0])),float(max(0,low[1])),float(min(gray.shape[1],high[0])),float(min(gray.shape[0],high[1]))]
                item = {'kind': kind, 'bbox_xyxy_px':box, 'class_probs':{label:1.},
                        'confidence':confidence, 'source':'public_prestudy_image',
                        'panel_corners_px':quad.tolist()}
                if kind == 'facility':
                    self._facility(bgr, item, transform)
                detections.append(item)
        selected = []
        for item in sorted(detections, key=lambda d:-d['confidence']):
            if all(_iou(item['bbox_xyxy_px'], old['bbox_xyxy_px']) < .45 for old in selected):
                selected.append(item)
        # Decoys compete in matching/NMS but never become M3 detections.
        return [item for item in selected if item['kind'] != 'decoy']

    def _facility(self, bgr, item, transform):
        cv2 = self.cv2
        expected = cv2.perspectiveTransform(np.float32([[[127.5,255*(.376-.32)/.352]]]), transform)[0,0]
        x1,y1,x2,y2 = item['bbox_xyxy_px']
        width, height = x2-x1, y2-y1
        radius = max(3, int(min(width,height)*.1))
        x, y = map(lambda v:int(round(v)), expected)
        left, top = max(0,x-radius), max(0,y-radius)
        right, bottom = min(bgr.shape[1],x+radius+1), min(bgr.shape[0],y+radius+1)
        roi = bgr[top:bottom,left:right].astype(float)
        if roi.size:
            b,g,r = roi[...,0],roi[...,1],roi[...,2]
            mask = ((b > r*1.12)&(g > r*1.04)&(b > 65)&(b-r < 90)).astype(np.uint8)
            count, _, stats, centers = cv2.connectedComponentsWithStats(mask, 8)
            choices = [(np.linalg.norm(center+[left,top]-expected), center+[left,top])
                       for stat,center in zip(stats[1:],centers[1:]) if 3 <= stat[4] <= max(20,width*height*.045)]
            if choices:
                distance, point = min(choices, key=lambda c:c[0])
                if distance < max(3,min(width,height)*.08):
                    item['aim_point_px'] = list(map(float,point))
                    item['aim_confidence'] = min(.9,item['confidence'])
                    camera = self.calibration.get('front_camera',self.calibration)
                    item['range_m'] = float(camera.get('fx_px',320.))*.352/max(width,1.)
                    item['range_source'] = 'public_panel_width_prior'
        # A visible red roof signal is the only hit feedback used by this model.
        left,right = max(0,int(x1+width*.25)),min(bgr.shape[1],int(x2-width*.25)+1)
        top,bottom = max(0,int(y1-height*.22)),max(0,int(y1))
        roi = bgr[top:bottom,left:right].astype(float)
        if roi.size:
            red = (roi[...,2]>130)&(roi[...,2]>roi[...,1]*2)&(roi[...,2]>roi[...,0]*2)
            if np.count_nonzero(red) >= 3:
                item['destroyed_observation'] = True
                item['destroyed_confidence'] = .85
