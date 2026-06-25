"""cadplatform CLI — the ONLY place the three subsystems are orchestrated.

First vertical slice:
    load image -> detect straight wall lines (OpenCV) -> convert to mm (+y-flip)
    -> orthogonalize & snap to 90 deg -> merge into wall centerlines
    -> assign A-WALL-NEWW -> serialize to DXF -> run dxf.audit().
"""

from __future__ import annotations

import argparse
import sys

from . import config
from .cad_pipeline.geometry import Segment
from .cad_pipeline.layers import assign_wall_layers
from .cad_pipeline.orthogonalize import orthogonalize
from .cad_pipeline.walls import (
    merge_collinear,
    pair_parallel_edges,
    standardize_thickness,
)
from .dxf_layer.serialize import build_doc, write_dxf
from .dxf_layer.validate import validate
from .image_engine.detect import detect_wall_edges
from .image_engine.loader import load_image
from .image_engine.preprocess import binarize, denoise


def _px_to_mm(segments: list[Segment], scale: float, height_px: int) -> list[Segment]:
    """Scale pixel segments to mm and flip the y-axis (image y-down -> CAD y-up)."""
    out = []
    for s in segments:
        out.append(
            Segment(
                s.x1 * scale,
                (height_px - s.y1) * scale,
                s.x2 * scale,
                (height_px - s.y2) * scale,
            )
        )
    return out


def convert(input_path: str, output_path: str, scale_mm_per_px: float) -> dict:
    """Run the wall slice end to end. Returns a summary dict."""
    standards = config.standard_wall_thicknesses_mm()
    guard = config.wall_thickness_snap_guard_mm()
    max_standard = max(standards)

    # --- image_engine: detect wall FACE edges ---
    gray = load_image(input_path)
    binary = denoise(binarize(gray))
    px_edges = detect_wall_edges(binary)

    # px -> mm (+ y-flip) at the subsystem boundary
    mm_edges = _px_to_mm(px_edges, scale_mm_per_px, gray.shape[0])

    # --- cad_pipeline (pure geometry) ---
    tol = config.ortho_tolerance_deg()
    ortho = orthogonalize(mm_edges, tol)

    # Consolidate collinear fragments (small axis tol so the two faces of one
    # wall are NOT merged; large gap tol to bridge junction interruptions).
    edges = merge_collinear(ortho, axis_tol_mm=20.0, gap_tol_mm=2.0 * max_standard)

    # Measure thickness from paired faces, then standardize against the guard.
    walls = pair_parallel_edges(
        edges,
        min_thickness_mm=0.5 * min(standards),
        max_thickness_mm=2.0 * max_standard,
        overlap_frac=0.3,
        min_edge_length_mm=max_standard + guard,  # drop short end-cap edges
    )
    standardize_thickness(walls, standards, guard)
    assign_wall_layers(walls)

    # --- dxf_layer ---
    doc = build_doc(walls)
    write_dxf(doc, output_path)

    # mandatory audit + thickness validation (CLAUDE.md rules 4, 6, 7)
    from .dxf_layer.layer_defs import LAYERS
    result = validate(
        output_path,
        required_layers={
            "A-WALL-NEWW": LAYERS["A-WALL-NEWW"],
            "A-WALL-REVIEW": LAYERS["A-WALL-REVIEW"],
        },
        check_thickness=True,
        standards_mm=standards,
    )

    standard_walls = [w for w in walls if not w.flagged]
    flagged_walls = [w for w in walls if w.flagged]
    return {
        "raw_edges": len(px_edges),
        "walls": len(walls),
        "standard_walls": len(standard_walls),
        "flagged_walls": len(flagged_walls),
        "wall_objects": walls,
        "audit_errors": result.audit_errors,
        "validation": result,
        "output": output_path,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cadplatform")
    sub = parser.add_subparsers(dest="command", required=True)

    conv = sub.add_parser("convert", help="convert a drawing into a DXF (wall slice)")
    conv.add_argument("input", help="input drawing (PDF/PNG/JPEG)")
    conv.add_argument("-o", "--output", required=True, help="output DXF path")
    conv.add_argument(
        "--scale",
        type=float,
        required=True,
        help="scale in millimeters per pixel (vision-estimated scale is deferred)",
    )

    args = parser.parse_args(argv)

    if args.command == "convert":
        summary = convert(args.input, args.output, args.scale)
        print(f"detected {summary['raw_edges']} raw edge segments")
        print(
            f"paired into {summary['walls']} walls "
            f"({summary['standard_walls']} standard on A-WALL-NEWW, "
            f"{summary['flagged_walls']} flagged on A-WALL-REVIEW)"
        )
        for w in summary["wall_objects"]:
            if w.flagged:
                print(f"  ! {w.note}")
        print(summary["validation"].summary())
        return 0 if summary["validation"].ok else 1

    return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
