"""The single DXF validator (CLAUDE.md rule 7).

Opens a produced DXF and asserts structural correctness:
  - ``doc.audit()`` reports ZERO errors,
  - every required layer exists with the correct ACI color and lineweight,
  - there are no stray entities (everything sits on an expected layer).

This is the ONE validator implementation. ``scripts/validate_dxf.py`` is a thin
CLI wrapper around :func:`validate` / :func:`main` — never a second copy.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field

import ezdxf

from ..cad_pipeline.geometry import Segment
from ..cad_pipeline.walls import pair_parallel_edges
from .layer_defs import LAYERS, LayerDef

# Layers ezdxf always creates; entities may legitimately sit on "0".
_BUILTIN_LAYERS = {"0", "Defpoints"}


@dataclass
class ValidationResult:
    """Outcome of validating a DXF file."""

    path: str
    audit_errors: int = 0
    problems: list[str] = field(default_factory=list)
    # Measured thicknesses (mm) of walls reconstructed from the review layer.
    flagged: list[float] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.audit_errors == 0 and not self.problems

    def summary(self) -> str:
        status = "PASS" if self.ok else "FAIL"
        lines = [f"[{status}] {self.path}", f"  audit errors: {self.audit_errors}"]
        if self.flagged:
            flagged = ", ".join(f"{t:.0f}mm" for t in self.flagged)
            lines.append(f"  review (A-WALL-REVIEW): {len(self.flagged)} outlier(s): {flagged}")
        for p in self.problems:
            lines.append(f"  - {p}")
        return "\n".join(lines)


def _measure_layer_thicknesses(msp, layer: str) -> list[float]:
    """Reconstruct wall thicknesses on ``layer`` by re-pairing its face LINEs."""
    segs = [
        Segment(float(e.dxf.start.x), float(e.dxf.start.y),
                float(e.dxf.end.x), float(e.dxf.end.y))
        for e in msp.query(f"LINE[layer=='{layer}']")
    ]
    walls = pair_parallel_edges(
        segs, min_thickness_mm=1.0, max_thickness_mm=10_000.0, overlap_frac=0.3
    )
    return [w.raw_thickness_mm for w in walls if w.raw_thickness_mm is not None]


def validate(
    path: str,
    required_layers: dict[str, LayerDef] | None = None,
    allowed_layers: set[str] | None = None,
    check_thickness: bool = False,
    standards_mm: tuple[float, ...] | None = None,
    thickness_tol_mm: float = 1.0,
    wall_layer: str = "A-WALL-NEWW",
    review_layer: str = "A-WALL-REVIEW",
) -> ValidationResult:
    """Validate the DXF at ``path``.

    ``required_layers`` must exist with exactly the defined color/lineweight
    (defaults to the full AIA table). ``allowed_layers`` bounds where entities
    may live (defaults to the required layers plus the DXF built-ins); any entity
    on another layer is reported as a stray.

    When ``check_thickness`` is set (Rule 4/6), wall thicknesses are reconstructed
    from the face LINEs and asserted: every wall on ``wall_layer`` must have a
    non-zero thickness matching a standard value (within ``thickness_tol_mm``);
    any outlier must instead live on the non-plotting ``review_layer`` and is
    reported in ``result.flagged``.
    """
    if required_layers is None:
        required_layers = LAYERS
    if allowed_layers is None:
        allowed_layers = set(required_layers) | _BUILTIN_LAYERS

    result = ValidationResult(path=path)

    doc = ezdxf.readfile(path)

    # 1. Audit must be clean.
    auditor = doc.audit()
    result.audit_errors = len(auditor.errors)
    for err in auditor.errors:
        result.problems.append(f"audit: {err}")

    # 2. Required layers exist with correct appearance.
    for name, ld in required_layers.items():
        if name not in doc.layers:
            result.problems.append(f"missing required layer: {name}")
            continue
        layer = doc.layers.get(name)
        if layer.color != ld.color:
            result.problems.append(
                f"layer {name}: color {layer.color} != expected {ld.color}"
            )
        if layer.dxf.lineweight != ld.lineweight:
            result.problems.append(
                f"layer {name}: lineweight {layer.dxf.lineweight} != expected {ld.lineweight}"
            )

    # 3. No stray entities (everything on an allowed layer).
    msp = doc.modelspace()
    for entity in msp:
        layer = entity.dxf.layer
        if layer not in allowed_layers:
            result.problems.append(
                f"stray entity {entity.dxftype()} on unexpected layer {layer!r}"
            )

    # 4. Wall thickness (Rule 4/6): standard walls match a standard value;
    #    outliers live on the non-plotting review layer and are reported.
    if check_thickness:
        if standards_mm is None:
            raise ValueError("check_thickness requires standards_mm")

        for t in _measure_layer_thicknesses(msp, wall_layer):
            if t <= 0:
                result.problems.append(f"{wall_layer}: zero-thickness wall")
                continue
            nearest = min(standards_mm, key=lambda s: abs(s - t))
            if abs(nearest - t) > thickness_tol_mm:
                result.problems.append(
                    f"{wall_layer}: non-standard thickness {t:.0f}mm "
                    f"(should be flagged to {review_layer})"
                )

        result.flagged = _measure_layer_thicknesses(msp, review_layer)
        for t in result.flagged:
            if t <= 0:
                result.problems.append(f"{review_layer}: zero-thickness wall")

        # The review layer, when present, must be non-plotting.
        if review_layer in doc.layers and doc.layers.get(review_layer).dxf.plot != 0:
            result.problems.append(f"{review_layer} must be non-plotting (plot flag set)")

    return result


def main(argv: list[str] | None = None) -> int:
    """CLI: validate a DXF file and print the result. Returns process exit code."""
    parser = argparse.ArgumentParser(description="Validate a cadplatform DXF file.")
    parser.add_argument("dxf", help="path to the DXF file")
    parser.add_argument(
        "--layer",
        action="append",
        dest="layers",
        help="required layer name (repeatable). Defaults to the full AIA table.",
    )
    args = parser.parse_args(argv)

    required = None
    if args.layers:
        required = {name: LAYERS[name] for name in args.layers}

    result = validate(args.dxf, required_layers=required)
    print(result.summary())
    return 0 if result.ok else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
