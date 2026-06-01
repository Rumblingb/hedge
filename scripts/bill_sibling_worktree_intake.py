#!/usr/bin/env python3
"""Create a read-only intake manifest for dirty sibling Bill/Hermes worktrees.

Sibling worktrees are useful research context, but they are not the canonical
source lane. This manifest makes their dirty files visible without staging,
deleting, merging, moving, routing, funding, or touching broker/order paths.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
VAULT = Path.home() / "Documents" / "memorybrain"
HERMES = VAULT / "Agent-Hermes"
WORKTREE = STATE / "worktree-consolidation.latest.json"
OUT = STATE / "bill-sibling-worktree-intake.latest.json"


def default_markdown_path() -> Path:
    date = datetime.now(timezone.utc).date().isoformat()
    return HERMES / f"bill-sibling-worktree-intake-{date}.md"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def parse_git_status(text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in text.splitlines():
        if len(line) < 4:
            continue
        status = line[:2].strip() or "modified"
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        if path:
            rows.append({"status": status, "path": path})
    return rows


def git_status_text(path: str) -> str:
    proc = subprocess.run(
        ["git", "status", "--short", "--untracked-files=all"],
        cwd=path,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return proc.stdout if proc.returncode == 0 else ""


def classify_path(path: str) -> str:
    lower = path.lower()
    if path in {"package.json", "package-lock.json", "requirements.bill-alpha.txt"}:
        return "dependency-review"
    if path.startswith("data/"):
        return "data-research-review"
    if path.startswith("retired/") or path.startswith("research-repos") or path.startswith("vendor/"):
        return "external-vendor-reference"
    if lower.endswith(".summary") or path.startswith(".rumbling-hedge/"):
        return "generated-cache"
    if (
        path.startswith("src/live/")
        or path.startswith("src/adapters/")
        or path.startswith("src/prediction/adapters/")
        or path.startswith("src/prediction/copyTrading")
        or path.startswith("src/prediction/sizing")
        or path.startswith("scripts/master_bridge")
        or path.startswith("scripts/60m_exec_bridge")
        or "execution" in lower
        or "fund" in lower
        or "deposit" in lower
        or "topstep" in lower
        or "broker" in lower
    ):
        return "execution-live-quarantine"
    if path.startswith("ops/") or path.startswith("docs/") or path.endswith(".md"):
        return "ops-docs-review"
    if (
        path.startswith("src/engine/")
        or path.startswith("src/config")
        or path.startswith("src/cli")
        or "readiness" in lower
        or "risk" in lower
        or "guard" in lower
        or "allocator" in lower
        or "cashflow" in lower
        or "hermes" in lower
    ):
        return "governance-risk-review"
    if path.startswith("src/") or path.startswith("scripts/") or path.startswith("tests/"):
        return "strategy-research-review"
    return "requires-review"


def sibling_rows(worktree_report: dict[str, Any]) -> list[dict[str, Any]]:
    dirty = worktree_report.get("dirtySiblingWorktrees")
    if isinstance(dirty, dict) and isinstance(dirty.get("worktrees"), list):
        return [row for row in dirty["worktrees"] if isinstance(row, dict)]
    rows = worktree_report.get("worktrees") if isinstance(worktree_report.get("worktrees"), list) else []
    return [
        row
        for row in rows
        if isinstance(row, dict)
        and row.get("intakeDecision") != "canonical-active"
        and int(row.get("dirtyFiles") or 0) > 0
    ]


def build_intake(
    worktree_report: dict[str, Any],
    *,
    status_text_by_path: dict[str, str] | None = None,
) -> dict[str, Any]:
    status_text_by_path = status_text_by_path or {}
    worktrees: list[dict[str, Any]] = []
    total_counts: Counter[str] = Counter()
    execution_live_total = 0
    for row in sibling_rows(worktree_report):
        path = str(row.get("path") or "")
        if not path:
            continue
        status_text = status_text_by_path.get(path)
        if status_text is None:
            status_text = git_status_text(path)
        status_rows = parse_git_status(status_text)
        items = []
        counts: Counter[str] = Counter()
        for status_row in status_rows:
            classification = classify_path(status_row["path"])
            counts[classification] += 1
            total_counts[classification] += 1
            items.append({
                "path": status_row["path"],
                "status": status_row["status"],
                "classification": classification,
            })
        execution_live_count = counts.get("execution-live-quarantine", 0)
        execution_live_total += execution_live_count
        worktrees.append({
            "path": path,
            "branch": row.get("branch"),
            "head": row.get("head"),
            "dirtyFilesFromWorktreeReport": row.get("dirtyFiles"),
            "dirtyFilesObserved": len(status_rows),
            "classificationCounts": dict(counts),
            "executionLiveDirtyCount": execution_live_count,
            "intakeDecision": "quarantine-selective-review",
            "topReviewFirst": [
                item["path"]
                for item in items
                if item["classification"] in {"execution-live-quarantine", "governance-risk-review", "dependency-review"}
            ][:12],
            "items": items,
            "reviewCommands": [
                f"git -C {path!r} status --short --untracked-files=all",
                f"git -C {path!r} diff --stat",
            ],
            "researchOnly": True,
            "writesOrders": False,
            "touchesBroker": False,
            "movesFunds": False,
            "safeToMergeAutomatically": False,
        })
    blockers: list[str] = []
    if worktrees:
        blockers.append("dirty-sibling-worktree-requires-selective-intake")
    if execution_live_total:
        blockers.append("sibling-worktree-has-execution-live-dirty-files")
    return {
        "command": "bill-sibling-worktree-intake",
        "generatedAt": now_iso(),
        "decision": "sibling-worktree-intake-visible-quarantine" if worktrees else "sibling-worktree-intake-clear",
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "movesFunds": False,
        "readyForExecution": False,
        "readyForDemoExpansion": False,
        "readyForLive": False,
        "sourceHygieneCleared": False,
        "safeToMergeAutomatically": False,
        "dirtySiblingWorktreeCount": len(worktrees),
        "dirtyFileCount": sum(int(item.get("dirtyFilesObserved") or 0) for item in worktrees),
        "executionLiveDirtyCount": execution_live_total,
        "classificationCounts": dict(total_counts),
        "worktrees": worktrees,
        "blockers": blockers,
        "nextCommands": [
            "npm run --silent bill:sibling-worktree-intake",
            "npm run --silent bill:worktree-consolidation || true",
            "npm run --silent bill:source-hygiene-plan",
            "npm run --silent bill:source-packet-review",
            "npm run --silent bill:goal-completion-audit",
            "npm run --silent bill:obsidian-sync",
        ],
        "hardRules": [
            "Do not merge, stage, delete, move, or revert sibling worktree files from this manifest.",
            "Sibling worktrees are quarantine/selective-intake only until canonical source hygiene is reviewed.",
            "Execution-live files in sibling worktrees cannot approve broker, funding, paper, demo, or live routes.",
        ],
    }


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Bill Sibling Worktree Intake",
        "",
        "Parent hub: [[BILL-CONTROL-HUB]]",
        "",
        "Read-only manifest for dirty sibling worktrees. This does not approve staging, merging, cleanup, routing, funding, demo, paper, or live trading.",
        "",
        "## Summary",
        "",
        f"- Decision: `{payload.get('decision')}`",
        f"- Dirty sibling worktrees: `{payload.get('dirtySiblingWorktreeCount')}`",
        f"- Dirty files observed: `{payload.get('dirtyFileCount')}`",
        f"- Execution/live dirty files: `{payload.get('executionLiveDirtyCount')}`",
        f"- Classification counts: `{payload.get('classificationCounts')}`",
        f"- Blockers: `{payload.get('blockers')}`",
        f"- Safe to merge automatically: `{payload.get('safeToMergeAutomatically')}`",
        "",
        "## Worktrees",
        "",
    ]
    for item in payload.get("worktrees") or []:
        lines.extend([
            f"### `{item.get('path')}`",
            "",
            f"- Branch: `{item.get('branch')}`",
            f"- Dirty files observed: `{item.get('dirtyFilesObserved')}`",
            f"- Classification counts: `{item.get('classificationCounts')}`",
            f"- Top review first: `{item.get('topReviewFirst')}`",
            f"- Safe to merge automatically: `{item.get('safeToMergeAutomatically')}`",
            "",
        ])
    lines.extend(["## Hard Rules", ""])
    for rule in payload.get("hardRules") or []:
        lines.append(f"- {rule}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a read-only sibling worktree intake manifest.")
    parser.add_argument("--worktree", default=str(WORKTREE))
    parser.add_argument("--output", default=str(OUT))
    parser.add_argument("--markdown-output", default=None)
    args = parser.parse_args()

    payload = build_intake(read_json(Path(args.worktree)))
    out = Path(args.output)
    md = Path(args.markdown_output) if args.markdown_output else default_markdown_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    md.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    md.write_text(render_markdown(payload))
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
