#!/usr/bin/env python3
"""Safely import legacy Bill/Hermes state into the canonical state root.

This is a one-way, non-destructive bridge:
- canonical: ~/hedge/.rumbling-hedge/state
- legacy:    ~/.rumbling-hedge/state

It never deletes legacy files. When a legacy duplicate is newer, the canonical
file is archived before replacement so stale split-brain state can be audited.
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


HOME = Path.home()
CANONICAL_STATE = HOME / "hedge" / ".rumbling-hedge" / "state"
LEGACY_STATE = HOME / ".rumbling-hedge" / "state"
OUT = CANONICAL_STATE / "bill-state-unifier.latest.json"
ARCHIVE_ROOT = CANONICAL_STATE / "split-state-archive"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def file_rows(path: Path) -> dict[str, Path]:
    if not path.exists():
        return {}
    return {item.name: item for item in path.iterdir() if item.is_file()}


def classify_state(legacy: Path, canonical: Path) -> dict[str, Any]:
    legacy_files = file_rows(legacy)
    canonical_files = file_rows(canonical)
    duplicate_names = sorted(set(legacy_files) & set(canonical_files))
    legacy_only = sorted(set(legacy_files) - set(canonical_files))
    canonical_only = sorted(set(canonical_files) - set(legacy_files))
    legacy_newer = []
    canonical_newer = []
    same_or_close = []

    for name in duplicate_names:
        legacy_mtime = legacy_files[name].stat().st_mtime
        canonical_mtime = canonical_files[name].stat().st_mtime
        if legacy_mtime > canonical_mtime + 1:
            legacy_newer.append(name)
        elif canonical_mtime > legacy_mtime + 1:
            canonical_newer.append(name)
        else:
            same_or_close.append(name)

    return {
        "legacyCount": len(legacy_files),
        "canonicalCount": len(canonical_files),
        "duplicateCount": len(duplicate_names),
        "legacyOnly": legacy_only,
        "canonicalOnlyCount": len(canonical_only),
        "legacyNewerDuplicates": legacy_newer,
        "canonicalNewerDuplicateCount": len(canonical_newer),
        "sameOrCloseDuplicateCount": len(same_or_close),
    }


def copy_with_archive(src: Path, dst: Path, archive_dir: Path, apply: bool) -> dict[str, Any]:
    row: dict[str, Any] = {
        "name": src.name,
        "src": str(src),
        "dst": str(dst),
        "srcMtime": datetime.fromtimestamp(src.stat().st_mtime, timezone.utc).isoformat(),
        "dstExisted": dst.exists(),
    }
    if not apply:
        row["status"] = "planned"
        return row

    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        archive_dir.mkdir(parents=True, exist_ok=True)
        archive_path = archive_dir / f"{dst.name}.canonical-before-legacy-import"
        shutil.copy2(dst, archive_path)
        row["archivedCanonicalTo"] = str(archive_path)
    shutil.copy2(src, dst)
    row["status"] = "copied"
    return row


def build_report(legacy: Path, canonical: Path, apply: bool) -> dict[str, Any]:
    generated_at = now_iso()
    classified = classify_state(legacy, canonical)
    legacy_files = file_rows(legacy)
    archive_dir = ARCHIVE_ROOT / generated_at.replace(":", "-")
    actions = []

    for name in classified["legacyOnly"]:
        actions.append(copy_with_archive(legacy_files[name], canonical / name, archive_dir, apply))
        actions[-1]["reason"] = "legacy-only"

    for name in classified["legacyNewerDuplicates"]:
        actions.append(copy_with_archive(legacy_files[name], canonical / name, archive_dir, apply))
        actions[-1]["reason"] = "legacy-newer-duplicate"

    report = {
        "command": "bill-state-unifier",
        "generatedAt": generated_at,
        "legacyState": str(legacy),
        "canonicalState": str(canonical),
        "apply": apply,
        "decision": "applied-canonical-import" if apply else "dry-run",
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "movesFunds": False,
        "readyForExecution": False,
        "readyForDemoExpansion": False,
        "readyForLive": False,
        **classified,
        "actionCount": len(actions),
        "actions": actions,
        "nextActions": [
            "Keep canonical ~/hedge/.rumbling-hedge/state as the control-plane state root.",
            "Patch remaining legacy consumers to read canonical or use BILL_STATE_DIR.",
            "Do not delete ~/.rumbling-hedge/state until all Hermes scripts and crons are confirmed canonical.",
        ],
    }
    return report


def write_report(report: dict[str, Any], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Safely unify legacy Bill state into canonical state")
    parser.add_argument("--legacy", default=str(LEGACY_STATE))
    parser.add_argument("--canonical", default=str(CANONICAL_STATE))
    parser.add_argument("--output", default=str(OUT))
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    report = build_report(Path(args.legacy), Path(args.canonical), apply=args.apply)
    write_report(report, Path(args.output))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
