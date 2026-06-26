"""Stage A (separation) + Stage B (classification) unit tests.

Convention-independent by construction: tests assert behavior on STRUCTURE, never
on specific colours.
"""

from __future__ import annotations

import cv2
import numpy as np

from cadplatform.cad_pipeline.classify import (
    GRID,
    WALL,
    GroupMeta,
    classify_group,
)
from cadplatform.cad_pipeline.geometry import Segment
from cadplatform.image_engine.layer_separation import discover_palette, separate_layers, extract_ink_mask


def test_synth_separates_to_single_group(sample_plan_png):
    bgr = cv2.imread(sample_plan_png, cv2.IMREAD_COLOR)
    groups = separate_layers(bgr)
    # Pure black-on-white synthetic plan -> exactly one discovered group.
    assert len(groups) == 1
    assert groups[0].mask.shape == bgr.shape[:2]


def test_palette_discovers_two_colors():
    # White sheet with one red and one blue stroke -> two ink groups.
    img = np.full((200, 200, 3), 255, np.uint8)
    cv2.line(img, (10, 50), (190, 50), (0, 0, 255), 3)    # red (BGR)
    cv2.line(img, (10, 150), (190, 150), (255, 0, 0), 3)  # blue
    ink = extract_ink_mask(img)
    centroids = discover_palette(img, ink, min_frac=0.001)
    assert len(centroids) == 2


def test_classify_wall_group(generated_dxf):
    # The synthetic plan's single group must classify as WALL.
    from cadplatform import config
    from cadplatform.image_engine.loader import load_bgr
    from cadplatform.image_engine.detect import detect_wall_edges
    from cadplatform.image_engine.preprocess import denoise

    _, summary = generated_dxf
    assert any(g["label"] == WALL for g in summary["groups"])


def test_grid_like_group_rejected():
    # Long, near-full-sheet, unpaired lines -> GRID (not wall), independent of colour.
    sheet = 10000.0
    segs = [Segment(0, y, sheet, y) for y in (1000, 3000, 5000, 7000, 9000)]
    cls = classify_group(segs, sheet, sheet, (90, 100, 150, 200, 300), 40.0, GroupMeta())
    assert cls.label == GRID


def test_wall_like_group_accepted():
    # Several paired faces at standard thickness, enclosing -> WALL.
    sheet = 10000.0
    segs = []
    for x in (1000, 3000, 5000):           # vertical wall pairs, 200mm apart
        segs.append(Segment(x, 500, x, 8000))
        segs.append(Segment(x + 200, 500, x + 200, 8000))
    cls = classify_group(segs, sheet, sheet, (90, 100, 150, 200, 300), 40.0, GroupMeta())
    assert cls.label == WALL
