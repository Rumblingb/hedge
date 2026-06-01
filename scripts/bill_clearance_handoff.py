#!/usr/bin/env python3
"""Generate the current Bill/Hermes clearance handoff.

The handoff is deliberately read-only: it gathers the current gates, evidence
artifacts, and next commands so another agent/operator can continue without
mistaking research evidence for execution approval.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


HOME = Path.home()
ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
OBSIDIAN = HOME / "Documents" / "memorybrain" / "Agent-Hermes"
DEFAULT_JSON = STATE / "bill-clearance-handoff.latest.json"
DEFAULT_MD = STATE / "bill-clearance-handoff.latest.md"
CLEARANCE_EVIDENCE = STATE / "bill-clearance-evidence.latest.json"
FUTURES_DATA_QUALITY = STATE / "futures-data-quality.latest.json"
FUTURES_DATA_REQUIREMENTS = STATE / "futures-data-requirements.latest.json"
FUTURES_BROKER_PARITY_PLAN = STATE / "futures-broker-parity-plan.latest.json"
FUTURES_NQ_RESEARCH_CYCLE = STATE / "futures-nq-research-cycle.latest.json"
SIGNAL_QUALITY = STATE / "signal-quality-advisor.latest.json"
PREDICTION_MACRO_RATES_REQUIREMENTS = STATE / "prediction-macro-rates-requirements.latest.json"
PREDICTION_MACRO_RATES_CROSS_SOURCE_REPLAY = STATE / "prediction-macro-rates-cross-source-replay.latest.json"
PREDICTION_EVENT_LAG_REQUIREMENTS = STATE / "prediction-event-lag-requirements.latest.json"
PREDICTION_EVENT_MARKET_MAPPING_PLAN = STATE / "prediction-event-market-mapping-plan.latest.json"
PREDICTION_EVENT_LAG_REPLAY = STATE / "prediction-event-lag-replay.latest.json"
PREDICTION_EVENT_CLOB_CAPTURE_TARGETS = STATE / "prediction-event-clob-capture-targets.latest.json"
PREDICTION_EVENT_CAPTURE_CYCLE = STATE / "prediction-event-capture-cycle.latest.json"
PREDICTION_EVENT_LABEL_GAP_PLAN = STATE / "prediction-event-label-gap-plan.latest.json"
PREDICTION_EVENT_PAPER_PROMOTION_GATE = STATE / "prediction-event-paper-promotion-gate.latest.json"
FINNHUB_NEWS = STATE / "finnhub-news.latest.json"
PREDICTION_EVENT_NEWS_RSS = STATE / "prediction-event-news-rss.latest.json"
PREDICTION_LABEL_CARD_AUDIT = STATE / "prediction-label-card-audit.latest.json"
PREDICTION_LABEL_MANIFEST = STATE / "prediction-label-source-manifest.latest.json"
PREDICTION_CLOB_MICROSTRUCTURE = STATE / "prediction-clob-microstructure-feature-audit.latest.json"
GOAL_COMPLETION_AUDIT = STATE / "bill-goal-completion-audit.latest.json"
SOURCE_PACKET_REVIEW = STATE / "bill-source-packet-review.latest.json"
SOURCE_HYGIENE_PLAN = STATE / "bill-source-hygiene-plan.latest.json"
RESEARCH_SEED_TRIAGE = STATE / "research-seed-triage.latest.json"
ALPHA_RESEARCH_DIRECTION = STATE / "alpha-research-direction-audit.latest.json"
STRATEGY_ZOO_AUDIT = STATE / "strategy-zoo-audit.latest.json"
EXECUTION_INTAKE_MANIFEST = STATE / "bill-execution-intake-manifest.latest.json"


def current_utc_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def default_daily_plan_path() -> Path:
    return OBSIDIAN / "daily" / f"{current_utc_date()}-bill-trading-plan.md"


def default_obsidian_md_path() -> Path:
    return OBSIDIAN / f"bill-clearance-handoff-{current_utc_date()}.md"


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def read_text(path: Path) -> str:
    try:
        return path.read_text(errors="ignore")
    except Exception:
        return ""


def extract_line(text: str, prefix: str, default: str = "missing") -> str:
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith(prefix):
            return line.split(":", 1)[1].strip() if ":" in line else line
    return default


def compact(values: Any, limit: int = 6) -> list[Any]:
    if not isinstance(values, list):
        return []
    return values[:limit]


def lane_actions(actions: list[dict[str, Any]], lane: str, limit: int = 6) -> list[dict[str, Any]]:
    return [
        {
            "id": item.get("id"),
            "oneVariable": item.get("oneVariable"),
            "firstCommand": item.get("firstCommand"),
            "commands": compact(item.get("commands"), 10),
        }
        for item in actions
        if item.get("lane") == lane
    ][:limit]


def warning_labels(audit: dict[str, Any]) -> list[str]:
    warnings = audit.get("warnings")
    if not isinstance(warnings, list):
        return []
    return [str(item.get("requirement", item)) for item in warnings if isinstance(item, dict)]


def status_from_artifact(data: dict[str, Any], *keys: str, default: str = "missing") -> Any:
    for key in keys:
        if key in data:
            return data.get(key)
    return default


def futures_data_quality_summary(data: dict[str, Any]) -> dict[str, Any]:
    datasets = data.get("datasets") if isinstance(data.get("datasets"), list) else []
    return {
        "present": bool(data),
        "pass": bool(data.get("pass")),
        "failingDatasets": data.get("failingDatasets") if isinstance(data.get("failingDatasets"), list) else [],
        "datasets": [
            {
                "name": Path(str(item.get("path", ""))).name,
                "rows": item.get("rows"),
                "endTs": item.get("endTs"),
                "pass": bool(item.get("pass")),
                "failingChecks": item.get("failingChecks") if isinstance(item.get("failingChecks"), list) else [],
            }
            for item in datasets
            if isinstance(item, dict)
        ],
    }


def futures_data_requirements_summary(data: dict[str, Any]) -> dict[str, Any]:
    requirements = data.get("requirements") if isinstance(data.get("requirements"), list) else []
    blocked = [item for item in requirements if isinstance(item, dict) and item.get("status") != "pass"]
    passed = [item for item in requirements if isinstance(item, dict) and item.get("status") == "pass"]
    return {
        "present": bool(data),
        "decision": data.get("decision"),
        "passCount": data.get("passCount", len(passed)),
        "blockedCount": data.get("blockedCount", len(blocked)),
        "blockedRequirementIds": [str(item.get("id")) for item in blocked if item.get("id")],
        "passedRequirementIds": [str(item.get("id")) for item in passed if item.get("id")],
        "readyForDemoExpansion": bool(data.get("readyForDemoExpansion")),
        "researchOnly": data.get("researchOnly", True),
    }


def futures_broker_parity_plan_summary(data: dict[str, Any]) -> dict[str, Any]:
    current = data.get("current") if isinstance(data.get("current"), dict) else {}
    return {
        "present": bool(data),
        "decision": data.get("decision"),
        "missingProofs": data.get("missingProofs") if isinstance(data.get("missingProofs"), list) else [],
        "blockedRequirementIds": current.get("blockedRequirementIds") if isinstance(current.get("blockedRequirementIds"), list) else [],
        "dailyRouteBlocked": current.get("dailyRouteBlocked"),
        "dataOnlyReady": current.get("dataOnlyReady"),
        "readyForDemoExpansion": bool(data.get("readyForDemoExpansion")),
        "researchOnly": data.get("researchOnly", True),
    }


def futures_nq_research_cycle_summary(data: dict[str, Any]) -> dict[str, Any]:
    historical = data.get("historical") if isinstance(data.get("historical"), dict) else {}
    current = data.get("current") if isinstance(data.get("current"), dict) else {}
    return {
        "present": bool(data),
        "decision": data.get("decision"),
        "mode": data.get("mode"),
        "bestHistoricalCandidate": historical.get("bestCandidate"),
        "walkforwardDecision": historical.get("walkforwardDecision"),
        "costStressDecision": historical.get("costStressDecision"),
        "currentParityDecision": current.get("currentParityDecision"),
        "dataRequirementsDecision": current.get("dataRequirementsDecision"),
        "blockers": data.get("blockers") if isinstance(data.get("blockers"), list) else [],
        "readyForExecution": bool(data.get("readyForExecution")),
        "readyForDemoExpansion": bool(data.get("readyForDemoExpansion")),
        "researchOnly": data.get("researchOnly", True),
    }


def signal_quality_summary(data: dict[str, Any]) -> dict[str, Any]:
    shadow_rows = data.get("shadowSignalRows") if isinstance(data.get("shadowSignalRows"), list) else []
    return {
        "present": bool(data),
        "decision": data.get("decision"),
        "overallRating": data.get("overallRating"),
        "blockers": compact(data.get("blockers"), 8),
        "warnings": compact(data.get("warnings"), 8),
        "shadowSignals": [
            {
                "name": item.get("name"),
                "direction": item.get("direction"),
                "confidence": item.get("confidence"),
                "shadowOnly": item.get("shadowOnly"),
                "proxyOnly": item.get("proxyOnly"),
                "disconnectedComponents": item.get("disconnectedComponents") if isinstance(item.get("disconnectedComponents"), list) else [],
                "promotedForExecution": item.get("promotedForExecution"),
                "tradableSignal": item.get("tradableSignal"),
            }
            for item in shadow_rows
            if isinstance(item, dict)
        ],
        "readyForExecution": bool(data.get("readyForExecution")),
        "researchOnly": data.get("researchOnly", True),
    }


def requirements_summary(data: dict[str, Any], *, ready_key: str = "readyForPaper") -> dict[str, Any]:
    requirements = data.get("requirements") if isinstance(data.get("requirements"), list) else []
    blocked = [item for item in requirements if isinstance(item, dict) and item.get("status") != "pass"]
    passed = [item for item in requirements if isinstance(item, dict) and item.get("status") == "pass"]
    return {
        "present": bool(data),
        "decision": data.get("decision"),
        "passCount": data.get("passCount", len(passed)),
        "blockedCount": data.get("blockedCount", len(blocked)),
        "blockedRequirementIds": [str(item.get("id")) for item in blocked if item.get("id")],
        "passedRequirementIds": [str(item.get("id")) for item in passed if item.get("id")],
        ready_key: bool(data.get(ready_key)),
        "researchOnly": data.get("researchOnly", True),
    }


def prediction_macro_rates_cross_source_replay_summary(data: dict[str, Any]) -> dict[str, Any]:
    rows = data.get("rows") if isinstance(data.get("rows"), list) else []
    watch = data.get("watchResearch") if isinstance(data.get("watchResearch"), list) else []
    return {
        "present": bool(data),
        "decision": data.get("decision"),
        "rowCount": data.get("rowCount", len(rows)),
        "watchResearchCount": data.get("watchResearchCount", len(watch)),
        "maxSpreadPct": data.get("maxSpreadPct"),
        "minEdgePct": data.get("minEdgePct"),
        "sampleRows": [
            {
                "ticker": item.get("ticker"),
                "meetingDate": item.get("meetingDate"),
                "thresholdUpperBound": item.get("thresholdUpperBound"),
                "kalshiSpreadPct": item.get("kalshiSpreadPct"),
                "yesEdgePctVsAsk": item.get("yesEdgePctVsAsk"),
                "noEdgePctVsNoAsk": item.get("noEdgePctVsNoAsk"),
                "paperStatus": item.get("paperStatus"),
                "blockers": item.get("blockers") if isinstance(item.get("blockers"), list) else [],
            }
            for item in rows[:4]
            if isinstance(item, dict)
        ],
        "readyForPaper": bool(data.get("readyForPaper")),
        "readyForExecution": bool(data.get("readyForExecution")),
        "researchOnly": data.get("researchOnly", True),
    }


def prediction_label_summary(data: dict[str, Any]) -> dict[str, Any]:
    coverage = data.get("coverage") if isinstance(data.get("coverage"), list) else []
    return {
        "present": bool(data),
        "decision": data.get("decision"),
        "watchCount": data.get("watchCount"),
        "historicalRowsLoaded": data.get("historicalRowsLoaded"),
        "labelCardRowsLoaded": data.get("labelCardRowsLoaded"),
        "usableForResearchJoinCount": data.get("usableForResearchJoinCount"),
        "itemsNeedingNewLabelSource": data.get("itemsNeedingNewLabelSource"),
        "statusCounts": data.get("statusCounts") if isinstance(data.get("statusCounts"), dict) else {},
        "coverage": [
            {
                "externalId": item.get("externalId"),
                "category": item.get("category"),
                "subjectKey": item.get("subjectKey"),
                "status": item.get("status"),
                "subjectResolvedCount": item.get("subjectResolvedCount"),
                "familyResolvedCount": item.get("familyResolvedCount"),
                "labelCardSubjectRows": item.get("labelCardSubjectRows"),
                "blockers": item.get("blockers") if isinstance(item.get("blockers"), list) else [],
            }
            for item in coverage[:6]
            if isinstance(item, dict)
        ],
        "readyForPaper": bool(data.get("readyForPaper")),
        "researchOnly": data.get("researchOnly", True),
    }


def prediction_label_card_audit_summary(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "present": bool(data),
        "decision": data.get("decision"),
        "cardCount": data.get("cardCount"),
        "validResolvedLabelRows": data.get("validResolvedLabelRows"),
        "incompleteRows": data.get("incompleteRows"),
        "blockers": data.get("blockers") if isinstance(data.get("blockers"), list) else [],
        "readyForPaper": bool(data.get("readyForPaper")),
        "researchOnly": data.get("researchOnly", True),
    }


def prediction_event_label_gap_summary(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "present": bool(data),
        "decision": data.get("decision"),
        "gapCount": data.get("gapCount"),
        "eventMappedGapCount": data.get("eventMappedGapCount"),
        "labelStatusCounts": data.get("labelStatusCounts") if isinstance(data.get("labelStatusCounts"), dict) else {},
        "blockedRequirements": data.get("blockedRequirements") if isinstance(data.get("blockedRequirements"), list) else [],
        "readyForPaper": bool(data.get("readyForPaper")),
        "researchOnly": data.get("researchOnly", True),
    }


def prediction_event_paper_promotion_gate_summary(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "present": bool(data),
        "decision": data.get("decision"),
        "passCount": data.get("passCount"),
        "blockedCount": data.get("blockedCount"),
        "blockedIds": data.get("blockedIds") if isinstance(data.get("blockedIds"), list) else [],
        "readyForPaper": bool(data.get("readyForPaper")),
        "readyForPaperReview": bool(data.get("readyForPaperReview")),
        "readyForExecution": bool(data.get("readyForExecution")),
        "writesOrders": bool(data.get("writesOrders")),
        "touchesBroker": bool(data.get("touchesBroker")),
        "movesFunds": bool(data.get("movesFunds")),
        "nextAction": data.get("nextAction"),
        "operatorRead": data.get("operatorRead"),
    }


def prediction_news_source_summary(data: dict[str, Any]) -> dict[str, Any]:
    trading_gate = data.get("trading_gate") if isinstance(data.get("trading_gate"), dict) else {}
    fetch_errors = data.get("fetchErrors") if isinstance(data.get("fetchErrors"), dict) else {}
    return {
        "present": bool(data),
        "command": data.get("command"),
        "sourceAdapter": data.get("sourceAdapter"),
        "status": data.get("status"),
        "decision": data.get("decision"),
        "apiKeyStatus": data.get("api_key_status"),
        "dataUsable": bool(data.get("dataUsable")),
        "newsCount": data.get("news_count", data.get("newsCount")),
        "activeAlerts": trading_gate.get("active_alerts"),
        "trendStrategiesAllowed": bool(trading_gate.get("trend_strategies_allowed")),
        "fetchErrors": fetch_errors,
        "readyForPaper": bool(data.get("readyForPaper")),
        "readyForExecution": bool(data.get("readyForExecution")),
        "researchOnly": data.get("researchOnly", True),
    }


def prediction_event_market_mapping_summary(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "present": bool(data),
        "decision": data.get("decision"),
        "candidateCount": data.get("candidateCount"),
        "minimumCandidates": data.get("minimumCandidates"),
        "categories": data.get("categories") if isinstance(data.get("categories"), dict) else {},
        "blockers": data.get("blockers") if isinstance(data.get("blockers"), list) else [],
        "readyForPaper": bool(data.get("readyForPaper")),
        "researchOnly": data.get("researchOnly", True),
    }


def prediction_event_lag_replay_summary(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "present": bool(data),
        "decision": data.get("decision"),
        "completeEventCount": data.get("completeEventCount"),
        "completeWindowCount": data.get("completeWindowCount"),
        "repricedWindowCount": data.get("repricedWindowCount"),
        "blockers": data.get("blockers") if isinstance(data.get("blockers"), list) else [],
        "readyForPaper": bool(data.get("readyForPaper")),
        "readyForExecution": bool(data.get("readyForExecution")),
        "researchOnly": data.get("researchOnly", True),
    }


def prediction_event_clob_capture_summary(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "present": bool(data),
        "decision": data.get("decision"),
        "targetCount": data.get("targetCount"),
        "coverageStatusCounts": data.get("coverageStatusCounts") if isinstance(data.get("coverageStatusCounts"), dict) else {},
        "existingAssetsWithQuotes": data.get("existingAssetsWithQuotes"),
        "blockers": data.get("blockers") if isinstance(data.get("blockers"), list) else [],
        "readyForPaper": bool(data.get("readyForPaper")),
        "readyForExecution": bool(data.get("readyForExecution")),
        "researchOnly": data.get("researchOnly", True),
    }


def prediction_event_capture_cycle_summary(data: dict[str, Any]) -> dict[str, Any]:
    sensitivity = data.get("eventLagSensitivity") if isinstance(data.get("eventLagSensitivity"), dict) else {}
    executed_recorder = data.get("executedRecorder") if isinstance(data.get("executedRecorder"), dict) else {}
    return {
        "present": bool(data),
        "decision": data.get("decision"),
        "mode": data.get("mode"),
        "captureMode": data.get("captureMode"),
        "executedCaptureMode": data.get("executedCaptureMode"),
        "captureCycleEvidencePassed": bool(data.get("captureCycleEvidencePassed")),
        "paperPromotionEvidencePassed": bool(data.get("paperPromotionEvidencePassed")),
        "paperPromotionBlockers": data.get("paperPromotionBlockers") if isinstance(data.get("paperPromotionBlockers"), list) else [],
        "executedRecorder": {
            "present": bool(executed_recorder.get("present")),
            "status": executed_recorder.get("status"),
            "mode": executed_recorder.get("mode"),
            "tokenIds": executed_recorder.get("tokenIds") if isinstance(executed_recorder.get("tokenIds"), list) else [],
            "publicMarketDataOnly": bool(executed_recorder.get("publicMarketDataOnly")),
            "writesOrders": bool(executed_recorder.get("writesOrders")),
            "touchesBroker": bool(executed_recorder.get("touchesBroker")),
        },
        "targetCount": data.get("targetCount"),
        "reviewLeadTargetCount": data.get("reviewLeadTargetCount"),
        "completeEventCount": data.get("completeEventCount"),
        "completeWindowCount": data.get("completeWindowCount"),
        "repricedWindowCount": data.get("repricedWindowCount"),
        "eventLagReplayDecision": data.get("eventLagReplayDecision"),
        "eventLagSensitivity": {
            "present": bool(sensitivity),
            "decision": sensitivity.get("decision"),
            "watchReady": bool(sensitivity.get("watchReady")),
            "watchScenarioCount": sensitivity.get("watchScenarioCount"),
            "bestRepricedWindowCount": sensitivity.get("bestRepricedWindowCount"),
            "readyForPaper": bool(sensitivity.get("readyForPaper")),
            "readyForExecution": bool(sensitivity.get("readyForExecution")),
            "blockers": sensitivity.get("blockers") if isinstance(sensitivity.get("blockers"), list) else [],
        },
        "blockers": data.get("blockers") if isinstance(data.get("blockers"), list) else [],
        "readyForPaper": bool(data.get("readyForPaper")),
        "readyForExecution": bool(data.get("readyForExecution")),
        "researchOnly": data.get("researchOnly", True),
    }


def prediction_clob_summary(data: dict[str, Any]) -> dict[str, Any]:
    rejected = data.get("rejectedBaseline") if isinstance(data.get("rejectedBaseline"), dict) else {}
    capture = data.get("capture") if isinstance(data.get("capture"), dict) else {}
    return {
        "present": bool(data),
        "decision": data.get("decision"),
        "readyFeatureCount": data.get("readyFeatureCount"),
        "rejectedBaselineStatus": rejected.get("status"),
        "rejectedBaselineWatchResearchGroups": rejected.get("watchResearchGroups"),
        "captureRecordsRead": capture.get("recordsRead"),
        "captureAssetsObserved": capture.get("assetsObserved"),
        "medianObservedSpread": capture.get("medianObservedSpread"),
        "researchOnly": data.get("researchOnly", True),
    }


def goal_completion_audit_summary(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "present": bool(data),
        "decision": data.get("decision"),
        "goalComplete": bool(data.get("goalComplete")),
        "checkCount": data.get("checkCount"),
        "passCount": data.get("passCount"),
        "blockedCount": data.get("blockedCount"),
        "blockedIds": data.get("blockedIds") if isinstance(data.get("blockedIds"), list) else [],
        "researchOnly": data.get("researchOnly", True),
        "writesOrders": data.get("writesOrders", False),
        "touchesBroker": data.get("touchesBroker", False),
    }


def source_packet_review_summary(data: dict[str, Any]) -> dict[str, Any]:
    packets = data.get("packets") if isinstance(data.get("packets"), list) else []
    packet_summaries = (
        data.get("packetSummaries")
        if isinstance(data.get("packetSummaries"), list)
        else []
    )
    if not packet_summaries:
        packet_summaries = [
            {
                "id": item.get("id"),
                "lane": item.get("lane"),
                "decision": item.get("decision"),
                "pathCount": item.get("pathCount"),
                "classificationCounts": item.get("classificationCounts") if isinstance(item.get("classificationCounts"), dict) else {},
            }
            for item in packets
            if isinstance(item, dict)
        ]
    return {
        "present": bool(data),
        "decision": data.get("decision"),
        "reviewedPacketCount": data.get("reviewedPacketCount"),
        "missingPackets": data.get("missingPackets") if isinstance(data.get("missingPackets"), list) else [],
        "classificationCounts": data.get("classificationCounts") if isinstance(data.get("classificationCounts"), dict) else {},
        "packetReviewCleared": bool(data.get("packetReviewCleared")),
        "safeToStageAutomatically": bool(data.get("safeToStageAutomatically")),
        "writesOrders": bool(data.get("writesOrders")),
        "touchesBroker": bool(data.get("touchesBroker")),
        "packetSummaries": packet_summaries,
    }


def source_hygiene_plan_summary(data: dict[str, Any]) -> dict[str, Any]:
    queue = data.get("worktreeClearanceQueue") if isinstance(data.get("worktreeClearanceQueue"), list) else []
    risk = data.get("reviewPacketRiskSummary") if isinstance(data.get("reviewPacketRiskSummary"), dict) else {}
    return {
        "present": bool(data),
        "decision": data.get("decision"),
        "sourceHygieneCleared": bool(data.get("sourceHygieneCleared")),
        "sourceClean": bool(data.get("sourceClean")),
        "dirtyStatusCount": int(data.get("dirtyStatusCount") or 0),
        "reviewBacklogCount": int(data.get("reviewBacklogCount") or 0),
        "sourceCleanBlockers": data.get("sourceCleanBlockers") if isinstance(data.get("sourceCleanBlockers"), list) else [],
        "worktreeClearanceQueue": [
            {
                "priority": item.get("priority"),
                "lane": item.get("lane"),
                "dirtyFiles": item.get("dirtyFiles"),
                "action": item.get("action"),
                "requiredEvidence": item.get("requiredEvidence") if isinstance(item.get("requiredEvidence"), list) else [],
                "sampleFiles": item.get("sampleFiles") if isinstance(item.get("sampleFiles"), list) else [],
            }
            for item in queue[:8]
            if isinstance(item, dict)
        ],
        "safeToStageAutomatically": bool(data.get("safeToStageAutomatically")),
        "automaticCleanupAllowed": bool(data.get("automaticCleanupAllowed")),
        "reviewPacketRiskSummary": {
            "packetCount": risk.get("packetCount"),
            "pathCount": risk.get("pathCount"),
            "trackedDiffPathCount": risk.get("trackedDiffPathCount"),
            "untrackedPathCount": risk.get("untrackedPathCount"),
            "modifiedPathCount": risk.get("modifiedPathCount"),
            "statusCounts": risk.get("statusCounts") if isinstance(risk.get("statusCounts"), dict) else {},
            "manualStageEligiblePacketIds": (
                risk.get("manualStageEligiblePacketIds")
                if isinstance(risk.get("manualStageEligiblePacketIds"), list)
                else []
            ),
            "blockedStagePacketIds": (
                risk.get("blockedStagePacketIds")
                if isinstance(risk.get("blockedStagePacketIds"), list)
                else []
            ),
            "operatorRead": risk.get("operatorRead"),
        },
        "writesOrders": bool(data.get("writesOrders")),
        "touchesBroker": bool(data.get("touchesBroker")),
        "movesFunds": bool(data.get("movesFunds")),
        "readyForExecution": bool(data.get("readyForExecution")),
    }


def research_seed_summary(data: dict[str, Any]) -> dict[str, Any]:
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    next_build_queue = data.get("nextBuildQueue") if isinstance(data.get("nextBuildQueue"), list) else []
    rejected = (
        data.get("localBacktraderRejections")
        if isinstance(data.get("localBacktraderRejections"), dict)
        else {}
    )
    return {
        "present": bool(data),
        "totalSeeds": summary.get("totalSeeds"),
        "youtubeSeeds": summary.get("youtubeSeeds"),
        "queuedYouTubeSeeds": summary.get("queuedYouTubeSeeds"),
        "paperSeeds": summary.get("paperSeeds"),
        "machineTestableSeeds": summary.get("machineTestableSeeds"),
        "executableSeeds": summary.get("executableSeeds"),
        "candidateRetestSeeds": summary.get("candidateRetestSeeds"),
        "quarantinedNoEdgeSeeds": summary.get("quarantinedNoEdgeSeeds"),
        "unmappedSeeds": summary.get("unmappedSeeds"),
        "nextBuildQueueCount": len(next_build_queue),
        "localBacktraderRejectedFamilies": sorted(rejected.keys()),
        "readyForExecution": bool(data.get("readyForExecution")),
        "researchOnly": data.get("researchOnly", True),
        "writesOrders": bool(data.get("writesOrders")),
    }


def alpha_research_direction_summary(data: dict[str, Any]) -> dict[str, Any]:
    next_test = data.get("nextOneVariableTest") if isinstance(data.get("nextOneVariableTest"), dict) else {}
    return {
        "present": bool(data),
        "decision": data.get("decision"),
        "queueSafe": bool(data.get("queueSafe")),
        "continueLanes": [
            item.get("id")
            for item in (data.get("continueLanes") if isinstance(data.get("continueLanes"), list) else [])
            if isinstance(item, dict)
        ],
        "retireOrQuarantineLanes": [
            item.get("id")
            for item in (
                data.get("retireOrQuarantineLanes")
                if isinstance(data.get("retireOrQuarantineLanes"), list)
                else []
            )
            if isinstance(item, dict)
        ],
        "nextOneVariableTest": {
            "id": next_test.get("id"),
            "lane": next_test.get("lane"),
            "oneVariable": next_test.get("oneVariable"),
            "command": next_test.get("command"),
            "parallelWatch": next_test.get("parallelWatch") if isinstance(next_test.get("parallelWatch"), dict) else {},
        },
        "missingEvidence": [
            item.get("id")
            for item in (data.get("missingEvidence") if isinstance(data.get("missingEvidence"), list) else [])
            if isinstance(item, dict)
        ],
        "readyForExecution": bool(data.get("readyForExecution")),
        "readyForDemoExpansion": bool(data.get("readyForDemoExpansion")),
        "readyForPaper": bool(data.get("readyForPaper")),
        "researchOnly": data.get("researchOnly", True),
        "writesOrders": bool(data.get("writesOrders")),
        "touchesBroker": bool(data.get("touchesBroker")),
    }


def strategy_zoo_summary(data: dict[str, Any]) -> dict[str, Any]:
    items = data.get("items") if isinstance(data.get("items"), list) else []
    candidates = [
        {
            "strategyId": item.get("strategyId"),
            "classification": item.get("classification"),
            "testable": bool(item.get("testable")),
            "executable": bool(item.get("executable")),
            "bestPropFirmStatus": (
                item.get("evidence", {}).get("bestPropFirmStatus")
                if isinstance(item.get("evidence"), dict)
                else None
            ),
            "blockers": (
                item.get("evidence", {}).get("blockers")
                if isinstance(item.get("evidence"), dict)
                and isinstance(item.get("evidence", {}).get("blockers"), list)
                else []
            ),
        }
        for item in items
        if isinstance(item, dict) and item.get("phase") == "candidate-retest"
    ]
    quarantined = [
        item.get("strategyId")
        for item in items
        if isinstance(item, dict) and item.get("phase") == "quarantine"
    ]
    return {
        "present": bool(data),
        "counts": data.get("counts") if isinstance(data.get("counts"), dict) else {},
        "candidateRetest": candidates,
        "quarantined": quarantined,
        "registeredCount": (data.get("counts") or {}).get("registered") if isinstance(data.get("counts"), dict) else None,
        "readyForExecution": False,
        "researchOnly": True,
        "writesOrders": False,
    }


def active_cron_diff_review_summary(data: dict[str, Any]) -> list[dict[str, Any]]:
    rows = data.get("activeCronDiffReview") if isinstance(data.get("activeCronDiffReview"), list) else []
    return [
        {
            "relativePath": item.get("relativePath"),
            "gitStatus": item.get("gitStatus"),
            "classification": item.get("classification"),
            "firewallId": item.get("firewallId"),
            "firewallPassed": item.get("firewallPassed"),
            "diffStats": item.get("diffStats") if isinstance(item.get("diffStats"), dict) else {},
            "cronNames": [
                ref.get("name")
                for ref in (item.get("activeCronReferences") if isinstance(item.get("activeCronReferences"), list) else [])
                if isinstance(ref, dict) and ref.get("name")
            ],
            "operatorAction": item.get("operatorAction"),
            "safeAutomaticAction": bool(item.get("safeAutomaticAction")),
            "readyForExecution": bool(item.get("readyForExecution")),
            "researchOnly": item.get("researchOnly", True),
            "writesOrders": bool(item.get("writesOrders")),
            "touchesBroker": bool(item.get("touchesBroker")),
        }
        for item in rows[:6]
        if isinstance(item, dict)
    ]


def cron_control_summary(data: dict[str, Any], execution_manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    cron_trust = data.get("cron_trust") if isinstance(data.get("cron_trust"), dict) else {}
    refs = (
        data.get("activeDirtyExecutionLiveScriptReferences")
        if isinstance(data.get("activeDirtyExecutionLiveScriptReferences"), list)
        else cron_trust.get("activeDirtyExecutionLiveScriptReferences")
        if isinstance(cron_trust.get("activeDirtyExecutionLiveScriptReferences"), list)
        else []
    )
    blocking_issues = (
        data.get("blockingIssues")
        if isinstance(data.get("blockingIssues"), list)
        else [
            issue
            for issue in (data.get("issues") if isinstance(data.get("issues"), list) else [])
            if isinstance(issue, dict) and issue.get("severity") in {"P0", "P1"}
        ]
    )
    return {
        "present": bool(data),
        "summary": data.get("summary", data.get("status", "missing")),
        "cronTrustCleared": bool(data.get("cronTrustCleared")),
        "blockingIssueCount": int(data.get("blockingIssueCount") or len(blocking_issues)),
        "activeDirtyExecutionLiveScriptReferenceCount": int(
            data.get("activeDirtyExecutionLiveScriptReferenceCount")
            or cron_trust.get("activeDirtyExecutionLiveScriptReferenceCount")
            or len(refs)
        ),
        "activeDirtyExecutionLiveScriptReferences": [
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "script": item.get("script"),
                "lastStatus": item.get("lastStatus"),
                "sourceClassification": (item.get("source") or {}).get("classification") if isinstance(item.get("source"), dict) else None,
                "firewallId": (item.get("source") or {}).get("firewallId") if isinstance(item.get("source"), dict) else None,
                "requiredAction": (item.get("operatorRemediation") or {}).get("requiredAction") if isinstance(item.get("operatorRemediation"), dict) else None,
                "safeAutomaticAction": (item.get("operatorRemediation") or {}).get("safeAutomaticAction") if isinstance(item.get("operatorRemediation"), dict) else None,
            }
            for item in refs
            if isinstance(item, dict)
        ],
        "blockingIssues": [
            {
                "id": item.get("id"),
                "job": item.get("job"),
                "severity": item.get("severity"),
                "type": item.get("type"),
            }
            for item in blocking_issues
            if isinstance(item, dict)
        ],
        "activeTradingAgentBackedCount": data.get(
            "activeTradingAgentBackedCount",
            cron_trust.get("activeTradingAgentBackedCount"),
        ),
        "noAgentMetadataMismatchCount": data.get(
            "noAgentMetadataMismatchCount",
            cron_trust.get("noAgentMetadataMismatchCount"),
        ),
        "activeCronDiffReview": active_cron_diff_review_summary(execution_manifest or {}),
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
    }


def source_packet_review_markdown(summary: dict[str, Any]) -> list[str]:
    if not summary.get("present"):
        return ["- Source packet review: `missing`"]
    lines = [
        (
            "- Source packet review: decision `{decision}`, reviewed `{reviewed}`, "
            "missing `{missing}`, classes `{classes}`, safeAutoStage `{safe}`, "
            "writesOrders `{writes}`, touchesBroker `{broker}`"
        ).format(
            decision=summary.get("decision"),
            reviewed=summary.get("reviewedPacketCount"),
            missing=summary.get("missingPackets"),
            classes=summary.get("classificationCounts"),
            safe=summary.get("safeToStageAutomatically"),
            writes=summary.get("writesOrders"),
            broker=summary.get("touchesBroker"),
        )
    ]
    for packet in summary.get("packetSummaries") or []:
        if not isinstance(packet, dict):
            continue
        lines.append(
            "  - `{id}` `{lane}`: decision `{decision}`, paths `{paths}`, classes `{classes}`".format(
                id=packet.get("id"),
                lane=packet.get("lane"),
                decision=packet.get("decision"),
                paths=packet.get("pathCount"),
                classes=packet.get("classificationCounts"),
            )
        )
    return lines


def lane_next_actions_markdown(label: str, actions: list[dict[str, Any]]) -> list[str]:
    lines = [f"- {label} lane next actions:"]
    if not actions:
        lines.append("  - none")
        return lines
    for item in actions:
        commands = item.get("commands") if isinstance(item.get("commands"), list) else []
        lines.append(
            "  - `{id}` one-variable `{one_variable}` first `{first}`".format(
                id=item.get("id"),
                one_variable=item.get("oneVariable"),
                first=item.get("firstCommand"),
            )
        )
        for command in commands[:3]:
            lines.append(f"    - `{command}`")
        if len(commands) > 3:
            lines.append(f"    - ... {len(commands) - 3} more command(s)")
    return lines


def source_hygiene_plan_markdown(summary: dict[str, Any]) -> list[str]:
    if not summary.get("present"):
        return ["- Source hygiene plan: `missing`"]
    lines = [
        (
            "- Source hygiene plan: decision `{decision}`, dirty `{dirty}`, backlog `{backlog}`, "
            "cleared `{cleared}`, safeAutoStage `{safe}`, autoCleanup `{cleanup}`"
        ).format(
            decision=summary.get("decision"),
            dirty=summary.get("dirtyStatusCount"),
            backlog=summary.get("reviewBacklogCount"),
            cleared=summary.get("sourceHygieneCleared"),
            safe=summary.get("safeToStageAutomatically"),
            cleanup=summary.get("automaticCleanupAllowed"),
        ),
        f"- Source clean blockers: `{summary.get('sourceCleanBlockers', [])}`",
    ]
    risk = summary.get("reviewPacketRiskSummary") if isinstance(summary.get("reviewPacketRiskSummary"), dict) else {}
    if risk:
        lines.append(
            "- Review packet risk: packets `{packets}`, paths `{paths}`, untracked `{untracked}`, modified `{modified}`, blockedStage `{blocked}`".format(
                packets=risk.get("packetCount"),
                paths=risk.get("pathCount"),
                untracked=risk.get("untrackedPathCount"),
                modified=risk.get("modifiedPathCount"),
                blocked=risk.get("blockedStagePacketIds"),
            )
        )
    lines.extend([
        "- Worktree clearance queue:",
    ])
    queue = summary.get("worktreeClearanceQueue") if isinstance(summary.get("worktreeClearanceQueue"), list) else []
    if queue:
        for item in queue:
            lines.append(
                "  - `{lane}` priority `{priority}` dirty `{dirty}` evidence `{evidence}`".format(
                    lane=item.get("lane"),
                    priority=item.get("priority"),
                    dirty=item.get("dirtyFiles"),
                    evidence=item.get("requiredEvidence", []),
                )
            )
    else:
        lines.append("  - none")
    return lines


def strategy_research_markdown(summary: dict[str, Any]) -> list[str]:
    seed = summary.get("researchSeedTriage") if isinstance(summary.get("researchSeedTriage"), dict) else {}
    direction = summary.get("alphaResearchDirection") if isinstance(summary.get("alphaResearchDirection"), dict) else {}
    zoo = summary.get("strategyZooAudit") if isinstance(summary.get("strategyZooAudit"), dict) else {}
    if not seed.get("present") and not zoo.get("present") and not direction.get("present"):
        return ["- Strategy research: `missing`"]

    lines = []
    if direction.get("present"):
        next_test = direction.get("nextOneVariableTest") if isinstance(direction.get("nextOneVariableTest"), dict) else {}
        lines.append(
            (
                "- Alpha research direction: decision `{decision}`, queueSafe `{safe}`, continue `{cont}`, "
                "retire `{retire}`, nextOneVariable `{next_id}` / `{one_variable}`"
            ).format(
                decision=direction.get("decision"),
                safe=direction.get("queueSafe"),
                cont=direction.get("continueLanes"),
                retire=direction.get("retireOrQuarantineLanes"),
                next_id=next_test.get("id"),
                one_variable=next_test.get("oneVariable"),
            )
        )
    lines.append(
        (
            "- Research seed triage: total `{total}`, youtube `{youtube}`, queuedYT `{queued_youtube}`, papers `{papers}`, "
            "machineTestable `{machine}`, executable `{executable}`, candidateRetest `{candidate}`, "
            "quarantinedNoEdge `{quarantine}`, unmapped `{unmapped}`, nextBuildQueue `{next_build}`"
        ).format(
            total=seed.get("totalSeeds"),
            youtube=seed.get("youtubeSeeds"),
            queued_youtube=seed.get("queuedYouTubeSeeds"),
            papers=seed.get("paperSeeds"),
            machine=seed.get("machineTestableSeeds"),
            executable=seed.get("executableSeeds"),
            candidate=seed.get("candidateRetestSeeds"),
            quarantine=seed.get("quarantinedNoEdgeSeeds"),
            unmapped=seed.get("unmappedSeeds"),
            next_build=seed.get("nextBuildQueueCount"),
        )
    )
    rejected = seed.get("localBacktraderRejectedFamilies")
    if rejected:
        lines.append(f"  - Local Backtrader rejected families: `{', '.join(str(item) for item in rejected)}`")
    lines.append(
        "  - Execution status: ready `{ready}`, researchOnly `{research}`, writesOrders `{writes}`".format(
            ready=seed.get("readyForExecution"),
            research=seed.get("researchOnly"),
            writes=seed.get("writesOrders"),
        )
    )

    counts = zoo.get("counts") if isinstance(zoo.get("counts"), dict) else {}
    lines.append(
        (
            "- Strategy zoo audit: registered `{registered}`, total `{total}`, skeleton `{skeleton}`, "
            "bronze `{bronze}`, quarantined `{quarantine}`"
        ).format(
            registered=zoo.get("registeredCount"),
            total=counts.get("total"),
            skeleton=counts.get("classification:SKELETON"),
            bronze=counts.get("classification:BRONZE"),
            quarantine=counts.get("classification:QUARANTINED"),
        )
    )
    candidates = zoo.get("candidateRetest") if isinstance(zoo.get("candidateRetest"), list) else []
    if candidates:
        lines.append("  - Candidate retest queue:")
        for item in candidates:
            if not isinstance(item, dict):
                continue
            blockers = item.get("blockers") if isinstance(item.get("blockers"), list) else []
            blocker_text = ", ".join(str(blocker) for blocker in blockers[:4]) or "none"
            if len(blockers) > 4:
                blocker_text += f", +{len(blockers) - 4} more"
            lines.append(
                (
                    "    - `{strategy}` class `{classification}` testable `{testable}` executable `{executable}` "
                    "propStatus `{status}` blockers `{blockers}`"
                ).format(
                    strategy=item.get("strategyId"),
                    classification=item.get("classification"),
                    testable=item.get("testable"),
                    executable=item.get("executable"),
                    status=item.get("bestPropFirmStatus"),
                    blockers=blocker_text,
                )
            )
    quarantined = zoo.get("quarantined") if isinstance(zoo.get("quarantined"), list) else []
    if quarantined:
        lines.append(f"  - Quarantined strategies: `{', '.join(str(item) for item in quarantined)}`")
    lines.append(
        "  - Execution status: ready `{ready}`, researchOnly `{research}`, writesOrders `{writes}`".format(
            ready=zoo.get("readyForExecution"),
            research=zoo.get("researchOnly"),
            writes=zoo.get("writesOrders"),
        )
    )
    return lines


def macro_cross_source_replay_markdown(summary: dict[str, Any]) -> list[str]:
    if not summary.get("present"):
        return ["- Prediction macro/rates cross-source replay: `missing`"]
    lines = [
        (
            "- Prediction macro/rates cross-source replay: decision `{decision}`, rows `{rows}`, "
            "watchResearch `{watch}`, readyForPaper `{paper}`, readyForExecution `{execution}`"
        ).format(
            decision=summary.get("decision"),
            rows=summary.get("rowCount"),
            watch=summary.get("watchResearchCount"),
            paper=summary.get("readyForPaper"),
            execution=summary.get("readyForExecution"),
        )
    ]
    sample_rows = summary.get("sampleRows") if isinstance(summary.get("sampleRows"), list) else []
    if sample_rows:
        lines.append("  - Sample blocked rows:")
        for item in sample_rows:
            if not isinstance(item, dict):
                continue
            blockers = item.get("blockers") if isinstance(item.get("blockers"), list) else []
            blocker_text = ", ".join(str(blocker) for blocker in blockers[:4]) or "none"
            lines.append(
                (
                    "    - `{ticker}` `{meeting}` threshold `{threshold}` spread `{spread}` "
                    "yesEdge `{yes_edge}` noEdge `{no_edge}` status `{status}` blockers `{blockers}`"
                ).format(
                    ticker=item.get("ticker"),
                    meeting=item.get("meetingDate"),
                    threshold=item.get("thresholdUpperBound"),
                    spread=item.get("kalshiSpreadPct"),
                    yes_edge=item.get("yesEdgePctVsAsk"),
                    no_edge=item.get("noEdgePctVsNoAsk"),
                    status=item.get("paperStatus"),
                    blockers=blocker_text,
                )
            )
    return lines


def build_handoff(args: argparse.Namespace) -> dict[str, Any]:
    daily_text = read_text(Path(args.daily_plan))
    hub_text = read_text(Path(args.control_hub))
    live = read_json(Path(args.live_readiness))
    fund = read_json(Path(args.fund_os_audit))
    worktree = read_json(Path(args.worktree))
    realtime = read_json(Path(args.realtime_preflight))
    databento = read_json(Path(args.databento_smoke))
    futures = read_json(Path(args.futures_triage))
    prediction = read_json(Path(args.prediction_triage))
    next_actions = read_json(Path(args.next_actions))
    tooling = read_json(Path(args.alpha_tooling))
    hermes_storage = read_json(Path(args.hermes_storage))
    clearance_evidence = read_json(Path(args.clearance_evidence))
    cron = read_json(Path(args.cron_validator))
    futures_data_quality = read_json(Path(args.futures_data_quality))
    futures_data_requirements = read_json(Path(args.futures_data_requirements))
    futures_broker_parity_plan = read_json(Path(args.futures_broker_parity_plan))
    futures_nq_research_cycle = read_json(Path(args.futures_nq_research_cycle))
    signal_quality = read_json(Path(args.signal_quality))
    prediction_macro_rates_requirements = read_json(Path(args.prediction_macro_rates_requirements))
    prediction_macro_rates_cross_source_replay = read_json(Path(args.prediction_macro_rates_cross_source_replay))
    prediction_event_lag_requirements = read_json(Path(args.prediction_event_lag_requirements))
    prediction_event_market_mapping_plan = read_json(Path(args.prediction_event_market_mapping_plan))
    prediction_event_lag_replay = read_json(Path(args.prediction_event_lag_replay))
    prediction_event_clob_capture_targets = read_json(Path(args.prediction_event_clob_capture_targets))
    prediction_event_capture_cycle = read_json(Path(args.prediction_event_capture_cycle))
    prediction_event_label_gap_plan = read_json(Path(args.prediction_event_label_gap_plan))
    prediction_event_paper_promotion_gate = read_json(Path(args.prediction_event_paper_promotion_gate))
    finnhub_news = read_json(Path(args.finnhub_news))
    prediction_event_news_rss = read_json(Path(args.prediction_event_news_rss))
    prediction_label_card_audit = read_json(Path(args.prediction_label_card_audit))
    prediction_label_manifest = read_json(Path(args.prediction_label_manifest))
    prediction_clob_microstructure = read_json(Path(args.prediction_clob_microstructure))
    goal_completion_audit = read_json(Path(args.goal_completion_audit))
    source_packet_review = read_json(Path(args.source_packet_review))
    source_hygiene_plan = read_json(Path(args.source_hygiene_plan))
    research_seed_triage = read_json(Path(args.research_seed_triage))
    alpha_research_direction = read_json(Path(args.alpha_research_direction))
    strategy_zoo_audit = read_json(Path(args.strategy_zoo_audit))
    execution_intake_manifest = read_json(Path(args.execution_intake_manifest))

    live_blockers = compact(live.get("blockers"), 10)
    source_blockers = compact(worktree.get("sourceCleanBlockers"), 10)
    realtime_blockers = compact(realtime.get("blockers"), 10)
    fund_warnings = warning_labels(fund)

    top_actions = []
    for item in compact(next_actions.get("actions"), 20):
        if not isinstance(item, dict):
            continue
        commands = compact(item.get("commands"), 10)
        top_actions.append({
            "id": item.get("id"),
            "lane": item.get("lane"),
            "oneVariable": item.get("oneVariable"),
            "firstCommand": item.get("firstCommand") or (commands[0] if commands else None),
            "commands": commands,
        })

    ready_for_execution = False
    ready_for_demo = bool(live.get("readyForDemoExpansion")) and not live_blockers
    ready_for_live = bool(live.get("readyForLive")) and not live_blockers

    return {
        "command": "bill-clearance-handoff",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "readyForExecution": ready_for_execution,
        "readyForDemoExpansion": ready_for_demo,
        "readyForLive": ready_for_live,
        "decision": "KEEP_EXECUTION_LOCKED",
        "obsidian": {
            "dailyRouteApproval": extract_line(daily_text, "BILL_ROUTE_APPROVAL"),
            "brokerReconciliation": extract_line(daily_text, "BROKER_RECONCILIATION"),
            "dailyMentionsNoOrders": "No new Bill/Hermes orders approved" in daily_text or "No new orders approved" in daily_text,
            "hubModeResearchShadow": "research / shadow / broker-flat monitoring" in hub_text,
        },
        "gates": {
            "liveReadinessBlockers": live_blockers,
            "sourceCleanBlockers": source_blockers,
            "realtimeDataDecision": realtime.get("decision"),
            "realtimeDataReady": realtime.get("readyForExecutionData"),
            "realtimeDataBlockers": realtime_blockers,
            "databentoStatus": databento.get("status"),
            "databentoReadyForExecutionDataProof": databento.get("readyForExecutionDataProof"),
            "cronValidator": cron.get("summary", cron.get("status", "missing")),
            "fundOsTradingReadiness": fund.get("tradingReadinessStatus"),
            "fundOsWarnings": fund_warnings,
        },
        "lanes": {
            "futures": {
                "decision": futures.get("decision"),
                "readyForDemoExpansion": futures.get("readyForDemoExpansion", False),
                "researchDataQuality": futures_data_quality_summary(futures_data_quality),
                "dataRequirements": futures_data_requirements_summary(futures_data_requirements),
                "brokerParityPlan": futures_broker_parity_plan_summary(futures_broker_parity_plan),
                "nqResearchCycle": futures_nq_research_cycle_summary(futures_nq_research_cycle),
                "nextTests": compact(futures.get("nextTests"), 6),
                "laneNextActions": lane_actions(top_actions, "futures"),
            },
            "predictionMarkets": {
                "decision": prediction.get("decision"),
                "readyForPaper": status_from_artifact(prediction, "readyForPaper", default=False),
                "macroRatesRequirements": requirements_summary(prediction_macro_rates_requirements),
                "macroRatesCrossSourceReplay": prediction_macro_rates_cross_source_replay_summary(
                    prediction_macro_rates_cross_source_replay
                ),
                "eventLagRequirements": requirements_summary(prediction_event_lag_requirements),
                "eventMarketMappingPlan": prediction_event_market_mapping_summary(prediction_event_market_mapping_plan),
                "eventLagReplay": prediction_event_lag_replay_summary(prediction_event_lag_replay),
                "eventClobCaptureTargets": prediction_event_clob_capture_summary(prediction_event_clob_capture_targets),
                "eventCaptureCycle": prediction_event_capture_cycle_summary(prediction_event_capture_cycle),
                "eventLabelGapPlan": prediction_event_label_gap_summary(prediction_event_label_gap_plan),
                "eventPaperPromotionGate": prediction_event_paper_promotion_gate_summary(
                    prediction_event_paper_promotion_gate
                ),
                "finnhubNews": prediction_news_source_summary(finnhub_news),
                "eventNewsRss": prediction_news_source_summary(prediction_event_news_rss),
                "labelCardAudit": prediction_label_card_audit_summary(prediction_label_card_audit),
                "labelManifest": prediction_label_summary(prediction_label_manifest),
                "clobMicrostructure": prediction_clob_summary(prediction_clob_microstructure),
                "nextTests": compact(prediction.get("nextTests"), 6),
                "laneNextActions": lane_actions(top_actions, "prediction-markets"),
            },
            "tooling": {
                "status": tooling.get("status"),
                "readyForResearchLoop": tooling.get("readyForResearchLoop"),
                "readyForExecution": tooling.get("readyForExecution"),
            },
            "sourceHygiene": {
                "plan": source_hygiene_plan_summary(source_hygiene_plan),
                "packetReview": source_packet_review_summary(source_packet_review),
            },
            "strategyResearch": {
                "alphaResearchDirection": alpha_research_direction_summary(alpha_research_direction),
                "researchSeedTriage": research_seed_summary(research_seed_triage),
                "strategyZooAudit": strategy_zoo_summary(strategy_zoo_audit),
            },
            "cronControl": cron_control_summary(cron, execution_intake_manifest),
            "storage": {
                "totalSize": hermes_storage.get("totalSize"),
                "archiveCandidateSize": hermes_storage.get("archiveCandidateSize"),
                "movesFiles": hermes_storage.get("movesFiles"),
                "deletesFiles": hermes_storage.get("deletesFiles"),
                "topCandidates": compact(hermes_storage.get("topCandidates"), 4),
                "stateSnapshotsArchive": (
                    (hermes_storage.get("archiveVerification") or {}).get("stateSnapshots")
                    if isinstance(hermes_storage.get("archiveVerification"), dict)
                    else None
                ),
            },
            "clearanceEvidence": {
                "status": clearance_evidence.get("status"),
                "allCommandsPassed": clearance_evidence.get("allCommandsPassed"),
                "failedCommandIds": clearance_evidence.get("failedCommandIds", []),
                "generatedAt": clearance_evidence.get("generatedAt"),
            },
            "goalCompletionAudit": goal_completion_audit_summary(goal_completion_audit),
            "signalQuality": signal_quality_summary(signal_quality),
        },
        "nextActions": top_actions,
        "artifactPaths": {
            "handoffJson": str(DEFAULT_JSON),
            "handoffMarkdown": str(DEFAULT_MD),
            "obsidianMarkdown": str(Path(args.obsidian_md)) if args.obsidian_md else None,
            "liveReadiness": str(Path(args.live_readiness)),
            "fundOsAudit": str(Path(args.fund_os_audit)),
            "worktree": str(Path(args.worktree)),
            "realtimePreflight": str(Path(args.realtime_preflight)),
            "databentoSmoke": str(Path(args.databento_smoke)),
            "goalCompletionAudit": str(Path(args.goal_completion_audit)),
        },
        "hardRules": [
            "No futures demo/live orders while BILL_ROUTE_APPROVAL is BLOCKED.",
            "No prediction-market funding or execution while readyForPaper is false.",
            "LLMs may research and summarize; deterministic code alone may route after gates pass.",
            "Do not clean Hermes or user files destructively without a verified archive and operator approval.",
        ],
    }


def render_markdown(payload: dict[str, Any]) -> str:
    gates = payload["gates"]
    lanes = payload["lanes"]
    obsidian = payload["obsidian"]
    source_packet_lines = source_packet_review_markdown(lanes["sourceHygiene"]["packetReview"])
    cron_control = lanes["cronControl"]
    futures_lane_actions = lane_next_actions_markdown("Futures", lanes["futures"]["laneNextActions"])
    prediction_lane_actions = lane_next_actions_markdown(
        "Prediction", lanes["predictionMarkets"]["laneNextActions"]
    )
    strategy_research_lines = strategy_research_markdown(lanes["strategyResearch"])
    source_hygiene_plan_lines = source_hygiene_plan_markdown(lanes["sourceHygiene"]["plan"])
    macro_replay_lines = macro_cross_source_replay_markdown(
        lanes["predictionMarkets"]["macroRatesCrossSourceReplay"]
    )
    generated_date = str(payload.get("generatedAt") or current_utc_date())[:10]
    lines = [
        f"# Bill/Hermes Clearance Handoff - {generated_date}",
        "",
        f"Generated: `{payload['generatedAt']}`",
        "",
        "## Decision",
        "",
        f"- Decision: `{payload['decision']}`",
        f"- Ready for execution: `{payload['readyForExecution']}`",
        f"- Ready for demo expansion: `{payload['readyForDemoExpansion']}`",
        f"- Ready for live: `{payload['readyForLive']}`",
        f"- Daily route approval: `{obsidian['dailyRouteApproval']}`",
        f"- Broker reconciliation: `{obsidian['brokerReconciliation']}`",
        "",
        "## Current Blockers",
        "",
    ]
    for blocker in gates["liveReadinessBlockers"] or ["none"]:
        lines.append(f"- {blocker}")
    lines.extend([
        "",
        "## Data And Execution",
        "",
        f"- Realtime data decision: `{gates['realtimeDataDecision']}`",
        f"- Realtime data ready: `{gates['realtimeDataReady']}`",
        f"- Databento smoke: `{gates['databentoStatus']}`",
        f"- Databento execution-data proof: `{gates['databentoReadyForExecutionDataProof']}`",
        f"- Futures research data quality: `{lanes['futures']['researchDataQuality']}`",
        f"- Futures data requirements: `{lanes['futures']['dataRequirements']}`",
        f"- Futures broker parity plan: `{lanes['futures']['brokerParityPlan']}`",
        f"- Futures NQ research cycle: `{lanes['futures']['nqResearchCycle']}`",
        f"- Signal quality: `{lanes['signalQuality']}`",
        f"- Cron validator: `{gates['cronValidator']}`",
        (
            "- Cron control: trustCleared `{cleared}`, blockers `{blockers}`, "
            "activeDirtyRefs `{active}`, activeTradingAgentBacked `{agents}`"
        ).format(
            cleared=cron_control.get("cronTrustCleared"),
            blockers=cron_control.get("blockingIssueCount"),
            active=cron_control.get("activeDirtyExecutionLiveScriptReferenceCount"),
            agents=cron_control.get("activeTradingAgentBackedCount"),
        ),
        "- Active dirty execution cron refs:",
    ])
    if cron_control.get("activeDirtyExecutionLiveScriptReferences"):
        for ref in cron_control.get("activeDirtyExecutionLiveScriptReferences") or []:
            lines.append(
                "  - `{name}` script `{script}`: `{required}`".format(
                    name=ref.get("name"),
                    script=ref.get("script"),
                    required=ref.get("requiredAction"),
                )
            )
    else:
        lines.append("  - none")
    lines.append("- Active cron diff review:")
    if cron_control.get("activeCronDiffReview"):
        for item in cron_control.get("activeCronDiffReview") or []:
            lines.append(
                (
                    "  - `{path}` crons `{crons}` diff `{diff}` firewall `{firewall}` passed `{passed}` "
                    "ready `{ready}` safeAuto `{safe}`"
                ).format(
                    path=item.get("relativePath"),
                    crons=item.get("cronNames"),
                    diff=item.get("diffStats"),
                    firewall=item.get("firewallId"),
                    passed=item.get("firewallPassed"),
                    ready=item.get("readyForExecution"),
                    safe=item.get("safeAutomaticAction"),
                )
            )
    else:
        lines.append("  - none")
    lines.extend([
        "",
        "## Research Lanes",
        "",
        f"- Futures: `{lanes['futures']['decision']}`",
        *futures_lane_actions,
        f"- Prediction markets: `{lanes['predictionMarkets']['decision']}`",
        *prediction_lane_actions,
        f"- Prediction macro/rates requirements: `{lanes['predictionMarkets']['macroRatesRequirements']}`",
        *macro_replay_lines,
        f"- Prediction event-lag requirements: `{lanes['predictionMarkets']['eventLagRequirements']}`",
        f"- Prediction event-market mapping plan: `{lanes['predictionMarkets']['eventMarketMappingPlan']}`",
        f"- Prediction event-lag replay: `{lanes['predictionMarkets']['eventLagReplay']}`",
        f"- Prediction event CLOB capture targets: `{lanes['predictionMarkets']['eventClobCaptureTargets']}`",
        f"- Prediction event capture cycle: `{lanes['predictionMarkets']['eventCaptureCycle']}`",
        f"- Prediction event-lag sensitivity: `{lanes['predictionMarkets']['eventCaptureCycle'].get('eventLagSensitivity')}`",
        f"- Prediction event label gaps: `{lanes['predictionMarkets']['eventLabelGapPlan']}`",
        f"- Prediction event paper-promotion gate: `{lanes['predictionMarkets']['eventPaperPromotionGate']}`",
        f"- Prediction Finnhub news source: `{lanes['predictionMarkets']['finnhubNews']}`",
        f"- Prediction RSS news source: `{lanes['predictionMarkets']['eventNewsRss']}`",
        f"- Prediction label card audit: `{lanes['predictionMarkets']['labelCardAudit']}`",
        f"- Prediction label manifest: `{lanes['predictionMarkets']['labelManifest']}`",
        f"- Prediction CLOB microstructure: `{lanes['predictionMarkets']['clobMicrostructure']}`",
        f"- Alpha tooling: `{lanes['tooling']['status']}`, research loop ready `{lanes['tooling']['readyForResearchLoop']}`",
        *strategy_research_lines,
        *source_hygiene_plan_lines,
        *source_packet_lines,
        f"- Hermes storage: `{lanes['storage']['archiveCandidateSize']}` archive candidates; moves `{lanes['storage']['movesFiles']}`, deletes `{lanes['storage']['deletesFiles']}`; stateSnapshotsArchive `{lanes['storage'].get('stateSnapshotsArchive')}`",
        f"- Clearance evidence: `{lanes['clearanceEvidence']['status']}`, all commands passed `{lanes['clearanceEvidence']['allCommandsPassed']}`",
        f"- Goal completion audit: `{lanes['goalCompletionAudit']}`",
        "",
        "## Next Actions",
        "",
    ])
    for item in payload["nextActions"]:
        commands = "; ".join(str(command) for command in item.get("commands", []))
        lines.append(f"- `{item.get('id')}` ({item.get('lane')}): first `{item.get('firstCommand')}`; {commands}")
    lines.extend([
        "",
        "## Hard Rules",
        "",
    ])
    for rule in payload["hardRules"]:
        lines.append(f"- {rule}")
    lines.append("")
    return "\n".join(lines)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    p.add_argument("--daily-plan", default=str(default_daily_plan_path()))
    p.add_argument("--control-hub", default=str(OBSIDIAN / "BILL-CONTROL-HUB.md"))
    p.add_argument("--live-readiness", default=str(STATE / "live-readiness-gate.latest.json"))
    p.add_argument("--fund-os-audit", default=str(STATE / "bill-fund-os-completion-audit.latest.json"))
    p.add_argument("--worktree", default=str(STATE / "worktree-consolidation.latest.json"))
    p.add_argument("--realtime-preflight", default=str(STATE / "realtime-data-preflight.latest.json"))
    p.add_argument("--databento-smoke", default=str(STATE / "databento-realtime-smoke.latest.json"))
    p.add_argument("--futures-triage", default=str(STATE / "futures-evidence-triage.latest.json"))
    p.add_argument("--prediction-triage", default=str(STATE / "prediction-evidence-triage.latest.json"))
    p.add_argument("--next-actions", default=str(STATE / "bill-next-research-actions.latest.json"))
    p.add_argument("--alpha-tooling", default=str(STATE / "alpha-research-tooling-check.latest.json"))
    p.add_argument("--hermes-storage", default=str(STATE / "hermes-storage-audit.latest.json"))
    p.add_argument("--clearance-evidence", default=str(CLEARANCE_EVIDENCE))
    p.add_argument("--futures-data-quality", default=str(FUTURES_DATA_QUALITY))
    p.add_argument("--futures-data-requirements", default=str(FUTURES_DATA_REQUIREMENTS))
    p.add_argument("--futures-broker-parity-plan", default=str(FUTURES_BROKER_PARITY_PLAN))
    p.add_argument("--futures-nq-research-cycle", default=str(FUTURES_NQ_RESEARCH_CYCLE))
    p.add_argument("--signal-quality", default=str(SIGNAL_QUALITY))
    p.add_argument("--prediction-macro-rates-requirements", default=str(PREDICTION_MACRO_RATES_REQUIREMENTS))
    p.add_argument("--prediction-macro-rates-cross-source-replay", default=str(PREDICTION_MACRO_RATES_CROSS_SOURCE_REPLAY))
    p.add_argument("--prediction-event-lag-requirements", default=str(PREDICTION_EVENT_LAG_REQUIREMENTS))
    p.add_argument("--prediction-event-market-mapping-plan", default=str(PREDICTION_EVENT_MARKET_MAPPING_PLAN))
    p.add_argument("--prediction-event-lag-replay", default=str(PREDICTION_EVENT_LAG_REPLAY))
    p.add_argument("--prediction-event-clob-capture-targets", default=str(PREDICTION_EVENT_CLOB_CAPTURE_TARGETS))
    p.add_argument("--prediction-event-capture-cycle", default=str(PREDICTION_EVENT_CAPTURE_CYCLE))
    p.add_argument("--prediction-event-label-gap-plan", default=str(PREDICTION_EVENT_LABEL_GAP_PLAN))
    p.add_argument("--prediction-event-paper-promotion-gate", default=str(PREDICTION_EVENT_PAPER_PROMOTION_GATE))
    p.add_argument("--finnhub-news", default=str(FINNHUB_NEWS))
    p.add_argument("--prediction-event-news-rss", default=str(PREDICTION_EVENT_NEWS_RSS))
    p.add_argument("--prediction-label-card-audit", default=str(PREDICTION_LABEL_CARD_AUDIT))
    p.add_argument("--prediction-label-manifest", default=str(PREDICTION_LABEL_MANIFEST))
    p.add_argument("--prediction-clob-microstructure", default=str(PREDICTION_CLOB_MICROSTRUCTURE))
    p.add_argument("--goal-completion-audit", default=str(GOAL_COMPLETION_AUDIT))
    p.add_argument("--source-packet-review", default=str(SOURCE_PACKET_REVIEW))
    p.add_argument("--source-hygiene-plan", default=str(SOURCE_HYGIENE_PLAN))
    p.add_argument("--research-seed-triage", default=str(RESEARCH_SEED_TRIAGE))
    p.add_argument("--alpha-research-direction", default=str(ALPHA_RESEARCH_DIRECTION))
    p.add_argument("--strategy-zoo-audit", default=str(STRATEGY_ZOO_AUDIT))
    p.add_argument("--cron-validator", default=str(STATE / "cron-state-validator.latest.json"))
    p.add_argument("--execution-intake-manifest", default=str(EXECUTION_INTAKE_MANIFEST))
    p.add_argument("--json-output", default=str(DEFAULT_JSON))
    p.add_argument("--markdown-output", default=str(DEFAULT_MD))
    p.add_argument("--obsidian-md", default=str(default_obsidian_md_path()))
    return p


def main() -> int:
    args = parser().parse_args()
    payload = build_handoff(args)
    markdown = render_markdown(payload)

    json_output = Path(args.json_output)
    markdown_output = Path(args.markdown_output)
    json_output.parent.mkdir(parents=True, exist_ok=True)
    markdown_output.parent.mkdir(parents=True, exist_ok=True)
    json_output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    markdown_output.write_text(markdown)
    if args.obsidian_md:
        obsidian_output = Path(args.obsidian_md)
        obsidian_output.parent.mkdir(parents=True, exist_ok=True)
        obsidian_output.write_text(markdown)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
