"""Tesseract OCR wrapper. Returns a flat list of word-records."""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pytesseract
from pytesseract import Output


@dataclass
class Word:
    text: str
    x: int
    y: int
    w: int
    h: int
    block_num: int
    par_num: int
    line_num: int
    word_num: int
    conf: float

    @property
    def right(self) -> int:
        return self.x + self.w

    @property
    def bottom(self) -> int:
        return self.y + self.h

    @property
    def cx(self) -> float:
        return self.x + self.w / 2.0


def configure_tesseract() -> str | None:
    """Locate tesseract.exe on Windows or honor an env override.

    Order of resolution:
      1. ``TESSERACT_CMD`` environment variable.
      2. ``tesseract`` on PATH.
      3. Common Windows install location (Program Files).
    Returns the resolved path, or ``None`` if Tesseract was not found
    (callers should surface a friendly error in that case).
    """
    override = os.environ.get("TESSERACT_CMD")
    if override and os.path.isfile(override):
        pytesseract.pytesseract.tesseract_cmd = override
        return override

    on_path = shutil.which("tesseract")
    if on_path:
        pytesseract.pytesseract.tesseract_cmd = on_path
        return on_path

    # When running as a PyInstaller bundle, check for bundled Tesseract-OCR folder
    # placed next to the executable.
    if getattr(sys, "frozen", False):
        bundled = os.path.join(os.path.dirname(sys.executable), "Tesseract-OCR", "tesseract.exe")
        if os.path.isfile(bundled):
            pytesseract.pytesseract.tesseract_cmd = bundled
            return bundled

    fallback = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    if os.path.isfile(fallback):
        pytesseract.pytesseract.tesseract_cmd = fallback
        return fallback

    return None


def run_ocr(gray_image: np.ndarray, *, psm: int = 3, min_conf: int = 30) -> list[Word]:
    """Run Tesseract in TSV mode and return only words above ``min_conf``."""
    configure_tesseract()

    config = f"--oem 3 --psm {psm}"
    data = pytesseract.image_to_data(
        gray_image,
        output_type=Output.DICT,
        config=config,
    )

    words: list[Word] = []
    n = len(data["text"])
    for i in range(n):
        text = (data["text"][i] or "").strip()
        if not text:
            continue
        try:
            conf = float(data["conf"][i])
        except (TypeError, ValueError):
            conf = -1.0
        if conf < min_conf:
            continue

        words.append(Word(
            text=text,
            x=int(data["left"][i]),
            y=int(data["top"][i]),
            w=int(data["width"][i]),
            h=int(data["height"][i]),
            block_num=int(data["block_num"][i]),
            par_num=int(data["par_num"][i]),
            line_num=int(data["line_num"][i]),
            word_num=int(data["word_num"][i]),
            conf=conf,
        ))
    return words


def group_into_lines(words: Iterable[Word]) -> list[list[Word]]:
    """Group words by ``(block_num, par_num, line_num)``, sorted left-to-right."""
    buckets: dict[tuple[int, int, int], list[Word]] = {}
    for w in words:
        buckets.setdefault((w.block_num, w.par_num, w.line_num), []).append(w)

    lines = list(buckets.values())
    for line in lines:
        line.sort(key=lambda w: w.x)
    lines.sort(key=lambda line: (line[0].block_num, line[0].par_num, line[0].line_num, line[0].y))
    return lines
