"""Shared test fixtures."""

from __future__ import annotations

import os
import sys

import pytest

# Make scripts/ importable for the synthetic-plan generator.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "scripts"))

# Scale used by the synthetic sample: 10 mm per pixel.
SAMPLE_SCALE_MM_PER_PX = 10.0


@pytest.fixture
def sample_plan_png(tmp_path):
    """Write the synthetic floor-plan PNG into a temp dir and return its path."""
    import make_sample_plan

    out = tmp_path / "floorplan.png"
    img = make_sample_plan.make_plan()
    import cv2

    cv2.imwrite(str(out), img)
    return str(out)


@pytest.fixture
def generated_dxf(sample_plan_png, tmp_path):
    """Run the convert slice on the sample and return (dxf_path, summary)."""
    from cadplatform.cli import convert

    out = tmp_path / "floorplan.dxf"
    summary = convert(sample_plan_png, str(out), SAMPLE_SCALE_MM_PER_PX)
    return str(out), summary
