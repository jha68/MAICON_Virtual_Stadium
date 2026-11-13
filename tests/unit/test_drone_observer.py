import numpy as np
import pytest

cv2 = pytest.importorskip('cv2')

from maicon_sim.perception.drone import DroneObserver


class Detector:
    calls = 0
    def detect(self, image):
        self.calls += 1
        return [{'kind':'ugv', 'marker_readout':{'camp':'RED', 'band_count':2, 'confidence':.9},
                 'visual_state':{'hp':4, 'ammo':8}, 'range_m':2., 'aim_point_px':[20,20]}]


def test_default_drone_does_not_load_or_match_unused_printed_panels(monkeypatch):
    from maicon_sim.perception import reference_images, combat
    def unused(*args, **kwargs):
        raise AssertionError('Drone identity observation must not construct a panel detector')
    monkeypatch.setattr(reference_images, 'ReferenceImageDetector', unused)
    monkeypatch.setattr(combat, 'SyntheticTemplateDetector', unused)
    observer = DroneObserver({'artwork_profile': 'prestudy', 'capture_clock_epoch':'2026-11-04T12:00:00+09:00'})
    blob = cv2.imencode('.jpg', np.zeros((48,64,3), np.uint8))[1].tobytes()
    observer.process(blob, {'X-Captured-At':'2026-11-04T12:00:01+09:00'}, 100)
    assert observer.observation(100)['status'] == 'available'
    assert observer.observation(100)['visual']['detections'] == []


def test_drone_clock_dedup_staleness_and_no_front_camera_aim_or_led_geometry():
    detector = Detector()
    observer = DroneObserver({'capture_clock_epoch':'2026-11-04T12:00:00+09:00'}, detector)
    blob = cv2.imencode('.jpg', np.zeros((48,64,3), np.uint8))[1].tobytes()
    headers = {'X-Captured-At':'2026-11-04T12:00:01+09:00', 'X-Frame-Interval-S':'1'}
    observer.process(blob, headers, 110)
    frame = observer.observation(110)
    assert frame['age_s'] == .1 and frame['visual']['captured_tick'] == 100
    cue = frame['visual']['detections'][0]
    assert 'aim_point_px' not in cue and 'visual_state' not in cue and 'range_m' not in cue
    observer.process(blob, headers, 200)
    assert detector.calls == 1 and observer.observation(200)['age_s'] == 1.
    assert observer.observation(401)['status'] == 'stale'
    assert observer.observation(401)['visual'] is None
    observer.unavailable(403)
    assert observer.observation(410)['status'] == 'disabled'
    assert observer.observation(410)['visual'] is None


def test_missing_clock_mapping_and_future_frame_never_become_fresh_evidence():
    detector = Detector()
    observer = DroneObserver({}, detector)
    headers = {'X-Captured-At':'2026-11-04T12:00:01+09:00'}
    observer.process(b'not decoded without a time mapping', headers, 100)
    assert observer.observation(100)['status'] == 'clock_unsynchronised'
    assert detector.calls == 0
    observer.epoch = '2026-11-04T12:00:00+09:00'
    observer.process(b'not decoded when in the future', headers, 0)
    assert observer.observation(0)['visual'] is None
