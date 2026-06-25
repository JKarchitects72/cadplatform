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
from .cad_pipeline.layers import assign_wall_layer
from .cad_pipeline.orthogonalize import orthogonalize
from .cad_pipeline.walls import merge_centerlines, to_walls
from .dxf_layer.serialize import build_doc, write_dxf
from .dxf_layer.validate import validate
from .image_engine.detect import detect_line_segments
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
    # --- image_engine ---
    gray = load_image(input_path)
    binary = denoise(binarize(gray))
    px_segments = detect_line_segments(binary)

    # px -> mm (+ y-flip) at the subsystem boundary
    mm_segments = _px_to_mm(px_segments, scale_mm_per_px, gray.shape[0])

    # --- cad_pipeline (pure geometry) ---
    tol = config.ortho_tolerance_deg()
    ortho = orthogonalize(mm_segments, tol)
    # merge tolerances scale with the standard wall set / drawing scale
    axis_tol = max(config.DEFAULT_WALL_THICKNESSES_MM)  # group fragments within a wall's span
    gap_tol = axis_tol
    centerlines = merge_centerlines(ortho, axis_tol_mm=axis_tol, gap_tol_mm=gap_tol)
    walls = assign_wall_layer(to_walls(centerlines))

    # --- dxf_layer ---
    doc = build_doc(walls)
    write_dxf(doc, output_path)

    # mandatory audit (CLAUDE.md rule 7)
    result = validate(output_path, required_layers={"A-WALL-NEWW": _walls_layer_def()})

    return {
        "raw_segments": len(px_segments),
        "walls": len(walls),
        "audit_errors": result.audit_errors,
        "validation": result,
        "output": output_path,
    }


def _walls_layer_def():
    from .dxf_layer.layer_defs import LAYERS
    return LAYERS["A-WALL-NEWW"]


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
        print(f"detected {summary['raw_segments']} raw segments")
        print(f"merged into {summary['walls']} wall centerlines on A-WALL-NEWW")
        print(summary["validation"].summary())
        return 0 if summary["validation"].ok else 1

    return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
