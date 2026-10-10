"""Thin wrapper around the Anthropic SDK.

The rest of the code depends on the small `LLM` protocol below, not on the SDK.
That keeps the provider swappable and lets the unit tests inject a fake model,
so they run offline, for free, and deterministically.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, TypeVar

import anthropic
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    """Raised when the model call fails or returns nothing usable."""


@dataclass
class Usage:
    """Token counter shared across the calls of one bot turn."""

    input_tokens: int = 0
    output_tokens: int = 0
    calls: int = 0

    def add(self, usage: object) -> None:
        self.input_tokens += getattr(usage, "input_tokens", 0) or 0
        self.output_tokens += getattr(usage, "output_tokens", 0) or 0
        self.calls += 1


class LLM(Protocol):
    def complete(self, system: str, messages: list[dict], usage: Usage | None = None) -> str:
        """Return the model's plain-text reply."""

    def structured(
        self, system: str, messages: list[dict], schema: type[T], usage: Usage | None = None
    ) -> T:
        """Return the model's reply parsed and validated against a Pydantic schema."""


class ClaudeLLM:
    """`LLM` implementation backed by the Claude Messages API."""

    def __init__(
        self,
        model: str,
        max_tokens: int = 4000,
        effort: str = "low",
        client: anthropic.Anthropic | None = None,
    ) -> None:
        self.model = model
        self.max_tokens = max_tokens
        # Support answers are short lookups over provided context, so low effort
        # keeps latency and cost down. Sampling parameters such as temperature
        # are not accepted by current Claude models; effort is the control.
        self.effort = effort
        # Credentials come from ANTHROPIC_API_KEY or an `ant auth login` profile.
        self.client = client or anthropic.Anthropic(max_retries=3, timeout=60.0)

    def _call(self, method, **kwargs):
        try:
            response = method(
                model=self.model,
                max_tokens=self.max_tokens,
                output_config={"effort": self.effort},
                **kwargs,
            )
        except anthropic.AuthenticationError as e:
            raise LLMError("Authentication failed. Set ANTHROPIC_API_KEY or run `ant auth login`.") from e
        except anthropic.NotFoundError as e:
            raise LLMError(f"Model not found: {self.model}") from e
        except anthropic.RateLimitError as e:
            raise LLMError("Rate limited by the model provider. Try again shortly.") from e
        except anthropic.APIStatusError as e:
            raise LLMError(f"Model API error {e.status_code}: {e.message}") from e
        except anthropic.APIConnectionError as e:
            raise LLMError("Could not reach the model provider.") from e
        except TypeError as e:
            # The SDK raises TypeError at request time when no credential is configured.
            if "authentication" not in str(e).lower():
                raise
            raise LLMError("No API credentials found. Set ANTHROPIC_API_KEY or run `ant auth login`.") from e
        if response.stop_reason == "refusal":
            raise LLMError("The model declined to respond to this request.")
        if response.stop_reason == "max_tokens":
            raise LLMError("The model response was cut off (max_tokens reached).")
        return response

    def complete(self, system: str, messages: list[dict], usage: Usage | None = None) -> str:
        response = self._call(self.client.messages.create, system=system, messages=messages)
        if usage is not None:
            usage.add(response.usage)
        text = "".join(block.text for block in response.content if block.type == "text").strip()
        if not text:
            raise LLMError("The model returned an empty response.")
        return text

    def structured(
        self, system: str, messages: list[dict], schema: type[T], usage: Usage | None = None
    ) -> T:
        # Structured outputs: the API constrains the reply to the schema, so there
        # is no fragile "parse JSON out of free text" step.
        response = self._call(
            self.client.messages.parse, system=system, messages=messages, output_format=schema
        )
        if usage is not None:
            usage.add(response.usage)
        if response.parsed_output is None:
            raise LLMError("The model returned no structured output.")
        return response.parsed_output
