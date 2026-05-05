# Phase 1 — Image-to-Word Converter (MVP)

A small desktop tool that converts a JPG/PNG of a printed English page into a `.docx`
that preserves **bold/italic emphasis**, **paragraph alignment**, and **paragraph
structure**.

## 1. Install Tesseract

`pytesseract` is just a thin wrapper around the Tesseract binary, so you must install
Tesseract itself first.

**Windows**
1. Download the installer from <https://github.com/UB-Mannheim/tesseract/wiki>.
2. Install to the default location (`C:\Program Files\Tesseract-OCR`).
3. Either add `C:\Program Files\Tesseract-OCR` to your PATH, **or** set:
   ```
   set TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
   ```

**Linux**
```
sudo apt install tesseract-ocr
```

Verify with `tesseract --version`.

## 2. Install Python dependencies

From the repository root:

```
python -m pip install -r phase1/requirements.txt
```

Python 3.10+ is recommended.

## 3. Run

```
python -m phase1.main
```

This opens the Tkinter GUI:

1. Click **Open image...** and choose a `.jpg`, `.jpeg`, or `.png`.
2. Click **Convert** — the right pane logs each pipeline stage.
3. The `.docx` is written next to the input image. Click **Save As...** to drop a
   copy somewhere else.

## 4. Project layout

```
phase1/
├── PRD.md                  Phase 1 product requirements document
├── Phase1_Report.md        Implementation report (what was actually built)
├── README.md               (this file)
├── requirements.txt
├── main.py                 Tkinter GUI entry point
├── samples/                Place test images here
├── output/                 Default output dir (created on demand)
└── src/
    ├── preprocess.py       Grayscale, deskew, adaptive threshold
    ├── ocr.py              Tesseract wrapper (image_to_data TSV)
    ├── formatting.py       Bold/italic/alignment/paragraph detection
    ├── docx_writer.py      python-docx output
    └── pipeline.py         End-to-end orchestration
```

## 5. Troubleshooting

| Symptom | Fix |
|---------|-----|
| `RuntimeError: Tesseract executable not found` | Install Tesseract (step 1) and/or set `TESSERACT_CMD`. |
| Output has no bold detected | The page is already uniformly bold/light — there is no contrast to detect against. Try a denser scan. |
| GUI looks frozen | The pipeline runs in a worker thread; if it really freezes, check the status pane for the last stage logged. |
| OCR text is garbled | Re-scan at ≥ 300 DPI, ensure the page is roughly upright (deskew handles small angles only). |
