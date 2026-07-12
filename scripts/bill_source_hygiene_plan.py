#!/usr/bin/env python3
"""Build a read-only Bill/Hermes source hygiene plan.

The source/data/execution intake manifests answer "what is dirty?". This plan
answers "what should a human or weaker agent reduce first?" without staging,
deleting, reverting, routing, or promoting anything.
"""
from __future__ import annotations

import argparse
import json
import shlex
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
VAULT = Path.home() / "Documents" / "memorybrain"
HERMES = VAULT / "Agent-Hermes"
DEFAULT_OUTPUT = STATE / "bill-source-hygiene-plan.latest.json"

BROKER_TOUCHING_VALIDATION_TERMS = (
    "bill:clearance-evidence",
    "bill:open-session-data-proof",
    "bill:topstep-readonly-bar-archive",
    "bill:topstep-realtime-proof",
    "bill:topstep-realtime-bridge",
)

MAX_CLEARANCE_SUB_BATCH_PATHS = 20

CONTROL_RESEARCH_PRIORITY_PATHS = (
    "ai-scientist-templates/financial_strategy/experiment.py",
    "ai-scientist-templates/financial_strategy/seed_ideas.json",
    "tests/test_ai_scientist_financial_template.py",
    "ops/activate-bill-workflows.sh",
    "scripts/codex_automation_audit.py",
    "tests/test_codex_automation_audit.py",
    "scripts/bill_source_intake_manifest.py",
    "tests/test_bill_source_intake_manifest.py",
    "scripts/bill_source_hygiene_plan.py",
    "tests/test_bill_source_hygiene_plan.py",
    "scripts/bill_source_packet_review.py",
    "tests/test_bill_source_packet_review.py",
    "command-center.html",
    "command_center_server.py",
    "tests/test_command_center_server.py",
    "scripts/bill_clearance_handoff.py",
    "tests/test_bill_clearance_handoff.py",
    "scripts/bill_goal_completion_audit.py",
    "tests/test_bill_goal_completion_audit.py",
    "scripts/bill_runtime_architecture_audit.py",
    "tests/test_bill_runtime_architecture_audit.py",
    "scripts/bill_fund_os_completion_audit.py",
    "tests/test_bill_fund_os_completion_audit.py",
    "scripts/stale_strategy_claim_guard.py",
    "tests/test_stale_strategy_claim_guard.py",
    "tests/test_strategy_evidence_copy.py",
    "scripts/bill_research_closed_loop_contract.py",
    "tests/test_bill_research_closed_loop_contract.py",
    "scripts/research_seed_target_refresh_plan.py",
    "tests/test_research_seed_target_refresh_plan.py",
    "scripts/research_seed_triage.py",
    "tests/test_research_seed_triage.py",
    "scripts/sync_bill_obsidian.py",
    "tests/test_sync_bill_obsidian.py",
    "scripts/alpha_research_direction_audit.py",
    "tests/test_alpha_research_direction_audit.py",
    "scripts/bill_open_session_data_proof.py",
    "tests/test_bill_open_session_data_proof.py",
    "scripts/build_data_master_csv.py",
    "tests/test_build_data_master_csv.py",
    "scripts/verify_no_execution_enabled_processes.py",
    "tests/test_verify_no_execution_processes.py",
    "scripts/topstep_daily_learning.py",
    "tests/test_topstep_daily_learning.py",
    "scripts/topstep_demo_observation_posture.py",
    "tests/test_topstep_demo_observation_posture.py",
    "tests/test_topstep_runtime_semantics.py",
    "scripts/realtime_data_preflight.py",
    "tests/test_realtime_data_preflight.py",
    "scripts/premarket_risk_brief.py",
    "tests/test_premarket_risk_brief.py",
    "scripts/signal_quality_advisor.py",
    "tests/test_signal_quality_advisor.py",
    "scripts/signal_source_truth_audit.py",
    "tests/test_signal_source_truth_audit.py",
    "scripts/ai_screener.py",
    "tests/test_ai_screener.py",
)

FUTURES_LANE_PRIORITY_PATHS = (
    "scripts/futures_evidence_triage.py",
    "tests/test_futures_evidence_triage.py",
    "scripts/futures_nq_historical_session_replay.py",
    "tests/test_futures_nq_historical_session_replay.py",
    "scripts/futures_nq_historical_session_walkforward.py",
    "tests/test_futures_nq_historical_session_walkforward.py",
    "scripts/futures_nq_historical_session_cost_stress.py",
    "tests/test_futures_nq_historical_session_cost_stress.py",
    "scripts/futures_no_edge_ledger.py",
    "tests/test_futures_no_edge_ledger.py",
    "scripts/futures_nq_sizing_overlay.py",
    "tests/test_futures_nq_sizing_overlay.py",
    "scripts/futures_nq_research_cycle.py",
    "scripts/futures_broker_parity_plan.py",
    "scripts/futures_data_requirements.py",
    "tests/test_futures_data_requirements.py",
    "scripts/topstep_market_data_smoke.py",
    "tests/test_topstep_market_data_smoke.py",
    "scripts/topstep_readonly_bar_archive.py",
    "tests/test_topstep_readonly_bar_archive.py",
    "scripts/topstep_broker_local_bar_parity.py",
    "tests/test_topstep_broker_local_bar_parity.py",
    "scripts/topstep_realtime_proof.py",
    "tests/test_topstep_realtime_proof.py",
    "scripts/futures_cost_slippage_gate.py",
    "scripts/bill_open_session_data_proof.py",
    "tests/test_bill_open_session_data_proof.py",
    "scripts/realtime_data_preflight.py",
    "tests/test_realtime_data_preflight.py",
    "scripts/signal_quality_advisor.py",
    "tests/test_signal_quality_advisor.py",
    "scripts/databento_orderflow_feature_smoke.py",
    "tests/test_databento_orderflow_feature_smoke.py",
    "scripts/databento_realtime_smoke.py",
    "tests/test_databento_realtime_smoke.py",
    "scripts/futures_data_quality_snapshot.py",
    "tests/test_futures_data_quality_snapshot.py",
    "scripts/futures_nq_current_data_parity.py",
    "tests/test_futures_nq_current_data_parity.py",
    "scripts/data_freshness_gate.py",
    "tests/test_data_freshness_gate.py",
    "scripts/alpha_frontier_queue.py",
    "tests/test_alpha_frontier_queue.py",
    "scripts/bill_next_research_actions.py",
    "tests/test_bill_next_research_actions.py",
)

PREDICTION_LANE_PRIORITY_PATHS = (
    "scripts/prediction_event_capture_cycle.py",
    "tests/test_prediction_event_capture_cycle.py",
    "scripts/prediction_event_lag_sensitivity.py",
    "tests/test_prediction_event_lag_sensitivity.py",
    "scripts/prediction_event_lag_watch_review.py",
    "tests/test_prediction_event_lag_watch_review.py",
    "scripts/prediction_event_lag_manual_review.py",
    "tests/test_prediction_event_lag_manual_review.py",
    "scripts/prediction_event_mapping_refinement.py",
    "tests/test_prediction_event_mapping_refinement.py",
    "scripts/prediction_event_lag_replay.py",
    "tests/test_prediction_event_lag_replay.py",
    "scripts/prediction_evidence_triage.py",
    "tests/test_prediction_evidence_triage.py",
    "scripts/polymarket_clob_recorder.mjs",
    "tests/polymarketClobRecorder.test.ts",
    "scripts/polymarket_clob_persistence_lab.mjs",
    "tests/polymarketClobPersistence.test.ts",
    "scripts/prediction_clob_trade_impact_replay.py",
    "tests/test_prediction_clob_trade_impact_replay.py",
    "scripts/prediction_event_timestamp_dataset.py",
    "tests/test_prediction_event_timestamp_dataset.py",
    "scripts/finnhub_news.py",
    "tests/test_finnhub_news.py",
    "scripts/free_data_feed_audit.py",
    "tests/test_free_data_feed_audit.py",
    "scripts/topstep_session_safety_clearance.py",
    "tests/test_topstep_session_safety_clearance.py",
    "scripts/founder_quant_cto_metaprompt.py",
    "tests/test_founder_quant_cto_metaprompt.py",
    "scripts/strategy_test_framework_status.py",
    "tests/test_strategy_test_framework_status.py",
    "scripts/cron_brain_tick.sh",
    "scripts/cron_verify_execution_quarantine.sh",
    "scripts/cron_verify_master_bridge.sh",
    "scripts/cron_verify_no_execution.sh",
    "scripts/cron_verify_topstep_demo.sh",
    "tests/test_cron_research_wrappers.py",
    "scripts/prediction_no_edge_ledger.py",
    "tests/test_prediction_no_edge_ledger.py",
    "scripts/alpha_frontier_queue.py",
    "tests/test_alpha_frontier_queue.py",
    "scripts/bill_next_research_actions.py",
    "tests/test_bill_next_research_actions.py",
    "scripts/prediction_macro_rates_requirements.py",
    "tests/test_prediction_macro_rates_requirements.py",
    "scripts/prediction_macro_rates_cross_source_replay.py",
    "tests/test_prediction_macro_rates_cross_source_replay.py",
    "scripts/prediction_macro_rates_parser_fixture.py",
    "tests/test_prediction_macro_rates_parser_fixture.py",
    "scripts/prediction_macro_rates_resolved_labels.py",
    "tests/test_prediction_macro_rates_resolved_labels.py",
    "scripts/kalshi_fillability_snapshot.py",
    "tests/test_kalshi_fillability_snapshot.py",
)

