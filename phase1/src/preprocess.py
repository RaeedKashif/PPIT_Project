"""Image preprocessing: grayscale, denoise, deskew, adaptive threshold."""

from __future__ import annotations

import cv2
import numpy as np


def _to_gray(bgr: np.ndarray) -> np.ndarray:
    if bgr.ndim == 2:
        return bgr
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)


_MAX_PLAUSIBLE_SKEW_DEG = 15.0
_MIN_SKEW_TO_CORRECT_DEG = 0.3


def _deskew(gray: np.ndarray) -> tuple[np.ndarray, float]:
    """Estimate a small rotation angle from the foreground pixels and rotate to flat.

    Real scans rarely skew more than ~5°. If the estimate exceeds
    ``_MAX_PLAUSIBLE_SKEW_DEG`` we treat it as a misfire (e.g. a sparse page
    where the bounding rect picks up the wrong principal axis) and skip rotation.
    """
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    coords = np.column_stack(np.where(binary > 0))
    if coords.shape[0] < 100:
        return gray, 0.0

    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = 90 + angle
    rotation = -angle  # degrees to rotate gray to upright

    if abs(rotation) < _MIN_SKEW_TO_CORRECT_DEG:
        return gray, 0.0
    if abs(rotation) > _MAX_PLAUSIBLE_SKEW_DEG:
        return gray, 0.0

    h, w = gray.shape
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), rotation, 1.0)
    rotated = cv2.warpAffine(
        gray, matrix, (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )
    return rotated, rotation


def preprocess(
    bgr_image: np.ndarray,
    *,
    deskew: bool = True,
    denoise: bool = True,
) -> dict:
    """Run the standard preprocessing pipeline and return intermediate images.

    Returns a dict with:
        gray:        grayscale (post-deskew, post-denoise) — fed to Tesseract.
        binary:      adaptive-threshold binary copy — used for formatting heuristics.
        deskew_deg:  the rotation in degrees applied (0 if none).
    """
    gray = _to_gray(bgr_image)

    if denoise:
        gray = cv2.medianBlur(gray, 3)

    angle = 0.0
    if deskew:
        gray, angle = _deskew(gray)

    binary = cv2.adaptiveThreshold(
        gray, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31, 15,
    )

    return {"gray": gray, "binary": binary, "deskew_deg": angle}


def load_image(path: str) -> np.ndarray:
    """Read a JPG/PNG from disk into a BGR numpy array."""
    img = cv2.imread(path, cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(f"Could not read image: {path}")
    return img
