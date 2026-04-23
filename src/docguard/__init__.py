"""docguard — scrub hidden prompt injections from .docx and .pdf before feeding
them to an LLM.

Public API:
    from docguard import sanitize, SanitizeConfig, SanitizeResult

Command-line:
    docguard FILE [--out DIR] [--semantic] [--backend NAME]
"""

from docguard.sanitize import sanitize
from docguard.types import (
    Finding,
    SanitizeConfig,
    SanitizeResult,
    SemanticFlag,
    SpotlightMode,
)

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "sanitize",
    "SanitizeConfig",
    "SanitizeResult",
    "SemanticFlag",
    "Finding",
    "SpotlightMode",
]
