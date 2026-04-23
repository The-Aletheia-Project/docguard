"""Ollama backend — fully local LLM for air-gapped users.

Expects an `ollama` server running on localhost (default port). Point at any
model that supports JSON-mode outputs — llama3.1, qwen2.5, etc.
"""

from __future__ import annotations

import json
import os

from docguard.semantic.base import (
    BackendUnavailable,
    load_classifier_prompt,
    wrap_user_input,
)
from docguard.types import SemanticFlag


class OllamaBackend:
    name = "ollama"
    default_model = "llama3.1:8b"

    def __init__(self, host: str | None = None) -> None:
        self.host = host or os.environ.get("OLLAMA_HOST", "http://localhost:11434")

    def available(self) -> bool:
        try:
            import ollama  # noqa: F401
        except ImportError:
            return False
        try:
            from ollama import Client
            Client(host=self.host).list()
            return True
        except Exception:  # noqa: BLE001
            return False

    def classify(self, text: str, model: str | None = None) -> list[SemanticFlag]:
        try:
            from ollama import Client
        except ImportError as e:
            raise BackendUnavailable(
                "ollama SDK not installed — `pip install docguard[ollama]`"
            ) from e

        client = Client(host=self.host)
        try:
            resp = client.chat(
                model=model or self.default_model,
                messages=[
                    {"role": "system", "content": load_classifier_prompt()},
                    {"role": "user", "content": wrap_user_input(text)},
                ],
                format="json",
                options={"temperature": 0},
            )
        except Exception as e:  # noqa: BLE001
            raise BackendUnavailable(f"ollama call failed: {e}") from e

        raw = resp.get("message", {}).get("content", "{}")
        return _parse_reply(raw, source=self.name)


def _parse_reply(raw: str, source: str) -> list[SemanticFlag]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return []
    flags: list[SemanticFlag] = []
    for f in payload.get("flags", []):
        flags.append(
            SemanticFlag(
                span=str(f.get("span", ""))[:500],
                reason=str(f.get("reason", "")),
                category=str(f.get("category", "other")),
                confidence=float(f.get("confidence", 0.5)),
                source=source,
            )
        )
    return flags


__all__ = ["OllamaBackend"]
