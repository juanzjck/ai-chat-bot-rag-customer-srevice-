"""Deterministic guardrails that run before and after the LLM.

These checks are cheap, testable without an API key, and do not depend on the
model behaving well. They are the first of three defense layers:

1. Input guardrails (this module): validation, PII masking, injection screening.
2. Retrieval gate (this module): refuse to generate when nothing relevant was found.
3. Grounded prompt (prompts.py): the model may only answer from retrieved context.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Phrases typical of prompt-injection / jailbreak attempts. A keyword screen is
# easy to bypass, so it is only a first filter: the grounded system prompt is
# what stops attacks this list misses.
_INJECTION_PATTERNS = [
    r"\b(ignore|disregard|forget|override)\b.{0,40}\b(instructions?|rules?|prompts?|guidelines?)\b",
    r"\b(reveal|show|print|repeat|output|display|leak)\b.{0,40}\b(system|hidden|initial|original)\b.{0,20}\b(prompt|instructions?|message)\b",
    r"\byou are now\b",
    r"\b(act|behave|pretend|roleplay)\b.{0,20}\b(as|like|to be)\b.{0,40}\b(dan|unrestricted|unfiltered|jailbroken|without (any )?(rules|restrictions))\b",
    r"\b(developer|debug|admin|god|sudo)\s+mode\b",
    r"\bjailbreak\b",
    r"</?\s*(system|context|instructions?)\s*>",
    r"\bnew (system )?(instructions?|prompt)\s*:",
]
_INJECTION_RE = re.compile("|".join(_INJECTION_PATTERNS), flags=re.IGNORECASE | re.DOTALL)

_HUMAN_REQUEST_RE = re.compile(
    r"\b(talk|speak|chat|connect|transfer|escalate)\b.{0,30}\b(human|person|agent|representative|someone|supervisor|manager)\b"
    r"|\b(human|live|real)\s+(agent|person|support|representative)\b",
    flags=re.IGNORECASE,
)

# 13-19 digits, optionally separated by spaces or dashes: payment card numbers.
_CARD_RE = re.compile(r"\b(?:\d[ -]?){12,18}\d\b")
_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")


@dataclass(frozen=True)
class InputCheck:
    ok: bool
    cleaned: str = ""
    reason: str = ""  # "empty" | "too_long" | "injection" when ok is False
    pii_masked: bool = False


def mask_pii(text: str) -> tuple[str, bool]:
    """Replace card numbers and SSNs so they never reach the LLM provider or logs."""
    masked = _CARD_RE.sub("[CARD NUMBER REMOVED]", text)
    masked = _SSN_RE.sub("[SSN REMOVED]", masked)
    return masked, masked != text


def looks_like_injection(text: str) -> bool:
    return bool(_INJECTION_RE.search(text))


def wants_human(text: str) -> bool:
    return bool(_HUMAN_REQUEST_RE.search(text))


def check_input(text: str | None, max_chars: int = 1000) -> InputCheck:
    """Validate and sanitize a user message before it enters the pipeline."""
    cleaned = (text or "").strip()
    if not cleaned:
        return InputCheck(ok=False, reason="empty")
    if len(cleaned) > max_chars:
        return InputCheck(ok=False, reason="too_long")
    cleaned, pii_masked = mask_pii(cleaned)
    if looks_like_injection(cleaned):
        return InputCheck(ok=False, cleaned=cleaned, reason="injection", pii_masked=pii_masked)
    return InputCheck(ok=True, cleaned=cleaned, pii_masked=pii_masked)


def passes_retrieval_gate(top_score: float | None, min_similarity: float) -> bool:
    """True when the best retrieved chunk is similar enough to justify answering."""
    return top_score is not None and top_score >= min_similarity
