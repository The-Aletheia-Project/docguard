"""Sidecar JSON + summary CSV writers."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _encode(obj: Any):
    if is_dataclass(obj):
        return asdict(obj)
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, (set, frozenset)):
        return list(obj)
    raise TypeError(f"not JSON serialisable: {type(obj).__name__}")


def write_report(path: Path, payload: dict) -> None:
    payload = {
        **payload,
        "scanned_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False, default=_encode)


def append_summary(csv_path: Path, row: dict) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "file",
        "kind",
        "structural_strips",
        "structural_flags",
        "unicode_chars_removed",
        "homoglyphs_logged",
        "regex_flags",
        "llm_flags",
        "injection_likely",
        "error",
    ]
    exists = csv_path.exists()
    with csv_path.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        if not exists:
            w.writeheader()
        w.writerow(row)
