"""Project-wide configuration resolved from environment variables.

All tunable defaults the pipeline depends on live here so they can be overridden
without code changes (see CLAUDE.md). Per CLAUDE.md, the vision model defaults to
``claude-sonnet-4-6`` and MUST be overridable via ``CADPLATFORM_VISION_MODEL``
(e.g. escalate to ``claude-opus-4-8`` for difficult scans).
"""

from __future__ import annotations

import os

# --- Vision -----------------------------------------------------------------

# Default vision model. Override with CADPLATFORM_VISION_MODEL.
DEFAULT_VISION_MODEL = "claude-sonnet-4-6"


def vision_model() -> str:
    """Return the configured Claude vision model string."""
    value = os.environ.get("CADPLATFORM_VISION_MODEL", DEFAULT_VISION_MODEL).strip()
    return value or DEFAULT_VISION_MODEL


# --- Wall thickness standardization (CLAUDE.md rule 4) ----------------------

# Configurable standard set of wall thicknesses in millimeters. Detected
# thicknesses snap to the NEAREST value here; raw pixel-derived values are
# never written. Override with CADPLATFORM_WALL_THICKNESSES (comma-separated mm).
DEFAULT_WALL_THICKNESSES_MM = (90.0, 100.0, 120.0, 150.0, 200.0, 250.0, 300.0)

# Max-snap-distance guard in millimeters. If a detected thickness is farther
# than this from every standard value, it is FLAGGED rather than force-snapped.
# Override with CADPLATFORM_WALL_SNAP_GUARD_MM.
DEFAULT_WALL_THICKNESS_SNAP_GUARD_MM = 40.0


def standard_wall_thicknesses_mm() -> tuple[float, ...]:
    """Return the configured standard wall-thickness set (sorted, mm)."""
    raw = os.environ.get("CADPLATFORM_WALL_THICKNESSES", "").strip()
    if not raw:
        return DEFAULT_WALL_THICKNESSES_MM
    values = tuple(sorted(float(part) for part in raw.split(",") if part.strip()))
    return values or DEFAULT_WALL_THICKNESSES_MM


def wall_thickness_snap_guard_mm() -> float:
    """Return the max-snap-distance guard in millimeters."""
    raw = os.environ.get("CADPLATFORM_WALL_SNAP_GUARD_MM", "").strip()
    if not raw:
        return DEFAULT_WALL_THICKNESS_SNAP_GUARD_MM
    return float(raw)


# --- Orthogonalization (CLAUDE.md rule 1a) ----------------------------------

# Tolerance band for 90°/axis snapping, in degrees. Lines within +/- this of an
# axis snap to exact orthogonal; lines outside the band are preserved as-is.
# Override with CADPLATFORM_ORTHO_TOLERANCE_DEG.
DEFAULT_ORTHO_TOLERANCE_DEG = 3.0


def ortho_tolerance_deg() -> float:
    """Return the orthogonalization tolerance band in degrees."""
    raw = os.environ.get("CADPLATFORM_ORTHO_TOLERANCE_DEG", "").strip()
    if not raw:
        return DEFAULT_ORTHO_TOLERANCE_DEG
    return float(raw)


# --- Vision adjudication (T2.3) ---------------------------------------------

# A group is "ambiguous" (and may be sent to the vision judge) when its dominant
# evidence share is below TOP1, or its margin over the runner-up is below MARGIN,
# or it is flagged heterogeneous. Confident groups never call vision.
DEFAULT_VISION_AMBIGUITY_TOP1 = 0.55
DEFAULT_VISION_AMBIGUITY_MARGIN = 0.20


def vision_ambiguity_top1() -> float:
    raw = os.environ.get("CADPLATFORM_VISION_AMBIGUITY_TOP1", "").strip()
    return float(raw) if raw else DEFAULT_VISION_AMBIGUITY_TOP1


def vision_ambiguity_margin() -> float:
    raw = os.environ.get("CADPLATFORM_VISION_AMBIGUITY_MARGIN", "").strip()
    return float(raw) if raw else DEFAULT_VISION_AMBIGUITY_MARGIN


def vision_cache_dir() -> str:
    return os.environ.get("CADPLATFORM_VISION_CACHE_DIR", "output/.vision_cache").strip() \
        or "output/.vision_cache"


# --- DXF output -------------------------------------------------------------

# DXF is authored in millimeters ($INSUNITS = 4).
INSUNITS_MILLIMETERS = 4

# Target DXF version is pinned to R2018 (AC1032).
DXF_VERSION = "AC1032"
