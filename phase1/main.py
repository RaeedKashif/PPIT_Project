"""Tkinter desktop GUI for the Image-to-Word converter.

Run from the repo root with:

    python -m phase1.main

A worker thread runs the OCR/formatting pipeline so the UI stays responsive.
"""

from __future__ import annotations

import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

if __package__ in (None, ""):
    # Allow `python main.py` from inside phase1/ in addition to
    # `python -m phase1.main` from the repo root.
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from phase1.src.pipeline import convert, ConversionResult  # type: ignore[import-not-found]
else:
    from .src.pipeline import convert, ConversionResult


PREVIEW_MAX = (480, 640)  # width, height
SUPPORTED_EXT = {".jpg", ".jpeg", ".png"}


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Image-to-Word Converter — Phase 1 MVP")
        self.geometry("900x640")
        self.minsize(820, 560)

        self.input_path: str | None = None
        self.last_result: ConversionResult | None = None
        self._msg_queue: "queue.Queue[tuple[str, object]]" = queue.Queue()

        self._build_layout()
        self.after(100, self._poll_queue)

    # ------------------------------------------------------------------ UI
    def _build_layout(self) -> None:
        container = ttk.Frame(self, padding=12)
        container.pack(fill=tk.BOTH, expand=True)

        toolbar = ttk.Frame(container)
        toolbar.pack(fill=tk.X, pady=(0, 8))

        ttk.Button(toolbar, text="Open image...", command=self._on_open).pack(side=tk.LEFT)
        self.convert_btn = ttk.Button(toolbar, text="Convert", command=self._on_convert,
                                      state=tk.DISABLED)
        self.convert_btn.pack(side=tk.LEFT, padx=6)
        self.saveas_btn = ttk.Button(toolbar, text="Save As...", command=self._on_save_as,
                                     state=tk.DISABLED)
        self.saveas_btn.pack(side=tk.LEFT, padx=6)
        ttk.Button(toolbar, text="Reset", command=self._on_reset).pack(side=tk.LEFT, padx=6)

        body = ttk.Frame(container)
        body.pack(fill=tk.BOTH, expand=True)

        # Left: image preview
        left = ttk.LabelFrame(body, text="Input image", padding=8)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 6))
        self.preview = ttk.Label(left, text="(no image loaded)", anchor="center")
        self.preview.pack(fill=tk.BOTH, expand=True)

        # Right: status / log
        right = ttk.LabelFrame(body, text="Status", padding=8)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(6, 0))
        self.log = tk.Text(right, height=20, wrap="word", state=tk.DISABLED)
        self.log.pack(fill=tk.BOTH, expand=True)

        # Footer: progress bar
        footer = ttk.Frame(container)
        footer.pack(fill=tk.X, pady=(8, 0))
        self.progress = ttk.Progressbar(footer, mode="indeterminate")
        self.progress.pack(fill=tk.X)

    # --------------------------------------------------------------- helpers
    def _log(self, msg: str) -> None:
        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, msg + "\n")
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)

    def _set_busy(self, busy: bool) -> None:
        if busy:
            self.progress.start(12)
            self.convert_btn.configure(state=tk.DISABLED)
            self.saveas_btn.configure(state=tk.DISABLED)
        else:
            self.progress.stop()
            self.convert_btn.configure(state=tk.NORMAL if self.input_path else tk.DISABLED)
            self.saveas_btn.configure(state=tk.NORMAL if self.last_result else tk.DISABLED)

    def _show_preview(self, path: str) -> None:
        try:
            img = Image.open(path)
        except Exception as exc:
            messagebox.showerror("Could not preview", str(exc))
            return
        img.thumbnail(PREVIEW_MAX)
        self._preview_imgref = ImageTk.PhotoImage(img)
        self.preview.configure(image=self._preview_imgref, text="")

    # ---------------------------------------------------------------- actions
    def _on_open(self) -> None:
        path = filedialog.askopenfilename(
            title="Choose an image",
            filetypes=[("Images", "*.jpg *.jpeg *.png"), ("All files", "*.*")],
        )
        if not path:
            return
        ext = os.path.splitext(path)[1].lower()
        if ext not in SUPPORTED_EXT:
            messagebox.showerror("Unsupported file",
                                 f"Only {', '.join(sorted(SUPPORTED_EXT))} are supported.")
            return
        self.input_path = path
        self.last_result = None
        self._show_preview(path)
        self._log(f"Loaded: {path}")
        self.convert_btn.configure(state=tk.NORMAL)
        self.saveas_btn.configure(state=tk.DISABLED)

    def _on_convert(self) -> None:
        if not self.input_path:
            return
        self._set_busy(True)
        self._log("Starting conversion...")

        def worker() -> None:
            try:
                result = convert(
                    self.input_path,
                    progress=lambda m: self._msg_queue.put(("log", m)),
                )
                self._msg_queue.put(("done", result))
            except Exception as exc:  # noqa: BLE001
                self._msg_queue.put(("error", exc))

        threading.Thread(target=worker, daemon=True).start()

    def _on_save_as(self) -> None:
        if not self.last_result:
            return
        target = filedialog.asksaveasfilename(
            defaultextension=".docx",
            filetypes=[("Word document", "*.docx")],
            initialfile=os.path.basename(self.last_result.output_path),
        )
        if not target:
            return
        try:
            # Re-write to the chosen path so we get exactly the user's file name.
            if __package__:
                from .src.docx_writer import write_docx
            else:
                from phase1.src.docx_writer import write_docx  # type: ignore[import-not-found]
            write_docx(self.last_result.paragraphs, target)
            self._log(f"Saved copy to: {target}")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Save failed", str(exc))

    def _on_reset(self) -> None:
        self.input_path = None
        self.last_result = None
        self.preview.configure(image="", text="(no image loaded)")
        self._preview_imgref = None
        self.log.configure(state=tk.NORMAL)
        self.log.delete("1.0", tk.END)
        self.log.configure(state=tk.DISABLED)
        self._set_busy(False)
        self.convert_btn.configure(state=tk.DISABLED)
        self.saveas_btn.configure(state=tk.DISABLED)

    # --------------------------------------------------------- worker plumbing
    def _poll_queue(self) -> None:
        try:
            while True:
                kind, payload = self._msg_queue.get_nowait()
                if kind == "log":
                    self._log(str(payload))
                elif kind == "done":
                    assert isinstance(payload, ConversionResult)
                    self.last_result = payload
                    self._log("")
                    self._log(f"Done. Wrote: {payload.output_path}")
                    self._log(f"  Words: {payload.word_count}    "
                              f"Bold: {payload.bold_count}    "
                              f"Italic: {payload.italic_count}")
                    self._log(f"  Paragraphs: {len(payload.paragraphs)}    "
                              f"Deskew: {payload.deskew_deg:.2f} deg")
                    self._set_busy(False)
                elif kind == "error":
                    self._set_busy(False)
                    self._log(f"ERROR: {payload}")
                    messagebox.showerror("Conversion failed", str(payload))
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)


def main() -> None:
    App().mainloop()


if __name__ == "__main__":
    main()
