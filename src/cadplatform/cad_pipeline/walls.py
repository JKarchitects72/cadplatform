"""Wall centerline merging and thickness standardization.

Two responsibilities, both pure geometry (CLAUDE.md rule 1):
  - merge fragmented orthogonal segments into single spanning centerlines;
  - snap a measured wall thickness to the configurable standard set, with a
    max-snap-distance guard that FLAGS outliers instead of force-snapping
    (CLAUDE.md rule 4).
"""

from __future__ import annotations

from dataclasses import dataclass

from .geometry import Segment, Wall


@dataclass(frozen=True)
class ThicknessSnap:
    """Result of snapping a measured thickness to the standard set."""

    value_mm: float          # snapped value (or the raw value when flagged)
    flagged: bool            # True when no standard value is within the guard
    distance_mm: float       # distance to the nearest standard value


def snap_thickness(
    measured_mm: float,
    standards_mm: tuple[float, ...],
    guard_mm: float,
) -> ThicknessSnap:
    """Snap ``measured_mm`` to the nearest standard value within ``guard_mm``.

    If the nearest standard is farther than the guard, the value is FLAGGED for
    review and returned unsnapped (CLAUDE.md rule 4 — never force-snap outliers).
    """
    nearest = min(standards_mm, key=lambda s: abs(s - measured_mm))
    distance = abs(nearest - measured_mm)
    if distance > guard_mm:
        return ThicknessSnap(value_mm=measured_mm, flagged=True, distance_mm=distance)
    return ThicknessSnap(value_mm=nearest, flagged=False, distance_mm=distance)


def _merge_runs(values: list[tuple[float, float]], gap_tol: float) -> list[tuple[float, float]]:
    """Merge overlapping/near-touching 1-D intervals into spanning runs."""
    if not values:
        return []
    values = sorted((min(a, b), max(a, b)) for a, b in values)
    merged = [values[0]]
    for lo, hi in values[1:]:
        plo, phi = merged[-1]
        if lo <= phi + gap_tol:
            merged[-1] = (plo, max(phi, hi))
        else:
            merged.append((lo, hi))
    return merged


def merge_centerlines(
    segments: list[Segment],
    axis_tol_mm: float,
    gap_tol_mm: float,
) -> list[Segment]:
    """Collapse fragmented orthogonal segments into single centerlines.

    Horizontal segments sharing a y (within ``axis_tol_mm``) are grouped and
    their overlapping x-extents merged; vertical segments are handled
    symmetrically on x. Non-orthogonal segments are passed through unchanged so
    intentional diagonals survive (CLAUDE.md rule 1a).
    """
    horizontals: list[Segment] = []
    verticals: list[Segment] = []
    passthrough: list[Segment] = []

    for s in segments:
        if s.y1 == s.y2:
            horizontals.append(s)
        elif s.x1 == s.x2:
            verticals.append(s)
        else:
            passthrough.append(s)

    out: list[Segment] = list(passthrough)
    out += _merge_axis(horizontals, axis_tol_mm, gap_tol_mm, horizontal=True)
    out += _merge_axis(verticals, axis_tol_mm, gap_tol_mm, horizontal=False)
    return out


def _merge_axis(
    segs: list[Segment],
    axis_tol: float,
    gap_tol: float,
    horizontal: bool,
) -> list[Segment]:
    """Group co-axial segments by their fixed coordinate, then merge extents."""
    # bucket key = the fixed coordinate (y for horizontals, x for verticals)
    buckets: list[tuple[float, list[Segment]]] = []
    for s in segs:
        key = s.y1 if horizontal else s.x1
        for i, (bkey, members) in enumerate(buckets):
            if abs(bkey - key) <= axis_tol:
                members.append(s)
                # keep bucket key as the running mean for stability
                buckets[i] = ((bkey * len(members) + key) / (len(members) + 1), members)
                break
        else:
            buckets.append((key, [s]))

    result: list[Segment] = []
    for fixed, members in buckets:
        spans = [
            (s.x1, s.x2) if horizontal else (s.y1, s.y2) for s in members
        ]
        for lo, hi in _merge_runs(spans, gap_tol):
            if horizontal:
                result.append(Segment(lo, fixed, hi, fixed))
            else:
                result.append(Segment(fixed, lo, fixed, hi))
    return result


def to_walls(centerlines: list[Segment]) -> list[Wall]:
    """Wrap merged centerlines as Wall objects (layer assigned downstream)."""
    return [Wall(centerline=c) for c in centerlines]
