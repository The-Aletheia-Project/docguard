"""Claude CLI backend — uses the local `claude` binary and the user's
Anthropic subscription (Max / Pro / Team). No API key required.

This is the default when `claude` is on PATH and no API env vars are set.
"""

from __future__ import annotations

import json
import subprocess

from docguard.semantic.base import (
    BackendUnavailableError,
    load_classifier_prompt,
    wrap_user_input,
)
from docguard.types import SemanticFlag


class ClaudeCliBackend:
    name = "claude-cli"
    default_model = "claude-haiku-4-5-20251001"

    def __init__(self, timeout: int = 60) -> None:
        self.timeout = timeout

    def available(self) -> bool:
        try:
            r = subprocess.run(
                ["claude", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return r.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            return False

    def classify(self, text: str, model: str | None = None) -> list[SemanticFlag]:
        prompt = load_classifier_prompt() + "\n\n" + wrap_user_input(text)
        try:
            result = subprocess.run(
                [
                    "claude",
                    "-p",
                    "--model", model or self.default_model,
                    "--output-format", "json",
                    "--permission-mode", "default",
                    prompt,
                ],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                encoding="utf-8",
                errors="replace",
            )
        except FileNotFoundError as e:
            raise BackendUnavailableError("`claude` CLI not found on PATH") from e
        except subprocess.TimeoutExpired as e:
            raise BackendUnavailableError(f"claude CLI timed out after {self.timeout}s") from e

        if result.returncode != 0:
            raise BackendUnavailableError(
                f"claude CLI exit {result.returncode}: {result.stderr[:300]}"
            )

        return _parse_reply(result.stdout, source=self.name)


def _parse_reply(raw: str, source: str) -> list[SemanticFlag]:
    # `claude -p --output-format json` returns {"result": "...", ...}.
    try:
        outer = json.loads(raw)
        inner_str = outer.get("result", "")
    except json.JSONDecodeError:
        inner_str = raw

    payload = _extract_json(inner_str)
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


__all__ = ["ClaudeCliBackend"]
