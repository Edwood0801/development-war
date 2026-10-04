"""Model-provider abstraction. The engine never imports a vendor SDK.

Adapters for OpenAI / Gemini / Anthropic / Ollama / OpenRouter are future work: each only has to
implement `generate` (messages in, text out). Agents that want an LLM take a `ModelProvider`.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable, Optional

from pydantic import BaseModel


class Message(BaseModel):
    role: str  # "system" | "user" | "assistant" | "tool"
    content: str


class ModelProvider(ABC):
    name: str = "base"

    @abstractmethod
    def generate(self, messages: list[Message], tools: Optional[list[dict[str, Any]]] = None) -> str:
        """Return the model's reply text (typically JSON for structured agent output)."""


class MockProvider(ModelProvider):
    """Deterministic provider for tests and offline runs: always returns the same canned reply."""

    name = "mock"

    def __init__(self, reply: str = '{"actions": [{"type": "pass"}]}'):
        self.reply = reply

    def generate(self, messages, tools=None) -> str:
        return self.reply


class ScriptedProvider(ModelProvider):
    """Returns queued replies in order (or calls a function). Useful to test LLM-style parsing."""

    name = "scripted"

    def __init__(self, replies: list[str] | Callable[[list[Message]], str]):
        self._replies = replies

    def generate(self, messages, tools=None) -> str:
        if callable(self._replies):
            return self._replies(messages)
        if not self._replies:
            raise RuntimeError("ScriptedProvider has no replies left")
        return self._replies.pop(0)
