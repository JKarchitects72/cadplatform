"""Step 4 validation: the generated DXF is structurally correct, with real
wall thickness and flagged outliers routed to the non-plotting review layer.

Confirms:
  - A-WALL-NEWW and A-WALL-REVIEW exist with correct ACI color/lineweight,
  - walls are LINE entities (two faces each) on those layers,
  - standard walls have non-zero thickness matching a standard value,
  - the deliberate outlier is flagged onto A-WALL-REVIEW (non-plotting),
  - doc.audit() reports no errors and there are no stray entities.
"""

from __future__ import annotations

import ezdxf

from cadplatform.config import standard_wall_thicknesses_mm
from cadplatform.dxf_layer.layer_defs import LAYERS
from cadplatform.dxf_layer.validate import validate

WALL_LAYER = "A-WALL-NEWW"
REVIEW_LAYER = "A-WALL-REVIEW"
WALL_ENTITY_TYPES = {"LINE", "LWPOLYLINE"}


def test_layers_exist_with_correct_properties(generated_dxf):
    dxf_path, _ = generated_dxf
    doc = ezdxf.readfile(dxf_path)
    for name in (WALL_LAYER, REVIEW_LAYER):
        assert name in doc.layers
        layer = doc.layers.get(name)
        expected = LAYERS[name]
        assert layer.color == expected.color
        assert layer.dxf.lineweight == expected.lineweight


def test_review_layer_is_non_plotting(generated_dxf):
    dxf_path, _ = generated_dxf
    doc = ezdxf.readfile(dxf_path)
    assert doc.layers.get(REVIEW_LAYER).dxf.plot == 0


def test_walls_are_lines_on_expected_layers(generated_dxf):
    dxf_path, _ = generated_dxf
    doc = ezdxf.readfile(dxf_path)
    entities = list(doc.modelspace())
    assert entities
    for e in entities:
        assert e.dxftype() in WALL_ENTITY_TYPES
        assert e.dxf.layer in {WALL_LAYER, REVIEW_LAYER}


def test_wall_and_face_counts(generated_dxf):
    # 5 standard walls + 1 flagged outlier; each wall serialized as 2 faces.
    _, summary = generated_dxf
    assert summary["walls"] == 6
    assert summary["standard_walls"] == 5
    assert summary["flagged_walls"] == 1

    dxf_path = summary["output"]
    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()
    assert len(list(msp.query(f"LINE[layer=='{WALL_LAYER}']"))) == 10
    assert len(list(msp.query(f"LINE[layer=='{REVIEW_LAYER}']"))) == 2


def test_standard_walls_have_nonzero_standard_thickness(generated_dxf):
    _, summary = generated_dxf
    standards = standard_wall_thicknesses_mm()
    for w in summary["wall_objects"]:
        if w.flagged:
            continue
        assert w.thickness_mm in standards
        assert w.thickness_mm > 0


def test_outlier_is_flagged_with_raw_thickness(generated_dxf):
    _, summary = generated_dxf
    flagged = [w for w in summary["wall_objects"] if w.flagged]
    assert len(flagged) == 1
    w = flagged[0]
    assert w.layer == REVIEW_LAYER
    # Raw thickness retained, not force-snapped to a standard.
    assert w.thickness_mm == w.raw_thickness_mm
    assert w.thickness_mm not in standard_wall_thicknesses_mm()


def test_validator_passes_with_thickness_check(generated_dxf):
    dxf_path, _ = generated_dxf
    result = validate(
        dxf_path,
        required_layers={
            WALL_LAYER: LAYERS[WALL_LAYER],
            REVIEW_LAYER: LAYERS[REVIEW_LAYER],
        },
        check_thickness=True,
        standards_mm=standard_wall_thicknesses_mm(),
    )
    assert result.ok, result.summary()
    assert len(result.flagged) == 1  # the one outlier reported


def test_audit_reports_no_errors(generated_dxf):
    dxf_path, _ = generated_dxf
    doc = ezdxf.readfile(dxf_path)
    auditor = doc.audit()
    assert len(auditor.errors) == 0
