"""DocAgent — agentic transformation of the Phase 1 Image-to-Word converter.

This package implements the Perceive -> Interpret -> Plan -> Act -> Evaluate
-> Decide -> Learn loop described in `phase2/Phase2_Document.md` (slides 19-32).
Each stage lives in its own module so the architecture diagram on slide 23
maps 1:1 to the code.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


DocType = str  # one of: form | letter | academic_page | receipt | id_card | unknown


@dataclass
class Goal:
    """Explicit, declarative goal (slide 21)."""
    quality_threshold: float = 0.85       # ship if aggregate confidence >= this
    retry_threshold: float = 0.60         # below this, escalate immediately
    max_retries: int = 1                  # how many alternative plans to try
    high_stakes_doc_types: tuple = ("id_card",)  # always escalate these


@dataclass
class Job:
    """A single unit of work emitted by the perceive layer."""
    image_path: str
    source: str                                       # e.g. "inbox/"
    job_id: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H-%M-%S")
                                              + "_" + uuid.uuid4().hex[:6])
    discovered_at: float = field(default_factory=time.time)


@dataclass
class DocClassification:
    """Output of the interpret stage."""
    label: DocType
    confidence: float
    quality_estimate: float       # rough estimate of how clean the scan looks (0..1)
    reasons: list[str] = field(default_factory=list)


@dataclass
class Plan:
    """The picked pipeline strategy (slide 25)."""
    preprocessor: str = "default"   # "default" | "high_contrast" | "denoise_heavy"
    psm: int = 3                    # Tesseract --psm
    lang: str = "eng"
    use_spell_check: bool = True
    use_llm_repair: bool = False    # opt-in only
    notes: list[str] = field(default_factory=list)


@dataclass
class Score:
    """Output of the evaluate stage."""
    aggregate_confidence: float     # mean per-word confidence, normalized 0..1
    structural_ok: bool             # did we produce >= 1 paragraph with text
    word_count: int
    low_conf_word_count: int        # words below the per-word floor


@dataclass
class Decision:
    """Output of the decide stage."""
    action: str                     # "ship" | "retry" | "escalate"
    reason: str


@dataclass
class JobOutcome:
    """Final record persisted by the learn stage."""
    job: Job
    classification: DocClassification
    plan: Plan
    score: Score
    decision: Decision
    output_path: str | None         # outbox path on ship; holding path on escalate
    duration_ms: int
    tool_calls: list[dict[str, Any]]


__all__ = [
    "DocType",
    "Goal",
    "Job",
    "DocClassification",
    "Plan",
    "Score",
    "Decision",
    "JobOutcome",
]
