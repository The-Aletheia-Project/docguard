"""Shared dataclasses used across the pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

FileKind = Literal["docx", "pdf"]
SpotlightMode = Literal["datamark", "base64", "delimit"]


@dataclass
class Finding:
    """A single scrub or flag event, for the audit report."""

    part: str  # e.g. "word/document.xml" or "page 3, span 12"
    technique: str  # e.g. "w:vanish (inline)" or "white-ink text"
    original_text: str
    action: Literal["stripped", "flagged", "logged"] = "stripped"
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class SemanticFlag:
    """A visible-content flag from the semantic scan (regex or LLM backend)."""

    span: str
    reason: str
    category: str
    confidence: float
    source: str  # backend name: "regex", "claude-cli", "anthropic", etc


@dataclass
class SanitizeConfig:
    """How the pipeline should run."""

    # Structural strip knobs
    keep_comments: bool = False
    keep_tracked_changes: bool = False
    keep_metadata: bool = False

    # Semantic scan (visible-content flagging)
    semantic: bool = False
    backend: str | None = None  # None = auto-select. Or: "regex", "claude-cli",
                                # "anthropic", "openai", "ollama"
    backend_model: str | None = None  # override the backend's default model

    # Spotlighting
    spotlight_mode: SpotlightMode = "datamark"
    assignment: str = "document"  # context string for the wrapper


@dataclass
class SanitizeResult:
    """Everything the pipeline produces for one input file."""

    source: str
    kind: FileKind
    clean_text: str
    spotlight_text: str
    structural_findings: list[Finding] = field(default_factory=list)
    unicode_findings: dict[str, Any] = field(default_factory=dict)
    semantic_flags: list[SemanticFlag] = field(default_factory=list)
    preamble_notes: list[dict[str, Any]] = field(default_factory=list)

    # Optional: on-disk artefacts produced by the CLI. Empty when used as a library.
    clean_docx_path: str | None = None
    clean_pdf_path: str | None = None
    clean_txt_path: str | None = None
    spotlight_txt_path: str | None = None
    report_json_path: str | None = None

    @property
    def injection_likely(self) -> bool:
        """True if any high-confidence signal fired."""
        if any(f.action == "stripped" for f in self.structural_findings):
            return True
        if any(f.confidence >= 0.5 for f in self.semantic_flags):
            return True
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "kind": self.kind,
            "injection_likely": self.injection_likely,
            "preamble_notes": self.preamble_notes,
            "structural_findings": [
                {
                    "part": f.part,
                    "technique": f.technique,
                    "original_text": f.original_text,
                    "action": f.action,
                    "details": f.details,
                }
                for f in self.structural_findings
            ],
            "unicode": self.unicode_findings,
            "semantic_flags": [
                {
                    "span": s.span,
                    "reason": s.reason,
                    "category": s.category,
                    "confidence": s.confidence,
                    "source": s.source,
                }
                for s in self.semantic_flags
            ],
            "outputs": {
                "clean_docx": self.clean_docx_path,
                "clean_pdf": self.clean_pdf_path,
                "clean_txt": self.clean_txt_path,
                "spotlight_txt": self.spotlight_txt_path,
                "report_json": self.report_json_path,
            },
        }
