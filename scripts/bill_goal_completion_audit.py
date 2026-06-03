#!/usr/bin/env python3
"""Audit the active Bill/Hermes clearance goal against real artifacts.

This is a read-only completion guard. It prevents agents from treating effort,
passing helper tests, or an attractive queue as proof that Bill/Hermes is
demo/live ready. It never touches broker APIs, funding, orders, or execution
routing.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
VAULT = Path.home() / "Documents" / "memorybrain"
HERMES = VAULT / "Agent-Hermes"
OUT = STATE / "bill-goal-completion-audit.latest.json"
TRADING_TIMEZONE = ZoneInfo(os.environ.get("BILL_TRADING_TIMEZONE", "Europe/London"))


OBJECTIVE = (
    "Get Bill/Hermes closer to a cleared research/demo-ready posture by fixing "
    "current blockers where safe, installing or wiring necessary alpha research "
    "tooling, and focusing the next build/research loop on futures and prediction "
    "markets while keeping execution locked until evidence gates pass."
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def current_utc_date() -> str:
    return datetime.now(timezone.utc).astimezone(TRADING_TIMEZONE).date().isoformat()


def default_daily_path() -> Path:
    return HERMES / "daily" / f"{current_utc_date()}-bill-trading-plan.md"


DAILY = default_daily_path()


def default_markdown_path() -> Path:
    return HERMES / f"bill-goal-completion-audit-{current_utc_date()}.md"


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


def actions_by_id(actions: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = actions.get("actions") if isinstance(actions.get("actions"), list) else []
    return {
        str(row.get("id")): row
        for row in rows
        if isinstance(row, dict) and row.get("id")
    }


def broker_touch_is_none_or_readonly_market_data(payload: dict[str, Any]) -> bool:
    if payload.get("touchesBroker") is not True:
        return payload.get("touchesBroker") is False
    return payload.get("brokerTouchMode") == "read-only-market-data"


def check(
    *,
    item_id: str,
    requirement: str,
    status: str,
    evidence: dict[str, Any],
    artifact: str,
    blocker: str | None = None,
) -> dict[str, Any]:
    row = {
        "id": item_id,
        "requirement": requirement,
        "status": status,
        "artifact": artifact,
        "evidence": evidence,
    }
    if blocker:
        row["blocker"] = blocker
    return row


def prompt_artifact_check(
    *,
    item_id: str,
    prompt_requirement: str,
    artifacts: list[str],
    status: str,
    evidence: dict[str, Any],
    uncovered: list[str] | None = None,
) -> dict[str, Any]:
    row = {
        "id": item_id,
        "promptRequirement": prompt_requirement,
        "artifacts": artifacts,
        "status": status,
        "evidence": evidence,
    }
    if uncovered:
        row["uncovered"] = uncovered
    return row


def has_command(action: dict[str, Any], fragment: str) -> bool:
    commands = action.get("commands") if isinstance(action.get("commands"), list) else []
    return any(fragment in str(command) for command in commands)


def build_audit(
    *,
    handoff: dict[str, Any],
    tooling: dict[str, Any],
    alpha_direction: dict[str, Any] | None = None,
    next_actions: dict[str, Any],
    futures_cycle: dict[str, Any],
    futures_requirements: dict[str, Any],
    futures_broker_parity: dict[str, Any] | None = None,
    prediction_capture: dict[str, Any],
    prediction_market_mapping: dict[str, Any] | None = None,
    prediction_mapping_refinement: dict[str, Any] | None = None,
    prediction_event_lag_manual_review: dict[str, Any] | None = None,
    prediction_paper_promotion_gate: dict[str, Any] | None = None,
    realtime_preflight: dict[str, Any],
    databento_smoke: dict[str, Any],
    worktree: dict[str, Any],
    source_intake: dict[str, Any] | None = None,
    data_intake: dict[str, Any] | None = None,
    execution_intake: dict[str, Any] | None = None,
    signal_quality: dict[str, Any] | None = None,
    signal_source_truth: dict[str, Any] | None = None,
    storage: dict[str, Any],
    clearance_evidence: dict[str, Any],
    stale_claim_guard: dict[str, Any] | None = None,
    daily_text: str = "",
    source_hygiene: dict[str, Any] | None = None,
    open_session_data_proof: dict[str, Any] | None = None,
    source_packet_review: dict[str, Any] | None = None,
    sibling_worktree_intake: dict[str, Any] | None = None,
    cron_validator: dict[str, Any] | None = None,
    codex_automation: dict[str, Any] | None = None,
    runtime_architecture: dict[str, Any] | None = None,
    seed_triage: dict[str, Any] | None = None,
    resource_inventory_text: str = "",
) -> dict[str, Any]:
    source_intake = source_intake or {}
    alpha_direction = alpha_direction or {}
    futures_broker_parity = futures_broker_parity or {}
    prediction_market_mapping = prediction_market_mapping or {}
    prediction_mapping_refinement = prediction_mapping_refinement or {}
    prediction_event_lag_manual_review = prediction_event_lag_manual_review or {}
    prediction_paper_promotion_gate = prediction_paper_promotion_gate or {}
    data_intake = data_intake or {}
    execution_intake = execution_intake or {}
    signal_quality = signal_quality or {}
    signal_source_truth = signal_source_truth or {}
    stale_claim_guard = stale_claim_guard or {}
    source_hygiene = source_hygiene or {}
    open_session_data_proof = open_session_data_proof or {}
    source_packet_review = source_packet_review or {}
    sibling_worktree_intake = sibling_worktree_intake or {}
    cron_validator = cron_validator or {}
    codex_automation = codex_automation or {}
    runtime_architecture = runtime_architecture or {}
    seed_triage = seed_triage or {}
    resource_inventory_text = resource_inventory_text or ""
    source_review_backlog_count = source_intake.get("reviewBacklogCount")
    if not isinstance(source_review_backlog_count, int):
        source_review_backlog_count = source_hygiene.get("reviewBacklogCount")
    action_map = actions_by_id(next_actions)
    futures_action = action_map.get("futures-paid-nq-1m-session-structure-oos", {})
    paper_action = action_map.get("futures-paper-source-one-variable-tests", {})
    prediction_action = action_map.get("prediction-news-first-event-lag-study", {})
    control_action = action_map.get("control-plane-clearance-before-demo", {})

    execution_locked = (
        handoff.get("decision") == "KEEP_EXECUTION_LOCKED"
        and handoff.get("readyForExecution") is False
        and handoff.get("readyForDemoExpansion") is False
        and handoff.get("readyForLive") is False
        and handoff.get("writesOrders") is False
        and handoff.get("touchesBroker") is False
    )
    daily_blocked = (
        "No new Bill/Hermes orders approved" in daily_text
        and "BILL_ROUTE_APPROVAL: BLOCKED" in daily_text
    )
    queue_safe = (
        next_actions.get("researchOnly") is True
        and next_actions.get("writesOrders") is False
        and next_actions.get("touchesBroker") is False
        and next_actions.get("readyForExecution") is False
    )
    prediction_recorder_wired = has_command(
        prediction_action,
        "prediction-event-capture-cycle -- --run-recorder --duration-sec 900 --max-assets 15",
    )
    latest_recorder = (
        prediction_capture.get("latestRecorder")
        if isinstance(prediction_capture.get("latestRecorder"), dict)
        else {}
    )
    live_quality = (
        latest_recorder.get("liveQualityDiagnostics")
        if isinstance(latest_recorder.get("liveQualityDiagnostics"), dict)
        else {}
    )
    prediction_capture_safe = (
        prediction_capture.get("researchOnly") is True
        and prediction_capture.get("writesOrders") is False
        and prediction_capture.get("touchesBroker") is False
        and prediction_capture.get("readyForExecution") is False
        and prediction_capture.get("readyForPaper") is False
        and prediction_capture.get("paperPromotionEvidencePassed") is False
        and latest_recorder.get("writesOrders") is False
        and live_quality.get("readyForPaperEvidence") is False
    )
    event_lag_sensitivity = (
        prediction_capture.get("eventLagSensitivity")
        if isinstance(prediction_capture.get("eventLagSensitivity"), dict)
        else {}
    )
    event_lag_sensitivity_summary = {
        "present": bool(event_lag_sensitivity),
        "decision": event_lag_sensitivity.get("decision"),
        "watchReady": bool(event_lag_sensitivity.get("watchReady")),
        "watchScenarioCount": event_lag_sensitivity.get("watchScenarioCount"),
        "bestRepricedWindowCount": event_lag_sensitivity.get("bestRepricedWindowCount"),
        "readyForPaper": bool(event_lag_sensitivity.get("readyForPaper")),
        "readyForExecution": bool(event_lag_sensitivity.get("readyForExecution")),
        "blockers": (
            event_lag_sensitivity.get("blockers")
            if isinstance(event_lag_sensitivity.get("blockers"), list)
            else []
        ),
    }
    event_lag_watch_review = (
        prediction_capture.get("eventLagWatchReview")
        if isinstance(prediction_capture.get("eventLagWatchReview"), dict)
        else {}
    )
    event_lag_watch_review_summary = {
        "present": bool(event_lag_watch_review),
        "decision": event_lag_watch_review.get("decision"),
        "watchReady": bool(event_lag_watch_review.get("watchReady")),
        "repricedWatchWindowCount": event_lag_watch_review.get("repricedWatchWindowCount"),
        "readyForPaper": bool(event_lag_watch_review.get("readyForPaper")),
        "readyForExecution": bool(event_lag_watch_review.get("readyForExecution")),
        "blockers": (
            event_lag_watch_review.get("blockers")
            if isinstance(event_lag_watch_review.get("blockers"), list)
            else []
        ),
    }
    event_lag_manual_review_summary = {
        "present": bool(prediction_event_lag_manual_review),
        "decision": prediction_event_lag_manual_review.get("decision"),
        "reviewedWindowCount": prediction_event_lag_manual_review.get("reviewedWindowCount"),
        "decisionCounts": (
            prediction_event_lag_manual_review.get("decisionCounts")
            if isinstance(prediction_event_lag_manual_review.get("decisionCounts"), dict)
            else {}
        ),
        "readyForPaper": bool(prediction_event_lag_manual_review.get("readyForPaper")),
        "readyForExecution": bool(prediction_event_lag_manual_review.get("readyForExecution")),
        "blockers": (
            prediction_event_lag_manual_review.get("blockers")
            if isinstance(prediction_event_lag_manual_review.get("blockers"), list)
            else []
        ),
    }
    prediction_mapping_refinement_summary = {
        "present": bool(prediction_mapping_refinement),
        "decision": prediction_mapping_refinement.get("decision"),
        "readyForPaper": bool(prediction_mapping_refinement.get("readyForPaper")),
        "readyForExecution": bool(prediction_mapping_refinement.get("readyForExecution")),
        "readyForForwardCapture": bool(prediction_mapping_refinement.get("readyForForwardCapture")),
        "reviewedWindowCount": prediction_mapping_refinement.get("reviewedWindowCount"),
        "mappingCandidateCount": prediction_mapping_refinement.get("mappingCandidateCount"),
        "mappingRepairTargetCount": prediction_mapping_refinement.get("mappingRepairTargetCount"),
        "mappingRepairTargetSample": [
            {
                "headline": item.get("headline"),
                "candidateCount": item.get("candidateCount"),
                "candidateFamilyCounts": item.get("candidateFamilyCounts"),
                "candidateCounterpartyCounts": item.get("candidateCounterpartyCounts"),
                "candidateDeadlineCounts": item.get("candidateDeadlineCounts"),
                "blockedUntil": item.get("blockedUntil"),
            }
            for item in (
                prediction_mapping_refinement.get("mappingRepairTargets")
                if isinstance(prediction_mapping_refinement.get("mappingRepairTargets"), list)
                else []
            )[:2]
            if isinstance(item, dict)
        ],
        "publicCaptureReviewLeadCount": prediction_mapping_refinement.get("publicCaptureReviewLeadCount"),
        "publicCaptureReviewLeadSample": [
            {
                "question": item.get("question"),
                "counterparty": item.get("counterparty"),
                "deadlineText": item.get("deadlineText"),
                "status": item.get("status"),
                "spread": item.get("spread"),
                "reviewUseOnly": item.get("reviewUseOnly"),
            }
            for item in (
                prediction_mapping_refinement.get("publicCaptureReviewLeads")
                if isinstance(prediction_mapping_refinement.get("publicCaptureReviewLeads"), list)
                else []
            )[:3]
            if isinstance(item, dict)
        ],
        "deadlineLadderCaptureCandidateCount": prediction_mapping_refinement.get("deadlineLadderCaptureCandidateCount"),
        "deadlineLadderCaptureCandidateSample": [
            {
                "question": item.get("question"),
                "deadlineText": item.get("deadlineText"),
                "deadlineDate": item.get("deadlineDate"),
                "spreadPct": item.get("spreadPct"),
                "topBookDepth": item.get("topBookDepth"),
                "reviewUseOnly": item.get("reviewUseOnly"),
            }
            for item in (
                prediction_mapping_refinement.get("deadlineLadderCaptureCandidates")
                if isinstance(prediction_mapping_refinement.get("deadlineLadderCaptureCandidates"), list)
                else []
            )[:4]
            if isinstance(item, dict)
        ],
        "mappingQualityCounts": (
            prediction_mapping_refinement.get("mappingQualityCounts")
            if isinstance(prediction_mapping_refinement.get("mappingQualityCounts"), dict)
            else {}
        ),
        "blockers": (
            prediction_mapping_refinement.get("blockers")
            if isinstance(prediction_mapping_refinement.get("blockers"), list)
            else []
        ),
    }
    prediction_market_mapping_summary = {
        "present": bool(prediction_market_mapping),
        "decision": prediction_market_mapping.get("decision"),
        "candidateCount": prediction_market_mapping.get("candidateCount"),
        "ambiguousHeadlineCount": prediction_market_mapping.get("ambiguousHeadlineCount"),
        "ambiguousCounterpartyHeadlineCount": prediction_market_mapping.get("ambiguousCounterpartyHeadlineCount"),
        "blockers": (
            prediction_market_mapping.get("blockers")
            if isinstance(prediction_market_mapping.get("blockers"), list)
            else []
        ),
        "headlineFamilyFanoutCount": len(prediction_market_mapping.get("headlineFamilyFanout") or [])
        if isinstance(prediction_market_mapping.get("headlineFamilyFanout"), list)
        else 0,
        "ambiguousHeadlineFamilyFanoutCount": len(prediction_market_mapping.get("ambiguousHeadlineFamilyFanout") or [])
        if isinstance(prediction_market_mapping.get("ambiguousHeadlineFamilyFanout"), list)
        else len([
            item
            for item in (prediction_market_mapping.get("headlineFamilyFanout") or [])
            if isinstance(item, dict) and item.get("ambiguous") is True
        ]),
        "ambiguousHeadlineCounterpartyFanoutCount": len(prediction_market_mapping.get("ambiguousHeadlineCounterpartyFanout") or [])
            if isinstance(prediction_market_mapping.get("ambiguousHeadlineCounterpartyFanout"), list)
            else len([
                item
                for item in (prediction_market_mapping.get("headlineFamilyFanout") or [])
                if isinstance(item, dict) and item.get("counterpartyAmbiguous") is True
            ]),
    }
    prediction_mapping_exclusion_summary = {
        "targetCount": prediction_capture.get("targetCount"),
        "tokenSpecificCandidateCount": prediction_capture.get("tokenSpecificCandidateCount"),
        "excludedMappingCandidateCount": prediction_capture.get("excludedMappingCandidateCount"),
        "excludedMappingReasonCounts": (
            prediction_capture.get("excludedMappingReasonCounts")
            if isinstance(prediction_capture.get("excludedMappingReasonCounts"), dict)
            else {}
        ),
        "mappingBlockers": (
            prediction_capture.get("mappingBlockers")
            if isinstance(prediction_capture.get("mappingBlockers"), list)
            else []
        ),
    }
    capture_cycle_watch_evidence = (
        prediction_capture.get("captureCycleEvidencePassed") is True
        and bool(prediction_capture.get("eventLagResearchWatchReady"))
        and int(prediction_capture.get("completeEventCount") or 0) > 0
        and int(prediction_capture.get("repricedWindowCount") or 0) > 0
    )
    if prediction_paper_promotion_gate.get("decision") == "research-only-paper-promotion-blocked":
        prediction_paper_blocker = "prediction event-lag watch evidence exists, but the explicit paper-promotion gate remains blocked"
    elif capture_cycle_watch_evidence:
        prediction_paper_blocker = "prediction event-lag watch evidence exists, but paper promotion remains blocked by manual/model paper gate, resolved-label/post-spread evidence, and mapping ambiguity"
    elif event_lag_manual_review_summary["present"] and event_lag_manual_review_summary["readyForPaper"] is False:
        prediction_paper_blocker = "prediction event-lag manual review found no paper-grade window; forward capture and mapping repair required"
    else:
        prediction_paper_blocker = "prediction event-lag replay is not watch-ready"
    broker_parity_missing = (
        futures_broker_parity.get("missingProofs")
        if isinstance(futures_broker_parity.get("missingProofs"), list)
        else []
    )
    broker_parity_window = (
        futures_broker_parity.get("nextOpenSessionProofWindow")
        if isinstance(futures_broker_parity.get("nextOpenSessionProofWindow"), dict)
        else {}
    )
    broker_parity_current = (
        futures_broker_parity.get("current")
        if isinstance(futures_broker_parity.get("current"), dict)
        else {}
    )
    futures_wired = all(
        has_command(futures_action, fragment)
        for fragment in [
            "bill:futures-nq-historical-session-replay",
            "bill:futures-nq-current-data-parity",
            "bill:futures-data-requirements",
            "bill:futures-broker-parity-plan",
            "bill:futures-nq-research-cycle",
        ]
    )
    futures_realtime_proof_cleared = (
        futures_requirements.get("executionGradeRealtimeProofPassed") is True
        or (
            broker_parity_current.get("topstepRealtimeReadyForExecutionDataProof") is True
            and broker_parity_current.get("topstepRealtimeWritesCanonicalQuoteState") is True
        )
        or broker_parity_current.get("projectxSignalRReadyForExecutionDataProof") is True
        or realtime_preflight.get("readyForExecutionData") is True
    )
    futures_cycle_remaining_blockers = [
        str(blocker)
        for blocker in (futures_cycle.get("blockers") if isinstance(futures_cycle.get("blockers"), list) else [])
        if str(blocker) != "execution-grade-realtime-not-cleared" or not futures_realtime_proof_cleared
    ]
    futures_cycle_safe = (
        futures_cycle.get("researchOnly") is True
        and futures_cycle.get("readyForExecution") is False
        and futures_cycle.get("readyForDemoExpansion") is False
        and futures_requirements.get("researchOnly") is True
        and futures_requirements.get("readyForDemoExpansion") is False
        and isinstance(futures_cycle.get("blockers"), list)
        and (
            "execution-grade-realtime-not-cleared" in futures_cycle.get("blockers", [])
            or futures_realtime_proof_cleared
        )
    )
    paper_source_wired = (
        has_command(paper_action, "bill:paper-source-cards")
        and has_command(paper_action, "bill:alpha-frontier-queue")
        and paper_action.get("researchOnly") is True
        and paper_action.get("writesOrders") is False
        and paper_action.get("touchesBroker") is False
        and paper_action.get("operatorApprovalRequiredBeforeExecution") is True
        and "one-variable" in str(paper_action.get("promotionGate") or "").lower()
        and "requires-one-variable-oos-before-promotion" in (paper_action.get("promotionBlockers") or [])
    )
    youtube_source_cards = (
        seed_triage.get("queuedYouTubeSourceCards")
        if isinstance(seed_triage.get("queuedYouTubeSourceCards"), dict)
        else {}
    )
    seed_summary = seed_triage.get("summary") if isinstance(seed_triage.get("summary"), dict) else {}
    youtube_source_cards_wired = (
        youtube_source_cards.get("present") is True
        and youtube_source_cards.get("executionRelevant") is False
        and int(youtube_source_cards.get("strategyHypothesesPromoted") or 0) == 0
        and int(seed_summary.get("executableSeeds") or 0) == 0
        and seed_triage.get("readyForExecution") is False
        and isinstance(youtube_source_cards.get("cards"), list)
        and len(youtube_source_cards.get("cards") or []) > 0
    )
    broker_parity_safe_env = (
        futures_broker_parity.get("safeEnv")
        if isinstance(futures_broker_parity.get("safeEnv"), dict)
        else {}
    )
    broker_parity_steps = (
        futures_broker_parity.get("proofSequence")
        if isinstance(futures_broker_parity.get("proofSequence"), list)
        else []
    )
    broker_parity_validation_sets = (
        futures_broker_parity.get("validationCommandSets")
        if isinstance(futures_broker_parity.get("validationCommandSets"), dict)
        else {}
    )
    broker_parity_step_ids = {str(step.get("step")) for step in broker_parity_steps if isinstance(step, dict)}
    broker_parity_commands = [
        str(command)
        for step in broker_parity_steps
        if isinstance(step, dict)
        for command in (step.get("commands") if isinstance(step.get("commands"), list) else [])
    ]
    broker_parity_visible = (
        futures_broker_parity.get("decision") == "research-only-futures-broker-parity-not-cleared"
        and futures_broker_parity.get("researchOnly") is True
        and futures_broker_parity.get("writesOrders") is False
        and futures_broker_parity.get("touchesBroker") is False
        and futures_broker_parity.get("readyForExecution") is False
        and futures_broker_parity.get("readyForDemoExpansion") is False
        and broker_parity_safe_env.get("BILL_ENABLE_FUTURES_DEMO_EXECUTION") == "false"
        and broker_parity_safe_env.get("RH_TOPSTEP_READ_ONLY") == "true"
        and broker_parity_safe_env.get("RH_LIVE_EXECUTION_ENABLED") == "false"
        and broker_parity_window.get("commandsAreDataOnly") is True
        and {
            "refresh-state-with-locks",
            "open-session-data-only-smoke",
            "read-only-broker-reconciliation",
            "read-only-broker-market-data-smoke",
            "regenerate-clearance-artifacts",
        }.issubset(broker_parity_step_ids)
        and any("bill:topstep-realtime-proof" in command for command in broker_parity_commands)
        and any("bill:topstep-realtime-bridge" in command for command in broker_parity_commands)
        and any("bill:topstep-readonly-bar-archive" in command for command in broker_parity_commands)
        and any("bill:topstep-market-data-smoke" in command for command in broker_parity_commands)
        and any("RH_TOPSTEP_READ_ONLY=true" in command for command in broker_parity_commands)
        and isinstance(broker_parity_validation_sets.get("openSessionDataOnlyProof"), list)
        and isinstance(broker_parity_validation_sets.get("optionalSecondaryDatabentoProof"), list)
        and isinstance(broker_parity_validation_sets.get("readOnlyBrokerMarketData"), list)
        and isinstance(broker_parity_validation_sets.get("readOnlyBrokerReconciliation"), list)
    )
    control_data_only_proof = control_action.get("dataOnlyProof") if isinstance(control_action.get("dataOnlyProof"), dict) else {}
    control_topstep_safety = (
        control_data_only_proof.get("topstepSessionSafety")
        if isinstance(control_data_only_proof.get("topstepSessionSafety"), dict)
        else {}
    )
    control_proof_paused_by_topstep = (
        control_data_only_proof.get("pausedByTopstepSessionSafety") is True
        and control_topstep_safety.get("pauseBrokerTouchingProofs") is True
    )
    control_commands = [
        str(command)
        for command in (control_action.get("commands") if isinstance(control_action.get("commands"), list) else [])
    ]
    control_common_wired = all(
        has_command(control_action, fragment)
        for fragment in [
            "bill:realtime-data-preflight",
            "bill:live-readiness-gate",
            "bill:source-intake-manifest",
            "bill:source-hygiene-plan",
            "bill:data-intake-manifest",
            "bill:verify-execution-quarantine",
            "bill:execution-intake-manifest",
            "bill:clearance-handoff",
            "bill:goal-completion-audit",
            "bill:obsidian-sync",
        ]
    )
    control_paused_broker_proof_commands_absent = not any(
        fragment in command
        for command in control_commands
        for fragment in [
            "bill:open-session-data-proof",
            "bill:topstep-realtime-proof",
            "bill:topstep-realtime-bridge",
            "bill:clearance-evidence",
        ]
    )
    control_wired = (
        control_common_wired
        and (
            has_command(control_action, "bill:open-session-data-proof")
            or (
                control_proof_paused_by_topstep
                and has_command(control_action, "bill:futures-broker-parity-plan")
                and control_paused_broker_proof_commands_absent
            )
        )
    )
    control_data_only_command_wired = (
        has_command(
            control_action,
            "BILL_ENABLE_FUTURES_DEMO_EXECUTION=false RH_TOPSTEP_READ_ONLY=true RH_LIVE_EXECUTION_ENABLED=false npm run --silent bill:open-session-data-proof -- --run-data-only",
        )
        if not control_proof_paused_by_topstep
        else (
            has_command(control_action, "bill:futures-broker-parity-plan")
            and has_command(control_action, "bill:realtime-data-preflight")
            and control_paused_broker_proof_commands_absent
        )
    )
    control_data_only_proof_normal_safe = (
        control_data_only_proof.get("writesOrders") is False
        and broker_touch_is_none_or_readonly_market_data(control_data_only_proof)
        and control_data_only_proof.get("movesFunds") is False
        and isinstance(control_data_only_proof.get("plannedStepIds"), list)
        and "topstep-realtime-proof" in control_data_only_proof.get("plannedStepIds", [])
        and "topstep-realtime-bridge-write" in control_data_only_proof.get("plannedStepIds", [])
        and "topstep-readonly-bar-archive" in control_data_only_proof.get("plannedStepIds", [])
    )
    control_data_only_proof_paused_safe = (
        control_proof_paused_by_topstep
        and control_data_only_proof.get("writesOrders") is False
        and broker_touch_is_none_or_readonly_market_data(control_data_only_proof)
        and control_data_only_proof.get("movesFunds") is False
        and control_topstep_safety.get("safeUntil") == "operator-confirms-topstep-session-warning-cleared"
    )
    control_data_only_proof_safe = (
        control_data_only_proof_normal_safe
        if not control_proof_paused_by_topstep
        else control_data_only_proof_paused_safe
    )
    source_intake_visible = (
        source_intake.get("sourceIntakeVisible") is True
        and source_intake.get("readyForExecution") is False
        and source_intake.get("writesOrders") is False
        and source_intake.get("touchesBroker") is False
        and source_intake.get("sourceClean") is False
        and int(source_intake.get("executionLiveDirtyCount") or 0) >= 0
    )
    source_validation_sets = (
        source_intake.get("validationCommandSets")
        if isinstance(source_intake.get("validationCommandSets"), dict)
        else {}
    )
    focused_source_suite = source_validation_sets.get("focusedResearchControlSuite")
    full_source_suite = source_validation_sets.get("fullLocalSuiteAndFirewalls")
    source_visibility_refresh = source_validation_sets.get("sourceVisibilityRefresh")
    source_validation_sets_visible = (
        isinstance(focused_source_suite, list)
        and any("tests.test_bill_clearance_evidence" in str(command) for command in focused_source_suite)
        and any("tests.test_bill_source_intake_manifest" in str(command) for command in focused_source_suite)
        and isinstance(full_source_suite, list)
        and any("npm run --silent typecheck" in str(command) for command in full_source_suite)
        and any("npm run --silent test" in str(command) for command in full_source_suite)
        and any("bill:verify-execution-quarantine" in str(command) for command in full_source_suite)
        and any("bill:clearance-evidence" in str(command) for command in full_source_suite)
        and isinstance(source_visibility_refresh, list)
        and any("bill:source-intake-manifest" in str(command) for command in source_visibility_refresh)
        and any("bill:source-hygiene-plan" in str(command) for command in source_visibility_refresh)
        and any("bill:source-packet-review" in str(command) for command in source_visibility_refresh)
        and any("bill:obsidian-sync" in str(command) for command in source_visibility_refresh)
    )
    source_intake_evidence_visible = source_intake_visible and source_validation_sets_visible
    source_review_packets = (
        source_hygiene.get("nextReviewPackets")
        if isinstance(source_hygiene.get("nextReviewPackets"), list)
        else []
    )
    source_review_packet_ids = {
        str(item.get("id"))
        for item in source_review_packets
        if isinstance(item, dict) and item.get("id")
    }
    source_packets_by_id = {
        str(item.get("id")): item
        for item in source_review_packets
        if isinstance(item, dict) and item.get("id")
    }
    control_lane_packet = source_packets_by_id.get("packet-01-control-research-scaffold", {})
    futures_lane_packet = source_packets_by_id.get("packet-05-futures-strategy-lane", {})
    prediction_lane_packet = source_packets_by_id.get("packet-06-prediction-market-lane", {})
    unsafe_lane_terms = (
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

    def packet_safe_for_research_lane(packet: dict[str, Any]) -> bool:
        paths = packet.get("paths") if isinstance(packet.get("paths"), list) else []
        commands = packet.get("commands") if isinstance(packet.get("commands"), list) else []
        return (
            packet.get("decision") == "lane-review-only"
            and packet.get("safeToStageAutomatically") is False
            and packet.get("automaticCleanupAllowed") is False
            and packet.get("operatorApprovalRequired") is True
            and packet.get("writesOrders") is False
            and packet.get("touchesBroker") is False
            and packet.get("movesFunds") is False
            and isinstance(packet.get("diffSummary"), dict)
            and packet.get("diffSummary", {}).get("pathCount") == len(paths)
            and isinstance(packet.get("pathFootprint"), list)
            and len(packet.get("pathFootprint", [])) == len(paths)
            and len(paths) > 0
            and len(commands) > 0
            and not any(term in str(path).lower() for path in paths for term in unsafe_lane_terms)
        )

    futures_lane_paths = (
        futures_lane_packet.get("paths")
        if isinstance(futures_lane_packet.get("paths"), list)
        else []
    )
    prediction_lane_paths = (
        prediction_lane_packet.get("paths")
        if isinstance(prediction_lane_packet.get("paths"), list)
        else []
    )
    futures_lane_commands = (
        futures_lane_packet.get("commands")
        if isinstance(futures_lane_packet.get("commands"), list)
        else []
    )
    prediction_lane_commands = (
        prediction_lane_packet.get("commands")
        if isinstance(prediction_lane_packet.get("commands"), list)
        else []
    )
    futures_lane_visible = (
        packet_safe_for_research_lane(futures_lane_packet)
        and any(
            term in str(path).lower()
            for path in futures_lane_paths
            for term in ("futures", "nq", "backtrader", "cot", "dom_proxy", "kalman", "whale_flow")
        )
        and any("bill:futures-evidence-triage" in str(command) for command in futures_lane_commands)
        and any("bill:futures-broker-parity-plan" in str(command) for command in futures_lane_commands)
    )
    prediction_lane_visible = (
        packet_safe_for_research_lane(prediction_lane_packet)
        and any(
            term in str(path).lower()
            for path in prediction_lane_paths
            for term in ("prediction", "polymarket", "kalshi", "clob", "macro_rates", "event_")
        )
        and any("bill:prediction-evidence-triage" in str(command) for command in prediction_lane_commands)
        and any("bill:verify-prediction-funding-firewall" in str(command) for command in prediction_lane_commands)
    )
    source_lane_packets_visible = futures_lane_visible and prediction_lane_visible
    packet_review_packets = source_packet_review.get("packets") if isinstance(source_packet_review.get("packets"), list) else []
    packet_review_ids = {
        str(packet.get("id"))
        for packet in packet_review_packets
        if isinstance(packet, dict) and packet.get("id")
    }
    manual_clearance = (
        source_packet_review.get("manualClearanceProposal")
        if isinstance(source_packet_review.get("manualClearanceProposal"), dict)
        else {}
    )
    manual_lane_proposals = (
        manual_clearance.get("laneProposals")
        if isinstance(manual_clearance.get("laneProposals"), list)
        else []
    )
    manual_lane_ids = {
        str(lane.get("lane"))
        for lane in manual_lane_proposals
        if isinstance(lane, dict) and lane.get("lane")
    }
    manual_clearance_visible = (
        manual_clearance.get("decision") == "manual-clearance-proposal-only"
        and manual_clearance.get("researchOnly") is True
        and manual_clearance.get("safeToStageAutomatically") is False
        and manual_clearance.get("writesOrders") is False
        and manual_clearance.get("touchesBroker") is False
        and manual_clearance.get("movesFunds") is False
        and {"control-research", "futures", "prediction-markets"}.issubset(manual_lane_ids)
        and any("bill:clearance-evidence" in str(command) for command in (manual_clearance.get("nextCommands") or []))
        and all(
            isinstance(lane, dict)
            and lane.get("safeToStageAutomatically") is False
            and lane.get("writesOrders") is False
            and lane.get("touchesBroker") is False
            and lane.get("movesFunds") is False
            and (
                bool(lane.get("reviewFirst"))
                or bool(lane.get("keepResearchCandidates"))
                or bool(lane.get("shadowOnly"))
                or bool(lane.get("quarantineReview"))
                or bool(lane.get("dependencyReviewed"))
                or bool(lane.get("historicalReference"))
                or bool(lane.get("retiredReference"))
            )
            for lane in manual_lane_proposals
        )
    )
    source_packet_review_visible = (
        source_packet_review.get("decision") == "source-packet-review-visible-execution-locked"
        and source_packet_review.get("researchOnly") is True
        and source_packet_review.get("sourceHygieneCleared") is False
        and source_packet_review.get("packetReviewCleared") is False
        and source_packet_review.get("readyForExecution") is False
        and source_packet_review.get("readyForDemoExpansion") is False
        and source_packet_review.get("readyForLive") is False
        and source_packet_review.get("safeToStageAutomatically") is False
        and source_packet_review.get("automaticCleanupAllowed") is False
        and source_packet_review.get("operatorApprovalRequired") is True
        and source_packet_review.get("writesOrders") is False
        and source_packet_review.get("touchesBroker") is False
        and source_packet_review.get("movesFunds") is False
        and source_packet_review.get("missingPackets") == []
        and {
            "packet-01-control-research-scaffold",
            "packet-05-futures-strategy-lane",
            "packet-06-prediction-market-lane",
        }.issubset(packet_review_ids)
        and isinstance(source_packet_review.get("classificationCounts"), dict)
        and manual_clearance_visible
        and all(
            isinstance(packet, dict)
            and packet.get("safeToStageAutomatically") is False
            and packet.get("automaticCleanupAllowed") is False
            and packet.get("operatorApprovalRequired") is True
            and packet.get("writesOrders") is False
            and packet.get("touchesBroker") is False
            and packet.get("movesFunds") is False
            and packet.get("readyForExecution") is False
            and isinstance(packet.get("rows"), list)
            and len(packet.get("rows", [])) == int(packet.get("pathCount") or 0)
            for packet in packet_review_packets
        )
    )
    source_review_packets_visible = (
        {
            "packet-01-control-research-scaffold",
            "packet-02-execution-firewall-quarantine",
            "packet-03-data-provenance-refresh",
            "packet-04-strategy-backlog-sample",
        }.issubset(source_review_packet_ids)
        and all(
            isinstance(item, dict)
            and item.get("safeToStageAutomatically") is False
            and item.get("automaticCleanupAllowed") is False
            and item.get("writesOrders") is False
            and item.get("touchesBroker") is False
            and item.get("movesFunds") is False
            and item.get("operatorApprovalRequired") is True
            and isinstance(item.get("paths"), list)
            and len(item.get("paths", [])) > 0
            and isinstance(item.get("pathFootprint"), list)
            and len(item.get("pathFootprint", [])) == len(item.get("paths", []))
            and isinstance(item.get("diffSummary"), dict)
            and item.get("diffSummary", {}).get("pathCount") == len(item.get("paths", []))
            and isinstance(item.get("diffSummary", {}).get("statusCounts"), dict)
            and isinstance(item.get("commands"), list)
            and len(item.get("commands", [])) > 0
            for item in source_review_packets
        )
    )
    source_hygiene_visible = (
        source_hygiene.get("decision") == "source-hygiene-plan-research-only-execution-locked"
        and source_hygiene.get("researchOnly") is True
        and source_hygiene.get("sourceHygieneCleared") is False
        and source_hygiene.get("automaticCleanupAllowed") is False
        and source_hygiene.get("safeToStageAutomatically") is False
        and source_hygiene.get("readyForExecution") is False
        and source_hygiene.get("readyForDemoExpansion") is False
        and source_hygiene.get("readyForLive") is False
        and source_hygiene.get("writesOrders") is False
        and source_hygiene.get("touchesBroker") is False
        and source_hygiene.get("movesFunds") is False
        and isinstance(source_hygiene.get("dirtyStatusCount"), int)
        and isinstance(source_hygiene.get("reviewBacklogCount"), int)
        and isinstance(source_hygiene.get("bundleSummary"), list)
        and all(
            isinstance(item, dict)
            and item.get("safeToStageAutomatically") is False
            and item.get("automaticCleanupAllowed") is False
            and item.get("writesOrders") is False
            and item.get("touchesBroker") is False
            and item.get("movesFunds") is False
            for item in source_hygiene.get("bundleSummary", [])
        )
        and source_review_packets_visible
    )
    stale_claim_guard_visible = (
        not stale_claim_guard
        or stale_claim_guard.get("status") == "PASS"
        and stale_claim_guard.get("decision") == "stale-claim-guard-pass"
        and stale_claim_guard.get("researchOnly") is True
        and stale_claim_guard.get("writesOrders") is False
        and stale_claim_guard.get("touchesBroker") is False
        and stale_claim_guard.get("readyForExecution") is False
        and int(stale_claim_guard.get("findingCount") or 0) == 0
    )
    data_intake_visible = (
        data_intake.get("decision") == "data-intake-visible-execution-locked"
        and data_intake.get("readyForExecutionData") is False
        and data_intake.get("executionGradeData") is False
        and data_intake.get("writesOrders") is False
        and data_intake.get("touchesBroker") is False
        and int(data_intake.get("dirtyDataFileCount") or 0) >= 0
    )
    data_validation_sets = (
        data_intake.get("validationCommandSets")
        if isinstance(data_intake.get("validationCommandSets"), dict)
        else {}
    )
    data_visibility_refresh = data_validation_sets.get("dataVisibilityRefresh")
    futures_data_evidence = data_validation_sets.get("futuresDataEvidence")
    data_validation_sets_visible = (
        isinstance(data_visibility_refresh, list)
        and any("bill:data-intake-manifest" in str(command) for command in data_visibility_refresh)
        and any("bill:obsidian-sync" in str(command) for command in data_visibility_refresh)
        and isinstance(futures_data_evidence, list)
        and any("bill:data-freshness-gate" in str(command) for command in futures_data_evidence)
        and any("bill:futures-data-requirements" in str(command) for command in futures_data_evidence)
        and any("bill:futures-broker-parity-plan" in str(command) for command in futures_data_evidence)
        and any("bill:open-session-data-proof -- --run-data-only" in str(command) for command in futures_data_evidence)
    )
    data_intake_evidence_visible = data_intake_visible and data_validation_sets_visible
    proof_steps = open_session_data_proof.get("plannedSteps") if isinstance(open_session_data_proof.get("plannedSteps"), list) else []
    proof_step_ids = open_session_data_proof.get("plannedStepIds") if isinstance(open_session_data_proof.get("plannedStepIds"), list) else [
        step.get("id")
        for step in proof_steps
        if isinstance(step, dict)
    ]

    def proof_step_locked(step: dict[str, Any]) -> bool:
        env = step.get("env") if isinstance(step.get("env"), dict) else {}
        command = str(step.get("command") or " ".join(str(part) for part in (step.get("argv") or [])))
        return (
            env.get("BILL_ENABLE_FUTURES_DEMO_EXECUTION") == "false"
            and env.get("RH_TOPSTEP_READ_ONLY") == "true"
            and env.get("RH_LIVE_EXECUTION_ENABLED") == "false"
            and "BILL_ENABLE_FUTURES_DEMO_EXECUTION=false" in command
            and "RH_TOPSTEP_READ_ONLY=true" in command
            and "RH_LIVE_EXECUTION_ENABLED=false" in command
        )

    data_smoke_step_visible = any(
        isinstance(step, dict)
        and step.get("id") == "databento-open-session-smoke"
        and "bill:databento-realtime-smoke" in str(step.get("command") or " ".join(str(part) for part in (step.get("argv") or [])))
        and proof_step_locked(step)
        and step.get("writesOrders") is False
        and step.get("touchesBroker") is False
        and step.get("movesFunds") is False
        for step in proof_steps
    )
    data_bridge_step_visible = any(
        isinstance(step, dict)
        and step.get("id") == "databento-open-session-bridge-write"
        and "realtime_data_bridge.py" in str(step.get("command") or " ".join(str(part) for part in (step.get("argv") or [])))
        and "--databento-only" in str(step.get("command") or " ".join(str(part) for part in (step.get("argv") or [])))
        and isinstance(step.get("env"), dict)
        and step.get("env", {}).get("BILL_DATABENTO_REALTIME_ENABLED") == "true"
        and proof_step_locked(step)
        and step.get("writesOrders") is False
        and step.get("touchesBroker") is False
        and step.get("movesFunds") is False
        for step in proof_steps
    )
    optional_databento_enabled = open_session_data_proof.get("includeDatabentoOptionalProof") is True
    optional_databento_state_ok = (
        (data_smoke_step_visible and data_bridge_step_visible)
        if optional_databento_enabled
        else all(
            step_id in (open_session_data_proof.get("skippedOptionalStepIds") or [])
            for step_id in [
                "databento-open-session-smoke",
                "databento-orderflow-feature-smoke",
                "databento-open-session-bridge-write",
            ]
        )
    )
    topstep_realtime_proof_visible = any(
        isinstance(step, dict)
        and step.get("id") == "topstep-realtime-proof"
        and "bill:topstep-realtime-proof" in str(step.get("command") or " ".join(str(part) for part in (step.get("argv") or [])))
        and proof_step_locked(step)
        and step.get("writesOrders") is False
        and step.get("touchesBroker") is True
        and step.get("brokerTouchMode") == "read-only-market-data"
        and step.get("movesFunds") is False
        for step in proof_steps
    )
    topstep_realtime_bridge_visible = any(
        isinstance(step, dict)
        and step.get("id") == "topstep-realtime-bridge-write"
        and "bill:topstep-realtime-bridge" in str(step.get("command") or " ".join(str(part) for part in (step.get("argv") or [])))
        and proof_step_locked(step)
        and step.get("writesOrders") is False
        and step.get("touchesBroker") is True
        and step.get("brokerTouchMode") == "read-only-market-data"
        and step.get("movesFunds") is False
        for step in proof_steps
    )
    topstep_readonly_archive_visible = any(
        isinstance(step, dict)
        and step.get("id") == "topstep-readonly-bar-archive"
        and "bill:topstep-readonly-bar-archive" in str(step.get("command") or " ".join(str(part) for part in (step.get("argv") or [])))
        and proof_step_locked(step)
        and step.get("writesOrders") is False
        and step.get("touchesBroker") is True
        and step.get("brokerTouchMode") == "read-only-market-data"
        and step.get("movesFunds") is False
        for step in proof_steps
    )
    data_proof_normal_visible = (
        open_session_data_proof.get("command") == "bill-open-session-data-proof"
        and open_session_data_proof.get("researchOnly") is True
        and open_session_data_proof.get("writesOrders") is False
        and broker_touch_is_none_or_readonly_market_data(open_session_data_proof)
        and open_session_data_proof.get("movesFunds") is False
        and open_session_data_proof.get("readyForExecution") is False
        and open_session_data_proof.get("readyForDemoExpansion") is False
        and open_session_data_proof.get("readyForLive") is False
        and open_session_data_proof.get("brokerReadOnlyStepIncluded") is True
        and isinstance(open_session_data_proof.get("executionGradeDataProofPassed"), bool)
        and open_session_data_proof.get("preferredDataPath") == "topstepx_projectx"
        and "topstep-realtime-proof" in proof_step_ids
        and "topstep-realtime-bridge-write" in proof_step_ids
        and "topstep-readonly-bar-archive" in proof_step_ids
        and topstep_realtime_proof_visible
        and topstep_realtime_bridge_visible
        and optional_databento_state_ok
        and topstep_readonly_archive_visible
        and all(
            isinstance(step, dict)
            and step.get("writesOrders") is False
            and broker_touch_is_none_or_readonly_market_data(step)
            and step.get("movesFunds") is False
            for step in proof_steps
        )
    )
    data_proof_paused_visible = (
        control_proof_paused_by_topstep
        and open_session_data_proof.get("command") == "bill-open-session-data-proof"
        and open_session_data_proof.get("researchOnly") is True
        and open_session_data_proof.get("writesOrders") is False
        and broker_touch_is_none_or_readonly_market_data(open_session_data_proof)
        and open_session_data_proof.get("movesFunds") is False
        and open_session_data_proof.get("readyForExecution") is False
        and open_session_data_proof.get("readyForDemoExpansion") is False
        and open_session_data_proof.get("readyForLive") is False
        and open_session_data_proof.get("brokerReadOnlyStepIncluded") is False
        and open_session_data_proof.get("brokerTouchingProofsPaused") is True
        and {
            "topstep-realtime-proof",
            "topstep-realtime-bridge-write",
            "topstep-readonly-bar-archive",
        }.issubset(set(open_session_data_proof.get("skippedBrokerTouchingStepIds") or []))
        and all(
            isinstance(step, dict)
            and step.get("writesOrders") is False
            and step.get("touchesBroker") is False
            and step.get("movesFunds") is False
            for step in proof_steps
        )
    )
    data_proof_visible = data_proof_normal_visible or data_proof_paused_visible
    execution_intake_visible = (
        execution_intake.get("decision") == "execution-intake-visible-execution-locked"
        and execution_intake.get("executionLocked") is True
        and execution_intake.get("readyForExecution") is False
        and execution_intake.get("writesOrders") is False
        and execution_intake.get("touchesBroker") is False
        and execution_intake.get("movesFunds") is False
        and int(execution_intake.get("dirtyExecutionFileCount") or 0) >= 0
    )
    execution_validation_sets = (
        execution_intake.get("validationCommandSets")
        if isinstance(execution_intake.get("validationCommandSets"), dict)
        else {}
    )
    execution_firewall_evidence = execution_validation_sets.get("executionFirewallEvidence")
    legacy_firewall_evidence = execution_validation_sets.get("firewallEvidence")
    execution_visibility_refresh = execution_validation_sets.get("executionVisibilityRefresh")
    firewall_commands = execution_firewall_evidence if isinstance(execution_firewall_evidence, list) else legacy_firewall_evidence
    execution_validation_sets_visible = (
        isinstance(firewall_commands, list)
        and all(
            any(fragment in str(command) for command in firewall_commands)
            for fragment in [
                "bill:verify-master-bridge-firewall",
                "bill:verify-60m-bridge-firewall",
                "bill:verify-topstep-demo-bridge-firewall",
                "bill:verify-signal-router-firewall",
                "bill:verify-prediction-funding-firewall",
                "bill:verify-execution-quarantine",
            ]
        )
        and any("bill:clearance-evidence" in str(command) for command in firewall_commands)
        and isinstance(execution_visibility_refresh, list)
        and any("bill:execution-intake-manifest" in str(command) for command in execution_visibility_refresh)
        and any("bill:goal-completion-audit" in str(command) for command in execution_visibility_refresh)
        and any("bill:obsidian-sync" in str(command) for command in execution_visibility_refresh)
    )
    uncovered_execution_paths = (
        execution_intake.get("uncoveredExecutionPaths")
        if isinstance(execution_intake.get("uncoveredExecutionPaths"), list)
        else []
    )
    execution_intake_evidence_visible = (
        execution_intake_visible
        and execution_intake.get("allFirewallCommandsPassed") is True
        and uncovered_execution_paths == []
        and execution_validation_sets_visible
    )
    shadow_signal_rows = (
        signal_quality.get("shadowSignalRows")
        if isinstance(signal_quality.get("shadowSignalRows"), list)
        else []
    )
    signal_quality_visible = (
        signal_quality.get("command") == "signal-quality-advisor"
        and signal_quality.get("researchOnly") is True
        and signal_quality.get("writesOrders") is False
        and signal_quality.get("readyForExecution") is False
        and isinstance(signal_quality.get("overallRating"), (int, float))
        and isinstance(signal_quality.get("blockers"), list)
        and signal_quality.get("blockers") == []
        and all(
            isinstance(item, dict)
            and item.get("promotedForExecution") is not True
            and item.get("tradableSignal") is not True
            for item in shadow_signal_rows
        )
    )
    source_truth_sources = (
        signal_source_truth.get("sources")
        if isinstance(signal_source_truth.get("sources"), list)
        else []
    )
    source_truth_issues = (
        signal_source_truth.get("issues")
        if isinstance(signal_source_truth.get("issues"), list)
        else []
    )
    source_truth_roles = {
        item.get("file"): item
        for item in source_truth_sources
        if isinstance(item, dict) and item.get("file")
    }
    signal_source_truth_visible = (
        signal_source_truth.get("command") == "signal-source-truth-audit"
        and signal_source_truth.get("researchOnly") is True
        and signal_source_truth.get("writesOrders") is False
        and signal_source_truth.get("touchesBroker") is False
        and signal_source_truth.get("movesFunds") is False
        and signal_source_truth.get("readyForExecution") is False
        and source_truth_roles.get("alpha-lab.latest.json", {}).get("authority") == "never-route"
        and source_truth_roles.get("60m-signals-latest.json", {}).get("role") == "advisory-shadow-signal"
        and source_truth_roles.get("arbitration.latest.json", {}).get("authority") == "block-or-reduce-only"
        and source_truth_roles.get("master-signal.latest.json", {}).get("authority") == "requires-daily-plan-and-firewalls"
        and not any(
            isinstance(item, dict) and item.get("issue") == "research-or-advisory-source-promoted"
            for item in source_truth_issues
        )
    )
    cron_trust = (
        cron_validator.get("cron_trust")
        if isinstance(cron_validator.get("cron_trust"), dict)
        else {}
    )
    cron_issues = cron_validator.get("issues") if isinstance(cron_validator.get("issues"), list) else []
    blocking_cron_issues = [
        issue
        for issue in cron_issues
        if isinstance(issue, dict) and issue.get("severity") in {"P0", "P1"}
    ]
    active_dirty_execution_refs = (
        cron_trust.get("activeDirtyExecutionLiveScriptReferences")
        if isinstance(cron_trust.get("activeDirtyExecutionLiveScriptReferences"), list)
        else []
    )
    active_dirty_execution_ref_count = int(
        cron_trust.get("activeDirtyExecutionLiveScriptReferenceCount") or len(active_dirty_execution_refs)
    )
    cron_control_trust_cleared = (
        isinstance(cron_validator.get("summary"), str)
        and active_dirty_execution_ref_count == 0
        and blocking_cron_issues == []
    )
    active_prediction_capture_ids = (
        codex_automation.get("activePredictionCaptureIds")
        if isinstance(codex_automation.get("activePredictionCaptureIds"), list)
        else []
    )
    paused_prediction_capture_ids = (
        codex_automation.get("pausedPredictionCaptureIds")
        if isinstance(codex_automation.get("pausedPredictionCaptureIds"), list)
        else []
    )
    active_futures_open_session_proof_ids = (
        codex_automation.get("activeFuturesOpenSessionProofIds")
        if isinstance(codex_automation.get("activeFuturesOpenSessionProofIds"), list)
        else []
    )
    active_futures_open_session_proof_conflict_ids = (
        codex_automation.get("activeFuturesOpenSessionProofConflictIds")
        if isinstance(codex_automation.get("activeFuturesOpenSessionProofConflictIds"), list)
        else []
    )
    codex_automation_blockers = (
        codex_automation.get("blockers")
        if isinstance(codex_automation.get("blockers"), list)
        else []
    )
    codex_automation_visible = (
        codex_automation.get("status") == "PASS"
        and codex_automation.get("researchOnly") is True
        and codex_automation.get("writesOrders") is False
        and codex_automation.get("touchesBroker") is False
        and codex_automation.get("movesFunds") is False
        and codex_automation.get("readyForExecution") is False
        and codex_automation.get("readyForPaper") is False
        and codex_automation.get("readyForDemoExpansion") is False
        and codex_automation_blockers == []
        and active_prediction_capture_ids == ["bill-prediction-forward-clob-capture"]
        and "bill-prediction-event-clob-capture" in paused_prediction_capture_ids
        and active_futures_open_session_proof_conflict_ids == []
    )
    runtime_n8n = runtime_architecture.get("n8n") if isinstance(runtime_architecture.get("n8n"), dict) else {}
    runtime_kanban = (
        runtime_architecture.get("hermesKanban")
        if isinstance(runtime_architecture.get("hermesKanban"), dict)
        else {}
    )
    runtime_cron = (
        runtime_architecture.get("hermesCron")
        if isinstance(runtime_architecture.get("hermesCron"), dict)
        else {}
    )
    runtime_ai_scientist = (
        runtime_architecture.get("aiScientistTemplate")
        if isinstance(runtime_architecture.get("aiScientistTemplate"), dict)
        else {}
    )
    runtime_ai_safety = (
        runtime_ai_scientist.get("safety")
        if isinstance(runtime_ai_scientist.get("safety"), dict)
        else {}
    )
    runtime_architecture_visible = (
        runtime_architecture.get("decision") == "runtime-architecture-visible-execution-locked"
        and runtime_architecture.get("researchOnly") is True
        and runtime_architecture.get("writesOrders") is False
        and runtime_architecture.get("touchesBroker") is False
        and runtime_architecture.get("movesFunds") is False
        and runtime_architecture.get("readyForExecution") is False
        and runtime_architecture.get("readyForDemoExpansion") is False
        and runtime_architecture.get("readyForPaper") is False
        and runtime_ai_scientist.get("hardSafetyOk") is True
        and runtime_ai_safety.get("research_only") is True
        and runtime_ai_safety.get("writes_orders") is False
        and runtime_ai_safety.get("touches_broker") is False
        and runtime_ai_safety.get("moves_funds") is False
        and isinstance(runtime_n8n.get("workflowCount"), int)
        and isinstance(runtime_kanban.get("statusCounts"), dict)
        and isinstance(runtime_cron.get("activeCount"), int)
    )

    gates = handoff.get("gates") if isinstance(handoff.get("gates"), dict) else {}
    live_blockers = gates.get("liveReadinessBlockers") if isinstance(gates.get("liveReadinessBlockers"), list) else []
    source_blockers = gates.get("sourceCleanBlockers") if isinstance(gates.get("sourceCleanBlockers"), list) else []
    realtime_blockers = gates.get("realtimeDataBlockers") if isinstance(gates.get("realtimeDataBlockers"), list) else []
    prediction_blockers = prediction_capture.get("blockers") if isinstance(prediction_capture.get("blockers"), list) else []
    futures_blockers = futures_cycle.get("blockers") if isinstance(futures_cycle.get("blockers"), list) else []
    worktree_blockers = worktree.get("sourceCleanBlockers") if isinstance(worktree.get("sourceCleanBlockers"), list) else []
    sibling_worktree_summary = {
        "present": bool(sibling_worktree_intake),
        "decision": sibling_worktree_intake.get("decision"),
        "dirtySiblingWorktreeCount": sibling_worktree_intake.get("dirtySiblingWorktreeCount"),
        "dirtyFileCount": sibling_worktree_intake.get("dirtyFileCount"),
        "executionLiveDirtyCount": sibling_worktree_intake.get("executionLiveDirtyCount"),
        "safeToMergeAutomatically": bool(sibling_worktree_intake.get("safeToMergeAutomatically")),
        "blockers": (
            sibling_worktree_intake.get("blockers")
            if isinstance(sibling_worktree_intake.get("blockers"), list)
            else []
        ),
        "classificationCounts": (
            sibling_worktree_intake.get("classificationCounts")
            if isinstance(sibling_worktree_intake.get("classificationCounts"), dict)
            else {}
        ),
    }
    obsidian_resource_inventory_visible = (
        "# Bill Resource Inventory" in resource_inventory_text
        and "Bill-Resource-Full-Manifest.jsonl" in resource_inventory_text
        and "## Priority Outside Obsidian" in resource_inventory_text
        and "Display policy: highest-signal Bill/Hermes resources first" in resource_inventory_text
        and "`execution-review`" in resource_inventory_text
    )

    checklist = [
        check(
            item_id="objective-restated",
            requirement="Restate the active objective as concrete success criteria.",
            status="pass",
            artifact="bill-goal-completion-audit.latest.json",
            evidence={"objective": OBJECTIVE},
        ),
        check(
            item_id="execution-locked",
            requirement="Keep execution locked until evidence gates pass.",
            status="pass" if execution_locked and daily_blocked else "blocked",
            artifact=".rumbling-hedge/state/bill-clearance-handoff.latest.json and daily plan",
            evidence={
                "handoffDecision": handoff.get("decision"),
                "readyForExecution": handoff.get("readyForExecution"),
                "readyForDemoExpansion": handoff.get("readyForDemoExpansion"),
                "readyForLive": handoff.get("readyForLive"),
                "dailyRouteBlocked": daily_blocked,
            },
            blocker=None if execution_locked and daily_blocked else "execution lock evidence is incomplete",
        ),
        check(
            item_id="alpha-tooling-ready",
            requirement="Install or verify necessary alpha research tooling.",
            status="pass" if tooling.get("status") == "PASS" and tooling.get("readyForResearchLoop") else "blocked",
            artifact=".rumbling-hedge/state/alpha-research-tooling-check.latest.json",
            evidence={
                "status": tooling.get("status"),
                "readyForResearchLoop": tooling.get("readyForResearchLoop"),
                "blockers": tooling.get("blockers", []),
            },
            blocker=None if tooling.get("status") == "PASS" and tooling.get("readyForResearchLoop") else "alpha tooling is not green",
        ),
        check(
            item_id="control-plane-queue",
            requirement="Keep a concrete control-plane refresh command sequence available.",
            status="pass" if control_wired and control_data_only_command_wired and control_data_only_proof_safe else "blocked",
            artifact=".rumbling-hedge/state/bill-next-research-actions.latest.json",
            evidence={
                "actionPresent": bool(control_action),
                "commands": control_action.get("commands", []),
                "dataOnlyProof": control_data_only_proof,
                "nextWindow": control_action.get("nextWindow", {}),
            },
            blocker=None if control_wired and control_data_only_command_wired and control_data_only_proof_safe else "control-plane queue is missing required refresh or data-only proof commands",
        ),
        check(
            item_id="futures-loop-focused",
            requirement="Focus the next build/research loop on futures with OOS, parity, broker-parity plan, and no execution.",
            status="pass" if futures_wired and futures_cycle_safe else "blocked",
            artifact=".rumbling-hedge/state/bill-next-research-actions.latest.json and futures-nq-research-cycle.latest.json",
            evidence={
                "actionPresent": bool(futures_action),
                "cycleDecision": futures_cycle.get("decision"),
                "cycleMode": futures_cycle.get("mode"),
                "researchOnly": futures_cycle.get("researchOnly"),
                "readyForExecution": futures_cycle.get("readyForExecution"),
                "readyForDemoExpansion": futures_cycle.get("readyForDemoExpansion"),
                "historicalCurrentParitySummary": (
                    futures_cycle.get("historical", {}).get("currentParitySummary")
                    if isinstance(futures_cycle.get("historical"), dict)
                    else {}
                ),
                "requirementsDecision": futures_requirements.get("decision"),
                "requirementsResearchOnly": futures_requirements.get("researchOnly"),
                "requirementsReadyForDemoExpansion": futures_requirements.get("readyForDemoExpansion"),
                "blockers": futures_blockers,
                "remainingBlockersAfterRealtimeProof": futures_cycle_remaining_blockers,
                "executionGradeRealtimeProofCleared": futures_realtime_proof_cleared,
                "commands": futures_action.get("commands", []),
            },
            blocker=None if futures_wired and futures_cycle_safe else "futures loop is not fully wired to a safe research-only, non-demo-expandable artifact",
        ),
        check(
            item_id="futures-broker-parity-visible",
            requirement="Expose a locked open-session broker/data parity proof plan before futures demo expansion.",
            status="pass" if broker_parity_visible else "blocked",
            artifact=".rumbling-hedge/state/futures-broker-parity-plan.latest.json",
            evidence={
                "decision": futures_broker_parity.get("decision"),
                "missingProofs": broker_parity_missing,
                "current": broker_parity_current,
                "nextOpenSessionProofWindow": broker_parity_window,
                "safeEnv": broker_parity_safe_env,
                "proofStepIds": sorted(broker_parity_step_ids),
                "validationCommandSets": broker_parity_validation_sets,
            },
            blocker=None if broker_parity_visible else "futures broker parity plan is missing, unsafe, incomplete, or lacks open-session/read-only validation commands",
        ),
        check(
            item_id="paper-source-frontier-wired",
            requirement="Wire collected papers into the futures research frontier as one-variable hypothesis seeds, not execution evidence.",
            status="pass" if paper_source_wired else "blocked",
            artifact=".rumbling-hedge/state/alpha-frontier-queue.latest.json and bill-next-research-actions.latest.json",
            evidence={
                "actionPresent": bool(paper_action),
                "commands": paper_action.get("commands", []),
                "researchOnly": paper_action.get("researchOnly"),
                "writesOrders": paper_action.get("writesOrders"),
                "touchesBroker": paper_action.get("touchesBroker"),
                "operatorApprovalRequiredBeforeExecution": paper_action.get("operatorApprovalRequiredBeforeExecution"),
                "promotionGate": paper_action.get("promotionGate"),
                "promotionBlockers": paper_action.get("promotionBlockers", []),
                "dataPaths": paper_action.get("dataPaths", []),
            },
            blocker=None if paper_source_wired else "paper-source frontier item is missing, unsafe, or not gated as one-variable OOS research only",
        ),
        check(
            item_id="prediction-loop-focused",
            requirement="Focus the prediction-market loop on news/event lag and public CLOB capture, not execution.",
            status="pass" if prediction_recorder_wired and prediction_capture_safe else "blocked",
            artifact=".rumbling-hedge/state/bill-next-research-actions.latest.json and prediction-event-capture-cycle.latest.json",
            evidence={
                "actionPresent": bool(prediction_action),
                "captureDecision": prediction_capture.get("decision"),
                "captureMode": prediction_capture.get("mode"),
                "researchOnly": prediction_capture.get("researchOnly"),
                "writesOrders": prediction_capture.get("writesOrders"),
                "touchesBroker": prediction_capture.get("touchesBroker"),
                "readyForExecution": prediction_capture.get("readyForExecution"),
                "readyForPaper": prediction_capture.get("readyForPaper"),
                "paperPromotionEvidencePassed": prediction_capture.get("paperPromotionEvidencePassed"),
                "latestRecorderWritesOrders": latest_recorder.get("writesOrders"),
                "liveQualityReadyForPaperEvidence": live_quality.get("readyForPaperEvidence"),
                "fillableLiveBookCount": live_quality.get("fillableLiveBookCount"),
                "commands": prediction_action.get("commands", []),
            },
            blocker=None if prediction_recorder_wired and prediction_capture_safe else "prediction event capture is not wired to a safe research-only recorder artifact",
        ),
        check(
            item_id="queue-safe-flags",
            requirement="Next research queue must not imply orders, broker access, paper, demo, or live routing.",
            status="pass" if queue_safe else "blocked",
            artifact=".rumbling-hedge/state/bill-next-research-actions.latest.json",
            evidence={
                "researchOnly": next_actions.get("researchOnly"),
                "writesOrders": next_actions.get("writesOrders"),
                "touchesBroker": next_actions.get("touchesBroker"),
                "readyForExecution": next_actions.get("readyForExecution"),
            },
            blocker=None if queue_safe else "next research queue safety flags are incomplete",
        ),
        check(
            item_id="source-intake-visible",
            requirement="Make dirty source state visible with validation command sets, without clearing source hygiene or touching execution.",
            status="pass" if source_intake_evidence_visible else "blocked",
            artifact=".rumbling-hedge/state/bill-source-intake-manifest.latest.json",
            evidence={
                "decision": source_intake.get("decision"),
                "sourceClean": source_intake.get("sourceClean"),
                "sourceIntakeVisible": source_intake.get("sourceIntakeVisible"),
                "executionLiveDirtyCount": source_intake.get("executionLiveDirtyCount"),
                "classificationCounts": source_intake.get("classificationCounts", {}),
                "validationCommandSets": source_validation_sets,
            },
            blocker=None if source_intake_evidence_visible else "source intake manifest is missing, unsafe, or lacks validation command sets",
        ),
        check(
            item_id="source-hygiene-plan-visible",
            requirement="Keep a read-only source hygiene reduction plan visible without clearing source hygiene.",
            status="pass" if source_hygiene_visible else "blocked",
            artifact=".rumbling-hedge/state/bill-source-hygiene-plan.latest.json",
            evidence={
                "decision": source_hygiene.get("decision"),
                "sourceHygieneCleared": source_hygiene.get("sourceHygieneCleared"),
                "automaticCleanupAllowed": source_hygiene.get("automaticCleanupAllowed"),
                "safeToStageAutomatically": source_hygiene.get("safeToStageAutomatically"),
                "dirtyStatusCount": source_hygiene.get("dirtyStatusCount"),
                "reviewBacklogCount": source_review_backlog_count,
                "hygienePlanReviewBacklogCount": source_hygiene.get("reviewBacklogCount"),
                "bundleSummary": source_hygiene.get("bundleSummary", []),
                "bundleCounts": [
                    (item.get("id"), item.get("count"))
                    for item in (source_hygiene.get("bundles") or [])
                    if isinstance(item, dict)
                ],
                "nextReviewPackets": [
                    {
                        "id": item.get("id"),
                        "bundleId": item.get("bundleId"),
                        "pathCount": item.get("pathCount"),
                        "diffSummary": item.get("diffSummary"),
                        "decision": item.get("decision"),
                        "safeToStageAutomatically": item.get("safeToStageAutomatically"),
                    }
                    for item in source_review_packets
                    if isinstance(item, dict)
                ],
                "nextReductionOrder": [
                    (item.get("rank"), item.get("bundleId"))
                    for item in (source_hygiene.get("nextReductionOrder") or [])[:4]
                    if isinstance(item, dict)
                ],
            },
            blocker=None if source_hygiene_visible else "source hygiene plan is missing, unsafe, or lacks review packets",
        ),
        check(
            item_id="stale-strategy-claim-guard-visible",
            requirement="Block stale trade-now or paper-now research claims unless nearby text explicitly supersedes or blocks them.",
            status="pass" if stale_claim_guard_visible else "blocked",
            artifact=".rumbling-hedge/state/stale-strategy-claim-guard.latest.json",
            evidence={
                "decision": stale_claim_guard.get("decision"),
                "status": stale_claim_guard.get("status"),
                "findingCount": stale_claim_guard.get("findingCount"),
                "fileCount": stale_claim_guard.get("fileCount"),
                "researchOnly": stale_claim_guard.get("researchOnly"),
                "writesOrders": stale_claim_guard.get("writesOrders"),
                "touchesBroker": stale_claim_guard.get("touchesBroker"),
                "readyForExecution": stale_claim_guard.get("readyForExecution"),
            },
            blocker=None if stale_claim_guard_visible else "stale strategy claim guard is missing or has findings",
        ),
        check(
            item_id="futures-prediction-lane-packets-visible",
            requirement="Split the broad strategy backlog into safe futures and prediction-market research packets for weaker agents.",
            status="pass" if source_lane_packets_visible else "blocked",
            artifact=".rumbling-hedge/state/bill-source-hygiene-plan.latest.json",
            evidence={
                "futuresPacket": {
                    "id": futures_lane_packet.get("id"),
                    "decision": futures_lane_packet.get("decision"),
                    "pathCount": futures_lane_packet.get("pathCount"),
                    "safeToStageAutomatically": futures_lane_packet.get("safeToStageAutomatically"),
                    "writesOrders": futures_lane_packet.get("writesOrders"),
                    "touchesBroker": futures_lane_packet.get("touchesBroker"),
                    "movesFunds": futures_lane_packet.get("movesFunds"),
                    "paths": futures_lane_paths[:24],
                    "commands": futures_lane_commands,
                },
                "predictionPacket": {
                    "id": prediction_lane_packet.get("id"),
                    "decision": prediction_lane_packet.get("decision"),
                    "pathCount": prediction_lane_packet.get("pathCount"),
                    "safeToStageAutomatically": prediction_lane_packet.get("safeToStageAutomatically"),
                    "writesOrders": prediction_lane_packet.get("writesOrders"),
                    "touchesBroker": prediction_lane_packet.get("touchesBroker"),
                    "movesFunds": prediction_lane_packet.get("movesFunds"),
                    "paths": prediction_lane_paths[:24],
                    "commands": prediction_lane_commands,
                },
            },
            blocker=None if source_lane_packets_visible else "futures/prediction lane packets are missing, unsafe, mixed with execution paths, or lack evidence commands",
        ),
        check(
            item_id="source-packet-review-visible",
            requirement="Review futures and prediction source packets into keep/review/shadow classifications without clearing source hygiene.",
            status="pass" if source_packet_review_visible else "blocked",
            artifact=".rumbling-hedge/state/bill-source-packet-review.latest.json",
            evidence={
                "decision": source_packet_review.get("decision"),
                "reviewedPacketCount": source_packet_review.get("reviewedPacketCount"),
                "missingPackets": source_packet_review.get("missingPackets", []),
                "classificationCounts": source_packet_review.get("classificationCounts", {}),
                "manualClearanceProposal": {
                    "decision": manual_clearance.get("decision"),
                    "nextCommands": manual_clearance.get("nextCommands", []),
                    "hardBlockers": manual_clearance.get("hardBlockers", []),
                    "laneProposals": [
                        {
                            "lane": lane.get("lane"),
                            "reviewFirst": lane.get("reviewFirst", []),
                            "keepResearchCandidates": lane.get("keepResearchCandidates", []),
                            "shadowOnly": lane.get("shadowOnly", []),
                            "quarantineReview": lane.get("quarantineReview", []),
                            "dependencyReviewed": lane.get("dependencyReviewed", []),
                            "historicalReference": lane.get("historicalReference", []),
                            "retiredReference": lane.get("retiredReference", []),
                            "safeToStageAutomatically": lane.get("safeToStageAutomatically"),
                            "writesOrders": lane.get("writesOrders"),
                            "touchesBroker": lane.get("touchesBroker"),
                            "movesFunds": lane.get("movesFunds"),
                        }
                        for lane in manual_lane_proposals
                        if isinstance(lane, dict)
                    ],
                },
                "packets": [
                    {
                        "id": packet.get("id"),
                        "lane": packet.get("lane"),
                        "decision": packet.get("decision"),
                        "packetDecision": packet.get("packetDecision"),
                        "pathCount": packet.get("pathCount"),
                        "classificationCounts": packet.get("classificationCounts", {}),
                        "firstCommand": packet.get("firstCommand"),
                        "researchOnly": packet.get("researchOnly"),
                        "safeToStageAutomatically": packet.get("safeToStageAutomatically"),
                        "writesOrders": packet.get("writesOrders"),
                        "touchesBroker": packet.get("touchesBroker"),
                        "movesFunds": packet.get("movesFunds"),
                    }
                    for packet in packet_review_packets
                    if isinstance(packet, dict)
                ],
            },
            blocker=None if source_packet_review_visible else "source packet review is missing, unsafe, incomplete, lacks manual clearance proposal, or is not linked to both research lanes",
        ),
        check(
            item_id="obsidian-resource-inventory-visible",
            requirement="Keep Bill/Hermes resources linked in Obsidian with a full manifest, prioritized outside-vault section, and execution-review labeling.",
            status="pass" if obsidian_resource_inventory_visible else "blocked",
            artifact="/Users/brain/Documents/memorybrain/Research-Catalog/Bill-Resource-Inventory.md",
            evidence={
                "hasInventoryTitle": "# Bill Resource Inventory" in resource_inventory_text,
                "hasFullManifest": "Bill-Resource-Full-Manifest.jsonl" in resource_inventory_text,
                "hasPriorityOutsideObsidian": "## Priority Outside Obsidian" in resource_inventory_text,
                "hasDisplayPolicy": "Display policy: highest-signal Bill/Hermes resources first" in resource_inventory_text,
                "hasExecutionReviewLabel": "`execution-review`" in resource_inventory_text,
            },
            blocker=None if obsidian_resource_inventory_visible else "Obsidian resource inventory is missing priority outside-vault indexing or execution-review labeling",
        ),
        check(
            item_id="data-intake-visible",
            requirement="Make dirty market data visible with data-validation command sets, without treating research bars as execution-grade data.",
            status="pass" if data_intake_evidence_visible else "blocked",
            artifact=".rumbling-hedge/state/bill-data-intake-manifest.latest.json",
            evidence={
                "decision": data_intake.get("decision"),
                "dirtyDataFileCount": data_intake.get("dirtyDataFileCount"),
                "csvFileCount": data_intake.get("csvFileCount"),
                "executionGradeData": data_intake.get("executionGradeData"),
                "readyForExecutionData": data_intake.get("readyForExecutionData"),
                "riskCounts": data_intake.get("riskCounts", {}),
                "validationCommandSets": data_validation_sets,
            },
            blocker=None if data_intake_evidence_visible else "data intake manifest is missing, unsafe, or lacks validation command sets",
        ),
        check(
            item_id="open-session-data-proof-visible",
            requirement="Keep a deterministic data-only open-session futures proof runner visible without clearing execution-grade data.",
            status="pass" if data_proof_visible else "blocked",
            artifact=".rumbling-hedge/state/bill-open-session-data-proof.latest.json",
            evidence={
                "mode": open_session_data_proof.get("mode"),
                "allCommandsPassed": open_session_data_proof.get("allCommandsPassed"),
                "executionGradeDataProofPassed": open_session_data_proof.get("executionGradeDataProofPassed"),
                "failedStepIds": open_session_data_proof.get("failedStepIds", []),
                "brokerReadOnlyStepIncluded": open_session_data_proof.get("brokerReadOnlyStepIncluded"),
                "plannedStepIds": proof_step_ids,
                "stateSummary": open_session_data_proof.get("stateSummary", {}),
                "pausedByTopstepSessionSafety": control_proof_paused_by_topstep,
            },
            blocker=None if data_proof_visible else "open-session data proof runner is missing or unsafe",
        ),
        check(
            item_id="execution-intake-visible",
            requirement="Map dirty execution-live files to firewall evidence without clearing or approving execution.",
            status="pass" if execution_intake_evidence_visible else "blocked",
            artifact=".rumbling-hedge/state/bill-execution-intake-manifest.latest.json",
            evidence={
                "decision": execution_intake.get("decision"),
                "dirtyExecutionFileCount": execution_intake.get("dirtyExecutionFileCount"),
                "canonicalExecutionLiveDirtyCount": execution_intake.get("canonicalExecutionLiveDirtyCount"),
                "executionAdjacentFileCount": execution_intake.get("executionAdjacentFileCount"),
                "classificationCounts": execution_intake.get("classificationCounts", {}),
                "allFirewallCommandsPassed": execution_intake.get("allFirewallCommandsPassed"),
                "uncoveredExecutionPaths": uncovered_execution_paths,
                "executionLocked": execution_intake.get("executionLocked"),
                "validationCommandSets": execution_validation_sets,
            },
            blocker=None if execution_intake_evidence_visible else "execution intake manifest is missing, unsafe, has uncovered execution paths, failed firewalls, or lacks validation command sets",
        ),
        check(
            item_id="signal-quality-visible",
            requirement="Expose deterministic signal-quality, signal-source authority, and shadow-cron evidence without allowing proxy/fallback/research signals to approve execution.",
            status="pass" if signal_quality_visible and signal_source_truth_visible else "blocked",
            artifact=".rumbling-hedge/state/signal-quality-advisor.latest.json and signal-source-truth-audit.latest.json",
            evidence={
                "decision": signal_quality.get("decision"),
                "overallRating": signal_quality.get("overallRating"),
                "blockers": signal_quality.get("blockers", []),
                "warnings": signal_quality.get("warnings", []),
                "readyForExecution": signal_quality.get("readyForExecution"),
                "shadowSignalRows": shadow_signal_rows,
                "sourceTruthDecision": signal_source_truth.get("decision"),
                "sourceTruthIssueCount": signal_source_truth.get("issueCount"),
                "sourceTruthIssues": source_truth_issues,
                "sourceTruthRoles": {
                    key: {
                        "role": value.get("role"),
                        "authority": value.get("authority"),
                        "promotedLikeExecution": value.get("promotedLikeExecution"),
                    }
                    for key, value in source_truth_roles.items()
                },
            },
            blocker=None if signal_quality_visible and signal_source_truth_visible else "signal quality/source-truth evidence is missing, stale/blocked, unsafe, or contains promoted/tradable shadow/research signals",
        ),
        check(
            item_id="cron-control-trust-not-cleared",
            requirement="Do not call the control plane cleared while active crons reference dirty or quarantined execution-live scripts.",
            status="pass" if cron_control_trust_cleared else "blocked",
            artifact=".rumbling-hedge/state/cron-state-validator.latest.json",
            evidence={
                "summary": cron_validator.get("summary"),
                "activeDirtyExecutionLiveScriptReferenceCount": active_dirty_execution_ref_count,
                "activeDirtyExecutionLiveScriptReferences": active_dirty_execution_refs,
                "blockingIssues": blocking_cron_issues,
                "activeTradingAgentBackedCount": cron_trust.get("activeTradingAgentBackedCount"),
                "noAgentMetadataMismatchCount": cron_trust.get("noAgentMetadataMismatchCount"),
                "executionIntakeManifest": cron_trust.get("executionIntakeManifest"),
            },
            blocker=None if cron_control_trust_cleared else "cron validator has P0/P1 issues or active jobs referencing dirty/quarantined execution-live scripts",
        ),
        check(
            item_id="codex-automation-control-visible",
            requirement="Codex app automations must be visible, locked, storage-bounded, and non-duplicative before control-plane completion.",
            status="pass" if codex_automation_visible else "blocked",
            artifact=".rumbling-hedge/state/codex-automation-audit.latest.json",
            evidence={
                "status": codex_automation.get("status"),
                "activeBillAutomationCount": codex_automation.get("activeBillAutomationCount"),
                "activeFuturesOpenSessionProofCount": codex_automation.get("activeFuturesOpenSessionProofCount"),
                "activeFuturesOpenSessionProofIds": active_futures_open_session_proof_ids,
                "activeFuturesOpenSessionProofConflictIds": active_futures_open_session_proof_conflict_ids,
                "activePredictionCaptureIds": active_prediction_capture_ids,
                "pausedPredictionCaptureIds": paused_prediction_capture_ids,
                "blockers": codex_automation_blockers,
                "writesOrders": codex_automation.get("writesOrders"),
                "touchesBroker": codex_automation.get("touchesBroker"),
                "readyForExecution": codex_automation.get("readyForExecution"),
            },
            blocker=None if codex_automation_visible else "Codex automation audit is missing/blocked, prediction capture automations are duplicated/unsafe, or futures proof automations conflict",
        ),
        check(
            item_id="runtime-architecture-control-visible",
            requirement="n8n, Hermes/Kanban, cron, and AI-Scientist-style research loops must be visible as research-only control-plane evidence.",
            status="pass" if runtime_architecture_visible else "blocked",
            artifact=".rumbling-hedge/state/bill-runtime-architecture-audit.latest.json",
            evidence={
                "decision": runtime_architecture.get("decision"),
                "warnings": (
                    runtime_architecture.get("warnings")
                    if isinstance(runtime_architecture.get("warnings"), list)
                    else []
                ),
                "n8nWorkflowCount": runtime_n8n.get("workflowCount"),
                "n8nActiveBillWorkflowCount": runtime_n8n.get("activeBillWorkflowCount"),
                "kanbanStatusCounts": runtime_kanban.get("statusCounts"),
                "cronActiveCount": runtime_cron.get("activeCount"),
                "cronActiveExecutionLikeCount": runtime_cron.get("activeExecutionLikeCount"),
                "aiScientistHardSafetyOk": runtime_ai_scientist.get("hardSafetyOk"),
                "aiScientistDecision": runtime_ai_scientist.get("decision"),
                "writesOrders": runtime_architecture.get("writesOrders"),
                "touchesBroker": runtime_architecture.get("touchesBroker"),
                "readyForExecution": runtime_architecture.get("readyForExecution"),
            },
            blocker=None if runtime_architecture_visible else "runtime architecture audit is missing, stale, or does not prove research-only separation",
        ),
        check(
            item_id="futures-demo-not-cleared",
            requirement="Do not call futures demo-ready until current-session depth, read-only broker/local parity, and execution-grade realtime data pass.",
            status="blocked",
            artifact=".rumbling-hedge/state/futures-data-requirements.latest.json, futures-broker-parity-plan.latest.json, and futures-nq-research-cycle.latest.json",
            evidence={
                "requirementsDecision": futures_requirements.get("decision"),
                "readyForDemoExpansion": futures_requirements.get("readyForDemoExpansion"),
                "futuresBlockers": futures_blockers,
                "brokerParityMissingProofs": broker_parity_missing,
                "topstepCurrentBarsProofPassed": broker_parity_current.get("topstepCurrentBarsProofPassed"),
                "topstepBrokerLocalBarParityPassed": broker_parity_current.get("topstepBrokerLocalBarParityPassed"),
                "realtimeReadyForExecutionData": broker_parity_current.get("realtimeReadyForExecutionData"),
                "topstepRealtimeReadyForExecutionDataProof": broker_parity_current.get("topstepRealtimeReadyForExecutionDataProof"),
                "topstepRealtimeWritesCanonicalQuoteState": broker_parity_current.get("topstepRealtimeWritesCanonicalQuoteState"),
            },
            blocker=(
                "futures demo expansion remains blocked by current-session depth, source hygiene, and clearance evidence; read-only Topstep broker/local parity and realtime proof are visible separately"
                if futures_realtime_proof_cleared
                else "futures demo expansion remains blocked by current-session depth and execution-grade realtime data; read-only Topstep broker/local parity is visible separately"
            ),
        ),
        check(
            item_id="prediction-paper-not-cleared",
            requirement="Do not call prediction markets paper/live ready until event-lag replay has complete no-lookahead windows and positive evidence.",
            status="blocked",
            artifact=".rumbling-hedge/state/prediction-event-capture-cycle.latest.json and prediction-event-market-mapping-plan.latest.json",
            evidence={
                "captureDecision": prediction_capture.get("decision"),
                "readyForPaper": prediction_capture.get("readyForPaper"),
                "captureCycleEvidencePassed": prediction_capture.get("captureCycleEvidencePassed"),
                "paperPromotionEvidencePassed": prediction_capture.get("paperPromotionEvidencePassed"),
                "paperPromotionBlockers": (
                    prediction_capture.get("paperPromotionBlockers")
                    if isinstance(prediction_capture.get("paperPromotionBlockers"), list)
                    else []
                ),
                "executedRecorder": (
                    prediction_capture.get("executedRecorder")
                    if isinstance(prediction_capture.get("executedRecorder"), dict)
                    else {}
                ),
                "completeEventCount": prediction_capture.get("completeEventCount"),
                "completeWindowCount": prediction_capture.get("completeWindowCount"),
                "repricedWindowCount": prediction_capture.get("repricedWindowCount"),
                "eventLagReplayDecision": prediction_capture.get("eventLagReplayDecision"),
                "eventLagResearchWatchReady": bool(prediction_capture.get("eventLagResearchWatchReady")),
                "eventLagSensitivity": event_lag_sensitivity_summary,
                "eventLagWatchReview": event_lag_watch_review_summary,
                "eventLagManualReview": event_lag_manual_review_summary,
                "eventMarketMapping": prediction_market_mapping_summary,
                "eventMappingExclusions": prediction_mapping_exclusion_summary,
                "eventMappingRefinement": prediction_mapping_refinement_summary,
                "paperPromotionGate": {
                    "present": bool(prediction_paper_promotion_gate),
                    "decision": prediction_paper_promotion_gate.get("decision"),
                    "passCount": prediction_paper_promotion_gate.get("passCount"),
                    "blockedCount": prediction_paper_promotion_gate.get("blockedCount"),
                    "blockedIds": (
                        prediction_paper_promotion_gate.get("blockedIds")
                        if isinstance(prediction_paper_promotion_gate.get("blockedIds"), list)
                        else []
                    ),
                    "readyForPaper": bool(prediction_paper_promotion_gate.get("readyForPaper")),
                    "readyForPaperReview": bool(prediction_paper_promotion_gate.get("readyForPaperReview")),
                    "readyForExecution": bool(prediction_paper_promotion_gate.get("readyForExecution")),
                    "writesOrders": bool(prediction_paper_promotion_gate.get("writesOrders")),
                    "touchesBroker": bool(prediction_paper_promotion_gate.get("touchesBroker")),
                },
                "blockers": prediction_blockers,
            },
            blocker=prediction_paper_blocker,
        ),
        check(
            item_id="execution-grade-data-not-cleared",
            requirement="Require execution-grade realtime futures data before any route can be approved.",
            status="pass" if futures_realtime_proof_cleared else "blocked",
            artifact=".rumbling-hedge/state/realtime-data-preflight.latest.json, topstep-realtime-proof.latest.json, and databento-realtime-smoke.latest.json",
            evidence={
                "preflightDecision": realtime_preflight.get("decision"),
                "readyForExecutionData": realtime_preflight.get("readyForExecutionData"),
                "databentoStatus": databento_smoke.get("status"),
                "readyForExecutionDataProof": databento_smoke.get("readyForExecutionDataProof"),
                "topstepRealtimeReadyForExecutionDataProof": broker_parity_current.get("topstepRealtimeReadyForExecutionDataProof"),
                "topstepRealtimeWritesCanonicalQuoteState": broker_parity_current.get("topstepRealtimeWritesCanonicalQuoteState"),
                "futuresRequirementsExecutionGradeRealtimeProofPassed": futures_requirements.get("executionGradeRealtimeProofPassed"),
                "realtimeBlockers": realtime_blockers,
            },
            blocker=(
                "execution-grade realtime TopstepX/ProjectX proof is visible; keep this gate blocked only until source/depth/approval artifacts regenerate"
                if futures_realtime_proof_cleared
                else "execution-grade realtime data is unavailable"
            ),
        ),
        check(
            item_id="source-hygiene-not-cleared",
            requirement="Do not call demo/live ready while source tree and execution-live files are dirty.",
            status="blocked",
            artifact=".rumbling-hedge/state/worktree-consolidation.latest.json, bill-sibling-worktree-intake.latest.json, and live-readiness-gate.latest.json",
            evidence={
                "sourceCleanBlockers": source_blockers or worktree_blockers,
                "liveBlockers": live_blockers,
                "siblingWorktreeIntake": sibling_worktree_summary,
                "staleStrategyClaimGuard": {
                    "present": bool(stale_claim_guard),
                    "decision": stale_claim_guard.get("decision"),
                    "status": stale_claim_guard.get("status"),
                    "findingCount": stale_claim_guard.get("findingCount"),
                },
            },
            blocker="source hygiene remains dirty",
        ),
        check(
            item_id="storage-plan-safe",
            requirement="Storage cleanup must remain non-destructive unless separately approved.",
            status="pass" if storage.get("deletesFiles") is False and storage.get("movesFiles") is False else "blocked",
            artifact=".rumbling-hedge/state/hermes-storage-audit.latest.json",
            evidence={
                "totalSize": storage.get("totalSize"),
                "archiveCandidateSize": storage.get("archiveCandidateSize"),
                "movesFiles": storage.get("movesFiles"),
                "deletesFiles": storage.get("deletesFiles"),
            },
            blocker=None if storage.get("deletesFiles") is False and storage.get("movesFiles") is False else "storage plan is destructive",
        ),
        check(
            item_id="clearance-evidence-not-sufficient",
            requirement="Treat passing verifiers as supporting evidence only, not goal completion.",
            status="pass" if clearance_evidence.get("allCommandsPassed") is True else "blocked",
            artifact=".rumbling-hedge/state/bill-clearance-evidence.latest.json",
            evidence={
                "status": clearance_evidence.get("status"),
                "allCommandsPassed": clearance_evidence.get("allCommandsPassed"),
                "failedCommandIds": clearance_evidence.get("failedCommandIds", []),
            },
            blocker=None if clearance_evidence.get("allCommandsPassed") is True else "clearance evidence commands failed",
        ),
    ]

    prompt_to_artifact_checklist = [
        prompt_artifact_check(
            item_id="execution-remains-locked",
            prompt_requirement="Keep execution locked until evidence gates pass.",
            artifacts=[
                ".rumbling-hedge/state/bill-clearance-handoff.latest.json",
                str(DAILY),
                ".rumbling-hedge/state/bill-goal-completion-audit.latest.json",
            ],
            status="pass" if execution_locked and daily_blocked else "blocked",
            evidence={
                "executionLocked": execution_locked,
                "dailyBlocked": daily_blocked,
                "writesOrders": False,
                "touchesBroker": False,
            },
            uncovered=None if execution_locked and daily_blocked else [
                "daily plan or clearance handoff does not prove route approval is blocked",
            ],
        ),
        prompt_artifact_check(
            item_id="futures-frontier-wired",
            prompt_requirement="Focus the next research/build loop mainly on futures and make demo expansion evidence-gated.",
            artifacts=[
                ".rumbling-hedge/state/futures-evidence-triage.latest.json",
                ".rumbling-hedge/state/futures-nq-research-cycle.latest.json",
                ".rumbling-hedge/state/futures-data-requirements.latest.json",
                ".rumbling-hedge/state/futures-broker-parity-plan.latest.json",
                ".rumbling-hedge/state/bill-next-research-actions.latest.json",
            ],
            status="blocked" if not futures_cycle_safe else "partial",
            evidence={
                "futuresWired": futures_wired,
                "readyForDemoExpansion": futures_requirements.get("readyForDemoExpansion"),
                "futuresBlockers": futures_blockers,
                "historicalCurrentParitySummary": (
                    futures_cycle.get("historical", {}).get("currentParitySummary")
                    if isinstance(futures_cycle.get("historical"), dict)
                    else {}
                ),
                "brokerParityMissingProofs": broker_parity_missing,
            },
            uncovered=[
                "open-session execution-grade realtime proof",
                "read-only broker/current parity proof",
                "daily route approval remains blocked",
            ],
        ),
        prompt_artifact_check(
            item_id="prediction-frontier-wired",
            prompt_requirement="Focus the next research/build loop mainly on prediction markets and require no-lookahead paper evidence.",
            artifacts=[
                ".rumbling-hedge/state/prediction-event-capture-cycle.latest.json",
                ".rumbling-hedge/state/prediction-event-market-mapping-plan.latest.json",
                ".rumbling-hedge/state/prediction-event-mapping-refinement.latest.json",
                ".rumbling-hedge/state/prediction-event-paper-promotion-gate.latest.json",
                ".rumbling-hedge/state/prediction-evidence-triage.latest.json",
                ".rumbling-hedge/state/bill-next-research-actions.latest.json",
            ],
            status="partial" if prediction_capture_safe and prediction_recorder_wired else "blocked",
            evidence={
                "predictionRecorderWired": prediction_recorder_wired,
                "readyForPaper": prediction_capture.get("readyForPaper"),
                "completeEventCount": prediction_capture.get("completeEventCount"),
                "repricedWindowCount": prediction_capture.get("repricedWindowCount"),
                "eventLagReplayDecision": prediction_capture.get("eventLagReplayDecision"),
                "eventLagResearchWatchReady": bool(prediction_capture.get("eventLagResearchWatchReady")),
                "eventLagSensitivity": event_lag_sensitivity_summary,
                "eventLagWatchReview": event_lag_watch_review_summary,
                "eventLagManualReview": event_lag_manual_review_summary,
                "eventMarketMapping": prediction_market_mapping_summary,
                "eventMappingExclusions": prediction_mapping_exclusion_summary,
                "eventMappingRefinement": prediction_mapping_refinement_summary,
                "paperPromotionGate": {
                    "present": bool(prediction_paper_promotion_gate),
                    "decision": prediction_paper_promotion_gate.get("decision"),
                    "passCount": prediction_paper_promotion_gate.get("passCount"),
                    "blockedCount": prediction_paper_promotion_gate.get("blockedCount"),
                    "blockedIds": (
                        prediction_paper_promotion_gate.get("blockedIds")
                        if isinstance(prediction_paper_promotion_gate.get("blockedIds"), list)
                        else []
                    ),
                    "readyForPaper": bool(prediction_paper_promotion_gate.get("readyForPaper")),
                    "readyForPaperReview": bool(prediction_paper_promotion_gate.get("readyForPaperReview")),
                },
                "blockers": prediction_blockers,
            },
            uncovered=[
                "explicit paper-promotion gate remains blocked",
                "no-lookahead replay with paper-grade event evidence",
                "fillable live book, post-spread CLOB edge, clean mapping, and resolved-label review before paper",
            ],
        ),
        prompt_artifact_check(
            item_id="codex-automation-loops-controlled",
            prompt_requirement="Keep automated research loops visible, storage-safe, and separated from execution.",
            artifacts=[
                ".rumbling-hedge/state/codex-automation-audit.latest.json",
                "/Users/brain/.codex/automations/bill-prediction-forward-clob-capture/automation.toml",
                "/Users/brain/.codex/automations/bill-prediction-event-clob-capture/automation.toml",
                "/Users/brain/.codex/automations/bill-futures-open-session-data-proof/automation.toml",
                "/Users/brain/.codex/automations/bill-open-session-data-proof/automation.toml",
            ],
            status="pass" if codex_automation_visible else "blocked",
            evidence={
                "activePredictionCaptureIds": active_prediction_capture_ids,
                "pausedPredictionCaptureIds": paused_prediction_capture_ids,
                "activeFuturesOpenSessionProofIds": active_futures_open_session_proof_ids,
                "activeFuturesOpenSessionProofConflictIds": active_futures_open_session_proof_conflict_ids,
                "blockers": codex_automation_blockers,
                "readyForExecution": codex_automation.get("readyForExecution"),
            },
            uncovered=None if codex_automation_visible else [
                "Codex automation audit must pass with one active bounded forward CLOB capture, duplicate capture paused, and no same-window futures proof conflict",
            ],
        ),
        prompt_artifact_check(
            item_id="runtime-architecture-and-ai-scientist-wired",
            prompt_requirement="Refresh the local picture across Obsidian, Hermes/Kanban, n8n, cron, and AI-Scientist-style loops while keeping research separate from execution.",
            artifacts=[
                ".rumbling-hedge/state/bill-runtime-architecture-audit.latest.json",
                str(HERMES / f"BILL-HERMES-SYSTEM-ARCHITECTURE-{current_utc_date()}.md"),
                "ai-scientist-templates/financial_strategy/experiment.py",
            ],
            status="pass" if runtime_architecture_visible else "blocked",
            evidence={
                "decision": runtime_architecture.get("decision"),
                "warnings": (
                    runtime_architecture.get("warnings")
                    if isinstance(runtime_architecture.get("warnings"), list)
                    else []
                ),
                "n8nWorkflowCount": runtime_n8n.get("workflowCount"),
                "n8nActiveBillWorkflowCount": runtime_n8n.get("activeBillWorkflowCount"),
                "kanbanStatusCounts": runtime_kanban.get("statusCounts"),
                "cronActiveCount": runtime_cron.get("activeCount"),
                "aiScientistHardSafetyOk": runtime_ai_scientist.get("hardSafetyOk"),
                "aiScientistPromotionBlockers": (
                    runtime_ai_scientist.get("promotionBlockers")
                    if isinstance(runtime_ai_scientist.get("promotionBlockers"), list)
                    else []
                ),
                "readyForExecution": runtime_architecture.get("readyForExecution"),
            },
            uncovered=None if runtime_architecture_visible else [
                "runtime architecture audit must prove n8n, Kanban, cron, and AI-Scientist loops are visible and research-only",
            ],
        ),
        prompt_artifact_check(
            item_id="alpha-tooling-installed-or-wired",
            prompt_requirement="Install or wire the necessary alpha research tooling and point the loop at useful futures/prediction lanes without turning it into execution authority.",
            artifacts=[
                ".rumbling-hedge/state/alpha-research-tooling-check.latest.json",
                ".rumbling-hedge/state/alpha-research-direction-audit.latest.json",
                ".rumbling-hedge/state/databento-orderflow-feature-smoke.latest.json",
                ".rumbling-hedge/state/bill-next-research-actions.latest.json",
            ],
            status="pass" if tooling.get("readyForResearchLoop") is True and queue_safe else "partial",
            evidence={
                "toolingStatus": tooling.get("status"),
                "readyForResearchLoop": tooling.get("readyForResearchLoop"),
                "queueSafe": queue_safe,
                "directionDecision": alpha_direction.get("decision"),
                "directionQueueSafe": alpha_direction.get("queueSafe"),
                "continueLanes": [
                    item.get("id")
                    for item in (
                        alpha_direction.get("continueLanes")
                        if isinstance(alpha_direction.get("continueLanes"), list)
                        else []
                    )
                    if isinstance(item, dict)
                ],
                "retireOrQuarantineLanes": [
                    item.get("id")
                    for item in (
                        alpha_direction.get("retireOrQuarantineLanes")
                        if isinstance(alpha_direction.get("retireOrQuarantineLanes"), list)
                        else []
                    )
                    if isinstance(item, dict)
                ],
                "nextOneVariableTest": (
                    alpha_direction.get("nextOneVariableTest")
                    if isinstance(alpha_direction.get("nextOneVariableTest"), dict)
                    else {}
                ),
            },
            uncovered=None if tooling.get("readyForResearchLoop") is True and queue_safe else [
                "tooling check or research queue is not green",
            ],
        ),
        prompt_artifact_check(
            item_id="youtube-gold-source-cards-wired",
            prompt_requirement="Treat Hermes/YouTube 'gold' strategy inputs as durable source cards and hypothesis seeds, not executable evidence.",
            artifacts=[
                ".rumbling-hedge/state/research-seed-triage.latest.json",
                "/Users/brain/Documents/memorybrain/Research-Catalog/Youtube-Transcript-Source-Cards-2026-05-30.md",
                ".rumbling-hedge/state/bill-next-research-actions.latest.json",
            ],
            status="pass" if youtube_source_cards_wired else "partial",
            evidence={
                "seedDecision": seed_triage.get("decision"),
                "queuedYouTubeSeeds": seed_summary.get("queuedYouTubeSeeds"),
                "executableSeeds": seed_summary.get("executableSeeds"),
                "candidateRetestSeeds": seed_summary.get("candidateRetestSeeds"),
                "sourceCardsPresent": youtube_source_cards.get("present"),
                "sourceCardsPath": youtube_source_cards.get("path"),
                "sourceCardResearcherRun": youtube_source_cards.get("researcherRun"),
                "targetsSucceeded": youtube_source_cards.get("targetsSucceeded"),
                "targetsAttempted": youtube_source_cards.get("targetsAttempted"),
                "strategyHypothesesPromoted": youtube_source_cards.get("strategyHypothesesPromoted"),
                "executionRelevant": youtube_source_cards.get("executionRelevant"),
                "cards": [
                    {
                        "title": item.get("title"),
                        "decision": item.get("decision"),
                        "lane": item.get("lane"),
                    }
                    for item in (youtube_source_cards.get("cards") or [])[:5]
                    if isinstance(item, dict)
                ],
                "readyForExecution": seed_triage.get("readyForExecution"),
            },
            uncovered=None if youtube_source_cards_wired else [
                "queued YouTube transcript/source-card evidence is missing or not explicitly demoted to non-executable research",
            ],
        ),
        prompt_artifact_check(
            item_id="source-hygiene-not-faked",
            prompt_requirement="Clear Bill/Hermes only when source hygiene is real, not when manifests merely exist.",
            artifacts=[
                ".rumbling-hedge/state/bill-source-intake-manifest.latest.json",
                ".rumbling-hedge/state/bill-source-hygiene-plan.latest.json",
                ".rumbling-hedge/state/bill-source-packet-review.latest.json",
                ".rumbling-hedge/state/stale-strategy-claim-guard.latest.json",
                ".rumbling-hedge/state/bill-sibling-worktree-intake.latest.json",
                ".rumbling-hedge/state/worktree-consolidation.latest.json",
            ],
            status="blocked",
            evidence={
                "sourceHygieneCleared": source_hygiene.get("sourceHygieneCleared"),
                "dirtyStatusCount": source_hygiene.get("dirtyStatusCount"),
                "reviewBacklogCount": source_review_backlog_count,
                "hygienePlanReviewBacklogCount": source_hygiene.get("reviewBacklogCount"),
                "sourceCleanBlockers": source_blockers or worktree_blockers,
                "siblingWorktreeIntake": sibling_worktree_summary,
                "staleStrategyClaimGuard": {
                    "present": bool(stale_claim_guard),
                    "decision": stale_claim_guard.get("decision"),
                    "status": stale_claim_guard.get("status"),
                    "findingCount": stale_claim_guard.get("findingCount"),
                },
            },
            uncovered=[
                "manual review/staging decision for dirty source packets",
                "execution-live dirty files remain quarantined",
                "sibling worktree remains quarantine/selective-intake only",
            ],
        ),
        prompt_artifact_check(
            item_id="completion-audit-uses-real-evidence",
            prompt_requirement="Before calling the goal done, map every explicit requirement to actual artifacts and treat uncertainty as incomplete.",
            artifacts=[
                ".rumbling-hedge/state/bill-goal-completion-audit.latest.json",
                str(default_markdown_path()),
            ],
            status="pass",
            evidence={
                "checkCount": len(checklist),
                "blockedIds": [item["id"] for item in checklist if item["status"] == "blocked"],
                "proxySignalsDoNotClear": True,
            },
        ),
    ]

    blocked = [item for item in checklist if item["status"] == "blocked"]
    missing = [item for item in checklist if item["status"] == "missing"]
    prompt_uncovered = [
        item
        for item in prompt_to_artifact_checklist
        if item.get("status") != "pass"
    ]
    goal_complete = not blocked and not missing and not prompt_uncovered
    return {
        "command": "bill-goal-completion-audit",
        "generatedAt": now_iso(),
        "objective": OBJECTIVE,
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "readyForExecution": False,
        "readyForDemoExpansion": False,
        "readyForLive": False,
        "goalComplete": goal_complete,
        "decision": "goal-complete" if goal_complete else "continue-research-only-locked",
        "checkCount": len(checklist),
        "passCount": sum(1 for item in checklist if item["status"] == "pass"),
        "blockedCount": len(blocked),
        "blockedIds": [item["id"] for item in blocked],
        "promptToArtifactChecklist": prompt_to_artifact_checklist,
        "promptUncoveredCount": len(prompt_uncovered),
        "promptUncoveredIds": [item["id"] for item in prompt_uncovered],
        "checklist": checklist,
        "hardRule": "Do not call update_goal complete while blockedIds is non-empty.",
    }


def render_markdown(payload: dict[str, Any]) -> str:
    generated_at = str(payload.get("generatedAt") or "")
    audit_date = generated_at[:10] if len(generated_at) >= 10 else current_utc_date()
    lines = [
        f"# Bill Goal Completion Audit - {audit_date}",
        "",
        "Parent hub: [[BILL-CONTROL-HUB]]",
        "",
        "This is a read-only completion guard. It does not approve paper, demo, live, funding, orders, sizing, or broker routing.",
        "",
        "## Decision",
        "",
        f"- Decision: `{payload.get('decision')}`",
        f"- Goal complete: `{payload.get('goalComplete')}`",
        f"- Pass count: `{payload.get('passCount')}` / `{payload.get('checkCount')}`",
        f"- Blocked count: `{payload.get('blockedCount')}`",
        f"- Blocked ids: `{payload.get('blockedIds')}`",
        "",
        "## Objective",
        "",
        payload.get("objective", ""),
        "",
        "## Prompt To Artifact Checklist",
        "",
    ]
    for item in payload.get("promptToArtifactChecklist") or []:
        lines.append(f"### {item.get('id')}")
        lines.append("")
        lines.append(f"- Status: `{item.get('status')}`")
        lines.append(f"- Prompt requirement: {item.get('promptRequirement')}")
        lines.append(f"- Artifacts: `{item.get('artifacts')}`")
        if item.get("uncovered"):
            lines.append(f"- Uncovered: `{item.get('uncovered')}`")
        lines.append("")
    lines.extend([
        "## Checklist",
        "",
    ])
    for item in payload.get("checklist") or []:
        lines.append(f"### {item.get('id')}")
        lines.append("")
        lines.append(f"- Status: `{item.get('status')}`")
        lines.append(f"- Requirement: {item.get('requirement')}")
        lines.append(f"- Artifact: `{item.get('artifact')}`")
        if item.get("blocker"):
            lines.append(f"- Blocker: {item.get('blocker')}")
        lines.append("")
    lines.extend(["## Hard Rule", "", f"- {payload.get('hardRule')}", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Bill/Hermes active goal completion against artifacts.")
    parser.add_argument("--handoff", default=str(STATE / "bill-clearance-handoff.latest.json"))
    parser.add_argument("--tooling", default=str(STATE / "alpha-research-tooling-check.latest.json"))
    parser.add_argument("--alpha-direction", default=str(STATE / "alpha-research-direction-audit.latest.json"))
    parser.add_argument("--next-actions", default=str(STATE / "bill-next-research-actions.latest.json"))
    parser.add_argument("--futures-cycle", default=str(STATE / "futures-nq-research-cycle.latest.json"))
    parser.add_argument("--futures-requirements", default=str(STATE / "futures-data-requirements.latest.json"))
    parser.add_argument("--futures-broker-parity", default=str(STATE / "futures-broker-parity-plan.latest.json"))
    parser.add_argument("--prediction-capture", default=str(STATE / "prediction-event-capture-cycle.latest.json"))
    parser.add_argument("--prediction-market-mapping", default=str(STATE / "prediction-event-market-mapping-plan.latest.json"))
    parser.add_argument("--prediction-mapping-refinement", default=str(STATE / "prediction-event-mapping-refinement.latest.json"))
    parser.add_argument("--prediction-event-lag-manual-review", default=str(STATE / "prediction-event-lag-manual-review.latest.json"))
    parser.add_argument("--prediction-paper-promotion-gate", default=str(STATE / "prediction-event-paper-promotion-gate.latest.json"))
    parser.add_argument("--realtime-preflight", default=str(STATE / "realtime-data-preflight.latest.json"))
    parser.add_argument("--databento-smoke", default=str(STATE / "databento-realtime-smoke.latest.json"))
    parser.add_argument("--worktree", default=str(STATE / "worktree-consolidation.latest.json"))
    parser.add_argument("--source-intake", default=str(STATE / "bill-source-intake-manifest.latest.json"))
    parser.add_argument("--source-hygiene", default=str(STATE / "bill-source-hygiene-plan.latest.json"))
    parser.add_argument("--source-packet-review", default=str(STATE / "bill-source-packet-review.latest.json"))
    parser.add_argument("--sibling-worktree-intake", default=str(STATE / "bill-sibling-worktree-intake.latest.json"))
    parser.add_argument("--open-session-data-proof", default=str(STATE / "bill-open-session-data-proof.latest.json"))
    parser.add_argument("--data-intake", default=str(STATE / "bill-data-intake-manifest.latest.json"))
    parser.add_argument("--execution-intake", default=str(STATE / "bill-execution-intake-manifest.latest.json"))
    parser.add_argument("--signal-quality", default=str(STATE / "signal-quality-advisor.latest.json"))
    parser.add_argument("--signal-source-truth", default=str(STATE / "signal-source-truth-audit.latest.json"))
    parser.add_argument("--cron-validator", default=str(STATE / "cron-state-validator.latest.json"))
    parser.add_argument("--codex-automation-audit", default=str(STATE / "codex-automation-audit.latest.json"))
    parser.add_argument("--runtime-architecture-audit", default=str(STATE / "bill-runtime-architecture-audit.latest.json"))
    parser.add_argument("--seed-triage", default=str(STATE / "research-seed-triage.latest.json"))
    parser.add_argument("--storage", default=str(STATE / "hermes-storage-audit.latest.json"))
    parser.add_argument("--clearance-evidence", default=str(STATE / "bill-clearance-evidence.latest.json"))
    parser.add_argument("--stale-claim-guard", default=str(STATE / "stale-strategy-claim-guard.latest.json"))
    parser.add_argument("--daily-plan", default=str(DAILY))
    parser.add_argument("--resource-inventory", default=str(VAULT / "Research-Catalog" / "Bill-Resource-Inventory.md"))
    parser.add_argument("--output", default=str(OUT))
    parser.add_argument("--markdown", default=None)
    args = parser.parse_args()

    payload = build_audit(
        handoff=read_json(Path(args.handoff)),
        tooling=read_json(Path(args.tooling)),
        alpha_direction=read_json(Path(args.alpha_direction)),
        next_actions=read_json(Path(args.next_actions)),
        futures_cycle=read_json(Path(args.futures_cycle)),
        futures_requirements=read_json(Path(args.futures_requirements)),
        futures_broker_parity=read_json(Path(args.futures_broker_parity)),
        prediction_capture=read_json(Path(args.prediction_capture)),
        prediction_market_mapping=read_json(Path(args.prediction_market_mapping)),
        prediction_mapping_refinement=read_json(Path(args.prediction_mapping_refinement)),
        prediction_event_lag_manual_review=read_json(Path(args.prediction_event_lag_manual_review)),
        prediction_paper_promotion_gate=read_json(Path(args.prediction_paper_promotion_gate)),
        realtime_preflight=read_json(Path(args.realtime_preflight)),
        databento_smoke=read_json(Path(args.databento_smoke)),
        worktree=read_json(Path(args.worktree)),
        source_intake=read_json(Path(args.source_intake)),
        data_intake=read_json(Path(args.data_intake)),
        execution_intake=read_json(Path(args.execution_intake)),
        signal_quality=read_json(Path(args.signal_quality)),
        signal_source_truth=read_json(Path(args.signal_source_truth)),
        cron_validator=read_json(Path(args.cron_validator)),
        codex_automation=read_json(Path(args.codex_automation_audit)),
        runtime_architecture=read_json(Path(args.runtime_architecture_audit)),
        seed_triage=read_json(Path(args.seed_triage)),
        storage=read_json(Path(args.storage)),
        clearance_evidence=read_json(Path(args.clearance_evidence)),
        stale_claim_guard=read_json(Path(args.stale_claim_guard)),
        daily_text=read_text(Path(args.daily_plan)),
        source_hygiene=read_json(Path(args.source_hygiene)),
        open_session_data_proof=read_json(Path(args.open_session_data_proof)),
        source_packet_review=read_json(Path(args.source_packet_review)),
        sibling_worktree_intake=read_json(Path(args.sibling_worktree_intake)),
        resource_inventory_text=read_text(Path(args.resource_inventory)),
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
