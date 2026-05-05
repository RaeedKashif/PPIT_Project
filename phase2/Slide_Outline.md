# Phase 2 — Slide-Ready Bullet Outline

> Condensed bullet form for the 32-slide deck. The full discussion lives in
> `Phase2_Document.md`. Each slide here gives you a tight bullet block + a
> "speaker note" cue.

---

## Slide 1 — Title

- **DocAgent** — Agentic Document Conversion System
- Phase 1: Image-to-Word Converter (MVP) → Phase 2: agentic redesign
- Course: Professional Practices in IT — FAST-NUCES BSAI
- Team: I22-0448, I22-2131
- Tagline: *"From a tool you push files into → an assistant that watches, plans,
  decides, and asks only when it isn't sure."*

*Speaker note:* introduce the team in one line, then drop the tagline.

---

## Slide 2 — Phase 1 Recap

- **Problem:** OCR strips formatting (bold/italic/alignment/paragraphs). Users
  rebuild it by hand.
- **Stack:** Tesseract 5 + OpenCV 4.10 + python-docx + Tkinter; classical CV, no GPU.
- **Pipeline:** preprocess → Tesseract `image_to_data` → bold/italic/alignment
  /paragraph heuristics → per-word `Run` in `.docx`.
- **Verified:** smoke test on synthetic 3-paragraph page → CENTER / LEFT / RIGHT
  alignment + emphasis flags survive.
- **Privacy:** fully offline.

*Speaker note:* show GUI screenshot; mention smoke test caught a real deskew bug.

---

## Slide 3 — Computing as a Formal Profession

- Software dev = formal profession (like medicine, law).
- Self-regulated by codes of ethics: ACM, IEEE-CS, PEC.
- Three duties owed:
  - **Users** — output must faithfully represent the source.
  - **Society** — accessible documents (screen-reader friendly).
  - **Data** — local processing for sensitive scans (CNICs, medical, contracts).

*Speaker note:* name one concrete real-world cost — e.g. wrong text in a contract.

---

## Slide 4 — Ethics vs. Morals

- **Morals** = personal beliefs; vary by culture; conscience-enforced.
- **Ethics** = profession-wide codified rules; enforced by professional bodies.
- Applied: in Phase 1 we picked **professional responsibility** over **personal
  convenience** three times:
  1. Page-relative thresholds (not hard-coded constants).
  2. Deterministic spell-check (not silent LLM repair).
  3. Real smoke test (not just running the GUI once).

*Speaker note:* the deskew bug was caught by the smoke test — pay-off in
practice, not just principle.

---

## Slide 5 — Professional Ethics

- **Code quality:** type hints, dataclasses, modular boundaries, pinned deps,
  smoke test.
- **Security:** no network calls, no telemetry, Tesseract path locked down,
  user-chosen paths only.
- **User safety:** save-next-to-input default, threaded worker (no GUI freeze),
  every pipeline stage logged.

---

## Slide 6 — A Real Ethical Decision

- **Decision:** *"Should LLM-based text correction be in Phase 1?"*
- **Frame:** speed (one API call) vs quality (auditable spell-check).
- **Choice:** deterministic, no LLM in Phase 1.
- **Why:** hallucination risk + privacy (data egress) + auditability + cost.
- **Phase 2:** LLM allowed *only* with confidence gate + HITL diff approval.

*Speaker note:* this is a real, named decision — not a hypothetical.

---

## Slide 7 — Importance of Ethical Decision Making

- **Users:** wrong info silently lands in their `.docx`.
- **Society:** every shoddy OCR pipeline erodes trust in the well-built ones.
- **System trust:** once a user catches one hallucination, they re-verify
  everything by hand → tool's productivity dividend goes to zero.

---

## Slide 8 — Ethical Theories & HCD

- **Utilitarianism applied:** classical CV (CPU-cheap) → tool runs on a low-end
  laptop; greatest good for the greatest number.
- **Deontology applied:** *"do not silently corrupt user data"* is a hard duty;
  no average-accuracy gain justifies a single hallucinated paragraph.
- **HCD:** every irreversible step (open/save/save-as/reset) is user-controlled.
- **Addictive-system risk:** flagged — agentic version's success metric is
  *user non-edits*, never engagement count.

---

## Slide 9 — ACM / IEEE Code of Ethics

- **Followed:**
  - ACM 1.2 (Avoid harm) — conservative thresholds, smoke test, HITL gate on LLM.
  - ACM 2.5 (Comprehensive evaluations) — Phase 1 Report + this Phase 2 doc enumerate limitations and risks.
  - ACM 1.6 (Respect privacy) — offline default, opt-in memory, auto-purge.
  - IEEE 1.1 (Public welfare) — high-stakes docs (ID cards) require user approval.
