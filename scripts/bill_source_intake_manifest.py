#!/usr/bin/env python3
"""Create a source-intake manifest for Bill/Hermes dirty-tree review.

This is intentionally read-only. It does not clean, stage, move, delete, route,
fund, or touch broker/order paths. Its job is to make the current source state
legible enough that weaker agents can continue safely.
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
OUT = STATE / "bill-source-intake-manifest.latest.json"


def default_markdown_path() -> Path:
    plan_date = datetime.now(timezone.utc).date().isoformat()
    return HERMES / f"bill-source-intake-manifest-{plan_date}.md"


VALIDATED_RESEARCH_FILES = [
    "ai-scientist-templates/financial_strategy/experiment.py",
    "ai-scientist-templates/financial_strategy/ideas.json",
    "ai-scientist-templates/financial_strategy/latex/fancyhdr.sty",
    "ai-scientist-templates/financial_strategy/latex/iclr2024_conference.bst",
    "ai-scientist-templates/financial_strategy/latex/iclr2024_conference.sty",
    "ai-scientist-templates/financial_strategy/latex/natbib.sty",
    "ai-scientist-templates/financial_strategy/latex/template.tex",
    "ai-scientist-templates/financial_strategy/plot.py",
    "ai-scientist-templates/financial_strategy/prompt.json",
    "ai-scientist-templates/financial_strategy/seed_ideas.json",
    "ai-scientist-templates/financial_strategy/test_run/final_info.json",
    "ai-scientist-templates/financial_strategy/test_run_15m/final_info.json",
    "ai-scientist-templates/financial_strategy/test_run_30m/final_info.json",
    "ai-scientist-templates/financial_strategy/test_run_60m/final_info.json",
    "ai-scientist-templates/financial_strategy/test_run_known_baselines/final_info.json",
    "tests/test_ai_scientist_financial_template.py",
    "ops/activate-bill-workflows.sh",
    "scripts/bill_corpus_audit.py",
    "tests/test_bill_corpus_audit.py",
    "scripts/external_alpha_data_audit.py",
    "tests/test_external_alpha_data_audit.py",
    "scripts/alpha_frontier_queue.py",
    "tests/test_alpha_frontier_queue.py",
    "ops/mac-mini/bin/bill-chatgpt-frontdoor",
    "tests/test_bill_package_scripts.py",
    "scripts/bill_source_intake_manifest.py",
    "tests/test_bill_source_intake_manifest.py",
    "scripts/bill_source_hygiene_plan.py",
    "tests/test_bill_source_hygiene_plan.py",
    "scripts/bill_source_packet_review.py",
    "tests/test_bill_source_packet_review.py",
    "scripts/bill_sibling_worktree_intake.py",
    "tests/test_bill_sibling_worktree_intake.py",
    "scripts/bill_clearance_handoff.py",
    "tests/test_bill_clearance_handoff.py",
    "scripts/bill_data_intake_manifest.py",
    "tests/test_bill_data_intake_manifest.py",
    "scripts/bill_execution_intake_manifest.py",
    "tests/test_bill_execution_intake_manifest.py",
    "scripts/verify_execution_quarantine.py",
    "tests/test_verify_execution_quarantine.py",
    "scripts/bill_research_closed_loop_contract.py",
    "tests/test_bill_research_closed_loop_contract.py",
    "scripts/futures_broker_parity_plan.py",
    "tests/test_futures_broker_parity_plan.py",
    "scripts/bill_open_session_data_proof.py",
    "tests/test_bill_open_session_data_proof.py",
    "scripts/topstep_daily_learning.py",
    "tests/test_topstep_daily_learning.py",
    "scripts/realtime_data_preflight.py",
    "tests/test_realtime_data_preflight.py",
    "scripts/signal_quality_advisor.py",
    "tests/test_signal_quality_advisor.py",
    "scripts/signal_source_truth_audit.py",
    "tests/test_signal_source_truth_audit.py",
    "scripts/ai_screener.py",
    "tests/test_ai_screener.py",
    "scripts/vol_regime_gate.py",
    "scripts/multitf_confirmation.py",
    "scripts/risk_aware_sizing.py",
    "scripts/failure_rag.py",
    "tests/test_advisory_signal_research_safety.py",
    "tests/test_risk_aware_sizing.py",
    "tests/test_failure_rag.py",
    "scripts/bill_next_research_actions.py",
    "tests/test_bill_next_research_actions.py",
    "scripts/brain_cortex.py",
    "ops/mac-mini/scripts/brain-cycle.sh",
    "tests/test_brain_cortex.py",
    "scripts/research_seed_target_refresh_plan.py",
    "tests/test_research_seed_target_refresh_plan.py",
    "scripts/research_seed_triage.py",
    "tests/test_research_seed_triage.py",
    "scripts/bill_goal_completion_audit.py",
    "tests/test_bill_goal_completion_audit.py",
    "scripts/bill_runtime_architecture_audit.py",
    "tests/test_bill_runtime_architecture_audit.py",
    "scripts/bill_fund_os_completion_audit.py",
    "tests/test_bill_fund_os_completion_audit.py",
    "scripts/bill_clearance_evidence.py",
    "tests/test_bill_clearance_evidence.py",
    "scripts/stale_strategy_claim_guard.py",
    "tests/test_stale_strategy_claim_guard.py",
    "tests/test_strategy_evidence_copy.py",
    "scripts/cron_state_validator.py",
    "tests/test_cron_state_validator.py",
    "scripts/codex_automation_audit.py",
    "tests/test_codex_automation_audit.py",
    "scripts/sync_bill_obsidian.py",
    "tests/test_sync_bill_obsidian.py",
    "scripts/paper_source_cards.py",
    "tests/test_paper_source_cards.py",
    "scripts/current_alpha_watch.py",
    "tests/test_current_alpha_watch.py",
    "scripts/cot_signal.py",
    "tests/test_cot_signal_safety.py",
    "scripts/donchian_breakout.py",
    "scripts/ichimoku_full_system.py",
    "scripts/noise_stepforward_analysis.py",
    "scripts/noise_area_scalp.py",
    "scripts/session_trader.py",
    "scripts/probe-60m-signals.ts",
    "scripts/qrs_session_bias.py",
    "scripts/refresh_futures_research_data.py",
    "scripts/vol_noise_scalp.py",
    "tests/test_futures_strategy_shadow_safety.py",
    "tests/test_noise_area_scalp_safety.py",
    "tests/test_qrs_session_bias_safety.py",
    "tests/test_refresh_futures_research_data.py",
    "tests/test_vol_noise_scalp_safety.py",
    "scripts/dom_proxy_ohlcv.py",
    "scripts/kalman_pairs.py",
    "scripts/rolling_window_optimizer.py",
    "scripts/whale_flow_signal.py",
    "tests/test_shadow_cron_research_safety.py",
    "tests/test_whale_flow_signal.py",
    "scripts/backtrader_research_loop.py",
    "scripts/cftc_tff_positioning_ingest.py",
    "tests/test_cftc_tff_positioning_ingest.py",
    "scripts/cot_regime_filter_research.py",
    "tests/test_cot_regime_filter_research.py",
    "scripts/futures_nq_sizing_overlay.py",
    "tests/test_futures_nq_sizing_overlay.py",
    "scripts/prediction_event_capture_cycle.py",
    "tests/test_prediction_event_capture_cycle.py",
    "scripts/prediction_event_paper_promotion_gate.py",
    "tests/test_prediction_event_paper_promotion_gate.py",
    "scripts/prediction_event_clob_capture_targets.py",
    "tests/test_prediction_event_clob_capture_targets.py",
    "scripts/prediction_event_label_gap_plan.py",
    "tests/test_prediction_event_label_gap_plan.py",
    "scripts/prediction_event_lag_replay.py",
    "tests/test_prediction_event_lag_replay.py",
    "scripts/prediction_event_lag_sensitivity.py",
    "tests/test_prediction_event_lag_sensitivity.py",
    "scripts/prediction_event_lag_watch_review.py",
    "tests/test_prediction_event_lag_watch_review.py",
    "scripts/prediction_event_lag_manual_review.py",
    "tests/test_prediction_event_lag_manual_review.py",
    "scripts/prediction_event_mapping_refinement.py",
    "tests/test_prediction_event_mapping_refinement.py",
    "scripts/prediction_event_lag_requirements.py",
    "tests/test_prediction_event_lag_requirements.py",
    "scripts/prediction_event_market_mapping_plan.py",
    "tests/test_prediction_event_market_mapping_plan.py",
    "scripts/prediction_event_timestamp_dataset.py",
    "tests/test_prediction_event_timestamp_dataset.py",
    "scripts/prediction_event_news_rss.py",
    "tests/test_prediction_event_news_rss.py",
    "scripts/prediction_no_edge_ledger.py",
    "tests/test_prediction_no_edge_ledger.py",
    "scripts/prediction_clob_microstructure_feature_audit.py",
    "tests/test_prediction_clob_microstructure_feature_audit.py",
    "scripts/prediction_clob_spread_compression_replay.py",
    "tests/test_prediction_clob_spread_compression_replay.py",
    "scripts/prediction_clob_latency_staleness_replay.py",
    "tests/test_prediction_clob_latency_staleness_replay.py",
    "scripts/prediction_clob_trade_impact_replay.py",
    "tests/test_prediction_clob_trade_impact_replay.py",
    "scripts/polymarket_clob_recorder.mjs",
    "tests/polymarketClobRecorder.test.ts",
    "scripts/polymarket_clob_persistence_lab.mjs",
    "tests/polymarketClobPersistence.test.ts",
]

DEPENDENCY_REVIEW_FILES = {
    "package.json",
    "package-lock.json",
    "requirements.bill-alpha.txt",
}

VALIDATION_COMMAND = (
    ".venv/bin/python -m unittest tests.test_sync_bill_obsidian "
    "tests.test_bill_corpus_audit "
    "tests.test_external_alpha_data_audit tests.test_alpha_frontier_queue "
    "tests.test_bill_package_scripts "
    "tests.test_bill_source_intake_manifest tests.test_bill_source_packet_review "
    "tests.test_bill_sibling_worktree_intake "
    "tests.test_bill_clearance_handoff "
    "tests.test_bill_data_intake_manifest "
    "tests.test_bill_execution_intake_manifest tests.test_verify_execution_quarantine "
    "tests.test_bill_research_closed_loop_contract "
    "tests.test_futures_broker_parity_plan "
    "tests.test_bill_open_session_data_proof "
    "tests.test_topstep_daily_learning "
    "tests.test_realtime_data_preflight "
    "tests.test_signal_quality_advisor "
    "tests.test_signal_source_truth_audit "
    "tests.test_ai_screener "
    "tests.test_ai_scientist_financial_template "
    "tests.test_advisory_signal_research_safety "
    "tests.test_risk_aware_sizing "
    "tests.test_failure_rag "
    "tests.test_bill_goal_completion_audit "
    "tests.test_bill_runtime_architecture_audit "
    "tests.test_bill_fund_os_completion_audit "
    "tests.test_bill_next_research_actions "
    "tests.test_brain_cortex "
    "tests.test_research_seed_target_refresh_plan "
    "tests.test_research_seed_triage "
    "tests.test_bill_clearance_evidence "
    "tests.test_stale_strategy_claim_guard "
    "tests.test_strategy_evidence_copy "
    "tests.test_cron_state_validator "
    "tests.test_codex_automation_audit "
    "tests.test_paper_source_cards "
    "tests.test_current_alpha_watch "
    "tests.test_cot_signal_safety "
    "tests.test_futures_strategy_shadow_safety "
    "tests.test_noise_area_scalp_safety "
    "tests.test_qrs_session_bias_safety "
    "tests.test_refresh_futures_research_data "
    "tests.test_vol_noise_scalp_safety "
    "tests.test_shadow_cron_research_safety "
    "tests.test_whale_flow_signal "
    "tests.test_cftc_tff_positioning_ingest "
    "tests.test_cot_regime_filter_research "
    "tests.test_futures_nq_sizing_overlay "
    "tests.test_prediction_event_capture_cycle "
    "tests.test_prediction_event_paper_promotion_gate "
    "tests.test_prediction_event_clob_capture_targets "
    "tests.test_prediction_event_label_gap_plan "
    "tests.test_prediction_event_lag_replay "
    "tests.test_prediction_event_lag_sensitivity "
    "tests.test_prediction_event_lag_watch_review "
    "tests.test_prediction_event_lag_manual_review "
    "tests.test_prediction_event_mapping_refinement "
    "tests.test_prediction_event_lag_requirements "
    "tests.test_prediction_event_market_mapping_plan "
    "tests.test_prediction_event_timestamp_dataset "
    "tests.test_prediction_event_news_rss "
    "tests.test_prediction_no_edge_ledger "
    "tests.test_prediction_clob_microstructure_feature_audit "
    "tests.test_prediction_clob_spread_compression_replay "
    "tests.test_prediction_clob_latency_staleness_replay "
    "tests.test_prediction_clob_trade_impact_replay "
    "tests.test_bill_source_hygiene_plan -v "
    "&& npm run --silent test -- tests/polymarketClobRecorder.test.ts "
    "tests/polymarketClobPersistence.test.ts"
)

FULL_VALIDATION_COMMANDS = [
    ".venv/bin/python -m unittest discover -s tests -p 'test_*.py'",
    "npm run --silent typecheck",
    "npm run --silent test",
    "npm run --silent bill:verify-60m-bridge-firewall",
    "npm run --silent bill:verify-signal-router-firewall",
    "npm run --silent bill:verify-master-bridge-firewall",
    "npm run --silent bill:verify-topstep-demo-bridge-firewall",
    "npm run --silent bill:verify-prediction-funding-firewall",
    "npm run --silent bill:verify-execution-quarantine",
    "npm run --silent bill:stale-strategy-claim-guard",
    "npm run --silent bill:clearance-evidence",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def git_status_text() -> str:
    proc = subprocess.run(
        ["git", "status", "--short", "--untracked-files=all"],
        cwd=ROOT,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        return ""
    return proc.stdout


def parse_git_status(text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in text.splitlines():
        if len(line) < 4:
            continue
        status = line[:2]
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        if path:
            rows.append({"status": status.strip() or "modified", "path": path})
    return rows


def classify_path(path: str, execution_live_files: set[str], validated_files: set[str]) -> str:
    if path in DEPENDENCY_REVIEW_FILES:
        return "dependency-review"
    if path in validated_files:
        return "validated-research-scaffold"
    if path in execution_live_files:
        return "quarantine-execution-live"
    if path.startswith("src/live/") or path.startswith("scripts/deposit-") or path in {
        "scripts/master_bridge.py",
        "scripts/60m_exec_bridge.py",
        "scripts/fund-and-trade.ts",
        "scripts/swap-and-fund.ts",
        "scripts/wire-up.ts",
    }:
        return "quarantine-execution-live"
    if path.startswith("data/"):
        return "data-needs-manifest"
    if path.startswith("docs/") or path.startswith("ops/") or path.endswith(".md"):
        return "obsidian-or-ops-review"
    if path.startswith("scripts/") or path.startswith("src/") or path.startswith("tests/"):
        return "requires-review"
    return "requires-review"


def sample_by_class(rows: list[dict[str, str]], limit: int = 12) -> dict[str, list[str]]:
    samples: dict[str, list[str]] = {}
    for row in rows:
        kind = row["classification"]
        samples.setdefault(kind, [])
        if len(samples[kind]) < limit:
            samples[kind].append(row["path"])
    return samples


def build_manifest(
    *,
    worktree: dict[str, Any],
    git_status_rows: list[dict[str, str]],
    generated_at: str | None = None,
) -> dict[str, Any]:
    canonical = worktree.get("canonicalSource") if isinstance(worktree.get("canonicalSource"), dict) else {}
    categories = canonical.get("categories") if isinstance(canonical.get("categories"), dict) else {}
    execution_live_files = {
        str(path)
        for path in canonical.get("executionLiveFiles", [])
        if path
    }
    validated_files = set(VALIDATED_RESEARCH_FILES)

    classified_rows: list[dict[str, str]] = []
    for row in git_status_rows:
        path = str(row.get("path", ""))
        if not path:
            continue
        classified_rows.append({
            "status": str(row.get("status", "")),
            "path": path,
            "classification": classify_path(path, execution_live_files, validated_files),
        })

    class_counts = Counter(row["classification"] for row in classified_rows)
    dirty_files = int(canonical.get("dirtyFiles") or len(classified_rows))
    canonical_execution_dirty = int(categories.get("execution-live") or 0)
    classified_execution_dirty = int(class_counts.get("quarantine-execution-live", 0))
    execution_dirty = max(canonical_execution_dirty, classified_execution_dirty)

    validated_status = []
    status_by_path = {row["path"]: row["status"] for row in classified_rows}
    for path in VALIDATED_RESEARCH_FILES:
        validated_status.append({
            "path": path,
            "status": status_by_path.get(path, "not-dirty"),
            "classification": "validated-research-scaffold",
            "evidence": VALIDATION_COMMAND,
        })

    source_clean = dirty_files == 0 and execution_dirty == 0 and not classified_rows
    return {
        "command": "bill-source-intake-manifest",
        "generatedAt": generated_at or now_iso(),
        "decision": "source-clean" if source_clean else "source-intake-visible-execution-locked",
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "readyForExecution": False,
        "readyForDemoExpansion": False,
        "readyForLive": False,
        "sourceClean": source_clean,
        "sourceIntakeVisible": True,
        "canonicalSource": {
            "path": canonical.get("path", str(ROOT)),
            "branch": canonical.get("branch"),
            "head": canonical.get("head"),
            "dirtyFiles": dirty_files,
            "categories": categories,
            "sourceCleanBlockers": worktree.get("sourceCleanBlockers") or [],
        },
        "classificationCounts": dict(sorted(class_counts.items())),
        "validatedResearchScaffold": validated_status,
        "quarantineExecutionLiveFiles": [
            row for row in classified_rows if row["classification"] == "quarantine-execution-live"
        ],
        "requiresReviewSamples": sample_by_class(classified_rows),
        "reviewBacklogCount": sum(
            count
            for kind, count in class_counts.items()
            if kind not in {"validated-research-scaffold", "quarantine-execution-live"}
        ),
        "executionLiveDirtyCount": execution_dirty,
        "canonicalExecutionLiveDirtyCount": canonical_execution_dirty,
        "classifiedExecutionLiveDirtyCount": classified_execution_dirty,
        "dirtyStatusCount": len(classified_rows),
        "laneSummaries": canonical.get("laneSummaries") if isinstance(canonical.get("laneSummaries"), list) else [],
        "nextCommands": [
            "npm run --silent bill:source-intake-manifest",
            "npm run --silent bill:source-hygiene-plan",
            "npm run --silent bill:source-packet-review",
            "npm run --silent bill:data-intake-manifest",
            "npm run --silent bill:execution-intake-manifest",
            "npm run --silent bill:verify-master-bridge-firewall",
            "npm run --silent bill:verify-60m-bridge-firewall",
            "npm run --silent bill:verify-topstep-demo-bridge-firewall",
            "npm run --silent bill:verify-signal-router-firewall",
            "npm run --silent bill:verify-prediction-funding-firewall",
            "npm run --silent bill:verify-execution-quarantine",
            "npm run --silent bill:clearance-evidence",
            "npm run --silent bill:goal-completion-audit",
            "npm run --silent bill:obsidian-sync",
        ],
        "validationEvidence": {
            "focusedSuite": VALIDATION_COMMAND,
            "fullSuite": FULL_VALIDATION_COMMANDS,
            "note": "Focused suite validates the new research/control scaffolding only; it does not clear execution-live dirty files.",
            "fullSuiteNote": "Full-suite and firewall commands are required evidence before any manual staging decision; green tests still do not approve execution.",
        },
        "validationCommandSets": {
            "focusedResearchControlSuite": [VALIDATION_COMMAND],
            "fullLocalSuiteAndFirewalls": FULL_VALIDATION_COMMANDS,
            "sourceVisibilityRefresh": [
                "npm run --silent bill:source-intake-manifest",
                "npm run --silent bill:source-hygiene-plan",
                "npm run --silent bill:source-packet-review",
                "npm run --silent bill:obsidian-sync",
            ],
            "operatorRead": "Command sets are source-review evidence only; they do not authorize staging, execution, funding, or paper/demo/live trading.",
        },
        "hardRules": [
            "Do not stage, delete, move, or revert files from this manifest without operator approval.",
            "Execution-live dirty files remain quarantined until no-order firewall checks pass.",
            "A visible source intake manifest does not clear the source-hygiene blocker.",
            "Keep BILL_ENABLE_FUTURES_DEMO_EXECUTION=false, RH_TOPSTEP_READ_ONLY=true, and RH_LIVE_EXECUTION_ENABLED=false.",
        ],
    }


def render_markdown(payload: dict[str, Any]) -> str:
    source = payload.get("canonicalSource") if isinstance(payload.get("canonicalSource"), dict) else {}
    lines = [
        "# Bill Source Intake Manifest - 2026-05-30",
        "",
        "Parent hub: [[BILL-CONTROL-HUB]]",
        "",
        "Read-only source hygiene map. This page does not clean, stage, route, fund, or approve orders.",
        "",
        "## Decision",
        "",
        f"- Decision: `{payload.get('decision')}`",
        f"- Source clean: `{payload.get('sourceClean')}`",
        f"- Ready for execution: `{payload.get('readyForExecution')}`",
        f"- Dirty files: `{source.get('dirtyFiles')}`",
        f"- Execution-live dirty count: `{payload.get('executionLiveDirtyCount')}`",
        f"- Canonical execution-live count: `{payload.get('canonicalExecutionLiveDirtyCount')}`",
        f"- Classified execution-live paths: `{payload.get('classifiedExecutionLiveDirtyCount')}`",
        f"- Review backlog count: `{payload.get('reviewBacklogCount')}`",
        "",
        "## Classification Counts",
        "",
    ]
    for key, value in (payload.get("classificationCounts") or {}).items():
        lines.append(f"- `{key}`: `{value}`")

    lines.extend(["", "## Validated Research Scaffold", ""])
    for row in payload.get("validatedResearchScaffold") or []:
        lines.append(f"- `{row.get('path')}` - `{row.get('status')}`")

    lines.extend(["", "## Quarantined Execution-Live Files", ""])
    for row in (payload.get("quarantineExecutionLiveFiles") or [])[:40]:
        lines.append(f"- `{row.get('path')}` - `{row.get('status')}`")
    if len(payload.get("quarantineExecutionLiveFiles") or []) > 40:
        lines.append("- Additional execution-live files are listed in the JSON artifact.")

    lines.extend(["", "## Next Commands", ""])
    for command in payload.get("nextCommands") or []:
        lines.append(f"- `{command}`")

    lines.extend(["", "## Hard Rules", ""])
    for rule in payload.get("hardRules") or []:
        lines.append(f"- {rule}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Bill/Hermes read-only source intake manifest.")
    parser.add_argument("--worktree", default=str(STATE / "worktree-consolidation.latest.json"))
    parser.add_argument("--output", default=str(OUT))
    parser.add_argument("--markdown", default=None)
    args = parser.parse_args()

    payload = build_manifest(
        worktree=read_json(Path(args.worktree)),
        git_status_rows=parse_git_status(git_status_text()),
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
