"""STAGE B assembly — the SINGLE source of wall emission (pure geometry).

After region detectors claim stairs/hatch/grid, the remaining long edges from ALL
groups are pooled into ONE geometric face-pool and paired by geometry — so a wall
whose two faces live in different colour-groups is still assembled. A hatch region
sitting spatially BETWEEN a face pair confirms the wall.

Anti-pattern guards (Gate 2 — these are the literal PR review checklist):
  1. The face-pool is built from EVERY group; no group is privileged as "the wall
     layer".
  2. Hatch is matched by its own geometry (a region between two faces), never by
     "this colour is the hatch layer".
  3. Face<->hatch association is pure spatial containment.
  4. Group identity is used ONLY for de-dup/attribution, never as meaning.
Nothing in this module reads colour or group identity to decide wall-ness.
"""

from __future__ import annotations

from .geometry import Segment, Wall
from .orthogonalize import orthogonalize
from .walls import merge_collinear, pair_parallel_edges, standardize_thickness


def _hatch_between(wall: Wall, hatch_bboxes: list[tuple]) -> bool:
    """True if a hatch region lies within the wall's thickness strip and span."""
    c = wall.centerline
    horizontal = c.y1 == c.y2
    t = (wall.thickness_mm or 0) / 2 + 1.0
    for (xlo, ylo, xhi, yhi) in hatch_bboxes:
        cx, cy = (xlo + xhi) / 2, (ylo + yhi) / 2
        if horizontal:
            if min(c.x1, c.x2) <= cx <= max(c.x1, c.x2) and abs(cy - c.y1) <= t:
                return True
        else:
            if min(c.y1, c.y2) <= cy <= max(c.y1, c.y2) and abs(cx - c.x1) <= t:
                return True
    return False


def assemble_walls(
    pool_segments: list[Segment],
    hatch_bboxes: list[tuple],
    standards_mm: tuple[float, ...],
    guard_mm: float,
    ortho_tol_deg: float,
    sheet_min_mm: float,
    conf_len_frac: float = 0.12,
) -> list[Wall]:
    """Pair faces across the pooled geometry and emit walls (production params).

    Identical geometry/params to the validated single-group pipeline, so a pool
    that contains exactly one clean group reduces byte-for-byte to that result.

    Confirmation gate: a pair is a confident wall when a hatch region lies between
    its faces OR its faces are wall-scale long (>= ``conf_len_frac`` of the sheet).
    UNCONFIRMED pairs (e.g. short furniture-edge parallels) are not dropped — they
    are flagged so they surface on A-WALL-REVIEW, visible and recoverable.
    """
    max_std = max(standards_mm)
    ortho = orthogonalize(pool_segments, ortho_tol_deg)
    edges = merge_collinear(ortho, axis_tol_mm=20.0, gap_tol_mm=2.0 * max_std)
    walls = pair_parallel_edges(
        edges,
        min_thickness_mm=0.5 * min(standards_mm),
        max_thickness_mm=2.0 * max_std,
        overlap_frac=0.3,
        min_edge_length_mm=max_std + guard_mm,
    )
    standardize_thickness(walls, standards_mm, guard_mm)

    conf_len = conf_len_frac * sheet_min_mm
    for w in walls:
        hatch = _hatch_between(w, hatch_bboxes)
        if hatch:
            w.note = (w.note + "; hatch-confirmed").strip("; ")
        if not (hatch or w.centerline.length >= conf_len):
            w.flagged = True
            w.note = (w.note + "; unconfirmed: short faces, no hatch").strip("; ")
    return walls
