"""Long-term memory store for DocAgent (slide 27).

Design constraints from the Phase 2 document:
  * Off by default. The `consent` flag must be true before anything is written.
  * Stores **metadata + corrections only** — never raw OCR text or image bytes
    (slide 17, data-theft mitigation).
  * Auto-purge after `retention_days` (default 30).
  * One-click `forget(source)` and `purge_all()` for right-of-erasure (slide 16).
  * Local SQLite file. No network.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from dataclasses import dataclass
from typing import Any


_DEFAULT_DB = os.path.join(os.path.dirname(__file__), "_memory.sqlite")
_DEFAULT_PRESETS = os.path.join(os.path.dirname(__file__), "_presets.json")


@dataclass
class MemoryConfig:
    enabled: bool = False             # opt-in
    retention_days: int = 30
    db_path: str = _DEFAULT_DB
    presets_path: str = _DEFAULT_PRESETS


_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS corrections (
           source TEXT NOT NULL,
           original_word TEXT NOT NULL,
           corrected_word TEXT NOT NULL,
           frequency INTEGER NOT NULL DEFAULT 1,
           last_seen REAL NOT NULL,
           PRIMARY KEY (source, original_word, corrected_word)
       )""",
    """CREATE TABLE IF NOT EXISTS outcomes (
           job_id TEXT PRIMARY KEY,
           source TEXT NOT NULL,
           plan_json TEXT NOT NULL,
           score REAL NOT NULL,
           decision TEXT NOT NULL,
           ts REAL NOT NULL,
           user_feedback TEXT
       )""",
    """CREATE TABLE IF NOT EXISTS doc_templates (
           doc_type TEXT PRIMARY KEY,
           prior_json TEXT NOT NULL,
           updated_at REAL NOT NULL
       )""",
]


