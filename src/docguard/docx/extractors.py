"""Raw OOXML walker.

python-docx alone misses at least six vectors for hidden text:
altChunk, mc:AlternateContent fallback branch, custom XML parts,
document variables, OMML math text, and style-chain vanish inheritance.
This module walks the full .docx ZIP and exposes every part as lxml trees.
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from lxml import etree

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"
M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
WP_NS = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
V_NS = "urn:schemas-microsoft-com:vml"

NAMESPACES = {
    "w": W_NS,
    "mc": MC_NS,
    "m": M_NS,
    "r": R_NS,
    "wp": WP_NS,
    "v": V_NS,
}

# Parts we walk for text content. Each can host hidden instructions.
TEXT_BEARING_PARTS = (
    "word/document.xml",
    "word/footnotes.xml",
    "word/endnotes.xml",
    "word/comments.xml",
)


def _q(tag: str) -> str:
    """Qualify a 'prefix:local' tag into Clark notation."""
    prefix, local = tag.split(":")
    return f"{{{NAMESPACES[prefix]}}}{local}"


@dataclass
class DocxParts:
    """All the XML trees we care about, keyed by zip path."""

    trees: dict[str, etree._ElementTree] = field(default_factory=dict)
    raw: dict[str, bytes] = field(default_factory=dict)  # for non-XML parts
    zip_names: list[str] = field(default_factory=list)

    def get(self, path: str) -> etree._ElementTree | None:
        return self.trees.get(path)

    def has(self, path: str) -> bool:
        return path in self.trees or path in self.raw


def load_docx(path: str | Path) -> DocxParts:
    """Load every part of a .docx into memory as parsed XML (where applicable)."""
    parts = DocxParts()
    path = Path(path)
    with zipfile.ZipFile(path, "r") as zf:
        parts.zip_names = zf.namelist()
        for name in parts.zip_names:
            if name.endswith("/"):
                continue
            data = zf.read(name)
            if name.endswith(".xml") or name.endswith(".rels"):
                try:
                    parts.trees[name] = etree.ElementTree(etree.fromstring(data))
                except etree.XMLSyntaxError:
                    parts.raw[name] = data
            else:
                parts.raw[name] = data
    return parts


def save_docx(parts: DocxParts, dest: str | Path) -> None:
    """Write the (possibly modified) parts back to a new .docx."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in parts.zip_names:
            if name.endswith("/"):
                continue
            if name in parts.trees:
                blob = etree.tostring(
                    parts.trees[name],
                    xml_declaration=True,
                    encoding="UTF-8",
                    standalone=True,
                )
                zf.writestr(name, blob)
            elif name in parts.raw:
                zf.writestr(name, parts.raw[name])


# ---------------------------------------------------------------------------
# Text extraction (visits EVERY text-bearing element across all parts)
# ---------------------------------------------------------------------------

# w:t            – normal run text
# w:instrText    – field-code instructions (often abused)
# m:t            – OMML math text
# v:textpath     – VML text on a path (legacy drawings)
TEXT_TAGS = (_q("w:t"), _q("w:instrText"), _q("m:t"))


def walk_runs(tree: etree._ElementTree) -> Iterator[etree._Element]:
    """Yield every w:r element in document order."""
    for r in tree.iter(_q("w:r")):
        yield r


def walk_text_elements(tree: etree._ElementTree) -> Iterator[etree._Element]:
    """Yield every text-bearing leaf element."""
    for el in tree.iter():
        if el.tag in TEXT_TAGS:
            yield el


def run_text(run: etree._Element) -> str:
    """Concatenate all text nodes inside a single w:r."""
    parts = []
    for t in run.iter():
        if t.tag in TEXT_TAGS and t.text:
            parts.append(t.text)
    return "".join(parts)


def paragraph_of(el: etree._Element) -> etree._Element | None:
    """Walk up to the nearest w:p ancestor, or None."""
    node = el.getparent()
    while node is not None:
        if node.tag == _q("w:p"):
            return node
        node = node.getparent()
    return None


# ---------------------------------------------------------------------------
# Extra vectors: altChunk, mc:AlternateContent, custom XML, docVars
# ---------------------------------------------------------------------------


