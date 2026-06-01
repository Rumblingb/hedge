#!/usr/bin/env python3
"""Hermes runtime storage audit.

This is a manifest-only cleanup aid. It does not move, delete, compress, or
modify Hermes runtime files. The goal is to separate active state from cold
archive candidates before any SSD cleanup is attempted.
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


HOME = Path.home()
ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
DEFAULT_OUTPUT = STATE / "hermes-storage-audit.latest.json"
DEFAULT_MARKDOWN = STATE / "hermes-storage-audit.latest.md"
HERMES_ROOT = HOME / ".hermes"
DEFAULT_ARCHIVE_ROOT = Path("/Volumes/Seagate Expansion Drive/hedge-data/local-archives/hermes-runtime")

ACTIVE_NAMES = {
    "state.db",
    "state.db-wal",
    "state.db-shm",
    "cron",
    "scripts",
    "bin",
    "workspace",
}


def bytes_to_human(value: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(value)
    unit = 0
    while size >= 1024 and unit < len(units) - 1:
        size /= 1024
        unit += 1
    return f"{size:.1f}{units[unit]}" if unit else f"{int(size)}B"


def path_size(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    total = 0
    for root, dirs, files in os.walk(path):
        dirs[:] = [item for item in dirs if item not in {".Trash", ".Spotlight-V100"}]
        root_path = Path(root)
        for name in files:
            try:
                total += (root_path / name).stat().st_size
            except OSError:
                pass
    return total


def file_tree_summary(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "path": str(path),
            "exists": False,
            "fileCount": 0,
            "bytes": 0,
            "size": "0B",
        }
    if path.is_file():
        size = path.stat().st_size
        return {
            "path": str(path),
            "exists": True,
            "fileCount": 1,
            "bytes": size,
            "size": bytes_to_human(size),
        }
    file_count = 0
    total = 0
    for root, dirs, files in os.walk(path):
        dirs[:] = [item for item in dirs if item not in {".Trash", ".Spotlight-V100"}]
        root_path = Path(root)
        for name in files:
            try:
                total += (root_path / name).stat().st_size
                file_count += 1
            except OSError:
                pass
    return {
        "path": str(path),
        "exists": True,
        "fileCount": file_count,
        "bytes": total,
        "size": bytes_to_human(total),
    }


def relative_file_manifest(path: Path) -> dict[str, int]:
    if not path.exists():
        return {}
    if path.is_file():
        return {path.name: path.stat().st_size}
    out: dict[str, int] = {}
    for root, dirs, files in os.walk(path):
        dirs[:] = [item for item in dirs if item not in {".Trash", ".Spotlight-V100"}]
        root_path = Path(root)
        for name in files:
            file_path = root_path / name
            try:
                out[str(file_path.relative_to(path))] = file_path.stat().st_size
            except OSError:
                pass
    return out


def archive_verification(source: Path, destination: Path) -> dict[str, Any]:
    source_summary = file_tree_summary(source)
    destination_summary = file_tree_summary(destination)
    source_manifest = relative_file_manifest(source)
    destination_manifest = relative_file_manifest(destination)
    missing_from_archive = sorted(
        rel_path for rel_path in source_manifest
        if rel_path not in destination_manifest
    )
    size_mismatches = sorted(
        rel_path for rel_path, size in source_manifest.items()
        if rel_path in destination_manifest and destination_manifest[rel_path] != size
    )
    checksum_path = destination.with_suffix(destination.suffix + ".sha256")
    alt_checksum_path = destination.parent / f"{destination.name}.sha256"
    checksum_exists = checksum_path.exists() or alt_checksum_path.exists()
    count_matches = (
        source_summary["exists"]
        and destination_summary["exists"]
        and source_summary["fileCount"] == destination_summary["fileCount"]
    )
    bytes_match = (
        source_summary["exists"]
        and destination_summary["exists"]
        and source_summary["bytes"] == destination_summary["bytes"]
    )
    archive_covers_source = (
        source_summary["exists"]
        and destination_summary["exists"]
        and not missing_from_archive
        and not size_mismatches
    )
    return {
        "source": source_summary,
        "destination": destination_summary,
        "checksumManifestExists": checksum_exists,
        "checksumManifestPath": str(checksum_path if checksum_path.exists() else alt_checksum_path),
        "countMatches": count_matches,
        "bytesMatch": bytes_match,
        "archiveCoversSource": archive_covers_source,
        "missingFromArchiveCount": len(missing_from_archive),
        "missingFromArchiveSample": missing_from_archive[:10],
        "sizeMismatchCount": len(size_mismatches),
        "sizeMismatchSample": size_mismatches[:10],
        "copyLooksComplete": archive_covers_source and checksum_exists,
        "operatorRead": (
            "Archive covers current source files and a checksum manifest exists; still spot-check "
            "checksums before proposing any local removal."
            if archive_covers_source and checksum_exists
            else "Archive copy is not yet sufficient evidence for removal."
        ),
    }


def mount_summary(path: Path) -> dict[str, Any]:
    existing = path
    while not existing.exists() and existing != existing.parent:
        existing = existing.parent
    try:
        proc = subprocess.run(["df", "-h", str(existing)], capture_output=True, text=True, timeout=10)
        lines = [line for line in proc.stdout.splitlines() if line.strip()]
        return {"path": str(path), "exists": path.exists(), "df": lines[-1] if lines else None}
    except Exception as exc:
        return {"path": str(path), "exists": path.exists(), "error": f"{type(exc).__name__}: {exc}"}


def classify_entry(path: Path, size: int) -> dict[str, str]:
    name = path.name
    if name in ACTIVE_NAMES:
        return {
            "tier": "hot-active",
            "action": "do-not-move",
            "reason": "Active Hermes runtime/control state.",
        }
    if name == "profiles":
        return {
            "tier": "warm-profile-cache",
            "action": "inspect-profile-subdirs-before-archive",
            "reason": "Large agent/model profile root; individual profiles may be active or cold.",
        }
    if name == "state-snapshots":
        return {
            "tier": "cold-snapshot-candidate",
            "action": "archive-with-checksum-before-delete",
            "reason": "Rollback snapshots are large and usually cold, but deletion requires verified archive copy.",
        }
    if name in {"sessions", "logs", "checkpoints"}:
        return {
            "tier": "warm-rotating-history",
            "action": "archive-old-files-only",
            "reason": "Useful recent history; only rotate/archive old files after retention policy is chosen.",
        }
    if name in {"venvs", "hermes-agent", "skills"}:
        return {
            "tier": "warm-runtime-dependency",
            "action": "keep-unless-reinstall-path-tested",
            "reason": "Runtime/dependency tree; moving can break Hermes unless wrappers know the new path.",
        }
    if size >= 100 * 1024 * 1024:
        return {
            "tier": "review-large",
            "action": "manual-review",
            "reason": "Large Hermes path not recognized as safe to move automatically.",
        }
    return {
        "tier": "small-keep",
        "action": "leave-in-place",
        "reason": "Small path; cleanup value is low.",
    }


def entry_summary(path: Path) -> dict[str, Any]:
    size = path_size(path)
    classification = classify_entry(path, size)
    return {
        "path": str(path),
        "name": path.name,
        "exists": path.exists(),
        "bytes": size,
        "size": bytes_to_human(size),
        **classification,
    }


def profile_summaries(profiles_root: Path) -> list[dict[str, Any]]:
    if not profiles_root.exists():
        return []
    out = []
    for child in sorted(profiles_root.iterdir(), key=lambda item: item.name):
        if not child.is_dir():
            continue
        size = path_size(child)
        has_ollama = (child / "home" / ".ollama").exists()
        has_rustup = (child / "home" / ".rustup").exists()
        out.append({
            "path": str(child),
            "name": child.name,
            "bytes": size,
            "size": bytes_to_human(size),
            "hasOllamaModels": has_ollama,
            "hasRustupToolchain": has_rustup,
            "tier": "profile-cache-heavy" if size >= 500 * 1024 * 1024 else "profile-cache-light",
            "action": "confirm-profile-inactive-before-archive" if size >= 500 * 1024 * 1024 else "leave-unless-known-cold",
        })
    return out


def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def cleanup_plan(report: dict[str, Any]) -> list[dict[str, Any]]:
    archive_root = Path(report["archiveRoot"])
    snapshots = next((item for item in report["entries"] if item["name"] == "state-snapshots"), None)
    heavy_profiles = [
        item for item in report["profiles"]
        if item.get("action") == "confirm-profile-inactive-before-archive"
    ]
    phases: list[dict[str, Any]] = []

    if snapshots:
        dst = archive_root / "state-snapshots"
        phases.append({
            "id": "archive-state-snapshots-copy-only",
            "executeManually": False,
            "destructive": False,
            "source": snapshots["path"],
            "destination": str(dst),
            "size": snapshots["size"],
            "prerequisites": [
                "Confirm Hermes is not actively rolling back from this snapshot.",
                "Confirm Seagate is mounted and has free space.",
            ],
            "commands": [
                f"mkdir -p {shell_quote(str(dst))}",
                f"rsync -a --info=progress2 {shell_quote(snapshots['path'] + '/')} {shell_quote(str(dst) + '/')}",
                f"find {shell_quote(str(dst))} -type f -print0 | xargs -0 shasum -a 256 > {shell_quote(str(dst) + '.sha256')}",
            ],
            "afterCopyReview": [
                "Do not delete the SSD source in the same run.",
                "Open the checksum file and spot-check file counts before any removal proposal.",
            ],
        })

    if heavy_profiles:
        phases.append({
            "id": "review-heavy-profile-caches",
            "executeManually": False,
            "destructive": False,
            "source": str(HERMES_ROOT / "profiles"),
            "destination": str(archive_root / "profiles"),
            "size": bytes_to_human(sum(int(item["bytes"]) for item in heavy_profiles)),
            "profileCandidates": [
                {
                    "name": item["name"],
                    "path": item["path"],
                    "size": item["size"],
                    "hasOllamaModels": item["hasOllamaModels"],
                    "hasRustupToolchain": item["hasRustupToolchain"],
                }
                for item in sorted(heavy_profiles, key=lambda row: row["bytes"], reverse=True)
            ],
            "prerequisites": [
                "Confirm each profile is inactive in Hermes fleet status.",
                "Do not move profiles with active gateways, running tasks, or required local model caches.",
                "Prefer moving only model blobs/cold toolchains after a tested restore path exists.",
            ],
            "commands": [
                "# No automatic profile move command is provided until inactive profiles are confirmed.",
            ],
        })

    phases.append({
        "id": "active-state-do-not-touch",
        "executeManually": False,
        "destructive": False,
        "protectedPaths": [
            str(HERMES_ROOT / name)
            for name in sorted(ACTIVE_NAMES)
        ],
        "reason": "These paths are active Hermes runtime/control state and should remain on SSD.",
    })
    return phases


def build_report(archive_root: Path = DEFAULT_ARCHIVE_ROOT) -> dict[str, Any]:
    entries = []
    if HERMES_ROOT.exists():
        entries = [entry_summary(child) for child in sorted(HERMES_ROOT.iterdir(), key=lambda item: item.name)]
    profiles = profile_summaries(HERMES_ROOT / "profiles")
    total = sum(item["bytes"] for item in entries)
    archive_candidates = [
        item for item in entries
        if item["tier"] in {"cold-snapshot-candidate", "warm-profile-cache", "warm-rotating-history"}
    ]
    hard_rules = [
        "This audit is manifest-only and must not delete, move, or compress files.",
        "Do not move state.db, cron, scripts, or active profile directories while Hermes is running.",
        "Archive candidates require a verified copy on Seagate before any local removal.",
        "Profile/model caches require an operator-confirmed inactive profile list before migration.",
    ]
    state_snapshots_source = HERMES_ROOT / "state-snapshots"
    state_snapshots_destination = archive_root / "state-snapshots"
    report = {
        "command": "hermes-storage-audit",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "hermesRoot": str(HERMES_ROOT),
        "archiveRoot": str(archive_root),
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "movesFiles": False,
        "deletesFiles": False,
        "totalBytes": total,
        "totalSize": bytes_to_human(total),
        "archiveCandidateBytes": sum(item["bytes"] for item in archive_candidates),
        "archiveCandidateSize": bytes_to_human(sum(item["bytes"] for item in archive_candidates)),
        "archiveMount": mount_summary(archive_root),
        "archiveVerification": {
            "stateSnapshots": archive_verification(state_snapshots_source, state_snapshots_destination),
        },
        "entries": entries,
        "profiles": profiles,
        "topCandidates": sorted(archive_candidates, key=lambda item: item["bytes"], reverse=True)[:8],
        "hardRules": hard_rules,
        "nextActions": [
            "Pick an inactive Hermes profile list before moving any profile/model cache.",
            "Archive state-snapshots with checksum verification to Seagate, then review removal separately.",
            "If archiveVerification.stateSnapshots.copyLooksComplete is true, spot-check checksums before any deletion proposal.",
            "Keep active state.db, state.db-wal, cron, scripts, and bin on SSD.",
            "Record any actual cleanup in Obsidian before and after running it.",
        ],
    }
    report["cleanupPlan"] = cleanup_plan(report)
    return report


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Hermes Storage Audit",
        "",
        f"- Generated: `{report['generatedAt']}`",
        f"- Hermes root: `{report['hermesRoot']}`",
        f"- Total: `{report['totalSize']}`",
        f"- Archive candidates: `{report['archiveCandidateSize']}`",
        f"- Moves files: `{report['movesFiles']}`",
        f"- Deletes files: `{report['deletesFiles']}`",
        "",
        "## Top Candidates",
        "",
    ]
    for item in report["topCandidates"]:
        lines.append(f"- `{item['size']}` `{item['path']}` — {item['action']}: {item['reason']}")
    state_archive = report.get("archiveVerification", {}).get("stateSnapshots", {})
    if state_archive:
        lines.extend(["", "## Archive Verification", ""])
        lines.append(f"- State snapshots source: `{state_archive['source']['size']}` / `{state_archive['source']['fileCount']}` files")
        lines.append(f"- State snapshots archive: `{state_archive['destination']['size']}` / `{state_archive['destination']['fileCount']}` files")
        lines.append(f"- Checksum manifest exists: `{state_archive['checksumManifestExists']}`")
        lines.append(f"- Archive covers source: `{state_archive['archiveCoversSource']}`")
        lines.append(f"- Exact count match: `{state_archive['countMatches']}`")
        lines.append(f"- Exact byte match: `{state_archive['bytesMatch']}`")
        lines.append(f"- Copy looks complete: `{state_archive['copyLooksComplete']}`")
        lines.append(f"- Operator read: {state_archive['operatorRead']}")
    lines.extend(["", "## Heavy Profiles", ""])
    for item in sorted(report["profiles"], key=lambda row: row["bytes"], reverse=True)[:10]:
        lines.append(
            f"- `{item['size']}` `{item['name']}` — {item['action']} "
            f"(ollama={item['hasOllamaModels']}, rustup={item['hasRustupToolchain']})"
        )
    lines.extend(["", "## Hard Rules", ""])
    for rule in report["hardRules"]:
        lines.append(f"- {rule}")
    lines.extend(["", "## Cleanup Plan", ""])
    for phase in report.get("cleanupPlan", []):
        lines.append(f"### {phase['id']}")
        lines.append("")
        lines.append(f"- Execute manually: `{phase.get('executeManually')}`")
        lines.append(f"- Destructive: `{phase.get('destructive')}`")
        if phase.get("size"):
            lines.append(f"- Size: `{phase.get('size')}`")
        if phase.get("source"):
            lines.append(f"- Source: `{phase.get('source')}`")
        if phase.get("destination"):
            lines.append(f"- Destination: `{phase.get('destination')}`")
        for command in phase.get("commands", []):
            lines.append(f"- Command: `{command}`")
        lines.append("")
    lines.extend(["", "## Next Actions", ""])
    for action in report["nextActions"]:
        lines.append(f"- {action}")
    return "\n".join(lines) + "\n"


def main() -> int:
    report = build_report()
    STATE.mkdir(parents=True, exist_ok=True)
    DEFAULT_OUTPUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    DEFAULT_MARKDOWN.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
