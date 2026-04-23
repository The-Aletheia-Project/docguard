"""Multi-backend semantic scan for visible-content flagging.

Backends all implement the same `classify(text) -> list[SemanticFlag]` shape.
The dispatcher picks one automatically based on available env and tools.
"""

from docguard.semantic.base import SemanticBackend, BackendUnavailable
from docguard.semantic.dispatcher import (
    available_backends,
    get_backend,
    scan,
)

__all__ = [
    "SemanticBackend",
    "BackendUnavailable",
    "available_backends",
    "get_backend",
    "scan",
]
