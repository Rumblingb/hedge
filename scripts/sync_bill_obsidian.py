#!/usr/bin/env python3
"""Sync Bill/Hermes state into the Obsidian vault.

This script writes only human-facing summary blocks. Broker APIs and execution
remain outside Obsidian; Obsidian approves and records, deterministic code routes.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


HOME = Path.home()
HEDGE = HOME / "hedge"
VAULT = HOME / "Documents/memorybrain"
HERMES = VAULT / "Agent-Hermes"
DAILY = HERMES / "daily"
TRADING = VAULT / "Trading/Topstep-100K"
STATE = HEDGE / ".rumbling-hedge/state"
SECURE_ENV = HOME / "Library/Application Support/AgentPay/bill/bill.env"
OPS_ENV = HEDGE / "ops/mac-mini/env/bill.env"
RESOURCE_INVENTORY = VAULT / "Research-Catalog/Bill-Resource-Inventory.md"
RESOURCE_FULL_MANIFEST = VAULT / "Research-Catalog/Bill-Resource-Full-Manifest.jsonl"
MAX_INVENTORY_ROWS = 320
MAX_PRIORITY_REASON_ROWS = 24
TRADING_TIMEZONE = ZoneInfo(os.environ.get("BILL_TRADING_TIMEZONE", "Europe/London"))

RESOURCE_ROOTS = [
    HOME / "Downloads",
    VAULT,
    HEDGE,
    HOME / ".bill-research",
    HOME / ".rumbling-hedge",
    HOME / "research",
    HOME / "research_nq",
    HOME / "quant_research",
    HOME / "Kronos",
    HOME / "gs-quant",
    HOME / ".openclaw/workspace-researcher",
    HOME / ".openclaw.retired-2026-05-12/workspace-researcher",
    HOME / ".openclaw.retired-2026-05-12/workspace-bill/hedge",
    HOME / "worktrees/hedge-goal-live",
    Path("/Volumes/Seagate Expansion Drive/hedge-data"),
]

RESOURCE_FILES = [
    HOME / "research_report_futures_alpha_2025_2026.md",
    HOME / "papers_market_microstructure.json",
    HOME / "research_findings.md",
    HOME / "research_summary.txt",
    HOME / "research_feed.jsonl",
    HOME / "research_pool1.md",
    HOME / "research_pool2.md",
    HOME / "oxford_man_papers.md",
    HOME / "paper_2502.15757.pdf",
    HOME / "quantagent_analysis.md",
    HOME / "ssrn_arxiv_paper_search_results.md",
    HOME / "research/feed/pending Strategies.md",
]

SKIP_DIRS = {
    ".git",
    "node_modules",
    "venv",
    ".venv",
    "__pycache__",
    ".next",
    "dist",
    "build",
    "target",
    ".cache",
    "tmp",
    "memory",
}

SKIP_DIR_PREFIXES = (
    ".venv",
    "venv",
)

SKIP_DIR_SUBSTRINGS = (
    "site-packages",
    ".dist-info",
    ".egg-info",
)

RESOURCE_EXTS = {
    ".md",
    ".pdf",
    ".py",
    ".ts",
    ".tsx",
    ".rs",
    ".json",
    ".jsonl",
    ".csv",
    ".parquet",
    ".ipynb",
    ".yaml",
    ".yml",
    ".toml",
}

RESOURCE_KEYWORDS = (
    "bill",
    "hermes",
    "hedge",
    "trading",
    "trade",
    "market",
    "futures",
    "prediction",
    "polymarket",
    "kalshi",
    "topstep",
    "strategy",
    "alpha",
    "quant",
    "volatility",
    "candle",
    "helsinki",
    "kronos",
    "timesfm",
    "paper",
    "research",
    "backtest",
    "order",
    "fill",
    "mistake",
)


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def read_env_flag(path: Path, key: str) -> str:
    if not path.exists():
        return "missing"
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        name, value = line.split("=", 1)
        if name.strip() == key:
            return value.strip().strip("'\"")
    return "unset"


def cron_job(name: str) -> dict:
    data = read_json(HOME / ".hermes/cron/jobs.json")
    jobs = data.get("jobs", data if isinstance(data, list) else [])
    for job in jobs:
        if job.get("name") == name:
            return job
    return {}


def best_backtrader() -> dict:
    data = read_json(STATE / "backtrader-research.latest.json")
    rows = data.get("results") or []
    if not rows:
        return {}
    return max(rows, key=lambda row: row.get("totalR", 0))


def vol_regime_oos() -> dict:
    return read_json(STATE / "vol-regime-oos-replay.latest.json")


def prediction_review_summary(data: dict, cycle: dict | None = None) -> dict:
    cycle = cycle or {}
    review = data.get("review") if isinstance(data.get("review"), dict) else data
    promotion = data.get("promotion") if isinstance(data.get("promotion"), dict) else {}
    cycle_promotion = cycle.get("promotion") if isinstance(cycle.get("promotion"), dict) else {}
    counts = review.get("counts") or {}
    return {
        "watch": counts.get("watch", data.get("watchCount", data.get("watch_count", "missing"))),
        "paper": counts.get("paper-trade", data.get("paperCount", data.get("paper_count", "missing"))),
        "readyForPaper": review.get("readyForPaper", "missing"),
        "recommendedStage": promotion.get("recommendedStage", cycle_promotion.get("recommendedStage", "missing")),
        "blockers": review.get("blockers") or promotion.get("blockers") or [],
    }


def prediction_calibration_gate() -> dict:
    return read_json(STATE / "prediction-calibration-gate.latest.json")


def prediction_watchlist() -> dict:
    return read_json(STATE / "prediction-research-watchlist.latest.json")


def prediction_evidence_triage() -> dict:
    return read_json(STATE / "prediction-evidence-triage.latest.json")


def prediction_category_drilldown() -> dict:
    return read_json(STATE / "prediction-category-drilldown.latest.json")


def prediction_narrow_scan_runner() -> dict:
    return read_json(STATE / "prediction-narrow-scan-runner.latest.json")


def prediction_resolved_outcome_join() -> dict:
    return read_json(STATE / "prediction-resolved-outcome-join.latest.json")


def prediction_resolved_subject_summary(payload: dict) -> list[tuple[object, object, object, object]]:
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    summary: list[tuple[object, object, object, object]] = []
    for item in items[:6]:
        if not isinstance(item, dict):
            continue
        summary.append(
            (
                item.get("externalId"),
                item.get("status"),
                item.get("resolvedMatchCount"),
                item.get("subjectSpecificMatchCount"),
            )
        )
    return summary


def prediction_resolved_review_summary(payload: dict) -> dict:
    review = payload.get("resolvedOutcomeReview") if isinstance(payload.get("resolvedOutcomeReview"), dict) else {}
    return {
        "status": review.get("status", "missing"),
        "decision": review.get("decision", "missing"),
        "broadPriorRisk": review.get("broadPriorRisk", "missing"),
        "readyForPaper": review.get("readyForPaper", False),
        "itemDecisions": [
            (
                item.get("externalId"),
                item.get("decision"),
                item.get("resolvedMatchCount"),
                item.get("subjectSpecificMatchCount"),
            )
            for item in (review.get("items") or [])[:6]
            if isinstance(item, dict)
        ],
    }


def prediction_no_edge_ledger() -> dict:
    return read_json(HEDGE / ".rumbling-hedge/research/prediction-no-edge-ledger/latest.json")


def prediction_learning() -> dict:
    return read_json(STATE / "prediction-learning.latest.json")


def polymarket_clob_edge_gate() -> dict:
    return read_json(STATE / "polymarket-clob-edge-gate.latest.json")


def prediction_clob_microstructure_audit() -> dict:
    return read_json(STATE / "prediction-clob-microstructure-feature-audit.latest.json")


def prediction_clob_spread_compression_replay() -> dict:
    return read_json(STATE / "prediction-clob-spread-compression-replay.latest.json")


def prediction_clob_latency_staleness_replay() -> dict:
    return read_json(STATE / "prediction-clob-latency-staleness-replay.latest.json")


def prediction_clob_trade_impact_replay() -> dict:
    return read_json(STATE / "prediction-clob-trade-impact-replay.latest.json")


def prediction_clob_microstructure_summary(payload: dict) -> dict:
    return {
        "decision": payload.get("decision", "missing"),
        "readyFeatureCount": payload.get("readyFeatureCount", "missing"),
        "repoFeatureCount": payload.get("repoFeatureCount", "missing"),
        "readyForPaper": payload.get("readyForPaper", "missing"),
        "featureIds": [
            item.get("id")
            for item in (payload.get("featureCandidates") or [])[:5]
            if isinstance(item, dict)
        ],
        "nextAction": payload.get("nextAction", "missing"),
    }


def polymarket_clob_recorder() -> dict:
    return read_json(STATE / "polymarket-clob-recorder.latest.json")


def kalshi_fillability_snapshot() -> dict:
    return read_json(STATE / "kalshi-fillability-snapshot.latest.json")


def prediction_macro_rates_requirements() -> dict:
    return read_json(STATE / "prediction-macro-rates-requirements.latest.json")


def prediction_macro_rates_resolved_labels() -> dict:
    return read_json(STATE / "prediction-macro-rates-resolved-labels.latest.json")


def prediction_macro_rates_cross_source_replay() -> dict:
    return read_json(STATE / "prediction-macro-rates-cross-source-replay.latest.json")


def prediction_macro_rates_summary(
    *,
    fillability: dict,
    requirements: dict,
    labels: dict,
    replay: dict,
) -> dict:
    return {
        "fillabilityDecision": fillability.get("decision", "missing"),
        "marketsInspected": fillability.get("marketsInspected", "missing"),
        "executablePublicQuotes": fillability.get("executablePublicQuotes", "missing"),
        "bucketCounts": fillability.get("bucketCounts", {}),
        "requirementsDecision": requirements.get("decision", "missing"),
        "requirementsPassCount": requirements.get("passCount", "missing"),
        "requirementsBlockedCount": requirements.get("blockedCount", "missing"),
        "officialComparableCount": labels.get("officialComparableCount", "missing"),
        "officialAgreementRate": labels.get("officialAgreementRate", "missing"),
        "replayDecision": replay.get("decision", "missing"),
        "readyForPaper": bool(
            fillability.get("readyForPaper")
            or requirements.get("readyForPaper")
            or labels.get("readyForPaper")
            or replay.get("readyForPaper")
        ),
        "readyForExecution": bool(
            fillability.get("readyForExecution")
            or requirements.get("readyForExecution")
            or labels.get("readyForExecution")
            or replay.get("readyForExecution")
        ),
    }


def prediction_event_label_gap_plan() -> dict:
    return read_json(STATE / "prediction-event-label-gap-plan.latest.json")


def prediction_event_paper_promotion_gate() -> dict:
    return read_json(STATE / "prediction-event-paper-promotion-gate.latest.json")


def prediction_event_capture_cycle() -> dict:
    return read_json(STATE / "prediction-event-capture-cycle.latest.json")


def prediction_event_lag_replay() -> dict:
    return read_json(STATE / "prediction-event-lag-replay.latest.json")


def prediction_event_timestamp_dataset() -> dict:
    return read_json(STATE / "prediction-event-timestamp-dataset.latest.json")


def prediction_event_clob_capture_targets() -> dict:
    return read_json(STATE / "prediction-event-clob-capture-targets.latest.json")


def prediction_event_market_mapping_plan() -> dict:
    return read_json(STATE / "prediction-event-market-mapping-plan.latest.json")


def prediction_event_mapping_refinement() -> dict:
    return read_json(STATE / "prediction-event-mapping-refinement.latest.json")


def prediction_event_mapping_summary(mapping: dict, refinement: dict) -> dict:
    family_fanout = mapping.get("headlineFamilyFanout") if isinstance(mapping.get("headlineFamilyFanout"), list) else []
    ambiguous_fanout = (
        mapping.get("ambiguousHeadlineFamilyFanout")
        if isinstance(mapping.get("ambiguousHeadlineFamilyFanout"), list)
        else [
            item
            for item in family_fanout
            if isinstance(item, dict) and item.get("ambiguous") is True
        ]
    )
    fanout_sample = []
    for item in ambiguous_fanout[:2]:
        if not isinstance(item, dict):
            continue
        fanout_sample.append((
            item.get("headline"),
            item.get("headlineEventFamilies"),
            item.get("candidateExternalIds"),
        ))
    counterparty_fanout = (
        mapping.get("ambiguousHeadlineCounterpartyFanout")
        if isinstance(mapping.get("ambiguousHeadlineCounterpartyFanout"), list)
        else [
            item
            for item in family_fanout
            if isinstance(item, dict) and item.get("counterpartyAmbiguous") is True
        ]
    )
    counterparty_sample = []
    for item in counterparty_fanout[:2]:
        if not isinstance(item, dict):
            continue
        counterparty_sample.append((
            item.get("headline"),
            item.get("headlineActors"),
            item.get("marketActorSets"),
            item.get("candidateExternalIds"),
        ))
    refinement_reviews = (
        refinement.get("headlineReviews")
        if isinstance(refinement.get("headlineReviews"), list)
        else []
    )
    specificity_sample = []
    for review in refinement_reviews[:2]:
        if not isinstance(review, dict):
            continue
        rows = review.get("candidateSpecificityRows") if isinstance(review.get("candidateSpecificityRows"), list) else []
        first_row = next((row for row in rows if isinstance(row, dict)), {})
        specificity_sample.append((
            review.get("headline"),
            review.get("mappingQuality"),
            first_row.get("headlineEventFamilies"),
            first_row.get("specificityIssues"),
        ))
    repair_targets = (
        refinement.get("mappingRepairTargets")
        if isinstance(refinement.get("mappingRepairTargets"), list)
        else []
    )
    repair_sample = []
    for target in repair_targets[:2]:
        if not isinstance(target, dict):
            continue
        repair_sample.append((
            target.get("headline"),
            target.get("candidateCount"),
            target.get("candidateFamilyCounts"),
            target.get("candidateCounterpartyCounts"),
            target.get("candidateDeadlineCounts"),
            target.get("blockedUntil"),
        ))
    capture_leads = (
        refinement.get("publicCaptureReviewLeads")
        if isinstance(refinement.get("publicCaptureReviewLeads"), list)
        else []
    )
    capture_lead_sample = []
    for lead in capture_leads[:3]:
        if not isinstance(lead, dict):
            continue
        capture_lead_sample.append((
            lead.get("question"),
            lead.get("counterparty"),
            lead.get("deadlineText"),
            lead.get("status"),
            lead.get("spread"),
        ))
    return {
        "mappingDecision": mapping.get("decision", "missing"),
        "mappingBlockers": mapping.get("blockers") if isinstance(mapping.get("blockers"), list) else [],
        "ambiguousHeadlineCount": mapping.get("ambiguousHeadlineCount", "missing"),
        "ambiguousCounterpartyHeadlineCount": mapping.get("ambiguousCounterpartyHeadlineCount", "missing"),
        "headlineFamilyFanoutCount": len(family_fanout),
        "ambiguousHeadlineFamilyFanoutCount": len(ambiguous_fanout),
        "ambiguousHeadlineCounterpartyFanoutCount": len(counterparty_fanout),
        "headlineFamilyFanoutSample": fanout_sample,
        "headlineCounterpartyFanoutSample": counterparty_sample,
        "refinementDecision": refinement.get("decision", "missing"),
        "refinementBlockers": refinement.get("blockers") if isinstance(refinement.get("blockers"), list) else [],
        "mappingQualityCounts": (
            refinement.get("mappingQualityCounts")
            if isinstance(refinement.get("mappingQualityCounts"), dict)
            else {}
        ),
        "mappingRepairTargetCount": refinement.get("mappingRepairTargetCount", len(repair_targets)),
        "mappingRepairTargetSample": repair_sample,
        "publicCaptureReviewLeadCount": refinement.get("publicCaptureReviewLeadCount", len(capture_leads)),
        "publicCaptureReviewLeadSample": capture_lead_sample,
        "refinementSpecificitySample": specificity_sample,
        "readyForPaper": bool(mapping.get("readyForPaper") or refinement.get("readyForPaper")),
        "readyForExecution": bool(mapping.get("readyForExecution") or refinement.get("readyForExecution")),
    }


def cron_state_validator() -> dict:
    return read_json(STATE / "cron-state-validator.latest.json")


def signal_quality_advisor() -> dict:
    return read_json(STATE / "signal-quality-advisor.latest.json")


def signal_source_truth_audit() -> dict:
    return read_json(STATE / "signal-source-truth-audit.latest.json")


def signal_quality_shadow_stale_rows(signal_quality: dict) -> list[tuple[object, object, object]]:
    rows = signal_quality.get("shadowSignalRows") if isinstance(signal_quality.get("shadowSignalRows"), list) else []
    stale = []
    for row in rows:
        if not isinstance(row, dict) or row.get("refreshedFromStaleSourceData") is not True:
            continue
        stale.append((row.get("name"), row.get("dataTimestamp"), row.get("dataAgeSeconds")))
    return stale[:6]


def signal_source_truth_issue_summary(source_truth: dict) -> list[tuple[object, object, object, object]]:
    issues = source_truth.get("issues") if isinstance(source_truth.get("issues"), list) else []
    rows = []
    for item in issues[:8]:
        if not isinstance(item, dict):
            continue
        rows.append((
            item.get("file", "missing"),
            item.get("issue", "missing"),
            item.get("canonicalPresent", "missing"),
            item.get("legacyPresent", "missing"),
        ))
    return rows


def whale_flow_signal() -> dict:
    return read_json(STATE / "whale-flow-signal.latest.json")


def futures_evidence_triage() -> dict:
    return read_json(STATE / "futures-evidence-triage.latest.json")


def databento_realtime_smoke() -> dict:
    return read_json(STATE / "databento-realtime-smoke.latest.json")


def databento_orderflow_feature_smoke() -> dict:
    return read_json(STATE / "databento-orderflow-feature-smoke.latest.json")


def futures_cost_slippage_gate() -> dict:
    return read_json(STATE / "futures-cost-slippage-gate.latest.json")


def futures_no_edge_ledger() -> dict:
    return read_json(HEDGE / ".rumbling-hedge/research/futures-no-edge-ledger/latest.json")


def research_closed_loop_contract() -> dict:
    return read_json(STATE / "bill-research-closed-loop-contract.latest.json")


def next_research_actions() -> dict:
    return read_json(STATE / "bill-next-research-actions.latest.json")


def prediction_forward_capture_command(actions: list[dict]) -> str:
    for item in actions:
        if not isinstance(item, dict) or item.get("id") != "prediction-news-first-event-lag-study":
            continue
        plan = item.get("forwardCapturePlan") if isinstance(item.get("forwardCapturePlan"), dict) else {}
        command = str(plan.get("command") or "").strip()
        if command:
            return command
        for candidate in item.get("commands") or []:
            text = str(candidate)
            if "bill:polymarket-clob-recorder" in text and "--max-output-mb" in text and "--min-free-gb" in text:
                return text
    return "missing"


def fund_os_completion_audit() -> dict:
    return read_json(STATE / "bill-fund-os-completion-audit.latest.json")


def fund_os_promotion_contract_summary(payload: dict) -> dict:
    contract = payload.get("fundPromotionContract") if isinstance(payload.get("fundPromotionContract"), dict) else {}
    ladder = contract.get("ladder") if isinstance(contract.get("ladder"), list) else []
    stage_status = [
        (item.get("id", "missing"), item.get("status", "missing"))
        for item in ladder
        if isinstance(item, dict)
    ]
    return {
        "decision": contract.get("decision", "missing"),
        "currentStage": contract.get("currentStage", "missing"),
        "nextStage": contract.get("nextStage", "missing"),
        "readyForDemoExpansion": contract.get("readyForDemoExpansion", "missing"),
        "readyForPaper": contract.get("readyForPaper", "missing"),
        "stageStatus": stage_status,
        "primaryLanes": (contract.get("portfolioIntent") or {}).get("primaryLanes", [])
        if isinstance(contract.get("portfolioIntent"), dict)
        else [],
        "compoundRule": (contract.get("portfolioIntent") or {}).get("compoundRule", "missing")
        if isinstance(contract.get("portfolioIntent"), dict)
        else "missing",
    }


def research_strategy_feed() -> dict:
    return read_json(HEDGE / ".rumbling-hedge/research/researcher/strategy-feed.latest.json")


def research_seed_triage() -> dict:
    return read_json(STATE / "research-seed-triage.latest.json")


def queued_youtube_source_card_summary(seed_triage: dict) -> dict:
    source_cards = (
        seed_triage.get("queuedYouTubeSourceCards")
        if isinstance(seed_triage.get("queuedYouTubeSourceCards"), dict)
        else {}
    )
    if not source_cards.get("present"):
        return {
            "present": False,
            "targets": "missing",
            "promoted": "missing",
            "executionRelevant": False,
            "cards": [],
            "path": "missing",
            "researcherRun": "missing",
        }
    cards = []
    for item in source_cards.get("cards") or []:
        if not isinstance(item, dict):
            continue
        cards.append((
            item.get("title", "missing"),
            item.get("decision", "missing"),
            item.get("lane", "missing"),
        ))
    attempted = source_cards.get("targetsAttempted", "unknown")
    succeeded = source_cards.get("targetsSucceeded", "unknown")
    return {
        "present": True,
        "targets": f"{succeeded}/{attempted}",
        "promoted": source_cards.get("strategyHypothesesPromoted", "unknown"),
        "rawChunks": source_cards.get("rawTranscriptChunksKept", "unknown"),
        "executionRelevant": source_cards.get("executionRelevant", False),
        "cards": cards[:5],
        "path": source_cards.get("path", "missing"),
        "researcherRun": source_cards.get("researcherRun", "missing"),
    }


def alpha_research_tooling_check() -> dict:
    return read_json(STATE / "alpha-research-tooling-check.latest.json")


def alpha_research_direction_audit() -> dict:
    return read_json(STATE / "alpha-research-direction-audit.latest.json")


def hermes_storage_audit() -> dict:
    return read_json(STATE / "hermes-storage-audit.latest.json")


def hermes_storage_summary(payload: dict) -> dict:
    top_candidates = payload.get("topCandidates") if isinstance(payload.get("topCandidates"), list) else []
    cleanup_plan = payload.get("cleanupPlan") if isinstance(payload.get("cleanupPlan"), list) else []
    archive_mount = payload.get("archiveMount") if isinstance(payload.get("archiveMount"), dict) else {}
    archive_verification = payload.get("archiveVerification") if isinstance(payload.get("archiveVerification"), dict) else {}
    state_snapshots_archive = (
        archive_verification.get("stateSnapshots")
        if isinstance(archive_verification.get("stateSnapshots"), dict)
        else {}
    )
    return {
        "totalSize": payload.get("totalSize", "missing"),
        "archiveCandidateSize": payload.get("archiveCandidateSize", "missing"),
        "archiveRoot": payload.get("archiveRoot", "missing"),
        "archiveMountExists": archive_mount.get("exists", "missing"),
        "movesFiles": payload.get("movesFiles", "missing"),
        "deletesFiles": payload.get("deletesFiles", "missing"),
        "topCandidates": [
            (
                item.get("name", "missing"),
                item.get("size", "missing"),
                item.get("action", "missing"),
            )
            for item in top_candidates[:5]
            if isinstance(item, dict)
        ],
        "cleanupPlanIds": [
            item.get("id", "missing")
            for item in cleanup_plan[:4]
            if isinstance(item, dict)
        ],
        "stateSnapshotsArchive": {
            "archiveCoversSource": state_snapshots_archive.get("archiveCoversSource", "missing"),
            "copyLooksComplete": state_snapshots_archive.get("copyLooksComplete", "missing"),
            "checksumManifestExists": state_snapshots_archive.get("checksumManifestExists", "missing"),
            "sourceSize": (state_snapshots_archive.get("source") or {}).get("size", "missing")
            if isinstance(state_snapshots_archive.get("source"), dict)
            else "missing",
            "destinationSize": (state_snapshots_archive.get("destination") or {}).get("size", "missing")
            if isinstance(state_snapshots_archive.get("destination"), dict)
            else "missing",
            "missingFromArchiveCount": state_snapshots_archive.get("missingFromArchiveCount", "missing"),
            "sizeMismatchCount": state_snapshots_archive.get("sizeMismatchCount", "missing"),
        },
        "nextActions": payload.get("nextActions", [])[:4] if isinstance(payload.get("nextActions"), list) else [],
    }


def codex_automation_audit() -> dict:
    return read_json(STATE / "codex-automation-audit.latest.json")


def runtime_architecture_audit() -> dict:
    return read_json(STATE / "bill-runtime-architecture-audit.latest.json")


def runtime_architecture_summary_line(runtime: dict, today: str) -> str:
    n8n = runtime.get("n8n") if isinstance(runtime.get("n8n"), dict) else {}
    kanban = runtime.get("hermesKanban") if isinstance(runtime.get("hermesKanban"), dict) else {}
    kanban_triage = kanban.get("blockedTaskTriage") if isinstance(kanban.get("blockedTaskTriage"), dict) else {}
    cron = runtime.get("hermesCron") if isinstance(runtime.get("hermesCron"), dict) else {}
    cron_review = cron.get("validatorReview") if isinstance(cron.get("validatorReview"), dict) else {}
    ai = runtime.get("aiScientistTemplate") if isinstance(runtime.get("aiScientistTemplate"), dict) else {}
    actions = runtime.get("operatorActions") if isinstance(runtime.get("operatorActions"), list) else []
    return (
        "- Runtime architecture audit: decision `{decision}`, n8n Bill active `{n8n_active}`, "
        "exportMismatches `{mismatch_count}`, Kanban blocked `{kanban_blocked}`, "
        "kanbanTriaged `{kanban_triaged}`, cron execution-like `{cron_execution_like}`, cronValidatorCleared `{cron_cleared}`, "
        "AI-Scientist hardSafety `{ai_safety}`, "
        "warnings `{warnings}`, actions `{actions}`, link `[[bill-runtime-architecture-audit-{today}]]`"
    ).format(
        decision=runtime.get("decision", "missing"),
        n8n_active=n8n.get("activeBillWorkflowCount", "missing"),
        mismatch_count=len(runtime.get("n8nExportMismatches") if isinstance(runtime.get("n8nExportMismatches"), list) else []),
        kanban_blocked=len(kanban.get("blockedRelevantTasks") if isinstance(kanban.get("blockedRelevantTasks"), list) else []),
        kanban_triaged=kanban_triage.get("allBlockedRelevantTasksTriaged", "missing"),
        cron_execution_like=cron.get("activeExecutionLikeCount", "missing"),
        cron_cleared=cron_review.get("cleared", "missing"),
        ai_safety=ai.get("hardSafetyOk", "missing"),
        warnings=runtime.get("warnings", []),
        actions=[(item.get("id"), item.get("priority")) for item in actions[:5] if isinstance(item, dict)],
        today=today,
    )


def data_freshness_gate() -> dict:
    return read_json(STATE / "data-freshness-gate.latest.json")


def futures_research_data_refresh() -> dict:
    return read_json(STATE / "futures-research-data-refresh.latest.json")


def futures_data_quality() -> dict:
    return read_json(STATE / "futures-data-quality.latest.json")


def futures_nq_research_cycle() -> dict:
    return read_json(STATE / "futures-nq-research-cycle.latest.json")


def futures_nq_sizing_overlay() -> dict:
    return read_json(STATE / "futures-nq-sizing-overlay.latest.json")


def premarket_risk_brief() -> dict:
    return read_json(STATE / "premarket-risk-brief.latest.json")


def futures_nq_sizing_overlay_summary(payload: dict) -> dict:
    profile_results = payload.get("profileResults") if isinstance(payload.get("profileResults"), list) else []
    return {
        "decision": payload.get("decision", "missing"),
        "bestProfileId": payload.get("bestProfileId", "missing"),
        "oneVariable": payload.get("oneVariable", "missing"),
        "assumptions": payload.get("assumptions", {}),
        "watchProfiles": [
            (
                item.get("id", "missing"),
                (item.get("summary") or {}).get("netPnl", "missing"),
                (item.get("summary") or {}).get("maxDrawdown", "missing"),
                item.get("bestDayPnl", "missing"),
            )
            for item in profile_results
            if isinstance(item, dict) and item.get("decision") == "research-only-sizing-watch"
        ][:5],
        "blockedProfiles": [
            (item.get("id", "missing"), item.get("blockers", []))
            for item in profile_results
            if isinstance(item, dict) and item.get("decision") != "research-only-sizing-watch"
        ][:5],
        "blockers": payload.get("blockers", []),
        "readyForDemoExpansion": payload.get("readyForDemoExpansion", "missing"),
    }


def futures_cost_gate_summary(payload: dict) -> dict:
    review = payload.get("survivorReview") if isinstance(payload.get("survivorReview"), dict) else {}
    return {
        "backtraderDiscoverySurvivors": (payload.get("backtrader") or {}).get("survivorCount", "missing")
        if isinstance(payload.get("backtrader"), dict)
        else "missing",
        "purgedOosPromotionSurvivors": (payload.get("volRegimeOos") or {}).get("survivorCount", "missing")
        if isinstance(payload.get("volRegimeOos"), dict)
        else "missing",
        "readyForDemoExpansion": payload.get("readyForDemoExpansion", "missing"),
        "failureCounts": payload.get("failureCounts", {}),
        "survivorReviewStatus": review.get("status", "missing"),
        "survivorReviewDecision": review.get("decision", "missing"),
        "parameterMiningRisk": review.get("parameterMiningRisk", "missing"),
        "requiredNextEvidence": review.get("requiredNextEvidence", [])[:5],
    }


def futures_nq_research_cycle_summary(payload: dict) -> dict:
    historical = payload.get("historical") if isinstance(payload.get("historical"), dict) else {}
    current = payload.get("current") if isinstance(payload.get("current"), dict) else {}
    return {
        "decision": payload.get("decision", "missing"),
        "mode": payload.get("mode", "missing"),
        "bestCandidate": historical.get("bestCandidate", "missing"),
        "tradeCount": historical.get("tradeCount", "missing"),
        "positiveFoldShare": historical.get("positiveFoldShare", "missing"),
        "survivingCaseCount": historical.get("survivingCaseCount", "missing"),
        "worstFoldNetR": historical.get("worstFoldNetR", "missing"),
        "currentLocalCsvParity": (
            historical.get("currentLocalCsvParityClearedCount", "missing"),
            historical.get("currentLocalCsvParityCheckedCount", "missing"),
        ),
        "historicalCurrentParitySummary": historical.get("currentParitySummary", {}),
        "coverageBlockers": historical.get("coverageBlockers", []),
        "currentParityDecision": current.get("currentParityDecision", "missing"),
        "brokerParityChecked": current.get("brokerParityChecked", "missing"),
        "readyForDemoExpansion": payload.get("readyForDemoExpansion", "missing"),
        "blockers": payload.get("blockers", []),
        "researchOnly": payload.get("researchOnly", "missing"),
    }


def open_session_data_proof() -> dict:
    return read_json(STATE / "bill-open-session-data-proof.latest.json")


def worktree_consolidation() -> dict:
    return read_json(STATE / "worktree-consolidation.latest.json")


def source_intake_manifest() -> dict:
    return read_json(STATE / "bill-source-intake-manifest.latest.json")


def source_hygiene_plan() -> dict:
    return read_json(STATE / "bill-source-hygiene-plan.latest.json")


def source_packet_review() -> dict:
    return read_json(STATE / "bill-source-packet-review.latest.json")


def data_intake_manifest() -> dict:
    return read_json(STATE / "bill-data-intake-manifest.latest.json")


def execution_intake_manifest() -> dict:
    return read_json(STATE / "bill-execution-intake-manifest.latest.json")


def clearance_evidence() -> dict:
    return read_json(STATE / "bill-clearance-evidence.latest.json")


def goal_completion_audit() -> dict:
    return read_json(STATE / "bill-goal-completion-audit.latest.json")


def execution_firewall_evidence_summary(payload: dict) -> dict:
    results = payload.get("results") if isinstance(payload.get("results"), list) else []
    firewall_rows = [
        row for row in results
        if isinstance(row, dict)
        and row.get("lane") == "execution-live"
        and "firewall" in str(row.get("id", ""))
    ]
    passed = [row.get("id") for row in firewall_rows if row.get("passed") is True]
    failed = [row.get("id") for row in firewall_rows if row.get("passed") is not True]
    return {
        "status": payload.get("status", "missing"),
        "passed": len(passed),
        "total": len(firewall_rows),
        "failed": failed,
    }


def trading_day(now_utc: datetime) -> str:
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    return now_utc.astimezone(TRADING_TIMEZONE).date().isoformat()


DAILY_REQUIRED_SECTIONS = [
    (
        "Gate State",
        "Synced machine state above is the current gate source. If any blocker is present, research/backtest only.",
    ),
    (
        "Planned Orders For Today",
        "None approved unless this note is updated manually after broker reconciliation.\n\n"
        "Machine-readable control lines:\n\n"
        "BILL_ROUTE_APPROVAL: BLOCKED\n\n"
        "BROKER_RECONCILIATION: UNKNOWN",
    ),
    (
        "Actual Orders/Fills",
        "No new orders/fills recorded in this daily note yet. Reconcile against broker artifacts and the Topstep operating log.",
    ),
    (
        "Broker Reconciliation",
        "BROKER_RECONCILIATION: UNKNOWN\n\n"
        "No new orders approved until broker position, orders, fills, P&L, and account limits are green.",
    ),
    (
        "Research Queue",
        "Use the synced next research actions above. Every item is research-only unless its named promotion gate passes.",
    ),
    (
        "Post-Market Mistakes",
        "Add mistakes after the session. If none, write `None observed` after broker and log reconciliation.",
    ),
    (
        "Tomorrow Changes",
        "Add one concrete next-day change after post-market review.",
    ),
]


def rewrite_current_daily_references(body: str, today: str) -> str:
    return re.sub(
        r"\[\[((?:\.\./Agent-Hermes/)?daily/)\d{4}-\d{2}-\d{2}-bill-trading-plan\]\]",
        rf"[[\g<1>{today}-bill-trading-plan]]",
        body,
    )


def rewrite_hub_daily_references(body: str, today: str) -> str:
    daily_link = f"[[daily/{today}-bill-trading-plan]]"
    body = re.sub(
        r"1\. \[\[daily/\d{4}-\d{2}-\d{2}-bill-trading-plan\]\]",
        f"1. {daily_link}",
        body,
    )
    body = re.sub(
        r"Current daily note: \[\[daily/\d{4}-\d{2}-\d{2}-bill-trading-plan\]\]",
        f"Current daily note: {daily_link}",
        body,
    )
    return rewrite_current_daily_references(body, today)


def rewrite_hub_read_first(body: str, today: str) -> str:
    section = f"""## Read First

