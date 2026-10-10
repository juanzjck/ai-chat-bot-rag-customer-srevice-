"""Ingestion: markdown files -> chunks -> embeddings -> ChromaDB.

Run once (or whenever the knowledge base changes):

    python -m supportbot.ingest
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

from .config import DEFAULT_SETTINGS, Settings


@dataclass(frozen=True)
class Chunk:
    id: str
    text: str
    source: str  # file name, e.g. "disputes.md"
    title: str  # document title (the "# " heading)
    section: str  # section title (the "## " heading)


def _split_long(body: str, max_chars: int) -> list[str]:
    """Split a section body on paragraph boundaries so no piece exceeds max_chars.

    A single paragraph longer than max_chars is kept whole rather than cut
    mid-sentence: a slightly long chunk is better than a broken policy rule.
    """
    if len(body) <= max_chars:
        return [body]
    pieces: list[str] = []
    current = ""
    for paragraph in re.split(r"\n\s*\n", body):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        if current and len(current) + len(paragraph) + 2 > max_chars:
            pieces.append(current)
            current = paragraph
        else:
            current = f"{current}\n\n{paragraph}" if current else paragraph
    if current:
        pieces.append(current)
    return pieces


def chunk_markdown(text: str, source: str, max_chars: int = 900) -> list[Chunk]:
    """Split one markdown document into chunks, one per "## " section.

    Structure-aware chunking: each section of a policy document answers one
    question, so a section is the natural retrieval unit. The document title
    and section title are prepended to the chunk text so the embedding carries
    the context ("Pay in 4 > Eligibility") even when the body does not repeat it.
    """
    title_match = re.search(r"^# (.+)$", text, flags=re.MULTILINE)
    title = title_match.group(1).strip() if title_match else Path(source).stem

    chunks: list[Chunk] = []
    # re.split with a capture group yields [preamble, heading1, body1, heading2, body2, ...]
    parts = re.split(r"^## (.+)$", text, flags=re.MULTILINE)
    for i in range(1, len(parts), 2):
        section = parts[i].strip()
        body = parts[i + 1].strip()
        if not body:
            continue
        for n, piece in enumerate(_split_long(body, max_chars)):
            chunks.append(
                Chunk(
                    id=f"{Path(source).stem}::{len(chunks)}",
                    text=f"{title} - {section}\n{piece}",
                    source=source,
                    title=title,
                    section=section if n == 0 else f"{section} (cont.)",
                )
            )
    return chunks


def load_chunks(kb_dir: Path, max_chars: int = 900) -> list[Chunk]:
    """Chunk every markdown file in the knowledge base directory."""
    files = sorted(kb_dir.glob("*.md"))
    if not files:
        raise FileNotFoundError(f"No .md files found in knowledge base dir: {kb_dir}")
    chunks: list[Chunk] = []
    for path in files:
        chunks.extend(chunk_markdown(path.read_text(encoding="utf-8"), path.name, max_chars))
    return chunks


def build_index(
    settings: Settings = DEFAULT_SETTINGS,
    embedder: SentenceTransformer | None = None,
) -> int:
    """(Re)build the vector index from scratch. Returns the number of chunks stored."""
    chunks = load_chunks(settings.kb_dir, settings.chunk_max_chars)
    embedder = embedder or SentenceTransformer(settings.embed_model)
    # Normalized vectors + cosine space => similarity = 1 - distance, in [-1, 1].
    embeddings = embedder.encode(
        [c.text for c in chunks], normalize_embeddings=True, show_progress_bar=False
    )

    client = chromadb.PersistentClient(path=str(settings.chroma_dir))
    # Drop and recreate so deleted/edited documents never leave stale chunks behind.
    if settings.collection in [c.name for c in client.list_collections()]:
        client.delete_collection(settings.collection)
    collection = client.create_collection(
        settings.collection, metadata={"hnsw:space": "cosine"}
    )
    collection.add(
        ids=[c.id for c in chunks],
        documents=[c.text for c in chunks],
        embeddings=embeddings.tolist(),
        metadatas=[{"source": c.source, "title": c.title, "section": c.section} for c in chunks],
    )
    return len(chunks)


if __name__ == "__main__":
    count = build_index()
    print(f"Indexed {count} chunks from {DEFAULT_SETTINGS.kb_dir} into {DEFAULT_SETTINGS.chroma_dir}")
