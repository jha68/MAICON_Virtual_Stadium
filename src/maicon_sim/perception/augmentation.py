"""Seeded pixel stress transforms, with no labels or world truth as input."""
from __future__ import annotations

import math

import numpy as np


def augment_image(bgr, seed, *, brightness=0., contrast=1., white_balance=(1., 1., 1.),
                  blur_sigma=0., noise_sigma=0., distortion_coefficients=None, intrinsics=None):
    """Return independent uint8 BGR pixels with deterministic photometry/lens noise.

    brightness is an additive pixel offset, contrast scales around mid-gray and
    white_balance is B,G,R gain. Optional Brown-Conrady coefficients synthesize
    lens distortion from an ideal pinhole frame; an explicit K is required.
    """
    import cv2

    if not isinstance(bgr, np.ndarray) or bgr.dtype != np.uint8 or bgr.ndim != 3 or bgr.shape[2] != 3:
        raise ValueError("augment_image expects uint8 HxWx3 BGR pixels")
    gains = np.asarray(white_balance, dtype=float)
    if gains.shape != (3,) or not np.isfinite(gains).all() or np.any(gains <= 0):
        raise ValueError("white_balance needs three positive finite BGR gains")
    if not all(math.isfinite(v) for v in (brightness, contrast, blur_sigma, noise_sigma)) or contrast <= 0 or blur_sigma < 0 or noise_sigma < 0:
        raise ValueError("stress parameters must be finite with positive contrast and nonnegative sigma")
    if type(seed) is not int or seed < 0:
        raise ValueError("seed must be a nonnegative integer")
    image = bgr.copy()
    if distortion_coefficients is not None:
        from .calibration import validate_calibration
        calibration = {"intrinsics": intrinsics, "distortion_model": "opencv_brown_conrady",
                       "distortion_coefficients": distortion_coefficients}
        matrix, distortion, size = validate_calibration(calibration)
        if image.shape[:2] != (size[1], size[0]):
            raise ValueError("lens stress intrinsics must match image resolution")
        xx, yy = np.meshgrid(np.arange(size[0], dtype=np.float32), np.arange(size[1], dtype=np.float32))
        distorted_pixels = np.stack((xx, yy), axis=-1).reshape(-1, 1, 2)
        # Destination is the distorted sensor plane; sample corresponding ideal
        # source pixels, the inverse of rectification's forward lens mapping.
        source = cv2.undistortPoints(distorted_pixels, matrix, distortion, P=matrix).reshape(size[1], size[0], 2)
        image = cv2.remap(image, source[..., 0], source[..., 1], cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
    result = ((image.astype(np.float32)-127.5)*contrast+127.5+brightness)*gains
    if blur_sigma:
        result = cv2.GaussianBlur(result, (0, 0), blur_sigma)
    if noise_sigma:
        result += np.random.default_rng(seed).normal(0., noise_sigma, result.shape)
    return np.clip(np.rint(result), 0, 255).astype(np.uint8)