### Operator Must Read These 4

1. [[daily/{today}-bill-trading-plan]]
2. [[BILL-OBSIDIAN-MEMORY-PROTOCOL]]
3. [[BILL-OBSIDIAN-CANONICAL-MAP]]
4. [[hermes-kalshi-compounding-input-2026-06-01]]

### Active Handoff

1. [[bill-next-research-actions-{today}]]
2. [[bill-source-hygiene-plan-{today}]]
3. [[bill-source-packet-review-{today}]]
4. [[bill-open-session-data-proof-{today}]]
5. [[bill-source-intake-manifest-{today}]]
6. [[bill-data-intake-manifest-{today}]]
7. [[bill-execution-intake-manifest-{today}]]
8. [[bill-goal-completion-audit-{today}]]
9. [[bill-hermes-clearance-progress-{today}]]
10. [[bill-hermes-clearance-runbook-{today}]]
11. [[bill-clearance-handoff-{today}]]
12. [[bill-shadow-cron-and-fabervaale-audit-{today}]]
13. [[bill-dependency-alpha-tooling-review-{today}]]
14. [[bill-runtime-architecture-audit-{today}]]
15. [[BILL-HERMES-SYSTEM-ARCHITECTURE-{today}]]
16. [[../Trading/Topstep-100K/2026-05-operating-log]]
17. [[../Trading/Topstep-100K/mistakes]]
18. [[topstep-daily-learning-{today}]]

