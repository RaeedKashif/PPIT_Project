"""End-to-end smoke test for DocAgent.

Synthesizes a page image, drops it into a temp inbox, runs the agent
once, and verifies that:
  * the doc-type classifier returns a label
  * the run produces a .docx in outbox/ (or correctly escalates)
  * an audit JSON was written
  * the audit page was appended to the .docx
  * the memory store, when enabled, accepts a correction and the right-of-
    erasure call wipes it cleanly

This test does NOT need Tesseract for the per-stage assertions; it does
need Tesseract for the full-pipeline assertion. If Tesseract is missing
we mark the pipeline assertion SKIPPED but still verify everything else.

Run with:
    python -m phase2.agent.smoke_test
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile

# Windows consoles default to cp1252 and choke on en-dashes/arrows in the
# reason strings the agent prints. Force UTF-8 so the test output is readable.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass

# Ensure the repo root is on sys.path so `phase1.*` and `phase2.*` resolve.
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(_HERE))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

import cv2  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from phase2.agent import Goal, Job  # noqa: E402
from phase2.agent.audit import AuditLogger, scrub_pii  # noqa: E402
from phase2.agent.interpret import classify_doc  # noqa: E402
from phase2.agent.memory import Memory, MemoryConfig  # noqa: E402
from phase2.agent.perceive import FolderWatcher  # noqa: E402
from phase2.agent.plan import pick_plan  # noqa: E402


def _font(size: int):
    for name in ("arial.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _synth_letter(path: str) -> None:
    W, H = 900, 1100
    img = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(img)
    body = _font(24)
    title = _font(36)

    draw.text((40, 60), "MEMO", fill="black", font=title)
    text_lines = [
        "Dear Reader,",
        "",
        "This is a synthetic page used by the DocAgent smoke test.",
        "It contains a few short paragraphs so the OCR pipeline has",
        "real content to chew on.",
        "",
        "Sincerely,",
        "DocAgent",
    ]
    y = 140
    for line in text_lines:
        draw.text((40, y), line, fill="black", font=body)
        y += 36
    img.save(path)


def _synth_id_card(path: str) -> None:
    """Card-shaped image — should be detected as id_card and escalated."""
    W, H = 1000, 630   # ~1.58 aspect ratio, CR80 standard
    img = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(img)
    body = _font(28)
    draw.rectangle((20, 20, W - 20, H - 20), outline="black", width=4)
    draw.text((40, 40), "REPUBLIC OF EXAMPLE", fill="black", font=body)
    draw.text((40, 120), "Name: J. Doe", fill="black", font=body)
    draw.text((40, 170), "ID: 12345-1234567-1", fill="black", font=body)
    img.save(path)


# --- assertion helpers ----------------------------------------------------

def assert_eq(actual, expected, label):
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")
    print(f"  OK  {label}")


def assert_true(cond, label):
    if not cond:
        raise AssertionError(f"{label}: expected truthy, got {cond!r}")
    print(f"  OK  {label}")


def main() -> None:
    print("== smoke 1: pure stages (no Tesseract required) ==")

    with tempfile.TemporaryDirectory() as tmp:
        # 1. classifier on a portrait letter
        letter_png = os.path.join(tmp, "letter.png")
        _synth_letter(letter_png)
        bgr = cv2.imread(letter_png, cv2.IMREAD_COLOR)
        c = classify_doc(bgr)
        print(f"  letter classified as {c.label} ({c.confidence:.2f}) -- {c.reasons}")
        assert_true(c.label in ("letter", "academic_page", "unknown"),
                    "classifier returns a sensible label for a letter")

        # 2. classifier on a card-shaped image
        card_png = os.path.join(tmp, "card.png")
        _synth_id_card(card_png)
        bgr2 = cv2.imread(card_png, cv2.IMREAD_COLOR)
        c2 = classify_doc(bgr2)
        print(f"  card classified as {c2.label} ({c2.confidence:.2f}) -- {c2.reasons}")
        assert_eq(c2.label, "id_card", "ID-card layout is detected before OCR")

        # 3. plan picks the high-stakes default
        plan = pick_plan(c2, goal=Goal())
        assert_eq(plan.preprocessor, "high_contrast", "id_card -> high_contrast preset")
        assert_eq(plan.psm, 11, "id_card -> psm 11 (sparse)")

        # 4. PII scrubbing
        scrubbed = scrub_pii("CNIC 12345-1234567-1 sent to user@example.com on 2026-05-01")
        assert_true("[CNIC]" in scrubbed and "[EMAIL]" in scrubbed and "[DATE]" in scrubbed,
                    "scrub_pii masks CNIC, email, date")

        # 5. perceive: drop a file in inbox/, expect a Job event
        inbox = os.path.join(tmp, "inbox")
        os.makedirs(inbox)
        watcher = FolderWatcher(inbox, poll_interval_s=0.1)
        shutil.copy(letter_png, os.path.join(inbox, "letter.png"))
        jobs = watcher.discover_new()
        assert_eq(len(jobs), 1, "watcher discovers the new file")
        assert_true(isinstance(jobs[0], Job), "emits a Job dataclass")

        # second poll: file already seen, no new job
        assert_eq(len(watcher.discover_new()), 0, "second poll: no duplicate jobs")

        # 6. memory: enable, write, lookup, forget, purge
        mem = Memory(MemoryConfig(enabled=True,
                                  db_path=os.path.join(tmp, "mem.sqlite"),
                                  presets_path=os.path.join(tmp, "pre.json")))
        # frequency 1 — should NOT yet be promoted to a rule (poison-resistance)
        mem.record_correction("inbox/", "rn", "m")
        assert_eq(mem.lookup_corrections("inbox/", min_frequency=2), {},
                  "single correction does not become a rule")
        # bump it: now it should appear
        mem.record_correction("inbox/", "rn", "m")
        looked = mem.lookup_corrections("inbox/", min_frequency=2)
        assert_eq(looked, {"rn": "m"}, "frequency >= 2 promotes the rule")

        mem.set_preset("inbox/", {"preprocessor": "high_contrast", "psm": 6})
        assert_eq(mem.get_preset("inbox/")["psm"], 6, "preset round-trip")

        mem.forget("inbox/")
        assert_eq(mem.lookup_corrections("inbox/", min_frequency=2), {},
                  "forget(source) wipes corrections")
        mem.purge_all()
        # Windows holds the sqlite file handle until we explicitly close.
        mem.disable()
        print("  OK  memory purge runs without error")

        # 7. audit logger writes JSON
        audit_dir = os.path.join(tmp, "audit")
        logger = AuditLogger(audit_dir)
        path = logger.write({
            "job_id": "smoke-1", "source": "inbox/",
            "decision": {"action": "ship"},
        })
        assert_true(os.path.isfile(path), "audit JSON file exists")
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
        assert_eq(obj["job_id"], "smoke-1", "audit JSON round-trips")

    print("\n== smoke 2: full pipeline (requires Tesseract) ==")

    # Defer importing main to avoid loading Phase 1 if user just wants stage tests
    from phase2.agent.act import execute_plan
    from phase2.agent.evaluate import score
    from phase2.agent.tools import default_registry
    from phase1.src.ocr import configure_tesseract

    if configure_tesseract() is None:
        print("  SKIPPED: Tesseract not found on this machine.")
        print("\nALL SMOKE CHECKS PASSED")
        return

    with tempfile.TemporaryDirectory() as tmp:
        in_dir = os.path.join(tmp, "inbox")
        out_dir = os.path.join(tmp, "outbox")
        os.makedirs(in_dir)
        letter_png = os.path.join(in_dir, "letter.png")
        _synth_letter(letter_png)

        bgr = cv2.imread(letter_png, cv2.IMREAD_COLOR)
        c = classify_doc(bgr)
        plan = pick_plan(c, goal=Goal())
        job = Job(image_path=letter_png, source=in_dir)
        run = execute_plan(job, plan, output_dir=out_dir, registry=default_registry())

        s = score(run)
        print(f"  pipeline produced {run.word_count} words, "
              f"agg_conf={s.aggregate_confidence:.2f}, "
              f"docx={os.path.basename(run.docx_path)}")
        assert_true(run.word_count > 0, "OCR produced words")
        assert_true(os.path.isfile(run.docx_path), ".docx file exists")
        assert_true(os.path.getsize(run.docx_path) > 1000, ".docx is non-trivial")

        # Append the audit page; verify it grows the file.
        from phase2.agent.audit import append_audit_page
        from phase2.agent.evaluate import low_conf_words
        before = os.path.getsize(run.docx_path)
        append_audit_page(
            run.docx_path,
            job_id=job.job_id,
            doc_type=c.label,
            plan_summary={"preprocessor": plan.preprocessor, "psm": plan.psm,
                          "lang": plan.lang, "use_spell_check": plan.use_spell_check,
                          "use_llm_repair": plan.use_llm_repair},
            aggregate_confidence=s.aggregate_confidence,
            word_count=s.word_count,
            low_conf_words=low_conf_words(run),
            fired_rules=[f"{o} -> {c2}" for o, c2 in run.applied_corrections],
        )
        after = os.path.getsize(run.docx_path)
        assert_true(after > before, "audit page enlarges the .docx")

    print("\nALL SMOKE CHECKS PASSED")


if __name__ == "__main__":
    main()
