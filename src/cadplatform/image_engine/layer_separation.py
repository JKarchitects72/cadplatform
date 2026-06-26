"""STAGE A — Unsupervised layer separation (convention-independent).

Cluster ink strokes into coherent groups by the drawing's OWN discovered palette,
WITHOUT assigning meaning. Color is the primary grouping signal; stroke width and
a coarse dash signature are carried as opaque metadata (no meaning attached).

CRITICAL (CLAUDE.md / Milestone 2): this module never maps a specific colour to a
meaning. It only answers "which strokes look alike". Meaning is decided downstream
by geometry in ``cad_pipeline/decompose.py``. If you ever write ``if hue == X`` to
mean "wall", that is the anti-pattern — stop.

Output: a list of ``LayerGroup`` (binary mask + opaque metadata). The grayscale
Otsu collapse that destroyed per-drawing layer structure in T2.0 is NOT used here.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

# A pixel is "ink" when it is clearly not near-white background.
_INK_MIN_DELTA = 30


@dataclass
class LayerGroup:
    """One discovered group of similarly-styled strokes. No meaning assigned."""

    group_id: int
    mask: np.ndarray              # uint8, 255 = ink in this group
    color_bgr: tuple              # representative colour (for human-readable report ONLY)
    ink_fraction: float           # share of total ink in this group
    stroke_width_px: float        # opaque grouping metadata
    dash_kind: str                # "solid" | "broken" (coarse, opaque metadata)


def extract_ink_mask(bgr: np.ndarray) -> np.ndarray:
    """Foreground ink = pixels clearly darker/more saturated than white paper."""
    mn = bgr.min(axis=2).astype(np.int16)
    ink = (255 - mn) > _INK_MIN_DELTA
    return (ink.astype(np.uint8)) * 255


def _merge_centers(centers: np.ndarray, counts: np.ndarray, merge_de: float):
    """Greedily merge Lab centroids closer than ``merge_de`` (≈ ΔE76)."""
    centers = [c.astype(np.float64) for c in centers]
    counts = list(counts.astype(np.float64))
    changed = True
    while changed and len(centers) > 1:
        changed = False
        for i in range(len(centers)):
            for j in range(i + 1, len(centers)):
                if np.linalg.norm(centers[i] - centers[j]) < merge_de:
                    w = counts[i] + counts[j]
                    centers[i] = (centers[i] * counts[i] + centers[j] * counts[j]) / w
                    counts[i] = w
                    del centers[j]
                    del counts[j]
                    changed = True
                    break
            if changed:
                break
    return np.array(centers), np.array(counts)


def discover_palette(
    bgr: np.ndarray,
    ink: np.ndarray,
    max_k: int = 8,
    sample: int = 60000,
    merge_de: float = 15.0,
    min_frac: float = 0.004,
    seed: int = 0,
) -> np.ndarray:
    """Discover this drawing's stroke palette as Lab centroids (no meaning)."""
    ys, xs = np.where(ink > 0)
    if len(xs) == 0:
        return np.empty((0, 3), np.float32)

    rng = np.random.default_rng(seed)
    idx = rng.choice(len(xs), size=min(sample, len(xs)), replace=False)
    pts = bgr[ys[idx], xs[idx]].reshape(-1, 1, 3).astype(np.uint8)
    lab = cv2.cvtColor(pts, cv2.COLOR_BGR2LAB).reshape(-1, 3).astype(np.float32)

    k = int(min(max_k, max(1, np.unique(lab, axis=0).shape[0])))
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
    _, labels, centers = cv2.kmeans(lab, k, None, criteria, 3, cv2.KMEANS_PP_CENTERS)
    counts = np.bincount(labels.flatten(), minlength=k).astype(np.float64)

    centers, counts = _merge_centers(centers, counts, merge_de)
    frac = counts / counts.sum()
    keep = centers[frac >= min_frac]
    return keep.astype(np.float32)


def _assign_nearest(px_lab: np.ndarray, centroids: np.ndarray, chunk: int = 1_000_000) -> np.ndarray:
    """Nearest-centroid label for each pixel (chunked to bound memory)."""
    out = np.empty(len(px_lab), np.int32)
    for s in range(0, len(px_lab), chunk):
        block = px_lab[s : s + chunk][:, None, :]          # (n,1,3)
        d = ((block - centroids[None, :, :]) ** 2).sum(2)  # (n,k)
        out[s : s + chunk] = d.argmin(1)
    return out


def _stroke_width(mask: np.ndarray) -> float:
    dt = cv2.distanceTransform(mask, cv2.DIST_L2, 3)
    vals = dt[dt > 0]
    return float(2.0 * np.median(vals)) if vals.size else 0.0


def _dash_kind(mask: np.ndarray, stroke_w: float) -> str:
    """Coarse solid/broken signature from connected-component fragmentation."""
    n, _ = cv2.connectedComponents(mask, connectivity=8)
    ink_area = int((mask > 0).sum())
    if ink_area == 0 or stroke_w <= 0:
        return "solid"
    approx_len = ink_area / max(stroke_w, 1.0)
    frag = (n - 1) / max(approx_len, 1.0)   # components per unit length
    return "broken" if frag > 0.02 else "solid"


def separate_layers(bgr: np.ndarray, **palette_kwargs) -> list[LayerGroup]:
    """Separate a colour drawing into discovered layer-groups (Stage A)."""
    ink = extract_ink_mask(bgr)
    centroids = discover_palette(bgr, ink, **palette_kwargs)
    if len(centroids) == 0:
        return []

    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    ys, xs = np.where(ink > 0)
    px_lab = lab[ys, xs].astype(np.float32)
    assign = _assign_nearest(px_lab, centroids)

    groups: list[LayerGroup] = []
    total = len(xs)
    for gid in range(len(centroids)):
        sel = assign == gid
        if not sel.any():
            continue
        mask = np.zeros(ink.shape, np.uint8)
        mask[ys[sel], xs[sel]] = 255
        color_bgr = tuple(float(v) for v in bgr[ys[sel], xs[sel]].mean(axis=0))
        sw = _stroke_width(mask)
        groups.append(
            LayerGroup(
                group_id=gid,
                mask=mask,
                color_bgr=color_bgr,
                ink_fraction=float(sel.sum()) / total,
                stroke_width_px=sw,
                dash_kind=_dash_kind(mask, sw),
            )
        )
    # Stable order: largest groups first (purely cosmetic for the report).
    groups.sort(key=lambda g: g.ink_fraction, reverse=True)
    return groups
