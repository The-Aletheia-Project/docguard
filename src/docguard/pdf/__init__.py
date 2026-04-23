"""PDF-specific sanitization. Requires `pip install docguard[pdf]`."""

from docguard.pdf.extractors import extract_text, load_pdf
from docguard.pdf.strippers import strip_all

__all__ = ["extract_text", "load_pdf", "strip_all"]
