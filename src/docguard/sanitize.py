"""docguard public Python API.

    from docguard import sanitize, SanitizeConfig

    result = sanitize("contract.pdf", config=SanitizeConfig(semantic=True))
    result.clean_text
    result.spotlight_text
    result.injection_likely
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from docguard.docx.extractors import (
    NAMESPACES,
    TEXT_BEARING_PARTS,
    find_attached_template,
    find_custom_xml_parts,
    find_doc_variables,
    load_docx,
    save_docx,
    walk_text_elements,
)
from docguard.docx.strippers import StripConfig, strip_all as docx_strip_all
from docguard.semantic.dispatcher import scan as semantic_scan
from docguard.spotlight import wrap as spotlight_wrap
from docguard.types import Finding, SanitizeConfig, SanitizeResult
from docguard.unicode_hygiene import UnicodeReport, clean_parts, clean_text as clean_unicode, log_homoglyphs

_W = NAMESPACES["w"]
_M = NAMESPACES["m"]
_TEXT_TAGS_FQ = (f"{{{_W}}}t", f"{{{_W}}}instrText", f"{{{_M}}}t")
_PARA_FQ = f"{{{_W}}}p"
_BR_FQ = f"{{{_W}}}br"
_TAB_FQ = f"{{{_W}}}tab"


# ---------------------------------------------------------------------------
# Dispatch by file extension
# ---------------------------------------------------------------------------


def _kind_of(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return "docx"
    if suffix == ".pdf":
        return "pdf"
    raise ValueError(f"Unsupported file extension: {suffix!r} (want .docx or .pdf)")


# ---------------------------------------------------------------------------
# DOCX pipeline
# ---------------------------------------------------------------------------


def _extract_docx_plain(parts) -> str:
    chunks: list[str] = []
    for path in TEXT_BEARING_PARTS:
        tree = parts.get(path)
        if tree is None:
            continue
        for para in tree.iter(_PARA_FQ):
            bits: list[str] = []
            for el in para.iter():
                if el.tag in _TEXT_TAGS_FQ and el.text:
                    bits.append(el.text)
                elif el.tag == _BR_FQ:
                    bits.append("\n")
                elif el.tag == _TAB_FQ:
                    bits.append("\t")
            if bits:
                chunks.append("".join(bits))
    return "\n\n".join(c for c in (s.strip() for s in chunks) if c).strip()


def _sanitize_docx(
    src: Path,
    config: SanitizeConfig,
    out_dir: Path | None,
) -> SanitizeResult:
    strip_config = StripConfig(
        keep_comments=config.keep_comments,
        keep_tracked_changes=config.keep_tracked_changes,
        keep_metadata=config.keep_metadata,
    )
    parts = load_docx(src)

    preamble: list[dict[str, Any]] = []
    cxml = find_custom_xml_parts(parts)
    if cxml:
        preamble.append({"technique": "customXml parts present", "paths": cxml})
    dvars = find_doc_variables(parts)
    if dvars:
        preamble.append({
            "technique": "document variables present",
            "vars": [{"name": n, "value": v} for n, v in dvars],
        })
    attached = find_attached_template(parts)
    if attached and attached.startswith(("http://", "https://", "file://", "\\\\")):
        preamble.append({"technique": "attached template (MITRE T1221)", "target": attached})

    structural = docx_strip_all(parts, strip_config)

    uni_report = UnicodeReport()
    clean_parts(parts, uni_report)
    clean_text_out = _extract_docx_plain(parts)
    log_homoglyphs(clean_text_out, uni_report)

    clean_docx_path = None
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        clean_docx_path = out_dir / f"{src.stem}.clean.docx"
        save_docx(parts, clean_docx_path)

    semantic_flags: list = []
    if config.semantic:
        flags, _backend, _err = semantic_scan(
            clean_text_out,
            backend_name=config.backend,
            model=config.backend_model,
        )
        semantic_flags = flags

    spotlight_text = spotlight_wrap(
        clean_text_out,
        student_name=src.stem,
        mode=config.spotlight_mode,
        assignment=config.assignment,
    )

    return SanitizeResult(
        source=str(src),
        kind="docx",
        clean_text=clean_text_out,
        spotlight_text=spotlight_text,
        structural_findings=structural,
        unicode_findings=uni_report.to_dict(),
        semantic_flags=semantic_flags,
        preamble_notes=preamble,
        clean_docx_path=str(clean_docx_path) if clean_docx_path else None,
    )


# ---------------------------------------------------------------------------
# PDF pipeline
# ---------------------------------------------------------------------------


def _sanitize_pdf(
    src: Path,
    config: SanitizeConfig,
    out_dir: Path | None,
) -> SanitizeResult:
    from docguard.pdf.extractors import extract_text
    from docguard.pdf.strippers import PdfStripConfig, clean_in_place, scan_pdf

    pdf_config = PdfStripConfig(
        keep_metadata=config.keep_metadata,
        keep_annotations=config.keep_comments,  # map docx "comments" -> pdf "annotations"
    )
    findings, doc = scan_pdf(src, pdf_config)
    # Clean the doc IN PLACE before extracting text, so extraction returns
    # post-redaction content. Otherwise hidden spans leak into clean_text.
    clean_in_place(doc, findings, pdf_config)
    raw_text = extract_text(doc)

    uni_report = UnicodeReport()
    cleaned = clean_unicode(raw_text, uni_report)
    log_homoglyphs(cleaned, uni_report)

    clean_pdf_path = None
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        clean_pdf_path = out_dir / f"{src.stem}.clean.pdf"
        Path(clean_pdf_path).parent.mkdir(parents=True, exist_ok=True)
        doc.save(str(clean_pdf_path), garbage=4, deflate=True, clean=True)

    semantic_flags = []
    if config.semantic:
        flags, _backend, _err = semantic_scan(
            cleaned,
            backend_name=config.backend,
            model=config.backend_model,
        )
        semantic_flags = flags

    spotlight_text = spotlight_wrap(
        cleaned,
        student_name=src.stem,
        mode=config.spotlight_mode,
        assignment=config.assignment,
    )

    return SanitizeResult(
        source=str(src),
        kind="pdf",
        clean_text=cleaned,
        spotlight_text=spotlight_text,
        structural_findings=findings,
        unicode_findings=uni_report.to_dict(),
        semantic_flags=semantic_flags,
        preamble_notes=[],
        clean_pdf_path=str(clean_pdf_path) if clean_pdf_path else None,
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def sanitize(
    path: str | Path,
    config: SanitizeConfig | None = None,
    out_dir: str | Path | None = None,
) -> SanitizeResult:
    """Sanitize a .docx or .pdf.

    If `out_dir` is provided, cleaned artefacts are written there. Otherwise
    everything is returned in memory on the `SanitizeResult`.
    """
    config = config or SanitizeConfig()
    src = Path(path)
    out = Path(out_dir) if out_dir else None
    kind = _kind_of(src)
    if kind == "docx":
        return _sanitize_docx(src, config, out)
    return _sanitize_pdf(src, config, out)


__all__ = ["sanitize", "SanitizeConfig", "SanitizeResult"]
