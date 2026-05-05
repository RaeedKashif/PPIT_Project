"""Batch convert every image in phase1/input/ to a .docx in phase1/output/.

Run from the repo root:
    python -m phase1.batch
"""

from __future__ import annotations

import os
import sys
import time

if __package__ in (None, ""):
    # Allow `python batch.py` from inside phase1/ in addition to
    # `python -m phase1.batch` from the repo root.
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from phase1.src.pipeline import convert  # type: ignore[import-not-found]
else:
    from .src.pipeline import convert


SUPPORTED_EXT = {".jpg", ".jpeg", ".png"}


def main() -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    in_dir = os.path.join(here, "input")
    out_dir = os.path.join(here, "output")
    os.makedirs(out_dir, exist_ok=True)

    if not os.path.isdir(in_dir):
        print(f"Input folder not found: {in_dir}", file=sys.stderr)
        return 2

    images = sorted(
        f for f in os.listdir(in_dir)
        if os.path.splitext(f)[1].lower() in SUPPORTED_EXT
    )
    if not images:
        print(f"No JPG/PNG images found in {in_dir}", file=sys.stderr)
        return 2

    print(f"Converting {len(images)} image(s) -> {out_dir}\n")
    failures = 0
    for name in images:
        src = os.path.join(in_dir, name)
        dst = os.path.join(out_dir, os.path.splitext(name)[0] + ".docx")
        print(f"-> {name}")
        t0 = time.time()
        try:
            r = convert(src, dst, progress=lambda m: print(f"   {m}"))
        except Exception as exc:  # noqa: BLE001
            print(f"   FAILED: {exc}\n")
            failures += 1
            continue
        dt = time.time() - t0
        print(f"   done in {dt:0.1f}s — words={r.word_count} "
              f"bold={r.bold_count} italic={r.italic_count} "
              f"paragraphs={len(r.paragraphs)} deskew={r.deskew_deg:.2f} deg")
        print(f"   wrote {r.output_path}\n")

    if failures:
        print(f"{failures} failure(s).")
        return 1
    print("All conversions succeeded.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
