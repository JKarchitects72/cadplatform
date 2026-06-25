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

### 1a. Orthogonalization is TOLERANCE-BASED
- 90° / axis enforcement is tolerance-based, NOT unconditional. Snap a line to
  exact orthogonal only when it is within ±N degrees of an axis (N configurable
  in `config.py`, default 3°). Lines outside that band are PRESERVED as-is.
- Never force a genuinely angled wall (intentional diagonal / splay) to 90°.
  When in doubt, preserve the measured angle.

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
- Freeform curves that are not clean circles/arcs/ellipses are emitted as
  SPLINE entities. They are NEVER chord-approximated into polylines.
- Straight walls / linear elements are LINE or LWPOLYLINE.
- Text is MTEXT.
- Detection-side rule: `image_engine` MUST attempt to recognize curved geometry
  (circles, arcs, ellipses, freeform curves) AS curves — it must not decompose
  everything into straight segments. Curve detection / reconstruction
  (Hough Circle, `cv2.fitEllipse`, arc fitting, spline fitting) is a DEFERRED
  subsystem stage and is NOT part of the first wall slice. The first slice's
  line-only detector is therefore understood as INCOMPLETE, not as the final
  design.

### 4. Wall thickness standardization
- Detected wall thicknesses are SNAPPED to the nearest value in a CONFIGURABLE
  standard set. Raw pixel-derived thicknesses are NEVER written.
- The standard set lives in `config.py` (`STANDARD_WALL_THICKNESSES_MM`,
  default 90 / 100 / 120 / 150 / 200 / 250 / 300 mm) and is overridable via env.
- Max-snap-distance guard: if a detected thickness is farther than the guard
  (`WALL_THICKNESS_SNAP_GUARD_MM` in `config.py`) from every standard value,
  FLAG it for review rather than force-snapping.
- Scope: this rule covers wall thickness values only. Associative DIMENSION
  entities are DEFERRED and out of scope here.

### 5. Vision API scope
- The Claude vision API is used for SEMANTICS (what is this element?) and
  SCALE (real-world units per pixel) ONLY.
- All geometry is produced by OpenCV + Shapely. Vision never emits coordinates
  that become DXF geometry.

### 6. Blocks for repeated elements
- Doors, windows, and repeated fixtures are emitted as reusable BLOCK
  definitions with defined insertion points — NEVER as loose primitives.
- (Deferred work; recorded now so the pattern is correct from the start.)

### 7. Validation is mandatory per feature
- Every feature ships with a validation script that:
  - opens the produced DXF,
  - runs `doc.audit()` and asserts ZERO errors,
  - asserts the required layers exist with correct ACI color and lineweight,
  - asserts there are no stray entities (everything sits on an expected layer).
- There is ONE validator implementation: `dxf_layer/validate.py`.
  `scripts/validate_dxf.py` is a thin CLI wrapper around it — never a second copy.
- A feature is NOT "done" until its validation passes.

## Vision model
- Default model string: `claude-sonnet-4-6`.
- MUST be configurable via env var `CADPLATFORM_VISION_MODEL` (e.g. escalate to
  `claude-opus-4-8` for difficult scans). Resolved in `config.py`.

## Units & DXF version
- Internal working units are millimeters. DXF is written in millimeters
  (`$INSUNITS = 4`).
- Target DXF version is PINNED to R2018 (`AC1032`), set in `config.py`
  (`DXF_VERSION`).
