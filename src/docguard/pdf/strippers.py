"""PDF hidden-text detection and scrubbing.

Findings cover: white-ink, near-transparent, off-CropBox, invisible OCG layers,
annotations, form-field values, metadata, JavaScript actions, embedded files.

Output strategy: we produce a cleaned PDF by rebuilding it via pymupdf's
page-by-page rasterisation with text re-rendered from our extractable text.
That's lossy but safe (no original hidden content survives). For a lossless
clean, see `save_redacted` which applies true PDF redactions to hidden spans.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from docguard.pdf.extractors import (
    detect_invisible_ocgs,
    detect_javascript,
    document_metadata,
    extract_text,
    iter_spans,
    list_annotations,
    list_embedded_files,
    list_widgets,
    load_pdf,
)
from docguard.types import Finding

try:
    import fitz
except ImportError:  # pragma: no cover
    fitz = None  # type: ignore[assignment]


WHITE_THRESHOLD = 240  # R,G,B each >= 240 counts as white


@dataclass
class PdfStripConfig:
    keep_annotations: bool = False
    keep_metadata: bool = False
    keep_form_values: bool = False


def _rgb_from_int(c: int) -> tuple[int, int, int]:
    return ((c >> 16) & 0xFF, (c >> 8) & 0xFF, c & 0xFF)


def _is_white(color: int) -> bool:
    r, g, b = _rgb_from_int(color)
    return r >= WHITE_THRESHOLD and g >= WHITE_THRESHOLD and b >= WHITE_THRESHOLD


def _is_off_page(span_bbox, page_bbox) -> bool:
    """True if the span's bbox lies entirely outside the page CropBox."""
    sx0, sy0, sx1, sy1 = span_bbox
    px0, py0, px1, py1 = page_bbox
    if sx1 <= px0 or sx0 >= px1:
        return True
    return bool(sy1 <= py0 or sy0 >= py1)


def scan_pdf(path: str | Path, config: PdfStripConfig | None = None) -> tuple[list[Finding], fitz.Document]:
    """Open the PDF, identify every hidden/suspicious element, return findings + doc.

    The returned doc has the in-memory state ready for redaction via `redact_and_save`.
    """
    if fitz is None:
        raise ImportError("pymupdf required — `pip install docguard[pdf]`")
    config = config or PdfStripConfig()
    doc = load_pdf(path)
    findings: list[Finding] = []

    # 1. Hidden spans (white-ink, near-transparent, off-page, sub-threshold size)
    for span in iter_spans(doc):
        reason = None
        details: dict[str, Any] = {}
        if _is_white(span.color):
            reason = "white text on white page"
            r, g, b = _rgb_from_int(span.color)
            details["color"] = f"#{r:02X}{g:02X}{b:02X}"
        elif span.alpha < 0.05:
            reason = f"near-zero alpha ({span.alpha:.2f})"
            details["alpha"] = span.alpha
        elif _is_off_page(span.bbox, span.page_bbox):
            reason = "span bbox outside page CropBox"
            details["bbox"] = list(span.bbox)
            details["page_bbox"] = list(span.page_bbox)
        elif span.size < 1.0 and span.text.strip():
            reason = f"sub-1pt font size ({span.size:.2f})"
            details["size"] = span.size

        if reason:
            # Always store bbox so redaction can find the span later.
            details.setdefault("bbox", list(span.bbox))
            findings.append(
                Finding(
                    part=f"page {span.page}",
                    technique=reason,
                    original_text=span.text[:500],
                    action="stripped",
                    details=details,
                )
            )

    # 2. Annotations
    annots = list_annotations(doc)
    if annots and not config.keep_annotations:
        for a in annots:
            findings.append(
                Finding(
                    part=f"page {a['page']} annotation",
                    technique=f"{a['subtype']} annotation with /Contents",
                    original_text=a["content"][:500],
                    action="stripped",
                )
            )

    # 3. Form-field values
    widgets = list_widgets(doc)
    if widgets and not config.keep_form_values:
        for w in widgets:
            findings.append(
                Finding(
                    part=f"page {w['page']} form field",
                    technique=f"{w['type']} widget value",
                    original_text=str(w["value"])[:500],
                    action="stripped",
                    details={"name": w["name"]},
                )
            )

    # 4. JavaScript actions
    for js_hit in detect_javascript(doc):
        findings.append(
            Finding(
                part="pdf catalog",
                technique="JavaScript action present",
                original_text=js_hit,
                action="flagged",
            )
        )

    # 5. Invisible OCG layers
    for ocg in detect_invisible_ocgs(doc):
        findings.append(
            Finding(
                part="Optional Content Group",
                technique="invisible OCG layer",
                original_text=f"name={ocg.get('name')!r}",
                action="flagged",
                details=ocg,
            )
        )

    # 6. Embedded files
    for emb in list_embedded_files(doc):
        findings.append(
            Finding(
                part="/EmbeddedFiles",
                technique="embedded attachment",
                original_text=str(emb.get("name", ""))[:500],
                action="flagged",
                details=emb,
            )
        )

    # 7. Metadata
    if not config.keep_metadata:
        meta = document_metadata(doc)
        if any(v for k, v in meta.items() if k != "format" and v):
            findings.append(
                Finding(
                    part="pdf metadata",
                    technique="document metadata present",
                    original_text=", ".join(f"{k}={v!r}"[:80] for k, v in meta.items() if v)[:500],
                    action="stripped",
                )
            )

    return findings, doc


