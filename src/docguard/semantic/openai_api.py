"""OpenAI API backend — uses OPENAI_API_KEY."""

from __future__ import annotations

import json
import os

from docguard.semantic.base import (
    BackendUnavailableError,
    load_classifier_prompt,
    wrap_user_input,
)
from docguard.types import SemanticFlag


class OpenAIBackend:
    name = "openai"
    default_model = "gpt-4.1-mini"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")

    def available(self) -> bool:
        if not self.api_key:
            return False
        try:
            import openai  # noqa: F401
            return True
        except ImportError:
            return False

    def classify(self, text: str, model: str | None = None) -> list[SemanticFlag]:
        if not self.api_key:
            raise BackendUnavailableError("OPENAI_API_KEY not set")
        try:
            from openai import OpenAI
        except ImportError as e:
            raise BackendUnavailableError(
                "openai SDK not installed — `pip install docguard[openai]`"
            ) from e

        client = OpenAI(api_key=self.api_key)
        resp = client.chat.completions.create(
            model=model or self.default_model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": load_classifier_prompt()},
                {"role": "user", "content": wrap_user_input(text)},
            ],
            temperature=0,
        )
        raw = resp.choices[0].message.content or "{}"
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


__all__ = ["OpenAIBackend"]
