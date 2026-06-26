"""STAGE B regions — structural detectors that CLAIM non-wall geometry.

Pure geometry. Each detector is bound to ONE defining structural feature (Gate 1):
  GRID   : lines spanning ~the whole sheet, UNPAIRED, crossing much other geometry.
  STAIRS : a LOCAL cluster of UNPAIRED parallel segments at near-constant pitch.
  HATCH  : a bounded region of dense, consistent-angle, regularly-spaced shorts.

"Unpaired" (no parallel partner within the wall thickness band) is the disambiguator
that keeps real walls — whose two faces ARE paired — out of grid/stairs.

Detectors run BEFORE cross-group wall assembly and CONSUME their members from the
pool, so phantom sources can never masquerade as wall faces. Colour is never an
input here.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .geometry import Segment


@dataclass
class Region:
    kind: str                       # "grid" | "stairs" | "hatch"
    members: list[int]              # indices into the pool
    bbox: tuple                     # (xlo, ylo, xhi, yhi) in mm
    axis: str | None = None         # 'H'/'V' for grid/stairs
    detail: dict = field(default_factory=dict)


def _angle(s: Segment) -> float:
    return math.degrees(math.atan2(s.y2 - s.y1, s.x2 - s.x1)) % 180.0


def _len(s: Segment) -> float:
    return math.hypot(s.x2 - s.x1, s.y2 - s.y1)


def _orient(s: Segment, tol: float = 5.0) -> str | None:
    a = _angle(s)
    if a <= tol or a >= 180 - tol:
        return "H"
    if abs(a - 90) <= tol:
        return "V"
    return None


def _pos(s: Segment, o: str) -> float:
    return (s.y1 + s.y2) / 2 if o == "H" else (s.x1 + s.x2) / 2


def _span(s: Segment, o: str) -> tuple:
    return (min(s.x1, s.x2), max(s.x1, s.x2)) if o == "H" else (min(s.y1, s.y2), max(s.y1, s.y2))


def _overlap(a: tuple, b: tuple) -> float:
    return min(a[1], b[1]) - max(a[0], b[0])


def _bbox(segs: list[Segment]) -> tuple:
    xs = [c for s in segs for c in (s.x1, s.x2)]
    ys = [c for s in segs for c in (s.y1, s.y2)]
    return (min(xs), min(ys), max(xs), max(ys))


def _has_partner(i, idxs, segs, orients, band_lo, band_hi) -> bool:
    """True if segment i has a parallel partner within the wall thickness band."""
    o = orients[i]
    if o is None:
        return False
    pi, spi = _pos(segs[i], o), _span(segs[i], o)
    span_i = spi[1] - spi[0]
    for j in idxs:
        if j == i or orients[j] != o:
            continue
        d = abs(_pos(segs[j], o) - pi)
        if band_lo <= d <= band_hi:
            spj = _span(segs[j], o)
            if _overlap(spi, spj) > 0.3 * min(span_i, spj[1] - spj[0] + 1e-9):
                return True
    return False


def detect_grid(segs, sheet_w, sheet_h, band_lo, band_hi, sheet_min=None,
                span_frac=0.7, min_cross=4) -> tuple[list[Region], set]:
    """GRID: a line that spans ~the whole sheet, is UNPAIRED, and crosses much else.

    Collinear fragments are bucketed by position first, so a DASHED grid line
    (which Hough returns as many short collinear segments) is reconstructed before
    its span is measured. "Unpaired + spanning + crossing" is the bound feature.
    """
    if sheet_min is None:
        sheet_min = min(sheet_w, sheet_h)
    axis_tol = 0.003 * sheet_min
    orients = [_orient(s) for s in segs]
    consumed, regions = set(), []

    for o in ("H", "V"):
        axis_len = sheet_w if o == "H" else sheet_h
        idx = [i for i in range(len(segs)) if orients[i] == o]
        # bucket collinear fragments (same position within axis_tol)
        buckets = []
        for i in sorted(idx, key=lambda i: _pos(segs[i], o)):
            p, sp = _pos(segs[i], o), _span(segs[i], o)
            for bk in buckets:
                if abs(bk["pos"] - p) <= axis_tol:
                    bk["idx"].append(i)
                    bk["lo"] = min(bk["lo"], sp[0]); bk["hi"] = max(bk["hi"], sp[1])
                    bk["pos"] = (bk["pos"] * (len(bk["idx"]) - 1) + p) / len(bk["idx"])
                    break
            else:
                buckets.append({"pos": p, "idx": [i], "lo": sp[0], "hi": sp[1]})

        positions = [bk["pos"] for bk in buckets]
        for bk in buckets:
            if (bk["hi"] - bk["lo"]) < span_frac * axis_len:
                continue
            # unpaired: no parallel reconstructed line within the wall band
            if any(band_lo <= abs(bk["pos"] - q) <= band_hi for q in positions if q != bk["pos"]):
                continue
            # crossings: perpendicular segments passing through within the span
            crosses = 0
            for j in range(len(segs)):
                if orients[j] == o:
                    continue
                cs = _span(segs[j], "V") if o == "H" else _span(segs[j], "H")
                mid = (segs[j].x1 + segs[j].x2) / 2 if o == "H" else (segs[j].y1 + segs[j].y2) / 2
                if cs[0] <= bk["pos"] <= cs[1] and bk["lo"] <= mid <= bk["hi"]:
                    crosses += 1
                    if crosses >= min_cross:
                        break
            if crosses >= min_cross:
                for i in bk["idx"]:
                    consumed.add(i)
                regions.append(Region("grid", bk["idx"],
                                      _bbox([segs[i] for i in bk["idx"]]), o,
                                      {"crosses": crosses, "span": round(bk["hi"] - bk["lo"])}))
    return regions, consumed


def _longest_constant_run(pos: list[float], cv: float) -> tuple[int, int] | None:
    """Longest run [i..j] of positions whose consecutive gaps are ~constant."""
    gaps = [pos[k + 1] - pos[k] for k in range(len(pos) - 1)]
    if not gaps:
        return None
    best = None
    i = 0
    while i < len(gaps):
        j = i
        while j + 1 < len(gaps):
            window = gaps[i:j + 2]
            m = sum(window) / len(window)
            if m > 0 and max(abs(g - m) for g in window) / m <= cv:
                j += 1
            else:
                break
        if best is None or (j + 1 - i) > (best[1] - best[0]):
            best = (i, j + 1)
        i = j + 1
    return best


def detect_stairs(segs, band_lo, band_hi, sheet_min, min_run=4, pitch_cv=0.2,
                  min_len_frac=0.02) -> tuple[list[Region], set]:
    """STAIRS: a LOCAL cluster of parallel segments forming a CONSTANT-PITCH RUN of
    >= min_run. A wall has exactly two faces and can never form such a run — that
    count-and-pitch signature is the right-reason discriminator. Treads must be real
    lines (>= min_len_frac of the sheet), which excludes hatch and dimension ticks.
    """
    orients = [_orient(s) for s in segs]
    min_len = min_len_frac * sheet_min
    axis_idx = [i for i, o in enumerate(orients) if o and _len(segs[i]) >= min_len]
    consumed, regions = set(), []
    for o in ("H", "V"):
        idx = [i for i in axis_idx if orients[i] == o]
        idx.sort(key=lambda i: _pos(segs[i], o))
        for a in range(len(idx)):
            if idx[a] in consumed:
                continue
            sp0 = _span(segs[idx[a]], o)
            cluster = [idx[a]]
            for b in range(len(idx)):
                if b == a or idx[b] in consumed:
                    continue
                spb = _span(segs[idx[b]], o)
                if _overlap(sp0, spb) > 0.5 * min(sp0[1] - sp0[0], spb[1] - spb[0] + 1e-9):
                    cluster.append(idx[b])
            cluster = sorted(set(cluster), key=lambda i: _pos(segs[i], o))
            if len(cluster) < min_run:
                continue
            pos = [_pos(segs[i], o) for i in cluster]
            run = _longest_constant_run(pos, pitch_cv)
            if run and (run[1] - run[0] + 1) >= min_run:
                members = cluster[run[0]:run[1] + 1]
                pitch = (pos[run[1]] - pos[run[0]]) / (run[1] - run[0])
                for i in members:
                    consumed.add(i)
                regions.append(Region("stairs", members, _bbox([segs[i] for i in members]), o,
                                      {"treads": len(members), "pitch_mm": round(pitch)}))
    return regions, consumed


def detect_hatch(segs, sheet_min, short_frac=0.05, min_count=12,
                 angle_spread=12.0) -> tuple[list[Region], set]:
    """HATCH: dense, consistent-angle, regularly-spaced SHORT parallels in a region.

    Candidates must be DIAGONAL (not axis-aligned). This is the right-reason
    discriminator that keeps axis-aligned WALL FACES out of hatch — poché hatch is
    a diagonal fill; wall faces run along the building axes. (Axis-aligned hatch is
    a deferred case.)
    """
    short_idx = [i for i, s in enumerate(segs)
                 if _len(s) < short_frac * sheet_min and _orient(s) is None]
    consumed, regions = set(), []
    used = set()
    for a in short_idx:
        if a in used:
            continue
        a0 = _angle(segs[a])
        # gather short segments of nearly the same angle in a compact neighbourhood
        cx = (segs[a].x1 + segs[a].x2) / 2
        cy = (segs[a].y1 + segs[a].y2) / 2
        reach = 0.08 * sheet_min
        cluster = []
        for b in short_idx:
            if b in used:
                continue
            da = abs(_angle(segs[b]) - a0)
            da = min(da, 180 - da)
            if da > angle_spread:
                continue
            bx = (segs[b].x1 + segs[b].x2) / 2
            by = (segs[b].y1 + segs[b].y2) / 2
            if abs(bx - cx) <= reach and abs(by - cy) <= reach:
                cluster.append(b)
        if len(cluster) >= min_count:
            for b in cluster:
                used.add(b); consumed.add(b)
            regions.append(Region("hatch", cluster, _bbox([segs[i] for i in cluster]), None,
                                  {"lines": len(cluster), "angle": round(a0)}))
    return regions, consumed
