"""Streamlit web interface for the Image-to-Word Converter.

Run locally:
    streamlit run PPIT_Project/phase1/app.py

Deployed on Streamlit Community Cloud with main file set to:
    PPIT_Project/phase1/app.py
"""

from __future__ import annotations

import os
import sys
import tempfile

import streamlit as st

# Allow imports from src/ regardless of working directory
sys.path.insert(0, os.path.dirname(__file__))
from src.pipeline import convert  # noqa: E402

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Image → Word Converter",
    page_icon="📄",
    layout="centered",
)

st.title("📄 Image → Word Converter")
st.caption(
    "Upload a scanned image (JPG or PNG) and download a formatted Word document."
)

# ── Upload ────────────────────────────────────────────────────────────────────
uploaded = st.file_uploader(
    "Choose an image",
    type=["jpg", "jpeg", "png"],
    help="Supported formats: JPEG, PNG",
)

if uploaded is None:
    st.info("Upload an image above to get started.")
    st.stop()

# ── Preview ───────────────────────────────────────────────────────────────────
st.image(uploaded, caption=uploaded.name, use_column_width=True)

if not st.button("Convert to Word", type="primary"):
    st.stop()

# ── Conversion ────────────────────────────────────────────────────────────────
log_box = st.empty()
messages: list[str] = []

def progress(msg: str) -> None:
    messages.append(msg)
    log_box.info("\n\n".join(messages))

with tempfile.TemporaryDirectory() as tmp:
    img_path = os.path.join(tmp, uploaded.name)
    docx_path = os.path.join(tmp, os.path.splitext(uploaded.name)[0] + ".docx")

    with open(img_path, "wb") as f:
        f.write(uploaded.getvalue())

    try:
        with st.spinner("Processing…"):
            result = convert(img_path, docx_path, progress=progress)
        log_box.empty()

        st.success(
            f"Done! "
            f"Words: **{result.word_count}** | "
            f"Bold: **{result.bold_count}** | "
            f"Italic: **{result.italic_count}** | "
            f"Deskew: **{result.deskew_deg:.1f}°**"
        )

        with open(docx_path, "rb") as fh:
            docx_bytes = fh.read()

        st.download_button(
            label="⬇️ Download Word document",
            data=docx_bytes,
            file_name=os.path.basename(docx_path),
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

    except RuntimeError as exc:
        log_box.empty()
        st.error(f"Conversion failed: {exc}")
    except Exception as exc:  # noqa: BLE001
        log_box.empty()
        st.error(f"Unexpected error: {exc}")
