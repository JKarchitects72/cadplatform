"""Vision adjudication — a SEMANTIC judge for ambiguous region classification.

CLAUDE.md Rule 5 / T2.3 constraint 1: this module returns ONLY a label (from a
fixed enum), a confidence, and a short reason. It NEVER returns or produces any
coordinate, dimension, length, or position. ``VisionVerdict`` has no numeric
geometry fields BY CONSTRUCTION — that is the grep-checkable guarantee. The crop
sent to the model is rendered FROM geometry, but no geometry is sent as data and
no number the model returns ever becomes emitted geometry.

Lives in image_engine (the subsystem that owns vision). cad_pipeline never imports
this; the CLI injects a ``judge`` callable that wraps :func:`adjudicate`.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass

import cv2
import numpy as np

from ..config import vision_model

PROMPT_VERSION = "v2"

LABELS = {"WALL", "STAIRS", "HATCH", "FURNITURE", "ANNOTATION", "GRID", "OTHER"}

PROMPT = """You are analyzing a crop from a 2D architectural floor plan (a hardline CAD \
drawing). The rest of the drawing is faded; the strokes to classify are drawn in \
solid RED. Classify ONLY the red element group into exactly one category.

Categories (pick the single best fit):
- WALL: a structural or partition wall - usually two parallel faces, often with \
hatching (poche) between them, enclosing rooms.
- STAIRS: a stair/step run - a series of parallel tread lines, often with a \
direction arrow or step numbers.
- HATCH: a fill pattern (closely spaced parallel/diagonal lines) shading an area; \
not an element boundary itself.
- FURNITURE: furniture, casework, fixtures, or appliances.
- ANNOTATION: text, dimensions, leaders, tags, tick marks, or symbols.
- GRID: structural column gridlines - long lines spanning the sheet, often \
dash-dot, with bubble tags.
- OTHER: none of the above, or you cannot tell.

Respond with ONLY a compact JSON object - no prose, no markdown:
{"label":"<WALL|STAIRS|HATCH|FURNITURE|ANNOTATION|GRID|OTHER>","confidence":<0.0-1.0>,"reason":"<<=12 words>"}

Do NOT include any coordinates, dimensions, lengths, measurements, or positions. \
Return only the label, confidence, and a short reason."""


@dataclass(frozen=True)
class VisionVerdict:
    """A semantic judgement. NO geometry fields — label/confidence/reason only."""

    label: str
    confidence: float
    reason: str


def render_crop(bgr: np.ndarray, mask: np.ndarray, pad_frac: float = 0.2,
                pad_min: int = 200, max_dim: int = 768):
    """Render a context crop of the colour drawing with the group highlighted.

    Uses geometry (the mask bbox) only to MAKE A PICTURE; nothing here is sent to
    the model as numeric data.
    """
    ys, xs = np.where(mask > 0)
    x0, x1, y0, y1 = int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())
    pad = int(max(pad_frac * max(x1 - x0, y1 - y0), pad_min))
    X0, Y0 = max(0, x0 - pad), max(0, y0 - pad)
    X1, Y1 = min(bgr.shape[1], x1 + pad), min(bgr.shape[0], y1 + pad)

    crop = bgr[Y0:Y1, X0:X1].copy()
    # Fade the whole crop toward white, then draw ONLY the target group's strokes in
    # bold red. Fading (rather than colour-highlighting) is palette-independent: it
    # works even when the drawing itself uses the highlight colour.
    crop = cv2.addWeighted(crop, 0.35, np.full_like(crop, 255), 0.65, 0)
    sub = mask[Y0:Y1, X0:X1]
    thick = cv2.dilate(sub, np.ones((3, 3), np.uint8))
    crop[thick > 0] = (0, 0, 255)  # red (BGR) target strokes
    cv2.rectangle(crop, (x0 - X0, y0 - Y0), (x1 - X0, y1 - Y0),
                  (0, 0, 255), max(2, crop.shape[0] // 250))

    longest = max(crop.shape[:2])
    if longest > max_dim:
        s = max_dim / longest
        crop = cv2.resize(crop, (int(crop.shape[1] * s), int(crop.shape[0] * s)),
                          interpolation=cv2.INTER_AREA)
    return crop, (X0, Y0, X1, Y1)


def _call_api(png_bytes: bytes, model: str, timeout: float) -> str:
    import anthropic

    client = anthropic.Anthropic(timeout=timeout)
    b64 = base64.standard_b64encode(png_bytes).decode("ascii")
    msg = client.messages.create(
        model=model,
        max_tokens=200,
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}},
            {"type": "text", "text": PROMPT},
        ]}],
    )
    return "".join(b.text for b in msg.content if b.type == "text")


def _parse(text: str) -> VisionVerdict:
    t = text.strip().strip("`")
    s = t[t.find("{"): t.rfind("}") + 1]
    d = json.loads(s)
    label = str(d.get("label", "OTHER")).upper()
    if label not in LABELS:
        label = "OTHER"
    try:
        conf = min(1.0, max(0.0, float(d.get("confidence", 0.5))))
    except (TypeError, ValueError):
        conf = 0.5
    reason = str(d.get("reason", ""))[:80]
    return VisionVerdict(label, conf, reason)


def adjudicate(bgr, mask, group_id, cache_dir, model=None, timeout=30.0):
    """Return (VisionVerdict | None, record).  None => caller must fall back."""
    model = model or vision_model()
    crop, bbox = render_crop(bgr, mask)
    ok, png = cv2.imencode(".png", crop)
    png_bytes = png.tobytes()
    key = hashlib.sha256(png_bytes + model.encode() + PROMPT_VERSION.encode()).hexdigest()
    record = {"group_id": group_id, "bbox_px": bbox, "cached": False, "fallback": False,
              "latency_ms": 0, "label": None, "confidence": None, "reason": None}

    cpath = os.path.join(cache_dir, key + ".json")
    if os.path.exists(cpath):
        with open(cpath) as fh:
            d = json.load(fh)
        v = VisionVerdict(d["label"], d["confidence"], d["reason"])
        record.update(cached=True, label=v.label, confidence=v.confidence, reason=v.reason)
        return v, record

    t0 = time.time()
    try:
        v = _parse(_call_api(png_bytes, model, timeout))
    except Exception as e:  # noqa: BLE001 — any failure => graceful fallback
        record.update(fallback=True, latency_ms=int((time.time() - t0) * 1000),
                      reason=f"fallback:{type(e).__name__}")
        logging.warning("vision fallback for group %s: %s", group_id, e)
        return None, record

    record.update(latency_ms=int((time.time() - t0) * 1000),
                  label=v.label, confidence=v.confidence, reason=v.reason)
    os.makedirs(cache_dir, exist_ok=True)
    with open(cpath, "w") as fh:
        json.dump({"label": v.label, "confidence": v.confidence, "reason": v.reason}, fh)
    return v, record
