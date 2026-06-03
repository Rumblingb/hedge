#!/usr/bin/env python3
"""Canonicalize Bill/Hermes runtime roots without breaking old callers.

The canonical roots live in:
  /Users/brain/hedge/.rumbling-hedge/{state,brain,events}

Legacy callers may still use:
  /Users/brain/.rumbling-hedge/{state,brain,events}

This tool first imports useful legacy files into canonical, archives any
canonical file before a newer legacy overwrite, moves the old legacy directory
to a retired-roots archive, then creates a symlink from legacy to canonical.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


HOME = Path.home()
CANONICAL_BASE = HOME / "hedge" / ".rumbling-hedge"
LEGACY_BASE = HOME / ".rumbling-hedge"
ROOT_NAMES = ("state", "brain", "events")
OUT = CANONICAL_BASE / "state" / "bill-canonical-roots.latest.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def files_under(root: Path) -> dict[str, Path]:
    if not root.exists() or root.is_symlink():
        return {}
    return {
        str(path.relative_to(root)): path
        for path in root.rglob("*")
        if path.is_file()
    }


def copy_file(src: Path, dst: Path, archive_root: Path, apply: bool) -> dict[str, Any]:
    row: dict[str, Any] = {
        "src": str(src),
        "dst": str(dst),
        "dstExisted": dst.exists(),
        "status": "planned",
    }
    if not apply:
        return row
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        archive_root.mkdir(parents=True, exist_ok=True)
        archive_path = archive_root / dst.name
        counter = 1
        while archive_path.exists():
            archive_path = archive_root / f"{dst.name}.{counter}"
            counter += 1
        shutil.copy2(dst, archive_path)
        row["archivedCanonicalTo"] = str(archive_path)
    shutil.copy2(src, dst)
    row["status"] = "copied"
    return row


def merge_root(name: str, canonical: Path, legacy: Path, archive_root: Path, apply: bool) -> dict[str, Any]:
    canonical_files = files_under(canonical)
    legacy_files = files_under(legacy)
    imported = []
    skipped = []

    for rel, src in sorted(legacy_files.items()):
        dst = canonical / rel
        reason = None
        if rel not in canonical_files:
            reason = "legacy-only"
        elif src.stat().st_mtime > canonical_files[rel].stat().st_mtime + 1:
            reason = "legacy-newer"
        if reason:
            row = copy_file(src, dst, archive_root / name / rel.replace("/", "__"), apply)
            row["relativePath"] = rel
            row["reason"] = reason
            imported.append(row)
        else:
            skipped.append(rel)

    return {
        "name": name,
        "canonical": str(canonical),
        "legacy": str(legacy),
        "legacyExists": legacy.exists(),
        "legacyIsSymlink": legacy.is_symlink(),
        "canonicalFileCountBefore": len(canonical_files),
        "legacyFileCount": len(legacy_files),
        "importCount": len(imported),
        "skippedCount": len(skipped),
        "imports": imported,
    }


def retire_and_symlink(name: str, canonical: Path, legacy: Path, retired_root: Path, apply: bool) -> dict[str, Any]:
    row: dict[str, Any] = {
        "name": name,
        "canonical": str(canonical),
        "legacy": str(legacy),
        "status": "planned",
    }
    if not apply:
        return row
    canonical.mkdir(parents=True, exist_ok=True)
    legacy.parent.mkdir(parents=True, exist_ok=True)
    if legacy.is_symlink():
        if legacy.resolve() == canonical.resolve():
            row["status"] = "already-symlinked"
            return row
        legacy.unlink()
    elif legacy.exists():
        retired_root.mkdir(parents=True, exist_ok=True)
        retired_path = retired_root / name
        counter = 1
        while retired_path.exists():
            retired_path = retired_root / f"{name}.{counter}"
            counter += 1
        shutil.move(str(legacy), str(retired_path))
        row["retiredLegacyTo"] = str(retired_path)
    os.symlink(canonical, legacy)
    row["status"] = "symlinked"
    return row


def build_report(apply: bool) -> dict[str, Any]:
    generated_at = now_iso()
    stamp = generated_at.replace(":", "-")
    archive_root = CANONICAL_BASE / "state" / "canonical-root-archive" / stamp
    retired_root = LEGACY_BASE / "retired-roots" / stamp
    merges = []
    retirements = []

    for name in ROOT_NAMES:
        canonical = CANONICAL_BASE / name
        legacy = LEGACY_BASE / name
        merges.append(merge_root(name, canonical, legacy, archive_root, apply))
    for name in ROOT_NAMES:
        canonical = CANONICAL_BASE / name
        legacy = LEGACY_BASE / name
        retirements.append(retire_and_symlink(name, canonical, legacy, retired_root, apply))

    return {
        "command": "bill-canonicalize-roots",
        "generatedAt": generated_at,
        "apply": apply,
        "decision": "applied-canonical-roots" if apply else "dry-run",
        "canonicalBase": str(CANONICAL_BASE),
        "legacyBase": str(LEGACY_BASE),
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "movesFunds": False,
        "readyForExecution": False,
        "readyForDemoExpansion": False,
        "readyForLive": False,
        "mergeImportCount": sum(item["importCount"] for item in merges),
        "merges": merges,
        "retirements": retirements,
        "nextActions": [
            "Use /Users/brain/hedge/.rumbling-hedge as the only real runtime root.",
            "Keep /Users/brain/.rumbling-hedge/{state,brain,events} as symlinks for compatibility.",
            "Patch remaining hard-coded legacy scripts over time; they now resolve through symlinks.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Canonicalize Bill/Hermes runtime roots")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--output", default=str(OUT))
    args = parser.parse_args()

    report = build_report(args.apply)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