- **Potentially violated (honest):** ACM 3.7 — output `.docx` lacks OOXML
  accessibility metadata (`xml:lang`, structural styles for screen readers).
  Tracked as professional debt; on Phase 3 backlog.

*Speaker note:* mentioning a violation is the rubric's "Critical Thinking & Honesty" hook.

---

## Slide 10 — 4-Step Ethical Decision Process

Applied to: *"Should agentic DocAgent invoke an LLM to repair low-confidence words?"*

1. **Identify** — hallucination risk vs accuracy gain.
2. **Stakeholders** — end users, downstream readers, dev team, OCR community.
3. **Alternatives** — do nothing / spell-check only / silent LLM / **LLM + HITL diff**.
4. **Decision** — option 4: LLM gated on (a) confidence threshold, (b) explicit
   approval, (c) visible diff in audit page.

- **Cybersecurity:** LLM API would push potentially-PII content off-device → mitigation = pluggable interface, default = local/no model, opt-in egress warning.
- **Vulnerability disclosure:** private-acceptance, 30-day fix, public credit unless declined.

---

## Slide 11 — Industry Practices vs. Student Project

| Dimension | Us today | Software house | Plan |
|-----------|---------|----------------|------|
| Comm | WhatsApp + in-person | Slack + Jira + RFCs | RFC per Phase 2 feature |
| VCS | git, single branch | GitHub PRs, required reviewers, CI | One PR per feature |
| Testing | one smoke test | unit + integration + e2e in CI | pytest + GitHub Actions |
| Docs | PRD + Report + this | + ADRs + runbooks + on-call | add `docs/adr/` |
| Sec | manual review | SAST/DAST + Dependabot | enable Dependabot |
| AI ethics | smoke test | model cards + bias audits | ship eval harness |

- **AI bias exposure:** doc-type classifier biased toward English serif pages —
  mitigated by an evaluation harness that gates deployment on per-class accuracy.

---

## Slide 12 — Trends in IT & Agentic Systems

- Industry arc: **static tools → assistants → agents** (2010s → 2020s → 2025+).
- Frameworks: LangChain, AutoGen, CrewAI, Cursor, Claude Code.
- *Agentic* requires: autonomy, goal orientation, tool use, memory, self-evaluation.
- Average submissions stop at "tool use". Outstanding submissions deliver all five.

---

## Slide 13 — Career Skills

- **Classical CV + modern OCR pipelines** — bedrock of every production OCR product.
- **Agent design** — Perceive/Interpret/Plan/Act/Evaluate/Decide/Learn loop, tool
  registries, HITL UX, memory stores. Top-paying AI skill, 2026.
- **Evaluation engineering** — building harnesses, not just shipping models.
- **Software craft** — type hints, modular boundaries, smoke tests, pinned deps.
- **Ethics literacy** as a *design input*, not a compliance afterthought.

---

## Slide 14 — Virtual Work & Sustainability

- **Remote work:** async git + this document as source of truth.
- **Green computing:** classical CV ≈ 1 Wh per A4 page; LLM-based ≈ 50-100×.
- **Decision:** primary path stays classical; LLM is optional, HITL-gated, opt-in.
  Tool scales to 1000 docs on a laptop, not on a data centre.

---

## Slide 15 — Legal Aspects

- **Pakistan PECA 2016** §13 (forgery), §16 (identity crime), §22 (unauthorized
  access to data) — direct relevance because we process scanned ID cards / personal docs.
- **Developer duties:** minimize collection, local default, opt-in for any remote
  processing.
- **User rights:** know what's processed, where, for how long; right to delete.
  Implemented as `agent forget` + `agent purge` commands.

---

## Slide 16 — Intellectual Property Rights (IPR)

- **Source images** — owned by user. **Output `.docx`** — owned by user.
- **Our code** — owned by the team; **proposed licence: MIT** (max academic reuse).
- **Upstream:** Tesseract Apache-2.0, OpenCV Apache-2.0, python-docx MIT — preserved attributions.
- **Trademarks:** "DocAgent" descriptive, not registered.
- **GDPR mindset:** lawful basis (consent), purpose limitation (corrections only),
  storage limitation (auto-purge 30 d), right of erasure (one command).

---

## Slide 17 — Computer Crimes & Risks

