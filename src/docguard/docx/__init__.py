"""DOCX-specific sanitization."""

from docguard.docx.extractors import DocxParts, load_docx, save_docx
from docguard.docx.strippers import strip_all

__all__ = ["DocxParts", "load_docx", "save_docx", "strip_all"]
