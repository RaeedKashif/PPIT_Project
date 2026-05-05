"""Action layer — execute the picked plan (slide 25 Act).

This is where the agent actually does work. It dispatches to the registered
tools and to the Phase 1 pipeline (Phase 1 is the *Action* layer of the
agent, per the Comparative Analysis table at the end of `Phase2_Document.md`).

Output: a `RunResult` carrying everything the Evaluate stage needs to score.
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any

import cv2

# Make the Phase 1 package importable regardless of where the agent is run from.
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(_HERE))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from phase1.src.preprocess import _deskew  # type: ignore
from phase1.src.ocr import configure_tesseract, run_ocr  # type: ignore
from phase1.src.formatting import annotate_words, build_paragraphs  # type: ignore
from phase1.src.docx_writer import write_docx  # type: ignore

from . import Job, Plan
from .tools import ToolRegistry, deterministic_spell_check


@dataclass
class RunResult:
    paragraphs: list                            # phase1.src.formatting.Paragraph
    word_confidences: list[float]
    word_count: int
    bold_count: int
    italic_count: int
    deskew_deg: float
    docx_path: str
    applied_corrections: list[tuple[str, str]] = field(default_factory=list)
    llm_suggestions: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


def execute_plan(
    job: Job,
    plan: Plan,
    *,
    output_dir: str,
    registry: ToolRegistry,
    corrections_from_memory: dict[str, str] | None = None,
) -> RunResult:
    """Run the chosen plan end-to-end and return a RunResult."""
    if configure_tesseract() is None:
        raise RuntimeError(
            "Tesseract executable not found. Install Tesseract or set "
            "TESSERACT_CMD."
        )

    tool_calls: list[dict[str, Any]] = []

    # --- 1. preprocess (variant chosen by the planner) ---------------------
    bgr = cv2.imread(job.image_path, cv2.IMREAD_COLOR)
    if bgr is None:
        raise FileNotFoundError(f"Could not read image: {job.image_path}")

    # Upscale small / low-res phone photos before OCR. Tesseract wants ~30 px
    # tall characters; WhatsApp re-encodes hand it 12-15 px. A 2x lanczos
    # upscale typically adds 10-20 confidence points on phone snapshots.
    if max(bgr.shape[:2]) < 1500:
        bgr = cv2.resize(bgr, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_LANCZOS4)
        tool_calls.append({"tool": "upscale_2x", "reason": "image < 1500 px"})

    page_width = bgr.shape[1]

    pp_tool = registry.get(f"preprocess_{plan.preprocessor}")
    if pp_tool is None:
        pp_tool = registry.get("preprocess_default")
    t0 = time.time()
    gray = pp_tool.fn(bgr)  # type: ignore[union-attr]
    tool_calls.append({"tool": pp_tool.name, "duration_ms": int((time.time() - t0) * 1000)})  # type: ignore[union-attr]

    # Deskew lives in Phase 1 — apply unconditionally (the bug fix in Phase 1
    # already caps it to 15° so this is safe for sparse pages).
    gray, deskew_deg = _deskew(gray)

    binary = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, 31, 15,
    )

    # --- 2. OCR with the chosen psm ---------------------------------------
    t0 = time.time()
    words = run_ocr(gray, psm=plan.psm)
    tool_calls.append({
        "tool": "tesseract",
        "psm": plan.psm,
        "lang": plan.lang,
        "n_words": len(words),
        "duration_ms": int((time.time() - t0) * 1000),
    })
    if not words:
        # Empty OCR is a real signal — let evaluate/decide handle it (no exception).
        return RunResult(
            paragraphs=[], word_confidences=[], word_count=0,
            bold_count=0, italic_count=0, deskew_deg=deskew_deg,
            docx_path="", tool_calls=tool_calls,
        )

    # --- 3. spell-check (deterministic; tier 1) ---------------------------
    applied_corrections: list[tuple[str, str]] = []
    word_texts = [w.text for w in words]

    if plan.use_spell_check:
        suggestions = deterministic_spell_check(word_texts)
        for idx, original, suggested in suggestions:
            words[idx].text = suggested
            applied_corrections.append((original, suggested))
        tool_calls.append({
            "tool": "deterministic_spell_check",
            "applied": len(applied_corrections),
        })

    # Memory-derived per-source corrections (slide 27).
    if corrections_from_memory:
        for w in words:
            replacement = corrections_from_memory.get(w.text)
            if replacement and replacement != w.text:
                applied_corrections.append((w.text, replacement))
                w.text = replacement
        tool_calls.append({
            "tool": "memory_corrections",
            "available": len(corrections_from_memory),
        })

    # --- 4. LLM repair (opt-in; surfaces suggestions only — never auto-applied)
    llm_suggestions: list[dict[str, Any]] = []
    if plan.use_llm_repair:
        llm_tool = registry.get("llm_repair")
        if llm_tool and llm_tool.enabled:
            for w in words:
                if w.conf < 60:
                    suggested = llm_tool.fn(w.text)
                    if suggested and suggested != w.text:
                        llm_suggestions.append({
                            "original": w.text, "suggested": suggested,
                            "confidence": w.conf, "status": "pending_user_approval",
                        })
            tool_calls.append({
                "tool": "llm_repair",
                "n_suggestions": len(llm_suggestions),
                "auto_applied": 0,  # never auto-applied — slide 10 step-4 decision
            })

    # --- 5. formatting + docx ---------------------------------------------
    annotated = annotate_words(binary, words)

    # The stroke-thickness / italic-angle heuristics still vote on misread
    # words, producing wrong bold/italic flags that make the .docx look
    # worse than it is. Suppress emphasis on anything below the per-word
    # confidence floor — if we don't trust the text, don't trust its style.
    _CONF_FLOOR = 60.0
    for wf in annotated:
        if wf.word.conf < _CONF_FLOOR:
            wf.bold = False
            wf.italic = False

    paragraphs = build_paragraphs(annotated, page_width=page_width)

    out_name = os.path.splitext(os.path.basename(job.image_path))[0] + ".docx"
    docx_path = os.path.join(output_dir, out_name)
    os.makedirs(output_dir, exist_ok=True)
    write_docx(paragraphs, docx_path)

    bold = sum(1 for wf in annotated if wf.bold)
    italic = sum(1 for wf in annotated if wf.italic)

    return RunResult(
        paragraphs=paragraphs,
        word_confidences=[w.conf for w in words],
        word_count=len(words),
        bold_count=bold,
        italic_count=italic,
        deskew_deg=deskew_deg,
        docx_path=docx_path,
        applied_corrections=applied_corrections,
        llm_suggestions=llm_suggestions,
        tool_calls=tool_calls,
    )
