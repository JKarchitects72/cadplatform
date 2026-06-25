"""Layer assignment (CLAUDE.md rule 2).

The pipeline assigns AIA layer *names* to geometry. Appearance (color,
lineweight, linetype) is NOT set here — it is fixed per layer in
``dxf_layer/layer_defs.py`` and applied at serialization time as BYLAYER.
"""

from __future__ import annotations

from .geometry import Wall

# First-slice scope: all detected walls are "new walls".
WALL_LAYER = "A-WALL-NEWW"


def assign_wall_layer(walls: list[Wall], layer: str = WALL_LAYER) -> list[Wall]:
    """Stamp ``layer`` onto every wall and return the list."""
    for w in walls:
        w.layer = layer
    return walls
