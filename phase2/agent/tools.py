"""Tool registry for DocAgent (slide 23, slide 26).

Each tool is a small callable with metadata. The plan stage selects which
tools to invoke; the act stage runs them. Adding a new tool means adding one
entry here — no other module changes.

Three tiers, in priority order (slide 26):
  1. Deterministic rules / classical CV (preprocessing variants).
  2. Local ML if needed (placeholder hook — small CNN can plug in here).
  3. LLM repair, OFF by default, gated on confidence + HITL diff approval.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import cv2
import numpy as np


# -- preprocessing variants -------------------------------------------------

def preprocess_default(bgr: np.ndarray) -> np.ndarray:
    """Phase 1's default path. Returns grayscale post-denoise."""
    gray = bgr if bgr.ndim == 2 else cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    return cv2.medianBlur(gray, 3)


def preprocess_high_contrast(bgr: np.ndarray) -> np.ndarray:
    """For faded scans: CLAHE-boost contrast before denoise."""
    gray = bgr if bgr.ndim == 2 else cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    boosted = clahe.apply(gray)
    return cv2.medianBlur(boosted, 3)


def preprocess_denoise_heavy(bgr: np.ndarray) -> np.ndarray:
    """For phone photos with sensor noise."""
    gray = bgr if bgr.ndim == 2 else cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    return cv2.fastNlMeansDenoising(gray, None, h=15, templateWindowSize=7,
                                    searchWindowSize=21)


# -- spell-check (deterministic) -------------------------------------------

# Tiny built-in dictionary of common OCR confusions. Real implementation could
# pull pyspellchecker; we keep the dependency surface small for the prototype.
_OCR_FIX_RULES: dict[str, str] = {
    "rn": "m",
    "vv": "w",
    "0f": "of",
    "1n": "in",
    "tlie": "the",
    "teh": "the",
    "thier": "their",
    "wlth": "with",
    "wlien": "when",
}


def deterministic_spell_check(words: list[str]) -> list[tuple[int, str, str]]:
    """Return (index, original, suggested) for every word we'd correct.

    Caller decides whether to apply (we do NOT mutate input here).
    """
    out: list[tuple[int, str, str]] = []
    for i, w in enumerate(words):
        lo = w.lower()
        if lo in _OCR_FIX_RULES:
            out.append((i, w, _OCR_FIX_RULES[lo]))
    return out


# -- LLM repair (stub; opt-in only) ----------------------------------------

class LLMRepairTool:
    """Restricted-prompt LLM repair (slide 31 prompt-injection mitigation).

    The interface is deliberately narrow: it sees only one low-confidence word
    at a time, never page-level text, and never instructions from the document.
    The default implementation is a no-op stub — wiring an actual model is the
    user's opt-in choice.
    """

    enabled: bool = False
    network_egress: bool = False        # explicit flag for audit

    def repair_word(self, low_conf_word: str) -> str | None:
        """Return a suggested replacement, or None to leave the word alone.

        The default stub returns None: the agent ships without LLM unless the
        user explicitly subclasses and opts in.
        """
        if not self.enabled:
            return None
        return None  # subclass to plug in a model


# -- registry ---------------------------------------------------------------

@dataclass
class Tool:
    name: str
    fn: Callable[..., Any]
    tier: int                 # 1=rule, 2=ml, 3=llm
    description: str
    network: bool = False     # whether this tool egresses
    enabled: bool = True


@dataclass
class ToolRegistry:
    tools: dict[str, Tool] = field(default_factory=dict)

    def register(self, tool: Tool) -> None:
        self.tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self.tools.get(name)

    def list_by_tier(self, tier: int) -> list[Tool]:
        return [t for t in self.tools.values() if t.tier == tier and t.enabled]


def default_registry(*, llm: LLMRepairTool | None = None) -> ToolRegistry:
    """Wire up the standard set of tools."""
    reg = ToolRegistry()
    reg.register(Tool(
        name="preprocess_default", fn=preprocess_default, tier=1,
        description="Phase 1 default: grayscale + median blur."))
    reg.register(Tool(
        name="preprocess_high_contrast", fn=preprocess_high_contrast, tier=1,
        description="CLAHE contrast boost for faded scans."))
    reg.register(Tool(
        name="preprocess_denoise_heavy", fn=preprocess_denoise_heavy, tier=1,
        description="Non-local means denoise for phone photos."))
    reg.register(Tool(
        name="deterministic_spell_check", fn=deterministic_spell_check, tier=1,
        description="Static OCR confusion-pair dictionary."))
    reg.register(Tool(
        name="llm_repair", fn=(llm or LLMRepairTool()).repair_word, tier=3,
        description="Per-word LLM repair, restricted prompt, opt-in only.",
        network=False, enabled=False))
    return reg
