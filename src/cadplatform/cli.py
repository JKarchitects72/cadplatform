"""cadplatform CLI — the ONLY place the three subsystems are orchestrated.

Pipeline:
    STAGE A (image_engine): separate ink into discovered layer-groups by the
        drawing's own palette (convention-independent; no colour->meaning), plus
        structural text-region metadata (where NOT to look for walls).
    STAGE B (cad_pipeline): evidence-based decomposition — region detectors claim
        stairs/hatch/grid by their bound features, cross-group assembly pairs the
        remaining faces into walls (the single wall emitter), and each group is
        labelled by its dominant structural evidence (+ heterogeneity flag).
    Walls -> existing thickness standardization -> DXF -> audit.
"""

from __future__ import annotations

import argparse
import sys

from . import config
from .cad_pipeline.decompose import WALL, decompose
from .cad_pipeline.geometry import Segment
from .cad_pipeline.layers import WALL_REVIEW_LAYER
from .dxf_layer.serialize import build_doc, write_dxf
from .dxf_layer.validate import validate
from .image_engine import vision_judge
from .image_engine.detect import detect_wall_edges
from .image_engine.layer_separation import separate_layers
from .image_engine.loader import load_bgr
from .image_engine.preprocess import denoise
from .image_engine.text_regions import detect_text_regions


def _px_to_mm(segments: list[Segment], scale: float, height_px: int) -> list[Segment]:
    """Scale pixel segments to mm and flip the y-axis (image y-down -> CAD y-up)."""
    return [
        Segment(s.x1 * scale, (height_px - s.y1) * scale,
                s.x2 * scale, (height_px - s.y2) * scale)
        for s in segments
    ]


def _separate_and_detect(input_path: str, scale: float):
    """Stage A: BGR -> groups (+segments mm) + text boxes (mm) + masks + image."""
    bgr = load_bgr(input_path)
    h_px, w_px = bgr.shape[:2]
    groups_raw = separate_layers(bgr)
    text_px = detect_text_regions(bgr)
    text_mm = [(x * scale, (h_px - (y + th)) * scale, (x + tw) * scale, (h_px - y) * scale)
               for (x, y, tw, th) in text_px]
    groups, masks = [], {}
    for g in groups_raw:
        edges = detect_wall_edges(denoise(g.mask))
        groups.append({
            "group_id": g.group_id,
            "segments": _px_to_mm(edges, scale, h_px),
            "ink_fraction": g.ink_fraction,
        })
        masks[g.group_id] = g.mask
    return groups, text_mm, (h_px, w_px), bgr, masks


def convert(input_path: str, output_path: str, scale_mm_per_px: float) -> dict:
    """Full pipeline -> DXF + audit. Returns a summary dict."""
    standards = config.standard_wall_thicknesses_mm()
    guard = config.wall_thickness_snap_guard_mm()

    groups, text_mm, (h_px, w_px), bgr, masks = _separate_and_detect(input_path, scale_mm_per_px)

    # Vision adjudication is injected: cad_pipeline calls this for AMBIGUOUS groups
    # only and receives a label back — never an image, never a coordinate.
    vision_records: list[dict] = []
    cache_dir = config.vision_cache_dir()

    def judge(group_id):
        verdict, record = vision_judge.adjudicate(bgr, masks[group_id], group_id, cache_dir)
        vision_records.append(record)
        return verdict

    decomp = decompose(
        groups, text_mm, w_px * scale_mm_per_px, h_px * scale_mm_per_px,
        standards, guard, config.ortho_tolerance_deg(),
        judge=judge,
        amb_top1=config.vision_ambiguity_top1(),
        amb_margin=config.vision_ambiguity_margin(),
    )
    walls = decomp.walls

    doc = build_doc(walls)
    write_dxf(doc, output_path)

    from .dxf_layer.layer_defs import LAYERS
    result = validate(
        output_path,
        required_layers={"A-WALL-NEWW": LAYERS["A-WALL-NEWW"],
                         "A-WALL-REVIEW": LAYERS["A-WALL-REVIEW"]},
        check_thickness=True,
        standards_mm=standards,
    )

    return {
        "walls": len(walls),
        "standard_walls": len([w for w in walls if w.layer == "A-WALL-NEWW"]),
        "flagged_walls": len([w for w in walls if w.layer == WALL_REVIEW_LAYER]),
        "wall_objects": walls,
        "groups": [vars(r) for r in decomp.group_reports],
        "region_counts": decomp.region_counts,
        "vision": {
            "calls": len(vision_records),
            "cached": sum(1 for r in vision_records if r["cached"]),
            "fallbacks": sum(1 for r in vision_records if r["fallback"]),
            "records": vision_records,
        },
        "audit_errors": result.audit_errors,
        "validation": result,
        "output": output_path,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cadplatform")
    sub = parser.add_subparsers(dest="command", required=True)
    conv = sub.add_parser("convert", help="convert a drawing into a DXF")
    conv.add_argument("input", help="input drawing (PDF/PNG/JPEG)")
    conv.add_argument("-o", "--output", required=True, help="output DXF path")
    conv.add_argument("--scale", type=float, required=True,
                      help="scale in millimeters per pixel (vision-estimated scale is deferred)")
    args = parser.parse_args(argv)

    if args.command == "convert":
        summary = convert(args.input, args.output, args.scale)
        print(f"discovered {len(summary['groups'])} layer-group(s); "
              f"regions {summary['region_counts']}")
        for g in summary["groups"]:
            emit = "EMIT" if g["label"] == WALL else "reject"
            src = g["source"]
            print(f"  g{g['group_id']}: {g['label']:11s} [{emit}] ({src}) {g['reason']}")
            if g["heterogeneous"]:
                print(f"      ! {g['hetero_note']}")
        v = summary["vision"]
        print(f"vision: {v['calls']} call(s) ({v['cached']} cached, {v['fallbacks']} fallback)")
        print(f"emitted {summary['walls']} walls "
              f"({summary['standard_walls']} on A-WALL-NEWW, "
              f"{summary['flagged_walls']} on A-WALL-REVIEW)")
        print(summary["validation"].summary())
        return 0 if summary["validation"].ok else 1
    return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
