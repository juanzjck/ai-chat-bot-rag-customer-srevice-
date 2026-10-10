"""Retrieval: embed the query and fetch the most similar chunks from ChromaDB."""

from __future__ import annotations

from dataclasses import dataclass

import chromadb
from sentence_transformers import SentenceTransformer

from .config import DEFAULT_SETTINGS, Settings
from .ingest import build_index


@dataclass(frozen=True)
class RetrievedChunk:
    id: str
    text: str
    source: str
    section: str
    score: float  # cosine similarity, higher is more relevant


class Retriever:
    """Semantic search over the knowledge base.

    The same embedding model must be used at index time and query time,
    otherwise query and chunk vectors live in different spaces.
    """

    def __init__(
        self,
        settings: Settings = DEFAULT_SETTINGS,
        embedder: SentenceTransformer | None = None,
    ) -> None:
        self.settings = settings
        self.embedder = embedder or SentenceTransformer(settings.embed_model)
        client = chromadb.PersistentClient(path=str(settings.chroma_dir))
        existing = [c.name for c in client.list_collections()]
        if settings.collection not in existing:
            # First run: build the index so the bot works out of the box.
            build_index(settings, self.embedder)
        self.collection = client.get_collection(settings.collection)

    def search(self, query: str, k: int | None = None) -> list[RetrievedChunk]:
        """Return the k most similar chunks, best first."""
        if not query.strip():
            return []
        k = k or self.settings.top_k
        query_embedding = self.embedder.encode(
            [query], normalize_embeddings=True, show_progress_bar=False
        )
        result = self.collection.query(
            query_embeddings=query_embedding.tolist(),
            n_results=min(k, self.collection.count()),
            include=["documents", "metadatas", "distances"],
        )
        return [
            RetrievedChunk(
                id=chunk_id,
                text=document,
                source=metadata["source"],
                section=metadata["section"],
                score=round(1.0 - distance, 4),
            )
            for chunk_id, document, metadata, distance in zip(
                result["ids"][0],
                result["documents"][0],
                result["metadatas"][0],
                result["distances"][0],
            )
        ]
