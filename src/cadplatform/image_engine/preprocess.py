"""Preprocess a grayscale drawing into a binary image for line detection.

Walls/linework become white foreground (255) on a black background so OpenCV's
detectors operate on the strokes.
"""

from __future__ import annotations

import cv2
import numpy as np


def binarize(gray: np.ndarray) -> np.ndarray:
    """Otsu threshold with inversion so dark linework becomes white foreground."""
    if gray.ndim != 2:
        raise ValueError("binarize expects a single-channel grayscale image")
    _, binary = cv2.threshold(
        gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )
    return binary


def denoise(binary: np.ndarray, kernel: int = 3) -> np.ndarray:
    """Light morphological opening to drop speckle before detection."""
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel, kernel))
    return cv2.morphologyEx(binary, cv2.MORPH_OPEN, k)
