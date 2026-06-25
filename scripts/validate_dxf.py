"""Thin CLI wrapper around the single validator in dxf_layer/validate.py.

Per CLAUDE.md rule 7 there is ONE validator implementation; this script just
forwards to it.

Usage:
    python scripts/validate_dxf.py output/floorplan.dxf [--layer A-WALL-NEWW ...]
"""

from __future__ import annotations

import sys

from cadplatform.dxf_layer.validate import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
