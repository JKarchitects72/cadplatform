"""Wall edge consolidation, parallel-edge pairing, and thickness standardization.

Pure geometry (CLAUDE.md rule 1). The order of operations matters: thickness is
measured from PAIRED EDGES *before* anything is collapsed to a centerline, or the
information is lost.

  detect edges -> orthogonalize -> merge_collinear (consolidate fragments)
              -> pair_parallel_edges (MEASURE thickness) -> standardize_thickness
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .geometry import Segment, Wall


# --------------------------------------------------------------------------- #
# Thickness snapping (CLAUDE.md rule 4)
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class ThicknessSnap:
    """Result of snapping a measured thickness to the standard set."""

    value_mm: float          # snapped value (or the raw value when flagged)
    flagged: bool            # True when no standard value is within the guard
    distance_mm: float       # distance to the nearest standard value
    nearest_mm: float        # the nearest standard value considered


def snap_thickness(
    measured_mm: float,
    standards_mm: tuple[float, ...],
    guard_mm: float,
) -> ThicknessSnap:
    """Snap ``measured_mm`` to the nearest standard within ``guard_mm``.

    If the nearest standard is farther than the guard, the value is FLAGGED for
    review and returned unsnapped (never force-snap outliers).
    """
    nearest = min(standards_mm, key=lambda s: abs(s - measured_mm))
    distance = abs(nearest - measured_mm)
    if distance > guard_mm:
        return ThicknessSnap(measured_mm, True, distance, nearest)
    return ThicknessSnap(nearest, False, distance, nearest)


# --------------------------------------------------------------------------- #
# Collinear fragment consolidation (run BEFORE pairing)
# --------------------------------------------------------------------------- #

def _merge_runs(intervals: list[tuple[float, float]], gap_tol: float) -> list[tuple[float, float]]:
    """Merge overlapping / near-touching 1-D intervals into spanning runs."""
    if not intervals:
        return []
    intervals = sorted((min(a, b), max(a, b)) for a, b in intervals)
    merged = [intervals[0]]
    for lo, hi in intervals[1:]:
        plo, phi = merged[-1]
        if lo <= phi + gap_tol:
            merged[-1] = (plo, max(phi, hi))
        else:
            merged.append((lo, hi))
    return merged


def merge_collinear(
    segments: list[Segment],
    axis_tol_mm: float,
    gap_tol_mm: float,
) -> list[Segment]:
    """Stitch collinear orthogonal fragments into continuous edges.

    Horizontal segments sharing a y (within ``axis_tol_mm``) are grouped and
    their overlapping x-extents merged (bridging gaps up to ``gap_tol_mm``, which
    rejoins edges interrupted at junctions); verticals are handled symmetrically.

    ``axis_tol_mm`` must be SMALL (a few mm) so the two parallel faces of one
    wall are NOT merged together — only truly collinear fragments are.
    """
    horizontals = [s for s in segments if s.y1 == s.y2]
    verticals = [s for s in segments if s.x1 == s.x2]
    passthrough = [s for s in segments if s.y1 != s.y2 and s.x1 != s.x2]

    out: list[Segment] = list(passthrough)
    out += _merge_axis(horizontals, axis_tol_mm, gap_tol_mm, horizontal=True)
    out += _merge_axis(verticals, axis_tol_mm, gap_tol_mm, horizontal=False)
    return out


def _merge_axis(segs, axis_tol, gap_tol, horizontal):
    buckets: list[tuple[float, list[Segment]]] = []
    for s in segs:
        key = s.y1 if horizontal else s.x1
        for i, (bkey, members) in enumerate(buckets):
            if abs(bkey - key) <= axis_tol:
                members.append(s)
                buckets[i] = ((bkey * len(members) + key) / (len(members) + 1), members)
                break
        else:
            buckets.append((key, [s]))

    result: list[Segment] = []
    for fixed, members in buckets:
        spans = [(s.x1, s.x2) if horizontal else (s.y1, s.y2) for s in members]
        for lo, hi in _merge_runs(spans, gap_tol):
            result.append(
                Segment(lo, fixed, hi, fixed) if horizontal else Segment(fixed, lo, fixed, hi)
            )
    return result


# --------------------------------------------------------------------------- #
# Parallel-edge pairing — measures thickness (the heart of this stage)
# --------------------------------------------------------------------------- #

@dataclass
class _Edge:
    pos: float          # fixed coordinate (y for horizontal, x for vertical)
    lo: float           # span start along the running axis
    hi: float           # span end
    horizontal: bool

    @property
    def length(self) -> float:
        return self.hi - self.lo


def pair_parallel_edges(
    segments: list[Segment],
    min_thickness_mm: float,
    max_thickness_mm: float,
    overlap_frac: float = 0.3,
    min_edge_length_mm: float = 0.0,
) -> list[Wall]:
    """Pair the two parallel faces of each wall and measure its thickness.

    A pair qualifies when the two edges:
      * are co-oriented (both horizontal or both vertical),
      * overlap along their shared axis by >= ``overlap_frac`` of the shorter,
      * are separated by a perpendicular gap in
        ``[min_thickness_mm, max_thickness_mm]``.
    Pairs are accepted greedily by smallest gap first, consuming each edge once,
    so a wall's own faces match before any spurious neighbour pair can form.

    Returns Wall objects with ``centerline`` and ``raw_thickness_mm`` set.
    """
    edges: list[_Edge] = []
    for s in segments:
        if s.y1 == s.y2:
            e = _Edge(s.y1, min(s.x1, s.x2), max(s.x1, s.x2), horizontal=True)
        elif s.x1 == s.x2:
            e = _Edge(s.x1, min(s.y1, s.y2), max(s.y1, s.y2), horizontal=False)
        else:
            continue  # non-orthogonal: not a wall face in this slice
        if e.length >= min_edge_length_mm:
            edges.append(e)

    horizontals = [e for e in edges if e.horizontal]
    verticals = [e for e in edges if not e.horizontal]
    return _pair_axis(horizontals, min_thickness_mm, max_thickness_mm, overlap_frac) + _pair_axis(
        verticals, min_thickness_mm, max_thickness_mm, overlap_frac
    )


def _pair_axis(edges, min_t, max_t, overlap_frac) -> list[Wall]:
    # Build all qualifying candidate pairs, sorted by perpendicular gap ascending.
    candidates = []
    for i in range(len(edges)):
        for j in range(i + 1, len(edges)):
            a, b = edges[i], edges[j]
            gap = abs(a.pos - b.pos)
            if not (min_t <= gap <= max_t):
                continue
            ov = min(a.hi, b.hi) - max(a.lo, b.lo)
            if ov <= 0:
                continue
            if ov < overlap_frac * min(a.length, b.length):
                continue
            candidates.append((gap, i, j, ov))
    candidates.sort(key=lambda c: c[0])

    used: set[int] = set()
    walls: list[Wall] = []
    for gap, i, j, _ov in candidates:
        if i in used or j in used:
            continue
        used.add(i)
        used.add(j)
        a, b = edges[i], edges[j]
        pos = (a.pos + b.pos) / 2.0
        lo = max(a.lo, b.lo)
        hi = min(a.hi, b.hi)
        if a.horizontal:
            centerline = Segment(lo, pos, hi, pos)
        else:
            centerline = Segment(pos, lo, pos, hi)
        walls.append(Wall(centerline=centerline, raw_thickness_mm=gap))
    return walls


# --------------------------------------------------------------------------- #
# Standardization: feed measured thickness into the snap guard
# --------------------------------------------------------------------------- #

def standardize_thickness(
    walls: list[Wall],
    standards_mm: tuple[float, ...],
    guard_mm: float,
) -> list[Wall]:
    """Snap each wall's raw thickness; flag and annotate outliers in place."""
    for w in walls:
        if w.raw_thickness_mm is None:
            continue
        snap = snap_thickness(w.raw_thickness_mm, standards_mm, guard_mm)
        w.thickness_mm = snap.value_mm
        w.flagged = snap.flagged
        if snap.flagged:
            w.note = (
                f"outlier: measured {w.raw_thickness_mm:.0f}mm, nearest standard "
                f"{snap.nearest_mm:.0f}mm (dist {snap.distance_mm:.0f}mm > guard)"
            )
    return walls
