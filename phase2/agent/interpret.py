"""Doc-type classifier (slide 25 Interpret, slide 26 Tier-2 hook).

The MVP is rule-based — fast, debuggable, and deterministic. The shape of
the function is the same as a learned classifier would be (image in, label
out, confidence out), so swapping in a CNN later is a one-file change.

We deliberately ship rules first (slide 26 ordering): the system must work
without any learned model in place.
"""

from __future__ import annotations

from typing import Sequence

import cv2
import numpy as np

from . import DocClassification


_LOW_INK_FRACTION = 0.04             # below this = sparse page
_HIGH_INK_FRACTION = 0.30            # above this = dense page or solid background
_HORIZONTAL_LINE_RATIO = 0.20        # tabular pages have many horizontal lines


def _ink_fraction(gray: np.ndarray) -> float:
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    return float((binary > 0).sum()) / float(binary.size or 1)


def _horizontal_line_count(gray: np.ndarray) -> int:
    """Count strong horizontal lines — a fingerprint of forms / tables."""
    edges = cv2.Canny(gray, 50, 150)
    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1))
    horiz = cv2.morphologyEx(edges, cv2.MORPH_OPEN, h_kernel)
    contours, _ = cv2.findContours(horiz, cv2.RETR_EXTERNAL,
                                   cv2.CHAIN_APPROX_SIMPLE)
    return sum(1 for c in contours if cv2.boundingRect(c)[2] > 0.4 * gray.shape[1])


def _aspect_ratio(gray: np.ndarray) -> float:
    h, w = gray.shape[:2]
    return w / h if h else 0.0


def _looks_like_id_card(gray: np.ndarray) -> tuple[bool, list[str]]:
    """Heuristic: ID cards are landscape (~1.58 aspect, CR80 standard) with
    a small footprint relative to a typical page.
    """
    h, w = gray.shape[:2]
    ar = _aspect_ratio(gray)
    reasons: list[str] = []
    is_card = False
    if 1.45 <= ar <= 1.75:
        reasons.append(f"aspect ratio {ar:.2f} matches CR80 ID-card range")
        # Cards photographed alone are usually small images (<2000px wide).
        if max(h, w) < 2000:
            reasons.append(f"image small ({w}x{h}) — consistent with a card photo")
            is_card = True
    return is_card, reasons


def classify_doc(image_bgr: np.ndarray) -> DocClassification:
    """Rule-based 6-way classifier.

    Returns one of: id_card | form | letter | academic_page | receipt | unknown.
    Confidence is a coarse self-report based on how clearly one rule fired.
    """
    if image_bgr.ndim == 3:
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    else:
        gray = image_bgr

    ink = _ink_fraction(gray)
    h_lines = _horizontal_line_count(gray)
    ar = _aspect_ratio(gray)
    h, w = gray.shape[:2]

    # Quality estimate: too dark or too sparse = lower quality scan.
    if 0.04 <= ink <= 0.25:
        quality = 0.9
    elif ink < 0.04:
        quality = 0.55
    else:
        quality = 0.7

    # ID card check (high-stakes — slide 28).
    is_card, card_reasons = _looks_like_id_card(gray)
    if is_card:
        return DocClassification(
            label="id_card", confidence=0.85, quality_estimate=quality,
            reasons=card_reasons,
        )

    # Form: many horizontal lines.
    if h_lines >= 4:
        return DocClassification(
            label="form", confidence=0.75, quality_estimate=quality,
            reasons=[f"detected {h_lines} long horizontal lines (form/table fingerprint)"],
        )

    # Receipt: very narrow / tall (1:2 or worse).
    if ar < 0.55:
        return DocClassification(
            label="receipt", confidence=0.7, quality_estimate=quality,
            reasons=[f"aspect ratio {ar:.2f} is receipt-shaped (narrow + tall)"],
        )

    # Academic page: dense ink (think a book chapter).
    if ink > 0.20:
        return DocClassification(
            label="academic_page", confidence=0.65, quality_estimate=quality,
            reasons=[f"high ink fraction {ink:.2f} suggests dense body text"],
        )

    # Letter: medium ink, portrait, no horizontal rules.
    if 0.04 <= ink <= 0.20 and ar < 1.0:
        return DocClassification(
            label="letter", confidence=0.6, quality_estimate=quality,
            reasons=[f"medium ink {ink:.2f} + portrait orientation"],
        )

    return DocClassification(
        label="unknown", confidence=0.4, quality_estimate=quality,
        reasons=["no rule matched strongly; falling back to default plan"],
    )
