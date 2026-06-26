"""STAGE A metadata — structural text-region detection (no OCR).

Detects WHERE text-shaped connected-component clusters sit, as opaque "text is
here" metadata. It never reads what the text says — reading is M6. Here it exists
only to tell geometry (Stage B / ANNOTATION) where NOT to look for walls.

Convention-independent: text is found by component SHAPE and CLUSTERING, never by
colour. Output: a list of pixel-space bounding boxes (x, y, w, h).
"""

from __future__ import annotations

import cv2
import numpy as np

from .layer_separation import extract_ink_mask


def detect_text_regions(bgr: np.ndarray) -> list[tuple[int, int, int, int]]:
    """Return bounding boxes of clustered text-like glyph components (px)."""
    ink = extract_ink_mask(bgr)
    h_img, w_img = ink.shape
    s = min(h_img, w_img)

    # Character-like component size, expressed as a fraction of the sheet so it is
    # resolution/convention-independent.
    h_lo, h_hi = 0.0015 * s, 0.02 * s
    w_hi = 0.03 * s

    n, _, stats, cents = cv2.connectedComponentsWithStats(ink, connectivity=8)
    glyphs = []  # (cx, cy, h)
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if not (h_lo <= h <= h_hi):
            continue
        if w > w_hi:
            continue
        if (w * h) == 0 or area / (w * h) < 0.15:   # too sparse -> a stroke, not a glyph
            continue
        if not (0.05 <= w / h <= 3.0):              # glyph-ish aspect
            continue
        glyphs.append((cents[i][0], cents[i][1], h))

    if len(glyphs) < 3:
        return []

    # Cluster glyphs that sit within ~1.5 glyph-heights of each other (a text run).
    pts = np.array([[g[0], g[1]] for g in glyphs], np.float32)
    med_h = float(np.median([g[2] for g in glyphs]))
    radius = 1.5 * med_h

    used = np.zeros(len(pts), bool)
    boxes: list[tuple[int, int, int, int]] = []
    for i in range(len(pts)):
        if used[i]:
            continue
        # simple agglomeration by spatial proximity
        members = [i]
        used[i] = True
        changed = True
        while changed:
            changed = False
            d = np.linalg.norm(pts - pts[members].mean(axis=0), axis=1)
            for j in np.where((d < radius) & (~used))[0]:
                members.append(int(j)); used[j] = True; changed = True
        if len(members) >= 3:
            mp = pts[members]
            x0, y0 = mp.min(axis=0); x1, y1 = mp.max(axis=0)
            pad = med_h
            boxes.append((int(x0 - pad), int(y0 - pad),
                          int(x1 - x0 + 2 * pad), int(y1 - y0 + 2 * pad)))
    return boxes
