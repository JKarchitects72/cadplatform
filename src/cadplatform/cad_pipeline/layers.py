"""Layer assignment (CLAUDE.md rule 2).

Assigns AIA layer *names* to geometry. Appearance (color, lineweight, linetype,
plot flag) is NOT set here — it is fixed per layer in ``dxf_layer/layer_defs.py``
and applied at serialization time as BYLAYER.
"""

from __future__ import annotations

from .geometry import Wall

# Standard new walls, and the non-plotting review layer for thickness outliers.
WALL_LAYER = "A-WALL-NEWW"
WALL_REVIEW_LAYER = "A-WALL-REVIEW"


def assign_wall_layers(
    walls: list[Wall],
    wall_layer: str = WALL_LAYER,
    review_layer: str = WALL_REVIEW_LAYER,
) -> list[Wall]:
    """Route flagged outliers to the review layer; standard walls to the wall layer."""
    for w in walls:
        w.layer = review_layer if w.flagged else wall_layer
    return walls