### Deep Context

1. [[../Research-Catalog/Bill-Resource-Priority-Index]]
2. [[../Research-Catalog/Unused-Research-And-Strategies-Inbox]]
3. [[current-alpha-watch-{today}]]
4. [[research-seed-triage-{today}]]
5. [[../Research-Catalog/Paper-Source-Cards-{today}]]
6. [[BILL-EDGE-DISCOVERY-AUDIT-2026-05-29]]
7. [[alpha-research-sprint-2026-05-29]]
8. [[shadow-cron-trust-gate-2026-05-29]]
9. [[external-alpha-resource-map-2026-05-29]]
10. [[prediction-market-clob-recorder-2026-05-29]]
11. [[yt-strategy-hypothesis-inbox-2026-05-29]]
12. [[../Research-Catalog/Index]]
"""
    pattern = r"## Read First\n.*?(?=\n## Source Of Truth\n)"
    if re.search(pattern, body, flags=re.DOTALL):
        return re.sub(pattern, section.rstrip(), body, flags=re.DOTALL)
    return body.rstrip() + "\n\n" + section


def ensure_daily_plan_contract(path: Path) -> None:
    body = path.read_text() if path.exists() else ""
    additions: list[str] = []
    for heading, default_body in DAILY_REQUIRED_SECTIONS:
        if not re.search(rf"^## {re.escape(heading)}\s*$", body, flags=re.MULTILINE):
            additions.append(f"## {heading}\n\n{default_body}")
    if additions:
        path.write_text(body.rstrip() + "\n\n" + "\n\n".join(additions) + "\n")


def latest_operating_log_events(path: Path, limit: int = 6) -> list[str]:
    try:
        lines = path.read_text().splitlines()
    except Exception:
        return []
    events = [
        line.removeprefix("### ").strip()
        for line in lines
        if line.startswith("### ")
    ]
    return events[-limit:]


def md_cell(value) -> str:
    text = str(value if value is not None else "missing")
    return text.replace("|", "\\|").replace("\n", " ")


def current_topstep_operating_log(now: datetime) -> Path:
    local_day = now.astimezone(TRADING_TIMEZONE)
    return TRADING / f"{local_day:%Y-%m}-operating-log.md"


def order_reconciliation_markdown(monitor: dict, submission: dict, log_path: Path) -> str:
    broker = monitor.get("broker_reconciliation") if isinstance(monitor.get("broker_reconciliation"), dict) else {}
    risk = monitor.get("risk") if isinstance(monitor.get("risk"), dict) else {}
    detail = submission.get("detail") if isinstance(submission.get("detail"), dict) else {}
    rows = [
        ("Monitor status", monitor.get("status", "missing")),
        ("Broker flat", broker.get("broker_flat", "missing")),
        ("Open positions", broker.get("open_positions", "missing")),
        ("Fills today", broker.get("fills_today", "missing")),
        ("Matched trades", broker.get("matched_trades", "missing")),
        ("Local position superseded", broker.get("local_position_superseded", "missing")),
        ("Daily P/L", f"profit={risk.get('daily_profit', 'missing')} loss={risk.get('daily_loss', 'missing')}"),
        ("Latest submission", f"submitted={submission.get('submitted', 'missing')} order={detail.get('entry_order_id', 'missing')} result={detail.get('message', 'missing')}"),
        ("Latest signal", submission.get("last_signal", submission.get("signal", "missing"))),
        ("Submission fill price", detail.get("fill_price", "missing")),
    ]
    table = ["| Check | Value |", "|---|---|"]
    table.extend(f"| {md_cell(name)} | {md_cell(value)} |" for name, value in rows)
    events = latest_operating_log_events(log_path)
    if events:
        table.append("")
        table.append("Latest operating-log events:")
        table.extend(f"- {event}" for event in events)
    else:
        table.append("")
        table.append(f"Latest operating-log events: missing or unreadable at `{log_path}`")
    return "\n".join(table)


def latest_signal_order_markdown(master: dict, submission: dict, *, routing_locked: bool) -> str:
    """Render route artifacts as context, not as approval."""
    context_mode = (
        "HISTORICAL_READ_ONLY - routing locked; this is not route approval."
        if routing_locked
        else "ROUTE_ARMED_REQUIRES_DAILY_PLAN_AND_BROKER_GREEN"
    )
    if routing_locked:
        action = "Do not route, size, copy, or repeat this signal from Obsidian."
    else:
        action = "Verify the daily plan and broker reconciliation before any deterministic route."
    return "\n".join([
        f"- Order-context mode: `{context_mode}`",
        f"- Operator/agent action: `{action}`",
        f"- Master signal artifact: `{master.get('signal', 'missing')}` / `{master.get('side', 'missing')}` / status `{master.get('status', 'missing')}`",
        f"- Entry/SL/TP artifact: `{master.get('entry', 'missing')}` / `{master.get('stop', 'missing')}` / `{master.get('target', 'missing')}`",
        f"- Latest Topstep submission artifact: submitted=`{submission.get('submitted', 'missing')}`, order=`{(submission.get('detail') or {}).get('entry_order_id', 'missing')}`",
    ])


def watchlist_summary(data: dict) -> dict:
    items = data.get("items") if isinstance(data.get("items"), list) else []
    spread_blocked = sum(
        1
        for item in items
        if "latest-clob-spread-too-wide" in (item.get("blockers") or [])
    )
    return {
        "watchCount": data.get("watchCount", len(items) if items else "missing"),
        "readyForPaper": data.get("readyForPaper", "missing"),
        "clobTokenCount": len(data.get("polymarketClobTokenIds") or []),
        "spreadBlocked": spread_blocked,
    }


def severity_counts(issues: list[dict]) -> dict:
    counts: dict[str, int] = {}
    for issue in issues:
        severity = str(issue.get("severity", "unknown"))
        counts[severity] = counts.get(severity, 0) + 1
    return counts


def shadow_cron_state_summary(cron_validator: dict) -> list[tuple[str, str, str, str, object, object]]:
    shadow_states = cron_validator.get("shadow_states")
    if not isinstance(shadow_states, dict):
        return []
    rows: list[tuple[str, str, str, str, object, object]] = []
    for name, item in sorted(shadow_states.items()):
        if not isinstance(item, dict):
            continue
        rows.append((
            str(name),
            str(item.get("method", "missing")),
            str(item.get("evidenceLevel", "missing")),
            str(item.get("executionRole", "missing")),
            item.get("tradableSignal", "missing"),
            item.get("promotedForExecution", "missing"),
        ))
    return rows


def active_shadow_cron_script_guardrail_summary(cron_validator: dict) -> list[tuple[object, object, object, object]]:
    cron_trust = cron_validator.get("cron_trust") if isinstance(cron_validator.get("cron_trust"), dict) else {}
    rows_raw = cron_trust.get("activeShadowCronScriptGuardrails")
    if not isinstance(rows_raw, list):
        return []
    rows: list[tuple[object, object, object, object]] = []
    for item in rows_raw[:8]:
        if not isinstance(item, dict):
            continue
        rows.append((
            item.get("name", "missing"),
            item.get("script", "missing"),
            item.get("guardrailPresent", "missing"),
            item.get("missingTokens", []),
        ))
    return rows


def active_dirty_execution_cron_summary(cron_validator: dict) -> list[tuple[object, object, object, object]]:
    cron_trust = cron_validator.get("cron_trust") if isinstance(cron_validator.get("cron_trust"), dict) else {}
    refs = cron_trust.get("activeDirtyExecutionLiveScriptReferences")
    if not isinstance(refs, list):
        return []
    rows: list[tuple[object, object, object, object]] = []
    for item in refs[:8]:
        if not isinstance(item, dict):
            continue
        source = item.get("source") if isinstance(item.get("source"), dict) else {}
        rows.append((
            item.get("name", "missing"),
            item.get("script", "missing"),
            source.get("relativePath", "missing"),
            source.get("firewallPassed", "missing"),
        ))
    return rows


def active_dirty_execution_cron_remediation(cron_validator: dict) -> list[tuple[object, object, object, object]]:
    cron_trust = cron_validator.get("cron_trust") if isinstance(cron_validator.get("cron_trust"), dict) else {}
    refs = cron_trust.get("activeDirtyExecutionLiveScriptReferences")
    if not isinstance(refs, list):
        return []
    rows: list[tuple[object, object, object, object]] = []
    for item in refs[:8]:
        if not isinstance(item, dict):
            continue
        remediation = item.get("operatorRemediation") if isinstance(item.get("operatorRemediation"), dict) else {}
        rows.append((
            item.get("name", "missing"),
            remediation.get("requiredAction", "operator review required"),
            remediation.get("approvalRequired", "missing"),
            (remediation.get("validationCommands") or [])[:3],
        ))
    return rows


def active_topstep_broker_session_cron_summary(cron_validator: dict) -> list[tuple[object, object, object]]:
    cron_trust = cron_validator.get("cron_trust") if isinstance(cron_validator.get("cron_trust"), dict) else {}
    refs = cron_trust.get("activeTopstepBrokerSessionCronRefs")
    if not isinstance(refs, list):
        return []
    rows: list[tuple[object, object, object]] = []
    for item in refs[:8]:
        if not isinstance(item, dict):
            continue
        rows.append((
            item.get("name", "missing"),
            item.get("script", "missing"),
            item.get("reason", "missing"),
        ))
    return rows


def active_topstep_broker_session_cron_remediation(cron_validator: dict) -> list[tuple[object, object, object]]:
    cron_trust = cron_validator.get("cron_trust") if isinstance(cron_validator.get("cron_trust"), dict) else {}
    refs = cron_trust.get("activeTopstepBrokerSessionCronRefs")
    if not isinstance(refs, list):
        return []
    rows: list[tuple[object, object, object]] = []
    for item in refs[:8]:
        if not isinstance(item, dict):
            continue
        remediation = item.get("operatorRemediation") if isinstance(item.get("operatorRemediation"), dict) else {}
        rows.append((
            item.get("name", "missing"),
            remediation.get("requiredAction", "pause broker-touching cron while session safety is active"),
            (remediation.get("validationCommands") or [])[:3],
        ))
    return rows


def futures_open_session_proof_summary(data_proof: dict) -> dict:
    state = data_proof.get("stateSummary") if isinstance(data_proof.get("stateSummary"), dict) else {}
    window = (
        state.get("nextOpenSessionProofWindow")
        if isinstance(state.get("nextOpenSessionProofWindow"), dict)
        else {}
    )
    planned_steps = data_proof.get("plannedSteps") if isinstance(data_proof.get("plannedSteps"), list) else []
    data_only_commands = [
        step.get("command")
        for step in planned_steps
        if isinstance(step, dict)
        and step.get("id") in {
            "topstep-realtime-proof",
            "topstep-realtime-bridge-write",
            "topstep-readonly-bar-archive",
            "refresh-data-freshness",
        }
        and step.get("writesOrders") is False
        and (
            step.get("touchesBroker") is False
            or step.get("brokerTouchMode") == "read-only-market-data"
        )
        and step.get("movesFunds") is False
    ]
    return {
        "nextOpenUtc": window.get("nextOpenUtc", "missing"),
        "recommendedProofStartUtc": window.get("recommendedProofStartUtc", "missing"),
        "recommendedProofEndUtc": window.get("recommendedProofEndUtc", "missing"),
        "reason": window.get("reason", "missing"),
        "commandsAreDataOnly": window.get("commandsAreDataOnly", "missing"),
        "dataOnlyCommands": data_only_commands,
        "executionGradeDataProofPassed": data_proof.get("executionGradeDataProofPassed", "missing"),
        "readyForExecutionData": state.get("readyForExecutionData", "missing"),
    }


def goal_completion_summary(goal_audit: dict) -> dict:
    blocked_ids = goal_audit.get("blockedIds") if isinstance(goal_audit.get("blockedIds"), list) else []
    prompt_uncovered_ids = (
        goal_audit.get("promptUncoveredIds")
        if isinstance(goal_audit.get("promptUncoveredIds"), list)
        else []
    )
    prompt_checklist = (
        goal_audit.get("promptToArtifactChecklist")
        if isinstance(goal_audit.get("promptToArtifactChecklist"), list)
        else []
    )
    checklist = goal_audit.get("checklist") if isinstance(goal_audit.get("checklist"), list) else []
    blockers_by_id = {
        str(item.get("id")): item.get("blocker")
        for item in checklist
        if isinstance(item, dict) and item.get("id") and item.get("status") == "blocked"
    }
    prompt_status_by_id = {
        str(item.get("id")): item.get("status")
        for item in prompt_checklist
        if isinstance(item, dict) and item.get("id")
    }
    return {
        "decision": goal_audit.get("decision", "missing"),
        "goalComplete": goal_audit.get("goalComplete", "missing"),
        "passCount": goal_audit.get("passCount", "missing"),
        "checkCount": goal_audit.get("checkCount", "missing"),
        "blockedCount": goal_audit.get("blockedCount", len(blocked_ids)),
        "blockedIds": blocked_ids,
        "promptUncoveredCount": goal_audit.get("promptUncoveredCount", len(prompt_uncovered_ids)),
        "promptUncoveredIds": prompt_uncovered_ids,
        "promptUncovered": [
            (prompt_id, prompt_status_by_id.get(str(prompt_id), "missing"))
            for prompt_id in prompt_uncovered_ids[:6]
        ],
        "topBlockers": [
            (blocked_id, blockers_by_id.get(str(blocked_id), "missing"))
            for blocked_id in blocked_ids[:6]
        ],
    }


def research_action_context(item: dict) -> object:
    selected = item.get("selectedCategory")
    if selected:
        return selected
    mapping = item.get("mappingExclusionSummary")
    if isinstance(mapping, dict) and mapping.get("excludedMappingCandidateCount") is not None:
        return (
            f"mappingExcluded={mapping.get('excludedMappingCandidateCount')} "
            f"tokenSpecific={mapping.get('tokenSpecificCandidateCount')}"
        )
    hint = str(item.get("commandHint") or "").strip()
    if hint and hint != "missing":
        if "bill:polymarket-clob-recorder" in hint:
            return hint
        return hint[:120]
    return "missing"


def research_action_display_command(item: dict) -> object:
    forward = item.get("forwardCapturePlan")
    if isinstance(forward, dict):
        for key in ("preferredCommand", "reviewLeadCommand", "command"):
            command = str(forward.get(key) or "").strip()
            if command:
                return command
    commands = item.get("commands") if isinstance(item.get("commands"), list) else []
    return commands[0] if commands else "missing"


def lead_research_action(actions: list, lane: str) -> tuple[object, object, object, object]:
    for item in actions:
        if not isinstance(item, dict) or item.get("lane") != lane:
            continue
        return (
            item.get("id", "missing"),
            item.get("oneVariable", "missing"),
            research_action_context(item),
            research_action_display_command(item),
        )
    return ("missing", "missing", "missing", "missing")


def lead_one_variable_retest(actions: list, lane: str) -> tuple[object, object, object, object]:
    for item in actions:
        if not isinstance(item, dict) or item.get("lane") != lane:
            continue
        if item.get("actionKind") == "no-edge-maintenance":
            continue
        if not item.get("selectedCategory") and not item.get("replacesTestId"):
            continue
        return (
            item.get("id", "missing"),
            item.get("oneVariable", "missing"),
            research_action_context(item),
            research_action_display_command(item),
        )
    for item in actions:
        if not isinstance(item, dict) or item.get("lane") != lane:
            continue
        if item.get("actionKind") == "no-edge-maintenance":
            continue
        if item.get("id") == "kalshi-fillability-guided-rates-scan":
            continue
        if not item.get("oneVariable"):
            continue
        return (
            item.get("id", "missing"),
            item.get("oneVariable", "missing"),
            research_action_context(item),
            research_action_display_command(item),
        )
    return ("missing", "missing", "missing", "missing")


def source_hygiene_lane_packet_summary(source_hygiene: dict) -> dict[str, dict[str, object]]:
    packets = source_hygiene.get("nextReviewPackets")
    if not isinstance(packets, list):
        return {}
    wanted = {
        "packet-05-futures-strategy-lane": "futures",
        "packet-06-prediction-market-lane": "prediction-markets",
    }
    summary: dict[str, dict[str, object]] = {}
    for packet in packets:
        if not isinstance(packet, dict):
            continue
        lane = wanted.get(str(packet.get("id")))
        if not lane:
            continue
        paths = packet.get("paths") if isinstance(packet.get("paths"), list) else []
        commands = packet.get("commands") if isinstance(packet.get("commands"), list) else []
        summary[lane] = {
            "id": packet.get("id", "missing"),
            "decision": packet.get("decision", "missing"),
            "pathCount": packet.get("pathCount", len(paths)),
            "safeToStageAutomatically": packet.get("safeToStageAutomatically", "missing"),
            "writesOrders": packet.get("writesOrders", "missing"),
            "touchesBroker": packet.get("touchesBroker", "missing"),
            "movesFunds": packet.get("movesFunds", "missing"),
            "firstPaths": paths[:8],
            "firstCommand": commands[0] if commands else "missing",
        }
    return summary


def source_hygiene_lane_packet_markdown(summary: dict[str, dict[str, object]]) -> str:
    if not summary:
        return "- Source hygiene lane packets: missing. Run `npm run --silent bill:source-hygiene-plan`."
    lines = [
        "- Source hygiene lane packets: research-only handoff; review these paths, do not stage/route/fund from this note.",
    ]
    for lane in ("futures", "prediction-markets"):
        item = summary.get(lane)
        if not item:
            lines.append(f"  - `{lane}`: missing packet")
            continue
        lines.append(
            "  - `{lane}` `{packet_id}`: decision `{decision}`, paths `{path_count}`, "
            "safeAutoStage `{safe}`, writesOrders `{writes}`, touchesBroker `{broker}`, movesFunds `{funds}`".format(
                lane=lane,
                packet_id=item.get("id", "missing"),
                decision=item.get("decision", "missing"),
                path_count=item.get("pathCount", "missing"),
                safe=item.get("safeToStageAutomatically", "missing"),
                writes=item.get("writesOrders", "missing"),
                broker=item.get("touchesBroker", "missing"),
                funds=item.get("movesFunds", "missing"),
            )
        )
        lines.append(f"    - First command: `{item.get('firstCommand', 'missing')}`")
        for path in item.get("firstPaths", []):
            lines.append(f"    - `{path}`")
    return "\n".join(lines)


def source_manual_clearance_markdown(source_packet: dict) -> str:
    proposal = source_packet.get("manualClearanceProposal") if isinstance(source_packet.get("manualClearanceProposal"), dict) else {}
    lanes = proposal.get("laneProposals") if isinstance(proposal.get("laneProposals"), list) else []
    if not lanes:
        return "- Source manual clearance proposal: missing. Run `npm run --silent bill:source-packet-review`."
    lines = [
        f"- Source manual clearance proposal: `{proposal.get('decision', 'missing')}`; review-only, no staging from this note.",
    ]
    for lane in lanes:
        if not isinstance(lane, dict):
            continue
        lines.append(
            "  - `{lane}` reviewFirst `{review}` keepResearch `{keep}` shadowOnly `{shadow}` quarantine `{quarantine}` safeAutoStage `{safe}`".format(
                lane=lane.get("lane", "missing"),
                review=(lane.get("reviewFirst") or [])[:3],
                keep=(lane.get("keepResearchCandidates") or [])[:3],
                shadow=(lane.get("shadowOnly") or [])[:3],
                quarantine=(lane.get("quarantineReview") or [])[:3],
                safe=lane.get("safeToStageAutomatically", "missing"),
            )
        )
    return "\n".join(lines)


def source_packet_review_summary_line(source_packet: dict, today: str) -> str:
    return (
        "- Source packet review: decision `{decision}`, reviewed `{reviewed}`, keepResearch `{keep}`, "
        "shadowOnly `{shadow}`, dependencyReviewed `{dependency}`, reviewBeforeStaging `{review_before}`, "
        "quarantineReview `{quarantine}`, topQuarantine `{top_quarantine}`, sourceBlockers `{source_blockers}`, "
        "cleared `{cleared}`, safeAutoStage `{safe}`, requiresOperatorDecision `{operator}`, "
        "link `[[bill-source-packet-review-{today}]]`"
    ).format(
        decision=source_packet.get("decision", "missing"),
        reviewed=source_packet.get("reviewedPacketCount", "missing"),
        keep=source_packet.get("keepResearchCount", "missing"),
        shadow=source_packet.get("shadowOnlyCount", "missing"),
        dependency=source_packet.get("dependencyReviewedCount", "missing"),
        review_before=source_packet.get("reviewBeforeStagingCount", "missing"),
        quarantine=source_packet.get("quarantineReviewCount", "missing"),
        top_quarantine=source_packet.get("topQuarantineReview", [])[:5],
        source_blockers=source_packet.get("sourceCleanBlockers", []),
        cleared=source_packet.get("packetReviewCleared", "missing"),
        safe=source_packet.get("safeToStageAutomatically", "missing"),
        operator=source_packet.get("requiresOperatorDecision", "missing"),
        today=today,
    )


def codex_automation_summary_line(codex_automations: dict, today: str) -> str:
    return (
        "- Codex automation audit: status `{status}`, activeBill `{active_bill}`, "
        "activePredictionCaptures `{active_prediction}`, pausedPredictionCaptures `{paused_prediction}`, "
        "activeFuturesOpenSessionProofs `{active_futures_proofs}`, "
        "futuresProofConflicts `{futures_proof_conflicts}`, blockers `{blockers}`, "
        "link `[[codex-automation-audit-{today}]]`"
    ).format(
        status=codex_automations.get("status", "missing"),
        active_bill=codex_automations.get("activeBillAutomationCount", "missing"),
        active_prediction=codex_automations.get("activePredictionCaptureIds", []),
        paused_prediction=codex_automations.get("pausedPredictionCaptureIds", []),
        active_futures_proofs=codex_automations.get("activeFuturesOpenSessionProofIds", []),
        futures_proof_conflicts=codex_automations.get("activeFuturesOpenSessionProofConflictIds", []),
        blockers=codex_automations.get("blockers", []),
        today=today,
    )


def replace_block(path: Path, title: str, block: str, preamble: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    start = f"<!-- {title}_START -->"
    end = f"<!-- {title}_END -->"
    body = path.read_text() if path.exists() else preamble.rstrip() + "\n"
    wrapped = f"{start}\n{block.rstrip()}\n{end}\n"
    if start in body and end in body:
        before = body.split(start, 1)[0]
        after = body.split(end, 1)[1]
        path.write_text(before.rstrip() + "\n\n" + wrapped + after.lstrip())
    else:
        path.write_text(body.rstrip() + "\n\n" + wrapped)


def path_matches(path: Path) -> bool:
    text = str(path).lower()
    return path.suffix.lower() in RESOURCE_EXTS and any(keyword in text for keyword in RESOURCE_KEYWORDS)


def category_for(path: Path) -> str:
    text = str(path).lower()
    name = path.name.lower()
    if path.suffix.lower() == ".pdf":
        return "paper"
    if any(token in text for token in ["topstep", "order", "fill", "trade", "broker"]):
        return "execution"
    if any(token in text for token in ["prediction", "polymarket", "kalshi", "gengar", "manifold"]):
        return "prediction-market"
    if any(token in text for token in ["strategy", "backtest", "walkforward", "oos", "alpha", "src/strategies"]):
        return "strategy-research"
    if any(token in text for token in ["kronos", "timesfm", "model"]):
        return "forecasting-model"
    if path.suffix.lower() in {".csv", ".parquet"}:
        return "dataset"
    if any(token in name for token in ["readme", "audit", "plan", "context", "protocol"]):
        return "control-doc"
    return "research"


def execution_review_path(path: Path) -> bool:
    text = str(path).lower()
    name = path.name.lower()
    risky_names = (
        "60m_exec_bridge",
        "agentic_fund",
        "auto-execute",
        "deposit",
        "fund-and-trade",
        "master_bridge",
        "pm_arb_scanner",
        "polymarketexecution",
        "realtime_data_bridge",
        "signalrouter",
        "start-gengar-live",
        "swap-and-fund",
        "topstep_demo_bridge",
        "wire-up",
    )
    return any(token in name for token in risky_names) or "/src/prediction/execution/" in text


def status_for(path: Path) -> str:
    text = str(path).lower()
    if any(token in text for token in ["retired", "notused", "graveyard", "no-edge", "mistake"]):
        return "retired-or-quarantine"
    if execution_review_path(path):
        return "execution-review"
    if any(token in text for token in ["state/", "latest", "runtime"]):
        return "current-artifact"
    if path.is_relative_to(VAULT):
        return "in-obsidian"
    if path.is_relative_to(HEDGE) and "/external/" not in text and "/research-repos/" not in text:
        return "implementation"
    if any(token in text for token in ["downloads", "/research/", "external-alpha", "gs-quant", "kronos"]):
        return "external-reference"
    if path.is_relative_to(HEDGE):
        return "implementation"
    return "candidate"


def inventory_priority_score(path: Path) -> int:
    """Rank resources for the human-facing Obsidian inventory.

    The full JSONL manifest remains exhaustive. This score only controls which
    rows surface first in the markdown page so archived dependency READMEs do
    not drown out Bill/Hermes control, research, data, and strategy evidence.
    """
    text = str(path).lower()
    name = path.name.lower()
    category = category_for(path)
    status = status_for(path)
    score = 0

    if path in RESOURCE_FILES:
        score += 220
    if path.is_relative_to(VAULT):
        score += 140
    if path.is_relative_to(HEDGE):
        score += 115
    if "/volumes/seagate expansion drive/hedge-data/features/" in text:
        score += 105
    if "/volumes/seagate expansion drive/hedge-data/external-alpha" in text:
        score += 70
    if "/downloads/" in text and path.suffix.lower() == ".pdf":
        score += 100

    score += {
        "current-artifact": 95,
        "in-obsidian": 90,
        "implementation": 80,
        "external-reference": 45,
        "candidate": 20,
        "execution-review": 5,
        "retired-or-quarantine": -90,
    }.get(status, 0)
    score += {
        "paper": 85,
        "prediction-market": 70,
        "strategy-research": 65,
        "dataset": 60,
        "execution": 55,
        "control-doc": 45,
        "forecasting-model": 35,
        "research": 30,
    }.get(category, 0)

    if any(token in text for token in ["/agent-hermes/", "/research-catalog/", "/trading/topstep-100k/"]):
        score += 80
    if any(token in text for token in ["/scripts/", "/src/prediction/", "/src/strategies/", "/bill-core/"]):
        score += 55
    if any(token in text for token in ["futures", "prediction", "polymarket", "kalshi", "topstep", "backtrader"]):
        score += 35
    if any(token in text for token in ["latest.json", "latest.md", "no-edge-ledger", "goal-completion", "clearance"]):
        score += 25

    if "/local-archives/" in text:
        score -= 140
    if ".openclaw.retired" in text:
        score -= 120
    if "/research-repos/" in text and name == "readme.md":
        score -= 95
    if "/examples/" in text:
        score -= 65
    if name == "readme.md":
        score -= 40
    if any(token in text for token in ["uv-cache", "cache-relocations", "/test/", "/tests/"]):
        score -= 45

    return score


def inventory_priority_reason(path: Path) -> str:
    text = str(path).lower()
    if path in RESOURCE_FILES:
        return "explicit Bill research seed"
    if path.is_relative_to(VAULT):
        return "already linked in Obsidian"
    if status_for(path) == "execution-review":
        return "execution/funding path; review firewall first"
    if "/volumes/seagate expansion drive/hedge-data/features/" in text:
        return "Seagate feature/data source"
    if path.is_relative_to(HEDGE) and any(token in text for token in ["/scripts/", "/src/prediction/", "/src/strategies/"]):
        return "active Bill implementation"
    if status_for(path) == "current-artifact":
        return "current machine artifact"
    if path.suffix.lower() == ".pdf":
        return "research paper"
    if "/local-archives/" in text or ".openclaw.retired" in text:
        return "archived/retired; low priority unless explicitly revived"
    if path.name.lower() == "readme.md":
        return "README/reference; summarize before use"
    return "candidate resource"


def prioritized_resource_paths(resources: list[Path]) -> list[Path]:
    return sorted(
        resources,
        key=lambda path: (
            -inventory_priority_score(path),
            category_for(path),
            status_for(path),
            str(path).lower(),
        ),
    )


def diversified_priority_paths(resources: list[Path], *, per_category: int = 18) -> list[Path]:
    selected: list[Path] = []
    counts: dict[str, int] = {}
    deferred: list[Path] = []
    for path in prioritized_resource_paths(resources):
        category = category_for(path)
        if counts.get(category, 0) < per_category:
            selected.append(path)
            counts[category] = counts.get(category, 0) + 1
        else:
            deferred.append(path)
    return selected + deferred


def next_obsidian_summary_paths(resources: list[Path], *, limit: int = 40) -> list[Path]:
    """Pick outside-vault research objects that need human/agent summaries.

    The main priority table intentionally surfaces active implementations and
    current artifacts. This queue is different: it is for papers, YT/research
    notes, datasets, feature stores, and external references that should be
    summarized into Obsidian before weaker agents treat them as evidence.
    """
    candidates: list[Path] = []
    for path in resources:
        if path.is_relative_to(VAULT):
            continue
        status = status_for(path)
        category = category_for(path)
        text = str(path).lower()
        name = path.name.lower()
        if status in {"execution-review", "retired-or-quarantine", "implementation", "current-artifact"}:
            continue
        if "/local-archives/" in text or ".openclaw.retired" in text or name == "readme.md":
            continue
        if category in {"paper", "dataset", "forecasting-model"}:
            candidates.append(path)
            continue
        if status in {"external-reference", "candidate"} and any(
            token in text
            for token in [
                "paper",
                "research",
                "youtube",
                "yt",
                "transcript",
                "futures",
                "prediction",
                "polymarket",
                "kalshi",
                "kronos",
                "timesfm",
                "gs-quant",
                "feature",
                "alpha",
            ]
        ):
            candidates.append(path)

    return sorted(
        candidates,
        key=lambda path: (
            -inventory_priority_score(path),
            category_for(path),
            status_for(path),
            str(path).lower(),
        ),
    )[:limit]


def link_for(path: Path) -> str:
    label = str(path)
    return f"[{label}](<{path}>)"


def iter_resource_paths() -> list[Path]:
    out: list[Path] = []
    seen: set[str] = set()
    for path in RESOURCE_FILES:
        if not path.exists() or not path.is_file() or not path_matches(path):
            continue
        seen.add(str(path))
        out.append(path)
    for root in RESOURCE_ROOTS:
        if not root.exists():
            continue
        if root.is_file():
            if path_matches(root) and str(root) not in seen:
                seen.add(str(root))
                out.append(root)
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [
                d for d in dirnames
                if d not in SKIP_DIRS
                and not d.startswith(".Trash")
                and not any(d.startswith(prefix) for prefix in SKIP_DIR_PREFIXES)
                and not any(token in d for token in SKIP_DIR_SUBSTRINGS)
            ]
            current = Path(dirpath)
            if any(token in current.parts for token in SKIP_DIR_SUBSTRINGS):
                dirnames[:] = []
                continue
            if current != root and len(current.relative_to(root).parts) > 5:
                dirnames[:] = []
            for filename in filenames:
                path = current / filename
                if not path_matches(path):
                    continue
                key = str(path)
                if key in seen:
                    continue
                seen.add(key)
                out.append(path)
    return sorted(out, key=lambda p: (category_for(p), status_for(p), str(p).lower()))


def write_full_resource_manifest(resources: list[Path], now: datetime) -> None:
    RESOURCE_FULL_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    with RESOURCE_FULL_MANIFEST.open("w") as handle:
        for idx, path in enumerate(resources, start=1):
            handle.write(json.dumps({
                "generatedAt": now.isoformat(),
                "index": idx,
                "category": category_for(path),
                "status": status_for(path),
                "path": str(path),
                "suffix": path.suffix.lower(),
            }, sort_keys=True) + "\n")


def write_resource_inventory(now: datetime) -> dict:
    resources = iter_resource_paths()
    write_full_resource_manifest(resources, now)
    priority_resources = prioritized_resource_paths(resources)
    priority_outside_obsidian = diversified_priority_paths(
        [path for path in priority_resources if not path.is_relative_to(VAULT)]
    )
    summary_queue = next_obsidian_summary_paths(resources)
    category_counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}
    outside_obsidian = 0
    for path in resources:
        category_counts[category_for(path)] = category_counts.get(category_for(path), 0) + 1
        status_counts[status_for(path)] = status_counts.get(status_for(path), 0) + 1
        if not path.is_relative_to(VAULT):
            outside_obsidian += 1

    rows = []
    for idx, path in enumerate(priority_resources[:MAX_INVENTORY_ROWS], start=1):
        rows.append(
            "| {idx} | {category} | {status} | {reason} | {path} |".format(
                idx=idx,
                category=category_for(path),
                status=status_for(path),
                reason=inventory_priority_reason(path),
                path=link_for(path),
            )
        )

    priority_reasons: dict[str, int] = {}
    for path in priority_resources[:MAX_PRIORITY_REASON_ROWS]:
        reason = inventory_priority_reason(path)
        priority_reasons[reason] = priority_reasons.get(reason, 0) + 1

    outside_rows = []
    for idx, path in enumerate(priority_outside_obsidian[:80], start=1):
        outside_rows.append(
            "| {idx} | {category} | {status} | {reason} | {path} |".format(
                idx=idx,
                category=category_for(path),
                status=status_for(path),
                reason=inventory_priority_reason(path),
                path=link_for(path),
            )
        )

    summary_rows = []
    for idx, path in enumerate(summary_queue, start=1):
        summary_rows.append(
            "| {idx} | {category} | {status} | {reason} | {path} |".format(
                idx=idx,
                category=category_for(path),
                status=status_for(path),
                reason=inventory_priority_reason(path),
                path=link_for(path),
            )
        )

    content = f"""# Bill Resource Inventory

