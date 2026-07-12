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


INTAKE_BATCH_RULES: dict[str, dict[str, Any]] = {
    "execution-live-quarantine": {
        "priority": 1,
        "action": "keep-quarantined",
        "decision": "do-not-intake-automatically",
        "reason": "Broker, route, funding, Topstep, or execution-adjacent changes must not enter canonical from a sibling worktree without a separate proof gate.",
        "requiredEvidence": [
            "npm run --silent bill:verify-execution-quarantine",
            "manual diff review proving no execution/demo/live flags or routes are armed",
        ],
    },
    "dependency-review": {
        "priority": 2,
        "action": "focused-dependency-review",
        "decision": "manual-review-only",
        "reason": "Dependency changes can alter research, cron, and control-plane behavior across the system.",
        "requiredEvidence": [
            "focused package/lockfile diff review",
            "npm run --silent typecheck",
        ],
    },
    "governance-risk-review": {
        "priority": 3,
        "action": "focused-governance-review",
        "decision": "manual-review-only",
        "reason": "Risk, allocator, readiness, Hermes, and guard code affects whether agents believe the fund is cleared.",
        "requiredEvidence": [
            "focused tests for touched governance/risk modules",
            "npm run --silent bill:goal-completion-audit",
        ],
    },
    "strategy-research-review": {
        "priority": 4,
        "action": "research-only-selective-review",
        "decision": "candidate-after-tests",
        "reason": "Strategy/research code can be useful, but it must remain research-only and cannot approve Topstep, paper, demo, or live routes.",
        "requiredEvidence": [
            "focused unit/backtest validation for the touched strategy lane",
            "npm run --silent bill:strategy-factory-one-variable-research",
        ],
    },
    "ops-docs-review": {
        "priority": 5,
        "action": "docs-and-scheduler-review",
        "decision": "manual-review-only",
        "reason": "Ops/docs changes can change what Hermes, n8n, cron, or human operators do next.",
        "requiredEvidence": [
            "manual Obsidian/ops review",
            "npm run --silent bill:obsidian-sync",
        ],
    },
    "data-research-review": {
        "priority": 6,
        "action": "link-or-catalog-data",
        "decision": "do-not-copy-large-data-automatically",
        "reason": "Large or external datasets should be cataloged and validated before they are pulled into canonical source.",
        "requiredEvidence": [
            "data provenance and schema notes",
            "bounded data-quality sample",
        ],
    },
    "external-vendor-reference": {
        "priority": 7,
        "action": "keep-as-reference-or-catalog-link",
        "decision": "do-not-vendor-automatically",
        "reason": "External repos and references should stay isolated unless a small reviewed adapter is intentionally reimplemented.",
        "requiredEvidence": [
            "license/provenance review",
            "explicit decision to reimplement versus vendor",
        ],
    },
    "generated-cache": {
        "priority": 8,
        "action": "ignore-or-retire",
        "decision": "not-source",
        "reason": "Generated state/cache files should not be considered canonical source patches.",
        "requiredEvidence": [
            "none; leave generated artifacts out of canonical source intake",
        ],
    },
    "requires-review": {
        "priority": 9,
        "action": "manual-classification-review",
        "decision": "manual-review-only",
        "reason": "Unclassified files need human/agent classification before any intake decision.",
        "requiredEvidence": [
            "manual path classification",
            "focused diff review",
        ],
    },
}


def make_selective_intake_plan(total_counts: Counter[str], worktrees: list[dict[str, Any]]) -> dict[str, Any]:
    """Turn raw classifications into a review plan that preserves quarantine."""
    sample_by_class: dict[str, list[str]] = {}
    for worktree in worktrees:
        root = str(worktree.get("path") or "")
        for item in worktree.get("items") or []:
            if not isinstance(item, dict):
                continue
            classification = str(item.get("classification") or "requires-review")
            sample_by_class.setdefault(classification, [])
            if len(sample_by_class[classification]) < 8:
                path = str(item.get("path") or "")
                sample_by_class[classification].append(f"{root}:{path}" if root and path else path)

    batches: list[dict[str, Any]] = []
    for classification, count in total_counts.items():
        rules = INTAKE_BATCH_RULES.get(classification, INTAKE_BATCH_RULES["requires-review"])
        batches.append({
            "classification": classification,
            "count": count,
            "priority": rules["priority"],
            "action": rules["action"],
            "decision": rules["decision"],
            "reason": rules["reason"],
            "requiredEvidence": rules["requiredEvidence"],
            "examplePaths": sample_by_class.get(classification, []),
            "autoMergeEligible": False,
            "researchOnly": True,
            "writesOrders": False,
            "touchesBroker": False,
            "movesFunds": False,
        })
    batches.sort(key=lambda item: (int(item.get("priority") or 99), str(item.get("classification") or "")))

    has_execution_live = bool(total_counts.get("execution-live-quarantine"))
    return {
        "decision": "quarantine-selective-review" if total_counts else "no-dirty-sibling-files",
        "nextBestAction": (
            "Keep execution-live files quarantined and prove the quarantine first; then review dependency/governance batches before any research-only cherry-pick."
            if has_execution_live
            else "Review dependency/governance batches first; any strategy intake stays research-only until focused tests and goal audit pass."
            if total_counts
            else "No dirty sibling worktree files observed."
        ),
        "reviewBatchCount": len(batches),
        "researchReviewCandidateCount": sum(
            count
            for classification, count in total_counts.items()
            if classification in {"strategy-research-review", "ops-docs-review", "data-research-review"}
        ),
        "executionLiveQuarantineCount": int(total_counts.get("execution-live-quarantine") or 0),
        "autoMergeEligible": False,
        "sourceHygieneClearedByThisPlan": False,
        "batches": batches,
    }


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
    selective_intake_plan = make_selective_intake_plan(total_counts, worktrees)
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
        "selectiveIntakePlan": selective_intake_plan,
        "worktrees": worktrees,
        "blockers": blockers,
        "nextCommands": [
            "npm run --silent bill:sibling-worktree-intake",
            "npm run --silent bill:verify-execution-quarantine",
            "npm run --silent bill:worktree-consolidation || true",
            "npm run --silent bill:source-hygiene-plan",
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
        "## Selective Intake Plan",
        "",
        f"- Decision: `{(payload.get('selectiveIntakePlan') or {}).get('decision')}`",
        f"- Next best action: {(payload.get('selectiveIntakePlan') or {}).get('nextBestAction')}",
        f"- Research review candidate count: `{(payload.get('selectiveIntakePlan') or {}).get('researchReviewCandidateCount')}`",
        f"- Execution/live quarantine count: `{(payload.get('selectiveIntakePlan') or {}).get('executionLiveQuarantineCount')}`",
        f"- Auto-merge eligible: `{(payload.get('selectiveIntakePlan') or {}).get('autoMergeEligible')}`",
        "",
        "### Review Batches",
        "",
    ]
    for batch in (payload.get("selectiveIntakePlan") or {}).get("batches") or []:
        lines.extend([
            f"- `{batch.get('classification')}` count=`{batch.get('count')}` action=`{batch.get('action')}` decision=`{batch.get('decision')}` autoMerge=`{batch.get('autoMergeEligible')}`",
            f"  - Evidence: `{batch.get('requiredEvidence')}`",
            f"  - Examples: `{batch.get('examplePaths')}`",
        ])
    lines.extend([
        "",
        "## Worktrees",
        "",
    ])
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
