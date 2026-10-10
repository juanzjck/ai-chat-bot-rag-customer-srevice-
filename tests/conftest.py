"""Shared test doubles. Unit tests never call the real model API."""

from __future__ import annotations

import pytest

from supportbot.chatbot import GroundedAnswer
from supportbot.llm import LLMError
from supportbot.retriever import RetrievedChunk


class FakeLLM:
    """Scripted stand-in for the model that records every call it receives."""

    def __init__(self, answer: GroundedAnswer | None = None, rewrite: str = "rewritten query", fail: bool = False):
        self.answer = answer or GroundedAnswer(
            answerable=True, answer="The late fee is $7.", cited_sources=[1], needs_human=False
        )
        self.rewrite = rewrite
        self.fail = fail
        self.complete_calls: list[dict] = []
        self.structured_calls: list[dict] = []

    def complete(self, system, messages, usage=None):
        self.complete_calls.append({"system": system, "messages": messages})
        if self.fail:
            raise LLMError("boom")
        return self.rewrite

    def structured(self, system, messages, schema, usage=None):
        self.structured_calls.append({"system": system, "messages": messages})
        if self.fail:
            raise LLMError("boom")
        return self.answer


class FakeRetriever:
    """Returns fixed chunks with a configurable top score and records queries."""

    def __init__(self, top_score: float = 0.7):
        self.top_score = top_score
        self.queries: list[str] = []

    def search(self, query, k=None):
        self.queries.append(query)
        return [
            RetrievedChunk("late::0", "Late fee is $7.", "late-payments-and-fees.md", "Late fee amounts", self.top_score),
            RetrievedChunk("late::1", "Grace period is 7 days.", "late-payments-and-fees.md", "Grace period", self.top_score - 0.1),
        ]


@pytest.fixture
def fake_llm():
    return FakeLLM()


@pytest.fixture
def fake_retriever():
    return FakeRetriever()
