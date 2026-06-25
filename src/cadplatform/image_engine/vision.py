"""Claude vision calls — SEMANTICS and SCALE only (CLAUDE.md rule 5).

Vision is asked "what is this element?" and "how many real-world millimeters per
pixel?". It NEVER emits coordinates that become DXF geometry — all geometry comes
from OpenCV + Shapely.

The first vertical slice does not require a live API call: the CLI accepts an
explicit ``--scale`` so the pipeline (and tests) run fully offline. This module
provides the call for when scale must be inferred from the drawing instead.
"""

from __future__ import annotations

import base64
import json
import os

from ..config import vision_model


def estimate_scale_mm_per_px(image_path: str) -> float:
    """Ask Claude for the drawing's scale in millimeters per pixel.

    Requires ``ANTHROPIC_API_KEY``. Returns a single float; raises if the model
    response cannot be parsed. Geometry is never requested here — scale only.
    """
    import anthropic

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY is required to estimate scale via vision")

    media_type = _media_type(image_path)
    with open(image_path, "rb") as fh:
        data = base64.standard_b64encode(fh.read()).decode("ascii")

    client = anthropic.Anthropic()
    message = client.messages.create(
        model=vision_model(),
        max_tokens=256,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": media_type, "data": data},
                    },
                    {
                        "type": "text",
                        "text": (
                            "This is an architectural floor plan. Using any scale bar, "
                            "dimension strings, or labelled measurements, estimate the "
                            "drawing scale as real-world MILLIMETERS PER PIXEL. Reply with "
                            'ONLY a JSON object: {"mm_per_px": <number>}. Do not describe '
                            "geometry or coordinates."
                        ),
                    },
                ],
            }
        ],
    )
    text = "".join(block.text for block in message.content if block.type == "text")
    payload = json.loads(text.strip())
    return float(payload["mm_per_px"])


def _media_type(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
    }.get(ext, "image/png")
