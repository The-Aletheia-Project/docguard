"""A LlamaIndex Reader that sanitises before yielding Documents.

    pip install docguard[pdf] llama-index-core

Usage:

    from examples.llamaindex_reader import GuardedReader
    docs = GuardedReader().load_data("contract.pdf")
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from llama_index.core.readers.base import BaseReader
from llama_index.core.schema import Document

from docguard import SanitizeConfig, sanitize


class GuardedReader(BaseReader):
    """Sanitises .docx and .pdf before emitting LlamaIndex Documents."""

    def __init__(
        self,
        *,
        semantic: bool = True,
        backend: str | None = None,
    ) -> None:
        self.config = SanitizeConfig(semantic=semantic, backend=backend)

    def load_data(self, file: Path | str, **kwargs: Any) -> list[Document]:
        path = Path(file) if isinstance(file, str) else file
        result = sanitize(path, config=self.config)
        return [
            Document(
                text=result.spotlight_text,
                metadata={
                    "source": str(path),
                    "kind": result.kind,
                    "injection_likely": result.injection_likely,
                },
            )
        ]
