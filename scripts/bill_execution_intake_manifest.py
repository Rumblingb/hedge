#!/usr/bin/env python3
"""Create a read-only manifest for dirty Bill/Hermes execution-live files."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
HOME = Path.home()
STATE = ROOT / ".rumbling-hedge" / "state"
VAULT = Path.home() / "Documents" / "memorybrain"
HERMES = VAULT / "Agent-Hermes"
OUT = STATE / "bill-execution-intake-manifest.latest.json"
CRON_JOBS = HOME / ".hermes" / "cron" / "jobs.json"
EXTERNAL_TOPSTEP_DEMO_BRIDGE = HOME / ".hermes" / "scripts" / "topstep_demo_bridge.py"


def default_markdown_path() -> Path:
    plan_date = datetime.now(timezone.utc).date().isoformat()
    return HERMES / f"bill-execution-intake-manifest-{plan_date}.md"


FIREWALL_MAP = {
    "ops/mac-mini/bin/bill-pm-auto-execute-loop.sh": "verify-execution-quarantine",
    "ops/mac-mini/launchd/com.agentpay.bill.realtime-bridge.plist.template": "verify-execution-quarantine",
    "ops/start-gengar-live.sh": "verify-execution-quarantine",
    "scripts/master_bridge.py": "verify-master-bridge-firewall",
    "scripts/60m_exec_bridge.py": "verify-60m-bridge-firewall",
    "scripts/topstep_demo_bridge.py": "verify-topstep-demo-bridge-firewall",
    "scripts/agentic_fund.sh": "verify-execution-quarantine",
    "scripts/bill_fund_os_completion_audit.py": "verify-execution-quarantine",
    "scripts/cron_position_sizing.sh": "verify-execution-quarantine",
    "scripts/pm_arb_scanner.py": "verify-execution-quarantine",
    "scripts/position_sizing_engine.py": "verify-execution-quarantine",
    "scripts/pre_trade_check.py": "verify-execution-quarantine",
    "scripts/realtime_data_bridge.py": "verify-execution-quarantine",
    "scripts/trade_journal.py": "verify-execution-quarantine",
    "src/adapters/projectx/projectxAdapter.ts": "verify-execution-quarantine",
    "src/live/signalRouter.ts": "verify-signal-router-firewall",
    "src/live/demoExecution.ts": "verify-execution-quarantine",
    "src/risk/topstepCompliance.ts": "verify-execution-quarantine",
    "src/prediction/gengarExecutionWatcher.ts": "verify-execution-quarantine",
    "tests/signalRouter.test.ts": "verify-signal-router-firewall",
    "scripts/deposit-clob.ts": "verify-prediction-funding-firewall",
    "scripts/deposit-simple.ts": "verify-prediction-funding-firewall",
    "scripts/fund-and-trade.ts": "verify-prediction-funding-firewall",
    "scripts/swap-and-fund.ts": "verify-prediction-funding-firewall",
    "scripts/wire-up.ts": "verify-prediction-funding-firewall",
    "src/prediction/execution/authorization.ts": "verify-prediction-funding-firewall",
    "src/prediction/execution/liveGate.ts": "verify-prediction-funding-firewall",
}

EXECUTION_PATTERNS = (
    "bridge",
    "router",
    "signalrouter",
    "topstep",
    "fund",
    "deposit",
    "swap",
    "wire",
    "execute",
    "execution",
    "position_sizing",
    "trade_journal",
    "pm_arb",
    "pre_trade",
    "projectx",
)

SELF_REVIEWED_PATHS = {
    "scripts/bill_execution_intake_manifest.py",
    "tests/test_bill_execution_intake_manifest.py",
}

READ_ONLY_BROKER_EVIDENCE_PATHS = {
    "scripts/topstep_market_data_smoke.py",
    "scripts/topstep_readonly_bar_archive.py",
    "scripts/topstep_broker_local_bar_parity.py",
    "scripts/topstep_realtime_proof.py",
    "scripts/topstepx_dashboard_screen_proof.py",
    "scripts/topstep_daily_learning.py",
}

EXECUTION_VERIFIER_WRAPPER_PATHS = {
    "scripts/cron_verify_execution_quarantine.sh",
    "scripts/cron_verify_master_bridge.sh",
    "scripts/cron_verify_no_execution.sh",
    "scripts/cron_verify_topstep_demo.sh",
}

READ_ONLY_CONTROL_EVIDENCE_PATHS = {
    "scripts/topstep_demo_observation_posture.py",
    "scripts/topstep_session_safety_clearance.py",
}

RESEARCH_SHADOW_BRIDGE_PATHS = {
    "scripts/dom_edge_bridge.py",
}

EXECUTION_ADJACENT_PREFIXES = (
    "ops/",
    "scripts/",
    "src/",
    "tests/",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def file_sha256(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except Exception:
        return None


def git_status_text() -> str:
    proc = subprocess.run(
        ["git", "status", "--short", "--untracked-files=all"],
        cwd=ROOT,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return proc.stdout if proc.returncode == 0 else ""


def parse_git_status(text: str) -> dict[str, str]:
    rows: dict[str, str] = {}
    for line in text.splitlines():
        if len(line) < 4:
            continue
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        if path:
            rows[path] = line[:2].strip() or "modified"
    return rows


def git_diff_numstat_text() -> str:
    proc = subprocess.run(
        ["git", "diff", "--numstat"],
        cwd=ROOT,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return proc.stdout if proc.returncode == 0 else ""


def parse_numstat(text: str) -> dict[str, dict[str, int | None]]:
    rows: dict[str, dict[str, int | None]] = {}
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        added_raw, deleted_raw, path_raw = parts[0], parts[1], parts[2]
        path = path_raw.split(" => ", 1)[-1].strip("{}") if " => " in path_raw else path_raw
        try:
            added = int(added_raw)
        except ValueError:
            added = None
        try:
            deleted = int(deleted_raw)
        except ValueError:
            deleted = None
        rows[path] = {"addedLines": added, "deletedLines": deleted}
    return rows


def clearance_results(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = payload.get("results") if isinstance(payload.get("results"), list) else []
    return {
        str(row.get("id")): row
        for row in rows
        if isinstance(row, dict) and row.get("id")
    }


def looks_execution_adjacent(path: str) -> bool:
    text = path.lower()
    return any(token in text for token in EXECUTION_PATTERNS)


def load_cron_jobs(path: Path = CRON_JOBS) -> list[dict[str, Any]]:
    data = read_json(path)
    jobs = data.get("jobs") if isinstance(data.get("jobs"), list) else []
    return [job for job in jobs if isinstance(job, dict)]


def cron_references_by_script(jobs: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    refs: dict[str, list[dict[str, Any]]] = {}
    for job in jobs:
        script = str(job.get("script") or "")
        if not script:
            continue
        enabled = job.get("enabled") is True and job.get("state") != "paused"
        row = {
            "id": job.get("id"),
            "name": job.get("name"),
            "script": script,
            "enabled": enabled,
            "state": job.get("state"),
            "noAgent": job.get("no_agent") is True,
            "lastStatus": job.get("last_status"),
            "operatorAction": (
                "If enabled, operator must either pause this cron until source review clears, "
                "or manually clear the referenced execution-live diff packet."
            ),
            "safeAutomaticAction": False,
            "approvalRequired": True,
        }
        refs.setdefault(Path(script).name, []).append(row)
    return refs


def execution_paths(worktree: dict[str, Any], git_status: dict[str, str]) -> list[str]:
    canonical = worktree.get("canonicalSource") if isinstance(worktree.get("canonicalSource"), dict) else {}
    paths = {
        str(path)
        for path in canonical.get("executionLiveFiles", [])
        if path and str(path) not in SELF_REVIEWED_PATHS
    }
    for path in git_status:
        if path in SELF_REVIEWED_PATHS:
            continue
        if path.startswith(EXECUTION_ADJACENT_PREFIXES) and looks_execution_adjacent(path):
            paths.add(path)
    return sorted(paths)


def classify(path: str, firewall_id: str | None, firewall_passed: bool | None) -> str:
    if path in READ_ONLY_BROKER_EVIDENCE_PATHS:
        return "read-only-broker-evidence-review"
    if path in READ_ONLY_CONTROL_EVIDENCE_PATHS:
        return "read-only-control-evidence-review"
    if path in RESEARCH_SHADOW_BRIDGE_PATHS:
        return "research-shadow-bridge-review"
    if path in EXECUTION_VERIFIER_WRAPPER_PATHS:
        return "execution-verifier-wrapper-review"
    if firewall_id and firewall_passed is True:
        return "firewall-covered-still-quarantined"
    if firewall_id and firewall_passed is not True:
        return "firewall-missing-or-failed"
    if path.startswith("tests/"):
        return "execution-test-review"
    if path.startswith("scripts/verify_"):
        return "firewall-verifier-review"
    return "manual-route-review-required"


def build_manifest(
    *,
    worktree: dict[str, Any],
    clearance: dict[str, Any],
    git_status: dict[str, str],
    cron_jobs: list[dict[str, Any]] | None = None,
    diff_stats: dict[str, dict[str, int | None]] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    results = clearance_results(clearance)
    canonical = worktree.get("canonicalSource") if isinstance(worktree.get("canonicalSource"), dict) else {}
    canonical_categories = canonical.get("categories") if isinstance(canonical.get("categories"), dict) else {}
    canonical_execution_live_dirty = int(canonical_categories.get("execution-live") or 0)
    cron_refs = cron_references_by_script(cron_jobs or [])
    items: list[dict[str, Any]] = []
    for rel in execution_paths(worktree, git_status):
        firewall_id = FIREWALL_MAP.get(rel)
        firewall = results.get(firewall_id or "")
        firewall_passed = firewall.get("passed") if firewall else None
        path = ROOT / rel
        active_cron_refs = [
            ref
            for ref in cron_refs.get(Path(rel).name, [])
            if ref.get("enabled") is True
        ]
        items.append({
            "relativePath": rel,
            "path": str(path),
            "gitStatus": git_status.get(rel, "not-dirty-in-git-status"),
            "exists": path.exists(),
            "firewallId": firewall_id,
            "firewallPassed": firewall_passed,
            "classification": classify(rel, firewall_id, firewall_passed),
            "researchOnly": True,
            "writesOrders": False,
            "touchesBroker": False,
            "movesFunds": False,
            "readyForExecution": False,
            "activeCronReferences": active_cron_refs,
            "activeCronReferenceCount": len(active_cron_refs),
            "diffStats": diff_stats.get(rel, {}) if diff_stats else {},
        })
    class_counts = Counter(str(item["classification"]) for item in items)
    active_cron_reference_count = sum(int(item.get("activeCronReferenceCount") or 0) for item in items)
    active_cron_reference_paths = [
        item["relativePath"]
        for item in items
        if int(item.get("activeCronReferenceCount") or 0) > 0
    ]
    uncovered = [
        item["relativePath"]
        for item in items
        if item["classification"] in {"manual-route-review-required", "firewall-missing-or-failed"}
    ]
    active_cron_diff_review = [
        {
            "relativePath": item["relativePath"],
            "gitStatus": item.get("gitStatus"),
            "classification": item.get("classification"),
            "firewallId": item.get("firewallId"),
            "firewallPassed": item.get("firewallPassed"),
            "diffStats": item.get("diffStats") if isinstance(item.get("diffStats"), dict) else {},
            "activeCronReferences": item.get("activeCronReferences") if isinstance(item.get("activeCronReferences"), list) else [],
            "operatorAction": "Manual operator review required: pause the cron or clear the referenced diff packet after firewall and source review.",
            "safeAutomaticAction": False,
            "approvalRequired": True,
            "readyForExecution": False,
            "researchOnly": True,
            "writesOrders": False,
            "touchesBroker": False,
            "movesFunds": False,
        }
        for item in items
        if int(item.get("activeCronReferenceCount") or 0) > 0
    ]
    firewall_commands = [
        "npm run --silent bill:verify-master-bridge-firewall",
        "npm run --silent bill:verify-60m-bridge-firewall",
        "npm run --silent bill:verify-topstep-demo-bridge-firewall",
        "npm run --silent bill:verify-signal-router-firewall",
        "npm run --silent bill:verify-prediction-funding-firewall",
        "npm run --silent bill:verify-execution-quarantine",
    ]
    next_commands = [
        *firewall_commands,
        "npm run --silent bill:execution-intake-manifest",
        "npm run --silent bill:clearance-evidence",
        "npm run --silent bill:goal-completion-audit",
        "npm run --silent bill:obsidian-sync",
    ]
    external_bridges = [
        {
            "id": "hermes-topstep-demo-bridge",
            "path": str(EXTERNAL_TOPSTEP_DEMO_BRIDGE),
            "exists": EXTERNAL_TOPSTEP_DEMO_BRIDGE.exists(),
            "sha256": file_sha256(EXTERNAL_TOPSTEP_DEMO_BRIDGE),
            "firewallId": "verify-topstep-demo-bridge-firewall",
            "firewallPassed": results.get("verify-topstep-demo-bridge-firewall", {}).get("passed"),
            "researchOnly": True,
            "writesOrders": False,
            "touchesBroker": False,
            "movesFunds": False,
            "readyForExecution": False,
            "operatorAction": (
                "This external Hermes bridge is the audited Topstep OCO submitter. "
                "Do not route through it unless the daily plan, broker reconciliation, "
                "goal audit, and bridge firewall all clear."
            ),
        }
    ]
    return {
        "command": "bill-execution-intake-manifest",
        "generatedAt": generated_at or now_iso(),
        "decision": "execution-intake-visible-execution-locked",
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "movesFunds": False,
        "readyForExecution": False,
        "readyForDemoExpansion": False,
        "readyForLive": False,
        "executionLocked": True,
        "dirtyExecutionFileCount": canonical_execution_live_dirty or len(items),
        "canonicalExecutionLiveDirtyCount": canonical_execution_live_dirty,
        "executionAdjacentFileCount": len(items),
        "activeCronReferenceCount": active_cron_reference_count,
        "activeCronReferencePaths": active_cron_reference_paths,
        "activeCronDiffReview": active_cron_diff_review,
        "classificationCounts": dict(sorted(class_counts.items())),
        "firewallEvidenceStatus": clearance.get("status", "missing"),
        "allFirewallCommandsPassed": all(
            results.get(firewall_id, {}).get("passed") is True
            for firewall_id in sorted(set(FIREWALL_MAP.values()))
        ),
        "uncoveredExecutionPaths": uncovered,
        "items": items,
        "externalBridgeEvidence": external_bridges,
        "nextCommands": next_commands,
        "validationCommandSets": {
            "executionFirewallEvidence": [
                *firewall_commands,
                "npm run --silent bill:clearance-evidence",
            ],
            "firewallEvidence": firewall_commands,
            "executionVisibilityRefresh": [
                "npm run --silent bill:execution-intake-manifest",
                "npm run --silent bill:clearance-evidence",
                "npm run --silent bill:goal-completion-audit",
                "npm run --silent bill:obsidian-sync",
            ],
            "operatorRead": "Firewall evidence proves no-order/no-funding guardrails only. It does not clear source hygiene, route approval, broker writes, or live/demo execution.",
            "activeCronReferenceReview": [
                "npm run --silent bill:execution-intake-manifest",
                "npm run --silent bill:cron-state-validator",
                "npm run --silent bill:goal-completion-audit",
                "npm run --silent bill:obsidian-sync",
            ],
        },
        "hardRules": [
            "Firewall-covered does not mean source-clean or execution-approved.",
            "Manual-route-review files remain quarantined until they have explicit no-order evidence.",
            "Active cron references to dirty execution-live files require operator review; this manifest only exposes them.",
            "Do not route, fund, size, or submit from any file in this manifest.",
            "Keep BILL_ENABLE_FUTURES_DEMO_EXECUTION=false, RH_TOPSTEP_READ_ONLY=true, and RH_LIVE_EXECUTION_ENABLED=false.",
        ],
    }


def render_markdown(payload: dict[str, Any]) -> str:
    manifest_date = str(payload.get("generatedAt") or now_iso())[:10]
    lines = [
        f"# Bill Execution Intake Manifest - {manifest_date}",
        "",
        "Parent hub: [[BILL-CONTROL-HUB]]",
        "",
        "Read-only execution-live map. This page does not approve routing, sizing, funding, orders, or broker access.",
        "",
        "## Decision",
        "",
        f"- Decision: `{payload.get('decision')}`",
        f"- Execution locked: `{payload.get('executionLocked')}`",
        f"- Dirty execution files: `{payload.get('dirtyExecutionFileCount')}`",
        f"- Canonical execution-live dirty count: `{payload.get('canonicalExecutionLiveDirtyCount')}`",
        f"- Execution-adjacent review files: `{payload.get('executionAdjacentFileCount')}`",
        f"- Active cron references to dirty execution files: `{payload.get('activeCronReferenceCount', 0)}`",
        f"- Active cron reference paths: `{payload.get('activeCronReferencePaths', [])}`",
        f"- Firewall evidence status: `{payload.get('firewallEvidenceStatus')}`",
        f"- All mapped firewall commands passed: `{payload.get('allFirewallCommandsPassed')}`",
        f"- Classification counts: `{payload.get('classificationCounts')}`",
        f"- Uncovered execution paths: `{payload.get('uncoveredExecutionPaths')}`",
        f"- External bridge evidence: `{payload.get('externalBridgeEvidence')}`",
        "",
        "## Active Cron Diff Review",
        "",
    ]
    active_cron_review = payload.get("activeCronDiffReview") if isinstance(payload.get("activeCronDiffReview"), list) else []
    if not active_cron_review:
        lines.append("- none")
    for item in active_cron_review:
        lines.append(f"### `{item.get('relativePath')}`")
        lines.append("")
        lines.append(f"- Status: `{item.get('gitStatus')}`")
        lines.append(f"- Classification: `{item.get('classification')}`")
        lines.append(f"- Firewall: `{item.get('firewallId')}` passed `{item.get('firewallPassed')}`")
        lines.append(f"- Diff stats: `{item.get('diffStats')}`")
        lines.append(f"- Operator action: {item.get('operatorAction')}")
        for ref in item.get("activeCronReferences") or []:
            lines.append(
                f"  - Cron `{ref.get('name')}` id `{ref.get('id')}` enabled `{ref.get('enabled')}` "
                f"state `{ref.get('state')}` safeAuto `{ref.get('safeAutomaticAction')}`"
            )
        lines.append("")
    lines.extend([
        "## Files",
        "",
    ])
    for item in payload.get("items") or []:
        lines.append(f"### `{item.get('relativePath')}`")
        lines.append("")
        lines.append(f"- Status: `{item.get('gitStatus')}`")
        lines.append(f"- Classification: `{item.get('classification')}`")
        lines.append(f"- Firewall: `{item.get('firewallId')}` passed `{item.get('firewallPassed')}`")
        lines.append(f"- Ready for execution: `{item.get('readyForExecution')}`")
        lines.append(f"- Active cron references: `{item.get('activeCronReferenceCount', 0)}`")
        for ref in item.get("activeCronReferences") or []:
            lines.append(
                f"  - `{ref.get('name')}` id `{ref.get('id')}` enabled `{ref.get('enabled')}` "
                f"noAgent `{ref.get('noAgent')}` lastStatus `{ref.get('lastStatus')}`"
            )
        lines.append("")
    if payload.get("nextCommands"):
        lines.extend(["## Next Commands", ""])
        for command in payload.get("nextCommands") or []:
            lines.append(f"- `{command}`")
        lines.append("")
    validation = payload.get("validationCommandSets") if isinstance(payload.get("validationCommandSets"), dict) else {}
    if validation:
        lines.extend(["## Validation Command Sets", ""])
        lines.append("These are execution-safety review commands only. They do not approve routing or broker writes.")
        lines.append("")
        for key, commands in validation.items():
            if isinstance(commands, list):
                lines.append(f"### `{key}`")
                for command in commands:
                    lines.append(f"- `{command}`")
                lines.append("")
        if validation.get("operatorRead"):
            lines.append(f"- Operator read: {validation.get('operatorRead')}")
            lines.append("")
    lines.extend(["## Hard Rules", ""])
    for rule in payload.get("hardRules") or []:
        lines.append(f"- {rule}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Bill/Hermes read-only execution intake manifest.")
    parser.add_argument("--worktree", default=str(STATE / "worktree-consolidation.latest.json"))
    parser.add_argument("--clearance", default=str(STATE / "bill-clearance-evidence.latest.json"))
    parser.add_argument("--output", default=str(OUT))
    parser.add_argument("--markdown", default=None)
    args = parser.parse_args()

    payload = build_manifest(
        worktree=read_json(Path(args.worktree)),
        clearance=read_json(Path(args.clearance)),
        git_status=parse_git_status(git_status_text()),
        cron_jobs=load_cron_jobs(),
        diff_stats=parse_numstat(git_diff_numstat_text()),
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    markdown = Path(args.markdown) if args.markdown else default_markdown_path()
    markdown.parent.mkdir(parents=True, exist_ok=True)
    markdown.write_text(render_markdown(payload))
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
