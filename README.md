# cadplatform

Convert 2D architectural drawings (PDF / PNG / JPEG) into Class-A,
production-ready DXF files.

> Project rules live in [`CLAUDE.md`](./CLAUDE.md) and are non-negotiable.

## Architecture

Three hard-separated subsystems, data flowing one direction:

```
image_engine  →  cad_pipeline  →  dxf_layer
   (pixels)       (geometry)        (DXF)
```

- **`image_engine/`** — load PDF/raster, preprocess, OpenCV line & contour
  detection, and a Claude vision call for **semantic labels and scale only**.
- **`cad_pipeline/`** — geometric correction: ortho snapping, parallel
  alignment, 90.0000° corner enforcement, wall-thickness standardization,
  layer assignment. Pure geometry (Shapely/NumPy), no I/O.
- **`dxf_layer/`** — ezdxf serialization: native CIRCLE/ARC/LINE/MTEXT
  entities, AIA layer definitions, blocks, and validation.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"     # or: pip install -r requirements.txt
```

### Vision model

The vision model defaults to `claude-sonnet-4-6` and is overridable:

```bash
export CADPLATFORM_VISION_MODEL=claude-opus-4-8   # escalate for hard scans
export ANTHROPIC_API_KEY=sk-...
```

## Usage

```bash
cadplatform convert samples/floorplan.png -o output/floorplan.dxf
```

## Wall subsystem

`load image → detect wall FACE edges (Canny + Hough) → orthogonalize & snap to
90° → consolidate collinear fragments → pair parallel faces & MEASURE thickness →
standardize thickness against the configurable standard set (flag outliers beyond
the guard) → serialize each wall as two parallel faces on A-WALL-NEWW (standard)
or the non-plotting A-WALL-REVIEW (flagged) → run dxf.audit()`.

Thickness is measured from the paired faces *before* any collapse to a
centerline. Outliers beyond the snap guard are never force-snapped: they land on
the non-plotting `A-WALL-REVIEW` layer at their raw measured thickness and are
reported by the validator.

## Tests

```bash
pytest
```
