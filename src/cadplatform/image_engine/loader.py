"""Load a drawing (PDF / PNG / JPEG) into a grayscale raster.

PDFs are rendered with PyMuPDF; rasters are read with OpenCV. Output is always a
single-channel uint8 ndarray so the rest of the engine has one input shape.
"""

from __future__ import annotations

import os

import cv2
import numpy as np

_RASTER_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}


def load_image(path: str, pdf_dpi: int = 200) -> np.ndarray:
    """Return a grayscale (uint8) image for the given file.

    PDFs render their first page at ``pdf_dpi``. Rasters load as-is and are
    converted to grayscale.
    """
    ext = os.path.splitext(path)[1].lower()

    if ext == ".pdf":
        return _load_pdf_first_page(path, pdf_dpi)

    if ext in _RASTER_EXTS:
        img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        if img is None:
            raise ValueError(f"could not read raster image: {path}")
        return img

    raise ValueError(f"unsupported input format: {ext!r} ({path})")


def _load_pdf_first_page(path: str, dpi: int) -> np.ndarray:
    import fitz  # PyMuPDF; imported lazily so non-PDF paths don't need it

    doc = fitz.open(path)
    try:
        page = doc.load_page(0)
        zoom = dpi / 72.0
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), colorspace=fitz.csGRAY)
        buf = np.frombuffer(pix.samples, dtype=np.uint8)
        return buf.reshape(pix.height, pix.width).copy()
    finally:
        doc.close()