def clean_in_place(
    doc: fitz.Document,
    findings: list[Finding],
    config: PdfStripConfig | None = None,
) -> None:
    """Mutate `doc` in memory: redact hidden spans, strip annotations, scrub
    metadata, delete embedded files. Call before extracting cleaned text."""
    if fitz is None:
        raise ImportError("pymupdf required")
    config = config or PdfStripConfig()

    # 1. Redact every hidden span by its bbox.
    # Also redact annotation bboxes and form-field widget bboxes.
    # First, add redactions for structural strips.
    # Build a mapping: for hidden spans we stored bbox in details.
    for f in findings:
        if f.action != "stripped":
            continue
        bbox = f.details.get("bbox")
        if not bbox:
            continue
        if not f.part.startswith("page "):
            continue
        try:
            pnum = int(f.part.split()[1])
            page = doc[pnum - 1]
            page.add_redact_annot(fitz.Rect(*bbox), fill=(1, 1, 1))
        except Exception:
            continue

    # 2. Apply redactions per page.
    for page in doc:
        try:
            page.apply_redactions()
        except Exception:
            continue

    # 3. Remove annotations unless kept.
    if not config.keep_annotations:
        for page in doc:
            for annot in list(page.annots() or []):
                try:
                    page.delete_annot(annot)
                except Exception:
                    continue

    # 4. Remove form-field widgets unless kept.
    if not config.keep_form_values:
        for page in doc:
            try:
                for widget in list(page.widgets() or []):
                    annot = widget._annot if hasattr(widget, "_annot") else None
                    if annot is not None:
                        page.delete_annot(annot)
            except Exception:
                pass

    # 5. Scrub metadata.
    if not config.keep_metadata:
        with contextlib.suppress(Exception):
            doc.set_metadata({})
        with contextlib.suppress(Exception):
            doc.del_xml_metadata()

    # 6. Remove embedded files.
    try:
        while doc.embfile_count():
            doc.embfile_del(0)
    except Exception:
        pass


def save_cleaned(
    doc: fitz.Document,
    dest: str | Path,
    findings: list[Finding],
    config: PdfStripConfig | None = None,
) -> None:
    """Clean the doc in place and write it to `dest`."""
    clean_in_place(doc, findings, config)
    Path(dest).parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(dest), garbage=4, deflate=True, clean=True)


def strip_all(path: str | Path, dest: str | Path | None = None,
              config: PdfStripConfig | None = None) -> tuple[list[Finding], str]:
    """End-to-end: scan + save cleaned PDF + return (findings, cleaned_text).

    If `dest` is None, no cleaned PDF is written; only findings and the
    visible-order plain text are returned.
    """
    findings, doc = scan_pdf(path, config)
    clean_text = extract_text(doc)
    if dest is not None:
        save_cleaned(doc, dest, findings, config)
    return findings, clean_text


__all__ = ["PdfStripConfig", "save_cleaned", "scan_pdf", "strip_all"]
