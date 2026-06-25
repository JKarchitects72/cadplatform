"""ezdxf serialization (CLAUDE.md rules 1, 2, 3).

Turns corrected geometry from ``cad_pipeline`` into a DXF document. This is the
only place ezdxf is used. Entities are created with appearance BYLAYER — no
per-entity color/lineweight/linetype is ever set.

A wall is serialized as TWO parallel face LINEs offset +/- thickness/2 from its
centerline (never a zero-width centerline). Standard walls carry the snapped
thickness; flagged outliers carry their raw thickness on the review layer.
"""

from __future__ import annotations

import math

import ezdxf

from ..cad_pipeline.geometry import Wall
from ..config import DXF_VERSION, INSUNITS_MILLIMETERS
from .layer_defs import LAYERS, LayerDef


def _ensure_layers(doc, layer_defs: dict[str, LayerDef]) -> None:
    """Create each layer with its fixed color, lineweight, and plot flag."""
    for name, ld in layer_defs.items():
        if name in doc.layers:
            layer = doc.layers.get(name)
        else:
            layer = doc.layers.add(name=name, color=ld.color, lineweight=ld.lineweight)
        layer.dxf.plot = 1 if ld.plot else 0


def _face_lines(wall: Wall):
    """Return the two ((x1,y1),(x2,y2)) face polylines for a wall."""
    c = wall.centerline
    t = wall.thickness_mm if wall.thickness_mm is not None else 0.0
    dx, dy = c.x2 - c.x1, c.y2 - c.y1
    length = math.hypot(dx, dy)
    if length == 0:
        return []
    # Unit normal to the centerline.
    nx, ny = -dy / length, dx / length
    h = t / 2.0
    face_a = ((c.x1 + nx * h, c.y1 + ny * h), (c.x2 + nx * h, c.y2 + ny * h))
    face_b = ((c.x1 - nx * h, c.y1 - ny * h), (c.x2 - nx * h, c.y2 - ny * h))
    return [face_a, face_b]


def build_doc(walls: list[Wall]):
    """Build an ezdxf document with each wall as two parallel face LINEs."""
    doc = ezdxf.new(dxfversion=DXF_VERSION, setup=True)
    doc.header["$INSUNITS"] = INSUNITS_MILLIMETERS

    _ensure_layers(doc, LAYERS)

    msp = doc.modelspace()
    for wall in walls:
        layer = wall.layer or "A-WALL-NEWW"
        for (p1, p2) in _face_lines(wall):
            # Appearance is BYLAYER: pass only the layer.
            msp.add_line(p1, p2, dxfattribs={"layer": layer})

    return doc


def write_dxf(doc, path: str) -> str:
    """Save ``doc`` to ``path`` and return the path."""
    doc.saveas(path)
    return path
