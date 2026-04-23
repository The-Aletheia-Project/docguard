"""Anthropic API backend — uses ANTHROPIC_API_KEY.

Preferred when you have an API key and want explicit per-call cost control.
"""

from __future__ import annotations

import json
import os

from docguard.semantic.base import (
    BackendUnavailableError,
    load_classifier_prompt,
    wrap_user_input,
)
from docguard.types import SemanticFlag


class AnthropicBackend:
    name = "anthropic"
    default_model = "claude-haiku-4-5-20251001"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")

    def available(self) -> bool:
        if not self.api_key:
            return False
        try:
            import anthropic  # noqa: F401
            return True
        except ImportError:
            return False

    def classify(self, text: str, model: str | None = None) -> list[SemanticFlag]:
        if not self.api_key:
            raise BackendUnavailableError("ANTHROPIC_API_KEY not set")
        try:
            from anthropic import Anthropic
        except ImportError as e:
            raise BackendUnavailableError(
                "anthropic SDK not installed — `pip install docguard[anthropic]`"
            ) from e

        client = Anthropic(api_key=self.api_key)
        resp = client.messages.create(
            model=model or self.default_model,
            max_tokens=1024,
            system=load_classifier_prompt(),
            messages=[{"role": "user", "content": wrap_user_input(text)}],
        )
        raw = "".join(
            block.text for block in resp.content if getattr(block, "type", None) == "text"
        )
        return _parse_reply(raw, source=self.name)


def _parse_reply(raw: str, source: str) -> list[SemanticFlag]:
    payload = _extract_json(raw)
    if payload is None:
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


def _extract_json(raw: str) -> dict | None:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()
        if raw.lower().startswith("json\n"):
            raw = raw[5:]
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return None


__all__ = ["AnthropicBackend"]
