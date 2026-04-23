"""A LangChain DocumentLoader that sanitises before emitting documents.

    pip install docguard[pdf] langchain-core

Then:

    from examples.langchain_loader import GuardedDocGuardLoader
    docs = GuardedDocGuardLoader("contract.pdf").load()
    # docs[0].page_content is spotlight-wrapped and safe to feed to an LLM
    # docs[0].metadata["injection_likely"] tells you whether anything was found
"""

from __future__ import annotations

from typing import Iterable

from langchain_core.document_loaders import BaseLoader
from langchain_core.documents import Document

from docguard import SanitizeConfig, sanitize


class GuardedDocGuardLoader(BaseLoader):
    """Load a .docx or .pdf, sanitise, and return one Document."""

    def __init__(
        self,
        path: str,
        *,
        semantic: bool = True,
        backend: str | None = None,
        spotlight_mode: str = "datamark",
    ) -> None:
        self.path = path
        self.config = SanitizeConfig(
            semantic=semantic,
            backend=backend,
            spotlight_mode=spotlight_mode,
        )

    def lazy_load(self) -> Iterable[Document]:
        result = sanitize(self.path, config=self.config)
        yield Document(
            page_content=result.spotlight_text,
            metadata={
                "source": self.path,
                "kind": result.kind,
                "injection_likely": result.injection_likely,
                "stripped_count": sum(
                    1 for f in result.structural_findings if f.action == "stripped"
                ),
                "flag_count": len(result.semantic_flags),
            },
        )

    def load(self) -> list[Document]:
        return list(self.lazy_load())