Generated: {now.isoformat()}

Parent hub: [[../Agent-Hermes/BILL-CONTROL-HUB]]

This is an index, not a file dump. Large datasets, PDFs, repos, and scripts stay in place and are linked here.

## Summary

- Total matched resources: {len(resources)}
- Outside Obsidian: {outside_obsidian}
- Rows shown: {min(len(resources), MAX_INVENTORY_ROWS)}
- Full machine-readable manifest: {link_for(RESOURCE_FULL_MANIFEST)}
- Category counts: `{category_counts}`
- Status counts: `{status_counts}`
- Display policy: highest-signal Bill/Hermes resources first; archived repo READMEs/examples are down-ranked, not removed.
- Top priority reasons: `{priority_reasons}`

## How To Use

- `external-reference`: paper, repo, model, or data that should be summarized into Obsidian before use.
- `implementation`: code that exists in the Bill repo and may need tests or docs.
- `execution-review`: execution/funding-adjacent code; review firewall evidence before use.
- `current-artifact`: machine state; treat as fresh only after checking timestamp.
- `retired-or-quarantine`: do not promote without new evidence.

## Priority Outside Obsidian

These are the highest-signal Bill/Hermes resources still living outside the vault. Link/summarize them before weaker agents use them as research evidence.

| # | Category | Status | Why shown | Resource |
|---|---|---|---|---|
{chr(10).join(outside_rows)}

