"""Timestamped public drone JPEGs. No simulator identity/pose data are consumed."""
from datetime import datetime

import numpy as np


class DroneObserver:
    def __init__(self, calibration, detector=None):
        from .combat import CombatVisionDetector
        self.detector = detector or CombatVisionDetector(calibration)
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
        detections = []
        for item in self.detector.detect(bgr):
            if item.get('kind') == 'ugv':
                cue = {k:v for k,v in item.items() if k in (
                    'kind', 'bbox_xyxy_px', 'marker_readout', 'confidence')}
                if item.get('view_model') == 'overhead':
                    cue['visual_state'] = item.get('visual_state', {})
                detections.append(cue)
        self.latest = {'camera_id':'drone/main', 'captured_tick':tick, 'received_tick':received_tick,
                       'sequence':tick, 'detections':detections}
        self.last_timestamp, self.status = timestamp, 'available'

    def observation(self, tick):
        age = None if self.latest is None else max(0, tick-self.latest['captured_tick'])/100.
        stale = age is not None and age > 2*self.interval_s+1.
        return {'status':'stale' if stale else self.status, 'age_s':age, 'interval_s':self.interval_s,
                'visual':None if stale else self.latest, 'source':'public_drone_jpeg'}
