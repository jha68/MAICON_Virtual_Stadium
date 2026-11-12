"""Calibration uses observable pixel correspondences, never fake field values."""
import json

import numpy as np
import pytest

pytestmark = pytest.mark.render

from maicon_sim.perception.augmentation import augment_image
from maicon_sim.perception.calibration import calibrate_camera, calibrate_points, rectify_camera, validate_calibration


def projected_boards():
    import cv2

    board = np.zeros((9*6, 3), np.float32)
    board[:, :2] = np.mgrid[0:9, 0:6].T.reshape(-1, 2)*.025
    matrix = np.array([[520., 0., 319.5], [0., 515., 239.5], [0., 0., 1.]])
    distortion = np.array([-.12, .04, .001, -.002, .01])
    objects, images = [], []
    for index in range(10):
        rotation = np.array([-.35+.08*index, .3*np.sin(index), .12*np.cos(index)])
        translation = np.array([-.1+.03*np.cos(index), -.06+.03*np.sin(index), .55+.03*index])
        corners, _ = cv2.projectPoints(board, rotation, translation, matrix, distortion)
        objects.append(board.copy())
        images.append(corners.reshape(-1, 2))
    return objects, images, matrix, distortion


def test_known_tilted_correspondences_recover_camera_and_save_quality_report(tmp_path):
    objects, images, matrix, distortion = projected_boards()
    output = tmp_path/"measured.json"
    report = calibrate_points(objects, images, (640, 480), output)
    recovered, coefficients, size = validate_calibration(report)
    assert size == (640, 480)
    assert recovered == pytest.approx(matrix, rel=1e-4, abs=.02)
    assert coefficients == pytest.approx(distortion, abs=.002)
    assert report["quality"]["view_count"] == 10
    assert report["quality"]["rms_reprojection_px"] < .01
    assert len(report["quality"]["per_view_rms_px"]) == 10
    assert json.loads(output.read_text()) == report
    with pytest.raises(FileExistsError):
        calibrate_points(objects, images, (640, 480), output)


def test_fronto_parallel_or_missing_views_do_not_claim_calibration():
    objects, images, _, _ = projected_boards()
    with pytest.raises(ValueError, match="six"):
        calibrate_points(objects[:3], images[:3], (640, 480))
    flat = objects[0][:, :2]*400+100
    with pytest.raises(ValueError, match="tilts"):
        calibrate_points(objects, [flat.copy() for _ in objects], (640, 480))
    images[0][0, 0] = np.nan
    with pytest.raises(ValueError, match="finite"):
        calibrate_points(objects, images, (640, 480))


def test_bad_correspondences_fail_reprojection_quality():
    objects, images, _, _ = projected_boards()
    rng = np.random.default_rng(42)
    noisy = [pixels+rng.normal(0, 2., pixels.shape) for pixels in images]
    with pytest.raises(ValueError, match="quality"):
        calibrate_points(objects, noisy, (640, 480), max_rms_px=.2)


def test_checkerboard_images_must_exist_have_corners_and_match_resolution(tmp_path):
    import cv2

    with pytest.raises(ValueError, match="missing"):
        calibrate_camera([tmp_path/f"missing{i}.png" for i in range(6)], (9, 6), .025, tmp_path/"bad.json")
    images = []
    for index in range(6):
        path = tmp_path/f"blank{index}.png"
        cv2.imwrite(str(path), np.zeros((120, 160, 3), np.uint8))
        images.append(path)
    with pytest.raises(ValueError, match="six"):
        calibrate_camera(images, (9, 6), .025, tmp_path/"bad.json")
    cv2.imwrite(str(images[-1]), np.zeros((240, 320, 3), np.uint8))
    with pytest.raises(ValueError, match="resolution"):
        calibrate_camera(images, (9, 6), .025, tmp_path/"bad.json")
    assert not (tmp_path/"bad.json").exists()


