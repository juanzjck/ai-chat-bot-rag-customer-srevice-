"""Central configuration. Every tunable of the pipeline lives here."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Lets ANTHROPIC_API_KEY and model overrides live in a local, git-ignored .env file.
load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    # --- Knowledge base / vector store ---
    kb_dir: Path = PROJECT_ROOT / "data" / "kb"
    chroma_dir: Path = PROJECT_ROOT / ".chroma"
    collection: str = "lumio_kb"
    embed_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    # Sections longer than this are split on paragraph boundaries.
    chunk_max_chars: int = 900

    # --- Retrieval ---
    top_k: int = 4
    # Cosine similarity the best chunk must reach before the LLM is allowed
    # to answer. Below it the bot escalates instead of guessing.
    # Tuned with `python -m eval.run_eval --sweep`: the first guess of 0.35 wrongly
    # refused 6.7% of in-scope questions; 0.20-0.30 refuses 0% of them while still
    # refusing 100% of the out-of-scope ones. 0.28 sits inside that band.
    min_similarity: float = 0.28

    # --- Generation ---
    chat_model: str = os.getenv("SUPPORTBOT_CHAT_MODEL", "claude-haiku-5-5")
    judge_model: str = os.getenv("SUPPORTBOT_JUDGE_MODEL", "claude-sonnet-5-5")
    max_tokens: int = 4000
    # Number of past user/assistant exchanges kept as conversation memory.
    history_turns: int = 4

    # --- Input guardrails ---
    max_input_chars: int = 1000


DEFAULT_SETTINGS = Settings()
