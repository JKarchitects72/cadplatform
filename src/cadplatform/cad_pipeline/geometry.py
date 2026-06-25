"""Shared geometry primitives for the CAD pipeline.

Pure geometry only (CLAUDE.md rule 1): no file I/O, no vision, no ezdxf.
All coordinates are in millimeters by the time they reach this subsystem.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Segment:
    """A straight line segment in millimeter space."""

    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def length(self) -> float:
        return math.hypot(self.x2 - self.x1, self.y2 - self.y1)

    @property
    def angle_deg(self) -> float:
        """Orientation in [0, 180): direction-agnostic angle from the x-axis."""
        ang = math.degrees(math.atan2(self.y2 - self.y1, self.x2 - self.x1)) % 180.0
        return ang

    def is_horizontal(self, tol_deg: float) -> bool:
        a = self.angle_deg
        return a <= tol_deg or a >= 180.0 - tol_deg

    def is_vertical(self, tol_deg: float) -> bool:
        return abs(self.angle_deg - 90.0) <= tol_deg


@dataclass
class Wall:
    """A wall centerline plus pipeline metadata."""

    centerline: Segment
    layer: str = ""
    # Nominal standardized thickness in mm (None until measured; thickness
    # measurement from the raster is a DEFERRED stage, see CLAUDE.md rule 4).
    thickness_mm: float | None = None
    flagged: bool = False
    note: str = ""
