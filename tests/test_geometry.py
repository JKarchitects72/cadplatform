"""Unit tests for the pure-geometry rules (orthogonalization, thickness snap)."""

from __future__ import annotations

from cadplatform.cad_pipeline.geometry import Segment
from cadplatform.cad_pipeline.orthogonalize import orthogonalize_segment
from cadplatform.cad_pipeline.walls import merge_centerlines, snap_thickness

STANDARDS = (90.0, 100.0, 120.0, 150.0, 200.0, 250.0, 300.0)
GUARD = 40.0


def test_orthogonalize_snaps_near_horizontal():
    seg = Segment(0, 0, 100, 2)  # ~1.1 deg
    out = orthogonalize_segment(seg, tol_deg=3.0)
    assert out.y1 == out.y2  # snapped flat


def test_orthogonalize_preserves_intentional_diagonal():
    seg = Segment(0, 0, 100, 100)  # 45 deg
    out = orthogonalize_segment(seg, tol_deg=3.0)
    assert out == seg  # untouched


def test_snap_thickness_snaps_within_guard():
    snap = snap_thickness(148.0, STANDARDS, GUARD)
    assert snap.value_mm == 150.0
    assert not snap.flagged


def test_snap_thickness_flags_outlier():
    snap = snap_thickness(420.0, STANDARDS, GUARD)  # nearest is 300, dist 120 > guard
    assert snap.flagged
    assert snap.value_mm == 420.0  # not force-snapped


def test_merge_centerlines_collapses_fragments():
    # Two collinear horizontal fragments on the same y should merge into one.
    segs = [Segment(0, 100, 50, 100), Segment(40, 100, 120, 100)]
    merged = merge_centerlines(segs, axis_tol_mm=10.0, gap_tol_mm=20.0)
    assert len(merged) == 1
    m = merged[0]
    assert (m.x1, m.x2) == (0, 120)
