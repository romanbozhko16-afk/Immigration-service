"""Anthropic API client for structured (JSON-schema) answers.

- Model and effort come from settings; every user gets the same ones.
- The response must match a JSON schema (`output_config.format`), and is validated again
  by the caller. Refusals, truncation, API errors and malformed output all raise
  `LLMUnavailable`; callers then fall back to a safe path that needs no model.
- Server-side refusal fallbacks are deliberately NOT enabled: they re-run a refused request
  on another model chosen by the server, which would break the owner's rules that one
  configured model serves everyone and that models requiring 30-day retention are not used.
- Nothing here logs prompts, answers or model output.
"""

import json
from typing import Any, Protocol

import anthropic
from pydantic import BaseModel, ConfigDict

from uscis_assistant.config import Settings


class LLMUnavailable(Exception):
    """No usable model answer; the message never contains user content."""


class StructuredLLM(Protocol):
    def json(self, *, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]: ...


class CitedRange(BaseModel):
    """Passages the model cited: indexes into the blocks it was given (end exclusive)."""

    model_config = ConfigDict(frozen=True)

    start: int
    end: int
    cited_text: str


class CitedAnswer(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str  # the model's own wording: never shown to users
    citations: list[CitedRange]


class CitingLLM(Protocol):
    def cite(self, *, system: str, title: str, blocks: list[str], question: str) -> CitedAnswer: ...


class AnthropicLLM:
    def __init__(self, settings: Settings, max_tokens: int = 16000):
        if settings.anthropic_api_key is None:
            raise LLMUnavailable("ANTHROPIC_API_KEY is not set")
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key.get_secret_value())
        self._model = settings.llm_model
        self._effort = settings.llm_effort
        self._max_tokens = max_tokens

    def json(self, *, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_config={
                    "effort": self._effort,
                    "format": {"type": "json_schema", "schema": schema},
                },
            )
        except anthropic.APIConnectionError as exc:
            raise LLMUnavailable(f"connection error: {type(exc).__name__}") from None
        except anthropic.APIStatusError as exc:
            raise LLMUnavailable(f"API error {exc.status_code}") from None
        # Check why the model stopped before reading content (a refusal has no usable JSON).
        if response.stop_reason != "end_turn":
            raise LLMUnavailable(f"stop_reason={response.stop_reason}")
        text = next((block.text for block in response.content if block.type == "text"), None)
        if text is None:
            raise LLMUnavailable("no text block")
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            raise LLMUnavailable("malformed JSON") from None
        if not isinstance(data, dict):
            raise LLMUnavailable("JSON is not an object")
        return data

    def cite(self, *, system: str, title: str, blocks: list[str], question: str) -> CitedAnswer:
        """Ask a question about `blocks` with the Citations API (no JSON format: the two
        features cannot be combined)."""
        document = {
            "type": "document",
            "source": {
                "type": "content",
                "content": [{"type": "text", "text": block} for block in blocks],
            },
            "title": title,
            "citations": {"enabled": True},
        }
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=system,
                messages=[
                    {"role": "user", "content": [document, {"type": "text", "text": question}]}
                ],
                output_config={"effort": self._effort},
            )
        except anthropic.APIConnectionError as exc:
            raise LLMUnavailable(f"connection error: {type(exc).__name__}") from None
        except anthropic.APIStatusError as exc:
            raise LLMUnavailable(f"API error {exc.status_code}") from None
        if response.stop_reason != "end_turn":
            raise LLMUnavailable(f"stop_reason={response.stop_reason}")
        texts, citations = [], []
        for block in response.content:
            if block.type != "text":
                continue
            texts.append(block.text)
            for citation in getattr(block, "citations", None) or []:
                if citation.type == "content_block_location" and citation.document_index == 0:
                    citations.append(
                        CitedRange(
                            start=citation.start_block_index,
                            end=citation.end_block_index,
                            cited_text=citation.cited_text,
                        )
                    )
        return CitedAnswer(text="".join(texts), citations=citations)
