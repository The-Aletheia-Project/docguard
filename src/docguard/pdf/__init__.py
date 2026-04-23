"""PDF-specific sanitization. Requires `pip install docguard[pdf]`."""

from docguard.pdf.extractors import extract_text, load_pdf
from docguard.pdf.strippers import strip_all

__all__ = ["load_pdf", "extract_text", "strip_all"]
