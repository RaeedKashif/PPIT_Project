"""Tkinter desktop GUI for DocAgent (Phase 2).

A separate UI from the Phase 1 converter. This one exposes the *agent loop*:
  * Start / Stop the folder watcher (the kill switch from slide 32).
  * Drop or add images into inbox/ and watch the agent perceive -> interpret
    -> plan -> act -> evaluate -> decide live.
  * Browse the four agent folders (inbox / outbox / holding / audit).
  * Memory: enable (with consent), forget(source), purge_all, summary.
  * Tune the ship / retry thresholds with sliders.

Run from the repo root with:

    python -m phase2.agent.gui
"""

from __future__ import annotations

import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# Force UTF-8 stdout so en-dashes / arrows in our log strings don't crash on
# Windows cp1252 consoles (same fix as main.py / smoke_test.py).
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass

# Make `phase1.*` and `phase2.*` importable whether the user runs
# `python -m phase2.agent.gui` from the repo root or `python gui.py`
# from inside phase2/agent.
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(_HERE))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from phase2.agent import Goal, Job  # noqa: E402
from phase2.agent.audit import AuditLogger  # noqa: E402
from phase2.agent.main import (  # noqa: E402
    AUDIT, HOLDING, INBOX, OUTBOX, _process_one,
)
from phase2.agent.memory import Memory, MemoryConfig  # noqa: E402
from phase2.agent.perceive import FolderWatcher  # noqa: E402


SUPPORTED_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
POLL_MS = 100


# Colour-coded decision tags used in the activity log.
_DECISION_COLOURS = {
    "ship":     "#1b6f1b",
    "retry":    "#a06900",
    "escalate": "#a0322d",
    "error":    "#a0322d",
    "info":     "#444444",
    "stage":    "#1f3b73",
}


