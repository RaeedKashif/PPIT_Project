"""Self-evaluation (slide 25 Evaluate, slide 28 Autonomy thresholds).

The agent must know how good its own output is. Without this signal, the
"ship vs retry vs escalate" decision is impossible.
"""

from __future__ import annotations

from . import Score
from .act import RunResult


_LOW_CONF_FLOOR = 60.0       # per-word Tesseract confidence below which a word is "low"


def score(run: RunResult) -> Score:
    """Aggregate confidence + structural integrity check.

    `aggregate_confidence` is normalized to 0..1 (Tesseract reports 0..100).
    `structural_ok` is a coarse sanity gate: produced at least one paragraph
    with at least one word.
    """
    if run.word_count == 0 or not run.word_confidences:
        return Score(
            aggregate_confidence=0.0,
            structural_ok=False,
            word_count=0,
            low_conf_word_count=0,
        )

    mean_conf = sum(run.word_confidences) / len(run.word_confidences)
    low = sum(1 for c in run.word_confidences if c < _LOW_CONF_FLOOR)
    structural_ok = bool(run.paragraphs) and run.word_count >= 3
    return Score(
        aggregate_confidence=mean_conf / 100.0,
        structural_ok=structural_ok,
        word_count=run.word_count,
        low_conf_word_count=low,
    )


def low_conf_words(run: RunResult, *, floor: float = _LOW_CONF_FLOOR) -> list[tuple[str, float]]:
    """Return (text, confidence) for every word below the floor — used by the
    audit page to highlight the parts the user should re-read."""
    out: list[tuple[str, float]] = []
    for para in run.paragraphs:
        for line in para.lines:
            for wf in line.words:
                if wf.word.conf < floor:
                    out.append((wf.word.text, wf.word.conf))
    return out
