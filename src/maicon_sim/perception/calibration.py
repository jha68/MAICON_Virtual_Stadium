"""Measured pinhole calibration and rectification, independent of simulator truth.

The returned file records measurements, not a fabricated real-robot profile.
Six or more differently tilted board views are required; the actual field TF,
camera latency and ROS message mappings still need separate measurement.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np


def _image_size(size):
    if len(size) != 2 or any(type(v) is not int or v < 16 for v in size):
        raise ValueError("image_size must contain integer width,height >=16")
    return tuple(size)


def _write_report(report, out):
    if out is not None:
        path = Path(out)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Measurement output must never silently replace an existing profile.
        with path.open("x", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, allow_nan=False)
            handle.write("\n")
    return report


def calibrate_points(object_points, image_points, image_size, out=None, *, max_rms_px=1.):
    """Estimate OpenCV Brown-Conrady intrinsics from known board correspondences.

    image_size is (width,height). Each object view is Nx3 board coordinates in
    metres and its image view is Nx2 pixels. Inputs must be planar boards with
    at least nine non-collinear points, observed in six distinct tilted views.
    """
    import cv2

    width, height = _image_size(image_size)
    if not math.isfinite(max_rms_px) or max_rms_px <= 0:
        raise ValueError("max_rms_px must be positive and finite")
    if len(object_points) != len(image_points) or len(object_points) < 6:
        raise ValueError("calibration requires at least six paired board views")
    objects, images, projective = [], [], []
    for index, (world, pixels) in enumerate(zip(object_points, image_points)):
        world = np.asarray(world, dtype=np.float64)
        pixels = np.asarray(pixels, dtype=np.float64)
        if world.ndim != 2 or world.shape[1:] != (3,) or len(world) < 9 or pixels.shape != (len(world), 2):
            raise ValueError(f"view {index}: expected matching Nx3/Nx2 arrays with N>=9")
        if not np.isfinite(world).all() or not np.isfinite(pixels).all():
            raise ValueError(f"view {index}: coordinates must be finite")
        if not np.allclose(world[:, 2], 0., atol=1e-9):
            raise ValueError(f"view {index}: board coordinates must have z=0")
        if np.linalg.matrix_rank(world[:, :2]-world[:, :2].mean(axis=0)) < 2 or np.linalg.matrix_rank(pixels-pixels.mean(axis=0)) < 2:
            raise ValueError(f"view {index}: board corners must not be collinear")
        if np.any(pixels < 0) or np.any(pixels[:, 0] >= width) or np.any(pixels[:, 1] >= height):
            raise ValueError(f"view {index}: detected corners must be inside the image")
        homography, _ = cv2.findHomography(world[:, :2], pixels, method=0)
        if homography is None or not np.isfinite(homography).all():
            raise ValueError(f"view {index}: board homography is degenerate")
        projective.append(homography[2, :2]/np.linalg.norm(homography[:2, :2]))
        objects.append(world.astype(np.float32))
        images.append(pixels.astype(np.float32))
    # Moving a fronto-parallel board sideways or spinning it in its own plane
    # cannot identify focal length and distance independently.
    projective = np.asarray(projective)
    if np.max(np.linalg.norm(projective, axis=1)) < 1e-7 or np.max(np.linalg.norm(projective-projective[0], axis=1)) < 1e-7:
        raise ValueError("board views need different out-of-plane tilts")
    try:
        rms, matrix, distortion, rotations, translations = cv2.calibrateCamera(
            objects, images, (width, height), None, None,
            flags=cv2.CALIB_FIX_K4 | cv2.CALIB_FIX_K5 | cv2.CALIB_FIX_K6)
    except cv2.error as error:
        raise ValueError("camera calibration failed; check board correspondences") from error
    errors = []
    for world, pixels, rotation, translation in zip(objects, images, rotations, translations):
        projection, _ = cv2.projectPoints(world, rotation, translation, matrix, distortion)
        errors.append(float(np.sqrt(np.mean(np.sum((projection.reshape(-1, 2)-pixels)**2, axis=1)))))
    if not math.isfinite(rms) or rms > max_rms_px or max(errors) > 2*max_rms_px:
        raise ValueError("reprojection error exceeds calibration quality limit")
    report = {
        "schema_version": "1.0", "source": "measured_board_correspondences",
        "intrinsics": {"width_px": width, "height_px": height,
                       "fx_px": float(matrix[0, 0]), "fy_px": float(matrix[1, 1]),
                       "cx_px": float(matrix[0, 2]), "cy_px": float(matrix[1, 2])},
        "distortion_model": "opencv_brown_conrady",
        "distortion_coefficients": distortion.reshape(-1)[:5].tolist(),
        "quality": {"status": "passed", "view_count": len(objects),
                    "rms_reprojection_px": float(rms), "per_view_rms_px": errors,
                    "maximum_allowed_rms_px": float(max_rms_px)},
    }
    validate_calibration(report)
    return _write_report(report, out)


def calibrate_camera(image_paths, board_size, square_size_m, out, *, max_rms_px=1.):
    """Find checkerboard inner corners in BGR images and save a measured report.

    board_size is (inner_columns,inner_rows), e.g. (9,6). Rejected input images
    are recorded by filename; at least six successful views remain necessary.
    """
    import cv2

    if len(board_size) != 2 or any(type(n) is not int or n < 3 for n in board_size):
        raise ValueError("board_size needs integer inner columns,rows >=3")
    if not math.isfinite(square_size_m) or square_size_m <= 0:
        raise ValueError("square_size_m must be positive and finite")
    board = np.zeros((math.prod(board_size), 3), dtype=np.float32)
    board[:, :2] = np.mgrid[0:board_size[0], 0:board_size[1]].T.reshape(-1, 2)*square_size_m
    objects, corners, sources, rejected = [], [], [], []
    image_size = None
    paths = [Path(path) for path in image_paths]
    if len(paths) < 6:
        raise ValueError("calibration requires at least six board images")
    for path in paths:
        if not path.is_file():
            raise ValueError(f"calibration image missing: {path.name}")
        bgr = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if bgr is None:
            raise ValueError(f"calibration image unreadable: {path.name}")
        size = (bgr.shape[1], bgr.shape[0])
        if image_size is not None and image_size != size:
            raise ValueError("all calibration images must have the same resolution")
        image_size = size
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        found, points = cv2.findChessboardCornersSB(gray, tuple(board_size), flags=cv2.CALIB_CB_NORMALIZE_IMAGE)
        if not found:
            rejected.append(path.name)
            continue
        objects.append(board.copy())
        corners.append(points.reshape(-1, 2))
        sources.append({"name": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    report = calibrate_points(objects, corners, image_size, max_rms_px=max_rms_px)
    report.update(source="measured_checkerboard_images", board_size=list(board_size),
                  square_size_m=float(square_size_m), source_images=sources, rejected_images=rejected)
    return _write_report(report, out)


def validate_calibration(calibration):
    """Validate an explicit calibration dict; return K, distortion, (width,height)."""
    intrinsics = calibration.get("intrinsics", calibration.get("front_camera"))
    if not isinstance(intrinsics, dict):
        raise ValueError("calibration needs an intrinsics object")
    width, height = _image_size((intrinsics.get("width_px"), intrinsics.get("height_px")))
    try:
        fx, fy, cx, cy = (float(intrinsics[key]) for key in ("fx_px", "fy_px", "cx_px", "cy_px"))
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("calibration intrinsics must be numeric") from error
    if not np.isfinite([fx, fy, cx, cy]).all() or not .05*width <= fx <= 10*width or not .05*height <= fy <= 10*height:
        raise ValueError("calibration focal lengths are implausible or non-finite")
    if not -.25*width <= cx <= 1.25*width or not -.25*height <= cy <= 1.25*height:
        raise ValueError("calibration principal point is outside supported image range")
    model = calibration.get("distortion_model", intrinsics.get("distortion_model", "none"))
    if model not in ("none", "opencv_brown_conrady"):
        raise ValueError("unsupported camera distortion model")
    distortion = np.asarray(calibration.get("distortion_coefficients", [] if model == "none" else None), dtype=float)
    if model == "none" and distortion.size == 0:
        distortion = np.zeros(5)
    if distortion.shape not in ((4,), (5,), (8,)) or not np.isfinite(distortion).all():
        raise ValueError("distortion_coefficients must contain 4,5 or8 finite values")
    matrix = np.array([[fx, 0., cx], [0., fy, cy], [0., 0., 1.]])
    return matrix, distortion, (width, height)


def rectify_camera(frame, calibration):
    """Rectify BGR pixels using the same K/resolution, without hidden cropping."""
    import cv2

    matrix, distortion, size = validate_calibration(calibration)
    data = frame.get("data") if isinstance(frame, dict) else frame
    if not isinstance(data, np.ndarray) or data.dtype != np.uint8 or data.shape != (size[1], size[0], 3):
        raise ValueError("camera frame must be uint8 BGR at calibrated resolution")
    rectified = cv2.undistort(data, matrix, distortion, None, matrix)
    if not isinstance(frame, dict):
        return rectified
    return {**frame, "data": rectified, "rectified": True,
            "intrinsics": {**calibration.get("intrinsics", calibration.get("front_camera")), "distortion_model": "none"}}
