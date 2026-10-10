"""Vector database: real embeddings + ChromaDB over the real knowledge base (offline)."""

from dataclasses import replace

import pytest

from supportbot.config import DEFAULT_SETTINGS
from supportbot.ingest import build_index
from supportbot.retriever import Retriever


@pytest.fixture(scope="module")
def retriever(tmp_path_factory):
    # Build into a temp dir so tests never depend on, or modify, the developer's index.
    settings = replace(DEFAULT_SETTINGS, chroma_dir=tmp_path_factory.mktemp("chroma"))
    return Retriever(settings)


def test_index_is_built_automatically_and_complete(retriever):
    assert retriever.collection.count() >= 50


@pytest.mark.parametrize(
    "question, source",
    [
        ("How much is the late fee?", "late-payments-and-fees.md"),
        ("how long do refunds take", "refunds-and-returns.md"),
        ("someone used my account to buy something", "account-and-security.md"),
        ("does lumio accept american express", "payment-methods.md"),
    ],
)
def test_top_result_comes_from_the_right_document(retriever, question, source):
    assert retriever.search(question)[0].source == source


def test_results_are_sorted_and_respect_k(retriever):
    results = retriever.search("late fee", k=3)
    scores = [r.score for r in results]
    assert len(results) == 3 and scores == sorted(scores, reverse=True)
    assert all(-1.0 <= s <= 1.0 for s in scores)


def test_k_larger_than_collection_does_not_crash(retriever):
    assert len(retriever.search("late fee", k=10_000)) == retriever.collection.count()


def test_empty_query_returns_nothing(retriever):
    assert retriever.search("   ") == []


def test_off_topic_query_scores_below_the_gate(retriever):
    assert retriever.search("How do I bake a chocolate cake?")[0].score < retriever.settings.min_similarity


def test_in_scope_query_scores_above_the_gate(retriever):
    assert retriever.search("How much is the late fee?")[0].score > retriever.settings.min_similarity


def test_rebuilding_the_index_does_not_duplicate_chunks(retriever):
    before = retriever.collection.count()
    assert build_index(retriever.settings, retriever.embedder) == before
