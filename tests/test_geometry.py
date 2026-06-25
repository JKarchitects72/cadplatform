"""Unit tests for the pure-geometry rules (orthogonalization, pairing, snap)."""

from __future__ import annotations

from cadplatform.cad_pipeline.geometry import Segment
from cadplatform.cad_pipeline.orthogonalize import orthogonalize_segment
from cadplatform.cad_pipeline.walls import (
    merge_collinear,
    pair_parallel_edges,
    snap_thickness,
)

STANDARDS = (90.0, 100.0, 120.0, 150.0, 200.0, 250.0, 300.0)
GUARD = 40.0


def test_orthogonalize_snaps_near_horizontal():
    seg = Segment(0, 0, 100, 2)  # ~1.1 deg
    out = orthogonalize_segment(seg, tol_deg=3.0)
    assert out.y1 == out.y2


def test_orthogonalize_preserves_intentional_diagonal():
    seg = Segment(0, 0, 100, 100)  # 45 deg
    out = orthogonalize_segment(seg, tol_deg=3.0)
    assert out == seg


def test_snap_thickness_snaps_within_guard():
    snap = snap_thickness(148.0, STANDARDS, GUARD)
    assert snap.value_mm == 150.0
    assert not snap.flagged


def test_snap_thickness_flags_outlier():
    snap = snap_thickness(420.0, STANDARDS, GUARD)  # nearest 300, dist 120 > guard
    assert snap.flagged
    assert snap.value_mm == 420.0  # not force-snapped


def test_merge_collinear_bridges_junction_gap():
    # Two collinear fragments split by a junction gap rejoin into one edge.
    segs = [Segment(0, 100, 50, 100), Segment(70, 100, 200, 100)]
    merged = merge_collinear(segs, axis_tol_mm=5.0, gap_tol_mm=40.0)
    assert len(merged) == 1
    assert (merged[0].x1, merged[0].x2) == (0, 200)


def test_pairing_measures_thickness_from_parallel_edges():
    # Two parallel horizontal edges 200 mm apart, same span -> one 200 mm wall.
    edges = [Segment(0, 0, 1000, 0), Segment(0, 200, 1000, 200)]
    walls = pair_parallel_edges(edges, min_thickness_mm=40, max_thickness_mm=600)
    assert len(walls) == 1
    assert walls[0].raw_thickness_mm == 200.0
    # Centerline sits midway and spans the shared extent.
    c = walls[0].centerline
    assert c.y1 == c.y2 == 100.0
    assert (c.x1, c.x2) == (0, 1000)


def test_pairing_separates_two_adjacent_walls():
    # Faces ordered y=0,100 (wall A) and y=400,500 (wall B). Nearest-gap exclusive
    # matching must pair A's faces and B's faces, never the 100<->400 inner faces.
    edges = [
        Segment(0, 0, 1000, 0),
        Segment(0, 100, 1000, 100),
        Segment(0, 400, 1000, 400),
        Segment(0, 500, 1000, 500),
    ]
    walls = pair_parallel_edges(edges, min_thickness_mm=40, max_thickness_mm=600)
    thicknesses = sorted(w.raw_thickness_mm for w in walls)
    assert thicknesses == [100.0, 100.0]
