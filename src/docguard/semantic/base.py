"""Semantic-scan backend interface."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from docguard.types import SemanticFlag

_PROMPT_PATH = Path(__file__).with_name("classifier_prompt.md")


class BackendUnavailable(RuntimeError):
    """Raised when a backend's prerequisites aren't met."""


class SemanticBackend(Protocol):
    """All semantic backends honour this shape."""

    name: str
    default_model: str

    def available(self) -> bool:
        """Return True if this backend can run on this machine right now."""
        ...

    def classify(self, text: str, model: str | None = None) -> list[SemanticFlag]:
        """Return flags for suspicious spans. Raise BackendUnavailable if preconditions fail."""
        ...


def load_classifier_prompt() -> str:
    """Load the system prompt used by every LLM-based backend."""
    return _PROMPT_PATH.read_text(encoding="utf-8")


def wrap_user_input(text: str) -> str:
    """Wrap the untrusted essay in the ESSAY markers the classifier expects."""
    return f"<ESSAY>\n{text}\n</ESSAY>"