def find_alt_chunks(parts: DocxParts) -> list[str]:
    """Find <w:altChunk> elements and return the list of related target paths."""
    doc = parts.get("word/document.xml")
    if doc is None:
        return []
    rels = parts.get("word/_rels/document.xml.rels")
    rid_to_target: dict[str, str] = {}
    if rels is not None:
        for rel in rels.getroot():
            rid = rel.get("Id")
            target = rel.get("Target")
            if rid and target:
                rid_to_target[rid] = target
    out = []
    for ac in doc.iter(_q("w:altChunk")):
        rid = ac.get(_q("r:id"))
        if rid and rid in rid_to_target:
            out.append(rid_to_target[rid])
    return out


def find_alternate_content(tree: etree._ElementTree) -> list[etree._Element]:
    """Find every mc:AlternateContent block. Strippers will replace with its Choice."""
    return list(tree.iter(_q("mc:AlternateContent")))


def find_custom_xml_parts(parts: DocxParts) -> list[str]:
    """Return paths to customXml/*.xml parts (hidden text reservoir)."""
    return [n for n in parts.zip_names if n.startswith("customXml/") and n.endswith(".xml")]


def find_doc_variables(parts: DocxParts) -> list[tuple[str, str]]:
    """Return [(name, value)] from word/settings.xml w:docVars."""
    settings = parts.get("word/settings.xml")
    if settings is None:
        return []
    out = []
    for dv in settings.iter(_q("w:docVar")):
        name = dv.get(_q("w:name")) or ""
        val = dv.get(_q("w:val")) or ""
        out.append((name, val))
    return out


def find_attached_template(parts: DocxParts) -> str | None:
    """Detect MITRE T1221 template-injection pointer, if present."""
    settings = parts.get("word/settings.xml")
    if settings is None:
        return None
    tmpl = settings.find(f".//{_q('w:attachedTemplate')}")
    if tmpl is None:
        return None
    rid = tmpl.get(_q("r:id"))
    if not rid:
        return None
    rels = parts.get("word/_rels/settings.xml.rels")
    if rels is None:
        return None
    for rel in rels.getroot():
        if rel.get("Id") == rid:
            return rel.get("Target")
    return None


# ---------------------------------------------------------------------------
# Style-chain resolution (for w:vanish inheritance)
# ---------------------------------------------------------------------------


def build_style_vanish_map(parts: DocxParts) -> dict[str, bool]:
    """Return {styleId: True} for every style whose chain resolves to vanish.

    A run inherits vanish if its pStyle/rStyle (or any ancestor basedOn) has it.
    """
    styles = parts.get("word/styles.xml")
    if styles is None:
        return {}

    style_defs: dict[str, dict] = {}
    for s in styles.iter(_q("w:style")):
        sid = s.get(_q("w:styleId"))
        if not sid:
            continue
        based_on = s.find(_q("w:basedOn"))
        based_on_id = based_on.get(_q("w:val")) if based_on is not None else None
        rpr = s.find(_q("w:rPr"))
        has_vanish = rpr is not None and rpr.find(_q("w:vanish")) is not None
        style_defs[sid] = {"basedOn": based_on_id, "vanish": has_vanish}

    resolved: dict[str, bool] = {}

    def resolves_to_vanish(sid: str, seen: set[str]) -> bool:
        if sid in resolved:
            return resolved[sid]
        if sid in seen or sid not in style_defs:
            return False
        seen.add(sid)
        d = style_defs[sid]
        if d["vanish"]:
            resolved[sid] = True
            return True
        parent = d["basedOn"]
        if parent and resolves_to_vanish(parent, seen):
            resolved[sid] = True
            return True
        resolved[sid] = False
        return False

    for sid in style_defs:
        resolves_to_vanish(sid, set())
    return resolved


__all__ = [
    "NAMESPACES",
    "DocxParts",
    "load_docx",
    "save_docx",
    "walk_runs",
    "walk_text_elements",
    "run_text",
    "paragraph_of",
    "find_alt_chunks",
    "find_alternate_content",
    "find_custom_xml_parts",
    "find_doc_variables",
    "find_attached_template",
    "build_style_vanish_map",
    "TEXT_BEARING_PARTS",
]
