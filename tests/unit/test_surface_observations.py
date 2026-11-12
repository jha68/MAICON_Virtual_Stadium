"""Delayed public observations, physical face association, and sector certainty."""
import math
import threading

import numpy as np
import pytest

from maicon_sim.policies.observations import (
    GimbalHistory, ObservationHistory, SurfaceMapper, certain_sector, estimate_surface,
)
from maicon_sim.policies.tracking import ObjectTracker


CALIBRATION = {"front_camera": {"fx_px": 320., "fy_px": 320., "cx_px": 319.5, "cy_px": 239.5},
               "gimbal_pivot_m": [.02, 0., .23], "camera_offset_gimbal_m": [.025, 0., 0.],
               "lidar": {"origin_body_m": [0., 0., .145]}}
FACE = (3.8, 2.8, 3.2)


def scan(pose, tick=0):
    """Fixture ranges from one known test box and rectangular boundary.

    Fixture truth creates a public scan; the implementation receives only ranges.
    """
    x, y, yaw = pose
    segments = [((0., 0.), (8., 0.)), ((0., 6.), (8., 6.)),
                ((0., 0.), (0., 6.)), ((8., 0.), (8., 6.)),
                ((3.8, 2.8), (4.2, 2.8)), ((3.8, 3.2), (4.2, 3.2)),
                ((3.8, 2.8), (3.8, 3.2)), ((4.2, 2.8), (4.2, 3.2))]
    ranges = []
    for index in range(360):
        angle = yaw-math.pi+index*math.pi/180
        direction = (math.cos(angle), math.sin(angle))
        hits = []
        for a, b in segments:
            axis = 0 if a[0] == b[0] else 1
            other = 1-axis
            if abs(direction[axis]) < 1e-9:
                continue
            t = (a[axis]-(x, y)[axis])/direction[axis]
            cross = (x, y)[other]+t*direction[other]
            if t > 0 and min(a[other], b[other])-1e-9 <= cross <= max(a[other], b[other])+1e-9:
                hits.append(t)
        ranges.append(min(hits) if hits else None)
    return {"captured_tick": tick, "sequence": tick, "angle_min_rad": -math.pi,
            "angle_increment_rad": math.pi/180, "range_min_m": .05, "range_max_m": 10., "ranges_m": ranges}


def detection(pose, side="west"):
    x, y, yaw = pose
    origin = np.array([x+.045*math.cos(yaw), y+.045*math.sin(yaw), .23])
    if side == "west":
        points = [(3.8, yy, zz) for yy in (2.824, 3.176) for zz in (.024, .376)]
    else:
        points = [(xx, 2.8, zz) for xx in (3.824, 4.176) for zz in (.024, .376)]
    pixels = []
    for point in points:
        dx, dy, dz = np.array(point)-origin
        forward = math.cos(yaw)*dx+math.sin(yaw)*dy
        left = -math.sin(yaw)*dx+math.cos(yaw)*dy
        pixels.append((319.5-320*left/forward, 239.5-320*dz/forward))
    points = np.asarray(pixels)
    return {"kind": "object", "bbox_xyxy_px": [float(points[:,0].min()), float(points[:,1].min()),
                                                   float(points[:,0].max()), float(points[:,1].max())],
            "class_probs": {"tank": 1.}, "confidence": 1.}


def odom(tick, x=0., y=0., yaw=0.):
    return {"captured_tick": tick, "local_pose": {"x_m": x, "y_m": y, "yaw_rad": yaw}}


def public_map(boundary=6.):
    return {"bounds": {"width_m": 8., "height_m": 6.},
            "nominal_starts": [{"slot": "B-1", "pose": {"x_m": 2., "y_m": 3., "yaw_rad": 0.}}],
            "sectors": [{"sector_id": "CM", "polygon_xy_m": [[0.,0.], [boundary,0.], [boundary,6.], [0.,6.]]}]}


def test_capture_pose_interpolates_delayed_odom_and_wraps_yaw():
    history = ObservationHistory()
    history.add({"odom": odom(0, yaw=math.radians(179))})
    history.add({"odom": odom(10, 1., .2, math.radians(-179))})
    pose = history.pose_at(5, (2., 3., 0.))
    assert pose[:2] == pytest.approx((2.5, 3.1))
    assert abs(abs(pose[2])-math.pi) < 1e-9
    assert history.pose_at(-20, (2., 3., 0.)) is None
    history.add({"odom": odom(100, 5.)})
    assert history.pose_at(50, (2., 3., 0.)) is None


