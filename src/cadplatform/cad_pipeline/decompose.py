"""STAGE B orchestrator — evidence-based decomposition (replaces the cascade).

For every group we compute each structural evidence INDEPENDENTLY (Gate 1: each
label is driven by its own bound feature), then:
  1. region detectors claim stairs / hatch / grid across the whole pool,
  2. cross-group assembly pairs the remaining faces into walls (single emitter),
  3. each group is labelled by its DOMINANT structural evidence, and flagged
     HETEROGENEOUS when two evidences co-occur (catches big mixed groups).

Colour is never an input. Group identity is only an attribution key.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .assembly import assemble_walls
from .geometry import Segment, Wall
from .layers import assign_wall_layers
from .orthogonalize import orthogonalize
from .regions import detect_grid, detect_hatch, detect_stairs
from .walls import merge_collinear, pair_parallel_edges

WALL = "WALL"
GRID = "GRID"
STAIRS = "STAIRS"
HATCH = "HATCH"
FURNITURE = "FURNITURE"
ANNOTATION = "ANNOTATION"
OTHER = "OTHER"


@dataclass
class GroupReport:
    group_id: int
    label: str
    reason: str
    shares: dict
    heterogeneous: bool = False
    hetero_note: str = ""
    ink_fraction: float = 0.0


@dataclass
class Decomposition:
    walls: list[Wall]
    group_reports: list[GroupReport]
    region_counts: dict = field(default_factory=dict)


def _len(s: Segment) -> float:
    return math.hypot(s.x2 - s.x1, s.y2 - s.y1)


def _mid(s: Segment) -> tuple:
    return ((s.x1 + s.x2) / 2, (s.y1 + s.y2) / 2)


def _in_box(p, box) -> bool:
    return box[0] <= p[0] <= box[2] and box[1] <= p[1] <= box[3]


def _wall_len(segs, standards, guard, max_std, ortho_tol) -> float:
    if not segs:
        return 0.0
    o = orthogonalize(segs, ortho_tol)
    e = merge_collinear(o, axis_tol_mm=20.0, gap_tol_mm=2.0 * max_std)
    pairs = pair_parallel_edges(
        e, min_thickness_mm=0.5 * min(standards), max_thickness_mm=2.0 * max_std,
        overlap_frac=0.3, min_edge_length_mm=max_std + guard,
    )
    return sum(p.centerline.length for p in pairs)


def decompose(
    groups: list[dict],            # {group_id, segments(mm), ink_fraction, color_bgr}
    text_boxes_mm: list[tuple],    # (xlo,ylo,xhi,yhi) in mm
    sheet_w_mm: float,
    sheet_h_mm: float,
    standards_mm: tuple,
    guard_mm: float,
    ortho_tol_deg: float,
) -> Decomposition:
    max_std = max(standards_mm)
    band_lo = max(1.0, min(standards_mm) - guard_mm)
    band_hi = max_std + guard_mm
    sheet_min = min(sheet_w_mm, sheet_h_mm)

    # ---- build the cross-group pool, remembering each segment's origin group ----
    pool: list[Segment] = []
    owner: list[int] = []
    for g in groups:
        for s in g["segments"]:
            pool.append(s)
            owner.append(g["group_id"])

    # ---- region detectors CLAIM non-wall geometry first (each by its feature) ----
    stairs_regs, c_st = detect_stairs(pool, band_lo, band_hi, sheet_min)
    hatch_regs, c_ha = detect_hatch(pool, sheet_min)
    grid_regs, c_gr = detect_grid(pool, sheet_w_mm, sheet_h_mm, band_lo, band_hi)
    consumed = c_st | c_ha | c_gr

    # ---- cross-group assembly on what remains (single wall emitter) ----
    remaining = [i for i in range(len(pool)) if i not in consumed]
    rem_segs = [pool[i] for i in remaining]
    hatch_boxes = [r.bbox for r in hatch_regs]
    walls = assemble_walls(rem_segs, hatch_boxes, standards_mm, guard_mm,
                           ortho_tol_deg, sheet_min)
    assign_wall_layers(walls)  # thickness outliers -> A-WALL-REVIEW, rest -> NEWW

    # ---- per-group evidence (each kind measured independently) ----
    reports: list[GroupReport] = []
    for g in groups:
        gid = g["group_id"]
        gseg = g["segments"]
        idxs = [i for i in range(len(pool)) if owner[i] == gid]
        total = sum(_len(pool[i]) for i in idxs) or 1.0

        L = {k: 0.0 for k in ("wall", "grid", "stairs", "hatch", "annotation")}
        unclaimed = []
        for i in idxs:
            s = pool[i]
            if i in c_st:
                L["stairs"] += _len(s)
            elif i in c_ha:
                L["hatch"] += _len(s)
            elif i in c_gr:
                L["grid"] += _len(s)
            elif any(_in_box(_mid(s), b) for b in text_boxes_mm):
                L["annotation"] += _len(s)
            else:
                unclaimed.append(s)
        # wall evidence from this group's own un-claimed faces (approx; cross-group
        # walls may exceed any single group's share — that is the point of assembly).
        # Credit both faces (2x centerline) so wall is measured on the same basis as
        # the region kinds (consumed raw-segment length).
        L["wall"] = 2.0 * _wall_len(unclaimed, standards_mm, guard_mm, max_std, ortho_tol_deg)
        other = max(0.0, total - sum(L.values()))

        shares = {k: round(v / total, 2) for k, v in L.items()}
        shares["other"] = round(other / total, 2)

        # short-segment fraction distinguishes FURNITURE from generic OTHER
        short_frac = (sum(1 for s in gseg if _len(s) < 0.03 * sheet_min) / len(gseg)) if gseg else 0.0

        ranked = sorted(L.items(), key=lambda kv: kv[1], reverse=True)
        dom_kind, dom_len = ranked[0]
        if dom_len <= other:
            label = FURNITURE if short_frac > 0.5 else OTHER
            reason = f"no dominant wall/region evidence (other={shares['other']}, short={short_frac:.2f})"
        else:
            label = {"wall": WALL, "grid": GRID, "stairs": STAIRS,
                     "hatch": HATCH, "annotation": ANNOTATION}[dom_kind]
            reason = f"dominant evidence {dom_kind}={shares[dom_kind]} of group ink"

        strong = [k for k, v in shares.items() if k != "other" and v > 0.2]
        heterogeneous = len(strong) >= 2
        hetero_note = ""
        if heterogeneous:
            mix = ", ".join(f"{k}={shares[k]}" for k in strong)
            hetero_note = (f"group mixes sub-populations ({mix}); "
                           "v1 colour-primary separation cannot split them")

        reports.append(GroupReport(
            group_id=gid, label=label, reason=reason, shares=shares,
            heterogeneous=heterogeneous, hetero_note=hetero_note,
            ink_fraction=g.get("ink_fraction", 0.0),
        ))

    return Decomposition(
        walls=walls,
        group_reports=reports,
        region_counts={"grid": len(grid_regs), "stairs": len(stairs_regs), "hatch": len(hatch_regs)},
    )
