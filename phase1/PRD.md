# Product Requirements Document (PRD)
## Phase 1 — Basic Image-to-Word Converter (MVP)

**Course / Program:** BSAI — FAST-NUCES (PPIT — Virtual Company)
**Phase:** 1 of N (Foundation)
**Document Version:** 1.0
**Authors:** I22-0448, I22-2131
**Target Submission Date:** 2026-01-28

---

## 1. Background & Problem Statement

Scanned documents and photographed pages are commonly archived as JPG/PNG images. When users
need to edit the underlying content, they typically copy/paste OCR output into a Word document
and lose every formatting cue: **bold and italic emphasis**, **left/right/center alignment**,
and **paragraph structure**. Re-formatting the document by hand is slow, error-prone, and
the single biggest pain point in OCR-driven workflows.

## 2. Vision

Deliver a small, dependency-light **desktop tool** that takes a single-page English-language
image and produces a `.docx` file that *looks* like the source — same emphasis, same
paragraph layout, same alignment — without manual touch-up.

Phase 1 is the **MVP foundation**. Later phases will extend it to equations, tables, and
multi-language support (out of scope here).

## 3. Goals (Phase 1)

| # | Goal | Measurable |
|---|------|------------|
| G1 | Extract text from clear printed English images | ≥ 90% character accuracy on the bundled sample set |
| G2 | Preserve **bold** and *italic* emphasis at the word level | Detected on the sample set, no hard-coded rules |
| G3 | Preserve paragraph **alignment** (left / center / right) | Correct on ≥ 90% of paragraphs in samples |
| G4 | Preserve **paragraph structure** (line grouping, blank-line breaks) | Correct paragraph count on samples |
| G5 | Run as a standalone desktop app | Single command (`python -m phase1.main`) launches a GUI |
| G6 | No cloud dependency | Works fully offline once Tesseract is installed |

## 4. Non-Goals (Phase 1)

- Multi-page PDFs.
- Handwritten input (the production samples are printed).
- Tables, equations, embedded images, headers/footers, columns.
- Languages other than English.
- Font family / font size recovery (only emphasis + alignment).
- Cloud / web deployment.

## 5. Users & Use Cases

**Primary user:** A student or office worker who has a photo or scan of a printed page and
wants to edit it in Word.

**Use Cases:**
1. *UC-1*: Open the app, browse for a JPG/PNG, click **Convert**, save the resulting `.docx`.
2. *UC-2*: Preview the source image and the recognized text side-by-side before saving.
3. *UC-3*: Re-run conversion with a different image without restarting the app.

## 6. Functional Requirements

### FR-1 — Input
- Accept `.jpg`, `.jpeg`, `.png` files via a file-chooser dialog.
- Reject other extensions with an inline error.

### FR-2 — Image Preprocessing
- Convert to grayscale.
- Adaptive thresholding to flatten paper texture / lighting.
- Mild deskew (rotation correction) using projection profile or Hough transform.
- Optional denoising (median blur) for noisy scans.

### FR-3 — OCR
- Use **Tesseract** (`pytesseract`) as the OCR engine.
- Use `image_to_data` (TSV mode) so every recognized word comes with:
  bounding box `(x, y, w, h)`, line/paragraph/block IDs, and confidence.

### FR-4 — Formatting Detection
- **Bold** detection: stroke-thickness heuristic per word
  (ratio of black ink area to bounding-box area, normalized against the page median).
- **Italic** detection: skew angle of the word's foreground pixels via image moments;
  threshold ≥ ~7°.
- **Alignment** detection: per text line, compare the line's left margin, right margin,
  and horizontal center to the page width — classify as left / center / right.
- **Paragraph** detection: group consecutive lines whose vertical gap is ≤ 1.5× the median
  inter-line gap; insert a paragraph break otherwise. Tesseract's `par_num` is used as a
  prior.

