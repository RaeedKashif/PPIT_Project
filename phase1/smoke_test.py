"""Sanity check for everything except the Tesseract call.

Synthesizes a 2-paragraph image with PIL, runs preprocess on it, hand-builds the
Word records that Tesseract would produce, then exercises annotate_words,
build_paragraphs, and write_docx. Verifies the resulting .docx opens.

Run with: python -m phase1.smoke_test
"""

from __future__ import annotations

import os
import tempfile

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .src.preprocess import preprocess
from .src.ocr import Word
from .src.formatting import annotate_words, build_paragraphs
from .src.docx_writer import write_docx


def _font(size: int, *, bold: bool = False, italic: bool = False) -> ImageFont.FreeTypeFont:
    candidates_regular = ["arial.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf"]
    candidates_bold = ["arialbd.ttf", "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf"]
    candidates_italic = ["ariali.ttf", "DejaVuSans-Oblique.ttf", "LiberationSans-Italic.ttf"]
    pool = candidates_bold if bold else candidates_italic if italic else candidates_regular
    for name in pool:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _synthesize_image(path: str) -> tuple[int, int]:
    W, H = 900, 500
    img = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(img)

    title_font = _font(36, bold=True)
    body_font = _font(22)
    italic_font = _font(22, italic=True)
    bold_font = _font(22, bold=True)

    # Centered bold title.
    title = "PHASE 1 SAMPLE"
    tw = draw.textlength(title, font=title_font)
    draw.text(((W - tw) / 2, 30), title, fill="black", font=title_font)

    # Left-aligned body with mixed emphasis.
    draw.text((40, 110), "This is a", fill="black", font=body_font)
    draw.text((180, 110), "bold", fill="black", font=bold_font)
    draw.text((260, 110), "sentence with one", fill="black", font=body_font)
    draw.text((500, 110), "italic", fill="black", font=italic_font)
    draw.text((590, 110), "word here.", fill="black", font=body_font)

    # Right-aligned signature.
    sig = "Signed, the Author"
    sw = draw.textlength(sig, font=body_font)
    draw.text((W - sw - 40, 360), sig, fill="black", font=body_font)

    img.save(path)
    return W, H


def _fake_words() -> list[Word]:
    """Same words the synthesized image carries — manually positioned."""
    return [
        # Centered bold title
        Word("PHASE", 320, 30, 90, 36, 1, 1, 1, 1, 95.0),
        Word("1",     420, 30, 18, 36, 1, 1, 1, 2, 95.0),
        Word("SAMPLE",450, 30, 130, 36, 1, 1, 1, 3, 95.0),
        # Left body
        Word("This",  40, 110, 60, 22, 1, 2, 1, 1, 95.0),
        Word("is",   105, 110, 22, 22, 1, 2, 1, 2, 95.0),
        Word("a",    130, 110, 14, 22, 1, 2, 1, 3, 95.0),
        Word("bold", 180, 110, 60, 22, 1, 2, 1, 4, 95.0),
        Word("sentence", 260, 110, 110, 22, 1, 2, 1, 5, 95.0),
        Word("with", 380, 110, 55, 22, 1, 2, 1, 6, 95.0),
        Word("one",  440, 110, 40, 22, 1, 2, 1, 7, 95.0),
        Word("italic",500, 110, 70, 22, 1, 2, 1, 8, 95.0),
        Word("word", 590, 110, 60, 22, 1, 2, 1, 9, 95.0),
        Word("here.",655, 110, 65, 22, 1, 2, 1, 10, 95.0),
        # Right signature
        Word("Signed,", 600, 360, 90, 22, 1, 3, 1, 1, 95.0),
        Word("the",     700, 360, 40, 22, 1, 3, 1, 2, 95.0),
        Word("Author",  745, 360, 95, 22, 1, 3, 1, 3, 95.0),
    ]


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        png = os.path.join(tmp, "sample.png")
        docx_out = os.path.join(tmp, "sample.docx")

        page_width, _ = _synthesize_image(png)
        bgr = cv2.imread(png, cv2.IMREAD_COLOR)
        pre = preprocess(bgr)
        print(f"preprocess ok, deskew={pre['deskew_deg']:.2f}, "
              f"binary shape={pre['binary'].shape}")

        words = _fake_words()
        annotated = annotate_words(pre["binary"], words)
        print(f"annotate_words ok: bold={sum(a.bold for a in annotated)}, "
              f"italic={sum(a.italic for a in annotated)}")

        paragraphs = build_paragraphs(annotated, page_width=page_width)
        print(f"build_paragraphs ok: {len(paragraphs)} paragraphs")
        for i, p in enumerate(paragraphs, 1):
            print(f"  para {i}: alignment={p.alignment}, text={p.text!r}")

        write_docx(paragraphs, docx_out)
        size = os.path.getsize(docx_out)
        print(f"write_docx ok: wrote {size} bytes")

        # Re-open the docx to confirm validity.
        from docx import Document
        doc = Document(docx_out)
        for i, p in enumerate(doc.paragraphs, 1):
            runs = [(r.text, bool(r.bold), bool(r.italic)) for r in p.runs]
            print(f"  docx para {i}: align={p.alignment}, runs={runs}")

        print("OK")


if __name__ == "__main__":
    main()
