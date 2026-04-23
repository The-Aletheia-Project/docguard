"""Backend selection and scan orchestration.

Selection order when `backend=None`:
  1. DOCGUARD_BACKEND environment variable
  2. ANTHROPIC_API_KEY set -> anthropic
  3. OPENAI_API_KEY set -> openai
  4. `claude` CLI on PATH -> claude-cli
  5. ollama server reachable -> ollama
  6. fallback -> regex
"""

from __future__ import annotations

import os

from docguard.semantic.anthropic_api import AnthropicBackend
from docguard.semantic.base import BackendUnavailableError, SemanticBackend
from docguard.semantic.claude_cli import ClaudeCliBackend
from docguard.semantic.ollama import OllamaBackend
from docguard.semantic.openai_api import OpenAIBackend
from docguard.semantic.regex_only import RegexBackend
from docguard.types import SemanticFlag

BACKEND_REGISTRY: dict[str, type] = {
    "regex": RegexBackend,
    "claude-cli": ClaudeCliBackend,
    "anthropic": AnthropicBackend,
    "openai": OpenAIBackend,
    "ollama": OllamaBackend,
}


def available_backends() -> list[str]:
    """Return names of backends that pass `available()` right now."""
    out = []
    for name, cls in BACKEND_REGISTRY.items():
        try:
            if cls().available():
                out.append(name)
        except Exception:
            continue
    return out


def get_backend(name: str | None = None) -> SemanticBackend:
    """Resolve a backend by name or by auto-selection."""
    if name is None:
        name = os.environ.get("DOCGUARD_BACKEND")

    if name:
        cls = BACKEND_REGISTRY.get(name)
        if cls is None:
            raise ValueError(
                f"Unknown backend '{name}'. Known: {list(BACKEND_REGISTRY)}"
            )
        backend = cls()
        if not backend.available():
            raise BackendUnavailableError(
                f"Backend '{name}' is not available on this machine."
            )
        return backend

    # Auto-select
    if os.environ.get("ANTHROPIC_API_KEY"):
        b = AnthropicBackend()
        if b.available():
            return b
    if os.environ.get("OPENAI_API_KEY"):
        b = OpenAIBackend()
        if b.available():
            return b
    cli = ClaudeCliBackend()
    if cli.available():
        return cli
    ol = OllamaBackend()
    if ol.available():
        return ol
    return RegexBackend()


def scan(
    text: str,
    backend_name: str | None = None,
    model: str | None = None,
    always_regex: bool = True,
    max_chars: int = 30_000,
) -> tuple[list[SemanticFlag], str, str | None]:
    """Run regex pass + (optionally) the selected LLM backend.

    Returns (flags, backend_name_used, error_or_none).
    """
    snippet = text[:max_chars]
    flags: list[SemanticFlag] = []
    if always_regex:
        flags.extend(RegexBackend().classify(snippet))

    try:
        backend = get_backend(backend_name)
    except BackendUnavailableError as e:
        return flags, "regex", str(e)

    # If the dispatcher fell back to regex, skip running it again.
    if backend.name == "regex" and always_regex:
        return flags, "regex", None

    try:
        flags.extend(backend.classify(snippet, model=model))
        return flags, backend.name, None
    except BackendUnavailableError as e:
        return flags, backend.name, str(e)
    except Exception as e:
        return flags, backend.name, f"{type(e).__name__}: {e}"


__all__ = [
    "BACKEND_REGISTRY",
    "available_backends",
    "get_backend",
    "scan",
]
