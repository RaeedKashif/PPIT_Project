"""Decision policy (slide 25 Decide, slide 28 Autonomy levels).

Maps a Score + Goal to one of: ship | retry | escalate.

The thresholds in `Goal` (default 0.85 / 0.60) are the operational definition
of semi-autonomy. They are intentionally explicit and conservative: silently
shipping a low-confidence document is the failure mode we want to avoid
(slide 8 Deontology, slide 31 first risk row).
"""

from __future__ import annotations

from . import DocClassification, Decision, Goal, Score


def decide(
    score: Score,
    *,
    goal: Goal,
    classification: DocClassification,
    attempt: int,
) -> Decision:
    # High-stakes doc-types short-circuit to escalate regardless of confidence
    # (slide 28 last bullet, slide 29 channel #2).
    if classification.label in goal.high_stakes_doc_types:
        return Decision(
            action="escalate",
            reason=f"high-stakes document type ({classification.label}); "
                   f"requires human review before shipping.",
        )

    if not score.structural_ok:
        if attempt < goal.max_retries:
            return Decision(
                action="retry",
                reason="structural integrity check failed (no paragraphs / "
                       "too few words); trying alternative plan.",
            )
        return Decision(
            action="escalate",
            reason="structural integrity check failed after all retries.",
        )

    if score.aggregate_confidence >= goal.quality_threshold:
        return Decision(
            action="ship",
            reason=f"aggregate confidence {score.aggregate_confidence:.2f} "
                   f">= ship threshold {goal.quality_threshold:.2f}.",
        )

    if score.aggregate_confidence >= goal.retry_threshold and attempt < goal.max_retries:
        return Decision(
            action="retry",
            reason=f"aggregate confidence {score.aggregate_confidence:.2f} "
                   f"in retry band [{goal.retry_threshold:.2f}, "
                   f"{goal.quality_threshold:.2f}); attempting alternative plan.",
        )

    return Decision(
        action="escalate",
        reason=f"aggregate confidence {score.aggregate_confidence:.2f} "
               f"below ship threshold and retries exhausted; sending to holding/.",
    )