def test_image_checkerboards_exercise_detection_and_measured_output(tmp_path):
    import cv2

    columns, rows, square = 9, 6, .025
    pixels_per_square = 80
    board = np.zeros(((rows+1)*pixels_per_square, (columns+1)*pixels_per_square), np.uint8)
    for y in range(rows+1):
        for x in range(columns+1):
            if (x+y) % 2:
                board[y*pixels_per_square:(y+1)*pixels_per_square, x*pixels_per_square:(x+1)*pixels_per_square] = 255
    matrix = np.array([[520., 0., 319.5], [0., 515., 239.5], [0., 0., 1.]])
    outer = np.array([[-square, -square, 0.], [columns*square, -square, 0.],
                      [columns*square, rows*square, 0.], [-square, rows*square, 0.]], np.float32)
    source = np.float32([[-.5, -.5], [board.shape[1]-.5, -.5],
                         [board.shape[1]-.5, board.shape[0]-.5], [-.5, board.shape[0]-.5]])
    paths = []
    for index in range(15):
        # Large boards at varied tilts cover enough of the image to constrain K;
        # tiny near-identical views can have low RMS but poorly identified K.
        rotation = np.array([-.5+.07*index, .5*np.sin(index), .2*np.cos(index)])
        translation = np.array([-.1+.02*np.cos(index), -.06+.02*np.sin(index), .4+.015*index])
        projection, _ = cv2.projectPoints(outer, rotation, translation, matrix, None)
        image = cv2.warpPerspective(board, cv2.getPerspectiveTransform(source, projection.reshape(4, 2)), (640, 480), borderValue=180)
        path = tmp_path/f"board-{index}.png"
        assert cv2.imwrite(str(path), image)
        paths.append(path)
    output = tmp_path/"checkerboard.json"
    report = calibrate_camera(paths, (columns, rows), square, output)
    recovered, _, _ = validate_calibration(report)
    assert recovered == pytest.approx(matrix, abs=4.)
    assert report["source"] == "measured_checkerboard_images"
    assert len(report["source_images"]) >= 6
    assert report["quality"]["rms_reprojection_px"] < .5
    assert all(len(source["sha256"]) == 64 for source in report["source_images"])


def calibration():
    return {"intrinsics": {"width_px": 64, "height_px": 48, "fx_px": 50., "fy_px": 50., "cx_px": 31.5, "cy_px": 23.5},
            "distortion_model": "opencv_brown_conrady", "distortion_coefficients": [0.] * 5}


def test_rectification_preserves_stamps_resolution_and_explicit_pinhole_geometry():
    pixels = np.arange(48*64*3, dtype=np.uint8).reshape(48, 64, 3)
    frame = {"data": pixels, "captured_tick": 123, "sequence": 7}
    result = rectify_camera(frame, calibration())
    assert np.array_equal(result["data"], pixels)
    assert result["data"] is not pixels
    assert result["captured_tick"] == 123 and result["sequence"] == 7
    assert result["intrinsics"]["distortion_model"] == "none"
    assert result["rectified"]
    assert np.array_equal(rectify_camera(pixels, calibration()), pixels)
    with pytest.raises(ValueError, match="resolution"):
        rectify_camera(pixels[:20], calibration())


def test_seeded_pixel_stress_is_reproducible_independent_and_does_not_mutate_input():
    pixels = np.full((48, 64, 3), 110, np.uint8)
    kwargs = dict(brightness=4., contrast=1.1, white_balance=(1., .9, 1.1), blur_sigma=.8, noise_sigma=3.)
    a = augment_image(pixels, 42, **kwargs)
    b = augment_image(pixels, 42, **kwargs)
    c = augment_image(pixels, 43, **kwargs)
    assert a.dtype == np.uint8 and a.shape == pixels.shape
    assert np.array_equal(a, b) and not np.array_equal(a, c)
    assert np.all(pixels == 110)
    assert not np.array_equal(a, pixels)
    assert np.array_equal(augment_image(pixels, 0), pixels)


def test_lens_stress_distorts_observable_pixels_then_rectifies_with_same_intrinsics():
    import cv2

    pixels = np.zeros((48, 64, 3), np.uint8)
    for x in range(4, 64, 8):
        cv2.line(pixels, (x, 0), (x, 47), (255, 255, 255), 1)
    profile = calibration()
    profile["distortion_coefficients"] = [-.3, .05, 0., 0., 0.]
    distorted = augment_image(pixels, 7, intrinsics=profile["intrinsics"], distortion_coefficients=profile["distortion_coefficients"])
    assert not np.array_equal(distorted, pixels)
    corrected = rectify_camera(distorted, profile)
    # Interpolation and sensor-edge loss preclude perfect reversibility, but the
    # central rectified field must better match the original pinhole pattern.
    roi = np.s_[8:-8, 12:-12]
    raw_error = np.abs(distorted[roi].astype(float)-pixels[roi]).mean()
    corrected_error = np.abs(corrected[roi].astype(float)-pixels[roi]).mean()
    assert corrected_error < raw_error


@pytest.mark.parametrize("kwargs", [{"noise_sigma": -1}, {"blur_sigma": float("nan")}, {"contrast": 0}, {"white_balance": (1, 0, 1)}])
def test_invalid_stress_parameters_are_rejected(kwargs):
    with pytest.raises(ValueError):
        augment_image(np.zeros((48, 64, 3), np.uint8), 0, **kwargs)
