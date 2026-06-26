"""Stage A (separation + text) and Stage B (regions / assembly / decompose) tests.

Convention-independent by construction: assertions are on STRUCTURE, never colour.
"""

from __future__ import annotations

import cv2
import numpy as np

from cadplatform.cad_pipeline.assembly import assemble_walls
from cadplatform.cad_pipeline.decompose import GRID, STAIRS, WALL, decompose
from cadplatform.cad_pipeline.geometry import Segment
from cadplatform.cad_pipeline.regions import detect_grid, detect_stairs
from cadplatform.image_engine.layer_separation import (
    discover_palette,
    extract_ink_mask,
    separate_layers,
)

STD = (90.0, 100.0, 150.0, 200.0, 300.0)
GUARD = 40.0


# --- Stage A ---------------------------------------------------------------

def test_synth_separates_to_single_group(sample_plan_png):
    bgr = cv2.imread(sample_plan_png, cv2.IMREAD_COLOR)
    groups = separate_layers(bgr)
    assert len(groups) == 1


def test_palette_discovers_two_colors():
    img = np.full((200, 200, 3), 255, np.uint8)
    cv2.line(img, (10, 50), (190, 50), (0, 0, 255), 3)
    cv2.line(img, (10, 150), (190, 150), (255, 0, 0), 3)
    centroids = discover_palette(img, extract_ink_mask(img), min_frac=0.001)
    assert len(centroids) == 2


# --- Stage B: region detectors (bound to defining features) ----------------

def test_grid_detected_by_spanning_unpaired_crossing():
    sheet = 10000.0
    segs = [Segment(0, y, sheet, y) for y in (1000, 3000, 5000, 7000, 9000)]
    # add crossing verticals so the grid lines "cross much other geometry"
    segs += [Segment(x, 0, x, sheet) for x in (2000, 4000, 6000, 8000)]
    regs, consumed = detect_grid(segs, sheet, sheet, band_lo=50, band_hi=340)
    assert any(r.kind == "grid" for r in regs)
    assert len(consumed) >= 5


def test_paired_wall_not_consumed_as_grid():
    # Two long parallel faces 200mm apart spanning the sheet = a wall, NOT grid.
    sheet = 10000.0
    segs = [Segment(0, 5000, sheet, 5000), Segment(0, 5200, sheet, 5200)]
    regs, consumed = detect_grid(segs, sheet, sheet, band_lo=50, band_hi=340)
    assert not consumed  # paired -> excluded from grid (right reason)


def test_stairs_detected_locally_for_unpaired_ladder():
    sheet = 10000.0
    # tread ladder: 6 unpaired horizontals at constant 300mm pitch, compact span
    segs = [Segment(1000, 2000 + 300 * k, 2500, 2000 + 300 * k) for k in range(6)]
    regs, consumed = detect_stairs(segs, band_lo=50, band_hi=340, sheet_min=10000)
    assert any(r.kind == "stairs" for r in regs)
    assert len(consumed) == 6


# --- Stage B: cross-group assembly -----------------------------------------

def test_assembly_pairs_faces_across_pool():
    sheet = 10000.0
    segs = []
    for x in (1000, 3000, 5000):           # three 200mm wall pairs
        segs += [Segment(x, 500, x, 8000), Segment(x + 200, 500, x + 200, 8000)]
    walls = assemble_walls(segs, [], STD, GUARD, ortho_tol_deg=3.0, sheet_min_mm=sheet)
    assert len(walls) == 3
    assert all(abs(w.thickness_mm - 200) < 1 for w in walls)


# --- Stage B: decomposition + heterogeneity --------------------------------

def test_decompose_flags_heterogeneous_group():
    # ONE group mixing grid lines + a wall pair -> labelled by dominant evidence
    # AND flagged heterogeneous.
    sheet = 10000.0
    grid = [Segment(0, y, sheet, y) for y in (1000, 3000, 5000, 7000)]
    grid += [Segment(x, 0, x, sheet) for x in (2500, 5000, 7500)]
    wall = [Segment(500, 500, 500, 9000), Segment(700, 500, 700, 9000)]
    groups = [{"group_id": 0, "segments": grid + wall, "ink_fraction": 1.0, "color_bgr": (0, 0, 0)}]
    d = decompose(groups, [], sheet, sheet, STD, GUARD, 3.0)
    assert d.group_reports[0].heterogeneous
