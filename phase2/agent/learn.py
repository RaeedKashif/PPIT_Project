"""Learning layer (slide 25 Learn, slide 27 long-term memory).

After every job, persist what happened so future runs can do better:
  * spell-check / memory corrections that fired -> bump frequency for those rules
  * the chosen plan + score + final decision -> outcomes table
  * if the decision was "ship" with high confidence on this source, remember
    the preprocessing variant + psm as a per-source preset

Memory writes are no-ops when memory is disabled (consent off), so this stays
safe to call unconditionally.
"""

from __future__ import annotations

from dataclasses import asdict

from . import JobOutcome
from .memory import Memory


def record(outcome: JobOutcome, memory: Memory) -> None:
    """Persist an outcome into long-term memory (consent-gated inside Memory)."""
    plan_dict = asdict(outcome.plan)
    memory.record_outcome(
        job_id=outcome.job.job_id,
        source=outcome.job.source,
        plan=plan_dict,
        score=outcome.score.aggregate_confidence,
        decision=outcome.decision.action,
    )

    # If we shipped confidently, learn the plan as a per-source preset.
    if (outcome.decision.action == "ship"
            and outcome.score.aggregate_confidence >= 0.90):
        memory.set_preset(
            outcome.job.source,
            {
                "preprocessor": outcome.plan.preprocessor,
                "psm": outcome.plan.psm,
                "lang": outcome.plan.lang,
            },
        )


def remember_correction(
    memory: Memory, source: str, original: str, corrected: str,
) -> None:
    """Surface for the HITL channel: when a user manually accepts a fix, the
    UI calls this so the rule's frequency goes up."""
    memory.record_correction(source, original, corrected)
