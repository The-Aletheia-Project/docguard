"""Shared pytest fixtures."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"


def _run(script: Path) -> None:
    subprocess.check_call([sys.executable, str(script)])


@pytest.fixture(scope="session")
def poisoned_docx() -> Path:
    """Generate (once per session) the poisoned .docx test fixture."""
    path = FIXTURES / "poisoned.docx"
    if not path.exists():
        _run(ROOT / "tools" / "make_poisoned_docx.py")
    assert path.exists(), f"failed to create {path}"
    return path


@pytest.fixture(scope="session")
def poisoned_pdf() -> Path:
    """Generate (once per session) the poisoned .pdf test fixture."""
    pytest.importorskip("fitz")
    pytest.importorskip("reportlab")
    path = FIXTURES / "poisoned.pdf"
    if not path.exists():
        _run(ROOT / "tools" / "make_poisoned_pdf.py")
    assert path.exists(), f"failed to create {path}"
    return path


@pytest.fixture
def tmp_out(tmp_path) -> Path:
    d = tmp_path / "out"
    d.mkdir()
    return d