def test_history_is_bounded_sorted_and_thread_safe_for_late_delivery():
    history = ObservationHistory(capacity=32)
    def add(values):
        for tick in values:
            history.add({"odom": odom(tick, tick*.01)})
    threads = [threading.Thread(target=add, args=(range(offset, 100, 2),)) for offset in (0, 1)]
    for thread in threads: thread.start()
    for thread in threads: thread.join()
    assert [tick for tick, _ in history.frames["odom"]] == list(range(68, 100))
    assert history.pose_at(90, (0., 0., 0.)) == pytest.approx((.9, 0., 0.))


def test_gimbal_history_uses_capture_time_and_cancel_uncertainty():
    gimbal = GimbalHistory()
    gimbal.command(100., 40., 10., 100)
    assert gimbal.at(50) == (0., 0.)
    assert gimbal.at(200) == pytest.approx((20., 40.))
    gimbal.cancel(200)
    assert gimbal.at(199) is not None
    assert gimbal.at(201) is None
    gimbal.command(0., 0., 20., 220)
    assert gimbal.at(320) == pytest.approx((0., 0.))


@pytest.mark.parametrize("pose", [(2.,3.,0.), (2.,2.5,.3), (2.,3.4,-.2)])
def test_plane_normal_and_face_midpoint_remain_stable_across_view_angles(pose):
    estimate = estimate_surface(detection(pose), pose, pose, scan(pose), CALIBRATION)
    assert estimate is not None
    assert estimate.position == pytest.approx((3.8, 3.), abs=.04)
    assert abs(abs(estimate.normal_rad)-math.pi) < .02


def test_revisiting_face_from_different_bearings_does_not_duplicate_it():
    tracker = ObjectTracker()
    for tick, pose in enumerate([(2.,3.,0.), (2.,2.5,.3), (2.,3.4,-.2)]):
        surface = estimate_surface(detection(pose), pose, pose, scan(pose), CALIBRATION)
        assert surface is not None
        tracker.observe(surface.position, surface.normal_rad, {"tank": 1.}, tick, "CM",
                        surface_extent=surface.extent, position_sigma_m=surface.sigma_m)
    assert len(tracker.tracks) == 1
    assert tracker.report() == {"sectors": [{"sector": "CM", "objects": [{"type": "TANK", "count": 1}]}]}
    # An orthogonal printed face of that box is a separate count, even with
    # exactly the same class and only0.28m centre separation.
    pose = (4., 1., math.pi/2)
    surface = estimate_surface(detection(pose, "south"), pose, pose, scan(pose), CALIBRATION)
    assert surface is not None
    tracker.observe(surface.position, surface.normal_rad, {"tank": 1.}, 4, "CM", surface_extent=surface.extent)
    assert len(tracker.tracks) == 2


def test_collinear_adjacent_faces_are_not_merged_without_segment_overlap():
    tracker = ObjectTracker()
    tracker.observe((2., 2.), math.pi, {"tank": 1.}, 0, "CM", surface_extent=((2.,1.8),(2.,2.2)))
    tracker.observe((2., 2.45), math.pi, {"tank": 1.}, 1, "CM", surface_extent=((2.,2.25),(2.,2.65)))
    assert len(tracker.tracks) == 2


def test_sector_uncertainty_withholds_boundary_track_then_accepts_clear_evidence():
    sectors = [{"sector_id": "B-S1", "polygon_xy_m": [[0.,0.], [4.,0.], [4.,6.], [0.,6.]]},
               {"sector_id": "CM", "polygon_xy_m": [[4.,0.], [8.,0.], [8.,6.], [4.,6.]]}]
    assert certain_sector((3.99,3.), sectors, .04) is None
    assert certain_sector((4.01,3.), sectors, .04) is None
    assert certain_sector((4.1,3.), sectors, .04) == "CM"
    tracker = ObjectTracker()
    tracker.observe((3.99,3.), math.pi, {"tank": 1.}, 0, None, sector_uncertain=True)
    assert tracker.report() == {"sectors": []}
    tracker.observe((3.94,3.), math.pi, {"tank": 1.}, 1, "B-S1")
    assert len(tracker.tracks) == 1
    assert tracker.report()["sectors"][0]["sector"] == "B-S1"


