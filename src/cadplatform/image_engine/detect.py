"""OpenCV straight-line detection (first vertical slice).

Returns raw line segments in PIXEL coordinates (image origin: top-left, y down).
Conversion to millimeters and the y-flip happen in the CLI before handing off to
``cad_pipeline``.

SCOPE / CLAUDE.md rule 3: this detector finds STRAIGHT wall faces only. Curve
recognition (circles, arcs, ellipses, freeform splines) is a DEFERRED stage; the
line-only detector here is intentionally INCOMPLETE, not the final design.
"""

from __future__ import annotations

import cv2
import numpy as np

from ..cad_pipeline.geometry import Segment


def detect_wall_edges(
    binary: np.ndarray,
    min_length_px: float = 40.0,
    max_gap_px: float = 10.0,
    threshold: int = 50,
) -> list[Segment]:
    """Detect wall FACE edges as pixel-space segments.

    Canny extracts the boundaries of the (filled) wall strokes, then a
    probabilistic Hough transform turns those boundaries into straight segments —
    so a wall of real thickness yields its two parallel faces, which downstream
    pairing measures the thickness from.
    """
    edges = cv2.Canny(binary, 50, 150)
    lines = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=np.pi / 180.0,
        threshold=threshold,
        minLineLength=min_length_px,
        maxLineGap=max_gap_px,
    )
    if lines is None:
        return []
    return [Segment(float(x1), float(y1), float(x2), float(y2)) for x1, y1, x2, y2 in lines[:, 0]]
