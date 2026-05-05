"""Perception layer (slide 20, slide 25).

A folder watcher that turns "a new image landed in inbox/" into a `Job` event.

Implementation note: we use polling, not `watchdog`, to keep the dependency
surface zero-extra over Phase 1. For a single-user desktop tool processing a
handful of files at a time this is more than fast enough; swapping to
`watchdog.observers.Observer` is a one-file change.
"""

from __future__ import annotations

import os
import time
from typing import Callable, Iterable

from . import Job


_IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp")


class FolderWatcher:
    def __init__(
        self,
        folder: str,
        *,
        poll_interval_s: float = 1.0,
        seen_extensions: Iterable[str] = _IMAGE_EXTS,
    ):
        self.folder = folder
        self.poll_interval_s = poll_interval_s
        self.seen_extensions = tuple(e.lower() for e in seen_extensions)
        self._seen: set[str] = set()
        self._stopped = False
        os.makedirs(self.folder, exist_ok=True)

    def snapshot(self) -> list[str]:
        out: list[str] = []
        for name in os.listdir(self.folder):
            if name.lower().endswith(self.seen_extensions):
                full = os.path.join(self.folder, name)
                if os.path.isfile(full):
                    out.append(full)
        return out

    def discover_new(self) -> list[Job]:
        """One-shot scan. Returns Jobs for files we have not seen before."""
        jobs: list[Job] = []
        for path in self.snapshot():
            if path in self._seen:
                continue
            if not self._is_stable(path):
                # File is still being written. Skip this round; pick it up next tick.
                continue
            self._seen.add(path)
            jobs.append(Job(image_path=path, source=self.folder))
        return jobs

    def _is_stable(self, path: str, *, settle_s: float = 0.4) -> bool:
        """Heuristic: a file whose size hasn't changed in `settle_s` is finished."""
        try:
            s1 = os.path.getsize(path)
        except OSError:
            return False
        time.sleep(settle_s)
        try:
            s2 = os.path.getsize(path)
        except OSError:
            return False
        return s1 == s2 and s2 > 0

    def stop(self) -> None:
        self._stopped = True

    def watch(self, on_job: Callable[[Job], None]) -> None:
        """Block-and-poll. Calls `on_job` for every new Job until `stop()` is called."""
        self._stopped = False
        while not self._stopped:
            for job in self.discover_new():
                on_job(job)
            time.sleep(self.poll_interval_s)