def test_mapper_aligns_delayed_image_to_historical_scan_and_gimbal():
    mapper = SurfaceMapper(public_map(), CALIBRATION, "B-1")
    history, gimbal, tracker = ObservationHistory(), GimbalHistory(), ObjectTracker()
    history.add({"odom": odom(0), "scan": scan((2.,3.,0.), 0)})
    history.add({"odom": odom(20, .8)})
    gimbal.command(60., 0., 90., 10)
    outcome = mapper.observe({"captured_tick": 0, "detections": [detection((2.,3.,0.))]}, history, gimbal, tracker)
    assert outcome["mapped"] == 1
    assert tracker.tracks[0].position == pytest.approx((3.8,3.), abs=.04)
    assert tracker.tracks[0].sector == "CM"


def test_mapper_rejects_unsynchronized_image_and_boundary_uncertainty():
    history, gimbal, tracker = ObservationHistory(), GimbalHistory(), ObjectTracker()
    history.add({"odom": odom(0), "scan": scan((2.,3.,0.), 0)})
    mapper = SurfaceMapper(public_map(3.82), CALIBRATION, "B-1")
    outcome = mapper.observe({"captured_tick": 0, "detections": [detection((2.,3.,0.))]}, history, gimbal, tracker)
    assert outcome["mapped"] == 1
    assert tracker.report() == {"sectors": []}
    outcome = mapper.observe({"captured_tick": 100, "detections": [detection((2.,3.,0.))]}, history, gimbal, tracker)
    assert outcome["reason"] == "unsynchronized_public_sensors"


def test_old_camera_frame_cannot_create_new_false_tracks():
    history, gimbal, tracker = ObservationHistory(), GimbalHistory(), ObjectTracker()
    history.add({"odom": odom(10), "scan": scan((2.,3.,0.), 10)})
    history.add({"odom": odom(0), "scan": scan((2.,3.,0.), 0)})
    mapper = SurfaceMapper(public_map(), CALIBRATION, "B-1")
    first = mapper.observe({"captured_tick": 10, "detections": [detection((2.,3.,0.))]}, history, gimbal, tracker)
    assert first["mapped"] == 1
    previous = tracker.tracks[0].observations
    old = mapper.observe({"captured_tick": 0, "detections": [detection((2.,3.,0.))]}, history, gimbal, tracker)
    assert old["reason"] == "old_camera_frame"
    assert tracker.tracks[0].observations == previous


def test_sector_near_boundary_waits_for_global_wall_registration():
    history, gimbal, tracker = ObservationHistory(), GimbalHistory(), ObjectTracker()
    partial = scan((2.,3.,0.), 0)
    partial["ranges_m"] = [distance if distance is not None and distance < 2.2 else None for distance in partial["ranges_m"]]
    history.add({"odom": odom(0), "scan": partial})
    mapper = SurfaceMapper(public_map(3.85), CALIBRATION, "B-1")
    first = mapper.observe({"captured_tick": 0, "detections": [detection((2.,3.,0.))]}, history, gimbal, tracker)
    assert first["mapped"] == 1
    assert not mapper._wall_registered
    assert tracker.report() == {"sectors": []}
    history.add({"odom": odom(10), "scan": scan((2.,3.,0.), 10)})
    mapper.observe({"captured_tick": 10, "detections": [detection((2.,3.,0.))]}, history, gimbal, tracker)
    assert mapper._wall_registered
    assert len(tracker.tracks) == 1
    assert tracker.report()["sectors"][0]["sector"] == "CM"


def test_late_wall_registration_moves_provisional_track_instead_of_duplicating():
    history, gimbal, tracker = ObservationHistory(), GimbalHistory(), ObjectTracker()
    partial = scan((2.,3.,0.), 0)
    partial["ranges_m"] = [distance if distance is not None and distance < 2.2 else None for distance in partial["ranges_m"]]
    history.add({"odom": odom(0), "scan": partial})
    prior = public_map()
    prior["nominal_starts"][0]["pose"]["x_m"] = 2.1
    mapper = SurfaceMapper(prior, CALIBRATION, "B-1")
    mapper.observe({"captured_tick": 0, "detections": [detection((2.,3.,0.))]}, history, gimbal, tracker)
    assert len(tracker.tracks) == 1
    assert tracker.tracks[0].position[0] == pytest.approx(3.9, abs=.02)
    history.add({"odom": odom(10), "scan": scan((2.,3.,0.), 10)})
    mapper.observe({"captured_tick": 10, "detections": [detection((2.,3.,0.))]}, history, gimbal, tracker)
    assert mapper._wall_registered
    assert len(tracker.tracks) == 1
    assert tracker.tracks[0].position[0] == pytest.approx(3.8, abs=.02)
