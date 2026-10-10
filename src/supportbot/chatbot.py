"""The RAG pipeline: guardrails -> query rewrite -> retrieve -> gate -> generate."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from . import guardrails, prompts
from .config import DEFAULT_SETTINGS, Settings
from .llm import LLM, ClaudeLLM, LLMError, Usage
from .retriever import RetrievedChunk, Retriever

# Canned replies for paths where the LLM is deliberately not called.
MSG_EMPTY = "I didn't catch that. What can I help you with?"
MSG_TOO_LONG = "That message is too long for me to process. Could you summarize your question in a few sentences?"
MSG_BLOCKED = (
    "I can't help with that request. I'm here to answer questions about Lumio Pay "
    "payments, fees, refunds, disputes and accounts."
)
MSG_HANDOFF = (
    "I'll connect you with a human agent. Agents are available Monday to Friday 8am-8pm ET "
    "and Saturday 9am-5pm ET, or you can call 1-800-555-0142."
)
MSG_NO_CONTEXT = (
    "I'm sorry, I don't have information about that in the Lumio Pay help center, and I don't "
    "want to guess. I can connect you with a human agent, or you can call 1-800-555-0142."
)
MSG_ERROR = (
    "I'm having trouble answering right now. Please try again in a moment, "
    "or call 1-800-555-0142 to reach a human agent."
)


class GroundedAnswer(BaseModel):
    """Schema the model must fill in. Enforced by the API (structured outputs)."""

    answerable: bool = Field(description="True only if the context excerpts contain the answer.")
    answer: str = Field(description="The reply shown to the customer.")
    cited_sources: list[int] = Field(description="Numbers of the excerpts used in the answer.")
    needs_human: bool = Field(
        description="True if the customer needs an account-specific action or exception "
        "that only a human agent can perform."
    )


@dataclass
class BotResponse:
    answer: str
    # answered  - grounded answer from the knowledge base
    # escalated - handed to a human (no relevant context, not answerable, or user asked)
    # blocked   - stopped by the injection screen
    # invalid   - empty or oversized input
    # error     - model/provider failure
    status: str
    reason: str = ""
    needs_human: bool = False
    search_query: str = ""
    sources: list[RetrievedChunk] = field(default_factory=list)  # chunks the answer cites
    retrieved: list[RetrievedChunk] = field(default_factory=list)  # everything retrieved
    top_score: float | None = None
    pii_masked: bool = False
    latency_ms: int = 0
    usage: Usage = field(default_factory=Usage)


class SupportBot:
    """Stateless RAG engine. Conversation state is passed in via `history`."""

    def __init__(
        self,
        retriever: Retriever | None = None,
        llm: LLM | None = None,
        settings: Settings = DEFAULT_SETTINGS,
    ) -> None:
        self.settings = settings
        self.retriever = retriever or Retriever(settings)
        self.llm = llm or ClaudeLLM(settings.chat_model, settings.max_tokens)

    def answer(self, message: str, history: list[dict] | None = None) -> BotResponse:
        """Answer one customer message.

        `history` is a list of {"role": "user"|"assistant", "content": str} with
        the previous turns of the conversation, oldest first.
        """
        start = time.perf_counter()
        response = self._answer(message, history or [])
        response.latency_ms = int((time.perf_counter() - start) * 1000)
        return response

    def _answer(self, message: str, history: list[dict]) -> BotResponse:
        # 1. Input guardrails: no model or retrieval cost for bad input.
        check = guardrails.check_input(message, self.settings.max_input_chars)
        if not check.ok:
            if check.reason == "injection":
                return BotResponse(MSG_BLOCKED, "blocked", "injection", pii_masked=check.pii_masked)
            text = MSG_EMPTY if check.reason == "empty" else MSG_TOO_LONG
            return BotResponse(text, "invalid", check.reason)
        question = check.cleaned

        # 2. An explicit request for a person is always honored, never argued with.
        if guardrails.wants_human(question):
            return BotResponse(
                MSG_HANDOFF, "escalated", "user_request", needs_human=True, pii_masked=check.pii_masked
            )

        usage = Usage()
        history = history[-2 * self.settings.history_turns :]
        try:
            # 3. Query rewrite: "what about for that one?" -> standalone search query.
            search_query = self._rewrite(question, history, usage)

            # 4. Retrieve.
            retrieved = self.retriever.search(search_query, self.settings.top_k)
            top_score = retrieved[0].score if retrieved else None
            base = dict(
                search_query=search_query,
                retrieved=retrieved,
                top_score=top_score,
                pii_masked=check.pii_masked,
                usage=usage,
            )

            # 5. Retrieval gate: nothing relevant found -> escalate instead of guessing.
            if not guardrails.passes_retrieval_gate(top_score, self.settings.min_similarity):
                return BotResponse(MSG_NO_CONTEXT, "escalated", "no_context", needs_human=True, **base)

            # 6. Grounded generation. History gives conversational continuity;
            #    only the current turn carries retrieved context.
            messages = history + [
                {"role": "user", "content": prompts.build_user_turn(question, retrieved)}
            ]
            result = self.llm.structured(prompts.SYSTEM_PROMPT, messages, GroundedAnswer, usage)
        except LLMError as e:
            return BotResponse(MSG_ERROR, "error", str(e), needs_human=True, usage=usage)

        if not result.answerable:
            return BotResponse(result.answer, "escalated", "not_in_context", needs_human=True, **base)

        cited = [retrieved[i - 1] for i in dict.fromkeys(result.cited_sources) if 1 <= i <= len(retrieved)]
        return BotResponse(
            result.answer, "answered", needs_human=result.needs_human, sources=cited, **base
        )

    def _rewrite(self, question: str, history: list[dict], usage: Usage) -> str:
        """Turn a follow-up into a standalone query. First turns are used as-is."""
        if not history:
            return question
        try:
            rewritten = self.llm.complete(
                prompts.REWRITE_SYSTEM_PROMPT,
                [{"role": "user", "content": prompts.build_rewrite_turn(history, question)}],
                usage,
            )
        except LLMError:
            # Degrade gracefully: a worse search query beats a failed turn.
            return question
        rewritten = rewritten.strip().splitlines()[0].strip()
        return rewritten or question


class ChatSession:
    """One customer conversation: keeps short-term memory between turns."""

    def __init__(self, bot: SupportBot) -> None:
        self.bot = bot
        self.history: list[dict] = []

    def send(self, message: str) -> BotResponse:
        response = self.bot.answer(message, self.history)
        # Blocked and invalid turns are not remembered, so an injection attempt
        # cannot influence later turns through the history.
        if response.status in ("answered", "escalated"):
            cleaned, _ = guardrails.mask_pii(message.strip())
            self.history.append({"role": "user", "content": cleaned})
            self.history.append({"role": "assistant", "content": response.answer})
        return response

    def reset(self) -> None:
        self.history.clear()
