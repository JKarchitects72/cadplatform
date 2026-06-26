"""cadplatform CLI — the ONLY place the three subsystems are orchestrated.

Pipeline:
    STAGE A (image_engine): separate ink into discovered layer-groups by the
        drawing's own palette (convention-independent; no colour->meaning).
    STAGE B (cad_pipeline): classify each group by STRUCTURE (geometry only) as
        wall / grid / stairs / annotation / furniture / hatch / other.
    Only WALL (and near-miss WALL_REVIEW) groups proceed into the existing
        detect -> pair faces -> measure thickness -> standardize -> DXF -> audit.
"""

from __future__ import annotations

import argparse
import sys

from . import config
from .cad_pipeline.classify import (
    EMITTED,
    WALL,
    GroupMeta,
    classify_group,
)
from .cad_pipeline.geometry import Segment
from .cad_pipeline.layers import WALL_REVIEW_LAYER, assign_wall_layers
from .cad_pipeline.orthogonalize import orthogonalize
from .cad_pipeline.walls import (
    merge_collinear,
    pair_parallel_edges,
    standardize_thickness,
)
from .dxf_layer.serialize import build_doc, write_dxf
from .dxf_layer.validate import validate
from .image_engine.detect import detect_wall_edges
from .image_engine.loader import load_bgr
from .image_engine.layer_separation import separate_layers
from .image_engine.preprocess import denoise


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


def _walls_from_edges(mm_edges: list[Segment], standards, guard, max_standard) -> list:
    """Existing wall pipeline on one group's edges: pair -> measure -> standardize."""
    tol = config.ortho_tolerance_deg()
    ortho = orthogonalize(mm_edges, tol)
    edges = merge_collinear(ortho, axis_tol_mm=20.0, gap_tol_mm=2.0 * max_standard)
    walls = pair_parallel_edges(
        edges,
        min_thickness_mm=0.5 * min(standards),
        max_thickness_mm=2.0 * max_standard,
        overlap_frac=0.3,
        min_edge_length_mm=max_standard + guard,
    )
    standardize_thickness(walls, standards, guard)
    return walls


def classify_groups(input_path: str, scale_mm_per_px: float) -> dict:
    """Stage A + Stage B only (no DXF): separate, detect, classify each group.

    Returns the discovered groups with their classification — used by both
    ``convert`` and the diagnostic harness (which re-classifies at several scales).
    """
    standards = config.standard_wall_thicknesses_mm()
    guard = config.wall_thickness_snap_guard_mm()

    bgr = load_bgr(input_path)
    height_px, width_px = bgr.shape[:2]
    sheet_w_mm = width_px * scale_mm_per_px
    sheet_h_mm = height_px * scale_mm_per_px

    groups = separate_layers(bgr)  # STAGE A — convention-independent
    reports = []
    for g in groups:
        px_edges = detect_wall_edges(denoise(g.mask))
        mm_edges = _px_to_mm(px_edges, scale_mm_per_px, height_px)
        meta = GroupMeta(
            stroke_width_mm=g.stroke_width_px * scale_mm_per_px,
            dash_kind=g.dash_kind,
            ink_fraction=g.ink_fraction,
        )
        cls = classify_group(mm_edges, sheet_w_mm, sheet_h_mm, standards, guard, meta)  # STAGE B
        reports.append({"group": g, "mm_edges": mm_edges, "classification": cls})
    return {
        "reports": reports,
        "image_shape": (height_px, width_px),
        "sheet_mm": (sheet_w_mm, sheet_h_mm),
    }


def convert(input_path: str, output_path: str, scale_mm_per_px: float) -> dict:
    """Run the full pipeline: Stage A separation -> Stage B classification ->
    existing wall pipeline (WALL/near-miss groups only) -> DXF -> audit."""
    standards = config.standard_wall_thicknesses_mm()
    guard = config.wall_thickness_snap_guard_mm()
    max_standard = max(standards)

    sep = classify_groups(input_path, scale_mm_per_px)

    all_walls = []
    group_summaries = []
    for rep in sep["reports"]:
        g = rep["group"]
        cls = rep["classification"]
        emitted = 0
        if cls.label in EMITTED:
            walls = _walls_from_edges(rep["mm_edges"], standards, guard, max_standard)
            if cls.label == WALL:
                assign_wall_layers(walls)  # flagged outliers -> review, rest -> NEWW
            else:  # WALL_REVIEW: whole near-miss group is visible-but-not-plotted
                for w in walls:
                    w.layer = WALL_REVIEW_LAYER
                    w.note = (w.note + "; near-miss wall group").strip("; ")
            all_walls.extend(walls)
            emitted = len(walls)
        group_summaries.append({
            "group_id": g.group_id, "label": cls.label, "reason": cls.reason,
            "features": cls.features, "heterogeneous": cls.heterogeneous,
            "hetero_note": cls.hetero_note, "emitted_walls": emitted,
            "color_bgr": g.color_bgr, "ink_fraction": g.ink_fraction,
        })

    # --- dxf_layer ---
    doc = build_doc(all_walls)
    write_dxf(doc, output_path)

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

    standard_walls = [w for w in all_walls if w.layer == "A-WALL-NEWW"]
    flagged_walls = [w for w in all_walls if w.layer == WALL_REVIEW_LAYER]
    return {
        "walls": len(all_walls),
        "standard_walls": len(standard_walls),
        "flagged_walls": len(flagged_walls),
        "wall_objects": all_walls,
        "groups": group_summaries,
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
        print(f"discovered {len(summary['groups'])} layer-group(s)")
        for g in summary["groups"]:
            tag = "" if g["emitted_walls"] else "  (rejected)"
            print(f"  group {g['group_id']}: {g['label']:11s} {g['reason']}{tag}")
            if g["heterogeneous"]:
                print(f"      ! {g['hetero_note']}")
        print(
            f"emitted {summary['walls']} walls "
            f"({summary['standard_walls']} on A-WALL-NEWW, "
            f"{summary['flagged_walls']} on A-WALL-REVIEW)"
        )
        print(summary["validation"].summary())
        return 0 if summary["validation"].ok else 1

    return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