## Next Obsidian Summary Queue

These are outside-vault research objects to summarize/link into Obsidian first. This queue intentionally favors papers, datasets, model/feature references, YT/transcript/research notes, and candidate alpha sources over active implementation files.

| # | Category | Status | Why shown | Resource |
|---|---|---|---|---|
{chr(10).join(summary_rows)}

## Inventory

| # | Category | Status | Why shown | Resource |
|---|---|---|---|---|
{chr(10).join(rows)}
"""
    RESOURCE_INVENTORY.parent.mkdir(parents=True, exist_ok=True)
    RESOURCE_INVENTORY.write_text(content)
    return {
        "inventory": str(RESOURCE_INVENTORY),
        "fullManifest": str(RESOURCE_FULL_MANIFEST),
        "resourceCount": len(resources),
        "outsideObsidian": outside_obsidian,
        "rowsShown": min(len(resources), MAX_INVENTORY_ROWS),
        "summaryQueueCount": len(summary_queue),
    }


def main() -> None:
    now = datetime.now(timezone.utc)
    today = trading_day(now)

    monitor = read_json(STATE / "topstep-100k-monitor.latest.json")
    master = read_json(STATE / "master-signal.latest.json")
    submission = read_json(STATE / "topstep-demo-submission.latest.json")
    contract = read_json(STATE / "strategy-research-contracts.latest.json")
    prediction = read_json(STATE / "prediction-review.latest.json")
    prediction_cycle = read_json(STATE / "prediction-cycle.latest.json")
    best = best_backtrader()
    vol_oos = vol_regime_oos()
    prediction_summary = prediction_review_summary(prediction, prediction_cycle)
    calibration_gate = prediction_calibration_gate()
    research_watchlist = prediction_watchlist()
    prediction_triage = prediction_evidence_triage()
    prediction_resolved_review = prediction_resolved_review_summary(prediction_triage)
    prediction_drilldown = prediction_category_drilldown()
    prediction_narrow_scan = prediction_narrow_scan_runner()
    prediction_resolved_join = prediction_resolved_outcome_join()
    prediction_no_edge = prediction_no_edge_ledger()
    prediction_training = prediction_learning()
    research_watchlist_summary = watchlist_summary(research_watchlist)
    clob_edge_gate = polymarket_clob_edge_gate()
    clob_microstructure = prediction_clob_microstructure_audit()
    clob_microstructure_summary = prediction_clob_microstructure_summary(clob_microstructure)
    clob_spread_compression = prediction_clob_spread_compression_replay()
    clob_latency_staleness = prediction_clob_latency_staleness_replay()
    clob_trade_impact = prediction_clob_trade_impact_replay()
    clob_recorder = polymarket_clob_recorder()
    macro_rates_summary = prediction_macro_rates_summary(
        fillability=kalshi_fillability_snapshot(),
        requirements=prediction_macro_rates_requirements(),
        labels=prediction_macro_rates_resolved_labels(),
        replay=prediction_macro_rates_cross_source_replay(),
    )
    prediction_event_gap = prediction_event_label_gap_plan()
    prediction_event_paper_gate = prediction_event_paper_promotion_gate()
    prediction_event_capture = prediction_event_capture_cycle()
    prediction_event_replay = prediction_event_lag_replay()
    prediction_event_timestamps = prediction_event_timestamp_dataset()
    prediction_event_targets = prediction_event_clob_capture_targets()
    prediction_event_mapping = prediction_event_mapping_summary(
        prediction_event_market_mapping_plan(),
        prediction_event_mapping_refinement(),
    )
    clob_live_quality = (
        clob_recorder.get("liveQualityDiagnostics")
        if isinstance(clob_recorder.get("liveQualityDiagnostics"), dict)
        else {}
    )
    event_capture_live_quality = (
        ((prediction_event_capture.get("latestRecorder") or {}).get("liveQualityDiagnostics") or {})
        if isinstance(prediction_event_capture.get("latestRecorder"), dict)
        else {}
    )
    cron_validator = cron_state_validator()
    cron_trust = cron_validator.get("cron_trust") if isinstance(cron_validator.get("cron_trust"), dict) else {}
    signal_quality = signal_quality_advisor()
    signal_source_truth = signal_source_truth_audit()
    whale_flow = whale_flow_signal()
    futures_triage = futures_evidence_triage()
    databento_realtime = databento_realtime_smoke()
    databento_orderflow = databento_orderflow_feature_smoke()
    futures_cost_gate = futures_cost_slippage_gate()
    futures_cost_summary = futures_cost_gate_summary(futures_cost_gate)
    futures_no_edge = futures_no_edge_ledger()
    research_loop = research_closed_loop_contract()
    fund_os_audit = fund_os_completion_audit()
    fund_promotion_summary = fund_os_promotion_contract_summary(fund_os_audit)
    strategy_feed = research_strategy_feed()
    seed_triage = research_seed_triage()
    youtube_source_cards = queued_youtube_source_card_summary(seed_triage)
    alpha_tooling = alpha_research_tooling_check()
    alpha_direction = alpha_research_direction_audit()
    storage_summary = hermes_storage_summary(hermes_storage_audit())
    codex_automations = codex_automation_audit()
    runtime_architecture = runtime_architecture_audit()
    data_freshness = data_freshness_gate()
    futures_refresh = futures_research_data_refresh()
    futures_quality = futures_data_quality()
    futures_nq_cycle = futures_nq_research_cycle()
    futures_nq_summary = futures_nq_research_cycle_summary(futures_nq_cycle)
    futures_sizing_summary = futures_nq_sizing_overlay_summary(futures_nq_sizing_overlay())
    premarket_risk = premarket_risk_brief()
    data_proof = open_session_data_proof()
    open_session_summary = futures_open_session_proof_summary(data_proof)
    worktree = worktree_consolidation()
    source_intake = source_intake_manifest()
    source_hygiene = source_hygiene_plan()
    source_lane_packets = source_hygiene_lane_packet_summary(source_hygiene)
    source_lane_packets_md = source_hygiene_lane_packet_markdown(source_lane_packets)
    source_packet = source_packet_review()
    source_manual_clearance_md = source_manual_clearance_markdown(source_packet)
    data_intake = data_intake_manifest()
    execution_intake = execution_intake_manifest()
    clearance = clearance_evidence()
    goal_audit = goal_completion_audit()
    goal_summary = goal_completion_summary(goal_audit)
    firewall_evidence = execution_firewall_evidence_summary(clearance)
    research_actions = next_research_actions()
    research_action_items = research_actions.get("actions") if isinstance(research_actions.get("actions"), list) else []
    forward_capture_command = prediction_forward_capture_command(research_action_items)
    cron_issues = cron_validator.get("issues") if isinstance(cron_validator.get("issues"), list) else []
    master_job = cron_job("master-strategy-bridge")
    canonical_worktree = next(
        (
            item for item in (worktree.get("worktrees") or [])
            if item.get("path") == str(HEDGE)
        ),
        {},
    )
    canonical_source = worktree.get("canonicalSource") if isinstance(worktree.get("canonicalSource"), dict) else {}
    if canonical_source:
        canonical_worktree = {
            **canonical_worktree,
            "dirtyFiles": canonical_source.get("dirtyFiles", canonical_worktree.get("dirtyFiles")),
            "categories": canonical_source.get("categories", canonical_worktree.get("categories")),
            "intakeDecision": canonical_source.get("intakeDecision", canonical_worktree.get("intakeDecision")),
        }
    execution_live_samples = canonical_source.get("executionLiveFiles") if isinstance(canonical_source.get("executionLiveFiles"), list) else []
    dirty_siblings = worktree.get("dirtySiblingWorktrees") if isinstance(worktree.get("dirtySiblingWorktrees"), dict) else {}
    clearance_queue = worktree.get("clearanceQueue") if isinstance(worktree.get("clearanceQueue"), list) else []
    source_clean_blockers = worktree.get("sourceCleanBlockers") if isinstance(worktree.get("sourceCleanBlockers"), list) else []
    clearance_summary = [
        {
            "lane": item.get("lane"),
            "dirtyFiles": item.get("dirtyFiles"),
            "nextEvidence": (item.get("requiredEvidence") or ["missing"])[0],
        }
        for item in clearance_queue[:4]
        if isinstance(item, dict)
    ]

    secure_flags = {
        key: read_env_flag(SECURE_ENV, key)
        for key in ["BILL_ENABLE_FUTURES_DEMO_EXECUTION", "RH_TOPSTEP_READ_ONLY", "RH_LIVE_EXECUTION_ENABLED"]
    }
    ops_flags = {
        key: read_env_flag(OPS_ENV, key)
        for key in ["BILL_ENABLE_FUTURES_DEMO_EXECUTION", "RH_TOPSTEP_READ_ONLY", "RH_LIVE_EXECUTION_ENABLED"]
    }
    topstep_log_path = current_topstep_operating_log(now)
    order_reconciliation = order_reconciliation_markdown(monitor, submission, topstep_log_path)

    blockers = monitor.get("hard_blockers") or []
    warnings = monitor.get("warnings") or []
    routing_locked = (
        secure_flags["BILL_ENABLE_FUTURES_DEMO_EXECUTION"] != "true"
        or secure_flags["RH_TOPSTEP_READ_ONLY"] == "true"
        or bool(blockers)
        or master_job.get("enabled") is False
    )
    order_decision = "No new Bill/Hermes orders approved." if routing_locked else "Demo routing is armed; verify broker and daily plan before any order."

    synced = f"""## Synced State

