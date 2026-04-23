"""PDF extractor using pymupdf (fitz).

`page.get_text("rawdict")` returns per-span color, bbox, alpha, font, flags —
the richest introspection available from pymupdf. We use it for both text
extraction and hidden-span detection.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import fitz  # pymupdf
except ImportError as e:  # pragma: no cover
    raise ImportError(
        "docguard.pdf requires pymupdf — `pip install docguard[pdf]`"
    ) from e


@dataclass
class Span:
    """One text run on a page. Carries everything we need to judge visibility."""

    page: int
    text: str
    bbox: tuple[float, float, float, float]  # x0, y0, x1, y1
    color: int  # 24-bit RGB, 0xRRGGBB
    alpha: float  # 0.0 = fully transparent; 1.0 = opaque
    size: float
    font: str
    flags: int  # fitz flag bits
    page_bbox: tuple[float, float, float, float]  # the page CropBox


def load_pdf(path: str | Path) -> "fitz.Document":
    return fitz.open(str(path))


def iter_spans(doc: "fitz.Document") -> list[Span]:
    """Walk every text span across every page."""
    out: list[Span] = []
    for pnum, page in enumerate(doc, start=1):
        raw = page.get_text("rawdict")
        page_bbox = tuple(page.rect)  # noqa: RUF005
        for block in raw.get("blocks", []):
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    chars = span.get("chars", [])
                    text = "".join(c.get("c", "") for c in chars)
                    if not text.strip():
                        continue
                    bbox = tuple(span.get("bbox", (0, 0, 0, 0)))
                    # pymupdf returns alpha as 0-255 int; normalise to 0.0-1.0.
                    raw_alpha = span.get("alpha", 255)
                    alpha_f = float(raw_alpha) / 255.0 if raw_alpha > 1 else float(raw_alpha)
                    out.append(
                        Span(
                            page=pnum,
                            text=text,
                            bbox=bbox,  # type: ignore[arg-type]
                            color=int(span.get("color", 0)),
                            alpha=max(0.0, min(1.0, alpha_f)),
                            size=float(span.get("size", 0)),
                            font=str(span.get("font", "")),
                            flags=int(span.get("flags", 0)),
                            page_bbox=page_bbox,  # type: ignore[arg-type]
                        )
                    )
    return out


def extract_text(doc: "fitz.Document") -> str:
    """Visible-order plain text — what a reader sees when viewing the PDF."""
    pages = []
    for page in doc:
        pages.append(page.get_text("text"))
    return "\n\n".join(pages).strip()


def document_metadata(doc: "fitz.Document") -> dict[str, Any]:
    """Standard and XMP metadata."""
    meta = dict(doc.metadata or {})
    try:
        xml = doc.get_xml_metadata()  # pymupdf method
        if xml:
            meta["xmp"] = xml
    except Exception:  # noqa: BLE001
        pass
    return meta


def list_annotations(doc: "fitz.Document") -> list[dict[str, Any]]:
    """Collect annotation contents — comments, notes, markup text."""
    out = []
    for pnum, page in enumerate(doc, start=1):
        for annot in page.annots() or []:
            info = annot.info or {}
            content = info.get("content", "")
            subtype = annot.type[1] if annot.type else "Unknown"
            if content:
                out.append({"page": pnum, "subtype": subtype, "content": content})
    return out


def list_widgets(doc: "fitz.Document") -> list[dict[str, Any]]:
    """Collect form-field values and defaults."""
    out = []
    for pnum, page in enumerate(doc, start=1):
        for w in page.widgets() or []:
            val = w.field_value or ""
            if val:
                out.append({
                    "page": pnum,
                    "name": w.field_name or "",
                    "type": w.field_type_string,
                    "value": val,
                })
    return out


def list_embedded_files(doc: "fitz.Document") -> list[dict[str, Any]]:
    """Attached / embedded files."""
    out = []
    try:
        count = doc.embfile_count()
    except Exception:  # noqa: BLE001
        return out
    for i in range(count):
        try:
            info = doc.embfile_info(i)
            out.append({
                "name": info.get("filename", f"embedded_{i}"),
                "size": info.get("size", 0),
                "desc": info.get("desc", ""),
            })
        except Exception:  # noqa: BLE001
            continue
    return out


def detect_javascript(doc: "fitz.Document") -> list[str]:
    """Any /JavaScript actions in the document. We flag presence only."""
    hits: list[str] = []
    try:
        xref_count = doc.xref_length()
    except Exception:  # noqa: BLE001
        return hits
    for xref in range(1, xref_count):
        try:
            js = doc.xref_get_key(xref, "JS") if hasattr(doc, "xref_get_key") else None
        except Exception:  # noqa: BLE001
            js = None
        if js and js[0] != "null":
            hits.append(f"xref {xref}: /JS key present")
    return hits


def detect_invisible_ocgs(doc: "fitz.Document") -> list[dict[str, Any]]:
    """Optional Content Groups (layers) marked off by default."""
    out: list[dict[str, Any]] = []
    try:
        ocg_cfg = doc.get_ocgs()
    except Exception:  # noqa: BLE001
        return out
    for xref, info in (ocg_cfg or {}).items():
        # info is a dict like {"name": ..., "on": bool, ...}
        if isinstance(info, dict) and info.get("on") is False:
            out.append({"xref": xref, "name": info.get("name", "")})
    return out


__all__ = [
    "Span",
    "load_pdf",
    "iter_spans",
    "extract_text",
    "document_metadata",
    "list_annotations",
    "list_widgets",
    "list_embedded_files",
    "detect_javascript",
    "detect_invisible_ocgs",
]
