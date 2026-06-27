"""Vision adjudication tests — Rule 5 guarantee + SYNTH zero-call (offline)."""

from __future__ import annotations

import dataclasses

from cadplatform.image_engine.vision_judge import LABELS, VisionVerdict, _parse


def test_verdict_has_no_geometry_fields():
    # Rule 5 / constraint 1: the verdict carries ONLY semantic fields.
    fields = {f.name for f in dataclasses.fields(VisionVerdict)}
    assert fields == {"label", "confidence", "reason"}


def test_parse_valid_json():
    v = _parse('{"label":"STAIRS","confidence":0.9,"reason":"tread run"}')
    assert v.label == "STAIRS" and 0 <= v.confidence <= 1


def test_parse_coerces_unknown_label_to_other():
    v = _parse('{"label":"WINDOW","confidence":2.0,"reason":"x"}')
    assert v.label == "OTHER"
    assert v.confidence == 1.0  # clamped
    assert v.label in LABELS


def test_synth_makes_zero_vision_calls(sample_plan_png, tmp_path):
    # The clean synthetic plan has no ambiguous group -> the judge is never called,
    # so no API request is made and the run stays fully offline/deterministic.
    from cadplatform.cli import convert

    out = tmp_path / "synth.dxf"
    summary = convert(sample_plan_png, str(out), 10.0)
    assert summary["vision"]["calls"] == 0