class Memory:
    def __init__(self, config: MemoryConfig | None = None):
        self.config = config or MemoryConfig()
        self._conn: sqlite3.Connection | None = None
        if self.config.enabled:
            self._open()

    # -- lifecycle -----------------------------------------------------------

    def _open(self) -> None:
        os.makedirs(os.path.dirname(self.config.db_path) or ".", exist_ok=True)
        self._conn = sqlite3.connect(self.config.db_path)
        for ddl in _SCHEMA:
            self._conn.execute(ddl)
        self._conn.commit()
        self._auto_purge()

    def enable(self) -> None:
        """Caller must show a consent banner BEFORE invoking this."""
        if self.config.enabled:
            return
        self.config.enabled = True
        self._open()

    def disable(self) -> None:
        self.config.enabled = False
        if self._conn:
            self._conn.close()
            self._conn = None

    # -- writes (no-op when disabled) ----------------------------------------

    def record_correction(self, source: str, original: str, corrected: str) -> None:
        if not self._conn:
            return
        if original == corrected or not original or not corrected:
            return
        now = time.time()
        cur = self._conn.cursor()
        cur.execute(
            "SELECT frequency FROM corrections WHERE source=? AND original_word=? AND corrected_word=?",
            (source, original, corrected),
        )
        row = cur.fetchone()
        if row:
            cur.execute(
                "UPDATE corrections SET frequency=?, last_seen=? "
                "WHERE source=? AND original_word=? AND corrected_word=?",
                (row[0] + 1, now, source, original, corrected),
            )
        else:
            cur.execute(
                "INSERT INTO corrections VALUES (?, ?, ?, 1, ?)",
                (source, original, corrected, now),
            )
        self._conn.commit()

    def record_outcome(
        self,
        job_id: str,
        source: str,
        plan: dict[str, Any],
        score: float,
        decision: str,
    ) -> None:
        if not self._conn:
            return
        self._conn.execute(
            "INSERT OR REPLACE INTO outcomes VALUES (?, ?, ?, ?, ?, ?, NULL)",
            (job_id, source, json.dumps(plan), score, decision, time.time()),
        )
        self._conn.commit()

    # -- reads (always safe; return defaults when disabled) ------------------

    def lookup_corrections(self, source: str, min_frequency: int = 2) -> dict[str, str]:
        """Return high-confidence original -> corrected mappings for this source.

        Weighted by frequency AND recency: an old single-shot correction is
        not promoted into a rule (slide 31, memory-poisoning mitigation).
        """
        if not self._conn:
            return {}
        thirty_days_ago = time.time() - 30 * 24 * 3600
        rows = self._conn.execute(
            "SELECT original_word, corrected_word, frequency "
            "FROM corrections WHERE source=? AND frequency>=? AND last_seen>=? ",
            (source, min_frequency, thirty_days_ago),
        ).fetchall()
        return {orig: corr for orig, corr, _ in rows}

    def get_preset(self, source: str) -> dict[str, Any]:
        """Per-source preprocessing knobs, persisted as JSON."""
        if not self.config.enabled or not os.path.isfile(self.config.presets_path):
            return {}
        try:
            with open(self.config.presets_path, "r", encoding="utf-8") as f:
                presets = json.load(f)
        except (OSError, json.JSONDecodeError):
            return {}
        return presets.get(source, {})

    def set_preset(self, source: str, preset: dict[str, Any]) -> None:
        if not self.config.enabled:
            return
        presets: dict[str, Any] = {}
        if os.path.isfile(self.config.presets_path):
            try:
                with open(self.config.presets_path, "r", encoding="utf-8") as f:
                    presets = json.load(f)
            except (OSError, json.JSONDecodeError):
                presets = {}
        presets[source] = preset
        with open(self.config.presets_path, "w", encoding="utf-8") as f:
            json.dump(presets, f, indent=2)

    # -- right-of-erasure ----------------------------------------------------

    def forget(self, source: str) -> int:
        """Delete everything we know about one source. Returns rows removed."""
        if not self._conn:
            return 0
        cur = self._conn.cursor()
        cur.execute("DELETE FROM corrections WHERE source=?", (source,))
        n_corr = cur.rowcount
        cur.execute("DELETE FROM outcomes WHERE source=?", (source,))
        n_out = cur.rowcount
        self._conn.commit()
        # also strip the preset
        if os.path.isfile(self.config.presets_path):
            try:
                with open(self.config.presets_path, "r", encoding="utf-8") as f:
                    presets = json.load(f)
                presets.pop(source, None)
                with open(self.config.presets_path, "w", encoding="utf-8") as f:
                    json.dump(presets, f, indent=2)
            except (OSError, json.JSONDecodeError):
                pass
        return n_corr + n_out

    def purge_all(self) -> None:
        """Total wipe. Re-creates an empty DB."""
        if self._conn:
            self._conn.close()
            self._conn = None
        for path in (self.config.db_path, self.config.presets_path):
            if os.path.isfile(path):
                os.remove(path)
        if self.config.enabled:
            self._open()

    def _auto_purge(self) -> None:
        """Drop records older than retention_days."""
        if not self._conn:
            return
        cutoff = time.time() - self.config.retention_days * 24 * 3600
        self._conn.execute("DELETE FROM corrections WHERE last_seen < ?", (cutoff,))
        self._conn.execute("DELETE FROM outcomes WHERE ts < ?", (cutoff,))
        self._conn.commit()

    def summary(self) -> dict[str, Any]:
        """Used by the weekly memory-review HITL channel (slide 29)."""
        if not self._conn:
            return {"enabled": False}
        n_corr = self._conn.execute("SELECT COUNT(*) FROM corrections").fetchone()[0]
        n_out = self._conn.execute("SELECT COUNT(*) FROM outcomes").fetchone()[0]
        top = self._conn.execute(
            "SELECT original_word, corrected_word, frequency FROM corrections "
            "ORDER BY frequency DESC LIMIT 5"
        ).fetchall()
        return {
            "enabled": True,
            "n_corrections": n_corr,
            "n_outcomes": n_out,
            "top_rules": [
                {"original": o, "corrected": c, "frequency": f} for o, c, f in top
            ],
        }
