"""ezdxf serialization (CLAUDE.md rules 1, 2, 3).

Turns corrected geometry from ``cad_pipeline`` into a DXF document. This is the
only place ezdxf is used. Entities are created with appearance BYLAYER — no
per-entity color/lineweight/linetype is ever set.
"""

from __future__ import annotations

import ezdxf

from ..cad_pipeline.geometry import Wall
from ..config import DXF_VERSION, INSUNITS_MILLIMETERS
from .layer_defs import LAYERS, LayerDef


def _ensure_layers(doc, layer_defs: dict[str, LayerDef]) -> None:
    """Create each layer with its fixed color and lineweight."""
    for name, ld in layer_defs.items():
        if name in doc.layers:
            continue
        doc.layers.add(name=name, color=ld.color, lineweight=ld.lineweight)


def build_doc(walls: list[Wall]):
    """Build an ezdxf document containing the given walls as LINE entities."""
    doc = ezdxf.new(dxfversion=DXF_VERSION, setup=True)
    doc.header["$INSUNITS"] = INSUNITS_MILLIMETERS

    # Define every AIA layer up front so the file is self-describing.
    _ensure_layers(doc, LAYERS)

    msp = doc.modelspace()
    for wall in walls:
        c = wall.centerline
        layer = wall.layer or "A-WALL-NEWW"
        # Appearance is BYLAYER: pass only the layer, never color/lineweight.
        msp.add_line((c.x1, c.y1), (c.x2, c.y2), dxfattribs={"layer": layer})

    return doc


def write_dxf(doc, path: str) -> str:
    """Save ``doc`` to ``path`` and return the path."""
    doc.saveas(path)
    return path