Updated: {now.isoformat()}

**Decision:** {order_decision}

### Gates

- Topstep monitor: `{monitor.get('status', 'missing')}`
- Hard blockers: `{blockers}`
- Warnings: `{warnings}`
- Strategy research contract: `{contract.get('status', 'missing')}`
- Master bridge cron: `enabled={master_job.get('enabled', 'missing')}`, `state={master_job.get('state', 'missing')}`
- Goal completion audit: decision `{goal_summary['decision']}`, complete `{goal_summary['goalComplete']}`, pass `{goal_summary['passCount']}/{goal_summary['checkCount']}`, blocked `{goal_summary['blockedCount']}`, blockedIds `{goal_summary['blockedIds']}`, promptUncovered `{goal_summary['promptUncovered']}`, link `[[bill-goal-completion-audit-{today}]]`
- Goal audit top blockers: `{goal_summary['topBlockers']}`
- Cron/state validator: `{cron_validator.get('summary', 'missing')}`, severityCounts `{severity_counts(cron_issues)}`
{codex_automation_summary_line(codex_automations, today)}
{runtime_architecture_summary_line(runtime_architecture, today)}
- Cron trust: activeTradingNoAgent `{cron_trust.get('activeTradingNoAgentCount', 'missing')}`, activeTradingAgentBacked `{cron_trust.get('activeTradingAgentBackedCount', 'missing')}`, noAgentMetadataMismatch `{cron_trust.get('noAgentMetadataMismatchCount', 'missing')}`, quarantinedScriptRefs `{cron_trust.get('quarantinedScriptReferenceCount', 'missing')}`, activeDirtyExecutionRefs `{cron_trust.get('activeDirtyExecutionLiveScriptReferenceCount', 'missing')}`, activeTopstepBrokerSessionRefs `{cron_trust.get('activeTopstepBrokerSessionCronRefCount', 'missing')}`
- Active dirty execution cron refs: `{active_dirty_execution_cron_summary(cron_validator)}`
- Active dirty execution cron remediation: `{active_dirty_execution_cron_remediation(cron_validator)}`
- Active Topstep broker-session cron refs: `{active_topstep_broker_session_cron_summary(cron_validator)}`
- Active Topstep broker-session cron remediation: `{active_topstep_broker_session_cron_remediation(cron_validator)}`
- Active shadow cron script guardrails: drift `{cron_trust.get('activeShadowCronScriptGuardrailDriftCount', 'missing')}`, scripts `{active_shadow_cron_script_guardrail_summary(cron_validator)}`
- Shadow cron states: `{shadow_cron_state_summary(cron_validator)}`
- Worktree hygiene: dirtyFiles `{canonical_worktree.get('dirtyFiles', 'missing')}`, categories `{canonical_worktree.get('categories', {})}`, intakeDecision `{canonical_worktree.get('intakeDecision', 'missing')}`
- Dirty execution/live samples: `{execution_live_samples[:8]}`
- Source intake manifest: decision `{source_intake.get('decision', 'missing')}`, sourceClean `{source_intake.get('sourceClean', 'missing')}`, visible `{source_intake.get('sourceIntakeVisible', 'missing')}`, executionLiveDirty `{source_intake.get('executionLiveDirtyCount', 'missing')}`, reviewBacklog `{source_intake.get('reviewBacklogCount', 'missing')}`, classes `{source_intake.get('classificationCounts', {})}`
- Source hygiene plan: decision `{source_hygiene.get('decision', 'missing')}`, cleared `{source_hygiene.get('sourceHygieneCleared', 'missing')}`, autoCleanup `{source_hygiene.get('automaticCleanupAllowed', 'missing')}`, safeAutoStage `{source_hygiene.get('safeToStageAutomatically', 'missing')}`, nextReduction `{[(item.get('rank'), item.get('bundleId')) for item in (source_hygiene.get('nextReductionOrder') or [])[:4] if isinstance(item, dict)]}`
{source_lane_packets_md}
{source_packet_review_summary_line(source_packet, today)}
{source_manual_clearance_md}
- Data intake manifest: decision `{data_intake.get('decision', 'missing')}`, dirtyDataFiles `{data_intake.get('dirtyDataFileCount', 'missing')}`, csvFiles `{data_intake.get('csvFileCount', 'missing')}`, executionGradeData `{data_intake.get('executionGradeData', 'missing')}`, readyForExecutionData `{data_intake.get('readyForExecutionData', 'missing')}`, risks `{data_intake.get('riskCounts', {})}`
- Execution intake manifest: decision `{execution_intake.get('decision', 'missing')}`, canonicalDirtyExecution `{execution_intake.get('canonicalExecutionLiveDirtyCount', execution_intake.get('dirtyExecutionFileCount', 'missing'))}`, executionAdjacentReview `{execution_intake.get('executionAdjacentFileCount', 'missing')}`, activeCronRefs `{execution_intake.get('activeCronReferenceCount', 'missing')}`, activeCronRefPaths `{execution_intake.get('activeCronReferencePaths', [])[:8]}`, locked `{execution_intake.get('executionLocked', 'missing')}`, allMappedFirewallsPassed `{execution_intake.get('allFirewallCommandsPassed', 'missing')}`, uncovered `{execution_intake.get('uncoveredExecutionPaths', [])[:8]}`, classes `{execution_intake.get('classificationCounts', {})}`
- Execution firewall evidence: `{firewall_evidence['passed']}/{firewall_evidence['total']} PASS`, failed `{firewall_evidence['failed']}`, clearanceStatus `{firewall_evidence['status']}`
- Dirty sibling worktrees: `{dirty_siblings.get('count', 'missing')}`
- Source-clean blockers: `{source_clean_blockers}`
- Clearance queue: `{clearance_summary}`

### Env Flags

Secure env:
- `BILL_ENABLE_FUTURES_DEMO_EXECUTION={secure_flags['BILL_ENABLE_FUTURES_DEMO_EXECUTION']}`
- `RH_TOPSTEP_READ_ONLY={secure_flags['RH_TOPSTEP_READ_ONLY']}`
- `RH_LIVE_EXECUTION_ENABLED={secure_flags['RH_LIVE_EXECUTION_ENABLED']}`

Ops env:
- `BILL_ENABLE_FUTURES_DEMO_EXECUTION={ops_flags['BILL_ENABLE_FUTURES_DEMO_EXECUTION']}`
- `RH_TOPSTEP_READ_ONLY={ops_flags['RH_TOPSTEP_READ_ONLY']}`
- `RH_LIVE_EXECUTION_ENABLED={ops_flags['RH_LIVE_EXECUTION_ENABLED']}`

### Latest Signal / Order

{latest_signal_order_markdown(master, submission, routing_locked=routing_locked)}

### Orders/Fills/Reconciliation

{order_reconciliation}

### Research Snapshot

