"""Participant image callback boundary: pixels in, uncertain detections out."""
from __future__ import annotations
from typing import Any, Protocol
import numpy as np


class VisionCallback(Protocol):
    def detect(self, bgr: np.ndarray) -> list[dict[str, Any]]: ...
