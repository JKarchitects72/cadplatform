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
    label: str                 # FINAL label (geometry, vision, or fallback)
    reason: str
    shares: dict
    heterogeneous: bool = False
    hetero_note: str = ""
    ink_fraction: float = 0.0
    geom_label: str = ""       # what geometry alone concluded
    source: str = "geometry"   # "geometry" | "vision" | "fallback"
    ambiguous: bool = False
    confidence: float = 1.0    # geometry margin (top1 - top2)
    vis_confidence: float | None = None
    vis_reason: str = ""


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


def _attribute(wall: Wall, segs: list[Segment], owners: list[int]) -> int | None:
    """Primary owning group of a wall = the group contributing most face length.

    Pure geometry/identity bookkeeping (proximity of original segments to the
    wall's faces). Used only to route NEWW/REVIEW — never to move a coordinate.
    """
    c = wall.centerline
    horizontal = c.y1 == c.y2
    pos = c.y1 if horizontal else c.x1
    lo, hi = (min(c.x1, c.x2), max(c.x1, c.x2)) if horizontal else (min(c.y1, c.y2), max(c.y1, c.y2))
    half = (wall.thickness_mm or 0) / 2 + 5.0
    tally: dict = {}
    for s, o in zip(segs, owners):
        sh = s.y1 == s.y2
        if sh != horizontal:
            continue
        spos = s.y1 if sh else s.x1
        if abs(spos - pos) > half:
            continue
        slo, shi = (min(s.x1, s.x2), max(s.x1, s.x2)) if sh else (min(s.y1, s.y2), max(s.y1, s.y2))
        ov = min(hi, shi) - max(lo, slo)
        if ov > 0:
            tally[o] = tally.get(o, 0.0) + ov
    return max(tally, key=tally.get) if tally else None


def decompose(
    groups: list[dict],            # {group_id, segments(mm), ink_fraction}
    text_boxes_mm: list[tuple],    # (xlo,ylo,xhi,yhi) in mm
    sheet_w_mm: float,
    sheet_h_mm: float,
    standards_mm: tuple,
    guard_mm: float,
    ortho_tol_deg: float,
    judge=None,                    # callable(group_id) -> VisionVerdict | None
    amb_top1: float = 0.55,
    amb_margin: float = 0.20,
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

    # ---- per-group evidence + geometry label + ambiguity (geometry FIRST) ----
    reports: list[GroupReport] = []
    final_label: dict = {}      # gid -> final label
    to_review: set = set()      # gids whose walls must be demoted (non-wall / fallback)
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
        L["wall"] = 2.0 * _wall_len(unclaimed, standards_mm, guard_mm, max_std, ortho_tol_deg)
        other = max(0.0, total - sum(L.values()))

        shares = {k: round(v / total, 2) for k, v in L.items()}
        shares["other"] = round(other / total, 2)
        short_frac = (sum(1 for s in gseg if _len(s) < 0.03 * sheet_min) / len(gseg)) if gseg else 0.0

        ranked = sorted(L.items(), key=lambda kv: kv[1], reverse=True)
        dom_kind, dom_len = ranked[0]
        no_dominant = dom_len <= other
        if no_dominant:
            geom_label = FURNITURE if short_frac > 0.5 else OTHER
            reason = f"geometry: no dominant evidence (other={shares['other']}, short={short_frac:.2f})"
        else:
            geom_label = {"wall": WALL, "grid": GRID, "stairs": STAIRS,
                          "hatch": HATCH, "annotation": ANNOTATION}[dom_kind]
            reason = f"geometry: dominant {dom_kind}={shares[dom_kind]}"

        strong = [k for k, v in shares.items() if k != "other" and v > 0.2]
        heterogeneous = len(strong) >= 2
        hetero_note = ""
        if heterogeneous:
            mix = ", ".join(f"{k}={shares[k]}" for k in strong)
            hetero_note = (f"group mixes sub-populations ({mix}); "
                           "v1 colour-primary separation cannot split them")

        # geometry confidence = margin of the top normalized share over the next
        ordered = sorted(shares.values(), reverse=True)
        top1 = ordered[0]
        margin = top1 - (ordered[1] if len(ordered) > 1 else 0.0)
        # A label from the "no dominant evidence" branch is a guess, not a confident
        # structural call -> treat as ambiguous so vision can adjudicate it.
        ambiguous = no_dominant or (top1 < amb_top1) or (margin < amb_margin) or heterogeneous

        label, source, vconf, vreason = geom_label, "geometry", None, ""
        if ambiguous and judge is not None:
            verdict = judge(gid)        # SEMANTIC only — returns a label, never geometry
            if verdict is not None:
                label, source = verdict.label, "vision"
                vconf, vreason = verdict.confidence, verdict.reason
                reason = f"vision: {verdict.label} ({verdict.confidence:.2f}) — {verdict.reason}"
            else:
                source = "fallback"
                reason = f"fallback to geometry ({geom_label}); routed to review"
                to_review.add(gid)
        elif ambiguous:
            source = "fallback"
            reason = f"ambiguous, no judge; geometry {geom_label}; routed to review"
            to_review.add(gid)

        final_label[gid] = label
        if label != WALL:
            to_review.add(gid)

        reports.append(GroupReport(
            group_id=gid, label=label, reason=reason, shares=shares,
            heterogeneous=heterogeneous, hetero_note=hetero_note,
            ink_fraction=g.get("ink_fraction", 0.0), geom_label=geom_label,
            source=source, ambiguous=ambiguous, confidence=round(margin, 2),
            vis_confidence=vconf, vis_reason=vreason,
        ))

    # ---- cross-group assembly on what remains (single wall emitter) ----
    remaining = [i for i in range(len(pool)) if i not in consumed]
    rem_segs = [pool[i] for i in remaining]
    rem_owner = [owner[i] for i in remaining]
    hatch_boxes = [r.bbox for r in hatch_regs]
    walls = assemble_walls(rem_segs, hatch_boxes, standards_mm, guard_mm,
                           ortho_tol_deg, sheet_min)

    # ---- route walls by their primary group's FINAL label (geometry never moves) ----
    for w in walls:
        pg = _attribute(w, rem_segs, rem_owner)
        if pg is not None and pg in to_review:
            w.flagged = True
            w.note = (w.note + f"; group {pg} = {final_label.get(pg)} -> review").strip("; ")
    assign_wall_layers(walls)  # flagged (thickness / unconfirmed / non-wall) -> review

    return Decomposition(
        walls=walls,
        group_reports=reports,
        region_counts={"grid": len(grid_regs), "stairs": len(stairs_regs), "hatch": len(hatch_regs)},
    )
