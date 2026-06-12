#!/usr/bin/env python3
"""Data manifest — coverage truth for every research dataset.

Generates data/MANIFEST.json: per CSV → rows, byte size, sha256 (first 1MB),
first/last timestamp where detectable, and an excel_truncation_suspect flag
(row count within 50 of 2**20 — the 2026-06-11 incident: a "2010-2023" options
file was Excel-truncated to 2010-2013 and nearly produced a false research
conclusion).

Modes:
  generate  — write/refresh the manifest (default)
  check     — exit 1 if any previously-recorded dataset shrank or vanished
"""
import csv
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path.home() / "hedge"
SCAN_DIRS = [ROOT / "data/free", ROOT / "data/kaggle-seagate"]
MANIFEST = ROOT / "data/MANIFEST.json"
EXCEL_LIMIT = 2 ** 20
TS_RE = re.compile(r"\d{4}-\d{2}-\d{2}|\d{2}[-/]\d{2}[-/]\d{4}")


def first_last_ts(path: Path):
    """Best-effort first/last timestamp-looking token from row 2 and last row."""
    try:
        with open(path, "r", errors="replace") as f:
            f.readline()  # header
            first = f.readline()
        with open(path, "rb") as f:
            f.seek(max(0, path.stat().st_size - 4096))
            last = f.read().decode(errors="replace").strip().splitlines()[-1] if path.stat().st_size else ""
        fm, lm = TS_RE.search(first or ""), TS_RE.search(last or "")
        return (fm.group(0) if fm else None), (lm.group(0) if lm else None)
    except OSError:
        return None, None


def line_count(path: Path) -> int:
    n = 0
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            n += chunk.count(b"\n")
    return n


def head_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read(1 << 20))
    return h.hexdigest()[:16]


def generate():
    entries = {}
    for d in SCAN_DIRS:
        if not d.exists():
            continue
        for p in sorted(d.rglob("*.csv")):
            rows = line_count(p)
            first, last = first_last_ts(p)
            entries[str(p.relative_to(ROOT))] = {
                "rows": rows,
                "bytes": p.stat().st_size,
                "head_sha256": head_sha256(p),
                "first_ts_token": first,
                "last_ts_token": last,
                "excel_truncation_suspect": abs(rows - EXCEL_LIMIT) <= 50,
            }
    doc = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "note": "first/last ts tokens are heuristic — VERIFY format (mm-dd vs dd-mm) before claiming coverage",
        "datasets": entries,
    }
    MANIFEST.write_text(json.dumps(doc, indent=2) + "\n")
    suspects = [k for k, v in entries.items() if v["excel_truncation_suspect"]]
    print(f"manifest: {len(entries)} datasets")
    if suspects:
        print(f"EXCEL-TRUNCATION SUSPECTS ({len(suspects)}):")
        for s in suspects:
            print(f"  {s} — claimed range may exceed actual coverage")


def check():
    if not MANIFEST.exists():
        print("no manifest; run generate first")
        sys.exit(1)
    old = json.loads(MANIFEST.read_text())["datasets"]
    bad = []
    for rel, rec in old.items():
        p = ROOT / rel
        if not p.exists():
            bad.append(f"MISSING: {rel}")
        elif line_count(p) < rec["rows"]:
            bad.append(f"SHRANK: {rel} ({line_count(p)} < {rec['rows']} rows)")
    if bad:
        print("\n".join(bad))
        sys.exit(1)
    print(f"all {len(old)} datasets intact")


if __name__ == "__main__":
    (check if (len(sys.argv) > 1 and sys.argv[1] == "check") else generate)()
