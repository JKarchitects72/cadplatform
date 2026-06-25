"""Generate a simple synthetic floor-plan PNG for the first vertical slice.

Draws an axis-aligned building outline plus two interior walls as thin black
centerlines on white. Deterministic; no external input required.

Usage:
    python scripts/make_sample_plan.py [output_path]
"""

from __future__ import annotations

import sys

import cv2
import numpy as np

# Image is 800x600 px. At 10 mm/px that is a 8000 x 6000 mm sheet.
WIDTH, HEIGHT = 800, 600
THICKNESS = 3
BLACK = 0


def make_plan() -> np.ndarray:
    img = np.full((HEIGHT, WIDTH), 255, dtype=np.uint8)

    # Outer building rectangle.
    cv2.rectangle(img, (80, 80), (720, 520), BLACK, THICKNESS)

    # Interior vertical wall.
    cv2.line(img, (400, 80), (400, 300), BLACK, THICKNESS)

    # Interior horizontal wall.
    cv2.line(img, (400, 300), (720, 300), BLACK, THICKNESS)

    return img


def main(argv: list[str]) -> int:
    out = argv[1] if len(argv) > 1 else "samples/floorplan.png"
    img = make_plan()
    if not cv2.imwrite(out, img):
        print(f"failed to write {out}", file=sys.stderr)
        return 1
    print(f"wrote {out} ({WIDTH}x{HEIGHT})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