DEPENDENCY_REVIEW_PRIORITY_PATHS = (
    "package.json",
    "package-lock.json",
    "requirements.bill-alpha.txt",
)


def default_markdown_path() -> Path:
    plan_date = datetime.now(timezone.utc).date().isoformat()
    return HERMES / f"bill-source-hygiene-plan-{plan_date}.md"


def read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text())
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return False


def topstep_proofs_paused(session_safety: dict[str, Any]) -> bool:
    return bool_value(session_safety.get("pauseBrokerTouchingProofs")) or bool_value(session_safety.get("topstepMultipleSessionsDetected"))


def filter_validation_commands_for_session_safety(commands: list[str], *, proof_paused: bool) -> tuple[list[str], list[str]]:
    if not proof_paused:
        return commands, []
    kept: list[str] = []
    suppressed: list[str] = []
    for command in commands:
        if any(term in command for term in BROKER_TOUCHING_VALIDATION_TERMS):
            suppressed.append(command)
        else:
            kept.append(command)
    if suppressed and "npm run --silent bill:goal-completion-audit" not in kept:
        kept.append("npm run --silent bill:goal-completion-audit")
    if suppressed and "npm run --silent bill:clearance-handoff" not in kept:
        kept.append("npm run --silent bill:clearance-handoff")
    return kept, suppressed


def clearance_status_summary(path: Path = STATE / "bill-clearance-evidence.latest.json") -> dict[str, Any]:
    payload = read_json(path)
    if not payload:
        return {
            "present": False,
            "status": "missing",
            "allCommandsPassed": False,
            "failedCommandIds": [],
            "coveredCommandIds": [],
        }
    results = payload.get("results") if isinstance(payload.get("results"), list) else []
    return {
        "present": True,
        "status": payload.get("status"),
        "allCommandsPassed": payload.get("allCommandsPassed"),
        "failedCommandIds": payload.get("failedCommandIds", []),
        "coveredCommandIds": [
            item.get("id")
            for item in results
            if isinstance(item, dict) and item.get("id")
        ],
        "readyForExecution": payload.get("readyForExecution"),
        "writesOrders": payload.get("writesOrders"),
        "touchesBroker": payload.get("touchesBroker"),
    }


def sample_paths(items: Any, limit: int = 12) -> list[str]:
    if not isinstance(items, list):
        return []
    paths: list[str] = []
    for item in items:
        if isinstance(item, dict):
            path = item.get("relativePath") or item.get("path")
        else:
            path = item
        if path:
            paths.append(str(path))
        if len(paths) >= limit:
            break
    return paths


def path_from_item(item: Any) -> str | None:
    if isinstance(item, dict):
        path = item.get("relativePath") or item.get("path")
        return str(path) if path else None
    if item:
        return str(item)
    return None


def source_samples(source: dict[str, Any], classification: str, limit: int = 12) -> list[str]:
    samples = source.get("requiresReviewSamples")
    if not isinstance(samples, dict):
        return []
    return sample_paths(samples.get(classification), limit=limit)


def status_from_items(*groups: Any) -> dict[str, str]:
    statuses: dict[str, str] = {}
    for group in groups:
        if isinstance(group, dict):
            group = group.values()
        if not isinstance(group, list) and not hasattr(group, "__iter__"):
            continue
        for item in group:
            if isinstance(item, list):
                statuses.update(status_from_items(item))
                continue
            if not isinstance(item, dict):
                continue
            path = path_from_item(item)
            status = item.get("status") or item.get("gitStatus")
            if path and status:
                statuses[path] = str(status)
    return statuses


