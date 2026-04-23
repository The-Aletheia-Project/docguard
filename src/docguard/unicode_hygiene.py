"""Unicode Layer-3 hygiene: normalize + strip invisible attack carriers.

Applied to (a) run text inside the cleaned docx and (b) the plain .clean.txt.

We STRIP silently:
  - Unicode Tags block        U+E0000..U+E007F
  - Variant selectors         U+FE00..U+FE0F, U+E0100..U+E01EF
  - Bidi overrides/isolates   U+202A..U+202E, U+2066..U+2069
  - Zero-width / invisible    U+200B..U+200F, U+2060..U+206F, U+FEFF, U+180E

We LOG but do NOT strip:
  - Homoglyphs (confusables) — false-positive risk on Turkish too high
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# One regex, one pass. Covers every invisible attack carrier used in 2024-26 PoCs.
_INVISIBLE_RE = re.compile(
    "["
    "​-‏"       # zero-width space/non-joiner/joiner, LRM/RLM
    " - "       # line/paragraph separator
    "‪-‮"       # embedding + overrides
    "⁠-⁯"       # word joiner, invisible times/plus/comma/separator, formatting
    "﻿"              # BOM / zero-width no-break space
    "᠎"              # mongolian vowel separator
    "︀-️"       # variant selectors 1-16
    "]|"
    "[\U000e0000-\U000e007f]|"   # Unicode Tags block
    "[\U000e0100-\U000e01ef]"    # Variant selectors 17-256
)


@dataclass
class UnicodeReport:
    tag_block_chars: int = 0
    variant_selectors: int = 0
    bidi_overrides: int = 0
    zero_width: int = 0
    total_chars_removed: int = 0
    homoglyphs_logged: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "tag_block_chars": self.tag_block_chars,
            "variant_selectors": self.variant_selectors,
            "bidi_overrides": self.bidi_overrides,
            "zero_width": self.zero_width,
            "total_chars_removed": self.total_chars_removed,
            "homoglyphs_logged": self.homoglyphs_logged,
        }


def _classify(ch: str) -> str:
    cp = ord(ch)
    if 0xE0000 <= cp <= 0xE007F:
        return "tag_block_chars"
    if 0xFE00 <= cp <= 0xFE0F or 0xE0100 <= cp <= 0xE01EF:
        return "variant_selectors"
    if 0x202A <= cp <= 0x202E or 0x2066 <= cp <= 0x2069:
        return "bidi_overrides"
    return "zero_width"


def clean_text(text: str, report: UnicodeReport | None = None) -> str:
    """NFKC normalize + strip invisible carriers. Optionally update a report."""
    if not text:
        return text
    if report is not None:
        for ch in _INVISIBLE_RE.findall(text):
            for c in ch:
                bucket = _classify(c)
                setattr(report, bucket, getattr(report, bucket) + 1)
                report.total_chars_removed += 1
    # Strip first, THEN normalize. NFKC can produce new characters from composition;
    # we don't want those freshly-minted invisible carriers smuggled in.
    stripped = _INVISIBLE_RE.sub("", text)
    normalized = unicodedata.normalize("NFKC", stripped)
    return normalized


def log_homoglyphs(text: str, report: UnicodeReport) -> None:
    """Detect confusable (non-Latin-looking-like-Latin) characters; LOG only, do not strip."""
    try:
        from confusable_homoglyphs import confusables
    except ImportError:
        return  # optional dep, soft-fail

    # `is_confusable` returns a list of {character, alias, homoglyphs[]} dicts.
    # The `greedy` kwarg (return every hit, not just the first) is supported in
    # recent versions but may be absent in older ones — try with it, then without.
    try:
        hits = confusables.is_confusable(text, greedy=True) or []
    except TypeError:
        hits = confusables.is_confusable(text) or []

    seen: set[str] = set()
    for hit in hits:
        ch = hit.get("character")
        if not ch or ch in seen:
            continue
        seen.add(ch)
        try:
            name = unicodedata.name(ch)
        except ValueError:
            name = "?"
        report.homoglyphs_logged.append(
            {
                "char": ch,
                "codepoint": f"U+{ord(ch):04X}",
                "name": name,
                "looks_like": [h.get("character") for h in hit.get("homoglyphs", [])][:3],
            }
        )


# ---------------------------------------------------------------------------
# In-place cleaning of a DocxParts text node
# ---------------------------------------------------------------------------


def clean_parts(parts, report: UnicodeReport) -> None:
    """Mutate every w:t / w:instrText / m:t text node inside the docx trees."""
    from docguard.docx.extractors import TEXT_BEARING_PARTS, walk_text_elements

    header_footer_paths = [n for n in parts.zip_names if
                           n.startswith("word/header") or n.startswith("word/footer")]
    for path in list(TEXT_BEARING_PARTS) + header_footer_paths:
        tree = parts.get(path)
        if tree is None:
            continue
        for el in walk_text_elements(tree):
            if el.text:
                el.text = clean_text(el.text, report)


__all__ = ["UnicodeReport", "clean_parts", "clean_text", "log_homoglyphs"]
