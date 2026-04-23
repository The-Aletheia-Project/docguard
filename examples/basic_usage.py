"""Minimal Python usage.

    python examples/basic_usage.py path/to/file.docx
"""

from __future__ import annotations

import sys

from docguard import SanitizeConfig, sanitize


def main(path: str) -> None:
    result = sanitize(path, config=SanitizeConfig(semantic=True))

    print(f"File:          {result.source}")
    print(f"Kind:          {result.kind}")
    print(f"Clean chars:   {len(result.clean_text)}")
    print(f"Stripped:      {sum(1 for f in result.structural_findings if f.action == 'stripped')}")
    print(f"Flagged:       {len(result.semantic_flags)}")
    print(f"Injection likely: {result.injection_likely}")

    if result.injection_likely:
        print("\nFindings:")
        for f in result.structural_findings:
            print(f"  [{f.action}] {f.part}: {f.technique}")
        for s in result.semantic_flags:
            print(f"  [flag/{s.source}] {s.category}: {s.span[:80]}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "README.md")
