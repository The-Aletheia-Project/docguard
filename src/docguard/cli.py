#!/usr/bin/env python
"""docguard CLI.

Usage:
  docguard INPUT [--out DIR] [options]
  docguard --batch 'pattern/*.docx' --out DIR [options]

Options:
  --semantic             enable visible-content flagging (regex + LLM backend)
  --backend NAME         regex | claude-cli | anthropic | openai | ollama
  --model MODEL          backend-specific model id (overrides default)
  --spotlight-mode MODE  datamark | base64 | delimit  (default: datamark)
  --assignment TEXT      context string embedded in the spotlight wrapper
  --keep-comments        preserve .docx comments / .pdf annotations
  --keep-tracked-changes preserve tracked changes (.docx)
  --keep-metadata        preserve document metadata
  --list-backends        print which backends are available on this machine
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
import traceback
from pathlib import Path

from docguard.report import append_summary, write_report
from docguard.sanitize import sanitize
from docguard.types import SanitizeConfig


def _run_one(src: Path, out_dir: Path, config: SanitizeConfig) -> dict:
    result = sanitize(src, config=config, out_dir=out_dir)

    # Emit plain .txt + spotlight .txt + report.json
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = src.stem
    clean_txt = out_dir / f"{stem}.clean.txt"
    clean_txt.write_text(result.clean_text, encoding="utf-8")
    result.clean_txt_path = str(clean_txt)

    spot_txt = out_dir / f"{stem}.spotlight.txt"
    spot_txt.write_text(result.spotlight_text, encoding="utf-8")
    result.spotlight_txt_path = str(spot_txt)

    report_path = out_dir / f"{stem}.report.json"
    write_report(report_path, result.to_dict())
    result.report_json_path = str(report_path)

    return {
        "file": src.name,
        "kind": result.kind,
        "structural_strips": sum(1 for f in result.structural_findings if f.action == "stripped"),
        "structural_flags": sum(1 for f in result.structural_findings if f.action != "stripped"),
        "unicode_chars_removed": result.unicode_findings.get("total_chars_removed", 0),
        "homoglyphs_logged": len(result.unicode_findings.get("homoglyphs_logged", [])),
        "regex_flags": sum(1 for s in result.semantic_flags if s.source == "regex"),
        "llm_flags": sum(1 for s in result.semantic_flags if s.source != "regex"),
        "injection_likely": "YES" if result.injection_likely else "no",
        "error": "",
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="docguard",
        description="Scrub hidden prompt injections from .docx and .pdf.",
    )
    p.add_argument("input", nargs="?", help="a single .docx or .pdf (or use --batch)")
    p.add_argument("--batch", help="glob pattern for batch mode, e.g. 'inbox/*.pdf'")
    p.add_argument("--out", help="output directory (required for single-file or batch)")
    p.add_argument("--semantic", action="store_true",
                   help="enable visible-content flagging (regex + LLM backend)")
    p.add_argument("--backend", choices=("regex", "claude-cli", "anthropic", "openai", "ollama"),
                   help="semantic backend; omit to auto-select")
    p.add_argument("--model", help="backend model id (overrides backend default)")
    p.add_argument("--spotlight-mode", choices=("datamark", "base64", "delimit"),
                   default="datamark")
    p.add_argument("--assignment", default="document")
    p.add_argument("--keep-comments", action="store_true")
    p.add_argument("--keep-tracked-changes", action="store_true")
    p.add_argument("--keep-metadata", action="store_true")
    p.add_argument("--list-backends", action="store_true",
                   help="print available semantic backends and exit")

    args = p.parse_args(argv)

    if args.list_backends:
        from docguard.semantic.dispatcher import available_backends
        for name in available_backends():
            print(name)
        return 0

    if not args.input and not args.batch:
        p.error("provide an input path or --batch")
    if not args.out:
        p.error("--out is required")

    config = SanitizeConfig(
        keep_comments=args.keep_comments,
        keep_tracked_changes=args.keep_tracked_changes,
        keep_metadata=args.keep_metadata,
        semantic=args.semantic,
        backend=args.backend,
        backend_model=args.model,
        spotlight_mode=args.spotlight_mode,
        assignment=args.assignment,
    )
    out_dir = Path(args.out)

    targets: list[Path] = []
    if args.batch:
        for match in glob.glob(args.batch):
            mp = Path(match)
            if mp.is_file() and mp.suffix.lower() in (".docx", ".pdf"):
                targets.append(mp)
    if args.input:
        targets.append(Path(args.input))

    if not targets:
        print("No .docx or .pdf files matched.", file=sys.stderr)
        return 2

    summary_path = out_dir / "summary.csv"
    if summary_path.exists():
        summary_path.unlink()

    errs = 0
    for i, src in enumerate(targets, 1):
        prefix = f"[{i}/{len(targets)}]"
        try:
            row = _run_one(src, out_dir, config)
            flag = " !" if row["injection_likely"] == "YES" else ""
            print(
                f"{prefix} {src.name} ({row['kind']}): "
                f"strips={row['structural_strips']} "
                f"unicode={row['unicode_chars_removed']} "
                f"regex={row['regex_flags']} "
                f"llm={row['llm_flags']}{flag}"
            )
            append_summary(summary_path, row)
        except Exception as e:  # noqa: BLE001
            errs += 1
            print(f"{prefix} {src.name}: ERROR — {e}", file=sys.stderr)
            traceback.print_exc()
            append_summary(summary_path, {
                "file": src.name, "kind": "?",
                "structural_strips": 0, "structural_flags": 0,
                "unicode_chars_removed": 0, "homoglyphs_logged": 0,
                "regex_flags": 0, "llm_flags": 0,
                "injection_likely": "error", "error": str(e)[:300],
            })

    print(f"\nDone. Outputs in {out_dir}")
    print(f"Summary: {summary_path}")
    if errs:
        print(f"Errors: {errs}", file=sys.stderr)
    return 1 if errs else 0


if __name__ == "__main__":
    raise SystemExit(main())