- Best Backtrader row: `{best.get('strategy', 'missing')}`, stop `{best.get('stopPoints', 'missing')}`, target `{best.get('targetPoints', 'missing')}`, totalR `{best.get('totalR', 'missing')}` (research-only full-sample)
- Vol-regime purged OOS: status `{vol_oos.get('status', 'missing')}`, netR `{(vol_oos.get('aggregateOos') or {}).get('netR', 'missing')}`, PF `{(vol_oos.get('aggregateOos') or {}).get('profitFactor', 'missing')}`, blockers `{len(vol_oos.get('blockers') or [])}`
- Futures evidence triage: decision `{futures_triage.get('decision', 'missing')}`, nextTests `{[item.get('id') for item in (futures_triage.get('nextTests') or [])[:3]]}`
- Futures cost/slippage gate: discoverySurvivors `{futures_cost_summary['backtraderDiscoverySurvivors']}`, purgedOosPromotionSurvivors `{futures_cost_summary['purgedOosPromotionSurvivors']}`, review `{futures_cost_summary['survivorReviewDecision']}`, status `{futures_cost_summary['survivorReviewStatus']}`, parameterMiningRisk `{futures_cost_summary['parameterMiningRisk']}`, readyForDemoExpansion `{futures_cost_summary['readyForDemoExpansion']}`, requiredNextEvidence `{futures_cost_summary['requiredNextEvidence']}`, failureCounts `{futures_cost_summary['failureCounts']}`
- Futures no-edge ledger: entries `{futures_no_edge.get('count', 'missing')}`, noEdge `{futures_no_edge.get('noEdgeCount', 'missing')}`, needsNewFeature `{futures_no_edge.get('needsNewFeatureCount', 'missing')}`, promotable `{futures_no_edge.get('promotableCount', 'missing')}`
- Alpha research tooling: status `{alpha_tooling.get('status', 'missing')}`, readyForResearchLoop `{alpha_tooling.get('readyForResearchLoop', 'missing')}`, blockers `{alpha_tooling.get('blockers', [])}`, warnings `{alpha_tooling.get('warnings', [])}`
- Alpha research direction: decision `{alpha_direction.get('decision', 'missing')}`, queueSafe `{alpha_direction.get('queueSafe', 'missing')}`, continue `{[item.get('id') for item in (alpha_direction.get('continueLanes') or [])[:3] if isinstance(item, dict)]}`, retire `{[item.get('id') for item in (alpha_direction.get('retireOrQuarantineLanes') or [])[:3] if isinstance(item, dict)]}`, nextOneVariable `{(alpha_direction.get('nextOneVariableTest') or {}).get('id', 'missing')}`, readyForExecution `{alpha_direction.get('readyForExecution', 'missing')}`
- Hermes storage: total `{storage_summary['totalSize']}`, archiveCandidates `{storage_summary['archiveCandidateSize']}`, archiveRoot `{storage_summary['archiveRoot']}`, mountExists `{storage_summary['archiveMountExists']}`, movesFiles `{storage_summary['movesFiles']}`, deletesFiles `{storage_summary['deletesFiles']}`, stateSnapshotsArchive `{storage_summary['stateSnapshotsArchive']}`, topCandidates `{storage_summary['topCandidates']}`, cleanupPlan `{storage_summary['cleanupPlanIds']}`, nextActions `{storage_summary['nextActions']}`
- Futures research data refresh: status `{futures_refresh.get('status', 'missing')}`, source `{futures_refresh.get('source', 'missing')}`, items `{[(item.get('interval'), item.get('rows'), item.get('latestTs'), item.get('wroteFile'), item.get('completeSymbolSet'), item.get('missingSymbols'), item.get('recoveredSymbols')) for item in (futures_refresh.get('items') or [])]}`
- Futures data quality: pass `{futures_quality.get('pass', 'missing')}`, datasets `{[(Path(item.get('path', '')).name, item.get('rows'), item.get('endTs'), item.get('pass'), item.get('failingChecks')) for item in (futures_quality.get('datasets') or [])]}`
- Futures NQ research cycle: decision `{futures_nq_summary['decision']}`, mode `{futures_nq_summary['mode']}`, bestCandidate `{futures_nq_summary['bestCandidate']}`, trades `{futures_nq_summary['tradeCount']}`, positiveFoldShare `{futures_nq_summary['positiveFoldShare']}`, survivingCostCases `{futures_nq_summary['survivingCaseCount']}`, historicalCurrentCsvParity `{futures_nq_summary['currentLocalCsvParity']}`, historicalCurrentParitySummary `{futures_nq_summary['historicalCurrentParitySummary']}`, coverageBlockers `{futures_nq_summary['coverageBlockers']}`, currentParity `{futures_nq_summary['currentParityDecision']}`, brokerParityChecked `{futures_nq_summary['brokerParityChecked']}`, readyForDemoExpansion `{futures_nq_summary['readyForDemoExpansion']}`, blockers `{futures_nq_summary['blockers']}`
- Futures NQ sizing overlay: decision `{futures_sizing_summary['decision']}`, bestProfile `{futures_sizing_summary['bestProfileId']}`, oneVariable `{futures_sizing_summary['oneVariable']}`, assumptions `{futures_sizing_summary['assumptions']}`, watchProfiles `{futures_sizing_summary['watchProfiles']}`, blockedProfiles `{futures_sizing_summary['blockedProfiles']}`, readyForDemoExpansion `{futures_sizing_summary['readyForDemoExpansion']}`, blockers `{futures_sizing_summary['blockers']}`
- Premarket risk brief: decision `{premarket_risk.get('decision', 'missing')}`, hard/reduce/watch `{premarket_risk.get('riskCounts', {})}`, algoMaxContracts `{(premarket_risk.get('sizingPosture') or {}).get('algoMaxContracts', 'missing')}`, manualWatchMaxIfCleared `{(premarket_risk.get('sizingPosture') or {}).get('manualWatchMaxContractsIfDailyPlanClears', 'missing')}`, topRisks `{[(item.get('kind'), item.get('severity'), item.get('reason')) for item in (premarket_risk.get('risks') or [])[:5] if isinstance(item, dict)]}`, link `[[premarket-risk-brief-{today}]]`
- Open-session data proof: mode `{data_proof.get('mode', 'missing')}`, allCommandsPassed `{data_proof.get('allCommandsPassed', 'missing')}`, executionGradeDataProofPassed `{data_proof.get('executionGradeDataProofPassed', 'missing')}`, failed `{data_proof.get('failedStepIds', [])}`, state `{data_proof.get('stateSummary', {})}`
- Databento realtime smoke: status `{databento_realtime.get('status', 'missing')}`, readyForExecutionDataProof `{databento_realtime.get('readyForExecutionDataProof', 'missing')}`, reason `{(databento_realtime.get('quoteSummary') or {}).get('reason', 'missing')}`
- Futures next open-session proof: start `{open_session_summary['recommendedProofStartUtc']}`, end `{open_session_summary['recommendedProofEndUtc']}`, nextOpen `{open_session_summary['nextOpenUtc']}`, reason `{open_session_summary['reason']}`, dataOnly `{open_session_summary['commandsAreDataOnly']}`, readyForExecutionData `{open_session_summary['readyForExecutionData']}`, commands `{open_session_summary['dataOnlyCommands']}`
- Futures lower-timeframe vol-regime OOS: `{ {tf: {'status': item.get('status'), 'trades': (item.get('aggregate') or {}).get('trades'), 'netR': (item.get('aggregate') or {}).get('netR'), 'PF': (item.get('aggregate') or {}).get('profitFactor')} for tf, item in (futures_triage.get('volRegimeLowerTimeframeOos') or {}).items()} }`
- Futures Databento order-flow feature smoke: status `{(futures_triage.get('databentoOrderflowFeatureSmoke') or {}).get('status', 'missing')}`, family `{(futures_triage.get('databentoOrderflowFeatureSmoke') or {}).get('featureFamily', 'missing')}`, researchUsable `{(futures_triage.get('databentoOrderflowFeatureSmoke') or {}).get('researchUsable', 'missing')}`, depth `{(futures_triage.get('databentoOrderflowFeatureSmoke') or {}).get('completeDepthSize', 'missing')}`, domProxyReplacementReady `{(futures_triage.get('databentoOrderflowFeatureSmoke') or {}).get('domProxyReplacementReady', 'missing')}`, readyForExecution `{(futures_triage.get('databentoOrderflowFeatureSmoke') or {}).get('readyForExecution', 'missing')}`
- Databento order-flow direct reason: status `{databento_orderflow.get('status', 'missing')}`, reason `{(databento_orderflow.get('features') or {}).get('reason', 'missing')}`
- Futures realtime data freshness: verdict `{data_freshness.get('verdict', 'missing')}`, action `{data_freshness.get('action', 'missing')}`, checks `{[(item.get('symbol'), item.get('status'), item.get('reason')) for item in (data_freshness.get('checks') or [])]}`
- Futures promotion read: `OOS overrides Backtrader sweep; no futures candidate is demo-expandable while OOS/live-readiness are red.`
- Research closed-loop contract: researchOnly `{research_loop.get('researchOnly', 'missing')}`, readyForExecution `{research_loop.get('readyForExecution', 'missing')}`, checklistSteps `{len(research_loop.get('promptToArtifactChecklist') or [])}`, priorityLanes `{research_loop.get('priorityLanes', [])}`
- Next research actions: count `{len(research_action_items)}`, researchOnly `{research_actions.get('researchOnly', 'missing')}`, writesOrders `{research_actions.get('writesOrders', 'missing')}`, topActions `{[(item.get('id'), item.get('lane'), (item.get('commands') or ['missing'])[0]) for item in research_action_items[:5] if isinstance(item, dict)]}`
- Lead prediction research action: `{lead_research_action(research_action_items, 'prediction-markets')}`
- Prediction one-variable retest: `{lead_one_variable_retest(research_action_items, 'prediction-markets')}`
- Fund OS completion audit: overallStatus `{fund_os_audit.get('overallStatus', 'missing')}`, tradingReadinessStatus `{fund_os_audit.get('tradingReadinessStatus', 'missing')}`, blocked `{len(fund_os_audit.get('blocked') or [])}`, warnings `{len(fund_os_audit.get('warnings') or [])}`
- Fund promotion contract: decision `{fund_promotion_summary['decision']}`, current `{fund_promotion_summary['currentStage']}`, next `{fund_promotion_summary['nextStage']}`, readyDemo `{fund_promotion_summary['readyForDemoExpansion']}`, readyPredictionPaper `{fund_promotion_summary['readyForPaper']}`, stages `{fund_promotion_summary['stageStatus']}`, primaryLanes `{fund_promotion_summary['primaryLanes']}`, compoundRule `{fund_promotion_summary['compoundRule']}`
- Research strategy feed: allowedDirectives `{len(strategy_feed.get('directives') or [])}`, blockedDirectives `{strategy_feed.get('blockedDirectiveCount', len(strategy_feed.get('blockedDirectives') or []))}`, blockReason `{strategy_feed.get('directiveBlockReason', 'missing')}`, blockedStrategies `{[item.get('strategyId') for item in (strategy_feed.get('blockedDirectives') or [])[:6]]}`
- Research seed triage: total `{(seed_triage.get('summary') or {}).get('totalSeeds', 'missing')}`, queuedYT `{(seed_triage.get('summary') or {}).get('queuedYouTubeSeeds', 'missing')}`, candidateRetest `{(seed_triage.get('summary') or {}).get('candidateRetestSeeds', 'missing')}`, quarantinedNoEdge `{(seed_triage.get('summary') or {}).get('quarantinedNoEdgeSeeds', 'missing')}`, executable `{(seed_triage.get('summary') or {}).get('executableSeeds', 'missing')}`, nextBuild `{[(item.get('inferredStrategyId'), item.get('title')) for item in (seed_triage.get('nextBuildQueue') or [])[:5]]}`
- Queued YouTube source cards: present `{youtube_source_cards['present']}`, targets `{youtube_source_cards['targets']}`, rawChunks `{youtube_source_cards.get('rawChunks', 'missing')}`, promoted `{youtube_source_cards['promoted']}`, executionRelevant `{youtube_source_cards['executionRelevant']}`, researcherRun `{youtube_source_cards['researcherRun']}`, cards `{youtube_source_cards['cards']}`, note `{youtube_source_cards['path']}`
- Prediction review candidates: watch `{prediction_summary['watch']}`, paper `{prediction_summary['paper']}`, readyForPaper `{prediction_summary['readyForPaper']}`, recommendedStage `{prediction_summary['recommendedStage']}`, blockers `{prediction_summary['blockers']}`
- Prediction calibration gate: status `{calibration_gate.get('status', 'missing')}`, watchResearch `{calibration_gate.get('watchResearchCandidates', 'missing')}`, readyForPaper `{calibration_gate.get('readyForPaper', 'missing')}`
- Prediction research watchlist: watch `{research_watchlist_summary['watchCount']}`, CLOB tokens `{research_watchlist_summary['clobTokenCount']}`, spread-blocked `{research_watchlist_summary['spreadBlocked']}`, readyForPaper `{research_watchlist_summary['readyForPaper']}`
- Prediction evidence triage: decision `{prediction_triage.get('decision', 'missing')}`, nextTests `{[item.get('id') for item in (prediction_triage.get('nextTests') or [])[:4]]}`
- Prediction forward CLOB capture: required `{(prediction_triage.get('eventForwardCapture') or {}).get('forwardCaptureRequired', 'missing')}`, targets `{(prediction_triage.get('eventForwardCapture') or {}).get('recordableTargetCount', 'missing')}`, tokenSpecificCandidates `{(prediction_triage.get('eventForwardCapture') or {}).get('tokenSpecificCandidateCount', 'missing')}`, excludedMappingCandidates `{(prediction_triage.get('eventForwardCapture') or {}).get('excludedMappingCandidateCount', 'missing')}`, reviewLeadTokens `{(prediction_triage.get('eventForwardCapture') or {}).get('publicCaptureReviewLeadCount', 'missing')}`, excludedReasons `{(prediction_triage.get('eventForwardCapture') or {}).get('excludedMappingReasonCounts', {})}`, staleContext `{(prediction_triage.get('eventForwardCapture') or {}).get('staleContextTargetCount', 'missing')}`, unrecoverablePreEvent `{(prediction_triage.get('eventForwardCapture') or {}).get('unrecoverablePreEventTargetCount', 'missing')}`, readyForPaper `{(prediction_triage.get('eventForwardCapture') or {}).get('readyForPaper', 'missing')}`, readyForExecution `{(prediction_triage.get('eventForwardCapture') or {}).get('readyForExecution', 'missing')}`
- Prediction category drilldown: snapshotMarkets `{prediction_drilldown.get('snapshotMarketCount', 'missing')}`, viablePairs `{(prediction_drilldown.get('scanDiagnostics') or {}).get('viablePairs', 'missing')}`, nextTests `{[item.get('id') for item in (prediction_drilldown.get('nextTests') or [])[:5]]}`, narrowSnapshots `{[(item.get('category'), item.get('marketCount'), item.get('path')) for item in (prediction_drilldown.get('narrowSnapshots') or [])[:6]]}`, readyForPaper `{prediction_drilldown.get('readyForPaper', 'missing')}`
- Prediction narrow scan: categories `{(prediction_narrow_scan.get('summary') or {}).get('categoryCount', 'missing')}`, watch `{(prediction_narrow_scan.get('summary') or {}).get('watchCandidates', 'missing')}`, paper `{(prediction_narrow_scan.get('summary') or {}).get('paperCandidates', 'missing')}`, viablePairs `{(prediction_narrow_scan.get('summary') or {}).get('viablePairs', 'missing')}`, repairableNearMisses `{(prediction_narrow_scan.get('summary') or {}).get('repairableNearMisses', 'missing')}`, readyForPaper `{prediction_narrow_scan.get('readyForPaper', 'missing')}`, researchOnly `{prediction_narrow_scan.get('researchOnly', 'missing')}`
- Prediction resolved-outcome join: historicalRows `{prediction_resolved_join.get('historicalRowsLoaded', 'missing')}`, statusCounts `{prediction_resolved_join.get('statusCounts', {})}`, joinedResearchOnly `{prediction_resolved_join.get('joinedResearchOnlyCount', 'missing')}`, minSpecificMatches `{prediction_resolved_join.get('minSpecificMatches', 'missing')}`, subjectSpecific `{prediction_resolved_subject_summary(prediction_resolved_join)}`, readyForPaper `{prediction_resolved_join.get('readyForPaper', 'missing')}`
- Prediction resolved-outcome review: status `{prediction_resolved_review['status']}`, decision `{prediction_resolved_review['decision']}`, broadPriorRisk `{prediction_resolved_review['broadPriorRisk']}`, readyForPaper `{prediction_resolved_review['readyForPaper']}`, itemDecisions `{prediction_resolved_review['itemDecisions']}`
- Prediction no-edge ledger: entries `{prediction_no_edge.get('count', 'missing')}`, noEdge `{prediction_no_edge.get('noEdgeCount', 'missing')}`, needsMoreData `{prediction_no_edge.get('needsMoreDataCount', 'missing')}`, promotable `{prediction_no_edge.get('promotableCount', 'missing')}`
- Prediction training: policyFrozen `{prediction_training.get('policyFrozen', 'missing')}`, freezeReason `{prediction_training.get('freezeReason', 'missing')}`, paperCandidates `{(prediction_training.get('selectedEvaluation') or {}).get('paperCount', 'missing')}`
- Polymarket CLOB edge gate: status `{clob_edge_gate.get('status', 'missing')}`, watchResearch `{clob_edge_gate.get('watchResearchGroups', 'missing')}`, readyForPaper `{clob_edge_gate.get('readyForPaper', 'missing')}`, blockerCounts `{clob_edge_gate.get('blockerCounts', {})}`
- Prediction CLOB microstructure audit: decision `{clob_microstructure_summary['decision']}`, readyFeatures `{clob_microstructure_summary['readyFeatureCount']}`, repoFeatures `{clob_microstructure_summary['repoFeatureCount']}`, featureIds `{clob_microstructure_summary['featureIds']}`, readyForPaper `{clob_microstructure_summary['readyForPaper']}`, nextAction `{clob_microstructure_summary['nextAction']}`
- Prediction CLOB spread-compression replay: decision `{clob_spread_compression.get('decision', 'missing')}`, watchResearch `{clob_spread_compression.get('watchResearchCount', 'missing')}`, rows `{clob_spread_compression.get('recordsRead', 'missing')}`, readyForPaper `{clob_spread_compression.get('readyForPaper', 'missing')}`, writesOrders `{clob_spread_compression.get('writesOrders', 'missing')}`
- Prediction CLOB latency/staleness replay: decision `{clob_latency_staleness.get('decision', 'missing')}`, watchResearch `{clob_latency_staleness.get('watchResearchCount', 'missing')}`, rows `{clob_latency_staleness.get('recordsRead', 'missing')}`, readyForPaper `{clob_latency_staleness.get('readyForPaper', 'missing')}`, writesOrders `{clob_latency_staleness.get('writesOrders', 'missing')}`
- Prediction CLOB trade-impact replay: decision `{clob_trade_impact.get('decision', 'missing')}`, watchResearch `{clob_trade_impact.get('watchResearchCount', 'missing')}`, trades `{clob_trade_impact.get('tradeFeatureRows', 'missing')}`, readyForPaper `{clob_trade_impact.get('readyForPaper', 'missing')}`, writesOrders `{clob_trade_impact.get('writesOrders', 'missing')}`
- Polymarket CLOB recorder: status `{clob_recorder.get('status', 'missing')}`, messages `{clob_recorder.get('messages', 'missing')}`, fillableLiveBooks `{clob_live_quality.get('fillableLiveBookCount', 'missing')}/{clob_live_quality.get('selectedAssetCount', 'missing')}`, writesOrders `{clob_recorder.get('writesOrders', 'missing')}`
- Prediction macro/rates evidence: fillability `{macro_rates_summary['fillabilityDecision']}`, executablePublicQuotes `{macro_rates_summary['executablePublicQuotes']}/{macro_rates_summary['marketsInspected']}`, buckets `{macro_rates_summary['bucketCounts']}`, requirements `{macro_rates_summary['requirementsDecision']} pass {macro_rates_summary['requirementsPassCount']} blocked {macro_rates_summary['requirementsBlockedCount']}`, officialLabels `{macro_rates_summary['officialComparableCount']} agreement {macro_rates_summary['officialAgreementRate']}`, replay `{macro_rates_summary['replayDecision']}`, readyForPaper `{macro_rates_summary['readyForPaper']}`, readyForExecution `{macro_rates_summary['readyForExecution']}`
- Prediction event capture: decision `{prediction_event_capture.get('decision', 'missing')}`, mode `{prediction_event_capture.get('mode', 'missing')}`, captureMode `{prediction_event_capture.get('captureMode', 'missing')}`, eventLagReplay `{prediction_event_capture.get('eventLagReplayDecision', 'missing')}`, replayBlockers `{prediction_event_capture.get('eventLagReplayBlockers', prediction_event_replay.get('blockers', []))}`, completeEvents `{prediction_event_capture.get('completeEventCount', 'missing')}`, completeWindows `{prediction_event_capture.get('completeWindowCount', prediction_event_replay.get('completeWindowCount', 'missing'))}`, repricedWindows `{prediction_event_capture.get('repricedWindowCount', 'missing')}`, replayMissing `{prediction_event_capture.get('eventLagReplayMissingReasonCounts', prediction_event_replay.get('missingReasonCounts', {}))}`, targetDecision `{prediction_event_targets.get('decision', 'missing')}`, targetCount `{prediction_event_targets.get('targetCount', 'missing')}`, tokenSpecificCandidates `{prediction_event_capture.get('tokenSpecificCandidateCount', prediction_event_targets.get('tokenSpecificCandidateCount', 'missing'))}`, excludedMappingCandidates `{prediction_event_capture.get('excludedMappingCandidateCount', prediction_event_targets.get('excludedMappingCandidateCount', 'missing'))}`, excludedReasons `{prediction_event_capture.get('excludedMappingReasonCounts', prediction_event_targets.get('excludedMappingReasonCounts', {}))}`, forwardRequired `{(prediction_event_targets.get('forwardCapturePlan') or {}).get('required', 'missing')}`, recorderFillable `{event_capture_live_quality.get('fillableLiveBookCount', 'missing')}/{event_capture_live_quality.get('selectedAssetCount', 'missing')}`, blockers `{prediction_event_capture.get('blockers', [])}`, readyForPaper `{prediction_event_capture.get('readyForPaper', 'missing')}`
- Prediction event mapping: decision `{prediction_event_mapping['mappingDecision']}`, blockers `{prediction_event_mapping['mappingBlockers']}`, ambiguousHeadlines `{prediction_event_mapping['ambiguousHeadlineCount']}`, ambiguousFamilyFanout `{prediction_event_mapping['ambiguousHeadlineFamilyFanoutCount']}`, ambiguousCounterparties `{prediction_event_mapping['ambiguousCounterpartyHeadlineCount']}`, counterpartyFanout `{prediction_event_mapping['ambiguousHeadlineCounterpartyFanoutCount']}`, totalFamilyFanout `{prediction_event_mapping['headlineFamilyFanoutCount']}`, refinement `{prediction_event_mapping['refinementDecision']}`, refinementBlockers `{prediction_event_mapping['refinementBlockers']}`, quality `{prediction_event_mapping['mappingQualityCounts']}`, repairTargets `{prediction_event_mapping['mappingRepairTargetCount']}`, publicCaptureReviewLeads `{prediction_event_mapping['publicCaptureReviewLeadCount']}`, readyForPaper `{prediction_event_mapping['readyForPaper']}`, readyForExecution `{prediction_event_mapping['readyForExecution']}`
- Prediction event mapping fanout sample: `{prediction_event_mapping['headlineFamilyFanoutSample']}`
- Prediction event counterparty fanout sample: `{prediction_event_mapping['headlineCounterpartyFanoutSample']}`
- Prediction event refinement specificity sample: `{prediction_event_mapping['refinementSpecificitySample']}`
- Prediction event mapping repair sample: `{prediction_event_mapping['mappingRepairTargetSample']}`
- Prediction event public capture review sample: `{prediction_event_mapping['publicCaptureReviewLeadSample']}`
- Prediction event timestamp dataset: decision `{prediction_event_timestamps.get('decision', 'missing')}`, candidates `{prediction_event_timestamps.get('candidateCount', 'missing')}`, coverage `{prediction_event_timestamps.get('coverageStatusCounts', {})}`, completeTargets `{prediction_event_timestamps.get('completeWindowTargetCount', 'missing')}`, unrecoverablePre `{prediction_event_timestamps.get('unrecoverablePreEventTargetCount', 'missing')}`, forwardCapture `{prediction_event_timestamps.get('forwardCaptureRequired', 'missing')}`, readyForPaper `{prediction_event_timestamps.get('readyForPaper', 'missing')}`
- Prediction event label/forward-capture gate: decision `{prediction_event_gap.get('decision', 'missing')}`, gapCount `{prediction_event_gap.get('gapCount', 'missing')}`, eventMappedGapCount `{prediction_event_gap.get('eventMappedGapCount', 'missing')}`, eventReplay `{(prediction_event_gap.get('eventLagReplay') or {}).get('decision', 'missing')}`, replayForwardCaptureRequired `{(prediction_event_gap.get('eventLagReplay') or {}).get('forwardCaptureRequired', 'missing')}`, requirementForwardCaptureRequired `{prediction_event_gap.get('eventRequirementForwardCaptureRequired', 'missing')}`, overallForwardCaptureRequired `{prediction_event_gap.get('overallForwardCaptureRequired', 'missing')}`, nextAction `{prediction_event_gap.get('nextAction', 'missing')}`
- Prediction event paper-promotion gate: decision `{prediction_event_paper_gate.get('decision', 'missing')}`, pass `{prediction_event_paper_gate.get('passCount', 'missing')}`, blocked `{prediction_event_paper_gate.get('blockedCount', 'missing')}`, blockedIds `{prediction_event_paper_gate.get('blockedIds', [])}`, readyForPaper `{prediction_event_paper_gate.get('readyForPaper', 'missing')}`, readyForExecution `{prediction_event_paper_gate.get('readyForExecution', 'missing')}`, writesOrders `{prediction_event_paper_gate.get('writesOrders', 'missing')}`, touchesBroker `{prediction_event_paper_gate.get('touchesBroker', 'missing')}`
- Prediction forward-capture command: `{forward_capture_command}`
- Signal quality advisor: rating `{signal_quality.get('overallRating', 'missing')}/10`, blockers `{signal_quality.get('blockers', [])}`, readyForExecution `{signal_quality.get('readyForExecution', 'missing')}`
- Signal quality warnings: `{signal_quality.get('warnings', [])[:8]}`, stale shadow source rows `{signal_quality_shadow_stale_rows(signal_quality)}`
- Signal source truth: decision `{signal_source_truth.get('decision', 'missing')}`, issueCount `{signal_source_truth.get('issueCount', 'missing')}`, readyForExecution `{signal_source_truth.get('readyForExecution', 'missing')}`
- Signal source truth issues: `{signal_source_truth_issue_summary(signal_source_truth)}`
- Whale/COT flow: method `{whale_flow.get('method', 'missing')}`, evidence `{whale_flow.get('evidence_level', 'missing')}`, direction `{whale_flow.get('direction', 'missing')}`, tradable `{whale_flow.get('tradable_signal', 'missing')}`
- Shadow cron read: `OK job output is not evidence by itself; validator now surfaces fallback/no-data/stale shadow signals before they can be mistaken for trade confirmation.`
"""

    hub = HERMES / "BILL-CONTROL-HUB.md"
    daily = DAILY / f"{today}-bill-trading-plan.md"
    canonical_map = HERMES / "BILL-OBSIDIAN-CANONICAL-MAP.md"
    priority_index = VAULT / "Research-Catalog" / "Bill-Resource-Priority-Index.md"
    inventory_summary = write_resource_inventory(now)
    if hub.exists():
        hub.write_text(rewrite_hub_read_first(rewrite_hub_daily_references(hub.read_text(), today), today))
    for link_doc in (canonical_map, priority_index):
        if link_doc.exists():
            link_doc.write_text(rewrite_current_daily_references(link_doc.read_text(), today))

    replace_block(
        hub,
        "BILL_SYNC",
        synced,
        "# Bill Control Hub\n\nThis is the single Obsidian start page for Bill/Hermes financial markets work.\n",
    )

    replace_block(
        daily,
        "BILL_SYNC",
        synced + "\n## Planned Orders For Today\n\nNone approved unless this note is updated manually after broker reconciliation.\n\nMachine-readable control lines:\n\nBILL_ROUTE_APPROVAL: BLOCKED\n\nBROKER_RECONCILIATION: UNKNOWN\n",
        f"# Bill Trading Plan - {today}\n\nParent hub: [[../BILL-CONTROL-HUB]]\n",
    )
    ensure_daily_plan_contract(daily)

    print(json.dumps({
        "updated": now.isoformat(),
        "hub": str(hub),
        "daily": str(daily),
        "inventory": inventory_summary["inventory"],
        "resourceCount": inventory_summary["resourceCount"],
        "outsideObsidian": inventory_summary["outsideObsidian"],
        "decision": order_decision,
        "monitor": monitor.get("status", "missing"),
        "masterBridgeEnabled": master_job.get("enabled", "missing"),
    }, indent=2))


if __name__ == "__main__":
    main()
