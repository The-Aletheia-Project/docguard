"""Tests for backend selection."""

from __future__ import annotations

import pytest

from docguard.semantic.dispatcher import (
    BACKEND_REGISTRY,
    available_backends,
    get_backend,
)
from docguard.semantic.regex_only import RegexBackend


def test_regex_always_available():
    assert RegexBackend().available() is True


def test_registry_has_all_backends():
    assert set(BACKEND_REGISTRY) == {"regex", "claude-cli", "anthropic", "openai", "ollama"}


def test_available_backends_includes_regex():
    names = available_backends()
    assert "regex" in names


def test_explicit_regex_works():
    b = get_backend("regex")
    assert b.name == "regex"


def test_unknown_backend_errors():
    with pytest.raises(ValueError):
        get_backend("nonexistent")


def test_auto_select_fallback_to_regex(monkeypatch):
    # Wipe env so nothing auto-selects
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DOCGUARD_BACKEND", raising=False)
    # Force claude-cli and ollama to report unavailable
    from docguard.semantic import claude_cli, ollama
    monkeypatch.setattr(claude_cli.ClaudeCliBackend, "available", lambda self: False)
    monkeypatch.setattr(ollama.OllamaBackend, "available", lambda self: False)
    b = get_backend(None)
    assert b.name == "regex"
