"""AIA layer definitions — the single source of truth for layer appearance.

Per CLAUDE.md rule 2: every layer has a FIXED ACI color and FIXED lineweight,
defined ONCE here. Entities never override appearance (color/lineweight/linetype
are always BYLAYER).

Lineweights use ezdxf's integer encoding: hundredths of a millimeter, drawn from
the fixed enumerated set of valid DXF lineweights (e.g. 50 == 0.50 mm).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LayerDef:
    """Fixed appearance for one AIA layer."""

    name: str
    color: int          # ACI color index
    lineweight: int     # 1/100 mm, from the valid DXF lineweight set
    description: str = ""


# AIA Discipline-Major-Minor layers. Add new layers here only.
LAYERS: dict[str, LayerDef] = {
    "A-WALL-NEWW": LayerDef("A-WALL-NEWW", color=7, lineweight=50, description="New walls"),
    "A-WALL-EXTR": LayerDef("A-WALL-EXTR", color=5, lineweight=70, description="Exterior walls"),
    "A-DOOR": LayerDef("A-DOOR", color=3, lineweight=35, description="Doors"),
    "A-FLOR-OVHD": LayerDef("A-FLOR-OVHD", color=8, lineweight=18, description="Overhead / hidden"),
    "I-FURN": LayerDef("I-FURN", color=4, lineweight=25, description="Furniture"),
}


def get(name: str) -> LayerDef:
    """Return the LayerDef for ``name`` or raise KeyError if unknown."""
    return LAYERS[name]
