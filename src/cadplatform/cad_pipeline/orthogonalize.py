"""Tolerance-based orthogonalization (CLAUDE.md rule 1a).

Lines within +/- ``tol_deg`` of an axis are snapped to exact orthogonal.
Lines outside that band are PRESERVED unchanged — a genuinely angled wall
(intentional diagonal / splay) is never forced to 90 degrees.
"""

from __future__ import annotations

from .geometry import Segment


def orthogonalize_segment(seg: Segment, tol_deg: float) -> Segment:
    """Snap ``seg`` to horizontal/vertical if within tolerance, else return it."""
    if seg.is_horizontal(tol_deg):
        y = (seg.y1 + seg.y2) / 2.0
        return Segment(seg.x1, y, seg.x2, y)
    if seg.is_vertical(tol_deg):
        x = (seg.x1 + seg.x2) / 2.0
        return Segment(x, seg.y1, x, seg.y2)
    # Outside the band: preserve the measured angle.
    return seg


def orthogonalize(segments: list[Segment], tol_deg: float) -> list[Segment]:
    """Apply :func:`orthogonalize_segment` to every segment."""
    return [orthogonalize_segment(s, tol_deg) for s in segments]
