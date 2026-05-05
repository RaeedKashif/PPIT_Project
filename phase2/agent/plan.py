"""Pipeline plan selector (slide 25).

Given the doc-type classification + memory presets, decide:
  * which preprocessing variant
  * which Tesseract --psm
  * whether to enable spell-check
  * whether to enable LLM repair (still gated downstream by HITL)

The function is pure: same inputs always produce the same plan. That makes
the agent's choices auditable.
"""

from __future__ import annotations

from typing import Any

from . import DocClassification, Goal, Plan


# Doc-type → default plan ingredients. Picked from the Tesseract guide:
#   --psm 3  fully automatic (default)
#   --psm 4  single column of text of variable sizes
#   --psm 6  single uniform block (good for forms/tables)
#   --psm 11 sparse text — find text in no particular order
_DOC_TYPE_DEFAULTS: dict[str, dict[str, Any]] = {
    "form":           {"preprocessor": "high_contrast",   "psm": 6},
    "letter":         {"preprocessor": "default",         "psm": 3},
    "academic_page":  {"preprocessor": "default",         "psm": 3},
    "receipt":        {"preprocessor": "denoise_heavy",   "psm": 4},
    "id_card":        {"preprocessor": "high_contrast",   "psm": 11},
    "unknown":        {"preprocessor": "default",         "psm": 3},
}


def pick_plan(
    classification: DocClassification,
    *,
    goal: Goal,
    preset: dict[str, Any] | None = None,
    attempt: int = 0,
) -> Plan:
    """Pick a plan for this attempt.

    `attempt`:
        0 = first try (use the doc-type default + any source preset).
        1 = retry alternative (escalate preprocessing or change psm).
    """
    base = dict(_DOC_TYPE_DEFAULTS.get(classification.label,
                                       _DOC_TYPE_DEFAULTS["unknown"]))

    # Memory preset overrides defaults (slide 27).
    if preset:
        for key in ("preprocessor", "psm", "lang"):
            if key in preset:
                base[key] = preset[key]

    notes = [
        f"doc_type={classification.label} ({classification.confidence:.2f})",
        f"attempt={attempt}",
    ]
    if preset:
        notes.append(f"applied source preset: {sorted(preset.keys())}")

    if attempt > 0:
        # Retry with alternative ingredients. Two concrete escalations:
        #   - denser preprocessing (default → high_contrast → denoise_heavy)
        #   - alternative psm — but per-doc-type, NOT a blind flip to psm=11.
        #     psm=11 ("sparse text") destroys body-text accuracy; we only use it
        #     for doc types that genuinely have sparse layout (forms, id_cards).
        if base["preprocessor"] == "default":
            base["preprocessor"] = "high_contrast"
        elif base["preprocessor"] == "high_contrast":
            base["preprocessor"] = "denoise_heavy"
        else:
            base["preprocessor"] = "default"

        if classification.label in ("letter", "academic_page", "unknown"):
            # body text: psm 3 ↔ psm 6 (single uniform block); never psm 11.
            base["psm"] = 6 if base["psm"] != 6 else 3
        elif classification.label == "receipt":
            base["psm"] = 6 if base["psm"] != 6 else 4
        else:
            # forms, id_cards: sparse modes are fair game.
            base["psm"] = 11 if base["psm"] != 11 else 6
        notes.append("escalated preprocessing + per-doc-type psm for retry")

    return Plan(
        preprocessor=base.get("preprocessor", "default"),
        psm=int(base.get("psm", 3)),
        lang=str(base.get("lang", "eng")),
        use_spell_check=True,
        use_llm_repair=False,        # always off unless caller upgrades the plan
        notes=notes,
    )