| Risk | Mitigation |
|------|-----------|
| Data theft (memory DB read) | Memory stores metadata + corrections, not raw text/images. |
| Copyright misuse | ToS clause; user warrants ownership / fair use. |
| PII misuse | ID-card layout detector pauses for explicit consent. |
| Unauthorized access | Per-user agent; OS ACLs as boundary; no service mode. |
| Memory poisoning | Weighted by frequency + recency; outlier-flagged. |
| Supply-chain | Pinned deps; no network in primary path; Dependabot. |
| **Prompt injection** | LLM tool sees individual low-conf words only — never page-level instructions. |

PECA mapping: §3, §13, §16, §20 directly relevant.

---

## Slide 18 — Computer Contracts

- **ToS:** you own input + output; we collect no telemetry; memory opt-in;
  user warrants rights to all input; verify before relying on output for legal
  decisions; no warranty.
- **User agreement:** opt-in for memory, opt-in for LLM, one-click export, one-click purge.
- **Developer responsibility:** patched deps, 90-day coordinated vulnerability disclosure, this document maintained as the system evolves.

---

## Slide 19 — Technical Limitations of Phase 1

| Gap | Concrete |
|-----|---------|
| Static logic | hard-coded heuristic constants |
| No autonomy | every conversion needs a click |
| No intelligence | no doc-type awareness; one OCR config for everything |
| No memory | re-discovers scanner biases every run |
| No self-eval | ships output regardless of confidence |
| No multi-tool | one Tesseract config |
| No failure recovery | crash on empty OCR; no retry |

Seven gaps → seven things the agentic redesign must fix.

---

## Slide 20 — Agentic System Concept

- **Agent** = perceives + reasons about goals + selects tools + acts + evaluates + learns + with HITL.
- Five capabilities: Perception, Decision-making, Action, Learning, **Self-evaluation**.
- DocAgent implements all five.

---

## Slide 21 — Gap Analysis

| Capability | Phase 1 | Phase 2 |
|-----------|---------|---------|
| Perception | user click | folder watcher (`agent/perceive.py`) |
| Goal | implicit | explicit `Goal` dataclass |
| Planning | none | `agent/plan.py` |
| Tool use | one tool | `agent/tools.py` registry |
| Memory | none | `agent/memory.py` (SQLite + JSON) |
| Self-eval | none | `agent/evaluate.py` |
| Decide | always emit | `agent/decide.py` (ship/retry/escalate) |
| Learn | static | `agent/learn.py` |
| HITL | save dialog | active escalation channel |
| Audit | none | `agent/audit.py` |

---

## Slide 22 — Agentic Vision

- **Phase 1 = tool. Phase 2 = assistant.**
- Drop scans into `inbox/` → agent watches, classifies, plans, runs, evaluates.
- High confidence → `outbox/` (no human action).
- Low confidence → `holding/` with audit page (user reviews).
- User involvement collapses from "click for every conversion" to "review only the hard cases".

---

## Slide 23 — Agent Architecture

```
sensors → Interpret → Plan → Act (tool dispatch) → Evaluate → Decide → ship/retry/escalate → Learn
                                  ↑                                                            │
                                  └────────────────── memory ──────────────────────────────────┘
```

- **Sensors:** `inbox/`, drag-drop, IPC.
- **Tools:** Tesseract, preprocessing variants, dictionary, optional LLM (HITL-gated), format detector.
- **Memory:** corrections + per-source presets + doc-type templates.
- Every box = one file under `phase2/agent/`.

---

## Slide 24 — Agent Type Selection

- **Goal-based + Learning agent** (Russell & Norvig).
- **Goal:** "produce a `.docx` the user will not need to re-edit".
- **Learning:** integrates user-edit diffs and explicit feedback into priors.
- Rejected alternatives: simple-reflex (too dumb), utility-based (overkill — single goal), BDI (overkill — no competing intentions).

---

## Slide 25 — Operational Workflow

```
Observe → Interpret → Decide(plan) → Act → Evaluate → Decide(action) → Learn
   ↑                                                                      │
   └──────────────────────────────────────────────────────────────────────┘
```

| Step | Code |
|------|------|
| Observe | `agent/perceive.py::watch()` |
| Interpret | `agent/interpret.py::classify_doc()` |
| Plan | `agent/plan.py::pick_plan()` |
| Act | `agent/act.py::execute_plan()` |
| Evaluate | `agent/evaluate.py::score()` |
| Decide | `agent/decide.py::decide()` |
| Learn | `agent/learn.py::record()` |

---

## Slide 26 — Intelligence Layer (3-tier)

