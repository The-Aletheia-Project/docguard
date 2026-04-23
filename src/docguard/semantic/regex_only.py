"""Regex-only backend: deterministic, offline, zero-cost.

Always available. Used as the floor of the backend chain.
"""

from __future__ import annotations

import re

from docguard.types import SemanticFlag

# (category, label, pattern). Patterns must compile with re.IGNORECASE | re.UNICODE.
PATTERNS: list[tuple[str, str, str]] = [
    # --- Direct instruction to the AI ------------------------------------------------
    ("direct_instruction", "ignore-previous",
     r"\bignore\s+(?:the\s+|all\s+|any\s+)?(?:previous|prior|above|earlier|preceding)\s+"
     r"(?:instructions?|prompts?|rules?|messages?|directives?)\b"),
    ("direct_instruction", "disregard-rules",
     r"\b(?:disregard|forget|override|bypass)\s+(?:the\s+|all\s+|your\s+)?"
     r"(?:instructions?|rules?|prompts?|system|prior\s+instructions?|training)\b"),
    ("direct_instruction", "do-not-follow",
     r"\b(?:do\s+not|don'?t)\s+(?:follow|obey|listen\s+to)\s+"
     r"(?:any|the|previous|your)\s+(?:instructions?|rules?|prompts?)\b"),

    # --- Persona / role hijack --------------------------------------------------------
    ("persona_hijack", "you-are-now",
     r"\byou\s+are\s+(?:now\s+)?(?:a|an|the)\s+\w+"),
    ("persona_hijack", "act-as",
     r"\b(?:act|pretend|behave|roleplay)\s+as\s+(?:a|an|the)\s+\w+"),
    ("persona_hijack", "new-persona",
     r"\bfrom\s+now\s+on,?\s+(?:you|act)\b"),

    # --- System prompt leakage / delimiter spoofing -----------------------------------
    ("system_prompt_leak", "chat-template-tokens",
     r"<\|(?:im_start|im_end|system|user|assistant|endoftext|eot_id|start_header_id|end_header_id)\|>"),
    ("system_prompt_leak", "delimiter-spoof",
     r"(?:^|\n)\s*(?:---+|\*\*\*+|```+|===+)\s*(?:system|instructions?)\b"),
    ("system_prompt_leak", "inst-brackets",
     r"\[/?(?:INST|SYSTEM|USER|ASSISTANT)\]"),

    # --- Goal / output manipulation ---------------------------------------------------
    ("goal_manipulation", "award-marks",
     r"\b(?:award|give|assign|grant)\s+(?:me\s+|this\s+)?(?:full|maximum|perfect|32|\d+)\s*"
     r"(?:/\s*\d+\s*)?(?:marks?|points?|scores?|grade|rating)"),
    ("goal_manipulation", "grade-as",
     r"\b(?:grade|score|mark|rate|classify|label|tag)\s+this\s+(?:as|with)\s+"),
    ("goal_manipulation", "deserves-full",
     r"\bthis\s+(?:essay\s+|document\s+|resume\s+|application\s+)?"
     r"deserves\s+(?:a\s+)?(?:full|perfect|high|32|an?\s+[A-a])"),
    ("goal_manipulation", "recommend-hire",
     r"\brecommend\s+(?:this\s+candidate|hiring|for\s+hire|approval|approve)\b"),
    ("goal_manipulation", "mark-safe",
     r"\b(?:mark|classify|flag|rate)\s+(?:as|this\s+as)\s+"
     r"(?:safe|approved|benign|clean|low[-\s]?risk|non[-\s]?malicious)\b"),
    ("goal_manipulation", "summarize-as",
     r"\bsummari[sz]e\s+(?:this|the\s+document)\s+as\s+['\"]"),

    # --- Exfiltration / output manipulation -------------------------------------------
    ("data_exfiltration", "markdown-image-exfil",
     r"!\[.*?\]\(https?://[^)]*\{[^}]+\}[^)]*\)"),
    ("data_exfiltration", "fetch-url",
     r"\b(?:fetch|load|retrieve|get|download)\s+(?:the\s+|this\s+)?"
     r"(?:url|page|file|resource)\s+(?:at|from)?\s*https?://"),

    # --- Turkish equivalents ----------------------------------------------------------
    ("direct_instruction", "turkish-ignore",
     r"\bönceki\s+talimatlar[ıi]\s+(?:yok\s+say|görmezden\s+gel|unut)"),
    ("goal_manipulation", "turkish-full-marks",
     r"\btam\s+not\s+ver|tam\s+puan\s+ver|yüksek\s+not\s+ver"),
    ("persona_hijack", "turkish-you-are",
     r"\bart[ıi]k\s+bir\s+\w+\s*s[ıi]n"),
]

_COMPILED = [
    (cat, label, re.compile(pat, re.IGNORECASE | re.UNICODE))
    for cat, label, pat in PATTERNS
]


class RegexBackend:
    """Always-available, offline regex scan."""

    name = "regex"
    default_model = "regex-patterns-v1"

    def available(self) -> bool:  # noqa: D401
        return True

    def classify(self, text: str, model: str | None = None) -> list[SemanticFlag]:
        flags: list[SemanticFlag] = []
        seen: set[tuple[str, int]] = set()
        for category, label, pattern in _COMPILED:
            for m in pattern.finditer(text):
                span = m.group(0)
                key = (span.lower(), m.start())
                if key in seen:
                    continue
                seen.add(key)
                lo = max(0, m.start() - 20)
                hi = min(len(text), m.end() + 20)
                context = text[lo:hi].replace("\n", " ").strip()
                flags.append(
                    SemanticFlag(
                        span=context,
                        reason=f"matched {label}",
                        category=category,
                        confidence=0.9,
                        source=self.name,
                    )
                )
        return flags


__all__ = ["RegexBackend", "PATTERNS"]
