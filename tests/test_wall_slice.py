"""Step 4 validation: the generated DXF is structurally correct.

Confirms:
  - A-WALL-NEWW exists with the correct ACI color and lineweight,
  - walls are LINE/LWPOLYLINE entities on that layer,
  - doc.audit() reports no errors,
  - no stray entities on unexpected layers.
"""

from __future__ import annotations

import ezdxf

from cadplatform.dxf_layer.layer_defs import LAYERS
from cadplatform.dxf_layer.validate import validate

WALL_LAYER = "A-WALL-NEWW"
WALL_ENTITY_TYPES = {"LINE", "LWPOLYLINE"}


def test_layer_exists_with_correct_properties(generated_dxf):
    dxf_path, _ = generated_dxf
    doc = ezdxf.readfile(dxf_path)

    assert WALL_LAYER in doc.layers
    layer = doc.layers.get(WALL_LAYER)
    expected = LAYERS[WALL_LAYER]
    assert layer.color == expected.color
    assert layer.dxf.lineweight == expected.lineweight


def test_walls_are_lines_on_the_wall_layer(generated_dxf):
    dxf_path, _ = generated_dxf
    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()

    entities = list(msp)
    assert entities, "expected at least one wall entity"
    for e in entities:
        assert e.dxftype() in WALL_ENTITY_TYPES
        assert e.dxf.layer == WALL_LAYER


def test_audit_reports_no_errors(generated_dxf):
    dxf_path, _ = generated_dxf
    doc = ezdxf.readfile(dxf_path)
    auditor = doc.audit()
    assert len(auditor.errors) == 0


def test_validator_passes(generated_dxf):
    dxf_path, _ = generated_dxf
    result = validate(dxf_path, required_layers={WALL_LAYER: LAYERS[WALL_LAYER]})
    assert result.ok, result.summary()


def test_detects_expected_wall_count(generated_dxf):
    # Outer rectangle (4 sides) + 2 interior walls = 6 merged centerlines.
    _, summary = generated_dxf
    assert summary["walls"] == 6
