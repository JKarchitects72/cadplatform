"""STAGE B — Geometry-based wall classification (pure geometry).

Each discovered group (from Stage A) is classified by CONVENTION-INDEPENDENT
structural tests — never by colour. The group arrives as an opaque id plus its
segments (in mm); colour is not an input here. Output: a label + human-readable
reason + the feature numbers behind the decision.

Labels:
  WALL          confident wall  -> A-WALL-NEWW (then existing thickness pipeline)
  WALL_REVIEW   near-miss wall   -> A-WALL-REVIEW (visible, non-plotting, recoverable)
  GRID          column grid      -> rejected (reported)
  STAIRS        stair treads     -> rejected (reported)
  HATCH         poché fill region-> rejected as lines (evidence for adjacent wall)
  FURNITURE     casework cluster -> rejected (reported)
  ANNOTATION    text/leaders     -> rejected (reported)
  OTHER         unclassified     -> rejected (reported)

Precision-first: a group is WALL only on clear structural evidence; otherwise it is
rejected, but anything with partial wall structure is routed to WALL_REVIEW so
missed recall stays visible.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .geometry import Segment
from .walls import merge_collinear, pair_parallel_edges

WALL = "WALL"
WALL_REVIEW = "WALL_REVIEW"
GRID = "GRID"
STAIRS = "STAIRS"
HATCH = "HATCH"
FURNITURE = "FURNITURE"
ANNOTATION = "ANNOTATION"
OTHER = "OTHER"

# Labels whose geometry is emitted (the rest are rejected, report-only).
EMITTED = {WALL, WALL_REVIEW}


@dataclass
class GroupMeta:
    """Opaque, structure-only metadata from Stage A (NO colour meaning)."""

    stroke_width_mm: float = 0.0
    dash_kind: str = "solid"
    ink_fraction: float = 0.0


@dataclass
class Classification:
    label: str
    reason: str
    features: dict = field(default_factory=dict)
    heterogeneous: bool = False
    hetero_note: str = ""


def _axis_segments(segs: list[Segment]) -> list[Segment]:
    return [s for s in segs if s.x1 == s.x2 or s.y1 == s.y2]


def _spans_sheet(segs, sheet_min, frac):
    return [s for s in segs if s.length > frac * sheet_min]


def _stair_runs(segs: list[Segment], min_run: int, pitch_tol: float):
    """Count runs of >=min_run parallel co-axial edges at near-constant pitch."""
    runs = 0
    for horizontal in (True, False):
        pos = sorted(
            ((s.y1 + s.y2) / 2 if horizontal else (s.x1 + s.x2) / 2)
            for s in segs
            if (s.y1 == s.y2) == horizontal and (s.x1 == s.x2) != horizontal
        )
        if len(pos) < min_run:
            continue
        gaps = [b - a for a, b in zip(pos, pos[1:])]
        i = 0
        while i < len(gaps):
            j = i
            while j + 1 < len(gaps) and abs(gaps[j + 1] - gaps[i]) <= pitch_tol * max(gaps[i], 1):
                j += 1
            if (j - i + 1) >= (min_run - 1) and gaps[i] > 0:
                runs += 1
            i = j + 1
    return runs


def classify_group(
    segments: list[Segment],
    sheet_w_mm: float,
    sheet_h_mm: float,
    standards_mm: tuple[float, ...],
    guard_mm: float,
    meta: GroupMeta | None = None,
) -> Classification:
    meta = meta or GroupMeta()
    sheet_min = min(sheet_w_mm, sheet_h_mm)
    n = len(segments)
    if n == 0:
        return Classification(OTHER, "empty group (no segments)")

    lengths = [s.length for s in segments]
    total_len = sum(lengths)
    median_len = sorted(lengths)[n // 2]

    band_lo = max(1.0, min(standards_mm) - guard_mm)
    band_hi = max(standards_mm) + guard_mm

    # --- wall-pair evidence (the positive structural signal) ---
    axis = _axis_segments(segments)
    # axis_tol must stay well BELOW the thickness band, or a wall's two faces get
    # merged into one and the pair structure is destroyed.
    axis_tol = min(20.0, 0.3 * band_lo)
    edges = merge_collinear(axis, axis_tol_mm=axis_tol, gap_tol_mm=band_hi)
    pairs = pair_parallel_edges(
        edges, min_thickness_mm=band_lo, max_thickness_mm=band_hi,
        overlap_frac=0.3, min_edge_length_mm=0.05 * sheet_min,
    )
    paired_len = sum(p.centerline.length for p in pairs)
    coverage = min(1.0, (2.0 * paired_len) / total_len) if total_len else 0.0
    in_band = [p for p in pairs if band_lo <= (p.raw_thickness_mm or 0) <= band_hi]

    # --- other structural signals ---
    long_span = _spans_sheet(segments, sheet_min, 0.8)          # near full-sheet lines
    long_unpaired = max(0, len(long_span) - len(in_band))
    stair_runs = _stair_runs(segments, min_run=4, pitch_tol=0.25)
    short_frac = sum(1 for L in lengths if L < 0.03 * sheet_min) / n
    diag_frac = sum(
        1 for s in segments
        if 10 < (math.degrees(math.atan2(s.y2 - s.y1, s.x2 - s.x1)) % 90) < 80
    ) / n

    feats = {
        "n_segments": n,
        "n_wall_pairs": len(in_band),
        "coverage": round(coverage, 3),
        "median_len_mm": round(median_len, 1),
        "long_spanning": len(long_span),
        "stair_runs": stair_runs,
        "short_frac": round(short_frac, 2),
        "diag_frac": round(diag_frac, 2),
        "stroke_w_mm": round(meta.stroke_width_mm, 1),
        "dash": meta.dash_kind,
    }

    # --- evidence booleans (for heterogeneity reporting) ---
    ev_wall = len(in_band) >= 3 and coverage >= 0.35
    ev_grid = long_unpaired >= 3
    ev_stairs = stair_runs >= 1

    hetero = sum([ev_wall, ev_grid, ev_stairs]) >= 2
    hetero_note = ""
    if hetero:
        parts = [name for name, on in
                 (("wall", ev_wall), ("grid", ev_grid), ("stairs", ev_stairs)) if on]
        hetero_note = (
            f"v1-limit: single colour-group mixes sub-populations ({'+'.join(parts)}); "
            "color-primary separation cannot split them this pass"
        )

    def C(label, reason):
        return Classification(label, reason, feats, hetero, hetero_note)

    # --- precision-first cascade ---
    if ev_grid and long_unpaired >= 3 and len(in_band) < 3:
        return C(GRID, f"{long_unpaired} near-full-sheet unpaired lines"
                       f"{' (dash-dot)' if meta.dash_kind == 'broken' else ''}")

    if ev_stairs and not ev_wall:
        return C(STAIRS, f"{stair_runs} run(s) of >=4 equally-spaced parallels (treads)")

    # hatch: dense short parallels, mostly diagonal, no wall-pair structure
    if short_frac > 0.6 and diag_frac > 0.5 and len(in_band) < 2 and n >= 20:
        return C(HATCH, f"dense short diagonal fill ({int(short_frac*100)}% short, "
                        f"{int(diag_frac*100)}% diagonal) — poché fill, not lines")

    if ev_wall:
        return C(WALL, f"{len(in_band)} paired faces in thickness band, "
                       f"coverage {coverage:.0%}")

    # near-miss wall -> visible review, not silent drop
    if len(in_band) >= 1 and coverage >= 0.12:
        return C(WALL_REVIEW, f"partial wall structure ({len(in_band)} pair(s), "
                              f"coverage {coverage:.0%}) below WALL threshold")

    # furniture: short closed-ish clusters, interior, little wall structure
    if short_frac > 0.5 and median_len < 0.15 * sheet_min and len(in_band) < 1:
        return C(FURNITURE, f"small short-segment clusters (median {median_len:.0f}mm), "
                            "no wall pairs")

    if meta.dash_kind == "broken" or short_frac > 0.5:
        return C(ANNOTATION, "thin/broken short strokes, no wall structure")

    return C(OTHER, "no clear wall structure")