```
1. Rules (deterministic)  ← always tried first
        ↓ promote on need
2. Local ML (small CNN)   ← doc-type classifier; preprocessing/psm selector
        ↓ promote only if confidence < threshold
3. LLM (HITL-gated, opt-in)  ← per-word repair only; diff approval
```

- Order is itself an ethical choice (Slide 8 deontology): never give the opaque
  tool authority over the auditable one.

---

## Slide 27 — Memory & Context

- **Short-term** (per-job, in-RAM): preprocessing artifacts, OCR words + conf,
  current plan, retries.
- **Long-term** (SQLite + JSON, opt-in, auto-purge):
  - `corrections` — `(source, original, corrected, frequency, last_seen)`
  - `source_presets` — per-folder preprocessing knobs
  - `doc_templates` — per-doc-type layout priors
  - `outcomes` — per-job audit
- One-click export + one-click forget commands.

---

## Slide 28 — Autonomy Level

- **Semi-autonomy** (justified):
  - Full autonomy → catastrophic on a single mis-classified legal doc.
  - Pure user-driven → defeats the purpose.
- Operational thresholds:
  - `conf ≥ 0.85` → ship.
  - `0.60 ≤ conf < 0.85` → retry with alternative plan once.
  - `conf < 0.60` → escalate.
  - High-stakes doc-type (ID card) → escalate regardless.

---

## Slide 29 — Human-in-the-Loop

- **Where the human is:**
  1. First-run consent (memory + LLM separately).
  2. High-stakes docs (ID-card detection).
  3. Low-confidence escalation (`holding/` + audit page).
  4. LLM-suggested correction (per-word diff approval).
  5. Weekly memory-rule review.
- **Override controls:** kill switch, undo last action, reset memory.
- **Principle:** human time is *cheap* (per-decision) but *real* (not a rubber stamp).

---

## Slide 30 — Ethical Agent Design

| Pillar | Enforced by |
|--------|------------|
| Privacy | local-only default; opt-in memory; auto-purge; PII redaction in logs. |
| Bias | doc-type classifier evaluated across font types + languages; deployment gated on per-class accuracy. |
| Transparency | `audit/<job>.json` per run; appended audit page on every output `.docx`. |
| User control | kill switch; undo; reset; per-source disable; no-LLM mode; no-memory mode. |

- **Anti-patterns rejected:** "move fast & ask forgiveness", "optimize engagement", "telemetry by default".

---

## Slide 31 — Risk Assessment

| Risk | Mitigation |
|------|-----------|
| Incorrect agent decisions (mis-classified doc-type) | per-class accuracy gate; ID-card pause; PII scrubbing in logs |
| Over-automation (user stops proofreading) | audit page in every `.docx`; below-threshold words highlighted yellow |
| Misuse (copyright, others' PII) | ToS warning; ID-card pause; documented permissible vs impermissible use |
| Memory poisoning | corrections weighted (freq + recency); outliers flagged; weekly review |
| Prompt injection (LLM tool) | LLM sees individual low-conf words only, never page-level instructions |
| Engagement-trap drift | success metric codified as user *non-edits*, not interaction count |

---

## Slide 32 — Safety Mechanisms

- **Logging:** structured JSON per job (`audit/<job>.json`); local; PII-scrubbed; rotated.
- **Override:** kill switch (CLI + GUI), per-job override, full memory reset.
- **Explainability:** appended audit page in every output `.docx` showing
  per-word confidence + applied corrections + fired memory rules.

---

## Comparative Analysis (slide-form)

| Feature | Phase 1 | Agentic Phase 2 |
|---------|---------|------------------|
| Control | User-driven | System-driven (HITL on hard cases) |
| Intelligence | Static | Adaptive 3-tier (rules → ML → HITL-LLM) |
| Behavior | Reactive | Proactive |
| Tools | One | Registry |
| Memory | None | Short + long-term, opt-in, auto-purge |
| Autonomy | Zero | Semi (confidence-gated) |
| Self-eval | None | Aggregate confidence + structural integrity |
| Failure handling | Crash / blind ship | Retry + escalate |
| Auditability | None | Per-job JSON + appended audit page |

---

## Wrap

- Phase 1 honored profession over convenience three times (page-relative thresholds, no silent LLM, real smoke test).
- Phase 2 redesigns decision-making — not by bolting a chatbot on, but by layering rules → ML → HITL-gated LLM and gating autonomy on aggregate confidence.
- Honesty: ACM 3.7 violation owned (no OOXML accessibility metadata yet); risks named specific to this design (memory poisoning, prompt injection, engagement-trap drift).
- Outstanding-tier alignment per §V of the brief.
