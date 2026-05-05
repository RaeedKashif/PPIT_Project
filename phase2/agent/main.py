"""DocAgent — orchestrator entry point.

Wires the Perceive → Interpret → Plan → Act → Evaluate → Decide → Learn
loop (slide 23, slide 25). Run as:

    python -m phase2.agent.main --watch                # watch inbox/, run forever
    python -m phase2.agent.main --once                 # one-pass, then exit
    python -m phase2.agent.main --memory               # turn memory on (consent)
    python -m phase2.agent.main --forget <source>      # right-of-erasure
    python -m phase2.agent.main --purge                # wipe all memory
    python -m phase2.agent.main --memory-summary       # weekly review surface

Every long-form decision rationale lives in ../Phase2_Document.md. This file
is the executable side of those design decisions.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import time

# Windows consoles default to cp1252 and choke on en-dashes/arrows in our
# log strings. Force UTF-8 so the agent output is always readable.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass

# Allow `python phase2/agent/main.py` (script-style) AND
# `python -m phase2.agent.main` (module-style) to both import correctly.
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(_HERE))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from phase2.agent import Decision, Goal, Job, JobOutcome, Plan, Score  # noqa: E402
from phase2.agent.act import execute_plan  # noqa: E402
from phase2.agent.audit import AuditLogger, append_audit_page  # noqa: E402
from phase2.agent.decide import decide  # noqa: E402
from phase2.agent.evaluate import score, low_conf_words  # noqa: E402
from phase2.agent.interpret import classify_doc  # noqa: E402
from phase2.agent.learn import record  # noqa: E402
from phase2.agent.memory import Memory, MemoryConfig  # noqa: E402
from phase2.agent.perceive import FolderWatcher  # noqa: E402
from phase2.agent.plan import pick_plan  # noqa: E402
from phase2.agent.tools import default_registry  # noqa: E402

import cv2  # noqa: E402


_PHASE2_ROOT = os.path.dirname(_HERE)
INBOX = os.path.join(_PHASE2_ROOT, "inbox")
OUTBOX = os.path.join(_PHASE2_ROOT, "outbox")
HOLDING = os.path.join(_PHASE2_ROOT, "holding")
AUDIT = os.path.join(_PHASE2_ROOT, "audit")


CONSENT_BANNER = """\
DocAgent — Memory consent
-------------------------
Memory stores per-source preprocessing presets and the corrections you
approve. It NEVER stores raw OCR text or image bytes. Records auto-purge
after 30 days. You can call --forget <source> or --purge at any time.

