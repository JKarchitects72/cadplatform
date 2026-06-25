# CLAUDE.md — cadplatform Project Memory

Platform purpose: convert 2D architectural drawings (PDF / PNG / JPEG) into
Class-A, production-ready DXF files.

This file encodes PERMANENT, non-negotiable rules. Every change to the codebase
must comply. If a task appears to conflict with a rule here, stop and flag it.

## NON-NEGOTIABLE RULES (always apply, no exceptions)

### 1. Architecture: three separated subsystems
- `image_engine/` — load + preprocess + OpenCV detection + vision (semantics/scale).
- `cad_pipeline/` — geometric correction (ortho snapping, parallel alignment,
  90.0000° corner enforcement, wall-thickness standardization, layer assignment).
  Pure geometry. No file I/O, no vision, no ezdxf.
- `dxf_layer/` — ezdxf serialization only.
- Data flows ONE direction: `image_engine → cad_pipeline → dxf_layer`.
  No subsystem imports anything "downstream" of itself. Only the CLI orchestrates
  all three.

### 2. Layers (AIA / US National CAD Standard)
- Layer names follow AIA `Discipline-Major-Minor`, e.g. `A-WALL-NEWW`,
  `A-WALL-EXTR`, `A-DOOR`, `A-FLOR-OVHD`, `I-FURN`.
- Every layer has a FIXED ACI color and FIXED lineweight, defined ONCE in
  `dxf_layer/layer_defs.py`. That table is the single source of truth.
- Entities NEVER override appearance. color = BYLAYER, lineweight = BYLAYER,
  linetype = BYLAYER. No per-entity color/lineweight/linetype is ever set.

### 3. Geometry fidelity
- Circles, arcs, and ellipses are emitted as NATIVE DXF entities
  (CIRCLE / ARC / ELLIPSE). They are NEVER approximated as segmented polylines.
- Straight walls / linear elements are LINE or LWPOLYLINE.
- Text is MTEXT.

### 4. Standardized dimensions
- Wall thicknesses snap to a standard set: 100 / 150 / 200 mm.
  Raw pixel-derived thicknesses are never written; always snap to the nearest
  standard value.

### 5. Vision API scope
- The Claude vision API is used for SEMANTICS (what is this element?) and
  SCALE (real-world units per pixel) ONLY.
- All geometry is produced by OpenCV + Shapely. Vision never emits coordinates
  that become DXF geometry.

### 6. Validation is mandatory per feature
- Every feature ships with a validation script that:
  - opens the produced DXF,
  - runs `doc.audit()` and asserts ZERO errors,
  - asserts the required layers exist with correct ACI color and lineweight,
  - asserts there are no stray entities (everything sits on an expected layer).
- Reuse `dxf_layer/validate.py`. A feature is NOT "done" until its validation
  passes.

## Vision model
- Default model string: `claude-sonnet-4-6`.
- MUST be configurable via env var `CADPLATFORM_VISION_MODEL` (e.g. escalate to
  `claude-opus-4-8` for difficult scans). Resolved in `config.py`.

## Units
- Internal working units are millimeters. DXF is written in millimeters
  (`$INSUNITS = 4`).
