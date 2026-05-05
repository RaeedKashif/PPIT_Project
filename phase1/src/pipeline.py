"""End-to-end pipeline: image path -> formatted .docx."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable

from .preprocess import load_image, preprocess
from .ocr import configure_tesseract, run_ocr
from .formatting import annotate_words, build_paragraphs, Paragraph
from .docx_writer import write_docx


ProgressFn = Callable[[str], None]


@dataclass
class ConversionResult:
    output_path: str
    paragraphs: list[Paragraph]
    deskew_deg: float
    word_count: int
    bold_count: int
    italic_count: int


def _noop(_msg: str) -> None:
    pass


def convert(
    input_path: str,
    output_path: str | None = None,
    *,
    progress: ProgressFn = _noop,
) -> ConversionResult:
    """Run the full pipeline. Returns metrics for the report / status pane."""
    if not os.path.isfile(input_path):
        raise FileNotFoundError(input_path)

    if configure_tesseract() is None:
        raise RuntimeError(
            "Tesseract executable not found. Install Tesseract or set "
            "the TESSERACT_CMD environment variable to the tesseract.exe path."
        )

    if output_path is None:
        base, _ = os.path.splitext(input_path)
        output_path = base + ".docx"

    progress("Loading image...")
    bgr = load_image(input_path)
    page_width = bgr.shape[1]

    progress("Preprocessing (deskew, threshold)...")
    pre = preprocess(bgr)

    progress("Running Tesseract OCR...")
    words = run_ocr(pre["gray"])
    if not words:
        raise RuntimeError("OCR produced no text. The image may be too noisy or blank.")

    progress(f"Analyzing formatting on {len(words)} words...")
    annotated = annotate_words(pre["binary"], words)

    progress("Building paragraphs and detecting alignment...")
    paragraphs = build_paragraphs(annotated, page_width=page_width)

    progress(f"Writing {output_path}...")
    write_docx(paragraphs, output_path)

    bold = sum(1 for wf in annotated if wf.bold)
    italic = sum(1 for wf in annotated if wf.italic)

    return ConversionResult(
        output_path=output_path,
        paragraphs=paragraphs,
        deskew_deg=pre["deskew_deg"],
        word_count=len(words),
        bold_count=bold,
        italic_count=italic,
    )