Continue with memory ENABLED for this run? (y/N): """


def _load_image_safely(path: str):
    img = cv2.imread(path, cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(f"Could not read image: {path}")
    return img


def _process_one(
    job: Job,
    *,
    goal: Goal,
    memory: Memory,
    audit_logger: AuditLogger,
    log: callable = print,
) -> JobOutcome:
    """Run the full loop for one Job."""
    started = time.time()
    log(f"[perceive ] new job: {job.image_path}")

    bgr = _load_image_safely(job.image_path)
    classification = classify_doc(bgr)
    log(f"[interpret] doc_type={classification.label} "
        f"({classification.confidence:.2f}) — {'; '.join(classification.reasons)}")

    registry = default_registry()
    preset = memory.get_preset(job.source)
    corrections = memory.lookup_corrections(job.source)

    attempt = 0
    last_run = None
    last_score: Score | None = None
    last_plan: Plan | None = None
    last_decision: Decision | None = None

    # High-stakes doc-types short-circuit: never OCR a CNIC without consent
    # (slide 28 last bullet, slide 29 channel #2). We pick a notional plan for
    # the audit log but never call act() on it.
    if classification.label in goal.high_stakes_doc_types:
        last_plan = pick_plan(classification, goal=goal, preset=preset, attempt=0)
        last_score = Score(aggregate_confidence=0.0, structural_ok=False,
                           word_count=0, low_conf_word_count=0)
        last_decision = Decision(
            action="escalate",
            reason=f"high-stakes document type ({classification.label}) "
                   f"detected before any OCR was run; awaiting user consent.",
        )
        log(f"[plan     ] (skipped — high-stakes type)")
        log(f"[decide   ] {last_decision.action} — {last_decision.reason}")
    else:
      while True:
        plan = pick_plan(classification, goal=goal, preset=preset, attempt=attempt)
        log(f"[plan     ] attempt={attempt} preprocessor={plan.preprocessor} "
            f"psm={plan.psm} llm_repair={plan.use_llm_repair}")

        run = execute_plan(
            job, plan,
            output_dir=OUTBOX,
            registry=registry,
            corrections_from_memory=corrections,
        )
        s = score(run)
        log(f"[evaluate ] aggregate_confidence={s.aggregate_confidence:.2f} "
            f"structural_ok={s.structural_ok} words={s.word_count} "
            f"low_conf={s.low_conf_word_count}")

        decision_obj = decide(s, goal=goal, classification=classification, attempt=attempt)
        log(f"[decide   ] {decision_obj.action} — {decision_obj.reason}")

        last_run = run
        last_score = s
        last_plan = plan
        last_decision = decision_obj

        if decision_obj.action != "retry":
            break
        attempt += 1
        if attempt > goal.max_retries:
            break
    # end of normal-path loop

    # Materialize the decision: ship | escalate.
    output_path: str | None = None
    if last_decision and last_decision.action == "ship" and last_run and last_run.docx_path:
        # Append the audit page to the produced .docx (slide 32).
        append_audit_page(
            last_run.docx_path,
            job_id=job.job_id,
            doc_type=classification.label,
            plan_summary={
                "preprocessor": last_plan.preprocessor,
                "psm": last_plan.psm,
                "lang": last_plan.lang,
                "use_spell_check": last_plan.use_spell_check,
                "use_llm_repair": last_plan.use_llm_repair,
            },
            aggregate_confidence=last_score.aggregate_confidence,
            word_count=last_score.word_count,
            low_conf_words=low_conf_words(last_run),
            fired_rules=[f"{o} -> {c}" for o, c in last_run.applied_corrections],
            llm_suggestions=last_run.llm_suggestions,
        )
        output_path = last_run.docx_path
        log(f"[ship     ] -> {output_path}")
    else:
        # Escalate: move source image to holding/ + write a sibling audit note.
        os.makedirs(HOLDING, exist_ok=True)
        held_path = os.path.join(HOLDING, os.path.basename(job.image_path))
        if not os.path.exists(held_path):
            shutil.copy2(job.image_path, held_path)
        # If the run produced a docx, move it next to the held image so a human
        # can compare side-by-side.
        if last_run and last_run.docx_path and os.path.isfile(last_run.docx_path):
            held_doc = os.path.join(HOLDING, os.path.basename(last_run.docx_path))
            shutil.move(last_run.docx_path, held_doc)
            output_path = held_doc
        else:
            output_path = held_path
        log(f"[escalate ] -> {held_path} (audit JSON in {AUDIT}/)")

    outcome = JobOutcome(
        job=job, classification=classification,
        plan=last_plan,
        score=last_score,
        decision=last_decision,
        output_path=output_path,
        duration_ms=int((time.time() - started) * 1000),
        tool_calls=last_run.tool_calls if last_run else [],
    )

    # Audit log (always on; PII scrubbed inside writer).
    audit_logger.write({
        "job_id": job.job_id,
        "source": job.source,
        "input_path": job.image_path,
        "doc_type": {
            "label": classification.label,
            "confidence": classification.confidence,
            "reasons": classification.reasons,
        },
        "plan": {
            "preprocessor": last_plan.preprocessor,
            "psm": last_plan.psm,
            "lang": last_plan.lang,
        },
        "tool_calls": outcome.tool_calls,
        "evaluate": {
            "aggregate_confidence": outcome.score.aggregate_confidence,
            "structural_ok": outcome.score.structural_ok,
            "word_count": outcome.score.word_count,
            "low_conf_word_count": outcome.score.low_conf_word_count,
        },
        "decision": {
            "action": last_decision.action,
            "reason": last_decision.reason,
        },
        "output_path": output_path,
        "duration_ms": outcome.duration_ms,
    })

    # Learning step.
    record(outcome, memory)
    return outcome


def _consent_prompt() -> bool:
    try:
        ans = input(CONSENT_BANNER).strip().lower()
    except EOFError:
        return False
    return ans in ("y", "yes")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="docagent",
                                     description="DocAgent orchestrator (Phase 2).")
    parser.add_argument("--watch", action="store_true",
                        help="watch inbox/ and run forever")
    parser.add_argument("--once", action="store_true",
                        help="process whatever is in inbox/ right now and exit")
    parser.add_argument("--memory", action="store_true",
                        help="enable memory for this run (will prompt for consent)")
    parser.add_argument("--forget", metavar="SOURCE",
                        help="forget everything DocAgent learned about SOURCE")
    parser.add_argument("--purge", action="store_true",
                        help="wipe all memory (corrections + presets + outcomes)")
    parser.add_argument("--memory-summary", action="store_true",
                        help="print a one-shot summary (the weekly review channel)")
    parser.add_argument("--ship-threshold", type=float, default=0.85)
    parser.add_argument("--retry-threshold", type=float, default=0.60)
    args = parser.parse_args(argv)

    for d in (INBOX, OUTBOX, HOLDING, AUDIT):
        os.makedirs(d, exist_ok=True)

    # Lifecycle commands first.
    mem = Memory(MemoryConfig(enabled=False))
    if args.purge:
        mem = Memory(MemoryConfig(enabled=True))
        mem.purge_all()
        print("memory purged.")
        return 0
    if args.forget:
        mem = Memory(MemoryConfig(enabled=True))
        n = mem.forget(args.forget)
        print(f"forgot {n} record(s) for source={args.forget!r}.")
        return 0
    if args.memory_summary:
        mem = Memory(MemoryConfig(enabled=True))
        import json
        print(json.dumps(mem.summary(), indent=2))
        return 0

    if args.memory:
        if _consent_prompt():
            mem.enable()
            print("memory: ENABLED (auto-purge after 30 days).")
        else:
            print("memory: declined; running stateless.")

    goal = Goal(
        quality_threshold=args.ship_threshold,
        retry_threshold=args.retry_threshold,
    )
    audit_logger = AuditLogger(AUDIT)

    watcher = FolderWatcher(INBOX)

    if args.once or (not args.watch and not args.once):
        # Default behaviour without flags: a single pass, like batch mode.
        jobs = watcher.discover_new()
        if not jobs:
            print(f"inbox/ is empty: drop scans into {INBOX} and re-run.")
            return 0
        for j in jobs:
            try:
                _process_one(j, goal=goal, memory=mem, audit_logger=audit_logger)
            except Exception as exc:  # broad on purpose: agent must not crash on one bad job
                print(f"[error    ] {j.image_path}: {exc}", file=sys.stderr)
        return 0

    # --watch
    print(f"DocAgent watching {INBOX} (Ctrl-C to stop)...")

    def _on_job(j: Job) -> None:
        try:
            _process_one(j, goal=goal, memory=mem, audit_logger=audit_logger)
        except Exception as exc:
            print(f"[error    ] {j.image_path}: {exc}", file=sys.stderr)

    try:
        watcher.watch(_on_job)
    except KeyboardInterrupt:
        watcher.stop()
        print("\nDocAgent stopped (kill switch).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
