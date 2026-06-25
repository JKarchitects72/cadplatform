"""Generate a synthetic floor-plan PNG with walls of real thickness.

At 10 mm/px the plan contains:
  - a 250 mm (25 px) external envelope wall  -> standard
  - a 100 mm (10 px) interior partition, T-joining the envelope (junction test)
  - a 350 mm (35 px) outlier wall            -> beyond the snap guard -> flagged

Walls are drawn as FILLED bands so their two faces are real, measurable edges.
Deterministic; no external input required.

Usage:
    python scripts/make_sample_plan.py [output_path]
"""

from __future__ import annotations

import sys

import cv2
import numpy as np

WIDTH, HEIGHT = 800, 600
BLACK = 0
WHITE = 255


def make_plan() -> np.ndarray:
    img = np.full((HEIGHT, WIDTH), WHITE, dtype=np.uint8)

    # External envelope: filled outer rect minus a white inner rect => 25 px ring.
    cv2.rectangle(img, (60, 60), (740, 540), BLACK, thickness=-1)
    cv2.rectangle(img, (85, 85), (715, 515), WHITE, thickness=-1)

    # Interior partition, 10 px wide, T-joining the bottom envelope wall.
    cv2.rectangle(img, (400, 300), (410, 515), BLACK, thickness=-1)

    # Outlier wall, 35 px tall, standalone in the upper interior.
    cv2.rectangle(img, (150, 150), (450, 185), BLACK, thickness=-1)

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
