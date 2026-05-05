"""Formatting detectors: bold, italic, alignment, paragraph grouping.

All decisions are derived from pixel measurements relative to the page itself
(no hard-coded thresholds against absolute font size). Each word is annotated
with ``bold`` and ``italic`` flags, then lines are grouped into paragraphs and
each paragraph is given an alignment.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from statistics import median
from typing import Sequence

import cv2
import numpy as np

from .ocr import Word


# ---------------------------------------------------------------------------
# Per-word feature extraction
# ---------------------------------------------------------------------------

def _word_crop(binary: np.ndarray, word: Word) -> np.ndarray:
    """Slice a word's bounding box out of the binarized page (0=ink, 255=bg)."""
    h_img, w_img = binary.shape
    x0 = max(0, word.x)
    y0 = max(0, word.y)
    x1 = min(w_img, word.x + word.w)
    y1 = min(h_img, word.y + word.h)
    if x1 <= x0 or y1 <= y0:
        return np.empty((0, 0), dtype=binary.dtype)
    return binary[y0:y1, x0:x1]


def _ink_ratio(crop: np.ndarray) -> float:
    """Fraction of the bounding box that is ink (foreground)."""
    if crop.size == 0:
        return 0.0
    ink = (crop < 128).sum()
    return float(ink) / float(crop.size)


def _stroke_thickness(crop: np.ndarray) -> float:
    """Average stroke thickness in pixels via the distance transform on ink."""
    if crop.size == 0:
        return 0.0
    ink_mask = (crop < 128).astype(np.uint8) * 255
    if ink_mask.sum() == 0:
        return 0.0
    dist = cv2.distanceTransform(ink_mask, cv2.DIST_L2, 3)
    # Average distance over ink pixels ≈ half the stroke width.
    return float(dist[ink_mask > 0].mean()) * 2.0


def _italic_angle(crop: np.ndarray) -> float:
    """Skew angle (degrees) of the ink in the crop using image moments.

    Positive = tilted to the right (typical italic). 0 = upright.
    """
    if crop.size == 0:
        return 0.0
    ink_mask = (crop < 128).astype(np.uint8)
    moments = cv2.moments(ink_mask, binaryImage=True)
    mu02 = moments.get("mu02", 0.0)
    mu11 = moments.get("mu11", 0.0)
    if mu02 < 1e-3:
        return 0.0
    skew = mu11 / mu02
    return math.degrees(math.atan(skew))


# ---------------------------------------------------------------------------
# Per-page calibration & emphasis flagging
# ---------------------------------------------------------------------------

@dataclass
class WordFormat:
    word: Word
    bold: bool = False
    italic: bool = False


def annotate_words(binary: np.ndarray, words: Sequence[Word]) -> list[WordFormat]:
    """Walk every word, measure stroke thickness + italic angle, and flag the
    outliers as bold / italic relative to the page baseline.
    """
    if not words:
        return []

    thickness, italic_deg = [], []
    for w in words:
        crop = _word_crop(binary, w)
        # Normalize thickness by the word's height so big titles don't look "thicker"
        # just because they're large.
        thick = _stroke_thickness(crop)
        norm_thick = thick / max(1.0, w.h)
        thickness.append(norm_thick)
        italic_deg.append(_italic_angle(crop))

    base_thick = median(thickness) if thickness else 0.0

    out: list[WordFormat] = []
    for w, thick, ang in zip(words, thickness, italic_deg):
        is_bold = thick > base_thick * 1.25 and thick > 0.03
        is_italic = ang > 7.0
        out.append(WordFormat(word=w, bold=is_bold, italic=is_italic))
    return out


# ---------------------------------------------------------------------------
# Lines, paragraphs, alignment
# ---------------------------------------------------------------------------

@dataclass
class Line:
    words: list[WordFormat]

    @property
    def left(self) -> int:
        return min(wf.word.x for wf in self.words)

    @property
    def right(self) -> int:
        return max(wf.word.right for wf in self.words)

    @property
    def top(self) -> int:
        return min(wf.word.y for wf in self.words)

    @property
    def bottom(self) -> int:
        return max(wf.word.bottom for wf in self.words)

    @property
    def height(self) -> int:
        return self.bottom - self.top

    @property
    def cx(self) -> float:
        return (self.left + self.right) / 2.0


@dataclass
class Paragraph:
    lines: list[Line]
    alignment: str = "left"  # one of: left, center, right
    block_num: int = 0
    par_num: int = 0
    text: str = field(default="", init=False)


def _group_words_into_lines(words: Sequence[WordFormat]) -> list[Line]:
    buckets: dict[tuple[int, int, int], list[WordFormat]] = {}
    for wf in words:
        key = (wf.word.block_num, wf.word.par_num, wf.word.line_num)
        buckets.setdefault(key, []).append(wf)

    lines: list[Line] = []
    for key in sorted(buckets.keys()):
        bucket = sorted(buckets[key], key=lambda wf: wf.word.x)
        lines.append(Line(words=bucket))
    lines.sort(key=lambda ln: (ln.words[0].word.block_num,
                               ln.words[0].word.par_num,
                               ln.top))
    return lines


def _classify_alignment(lines: list[Line], page_width: int) -> str:
    """Return ``left | center | right`` for a paragraph by looking at the first
    line's left margin and the line center relative to the page.
    """
    if not lines or page_width <= 0:
        return "left"

    centers = [ln.cx / page_width for ln in lines]
    left_norm = lines[0].left / page_width
    right_norm = lines[0].right / page_width

    avg_center = sum(centers) / len(centers)

    if 0.40 < avg_center < 0.60 and left_norm > 0.15 and (1 - right_norm) > 0.15:
        return "center"
    if (1 - right_norm) < 0.10 and left_norm > 0.30:
        return "right"
    return "left"


def build_paragraphs(
    word_formats: Sequence[WordFormat],
    page_width: int,
) -> list[Paragraph]:
    """Group lines into paragraphs (using Tesseract's par_num as the seed) and
    classify each paragraph's alignment from its line geometry.
    """
    if not word_formats:
        return []

    lines = _group_words_into_lines(word_formats)

    para_buckets: dict[tuple[int, int], list[Line]] = {}
    for ln in lines:
        key = (ln.words[0].word.block_num, ln.words[0].word.par_num)
        para_buckets.setdefault(key, []).append(ln)

    # Insert a paragraph break wherever the vertical gap between consecutive lines
    # in the same Tesseract paragraph is much larger than the median gap — Tesseract
    # sometimes lumps visually-distinct paragraphs together.
    paragraphs: list[Paragraph] = []
    for (block_num, par_num), bucket in sorted(para_buckets.items()):
        bucket.sort(key=lambda ln: ln.top)
        if len(bucket) <= 1:
            paragraphs.append(Paragraph(lines=bucket, block_num=block_num, par_num=par_num))
            continue

        gaps = [bucket[i + 1].top - bucket[i].bottom for i in range(len(bucket) - 1)]
        med_gap = median(gaps) if gaps else 0
        threshold = max(med_gap * 1.6, 8)

        current: list[Line] = [bucket[0]]
        for prev, ln, gap in zip(bucket, bucket[1:], gaps):
            if gap > threshold:
                paragraphs.append(Paragraph(lines=current, block_num=block_num, par_num=par_num))
                current = [ln]
            else:
                current.append(ln)
        paragraphs.append(Paragraph(lines=current, block_num=block_num, par_num=par_num))

    for p in paragraphs:
        p.alignment = _classify_alignment(p.lines, page_width)
        p.text = " ".join(wf.word.text for ln in p.lines for wf in ln.words)

    return paragraphs
