"""Structural Layer-2 rules: remove hidden content from a DocxParts tree.

Every strip records a Finding so the report.json has an audit trail.
Rules applied, in order:
  1. Drop mc:Fallback, keep mc:Choice (legacy-compat branch trust)
  2. Remove altChunk imports entirely (rarely legitimate)
  3. Resolve style chain once; mark vanish-inheriting styles
  4. For each w:r:
       - vanish (inline or via style) -> remove
       - near-white text on white doc background -> remove
       - font size below threshold -> remove
  5. Remove text boxes anchored off-page
  6. Optionally strip comments, tracked-change insertions/deletions, metadata
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lxml import etree

from docguard.docx.extractors import (
    DocxParts,
    NAMESPACES,
    TEXT_BEARING_PARTS,
    build_style_vanish_map,
    find_alt_chunks,
    find_alternate_content,
    run_text,
    walk_runs,
)
from docguard.types import Finding

W = NAMESPACES["w"]
MC = NAMESPACES["mc"]
WP = NAMESPACES["wp"]


def _q(tag: str) -> str:
    prefix, local = tag.split(":")
    return f"{{{NAMESPACES[prefix]}}}{local}"


# Near-white threshold. Anything with R,G,B all >= 240 counts as white.
WHITE_THRESHOLD = 240
# Font size threshold in half-points (4 = 2pt). Genuine body text is ~20-24.
MIN_FONT_HALFPOINTS = 4


@dataclass
class StripConfig:
    keep_comments: bool = False
    keep_tracked_changes: bool = False
    keep_metadata: bool = False
    color_mode: str = "default"


# ---------------------------------------------------------------------------
# Helpers: inspect run properties
# ---------------------------------------------------------------------------


def _rpr(run: etree._Element) -> etree._Element | None:
    return run.find(_q("w:rPr"))


def _style_id(run: etree._Element) -> str | None:
    rpr = _rpr(run)
    if rpr is None:
        return None
    rstyle = rpr.find(_q("w:rStyle"))
    if rstyle is None:
        return None
    return rstyle.get(_q("w:val"))


def _pstyle_id(run: etree._Element) -> str | None:
    p = run.getparent()
    while p is not None and p.tag != _q("w:p"):
        p = p.getparent()
    if p is None:
        return None
    ppr = p.find(_q("w:pPr"))
    if ppr is None:
        return None
    pstyle = ppr.find(_q("w:pStyle"))
    if pstyle is None:
        return None
    return pstyle.get(_q("w:val"))


def _has_inline_vanish(run: etree._Element) -> bool:
    rpr = _rpr(run)
    if rpr is None:
        return False
    v = rpr.find(_q("w:vanish"))
    if v is None:
        return False
    # w:val="false" explicitly disables it
    val = v.get(_q("w:val"))
    return val not in ("false", "0")


def _hex_color(run: etree._Element) -> str | None:
    rpr = _rpr(run)
    if rpr is None:
        return None
    c = rpr.find(_q("w:color"))
    if c is None:
        return None
    val = c.get(_q("w:val"))
    if not val or val.lower() == "auto":
        return None
    return val.upper()


def _is_white(color_hex: str) -> bool:
    if len(color_hex) != 6:
        return False
    try:
        r = int(color_hex[0:2], 16)
        g = int(color_hex[2:4], 16)
        b = int(color_hex[4:6], 16)
    except ValueError:
        return False
    return r >= WHITE_THRESHOLD and g >= WHITE_THRESHOLD and b >= WHITE_THRESHOLD


def _font_size_halfpts(run: etree._Element) -> int | None:
    rpr = _rpr(run)
    if rpr is None:
        return None
    sz = rpr.find(_q("w:sz"))
    if sz is None:
        return None
    try:
        return int(sz.get(_q("w:val")) or "")
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Stripping passes
# ---------------------------------------------------------------------------


def strip_alternate_content(parts: DocxParts, findings: list[Finding]) -> None:
    """For each mc:AlternateContent, drop mc:Fallback and inline mc:Choice children.

    We trust the Choice branch (modern Word renders it) and throw away Fallback,
    which sneaky docs can populate differently.
    """
    for part_path in TEXT_BEARING_PARTS + ("word/header1.xml", "word/footer1.xml"):
        tree = parts.get(part_path)
        if tree is None:
            continue
        for block in find_alternate_content(tree):
            choice = block.find(_q("mc:Choice"))
            fallback = block.find(_q("mc:Fallback"))
            if fallback is not None:
                text = "".join(t.text or "" for t in fallback.iter() if t.tag.endswith("}t"))
                if text.strip():
                    findings.append(
                        Finding(
                            part=part_path,
                            technique="mc:Fallback branch discarded",
                            original_text=text[:500],
                            details={"choice_present": choice is not None},
                        )
                    )
            parent = block.getparent()
            if parent is None:
                continue
            idx = list(parent).index(block)
            # Splice Choice children in place; drop Fallback entirely.
            if choice is not None:
                for i, child in enumerate(list(choice)):
                    parent.insert(idx + i, child)
            parent.remove(block)


def strip_alt_chunks(parts: DocxParts, findings: list[Finding]) -> None:
    """Remove every w:altChunk element and its referenced zip entry."""
    doc = parts.get("word/document.xml")
    if doc is None:
        return
    targets = find_alt_chunks(parts)
    for ac in list(doc.iter(_q("w:altChunk"))):
        parent = ac.getparent()
        if parent is not None:
            parent.remove(ac)
        findings.append(
            Finding(
                part="word/document.xml",
                technique="w:altChunk removed",
                original_text="(altChunk import)",
                details={"targets": targets},
            )
        )
    # Drop imported files from the zip we'll re-emit.
    for tgt in targets:
        full = f"word/{tgt}" if not tgt.startswith("word/") else tgt
        for candidate in (tgt, full):
            parts.raw.pop(candidate, None)
            parts.trees.pop(candidate, None)
            if candidate in parts.zip_names:
                parts.zip_names.remove(candidate)


def strip_runs_by_rules(
    parts: DocxParts, findings: list[Finding], config: StripConfig
) -> None:
    """Remove w:r elements that are vanish, white-on-white, or sub-threshold size."""
    vanish_styles = build_style_vanish_map(parts)

    for part_path in ("word/document.xml", "word/footnotes.xml", "word/endnotes.xml",
                      "word/header1.xml", "word/header2.xml", "word/header3.xml",
                      "word/footer1.xml", "word/footer2.xml", "word/footer3.xml"):
        tree = parts.get(part_path)
        if tree is None:
            continue
        runs_to_remove: list[tuple[etree._Element, Finding]] = []
        for run in walk_runs(tree):
            text = run_text(run)
            if not text.strip():
                continue  # whitespace-only runs are harmless

            reason = None
            details: dict[str, Any] = {}

            if _has_inline_vanish(run):
                reason = "w:vanish (inline)"
            else:
                rid = _style_id(run) or _pstyle_id(run)
                if rid and vanish_styles.get(rid):
                    reason = "w:vanish (via style chain)"
                    details["style"] = rid

            if reason is None:
                color = _hex_color(run)
                if color and _is_white(color):
                    reason = "near-white text on white background"
                    details["color"] = color

            if reason is None:
                sz = _font_size_halfpts(run)
                if sz is not None and sz < MIN_FONT_HALFPOINTS:
                    reason = f"font size {sz/2}pt below threshold"
                    details["halfpoints"] = sz

            if reason:
                runs_to_remove.append(
                    (
                        run,
                        Finding(
                            part=part_path,
                            technique=reason,
                            original_text=text[:500],
                            details=details,
                        ),
                    )
                )

        for run, finding in runs_to_remove:
            parent = run.getparent()
            if parent is not None:
                parent.remove(run)
            findings.append(finding)


def strip_off_page_textboxes(parts: DocxParts, findings: list[Finding]) -> None:
    """Remove wp:anchor drawings positioned off-page (>2x page in any axis)."""
    doc = parts.get("word/document.xml")
    if doc is None:
        return
    # Cheap heuristic: look for positionOffset values with unreasonably large magnitudes.
    # Word EMU: 914400 per inch; a page is typically ~7.5 inches wide => ~6_858_000 EMU.
    THRESHOLD_EMU = 15_000_000  # ~16 inches offset = well off-page in any direction
    for anchor in doc.iter(_q("wp:anchor")):
        bad = False
        for off in anchor.iter(_q("wp:positionOffset")):
            try:
                val = int((off.text or "0").strip())
            except ValueError:
                continue
            if abs(val) > THRESHOLD_EMU:
                bad = True
                break
        if bad:
            text = "".join(
                t.text or "" for t in anchor.iter() if t.tag.endswith("}t") and t.text
            )
            parent = anchor.getparent()
            if parent is not None:
                parent.remove(anchor)
            findings.append(
                Finding(
                    part="word/document.xml",
                    technique="off-page wp:anchor removed",
                    original_text=text[:500] or "(empty drawing)",
                )
            )


def strip_comments(parts: DocxParts, findings: list[Finding]) -> None:
    """Remove the comments part entirely, and comment-range markers in document.xml."""
    comments = parts.get("word/comments.xml")
    if comments is not None:
        count = len(list(comments.iter(_q("w:comment"))))
        if count:
            findings.append(
                Finding(
                    part="word/comments.xml",
                    technique=f"{count} comment(s) stripped",
                    original_text="(comments)",
                )
            )
        parts.trees.pop("word/comments.xml", None)
        if "word/comments.xml" in parts.zip_names:
            parts.zip_names.remove("word/comments.xml")
    for part_path in ("word/document.xml",):
        tree = parts.get(part_path)
        if tree is None:
            continue
        for tag in ("w:commentRangeStart", "w:commentRangeEnd", "w:commentReference"):
            for el in list(tree.iter(_q(tag))):
                parent = el.getparent()
                if parent is not None:
                    parent.remove(el)


def strip_tracked_changes(parts: DocxParts, findings: list[Finding]) -> None:
    """Accept all: keep w:ins content, drop w:del content."""
    for part_path in ("word/document.xml", "word/header1.xml", "word/footer1.xml"):
        tree = parts.get(part_path)
        if tree is None:
            continue
        # Unwrap w:ins (keep children).
        for ins in list(tree.iter(_q("w:ins"))):
            parent = ins.getparent()
            if parent is None:
                continue
            idx = list(parent).index(ins)
            for i, child in enumerate(list(ins)):
                parent.insert(idx + i, child)
            parent.remove(ins)
        # Drop w:del entirely.
        deleted_count = 0
        for d in list(tree.iter(_q("w:del"))):
            parent = d.getparent()
            if parent is None:
                continue
            parent.remove(d)
            deleted_count += 1
        if deleted_count:
            findings.append(
                Finding(
                    part=part_path,
                    technique=f"{deleted_count} tracked-delete block(s) discarded",
                    original_text="(tracked changes)",
                )
            )


def strip_metadata(parts: DocxParts, findings: list[Finding]) -> None:
    """Blank out core.xml and app.xml custom properties."""
    for path in ("docProps/core.xml", "docProps/app.xml", "docProps/custom.xml"):
        tree = parts.get(path)
        if tree is None:
            continue
        stripped = False
        for el in tree.iter():
            if el.text and el.text.strip():
                el.text = ""
                stripped = True
        if stripped:
            findings.append(
                Finding(
                    part=path,
                    technique="metadata fields cleared",
                    original_text="(metadata)",
                )
            )


def strip_all(parts: DocxParts, config: StripConfig | None = None) -> list[Finding]:
    """Run every structural pass. Returns the list of Findings."""
    config = config or StripConfig()
    findings: list[Finding] = []
    strip_alternate_content(parts, findings)
    strip_alt_chunks(parts, findings)
    strip_runs_by_rules(parts, findings, config)
    strip_off_page_textboxes(parts, findings)
    if not config.keep_tracked_changes:
        strip_tracked_changes(parts, findings)
    if not config.keep_comments:
        strip_comments(parts, findings)
    if not config.keep_metadata:
        strip_metadata(parts, findings)
    return findings


__all__ = ["StripConfig", "strip_all"]