def git_numstat(paths: list[str]) -> dict[str, dict[str, int]]:
    if not paths:
        return {}
    proc = subprocess.run(
        ["git", "diff", "--numstat", "--", *paths],
        cwd=ROOT,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        return {}
    stats: dict[str, dict[str, int]] = {}
    for line in proc.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        added, deleted, path = parts[0], parts[1], parts[2]
        if added == "-" or deleted == "-":
            continue
        try:
            stats[path] = {"addedLines": int(added), "deletedLines": int(deleted)}
        except ValueError:
            continue
    return stats


def parse_git_status_line(line: str) -> tuple[str, str] | None:
    if len(line) < 4:
        return None
    status = line[:2].strip() or line[:2]
    path = line[3:].strip()
    if not path:
        return None
    if " -> " in path:
        path = path.split(" -> ", 1)[1].strip()
    return path, status


def git_status_entries() -> dict[str, str]:
    proc = subprocess.run(
        ["git", "status", "--short", "--untracked-files=all"],
        cwd=ROOT,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        return {}
    entries: dict[str, str] = {}
    for line in proc.stdout.splitlines():
        parsed = parse_git_status_line(line)
        if not parsed:
            continue
        path, status = parsed
        entries[path] = status
    return entries


def dedupe_paths(paths: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        result.append(path)
    return result


def path_matches_terms(path: str, terms: tuple[str, ...]) -> bool:
    lower = path.lower()
    return any(term.lower() in lower for term in terms)


def prioritize_paths(paths: list[str], priority_paths: tuple[str, ...]) -> list[str]:
    available = set(paths)
    selected = [path for path in priority_paths if path in available]
    selected.extend(path for path in paths if path not in set(selected))
    return selected


def py_compile_review_command(paths: list[str]) -> str:
    py_paths = [path for path in dedupe_paths(paths) if path.endswith(".py")]
    fallback = ["scripts/bill_source_hygiene_plan.py", "scripts/bill_goal_completion_audit.py"]
    selected = py_paths or fallback
    return "python3 -m py_compile " + " ".join(shlex.quote(path) for path in selected)


def shell_quoted_paths(paths: list[str]) -> str:
    return " ".join(shlex.quote(path) for path in dedupe_paths(paths))


def packet_review_commands(paths: list[str]) -> list[str]:
    if any(path.startswith("/") and ":" in path for path in paths):
        return []
    quoted = shell_quoted_paths(paths)
    if not quoted:
        return []
    return [
        f"git status --short -- {quoted}",
        f"git diff -- {quoted}",
    ]


def manual_stage_command(paths: list[str]) -> str:
    quoted = shell_quoted_paths(paths)
    if not quoted:
        return "no paths selected; nothing to stage"
    return f"git add -- {quoted}"


def blocked_stage_command(reason: str) -> str:
    return f"blocked for this packet: {reason}"


def lane_paths(
    paths: list[str],
    *,
    include_terms: tuple[str, ...],
    exclude_paths: set[str],
    exclude_terms: tuple[str, ...] = (),
    limit: int = 24,
) -> list[str]:
    terms = tuple(term.lower() for term in include_terms)
    blocked_terms = tuple(term.lower() for term in exclude_terms)
    selected: list[str] = []
    for path in paths:
        if path in exclude_paths:
            continue
        lower = path.lower()
        if any(term in lower for term in blocked_terms):
            continue
        if any(term in lower for term in terms):
            selected.append(path)
        if len(selected) >= limit:
            break
    return dedupe_paths(selected)


def prioritized_lane_paths(
    paths: list[str],
    *,
    priority_paths: tuple[str, ...],
    include_terms: tuple[str, ...],
    exclude_paths: set[str],
    exclude_terms: tuple[str, ...] = (),
    limit: int = 24,
) -> list[str]:
    """Return lane paths with current frontier artifacts first.

    The dirty tree is large and git-status order can bury the active futures and
    prediction-market research controls. Priority paths keep the handoff packet
    useful for humans and weaker agents without clearing, staging, or promoting
    anything.
    """
    available = set(paths)
    prioritized = [
        path
        for path in priority_paths
        if path in available and path not in exclude_paths
    ]
    remaining = lane_paths(
        paths,
        include_terms=include_terms,
        exclude_paths=exclude_paths | set(prioritized),
        exclude_terms=exclude_terms,
        limit=limit,
    )
    return dedupe_paths([*prioritized, *remaining])[:limit]


def packet_footprint(paths: list[str], statuses: dict[str, str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    diff_stats = git_numstat(paths)
    rows: list[dict[str, Any]] = []
    for path in paths:
        abs_path = ROOT / path
        stats = diff_stats.get(path, {})
        rows.append({
            "path": path,
            "status": statuses.get(path, "status-not-in-intake"),
            "exists": abs_path.exists(),
            "addedLines": stats.get("addedLines", 0),
            "deletedLines": stats.get("deletedLines", 0),
            "trackedDiff": path in diff_stats,
        })
    summary = {
        "pathCount": len(paths),
        "existingPathCount": sum(1 for row in rows if row["exists"]),
        "trackedDiffPathCount": sum(1 for row in rows if row["trackedDiff"]),
        "addedLines": sum(int(row["addedLines"]) for row in rows),
        "deletedLines": sum(int(row["deletedLines"]) for row in rows),
        "statusCounts": {},
    }
    for row in rows:
        status = str(row["status"])
        summary["statusCounts"][status] = summary["statusCounts"].get(status, 0) + 1
    return rows, summary


def clearance_queue_summary(worktree: dict[str, Any], limit: int = 8) -> list[dict[str, Any]]:
    queue = worktree.get("clearanceQueue") if isinstance(worktree.get("clearanceQueue"), list) else []
    rows: list[dict[str, Any]] = []
    for item in queue[:limit]:
        if not isinstance(item, dict):
            continue
        rows.append({
            "priority": item.get("priority"),
            "lane": item.get("lane"),
            "dirtyFiles": item.get("dirtyFiles"),
            "sampleFiles": item.get("sampleFiles", [])[:8] if isinstance(item.get("sampleFiles"), list) else [],
            "action": item.get("action"),
            "requiredEvidence": item.get("requiredEvidence", []) if isinstance(item.get("requiredEvidence"), list) else [],
        })
    return rows


def sibling_worktree_summary(sibling: dict[str, Any]) -> dict[str, Any]:
    if not sibling:
        return {
            "present": False,
            "decision": "missing",
            "dirtySiblingWorktreeCount": 0,
            "dirtyFileCount": 0,
            "executionLiveDirtyCount": 0,
            "classificationCounts": {},
            "blockers": [],
            "topReviewFirst": [],
        }
    top_review: list[str] = []
    for worktree in sibling.get("worktrees") or []:
        if not isinstance(worktree, dict):
            continue
        path = str(worktree.get("path") or "")
        for item in worktree.get("topReviewFirst") or []:
            item_path = str(item)
            top_review.append(f"{path}:{item_path}" if path else item_path)
            if len(top_review) >= 12:
                break
        if len(top_review) >= 12:
            break
    return {
        "present": True,
        "decision": sibling.get("decision", "missing"),
        "dirtySiblingWorktreeCount": int(sibling.get("dirtySiblingWorktreeCount", 0) or 0),
        "dirtyFileCount": int(sibling.get("dirtyFileCount", 0) or 0),
        "executionLiveDirtyCount": int(sibling.get("executionLiveDirtyCount", 0) or 0),
        "classificationCounts": sibling.get("classificationCounts", {})
        if isinstance(sibling.get("classificationCounts"), dict)
        else {},
        "blockers": sibling.get("blockers", [])
        if isinstance(sibling.get("blockers"), list)
        else [],
        "topReviewFirst": top_review,
        "safeToMergeAutomatically": bool(sibling.get("safeToMergeAutomatically")),
    }


def packet(
    *,
    packet_id: str,
    bundle_id: str,
    title: str,
    paths: list[str],
    commands: list[str],
    decision: str,
    why: str,
    statuses: dict[str, str] | None = None,
    manual_stage_allowed: bool = True,
    manual_stage_block_reason: str = "operator approval required",
) -> dict[str, Any]:
    footprint, diff_summary = packet_footprint(paths, statuses or {})
    manual_stage_warning = "Manual operator review required; do not run this automatically."
    stage_command = manual_stage_command(paths)
    if not manual_stage_allowed:
        manual_stage_warning = "Manual staging is blocked for this packet."
        stage_command = blocked_stage_command(manual_stage_block_reason)
    return {
        "id": packet_id,
        "bundleId": bundle_id,
        "title": title,
        "paths": paths,
        "pathCount": len(paths),
        "pathFootprint": footprint,
        "diffSummary": diff_summary,
        "reviewCommands": packet_review_commands(paths),
        "manualStageEligible": manual_stage_allowed,
        "manualStageCommand": stage_command,
        "manualStageWarning": manual_stage_warning,
        "commands": commands,
        "decision": decision,
        "why": why,
        "researchOnly": True,
        "safeToStageAutomatically": False,
        "automaticCleanupAllowed": False,
        "operatorApprovalRequired": True,
        "writesOrders": False,
        "touchesBroker": False,
        "movesFunds": False,
        "readyForExecution": False,
    }


def review_packet_risk_summary(packets: list[dict[str, Any]]) -> dict[str, Any]:
    status_counts: dict[str, int] = {}
    packet_rows: list[dict[str, Any]] = []
    blocked_stage_packets: list[str] = []
    manual_stage_packets: list[str] = []
    total_paths = 0
    tracked_diff_paths = 0
    added_lines = 0
    deleted_lines = 0
    for item in packets:
        if not isinstance(item, dict):
            continue
        packet_id = str(item.get("id") or "")
        diff = item.get("diffSummary") if isinstance(item.get("diffSummary"), dict) else {}
        path_count = int(diff.get("pathCount") or item.get("pathCount") or 0)
        tracked_count = int(diff.get("trackedDiffPathCount") or 0)
        total_paths += path_count
        tracked_diff_paths += tracked_count
        added_lines += int(diff.get("addedLines") or 0)
        deleted_lines += int(diff.get("deletedLines") or 0)
        for status, count in (diff.get("statusCounts") or {}).items():
            status_counts[str(status)] = status_counts.get(str(status), 0) + int(count or 0)
        if item.get("manualStageEligible"):
            manual_stage_packets.append(packet_id)
        else:
            blocked_stage_packets.append(packet_id)
        packet_rows.append({
            "id": packet_id,
            "bundleId": item.get("bundleId"),
            "decision": item.get("decision"),
            "pathCount": path_count,
            "trackedDiffPathCount": tracked_count,
            "statusCounts": diff.get("statusCounts", {}),
            "manualStageEligible": bool(item.get("manualStageEligible")),
            "writesOrders": bool(item.get("writesOrders")),
            "touchesBroker": bool(item.get("touchesBroker")),
            "movesFunds": bool(item.get("movesFunds")),
        })
    return {
        "packetCount": len(packet_rows),
        "pathCount": total_paths,
        "trackedDiffPathCount": tracked_diff_paths,
        "untrackedPathCount": int(status_counts.get("??", 0)),
        "modifiedPathCount": int(status_counts.get("M", 0)),
        "statusCounts": status_counts,
        "addedLines": added_lines,
        "deletedLines": deleted_lines,
        "manualStageEligiblePacketIds": manual_stage_packets,
        "blockedStagePacketIds": blocked_stage_packets,
        "packets": packet_rows,
        "operatorRead": "Risk summary only. Packets still require manual review and never authorize automatic staging, cleanup, execution, funding, or routing.",
    }


def diff_check_command(paths: list[str]) -> str | None:
    if not paths or any(path.startswith("/") and ":" in path for path in paths):
        return None
    quoted = shell_quoted_paths(paths)
    if not quoted:
        return None
    return f"git diff --check -- {quoted}"


def chunk_paths(paths: list[str], size: int = MAX_CLEARANCE_SUB_BATCH_PATHS) -> list[list[str]]:
    if size <= 0:
        return [paths]
    return [paths[index:index + size] for index in range(0, len(paths), size)]


def clearance_sub_batches(
    *,
    parent_id: str,
    packet_item: dict[str, Any],
    paths: list[str],
    statuses: dict[str, str],
) -> list[dict[str, Any]]:
    chunks = chunk_paths(paths)
    if len(chunks) <= 1:
        return []
    rows: list[dict[str, Any]] = []
    for index, chunk in enumerate(chunks, start=1):
        footprint, diff_summary = packet_footprint(chunk, statuses)
        review_commands = packet_review_commands(chunk)
        diff_check = diff_check_command(chunk)
        compile_command = py_compile_review_command(chunk) if any(path.endswith(".py") for path in chunk) else None
        rows.append({
            "id": f"{parent_id}-part-{index:02d}",
            "parentBatchId": parent_id,
            "packetId": packet_item.get("id"),
            "bundleId": packet_item.get("bundleId"),
            "decision": "manual-sub-batch-review-only",
            "pathCount": len(chunk),
            "paths": chunk,
            "pathFootprint": footprint,
            "diffSummary": diff_summary,
            "verificationCommands": [
                *review_commands,
                *([diff_check] if diff_check else []),
                *([compile_command] if compile_command else []),
                *[
                    command
                    for command in (packet_item.get("commands") or [])[:2]
                    if command
                ],
            ],
            "stagePolicy": "inherits-parent-manual-review-policy",
            "safeToStageAutomatically": False,
            "automaticCleanupAllowed": False,
            "operatorApprovalRequired": True,
            "researchOnly": True,
            "writesOrders": False,
            "touchesBroker": False,
            "movesFunds": False,
            "readyForExecution": False,
        })
    return rows


def source_clearance_batches(packets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Turn review packets into deterministic clearance batches.

    A batch is a review/checklist object only. It intentionally does not clear
    source hygiene or authorize staging by itself, but it gives humans and weaker
    agents exact paths plus proof commands for one coherent source-reduction pass.
    """
    batches: list[dict[str, Any]] = []
    for rank, packet_item in enumerate(packets, start=1):
        if not isinstance(packet_item, dict):
            continue
        paths = [str(path) for path in packet_item.get("paths") or [] if path]
        review_commands = [
            str(command)
            for command in packet_item.get("reviewCommands") or []
            if command
        ]
        evidence_commands = [
            str(command)
            for command in packet_item.get("commands") or []
            if command
        ]
        diff_check = diff_check_command(paths)
        stage_allowed = bool(packet_item.get("manualStageEligible"))
        batch_id = f"clearance-batch-{rank:02d}-{packet_item.get('bundleId')}"
        statuses = {
            str(row.get("path")): str(row.get("status"))
            for row in packet_item.get("pathFootprint") or []
            if isinstance(row, dict) and row.get("path")
        }
        sub_batches = clearance_sub_batches(
            parent_id=batch_id,
            packet_item=packet_item,
            paths=paths,
            statuses=statuses,
        )
        batches.append({
            "id": batch_id,
            "rank": rank,
            "packetId": packet_item.get("id"),
            "bundleId": packet_item.get("bundleId"),
            "title": packet_item.get("title"),
            "decision": "manual-clearance-review-only",
            "pathCount": len(paths),
            "oversizedForSingleReview": len(paths) > MAX_CLEARANCE_SUB_BATCH_PATHS,
            "recommendedSubBatchPathLimit": MAX_CLEARANCE_SUB_BATCH_PATHS,
            "subBatchCount": len(sub_batches),
            "subBatches": sub_batches,
            "paths": paths,
            "firstReviewCommand": review_commands[0] if review_commands else None,
            "firstEvidenceCommand": evidence_commands[0] if evidence_commands else None,
            "verificationCommands": [
                *review_commands,
                *([diff_check] if diff_check else []),
                *evidence_commands,
            ],
            "stagePolicy": "manual-operator-review-required" if stage_allowed else "manual-staging-blocked",
            "manualStageEligible": stage_allowed,
            "manualStageCommand": packet_item.get("manualStageCommand"),
            "clearanceEffect": (
                "Can reduce the source-hygiene blocker only after manual review, "
                "operator-approved staging/commit if applicable, regenerated manifests, "
                "and a goal audit showing the source-hygiene blocker removed."
            ),
            "blockedFromAutoClearance": True,
            "safeToStageAutomatically": False,
            "automaticCleanupAllowed": False,
            "operatorApprovalRequired": True,
            "researchOnly": True,
            "writesOrders": False,
            "touchesBroker": False,
            "movesFunds": False,
            "readyForExecution": False,
        })
    return batches


def clearance_ticket_for_bundle(item: dict[str, Any], rank: int) -> dict[str, Any]:
    commands = item.get("commands") if isinstance(item.get("commands"), list) else []
    blockers = item.get("blockers") if isinstance(item.get("blockers"), list) else []
    sample_paths_value = item.get("samplePaths") if isinstance(item.get("samplePaths"), list) else []
    return {
        "rank": rank,
        "bundleId": item.get("id"),
        "title": item.get("title"),
        "count": int(item.get("count") or 0),
        "decision": "manual-review-only",
        "firstEvidenceCommand": commands[0] if commands else None,
        "evidenceCommands": commands[:8],
        "samplePaths": sample_paths_value[:8],
        "blockers": blockers[:6],
        "safeToStageAutomatically": False,
        "automaticCleanupAllowed": False,
        "operatorApprovalRequired": True,
        "writesOrders": bool(item.get("writesOrders")),
        "touchesBroker": bool(item.get("touchesBroker")),
        "movesFunds": bool(item.get("movesFunds")),
        "clearanceRule": "Review evidence and paths manually; no auto staging, cleanup, deletion, funding, routing, or broker writes.",
    }


def source_clearance_runway(bundles: list[dict[str, Any]], next_reduction_order: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {
        str(item.get("id")): item
        for item in bundles
        if isinstance(item, dict) and item.get("id")
    }
    ordered: list[dict[str, Any]] = []
    seen: set[str] = set()
    for order in next_reduction_order:
        if not isinstance(order, dict):
            continue
        bundle_id = str(order.get("bundleId") or "")
        if not bundle_id or bundle_id in seen or bundle_id not in by_id:
            continue
        seen.add(bundle_id)
        ordered.append(by_id[bundle_id])
    ordered.extend(item for item in bundles if str(item.get("id")) not in seen)
    return [
        clearance_ticket_for_bundle(item, rank)
        for rank, item in enumerate(ordered, start=1)
    ]


def bundle(
    *,
    bundle_id: str,
    title: str,
    count: int,
    action: str,
    samples: list[str],
    commands: list[str],
    blockers: list[str],
    notes: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": bundle_id,
        "title": title,
        "count": count,
        "action": action,
        "samplePaths": samples,
        "commands": commands,
        "blockers": blockers,
        "notes": notes or [],
        "researchOnly": True,
        "safeToStageAutomatically": False,
        "automaticCleanupAllowed": False,
        "operatorApprovalRequired": True,
        "writesOrders": False,
        "touchesBroker": False,
        "movesFunds": False,
        "readyForExecution": False,
    }


def build_plan(args: argparse.Namespace) -> dict[str, Any]:
    source = read_json(Path(args.source_intake))
    data = read_json(Path(args.data_intake))
    execution = read_json(Path(args.execution_intake))
    worktree = read_json(Path(args.worktree))
    sibling = read_json(Path(getattr(args, "sibling_worktree_intake", STATE / "bill-sibling-worktree-intake.latest.json")))
    session_safety_path = getattr(args, "topstep_session_safety", None)
    session_safety = read_json(Path(session_safety_path)) if session_safety_path else {}
    proof_paused = topstep_proofs_paused(session_safety)

    source_counts = source.get("classificationCounts") if isinstance(source.get("classificationCounts"), dict) else {}
    data_counts = data.get("classificationCounts") if isinstance(data.get("classificationCounts"), dict) else {}
    data_risks = data.get("riskCounts") if isinstance(data.get("riskCounts"), dict) else {}
    execution_counts = execution.get("classificationCounts") if isinstance(execution.get("classificationCounts"), dict) else {}
    validation_evidence = source.get("validationEvidence") if isinstance(source.get("validationEvidence"), dict) else {}
    focused_suite = str(validation_evidence.get("focusedSuite") or "").strip()
    raw_full_suite = [
        str(command)
        for command in validation_evidence.get("fullSuite", [])
        if command
    ] if isinstance(validation_evidence.get("fullSuite"), list) else []
    full_suite, suppressed_validation_commands = filter_validation_commands_for_session_safety(
        raw_full_suite,
        proof_paused=proof_paused,
    )
    clearance_status = clearance_status_summary()
    sibling_summary = sibling_worktree_summary(sibling)
    source_clean_blockers = (
        worktree.get("sourceCleanBlockers")
        if isinstance(worktree.get("sourceCleanBlockers"), list)
        else []
    )
    worktree_clearance_queue = clearance_queue_summary(worktree)

    validated = source.get("validatedResearchScaffold") if isinstance(source.get("validatedResearchScaffold"), list) else []
    quarantine = source.get("quarantineExecutionLiveFiles") if isinstance(source.get("quarantineExecutionLiveFiles"), list) else []
    execution_items = execution.get("items") if isinstance(execution.get("items"), list) else []
    data_items = data.get("items") if isinstance(data.get("items"), list) else []
    review_samples = source.get("requiresReviewSamples") if isinstance(source.get("requiresReviewSamples"), dict) else {}
    raw_dirty_paths = getattr(args, "dirty_paths", None)
    if isinstance(raw_dirty_paths, list):
        dirty_status_map = {str(path): "dirty-tree" for path in raw_dirty_paths if path}
    else:
        dirty_status_map = git_status_entries()
    dirty_paths = list(dirty_status_map)
    status_map = {**dirty_status_map, **status_from_items(validated, quarantine, execution_items, data_items)}

    bundles = [
        bundle(
            bundle_id="validated-research-scaffold",
            title="Validated research scaffold",
            count=len(validated),
            action="Review the focused validation evidence, then decide manually whether any research-only scaffold should be staged as one coherent control-plane patch.",
            samples=sample_paths(validated),
            commands=[
                focused_suite or ".venv/bin/python -m unittest tests.test_bill_source_intake_manifest tests.test_bill_next_research_actions tests.test_sync_bill_obsidian -v",
                *full_suite,
                "npm run --silent bill:source-intake-manifest",
                "npm run --silent bill:source-hygiene-plan",
                "npm run --silent bill:source-packet-review",
                "npm run --silent bill:obsidian-sync",
            ],
            blockers=[
                "operator approval required before staging",
                "green focused tests do not imply execution approval",
                "must remain linked from Obsidian before weaker agents use it",
            ],
            notes=[
                str(note)
                for note in [
                    validation_evidence.get("note"),
                    validation_evidence.get("fullSuiteNote"),
                ]
                if note
            ],
        ),
        bundle(
            bundle_id="execution-live-quarantine",
            title="Execution/live quarantine",
            count=len(quarantine) or int(source_counts.get("quarantine-execution-live", 0) or 0),
            action="Keep all execution-adjacent changes locked until firewall evidence and execution intake stay green across the full control-plane run.",
            samples=sample_paths(quarantine) or sample_paths(execution_items),
            commands=[
                "npm run --silent bill:verify-execution-quarantine",
                "npm run --silent bill:verify-master-bridge-firewall",
                "npm run --silent bill:verify-60m-bridge-firewall",
                "npm run --silent bill:verify-topstep-demo-bridge-firewall",
                "npm run --silent bill:verify-signal-router-firewall",
                "npm run --silent bill:verify-prediction-funding-firewall",
                "npm run --silent bill:execution-intake-manifest",
            ],
            blockers=[
                "execution remains locked",
                "firewall-covered still means quarantined, not approved",
                "daily plan approval and broker reconciliation are blocked",
            ],
            notes=[
                f"allFirewallCommandsPassed={execution.get('allFirewallCommandsPassed', 'missing')}",
                f"uncoveredExecutionPaths={execution.get('uncoveredExecutionPaths', [])}",
            ],
        ),
        bundle(
            bundle_id="sibling-worktree-quarantine",
            title="Sibling worktree quarantine",
            count=int(sibling_summary.get("dirtyFileCount", 0) or 0),
            action="Treat dirty sibling worktrees as selective-intake only; review their execution-live and governance files before considering any manual cherry-pick.",
            samples=[
                str(path)
                for path in sibling_summary.get("topReviewFirst", [])
            ],
            commands=[
                "npm run --silent bill:sibling-worktree-intake",
                "npm run --silent bill:worktree-consolidation || true",
                "npm run --silent bill:source-hygiene-plan",
                "npm run --silent bill:source-packet-review",
                "npm run --silent bill:goal-completion-audit",
            ],
            blockers=[
                "sibling worktrees are not canonical source",
                "selective intake requires manual diff review",
                "execution-live files in sibling worktrees remain quarantined",
                "do not merge, move, delete, stage, or revert from this bundle automatically",
            ],
            notes=[
                f"decision={sibling_summary.get('decision')}",
                f"classificationCounts={sibling_summary.get('classificationCounts')}",
                f"blockers={sibling_summary.get('blockers')}",
            ],
        ),
        bundle(
            bundle_id="data-research-refresh",
            title="Research data refresh",
            count=int(data.get("dirtyDataFileCount", 0) or 0),
            action="Keep refreshed CSVs as research inputs only until provenance, timestamp range, and broker-parity requirements are independently green.",
            samples=sample_paths(data_items),
            commands=[
                "npm run --silent bill:data-intake-manifest",
                "npm run --silent bill:data-freshness-gate || true",
                "npm run --silent bill:futures-data-requirements",
                "npm run --silent bill:futures-broker-parity-plan",
            ],
            blockers=[
                "execution-grade realtime data is not cleared",
                "research CSV freshness does not satisfy broker parity",
                "dataset storage policy still needs human review before cleanup",
            ],
            notes=[f"classificationCounts={data_counts}", f"riskCounts={data_risks}"],
        ),
        bundle(
            bundle_id="dependency-review",
            title="Dependency drift review",
            count=int(source_counts.get("dependency-review", 0) or 0),
            action="Treat package and requirements changes as a toolchain patch; keep only dependencies with a named Bill alpha use and passing tests.",
            samples=source_samples(source, "dependency-review"),
            commands=[
                "npm run --silent bill:alpha-tooling-check",
                "npm run --silent typecheck",
                "npm run --silent bill:source-intake-manifest",
                "npm run --silent bill:source-hygiene-plan",
                "npm run --silent bill:source-packet-review",
            ],
            blockers=[
                "dependency drift can change research results",
                "tooling install success is not strategy evidence",
            ],
        ),
        bundle(
            bundle_id="obsidian-ops-docs",
            title="Obsidian and ops docs",
            count=int(source_counts.get("obsidian-or-ops-review", 0) or 0),
            action="Link documents into the canonical Obsidian map and classify each as active, candidate, research-only, quarantine, or retired.",
            samples=source_samples(source, "obsidian-or-ops-review"),
            commands=[
                "npm run --silent bill:obsidian-sync",
                "npm run --silent bill:source-intake-manifest",
                "npm run --silent bill:source-hygiene-plan",
                "npm run --silent bill:source-packet-review",
            ],
            blockers=[
                "too many unranked READMEs weaken agent handoffs",
                "Obsidian memory is not broker truth",
            ],
        ),
        bundle(
            bundle_id="strategy-research-review",
            title="Strategy research review",
            count=int(source_counts.get("requires-review", 0) or 0),
            action="Split the broad review backlog into futures and prediction-market lanes, then add focused tests before any manual staging decision.",
            samples=source_samples(source, "requires-review"),
            commands=[
                "npm run --silent bill:futures-evidence-triage || true",
                "npm run --silent bill:prediction-evidence-triage",
                "npm run --silent bill:source-packet-review",
                "npm run --silent bill:next-research-actions",
            ],
            blockers=[
                "review backlog is too large for automatic cleanup",
                "no overfit parameter mining without OOS and no-edge memory",
                "no prediction paper promotion without fillability and resolved-outcome checks",
            ],
        ),
    ]

    next_reduction_order = [
        {
            "rank": 1,
            "bundleId": "validated-research-scaffold",
            "reason": "lowest ambiguity and already has focused validation evidence",
            "operatorAction": "review evidence and decide whether to stage as a research-only control patch",
        },
        {
            "rank": 2,
            "bundleId": "execution-live-quarantine",
            "reason": "highest risk; keep visible and locked before touching adjacent source",
            "operatorAction": "verify firewalls, then leave locked unless a specific code review is requested",
        },
        {
            "rank": 3,
            "bundleId": "sibling-worktree-quarantine",
            "reason": "non-canonical dirty worktrees can hide useful research and dangerous execution-live drift",
            "operatorAction": "review sibling intake and selectively copy only approved research patches after canonical hygiene is stable",
        },
        {
            "rank": 4,
            "bundleId": "data-research-refresh",
            "reason": "data can silently contaminate backtests if provenance and freshness are unclear",
            "operatorAction": "confirm data policy and broker-parity proof before retaining as canonical",
        },
        {
            "rank": 5,
            "bundleId": "strategy-research-review",
            "reason": "largest backlog; reduce only by evidence lane, not by file count",
            "operatorAction": "triage futures and prediction-market work separately",
        },
        {
            "rank": 6,
            "bundleId": "dependency-review",
            "reason": "dependency changes should be justified by alpha tooling, not general convenience",
            "operatorAction": "keep or remove packages manually after tests and use-case review",
        },
        {
            "rank": 7,
            "bundleId": "obsidian-ops-docs",
            "reason": "documentation cleanup is useful after the current risk posture is stable",
            "operatorAction": "link and classify docs instead of copying large files",
        },
    ]
    futures_include_terms = (
        "futures",
        "topstep",
        "nq",
        "backtrader",
        "60m",
        "vol_",
        "vol-",
        "cot",
        "cftc",
        "dom_proxy",
        "kalman",
        "whale_flow",
        "rolling_window",
        "databento",
        "broker_parity",
        "data_quality",
        "session",
        "donchian",
        "ichimoku",
        "qrs",
        "noise_area",
        "noise_stepforward",
        "vol_noise",
        "microstructure",
    )
    prediction_include_terms = (
        "prediction",
        "polymarket",
        "kalshi",
        "clob",
        "gengar",
        "pm_",
        "pmbot",
        "macro_rates",
        "event_",
        "label_",
        "resolved",
        "fillability",
        "calibration",
    )
    raw_validated_paths = prioritize_paths(
        [path for path in (path_from_item(item) for item in validated) if path],
        CONTROL_RESEARCH_PRIORITY_PATHS,
    )
    control_priority = set(CONTROL_RESEARCH_PRIORITY_PATHS)
    validated_paths = [
        path
        for path in raw_validated_paths
        if path in control_priority
        or not (
            path_matches_terms(path, futures_include_terms)
            or path_matches_terms(path, prediction_include_terms)
        )
    ]
    execution_paths = [path for path in (path_from_item(item) for item in execution_items) if path]
    data_paths = [path for path in (path_from_item(item) for item in data_items) if path]
    dependency_paths = prioritize_paths(
        dedupe_paths([
            *[
                path
                for path in DEPENDENCY_REVIEW_PRIORITY_PATHS
                if path in status_map or path in dirty_paths or path in raw_validated_paths
            ],
            *source_samples(source, "dependency-review", limit=12),
        ]),
        DEPENDENCY_REVIEW_PRIORITY_PATHS,
    )
    lane_candidate_paths = dedupe_paths([*raw_validated_paths, *dirty_paths])
    already_packeted = set(validated_paths) | set(execution_paths) | set(data_paths)
    lane_exclude_terms = (
        "ops/",
        "/live/",
        "execute",
        "execution",
        "fund",
        "deposit",
        "swap",
        "wire-up",
        "router",
        "route",
        "bridge",
        "pmbot",
        "gengarexecution",
    )
    futures_lane_paths = prioritized_lane_paths(
        lane_candidate_paths,
        priority_paths=FUTURES_LANE_PRIORITY_PATHS,
        include_terms=futures_include_terms,
        exclude_paths=already_packeted,
        exclude_terms=lane_exclude_terms,
        limit=26,
    )
    prediction_validated_paths = prioritized_lane_paths(
        raw_validated_paths,
        priority_paths=PREDICTION_LANE_PRIORITY_PATHS,
        include_terms=prediction_include_terms
        + (
            "alpha_frontier",
            "bill_next_research",
            "no_edge",
        ),
        exclude_paths=set(),
        exclude_terms=lane_exclude_terms,
        limit=16,
    )
    prediction_review_paths = prioritized_lane_paths(
        lane_candidate_paths,
        priority_paths=PREDICTION_LANE_PRIORITY_PATHS,
        include_terms=prediction_include_terms,
        exclude_paths=already_packeted,
        exclude_terms=lane_exclude_terms,
        limit=max(0, 24 - len(prediction_validated_paths)),
    )
    prediction_lane_paths = prioritize_paths(
        dedupe_paths([*prediction_validated_paths, *prediction_review_paths]),
        PREDICTION_LANE_PRIORITY_PATHS,
    )[:24]
    next_review_packets = [
        packet(
            packet_id="packet-01-control-research-scaffold",
            bundle_id="validated-research-scaffold",
            title="Control/research scaffold review packet",
            paths=validated_paths,
            commands=[
                focused_suite or ".venv/bin/python -m unittest tests.test_bill_source_intake_manifest tests.test_bill_next_research_actions tests.test_sync_bill_obsidian -v",
                py_compile_review_command(validated_paths),
                "npm run --silent bill:source-intake-manifest",
                "npm run --silent bill:source-hygiene-plan",
                "npm run --silent bill:source-packet-review",
                "npm run --silent bill:goal-completion-audit",
            ],
            decision="manual-review-only",
            why="Smallest coherent patch surface with focused validation evidence; still requires human staging approval.",
            statuses=status_map,
        ),
        packet(
            packet_id="packet-02-execution-firewall-quarantine",
            bundle_id="execution-live-quarantine",
            title="Execution firewall quarantine packet",
            paths=execution_paths[:12],
            commands=[
                "npm run --silent bill:verify-master-bridge-firewall",
                "npm run --silent bill:verify-60m-bridge-firewall",
                "npm run --silent bill:verify-topstep-demo-bridge-firewall",
                "npm run --silent bill:verify-signal-router-firewall",
                "npm run --silent bill:verify-prediction-funding-firewall",
                "npm run --silent bill:verify-execution-quarantine",
                "npm run --silent bill:execution-intake-manifest",
            ],
            decision="quarantine-locked",
            why="Execution-adjacent files need firewall evidence and route approval; passing firewalls still does not clear execution.",
            statuses=status_map,
            manual_stage_allowed=False,
            manual_stage_block_reason="execution-live files remain quarantined until route approval, broker reconciliation, and daily plan gates clear",
        ),
        packet(
            packet_id="packet-03-data-provenance-refresh",
            bundle_id="data-research-refresh",
            title="Research data provenance packet",
            paths=data_paths[:12],
            commands=[
                "npm run --silent bill:data-intake-manifest",
                "npm run --silent bill:data-freshness-gate || true",
                "npm run --silent bill:futures-data-requirements",
                "npm run --silent bill:futures-broker-parity-plan",
                "npm run --silent bill:goal-completion-audit",
            ],
            decision="research-data-only",
            why="Market-data files can contaminate backtests; review provenance before retaining them as canonical research inputs.",
            statuses=status_map,
            manual_stage_allowed=False,
            manual_stage_block_reason="research data needs provenance and broker-parity review before it can become canonical",
        ),
        packet(
            packet_id="packet-07-dependency-review",
            bundle_id="dependency-review",
            title="Dependency and script wiring review packet",
            paths=dependency_paths,
            commands=[
                "npm run --silent bill:alpha-tooling-check",
                "npm run --silent typecheck",
                "npm run --silent test",
                "npm run --silent bill:source-packet-review",
                "npm run --silent bill:goal-completion-audit",
            ],
            decision="dependency-review-only",
            why="Dependency and package-script drift can change research/runtime behavior; review separately from strategy evidence.",
            statuses=status_map,
        ),
        packet(
            packet_id="packet-04-strategy-backlog-sample",
            bundle_id="strategy-research-review",
            title="Strategy backlog sample packet",
            paths=sample_paths(review_samples.get("requires-review"), limit=12),
            commands=[
                "npm run --silent bill:futures-evidence-triage || true",
                "npm run --silent bill:prediction-evidence-triage",
                "npm run --silent bill:alpha-frontier-queue",
                "npm run --silent bill:source-packet-review",
                "npm run --silent bill:next-research-actions",
            ],
            decision="split-before-review",
            why="Largest backlog; reduce by futures/prediction evidence lanes instead of broad file-count cleanup.",
            statuses=status_map,
        ),
    ]
    if futures_lane_paths:
        next_review_packets.append(
            packet(
                packet_id="packet-05-futures-strategy-lane",
                bundle_id="strategy-research-review",
                title="Futures strategy lane packet",
                paths=futures_lane_paths,
                commands=[
                    "npm run --silent bill:futures-evidence-triage || true",
                    "npm run --silent bill:futures-data-requirements",
                    "npm run --silent bill:futures-broker-parity-plan",
                    "npm run --silent bill:alpha-frontier-queue",
                    "npm run --silent bill:source-packet-review",
                    "npm run --silent bill:next-research-actions",
                ],
                decision="lane-review-only",
                why="Primary futures lane: reduce NQ/Topstep/backtrader/order-flow research separately from prediction markets before any staging or demo expansion decision.",
                statuses=status_map,
            )
        )
    if prediction_lane_paths:
        next_review_packets.append(
            packet(
                packet_id="packet-06-prediction-market-lane",
                bundle_id="strategy-research-review",
                title="Prediction-market strategy lane packet",
                paths=prediction_lane_paths,
                commands=[
                    "npm run --silent bill:prediction-evidence-triage",
                    "npm run --silent bill:verify-prediction-funding-firewall",
                    "npm run --silent bill:alpha-frontier-queue",
                    "npm run --silent bill:source-packet-review",
                    "npm run --silent bill:next-research-actions",
                ],
                decision="lane-review-only",
                why="Primary prediction-market lane: keep CLOB, resolved-label, fillability, and calibration work separate from futures and funding/execution code.",
                statuses=status_map,
            )
        )
    sibling_review_paths = [
        path
        for path in sibling_summary.get("topReviewFirst", [])
        if isinstance(path, str) and path
    ]
    if sibling_review_paths:
        next_review_packets.append(
            packet(
                packet_id="packet-08-sibling-worktree-selective-intake",
                bundle_id="sibling-worktree-quarantine",
                title="Sibling worktree selective-intake packet",
                paths=sibling_review_paths[:12],
                commands=[
                    "npm run --silent bill:sibling-worktree-intake",
                    "npm run --silent bill:worktree-consolidation || true",
                    "npm run --silent bill:source-hygiene-plan",
                    "npm run --silent bill:source-packet-review",
                    "npm run --silent bill:goal-completion-audit",
                ],
                decision="quarantine-selective-review",
                why="Dirty sibling worktrees are useful context but not canonical; review only, then selectively reimplement or copy approved research patches.",
                statuses={path: "sibling-worktree-dirty" for path in sibling_review_paths},
                manual_stage_allowed=False,
                manual_stage_block_reason="sibling worktree paths are non-canonical and require selective intake before any staging",
            )
        )
    bundle_summary = [
        {
            "id": item["id"],
            "count": item["count"],
            "safeToStageAutomatically": item["safeToStageAutomatically"],
            "automaticCleanupAllowed": item["automaticCleanupAllowed"],
            "operatorApprovalRequired": item["operatorApprovalRequired"],
            "writesOrders": item["writesOrders"],
            "touchesBroker": item["touchesBroker"],
            "movesFunds": item["movesFunds"],
        }
        for item in bundles
    ]
    review_packet_summary = review_packet_risk_summary(next_review_packets)
    clearance_runway = source_clearance_runway(bundles, next_reduction_order)
    clearance_batches = source_clearance_batches(next_review_packets)

    return {
        "command": "bill-source-hygiene-plan",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "decision": "source-hygiene-plan-research-only-execution-locked",
        "researchOnly": True,
        "sourceHygieneCleared": False,
        "sourceClean": bool(source.get("sourceClean")) if source else False,
        "automaticCleanupAllowed": False,
        "safeToStageAutomatically": False,
        "operatorApprovalRequired": True,
        "dirtyStatusCount": int(source.get("dirtyStatusCount", 0) or 0),
        "reviewBacklogCount": int(source.get("reviewBacklogCount", 0) or 0),
        "sourceCleanBlockers": source_clean_blockers,
        "worktreeClearanceQueue": worktree_clearance_queue,
        "writesOrders": False,
        "touchesBroker": False,
        "movesFunds": False,
        "readyForExecution": False,
        "readyForDemoExpansion": False,
        "readyForLive": False,
        "inputs": {
            "sourceDecision": source.get("decision", "missing"),
            "dataDecision": data.get("decision", "missing"),
            "executionDecision": execution.get("decision", "missing"),
            "worktreePosture": worktree.get("posture", "missing"),
            "sourceClassificationCounts": source_counts,
            "dataClassificationCounts": data_counts,
            "dataRiskCounts": data_risks,
            "executionClassificationCounts": execution_counts,
            "sourceCleanBlockers": source_clean_blockers,
            "worktreeClearanceQueue": worktree_clearance_queue,
            "siblingWorktreeIntake": sibling_summary,
            "topstepSessionSafety": {
                "present": bool(session_safety),
                "pauseBrokerTouchingProofs": proof_paused,
                "reason": session_safety.get("reason"),
                "suppressedValidationCommands": suppressed_validation_commands,
            },
        },
        "latestVerificationEvidence": {
            "focusedSuite": focused_suite,
            "fullSuite": full_suite,
            "suppressedCommands": suppressed_validation_commands,
            "topstepProofsPaused": proof_paused,
            "clearanceEvidence": clearance_status,
            "operatorRead": "These commands are evidence for manual source review only. They do not clear source hygiene, route approval, or execution-grade data.",
        },
        "bundleSummary": bundle_summary,
        "sourceClearanceRunway": clearance_runway,
        "laneReviewTickets": clearance_runway,
        "sourceClearanceBatches": clearance_batches,
        "reviewPacketRiskSummary": review_packet_summary,
        "bundles": bundles,
        "nextReductionOrder": next_reduction_order,
        "nextReviewPackets": next_review_packets,
        "hardRules": [
            "No automatic staging, deletion, moves, or reverts.",
            "No order routing, broker writes, or funding actions.",
            "Execution-live files remain quarantined even when firewall checks pass.",
            "Sibling worktrees are quarantine/selective-intake only until reviewed against canonical source.",
            "Source hygiene is not cleared until a human reviews the bundles and the goal audit blocker disappears.",
        ],
    }


def render_markdown(payload: dict[str, Any]) -> str:
    generated_at = str(payload.get("generatedAt") or "")
    generated_date = generated_at[:10] if len(generated_at) >= 10 else datetime.now(timezone.utc).date().isoformat()
    lines = [
        f"# Bill Source Hygiene Plan - {generated_date}",
        "",
        "Parent hub: [[BILL-CONTROL-HUB]]",
        "",
        "Read-only cleanup and review plan. This page does not approve staging, deletion, reverts, orders, demo expansion, or live trading.",
        "",
        "## Decision",
        "",
        f"- Decision: `{payload.get('decision')}`",
        f"- Dirty status count: `{payload.get('dirtyStatusCount')}`",
        f"- Review backlog count: `{payload.get('reviewBacklogCount')}`",
        f"- Source hygiene cleared: `{payload.get('sourceHygieneCleared')}`",
        f"- Automatic cleanup allowed: `{payload.get('automaticCleanupAllowed')}`",
        f"- Safe to stage automatically: `{payload.get('safeToStageAutomatically')}`",
        f"- Ready for execution: `{payload.get('readyForExecution')}`",
        f"- Source clean blockers: `{payload.get('sourceCleanBlockers', [])}`",
        "",
        "## Sibling Worktree Intake",
        "",
    ]
    sibling = payload.get("inputs", {}).get("siblingWorktreeIntake") if isinstance(payload.get("inputs"), dict) else {}
    if sibling:
        lines.extend([
            f"- Decision: `{sibling.get('decision')}`",
            f"- Dirty sibling worktrees: `{sibling.get('dirtySiblingWorktreeCount')}`",
            f"- Dirty sibling files: `{sibling.get('dirtyFileCount')}`",
            f"- Execution/live dirty files: `{sibling.get('executionLiveDirtyCount')}`",
            f"- Classification counts: `{sibling.get('classificationCounts')}`",
            f"- Blockers: `{sibling.get('blockers')}`",
            f"- Top review first: `{sibling.get('topReviewFirst')}`",
            "",
        ])
    else:
        lines.extend(["- No sibling worktree intake found.", ""])
    lines.extend([
        "## Worktree Clearance Queue",
        "",
    ])
    if payload.get("worktreeClearanceQueue"):
        for item in payload.get("worktreeClearanceQueue") or []:
            lines.append(
                f"{item.get('priority')}. `{item.get('lane')}` - dirtyFiles `{item.get('dirtyFiles')}`"
            )
            lines.append(f"   Action: {item.get('action')}")
            lines.append(f"   Required evidence: `{item.get('requiredEvidence', [])}`")
            if item.get("sampleFiles"):
                lines.append(f"   Sample files: `{item.get('sampleFiles')}`")
    else:
        lines.append("- No worktree clearance queue found.")
    lines.extend([
        "",
        "## Next Reduction Order",
        "",
    ])
    runway = payload.get("sourceClearanceRunway") if isinstance(payload.get("sourceClearanceRunway"), list) else []
    if runway:
        lines.extend([
            "## Source Clearance Runway",
            "",
            "Canonical lane tickets for reducing the dirty tree. These are review tickets, not auto-cleanup permission.",
            "",
        ])
        for item in runway:
            lines.append(
                f"{item.get('rank')}. `{item.get('bundleId')}` - count `{item.get('count')}`"
            )
            lines.append(f"   Decision: `{item.get('decision')}`")
            lines.append(f"   First evidence command: `{item.get('firstEvidenceCommand')}`")
            lines.append(f"   Safe to stage automatically: `{item.get('safeToStageAutomatically')}`")
            lines.append(f"   Automatic cleanup allowed: `{item.get('automaticCleanupAllowed')}`")
            lines.append(f"   Clearance rule: {item.get('clearanceRule')}")
            if item.get("samplePaths"):
                lines.append(f"   Sample paths: `{item.get('samplePaths')}`")
            if item.get("blockers"):
                lines.append(f"   Blockers: `{item.get('blockers')}`")
        lines.append("")
    latest = payload.get("latestVerificationEvidence") if isinstance(payload.get("latestVerificationEvidence"), dict) else {}
    if latest:
        lines.extend([
            "## Latest Verification Evidence",
            "",
            "These commands are evidence for manual source review only. They do not approve staging, routing, demo, paper, or live execution.",
            "",
        ])
        if latest.get("focusedSuite"):
            lines.append(f"- Focused suite: `{latest.get('focusedSuite')}`")
        if latest.get("fullSuite"):
            lines.append("- Full suites / firewall checks:")
            for command in latest.get("fullSuite") or []:
                lines.append(f"  - `{command}`")
        if latest.get("suppressedCommands"):
            lines.append(f"- Topstep broker-touching proof commands paused: `{latest.get('topstepProofsPaused')}`")
            lines.append(f"- Suppressed validation commands: `{latest.get('suppressedCommands')}`")
        clearance = latest.get("clearanceEvidence") if isinstance(latest.get("clearanceEvidence"), dict) else {}
        if clearance:
            lines.append(f"- Clearance evidence: status `{clearance.get('status')}`, allCommandsPassed `{clearance.get('allCommandsPassed')}`, failed `{clearance.get('failedCommandIds', [])}`")
            lines.append(f"- Clearance covered command ids: `{clearance.get('coveredCommandIds', [])}`")
        lines.append("")
    for item in payload.get("nextReductionOrder") or []:
        lines.append(f"{item.get('rank')}. `{item.get('bundleId')}` - {item.get('reason')}")
        lines.append(f"   Operator action: {item.get('operatorAction')}")
    if payload.get("nextReviewPackets"):
        lines.extend(["", "## Next Review Packets", ""])
        risk = payload.get("reviewPacketRiskSummary") if isinstance(payload.get("reviewPacketRiskSummary"), dict) else {}
        if risk:
            lines.extend([
                f"- Packet count: `{risk.get('packetCount')}`",
                f"- Packet paths: `{risk.get('pathCount')}`",
                f"- Status counts: `{risk.get('statusCounts')}`",
                f"- Manual-stage eligible packets: `{risk.get('manualStageEligiblePacketIds')}`",
                f"- Blocked-stage packets: `{risk.get('blockedStagePacketIds')}`",
                f"- Operator read: {risk.get('operatorRead')}",
                "",
            ])
        for item in payload.get("nextReviewPackets") or []:
            lines.append(f"### `{item.get('id')}`")
            lines.append("")
            lines.append(f"- Bundle: `{item.get('bundleId')}`")
            lines.append(f"- Decision: `{item.get('decision')}`")
            lines.append(f"- Why: {item.get('why')}")
            lines.append(f"- Safe to stage automatically: `{item.get('safeToStageAutomatically')}`")
            lines.append(f"- Manual stage eligible: `{item.get('manualStageEligible')}`")
            lines.append(f"- Manual stage warning: {item.get('manualStageWarning')}")
            lines.append(f"- Manual stage command: `{item.get('manualStageCommand')}`")
            lines.append(f"- Diff summary: `{item.get('diffSummary')}`")
            lines.append("- Paths:")
            for row in item.get("pathFootprint") or []:
                lines.append(
                    f"  - `{row.get('path')}` status `{row.get('status')}` "
                    f"+{row.get('addedLines')}/-{row.get('deletedLines')}"
                )
            if item.get("reviewCommands"):
                lines.append("- Review commands:")
                for command in item.get("reviewCommands") or []:
                    lines.append(f"  - `{command}`")
            lines.append("- Commands:")
            for command in item.get("commands") or []:
                lines.append(f"  - `{command}`")
            lines.append("")
    batches = payload.get("sourceClearanceBatches") if isinstance(payload.get("sourceClearanceBatches"), list) else []
    if batches:
        lines.extend([
            "",
            "## Source Clearance Batches",
            "",
            "Ordered review batches for reducing the dirty tree. These are not automatic staging, cleanup, routing, funding, demo, paper, or live-trading permission.",
            "",
        ])
        for item in batches:
            lines.append(f"### `{item.get('id')}`")
            lines.append("")
            lines.append(f"- Packet: `{item.get('packetId')}`")
            lines.append(f"- Decision: `{item.get('decision')}`")
            lines.append(f"- Path count: `{item.get('pathCount')}`")
            lines.append(f"- Oversized for single review: `{item.get('oversizedForSingleReview')}`")
            lines.append(f"- Sub-batch count: `{item.get('subBatchCount')}`")
            lines.append(f"- Stage policy: `{item.get('stagePolicy')}`")
            lines.append(f"- Manual stage eligible: `{item.get('manualStageEligible')}`")
            lines.append(f"- Safe to stage automatically: `{item.get('safeToStageAutomatically')}`")
            lines.append(f"- Blocked from auto-clearance: `{item.get('blockedFromAutoClearance')}`")
            lines.append(f"- Clearance effect: {item.get('clearanceEffect')}")
            if item.get("verificationCommands"):
                lines.append("- Verification commands:")
                for command in item.get("verificationCommands") or []:
                    lines.append(f"  - `{command}`")
            if item.get("paths"):
                lines.append(f"- Paths: `{item.get('paths')}`")
            if item.get("subBatches"):
                lines.append("- Sub-batches:")
                for sub_batch in item.get("subBatches") or []:
                    lines.append(
                        f"  - `{sub_batch.get('id')}` paths `{sub_batch.get('pathCount')}` "
                        f"status `{sub_batch.get('diffSummary', {}).get('statusCounts')}`"
                    )
                    first_command = (
                        sub_batch.get("verificationCommands", [None])[0]
                        if isinstance(sub_batch.get("verificationCommands"), list)
                        else None
                    )
                    lines.append(f"    First command: `{first_command}`")
            lines.append("")
    lines.extend(["", "## Bundles", ""])
    for item in payload.get("bundles") or []:
        lines.append(f"### {item.get('title')}")
        lines.append("")
        lines.append(f"- Bundle id: `{item.get('id')}`")
        lines.append(f"- Count: `{item.get('count')}`")
        lines.append(f"- Action: {item.get('action')}")
        lines.append(f"- Safe to stage automatically: `{item.get('safeToStageAutomatically')}`")
        lines.append(f"- Automatic cleanup allowed: `{item.get('automaticCleanupAllowed')}`")
        lines.append(f"- Blockers: `{item.get('blockers')}`")
        if item.get("samplePaths"):
            lines.append("- Sample paths:")
            for path in item.get("samplePaths") or []:
                lines.append(f"  - `{path}`")
        lines.append("- Commands:")
        for command in item.get("commands") or []:
            lines.append(f"  - `{command}`")
        lines.append("")
    lines.extend(["## Hard Rules", ""])
    for rule in payload.get("hardRules") or []:
        lines.append(f"- {rule}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the Bill/Hermes source hygiene plan.")
    parser.add_argument("--source-intake", default=str(STATE / "bill-source-intake-manifest.latest.json"))
    parser.add_argument("--data-intake", default=str(STATE / "bill-data-intake-manifest.latest.json"))
    parser.add_argument("--execution-intake", default=str(STATE / "bill-execution-intake-manifest.latest.json"))
    parser.add_argument("--worktree", default=str(STATE / "worktree-consolidation.latest.json"))
    parser.add_argument("--sibling-worktree-intake", default=str(STATE / "bill-sibling-worktree-intake.latest.json"))
    parser.add_argument("--topstep-session-safety", default=str(STATE / "topstep-session-safety.latest.json"))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=None)
    args = parser.parse_args()

    payload = build_plan(args)
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
