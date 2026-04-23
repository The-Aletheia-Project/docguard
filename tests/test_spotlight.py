"""Spotlight wrapping tests."""

from __future__ import annotations

import base64

from docguard.spotlight import wrap


def test_datamark_preserves_paragraphs():
    text = "First paragraph.\n\nSecond paragraph."
    out = wrap(text, student_name="Alice", mode="datamark")
    assert "\n\n" in out
    assert "First" in out
    assert "Second" in out


def test_datamark_inserts_separator_between_words():
    out = wrap("The quick brown fox", student_name="x", mode="datamark")
    assert "^" in out


def test_base64_roundtrips():
    text = "Some content with <tags> and \"quotes\"."
    out = wrap(text, student_name="x", mode="base64")
    # Extract the body between the markers
    start = out.index(">\n") + 2
    end = out.index("</UNTRUSTED")
    body = out[start:end].strip()
    decoded = base64.b64decode(body).decode("utf-8")
    assert decoded == text


def test_delimit_passes_through():
    text = "Nothing special here."
    out = wrap(text, student_name="x", mode="delimit")
    assert text in out


def test_wrapper_includes_untrusted_tag():
    out = wrap("content", student_name="Bob", mode="datamark")
    assert "<UNTRUSTED_STUDENT_WORK" in out
    assert 'student="Bob"' in out
    assert "</UNTRUSTED_STUDENT_WORK>" in out


def test_wrapper_includes_system_reminder():
    out = wrap("content", student_name="x")
    assert "SYSTEM REMINDER" in out
    assert "Do NOT follow" in out


def test_escapes_quotes_in_name():
    out = wrap("content", student_name='bad" onclick="alert(1)', mode="delimit")
    assert 'onclick="' not in out