class App(tk.Tk):

    def __init__(self) -> None:
        super().__init__()
        self.title("DocAgent — Phase 2 (agent test harness)")
        self.geometry("1100x740")
        self.minsize(960, 620)

        self._msg_queue: "queue.Queue[tuple[str, object]]" = queue.Queue()
        self._watcher: FolderWatcher | None = None
        self._watcher_thread: threading.Thread | None = None
        self._watcher_stop = threading.Event()

        # Goal sliders' live values
        self._ship_var = tk.DoubleVar(value=0.85)
        self._retry_var = tk.DoubleVar(value=0.60)

        # Memory state
        self._memory = Memory(MemoryConfig(enabled=False))
        self._memory_var = tk.BooleanVar(value=False)

        # Audit logger always on
        self._audit_logger = AuditLogger(AUDIT)

        for d in (INBOX, OUTBOX, HOLDING, AUDIT):
            os.makedirs(d, exist_ok=True)

        self._build_layout()
        self._refresh_folders()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(POLL_MS, self._poll_queue)

    # ------------------------------------------------------------------ UI
    def _build_layout(self) -> None:
        outer = ttk.Frame(self, padding=10)
        outer.pack(fill=tk.BOTH, expand=True)

        # ---------- toolbar ----------
        toolbar = ttk.Frame(outer)
        toolbar.pack(fill=tk.X, pady=(0, 8))

        self._start_btn = ttk.Button(
            toolbar, text="Start watcher", command=self._on_start)
        self._start_btn.pack(side=tk.LEFT)

        self._stop_btn = ttk.Button(
            toolbar, text="Stop watcher", command=self._on_stop, state=tk.DISABLED)
        self._stop_btn.pack(side=tk.LEFT, padx=4)

        ttk.Button(toolbar, text="Run once",
                   command=self._on_run_once).pack(side=tk.LEFT, padx=4)
        ttk.Button(toolbar, text="Add image to inbox...",
                   command=self._on_add_image).pack(side=tk.LEFT, padx=4)

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=8)

        ttk.Button(toolbar, text="Open inbox",
                   command=lambda: self._open_folder(INBOX)).pack(side=tk.LEFT)
        ttk.Button(toolbar, text="Open outbox",
                   command=lambda: self._open_folder(OUTBOX)).pack(
            side=tk.LEFT, padx=4)
        ttk.Button(toolbar, text="Open holding",
                   command=lambda: self._open_folder(HOLDING)).pack(side=tk.LEFT)
        ttk.Button(toolbar, text="Open audit",
                   command=lambda: self._open_folder(AUDIT)).pack(
            side=tk.LEFT, padx=4)

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=8)

        ttk.Button(toolbar, text="Clear log",
                   command=self._clear_log).pack(side=tk.LEFT)

        # ---------- body: left = folders, right = log ----------
        body = ttk.Frame(outer)
        body.pack(fill=tk.BOTH, expand=True)

        # left: tabs for the four folders
        left = ttk.LabelFrame(body, text="Agent folders", padding=6)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=(0, 6))

        self._notebook = ttk.Notebook(left)
        self._notebook.pack(fill=tk.BOTH, expand=True)

        self._folder_lists: dict[str, tk.Listbox] = {}
        for label, path in (("inbox/", INBOX), ("outbox/", OUTBOX),
                            ("holding/", HOLDING), ("audit/", AUDIT)):
            frame = ttk.Frame(self._notebook, padding=4)
            self._notebook.add(frame, text=label)
            lb = tk.Listbox(frame, width=40, height=22)
            lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            sb = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=lb.yview)
            sb.pack(side=tk.RIGHT, fill=tk.Y)
            lb.configure(yscrollcommand=sb.set)
            lb.bind("<Double-Button-1>",
                    lambda _e, p=path, b=lb: self._open_listbox_item(p, b))
            self._folder_lists[path] = lb

        ttk.Button(left, text="Refresh", command=self._refresh_folders).pack(
            fill=tk.X, pady=(6, 0))

        # right: activity log
        right = ttk.LabelFrame(body, text="Agent activity", padding=6)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(6, 0))

        self._log = tk.Text(right, height=24, wrap="word", state=tk.DISABLED)
        self._log.pack(fill=tk.BOTH, expand=True)
        for tag, colour in _DECISION_COLOURS.items():
            self._log.tag_configure(tag, foreground=colour)
        self._log.tag_configure("bold", font=("Segoe UI", 10, "bold"))
        log_sb = ttk.Scrollbar(right, orient=tk.VERTICAL, command=self._log.yview)
        log_sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._log.configure(yscrollcommand=log_sb.set)

        # ---------- footer: thresholds + memory + status ----------
        footer = ttk.LabelFrame(outer, text="Settings", padding=8)
        footer.pack(fill=tk.X, pady=(8, 0))

        # Threshold sliders
        sliders = ttk.Frame(footer)
        sliders.pack(side=tk.LEFT, fill=tk.X, expand=True)

        ttk.Label(sliders, text="Ship threshold:").grid(
            row=0, column=0, sticky=tk.W)
        ttk.Scale(sliders, from_=0.30, to=0.99, variable=self._ship_var,
                  command=self._on_ship_change, length=240).grid(
            row=0, column=1, padx=4, sticky=tk.W)
        self._ship_lbl = ttk.Label(sliders, text="0.85")
        self._ship_lbl.grid(row=0, column=2, padx=4, sticky=tk.W)

        ttk.Label(sliders, text="Retry threshold:").grid(
            row=1, column=0, sticky=tk.W, pady=(4, 0))
        ttk.Scale(sliders, from_=0.10, to=0.95, variable=self._retry_var,
                  command=self._on_retry_change, length=240).grid(
            row=1, column=1, padx=4, sticky=tk.W, pady=(4, 0))
        self._retry_lbl = ttk.Label(sliders, text="0.60")
        self._retry_lbl.grid(row=1, column=2, padx=4, sticky=tk.W, pady=(4, 0))

        # Memory controls
        memory = ttk.Frame(footer)
        memory.pack(side=tk.LEFT, padx=20)

        ttk.Checkbutton(
            memory, text="Memory enabled (consent)",
            variable=self._memory_var, command=self._on_toggle_memory,
        ).grid(row=0, column=0, columnspan=3, sticky=tk.W)

        ttk.Button(memory, text="Forget source...",
                   command=self._on_forget).grid(row=1, column=0, pady=(4, 0))
        ttk.Button(memory, text="Purge all",
                   command=self._on_purge).grid(
            row=1, column=1, padx=4, pady=(4, 0))
        ttk.Button(memory, text="Summary",
                   command=self._on_memory_summary).grid(
            row=1, column=2, pady=(4, 0))

        # Status bar
        self._status_var = tk.StringVar(value="Idle. Drop images into inbox/ or click Run once.")
        status = ttk.Label(outer, textvariable=self._status_var,
                           relief=tk.SUNKEN, anchor=tk.W, padding=4)
        status.pack(fill=tk.X, pady=(8, 0))

    # ------------------------------------------------------- helpers (UI)
    def _log_line(self, text: str, tag: str | None = None) -> None:
        self._log.configure(state=tk.NORMAL)
        if tag:
            self._log.insert(tk.END, text + "\n", tag)
        else:
            self._log.insert(tk.END, text + "\n")
        self._log.see(tk.END)
        self._log.configure(state=tk.DISABLED)

    def _clear_log(self) -> None:
        self._log.configure(state=tk.NORMAL)
        self._log.delete("1.0", tk.END)
        self._log.configure(state=tk.DISABLED)

    def _set_status(self, text: str) -> None:
        self._status_var.set(text)

    def _refresh_folders(self) -> None:
        for path, lb in self._folder_lists.items():
            lb.delete(0, tk.END)
            try:
                names = sorted(os.listdir(path))
            except OSError:
                names = []
            for n in names:
                lb.insert(tk.END, n)

    def _open_folder(self, path: str) -> None:
        try:
            if sys.platform.startswith("win"):
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Could not open", str(exc))

    def _open_listbox_item(self, base: str, lb: tk.Listbox) -> None:
        sel = lb.curselection()
        if not sel:
            return
        full = os.path.join(base, lb.get(sel[0]))
        if not os.path.exists(full):
            return
        try:
            if sys.platform.startswith("win"):
                os.startfile(full)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", full])
            else:
                subprocess.Popen(["xdg-open", full])
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Could not open", str(exc))

    def _make_goal(self) -> Goal:
        ship = float(self._ship_var.get())
        retry = float(self._retry_var.get())
        # Keep retry strictly below ship so the thresholds are coherent.
        if retry > ship - 0.01:
            retry = max(0.1, ship - 0.05)
            self._retry_var.set(retry)
            self._retry_lbl.configure(text=f"{retry:.2f}")
        return Goal(quality_threshold=ship, retry_threshold=retry)

    # ----------------------------------------------------------- callbacks
    def _on_ship_change(self, _v: str) -> None:
        self._ship_lbl.configure(text=f"{self._ship_var.get():.2f}")

    def _on_retry_change(self, _v: str) -> None:
        self._retry_lbl.configure(text=f"{self._retry_var.get():.2f}")

    def _on_toggle_memory(self) -> None:
        if self._memory_var.get():
            ok = messagebox.askyesno(
                "Memory consent",
                "Memory stores per-source presets and the corrections you "
                "approve. It NEVER stores raw OCR text or image bytes. "
                "Records auto-purge after 30 days. You can call Forget or "
                "Purge at any time.\n\nEnable memory?",
            )
            if ok:
                self._memory.enable()
                self._log_line("memory: ENABLED.", tag="info")
            else:
                self._memory_var.set(False)
        else:
            self._memory.disable()
            self._log_line("memory: disabled.", tag="info")

    def _on_forget(self) -> None:
        if not self._memory.config.enabled:
            messagebox.showinfo("Memory off",
                                "Enable memory before using Forget.")
            return
        # Default to the inbox source — the most common case for this UI.
        source = filedialog.askdirectory(
            title="Pick the source folder to forget", initialdir=INBOX)
        if not source:
            return
        n = self._memory.forget(source)
        self._log_line(f"forgot {n} record(s) for {source}.", tag="info")

    def _on_purge(self) -> None:
        if not messagebox.askyesno(
                "Purge memory",
                "Wipe ALL memory (corrections, presets, outcomes). Continue?"):
            return
        # purge_all is a no-op when memory is disabled, so enable a temp instance.
        m = Memory(MemoryConfig(enabled=True))
        m.purge_all()
        m.disable()
        self._log_line("memory purged.", tag="info")

    def _on_memory_summary(self) -> None:
        m = Memory(MemoryConfig(enabled=True))
        s = m.summary()
        m.disable()
        import json
        self._log_line("memory summary:", tag="bold")
        self._log_line(json.dumps(s, indent=2), tag="info")

    def _on_add_image(self) -> None:
        path = filedialog.askopenfilename(
            title="Pick an image to drop into inbox",
            filetypes=[("Images", " ".join("*" + e for e in SUPPORTED_EXT)),
                       ("All files", "*.*")],
        )
        if not path:
            return
        ext = os.path.splitext(path)[1].lower()
        if ext not in SUPPORTED_EXT:
            messagebox.showerror("Unsupported", f"Only {sorted(SUPPORTED_EXT)} are supported.")
            return
        target = os.path.join(INBOX, os.path.basename(path))
        try:
            shutil.copy2(path, target)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Copy failed", str(exc))
            return
        self._log_line(f"copied to inbox: {target}", tag="info")
        self._refresh_folders()

    # ------------------------------------------------------- run-once / watcher
    def _on_run_once(self) -> None:
        watcher = FolderWatcher(INBOX, poll_interval_s=0.1)
        # Avoid re-processing files already moved out by the watcher thread.
        if self._watcher is not None:
            for seen in self._watcher._seen:
                watcher._seen.add(seen)
        jobs = watcher.discover_new()
        if not jobs:
            messagebox.showinfo("Nothing to do",
                                "inbox/ is empty. Drop images via "
                                "'Add image to inbox...' first.")
            return
        self._set_status(f"Run-once: processing {len(jobs)} job(s)...")
        threading.Thread(target=self._process_jobs, args=(jobs,),
                         daemon=True).start()

    def _process_jobs(self, jobs: list[Job]) -> None:
        goal = self._make_goal()
        for job in jobs:
            try:
                self._msg_queue.put(("job_start", job))
                outcome = _process_one(
                    job, goal=goal, memory=self._memory,
                    audit_logger=self._audit_logger,
                    log=lambda m: self._msg_queue.put(("log", m)),
                )
                self._msg_queue.put(("job_done", outcome))
            except Exception as exc:  # noqa: BLE001
                self._msg_queue.put(("job_error", (job, exc)))

    def _on_start(self) -> None:
        if self._watcher_thread and self._watcher_thread.is_alive():
            return
        self._watcher_stop.clear()
        self._watcher = FolderWatcher(INBOX, poll_interval_s=1.0)
        goal = self._make_goal()

        def loop() -> None:
            self._msg_queue.put(("log", f"watching {INBOX} ..."))
            try:
                while not self._watcher_stop.is_set():
                    new_jobs = self._watcher.discover_new()
                    for job in new_jobs:
                        try:
                            self._msg_queue.put(("job_start", job))
                            outcome = _process_one(
                                job, goal=goal, memory=self._memory,
                                audit_logger=self._audit_logger,
                                log=lambda m: self._msg_queue.put(("log", m)),
                            )
                            self._msg_queue.put(("job_done", outcome))
                        except Exception as exc:  # noqa: BLE001
                            self._msg_queue.put(("job_error", (job, exc)))
                    time.sleep(1.0)
            finally:
                self._msg_queue.put(("log", "watcher stopped."))

        self._watcher_thread = threading.Thread(target=loop, daemon=True)
        self._watcher_thread.start()
        self._start_btn.configure(state=tk.DISABLED)
        self._stop_btn.configure(state=tk.NORMAL)
        self._set_status("Watcher running. Drop images into inbox/.")

    def _on_stop(self) -> None:
        self._watcher_stop.set()
        if self._watcher:
            self._watcher.stop()
        self._start_btn.configure(state=tk.NORMAL)
        self._stop_btn.configure(state=tk.DISABLED)
        self._set_status("Watcher stopped (kill switch).")

    def _on_close(self) -> None:
        self._on_stop()
        try:
            self._memory.disable()
        except Exception:  # noqa: BLE001
            pass
        self.destroy()

    # --------------------------------------------------------- worker plumbing
    def _poll_queue(self) -> None:
        try:
            while True:
                kind, payload = self._msg_queue.get_nowait()
                if kind == "log":
                    self._log_line(str(payload), tag="stage")
                elif kind == "job_start":
                    job = payload  # type: ignore[assignment]
                    self._log_line("")
                    self._log_line(f"=== job {job.job_id} ===", tag="bold")
                    self._log_line(f"input: {job.image_path}", tag="info")
                elif kind == "job_done":
                    out = payload  # type: ignore[assignment]
                    tag = out.decision.action  # ship / retry / escalate
                    self._log_line(
                        f"DECISION: {out.decision.action.upper()} -- "
                        f"{out.decision.reason}", tag=tag)
                    if out.output_path:
                        self._log_line(f"-> {out.output_path}", tag=tag)
                    self._log_line(
                        f"  doc_type={out.classification.label} "
                        f"({out.classification.confidence:.2f})    "
                        f"conf={out.score.aggregate_confidence:.2f}    "
                        f"words={out.score.word_count}    "
                        f"low_conf={out.score.low_conf_word_count}    "
                        f"in {out.duration_ms} ms",
                        tag="info",
                    )
                    self._refresh_folders()
                elif kind == "job_error":
                    job, exc = payload  # type: ignore[misc]
                    self._log_line(f"ERROR on {job.image_path}: {exc}",
                                   tag="error")
        except queue.Empty:
            pass
        self.after(POLL_MS, self._poll_queue)


def main() -> None:
    App().mainloop()


if __name__ == "__main__":
    main()
