"""Timestamped public drone JPEGs. No simulator identity/pose data are consumed."""
from datetime import datetime

import numpy as np


class DroneObserver:
    def __init__(self, calibration, detector=None):
        from .overhead import OverheadPixelDetector, OverheadProjection
        camera = calibration.get('drone_camera')
        self.projection = OverheadProjection(camera) if camera else None
        self.detector = detector or (OverheadPixelDetector(camera) if camera else None)
        self.epoch = calibration.get('capture_clock_epoch')
        self.last_timestamp = None
        self.latest = None
        self.status = 'waiting'
        self.interval_s = 1.

    def unavailable(self, status):
        self.status = {403: 'disabled', 409: 'outside_match', 503: 'unavailable'}.get(status, 'unavailable')
        self.latest = None

    def process(self, data, headers, received_tick):
        import cv2
        headers = {k.lower(): v for k,v in headers.items()}
        timestamp = datetime.fromisoformat(headers['x-captured-at'])
        self.interval_s = max(1., min(5., float(headers.get('x-frame-interval-s', 1))))
        if self.last_timestamp is not None and timestamp <= self.last_timestamp:
            return
        # Real deployments must configure a clock mapping. Unknown latency must
        # never turn an old frame into fresh HP/ammo or a laser aim point.
        if not self.epoch:
            self.status = 'clock_unsynchronised'
            self.latest = None
            return
        tick = round((timestamp-datetime.fromisoformat(self.epoch)).total_seconds()*100)
        if tick < 0 or tick > received_tick+1:
            self.status = 'clock_unsynchronised'
            self.latest = None
            return
        if len(data) > 8*1024*1024:
            raise ValueError('drone JPEG exceeds size limit')
        bgr = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        if bgr is None or bgr.shape[0]*bgr.shape[1] > 4096*4096:
            raise ValueError('invalid drone JPEG')
        # Front-camera range and LED layout are not valid overhead. The built-in
        # model transfers identity only; an overhead-specific model may supply
        # calibrated LED evidence. Never infer invisible bands/LEDs from truth.
        detections, obstacles, robots = [], [], []
        dimensions_match = self.projection is not None and bgr.shape[:2] == (self.projection.height, self.projection.width)
        for item in self.detector.detect(bgr) if self.detector else []:
            if dimensions_match and item.get('confidence', 0) >= .75:
                if item.get('kind') == 'obstacle' and item.get('surface_polygon_px') and item.get('projection_plane_z_m') == .4:
                    polygon = self.projection.intersect(item['surface_polygon_px'], .4)
                    if polygon is not None:
                        obstacles.append({'polygon_xy_m': polygon.tolist(), 'uncertainty_m': .06})
                if item.get('kind') == 'ugv' and item.get('view_model') == 'overhead' and item.get('navigation_point_px') and item.get('projection_plane_z_m') == .13:
                    point = self.projection.intersect([item['navigation_point_px']], .13)
                    if point is not None:
                        robots.append({'position_xy_m': point[0].tolist(), 'camp': item.get('camp_observation'), 'uncertainty_m': .18})
            if item.get('kind') == 'ugv':
                cue = {k:v for k,v in item.items() if k in (
                    'kind', 'bbox_xyxy_px', 'marker_readout', 'confidence')}
                if item.get('view_model') == 'overhead' and 'visual_state' in item:
                    cue['visual_state'] = item.get('visual_state', {})
                detections.append(cue)
        self.latest = {'camera_id':'drone/main', 'captured_tick':tick, 'received_tick':received_tick,
                       'sequence':tick, 'detections':detections,
                       'navigation': {'obstacles': obstacles, 'robots': robots,
                                      'source': 'calibrated_overhead_pixels', 'model': 'SIM-OVERHEAD-PRIORS'}}
        self.last_timestamp, self.status = timestamp, 'available'

    def observation(self, tick):
        age = None if self.latest is None else max(0, tick-self.latest['captured_tick'])/100.
        stale = age is not None and age > 2*self.interval_s+1.
        return {'status':'stale' if stale else self.status, 'age_s':age, 'interval_s':self.interval_s,
                'visual':None if stale else self.latest, 'source':'public_drone_jpeg'}