### FR-5 — DOCX Generation
- One paragraph per detected paragraph.
- Each word emitted as a `Run` so emphasis can be applied per word.
- Apply `bold=True` / `italic=True` flags from the detector.
- Apply paragraph-level alignment (`WD_ALIGN_PARAGRAPH.{LEFT,CENTER,RIGHT}`).
- Use the system default body font; do not attempt to recover the source font.

### FR-6 — GUI (Tkinter)
- Window with: file picker, image preview pane, log/status area, **Convert**, **Save As**,
  **Reset** buttons.
- Long-running OCR work runs in a background thread so the UI does not freeze.
- A progress indicator (indeterminate bar) is shown while OCR runs.
- A non-fatal error is displayed in the status area; a fatal error opens a `messagebox`.

### FR-7 — Persistence
- The produced `.docx` defaults to the input filename with a `.docx` extension, saved next
  to the input. The user can override via Save-As.

## 7. Non-Functional Requirements

| ID | Requirement |
|----|------------|
| NFR-1 | Convert a typical A4 single-page scan in ≤ 10 seconds on a mid-range laptop. |
| NFR-2 | Work offline. |
| NFR-3 | All third-party dependencies pinned in `requirements.txt`. |
| NFR-4 | Source code organized into single-responsibility modules. |
| NFR-5 | Code runs on Windows 10/11 and modern Linux without changes (paths use `os.path`). |

## 8. Architecture (High Level)

```
┌──────────────┐    ┌────────────┐    ┌────────────────┐    ┌─────────────┐    ┌────────────┐
│  Tkinter UI  │ -> │ Preprocess │ -> │ Tesseract OCR  │ -> │  Format     │ -> │  DOCX      │
│  (main.py)   │    │ (cv2)      │    │ (pytesseract)  │    │  Detector   │    │  Writer    │
└──────────────┘    └────────────┘    └────────────────┘    └─────────────┘    └────────────┘
```

Modules under `phase1/src/`:
- `preprocess.py` — grayscale, threshold, deskew.
- `ocr.py` — wraps `pytesseract.image_to_data`.
- `formatting.py` — bold / italic / alignment / paragraph detection.
- `docx_writer.py` — converts the formatted token stream into a `.docx`.
- `pipeline.py` — orchestrates the four stages end-to-end.
- `../main.py` — Tkinter front-end.

## 9. Success Criteria (Acceptance)

The phase is **accepted** when, on the bundled sample images:
1. The output `.docx` opens cleanly in MS Word / LibreOffice.
2. All bold words in the source are bold in the output (verified on sample set).
3. All italic words in the source are italic in the output (verified on sample set).
4. Centered titles and right-aligned signatures land in the correct alignment.
5. Paragraph breaks in the source appear as paragraph breaks (not single line breaks) in the output.
6. The app launches from a single command, accepts a file, and saves a `.docx`.

## 10. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Tesseract not installed on grader's machine | README documents Windows installer + `TESSERACT_CMD` env var override. |
| Skew / noise breaks OCR | Preprocessing pass: deskew + adaptive threshold. |
| False bold detection on dark scans | Normalize stroke-thickness ratio against the **page median**, not an absolute. |
| Italic detection misfires on serif fonts | Threshold tuned conservatively; serif fonts at 0° remain non-italic. |
| GUI freezes during OCR | Run pipeline in a worker thread; UI polls a queue. |

## 11. Deliverables

- Source code under `phase1/`.
- `phase1/PRD.md` (this document).
- `phase1/Phase1_Report.md` — implementation report.
- `phase1/requirements.txt`.
- `phase1/README.md` — install + run instructions.
- Demo video (recorded separately by the team).

## 12. Out-of-Scope / Future Phases

- **Phase 2:** Equations, multi-language, font-size recovery.
- **Phase 3:** Multi-page PDFs, batch mode, table reconstruction.
- **Phase 4:** Handwriting support, web-based deployment.
