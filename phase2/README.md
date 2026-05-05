# DocAgent — Phase 2

Agentic transformation of the Phase 1 Image-to-Word Converter.
Reads `phase2/Phase2_Document.md` for the full design rationale (32 slides
covering ethics, legal, IPR, and the architecture). This README is the
operator-facing how-to.

## Folder layout

```
phase2/
├── Phase2_Document.md     32-slide design + rationale (read this first)
├── Slide_Outline.md       slide-ready bullet condensation
├── README.md              <- you are here
├── inbox/                 drop scans here (watched)
├── outbox/                shipped .docx files land here
├── holding/               escalations parked here for human review
├── audit/                 one structured JSON event log per job
└── agent/                 the agent prototype
    ├── __init__.py
    ├── perceive.py        folder watcher → Job
    ├── interpret.py       rule-based doc-type classifier (+ ID-card detector)
    ├── plan.py            picks (preprocessor, psm, lang) per doc-type + memory
    ├── act.py             executes the plan (wraps the Phase 1 pipeline)
    ├── tools.py           tool registry (preprocessing variants, spell-check, LLM stub)
    ├── evaluate.py        aggregate confidence + structural integrity
    ├── decide.py          ship | retry | escalate
    ├── learn.py           records outcomes / updates memory
    ├── memory.py          consent-gated SQLite + JSON store
    ├── audit.py           PII-scrubbed event log + audit-page generator
    ├── main.py            orchestrator entry point
    └── smoke_test.py      end-to-end sanity check
```

## Install

The agent reuses the Phase 1 venv — there are **no new dependencies**.

```powershell
# from the repo root, on Windows
phase1\venv\Scripts\Activate.ps1
# verify
python -c "import cv2, pytesseract, docx, PIL; print('ok')"
```

Tesseract must be installed and discoverable (PATH or `TESSERACT_CMD` env var).

## Run

### One-pass batch (default)

```powershell
# drops scans into phase2/inbox/, then:
python -m phase2.agent.main --once
```

### Watch mode

```powershell
python -m phase2.agent.main --watch
# Ctrl-C to stop (clean kill switch)
```

### With memory enabled (will prompt for consent)

```powershell
python -m phase2.agent.main --watch --memory
```

### Right-of-erasure / housekeeping

```powershell
# wipe everything we learned about a specific source
python -m phase2.agent.main --forget "phase2/inbox"

# nuclear option: wipe all corrections, presets, outcomes
python -m phase2.agent.main --purge

# weekly review summary (HITL channel #5)
python -m phase2.agent.main --memory-summary
```

## What lands where

| Outcome | What you'll see |
|---|---|
| `ship` (confidence ≥ 0.85)     | `outbox/<name>.docx` with an appended **audit page** showing the plan, fired rules, and low-confidence words highlighted yellow. |
| `retry`                         | A second pass with an alternative plan (escalate preprocessing + flip psm). |
| `escalate` (confidence < 0.60 or ID-card detected) | The source image and (if any) the partial `.docx` move into `holding/` for human review. The reason is in `audit/<job_id>.json`. |

Every job — shipped or escalated — writes a structured JSON entry to
`audit/`. PII patterns (CNICs, emails, phones, dates) are masked in those
logs.

## Smoke test

```powershell
python -m phase2.agent.smoke_test
```

This runs two passes:
1. **Pure stages** — classifier, planner, watcher, memory, audit logger.
   Does not need Tesseract.
2. **Full pipeline** — synthesizes a letter image, runs the entire agent
   loop, asserts a non-trivial `.docx` is produced and the audit page is
   appended.

## Design pointers

- The 7-stage loop and the rationale for each module: `Phase2_Document.md`
  slides 19–32.
- Why semi-autonomy (not full): slide 28.
- Where the human is in the loop: slide 29.
- The risk catalogue (memory poisoning, prompt injection, etc.): slide 31.
- Comparative analysis Phase 1 ↔ Phase 2: end of `Phase2_Document.md`.
