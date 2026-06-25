"""Project-wide configuration resolved from environment variables.

Per CLAUDE.md: the vision model defaults to ``claude-sonnet-4-6`` and MUST be
overridable via the ``CADPLATFORM_VISION_MODEL`` env var (e.g. escalate to
``claude-opus-4-8`` for difficult scans).
"""

from __future__ import annotations

import os

# Default vision model. Override with CADPLATFORM_VISION_MODEL.
DEFAULT_VISION_MODEL = "claude-sonnet-4-6"

# Standard wall thicknesses in millimeters (CLAUDE.md rule 4).
STANDARD_WALL_THICKNESSES_MM = (100.0, 150.0, 200.0)

# DXF is authored in millimeters ($INSUNITS = 4).
INSUNITS_MILLIMETERS = 4


def vision_model() -> str:
    """Return the configured Claude vision model string."""
    return os.environ.get("CADPLATFORM_VISION_MODEL", DEFAULT_VISION_MODEL).strip() or DEFAULT_VISION_MODEL
