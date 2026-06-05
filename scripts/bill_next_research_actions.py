#!/usr/bin/env python3
"""Build Bill/Hermes' next research actions.

This is a deterministic, research-only handoff. It turns the current futures,
prediction-market, seed, and readiness artifacts into a concrete queue weaker
agents can run without improvising execution, sizing, or promotion.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
VAULT = Path.home() / "Documents" / "memorybrain"
HERMES = VAULT / "Agent-Hermes"
DEFAULT_OUTPUT = STATE / "bill-next-research-actions.latest.json"
PREDICTION_CAPTURE_MIN_FREE_GB = 20.0
TOPSTEP_SESSION_SAFETY = STATE / "topstep-session-safety.latest.json"


def default_markdown_path() -> Path:
    queue_date = datetime.now(timezone.utc).date().isoformat()
    return HERMES / f"bill-next-research-actions-{queue_date}.md"


FUTURES_COMMANDS: dict[str, list[str]] = {
    "fabervaale-orb-broker-grade-5m-depth": [
        "BILL_ENABLE_FUTURES_DEMO_EXECUTION=false RH_TOPSTEP_READ_ONLY=true RH_LIVE_EXECUTION_ENABLED=false npm run --silent bill:open-session-data-proof -- --run-data-only",
        "npm run --silent bill:futures-nq-historical-session-replay -- --strategy fabervaale-orb --input .rumbling-hedge/research/topstep-readonly-bars/NQ-1m-topstep-readonly.csv --cadence-minutes 1 --output .rumbling-hedge/state/futures-nq-fabervaale-orb-topstep-1m-replay.latest.json",
        "npm run --silent bill:futures-evidence-triage",
        "npm run --silent bill:next-research-actions",
    ],
    "fabervaale-orb-walkforward-depth": [
        "BILL_ENABLE_FUTURES_DEMO_EXECUTION=false RH_TOPSTEP_READ_ONLY=true RH_LIVE_EXECUTION_ENABLED=false npm run --silent bill:open-session-data-proof -- --run-data-only",
        "npm run --silent bill:futures-nq-historical-session-replay -- --strategy fabervaale-orb --input .rumbling-hedge/research/topstep-readonly-bars/NQ-1m-topstep-readonly.csv --cadence-minutes 1 --output .rumbling-hedge/state/futures-nq-fabervaale-orb-topstep-1m-replay.latest.json",
        "npm run --silent bill:futures-nq-historical-session-walkforward -- --replay .rumbling-hedge/state/futures-nq-fabervaale-orb-topstep-1m-replay.latest.json --output .rumbling-hedge/state/futures-nq-fabervaale-orb-topstep-1m-walkforward.latest.json",
        "npm run --silent bill:futures-evidence-triage",
    ],
    "fabervaale-orb-cost-stress-holdout": [
        "npm run --silent bill:futures-nq-historical-session-cost-stress -- --replay .rumbling-hedge/state/futures-nq-fabervaale-orb-topstep-1m-replay.latest.json --output .rumbling-hedge/state/futures-nq-fabervaale-orb-topstep-1m-cost-stress.latest.json",
        "npm run --silent bill:futures-evidence-triage",
    ],
    "orderflow-current-depth-capture": [
        "BILL_ENABLE_FUTURES_DEMO_EXECUTION=false RH_TOPSTEP_READ_ONLY=true RH_LIVE_EXECUTION_ENABLED=false npm run --silent bill:topstep-realtime-proof",
        "BILL_ENABLE_FUTURES_DEMO_EXECUTION=false RH_TOPSTEP_READ_ONLY=true RH_LIVE_EXECUTION_ENABLED=false npm run --silent bill:topstep-realtime-bridge",
        "BILL_ENABLE_FUTURES_DEMO_EXECUTION=false RH_TOPSTEP_READ_ONLY=true RH_LIVE_EXECUTION_ENABLED=false npm run --silent bill:topstep-readonly-bar-archive",
        "npm run --silent bill:futures-evidence-triage",
    ],
    "lower-timeframe-vol-regime-current-form-rejected": [
        "npm run --silent bill:vol-regime-oos-15m",
        "npm run --silent bill:vol-regime-oos-30m",
        "npm run --silent bill:futures-cost-slippage-gate || true",
        "npm run --silent bill:futures-evidence-triage || true",
        "npm run --silent bill:futures-no-edge-ledger || true",
    ],
    "increase-oos-sample-before-parameter-mining": [
        "npm run --silent bill:vol-regime-oos-15m",
        "npm run --silent bill:vol-regime-oos-30m",
        "npm run --silent bill:futures-cost-slippage-gate || true",
        "npm run --silent bill:futures-evidence-triage || true",
    ],
    "retire-vol-regime-60m-current-form": [
        "npm run --silent bill:futures-no-edge-ledger || true",
        "npm run --silent bill:futures-evidence-triage || true",
    ],
    "cost-slippage-survivor-review": [
        "npm run --silent bill:futures-cost-slippage-gate || true",
        "npm run --silent bill:futures-evidence-triage || true",
        "npm run --silent bill:futures-no-edge-ledger || true",
    ],
}

BROKER_PROOF_PAUSED_FUTURES_COMMANDS: dict[str, list[str]] = {
    "fabervaale-orb-broker-grade-5m-depth": [
        "npm run --silent bill:futures-broker-parity-plan",
        "npm run --silent bill:futures-evidence-triage",
        "npm run --silent bill:next-research-actions",
    ],
    "fabervaale-orb-walkforward-depth": [
        "npm run --silent bill:futures-broker-parity-plan",
        "npm run --silent bill:futures-evidence-triage",
        "npm run --silent bill:next-research-actions",
    ],
    "orderflow-current-depth-capture": [
        "npm run --silent bill:futures-broker-parity-plan",
        "npm run --silent bill:futures-evidence-triage",
    ],
}

PREDICTION_COMMANDS: dict[str, list[str]] = {
    "kalshi-fillability-guided-rates-scan": [
        "npm run --silent bill:kalshi-fillability-snapshot",
        "npm run --silent bill:prediction-category-drilldown",
        "npm run --silent bill:prediction-narrow-scan",
        "npm run --silent bill:prediction-evidence-triage",
    ],
    "narrow-cross-venue-normalization": [
        "npm run --silent bill:kalshi-fillability-snapshot",
        "npm run --silent bill:prediction-category-drilldown",
        "npm run --silent bill:prediction-narrow-scan",
        "npm run --silent bill:prediction-evidence-triage",
    ],
    "resolved-outcome-join-review": [
        "npm run --silent bill:kalshi-fillability-snapshot",
        "npm run --silent bill:prediction-resolved-outcome-join",
        "npm run --silent bill:prediction-evidence-triage",
        "npm run --silent bill:prediction-no-edge-ledger",
    ],
    "targeted-clob-persistence-capture": [
        "npm run --silent bill:prediction-research-watchlist",
        "npm run --silent bill:polymarket-clob-recorder -- --duration-sec 120 --max-assets 8 --max-output-mb 128 --min-free-gb 20",
        "npm run --silent bill:polymarket-clob-persistence",
        "npm run --silent bill:polymarket-clob-edge-gate",
        "npm run --silent bill:prediction-evidence-triage",
    ],
    "reject-current-clob-drift-hypothesis": [
        "npm run --silent bill:prediction-no-edge-ledger",
        "npm run --silent bill:prediction-evidence-triage",
    ],
}


def read_json(path: Path, default: Any | None = None) -> Any:
    try:
        return json.loads(path.read_text())
    except Exception:
        return {} if default is None else default


def bool_value(value: Any) -> bool:
    return bool(value) if value is not None else False


def storage_gate(args: argparse.Namespace | None = None, live: dict[str, Any] | None = None) -> dict[str, Any]:
    override = getattr(args, "storage_free_gb", None) if args is not None else None
    warning_free_gb = None
    live = live or {}
    warnings = live.get("warnings") if isinstance(live.get("warnings"), list) else []
    for warning in warnings:
        match = re.search(r"SSD free space is low \(([0-9]+(?:\.[0-9]+)?)GB\)", str(warning))
        if match:
            try:
                warning_free_gb = float(match.group(1))
            except ValueError:
                warning_free_gb = None
            break
    try:
        free_gb = float(override) if override is not None else shutil.disk_usage(ROOT).free / 1_000_000_000
    except Exception:
        free_gb = None
    measured_free_gb = free_gb
    if isinstance(warning_free_gb, (int, float)):
        free_gb = min(free_gb, warning_free_gb) if isinstance(free_gb, (int, float)) else warning_free_gb
    return {
        "freeGb": round(free_gb, 2) if isinstance(free_gb, (int, float)) else None,
        "measuredFreeGb": round(measured_free_gb, 2) if isinstance(measured_free_gb, (int, float)) else None,
        "liveReadinessWarningFreeGb": warning_free_gb,
        "minPredictionCaptureFreeGb": PREDICTION_CAPTURE_MIN_FREE_GB,
        "predictionCaptureStorageBlocked": (
            isinstance(free_gb, (int, float)) and free_gb < PREDICTION_CAPTURE_MIN_FREE_GB
        ),
        "storageAuditCommand": "npm run --silent bill:hermes-storage-audit",
        "operatorRead": "Prediction CLOB capture is deferred when free space is below the recorder --min-free-gb floor.",
    }


def first_command(commands: Any) -> str | None:
    if not isinstance(commands, list) or not commands:
        return None
    return str(commands[0])


def finalize_action(action: dict[str, Any]) -> dict[str, Any]:
    action.setdefault("researchOnly", True)
    action.setdefault("writesOrders", False)
    action.setdefault("touchesBroker", False)
    action.setdefault("operatorApprovalRequiredBeforeExecution", True)
    action["firstCommand"] = first_command(action.get("commands"))
    return action


def topstep_session_safety_summary(session_safety: dict[str, Any] | None = None) -> dict[str, Any]:
    session_safety = session_safety or {}
    pause = bool_value(session_safety.get("pauseBrokerTouchingProofs")) or bool_value(session_safety.get("topstepMultipleSessionsDetected"))
    return {
        "present": bool(session_safety),
        "pauseBrokerTouchingProofs": pause,
        "reason": session_safety.get("reason", "missing"),
        "lastMitigation": session_safety.get("lastMitigation", "missing"),
        "safeUntil": session_safety.get("safeUntil", "operator-clears-warning"),
        "notesPath": session_safety.get("notesPath"),
    }


def broker_proof_paused(session_safety: dict[str, Any] | None = None) -> bool:
    return bool_value(topstep_session_safety_summary(session_safety).get("pauseBrokerTouchingProofs"))


def base_action(
    *,
    action_id: str,
    lane: str,
    priority: int,
    source_artifact: str,
    test: dict[str, Any],
    commands: list[str],
    promotion_gate: str,
    blockers: list[str],
) -> dict[str, Any]:
    return {
        "id": action_id,
        "lane": lane,
        "priority": priority,
        "sourceArtifact": source_artifact,
        "oneVariable": test.get("oneVariable", "missing"),
        "hypothesis": test.get("hypothesis", "missing"),
        "commandHint": test.get("commandHint", "missing"),
        "commands": commands,
        "promotionGate": promotion_gate,
        "promotionBlockers": blockers,
        "writesOrders": False,
        "touchesBroker": False,
        "researchOnly": True,
        "operatorApprovalRequiredBeforeExecution": True,
    }


def futures_actions(futures: dict[str, Any], session_safety: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    broker_proof_pause = broker_proof_paused(session_safety)
    session_summary = topstep_session_safety_summary(session_safety)
    for index, test in enumerate(futures.get("nextTests") or [], start=1):
        if not isinstance(test, dict):
            continue
        test_id = str(test.get("id") or f"futures-test-{index}")
        commands = (
            BROKER_PROOF_PAUSED_FUTURES_COMMANDS.get(test_id)
            if broker_proof_pause and test_id in BROKER_PROOF_PAUSED_FUTURES_COMMANDS
            else FUTURES_COMMANDS.get(test_id, ["inspect futures-evidence-triage.latest.json before running anything"])
        )
        blockers = [
            "daily plan approval is blocked",
            "Backtrader full-sample rows are hypothesis seeds only",
            "requires positive OOS, walk-forward, rolling OOS, and cost/slippage evidence",
        ]
        action = base_action(
            action_id=test_id,
            lane="futures",
            priority=10 + index,
            source_artifact=".rumbling-hedge/state/futures-evidence-triage.latest.json",
            test=test,
            commands=commands,
            promotion_gate=str(test.get("promotionRule") or "no futures demo promotion without OOS and live-readiness gates"),
            blockers=blockers + (["Topstep broker-touching proof paused until multiple-session warning clears"] if broker_proof_pause and test_id in BROKER_PROOF_PAUSED_FUTURES_COMMANDS else []),
        )
        if broker_proof_pause and test_id in BROKER_PROOF_PAUSED_FUTURES_COMMANDS:
            action["topstepSessionSafety"] = session_summary
        actions.append(action)
    return actions


def futures_no_edge_entry(futures_no_edge: dict[str, Any], entry_id: str) -> dict[str, Any]:
    entries = futures_no_edge.get("entries") if isinstance(futures_no_edge.get("entries"), list) else []
    for entry in entries:
        if isinstance(entry, dict) and entry.get("id") == entry_id:
            return entry
    return {}


def futures_no_edge_verdict(futures_no_edge: dict[str, Any], entry_id: str) -> str:
    entry = futures_no_edge_entry(futures_no_edge, entry_id)
    return str(entry.get("verdict") or "")


def futures_positioning_actions(
    positioning: dict[str, Any],
    cot_research: dict[str, Any],
    futures_no_edge: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    futures_no_edge = futures_no_edge or {}
    cot_summary = cot_research.get("summary") if isinstance(cot_research.get("summary"), dict) else {}
    if cot_summary.get("decision") == "research-only-no-positive-full-sample-improvement":
        if futures_no_edge_verdict(futures_no_edge, "cot-tff-regime-filter-current-backtrader-set") == "no-edge":
            return []
        return [{
            "id": "cot-positioning-filter-current-form-rejected",
            "lane": "futures",
            "priority": 14,
            "sourceArtifact": ".rumbling-hedge/state/cot-regime-filter-research.latest.json",
            "oneVariable": "weekly positioning regime",
            "hypothesis": "The current COT/TFF gate was already tested and produced no positive full-sample improvement.",
            "commandHint": "Do not rerun the same COT filter. Add it to no-edge memory, then revisit only with a different policy, longer sample, or an OOS-specific hypothesis.",
            "commands": [
                "npm run --silent bill:futures-no-edge-ledger || true",
                "npm run --silent bill:futures-evidence-triage || true",
            ],
            "promotionGate": str(cot_summary.get("promotionGate") or "No promotion from the current COT/TFF gate."),
            "promotionBlockers": [
                "latest COT gate decision: research-only-no-positive-full-sample-improvement",
                "do not repeat the same one-variable COT test without new data, policy, or OOS hypothesis",
                "requires positive OOS, walk-forward, rolling OOS, cost/slippage, and live-readiness gates",
            ],
            "writesOrders": False,
            "researchOnly": True,
            "operatorApprovalRequiredBeforeExecution": True,
        }]
    if positioning.get("freshForWeeklyResearch") is True:
        hypothesis = (
            "CFTC TFF positioning is fresh enough for weekly research; test it as the only "
            "new futures regime/risk variable, not as an entry signal."
        )
        blockers = [
            "COT is weekly and lagged",
            "must be joined into OOS tests as a regime/risk feature only",
            "requires positive OOS, walk-forward, rolling OOS, cost/slippage, and live-readiness gates",
        ]
    else:
        hypothesis = "CFTC TFF positioning is missing or stale; refresh the official weekly intake before testing COT-gated futures ideas."
        blockers = positioning.get("blockers") or ["CFTC TFF positioning artifact missing or stale"]
    return [{
        "id": "cftc-tff-positioning-regime-filter",
        "lane": "futures",
        "priority": 14,
        "sourceArtifact": ".rumbling-hedge/state/cftc-tff-positioning.latest.json",
        "oneVariable": "weekly positioning regime",
        "hypothesis": hypothesis,
        "commandHint": "Use COT as a single added filter/gate on a known strategy family; do not combine it with parameter changes in the same test.",
        "commands": [
            "npm run --silent bill:cftc-tff-positioning || true",
            "npm run --silent bill:cot-regime-filter-research",
            "npm run --silent bill:futures-cost-slippage-gate || true",
            "npm run --silent bill:futures-evidence-triage || true",
        ],
        "promotionGate": "COT-gated futures branch remains research-only unless it improves OOS/stressed evidence without worsening drawdown or prop-firm consistency risk.",
        "promotionBlockers": blockers,
        "writesOrders": False,
        "researchOnly": True,
        "operatorApprovalRequiredBeforeExecution": True,
    }]


def topstep_learning_actions(daily_learning: dict[str, Any]) -> list[dict[str, Any]]:
    if not daily_learning:
        return []
    issues = daily_learning.get("issues") if isinstance(daily_learning.get("issues"), list) else []
    operator_pnl = daily_learning.get("operatorReportedPnl") if isinstance(daily_learning.get("operatorReportedPnl"), dict) else {}
    account_sizing = daily_learning.get("accountSizing") if isinstance(daily_learning.get("accountSizing"), dict) else {}
    if not issues and not operator_pnl.get("brokerProofRequired"):
        return []
    issue_ids = [
        str(item.get("id"))
        for item in issues
        if isinstance(item, dict) and item.get("id")
    ]
    blockers = [
        "demo learning is evidence only, not route approval",
        "broker-native P&L/reconciliation must prove any operator-reported 100K result",
        "50K MNQ-first prop-firm policy is the live/challenge sizing source of truth",
        "do not copy 100K demo contract sizing into the 50K challenge or funded account",
        *issue_ids,
    ]
    return [{
        "id": "topstep-demo-learning-50k-reconciliation",
        "lane": "futures",
        "priority": 12,
        "sourceArtifact": ".rumbling-hedge/state/topstep-daily-learning.latest.json",
        "oneVariable": "broker-native demo learning reconciliation",
        "hypothesis": "The 100K demo can improve setup selection and mistake prevention only after broker-native evidence is reconciled and translated through the 50K MNQ-first sizing policy.",
        "commandHint": "Refresh local demo learning, the 50K payout plan, and futures broker parity. Do not change route flags or sizing from this action.",
        "commands": [
            "npm run --silent bill:topstep-daily-learning",
            "npm run --silent bill:prop-firm-payout-plan",
            "npm run --silent bill:futures-broker-parity-plan",
            "npm run --silent bill:obsidian-sync",
            "npm run --silent bill:next-research-actions",
        ],
        "promotionGate": "No futures demo expansion or 50K challenge execution until daily plan, broker reconciliation, execution-grade data, source hygiene, and 50K sizing gates all pass.",
        "promotionBlockers": blockers,
        "learningStatus": daily_learning.get("learningStatus"),
        "issueIds": issue_ids,
        "operatorReportedPnl": {
            "claimCount": operator_pnl.get("claimCount", 0),
            "brokerProofRequired": bool_value(operator_pnl.get("brokerProofRequired")),
            "promotionUse": operator_pnl.get("promotionUse"),
        },
        "accountSizing": account_sizing,
        "readyForExecution": False,
        "readyForDemoExpansion": False,
        "writesOrders": False,
        "touchesBroker": False,
        "researchOnly": True,
        "operatorApprovalRequiredBeforeExecution": True,
    }]


def current_category_universe(category_drilldown: dict[str, Any]) -> dict[str, Any]:
    """Summarize the latest category drilldown for weaker research agents."""
    next_tests = category_drilldown.get("nextTests") if isinstance(category_drilldown.get("nextTests"), list) else []
    categories: list[dict[str, Any]] = []
    for item in next_tests:
        if not isinstance(item, dict):
            continue
        categories.append({
            "id": item.get("id"),
            "category": item.get("category"),
            "oneVariable": item.get("oneVariable"),
            "marketCount": item.get("marketCount"),
            "venues": item.get("venues") or [],
            "fillabilityGuided": bool_value(item.get("fillabilityGuided")),
            "kalshiFillability": item.get("kalshiFillability") if isinstance(item.get("kalshiFillability"), dict) else {},
        })
    return {
        "readyForPaper": bool_value(category_drilldown.get("readyForPaper")),
        "writesOrders": bool_value(category_drilldown.get("writesOrders")),
        "kalshiFillability": category_drilldown.get("kalshiFillability") if isinstance(category_drilldown.get("kalshiFillability"), dict) else {},
        "categories": categories,
    }


def prediction_no_edge_entry(prediction_no_edge: dict[str, Any], entry_id: str) -> dict[str, Any]:
    entries = prediction_no_edge.get("entries") if isinstance(prediction_no_edge.get("entries"), list) else []
    for entry in entries:
        if isinstance(entry, dict) and entry.get("id") == entry_id:
            return entry
    return {}


def prediction_no_edge_verdict(prediction_no_edge: dict[str, Any], entry_id: str) -> str:
    entry = prediction_no_edge_entry(prediction_no_edge, entry_id)
    return str(entry.get("verdict") or "")


def narrow_single_variable_retest(
    prediction_no_edge: dict[str, Any],
    category_universe: dict[str, Any],
) -> dict[str, Any]:
    entry = prediction_no_edge_entry(prediction_no_edge, "narrow-category-cross-venue-current-universe")
    if entry.get("verdict") != "needs-more-data":
        return {}
    categories = {
        str(item.get("category")): item
        for item in category_universe.get("categories", [])
        if isinstance(item, dict) and item.get("category")
    }
    next_action = str(entry.get("nextAction") or "").lower()
    evidence = entry.get("evidence") if isinstance(entry.get("evidence"), dict) else {}
    reject_reasons = evidence.get("categoryRejectReasons") if isinstance(evidence.get("categoryRejectReasons"), dict) else {}
    crypto_current_form_rejected = (
        prediction_no_edge_verdict(prediction_no_edge, "crypto-settlement-horizon-parser-current-form") == "no-edge"
    )
    macro_current_form_rejected = (
        prediction_no_edge_verdict(prediction_no_edge, "macro-rates-line-parser-current-form") == "no-edge"
    )

    if crypto_current_form_rejected and macro_current_form_rejected:
        return {
            "id": "narrow-cross-venue-current-universe-current-form-rejected",
            "actionKind": "no-edge-maintenance",
            "category": "none-current-form-rejected",
            "oneVariable": "current narrow universe",
            "hypothesis": "The current category-narrow prediction universe has been tested one variable at a time and has no paper/watch candidate under existing safety gates.",
            "commandHint": "Do not rerun crypto settlement or macro/rates line parsing without a new market source, resolved-outcome label, or genuinely new feature.",
            "commands": [
                "npm run --silent bill:prediction-no-edge-ledger",
                "npm run --silent bill:prediction-evidence-triage",
            ],
            "noEdgeReason": "crypto settlement and macro/rates line parser current forms rejected",
        }

    if (
        "crypto" in categories
        and not crypto_current_form_rejected
        and ("crypto" in next_action or "temporal-mismatch" in (reject_reasons.get("crypto") or {}))
    ):
        return {
            "id": "crypto-settlement-horizon-parser-retest",
            "category": "crypto",
            "oneVariable": "settlement horizon parser",
            "hypothesis": "Crypto near misses are mostly the same underlying BTC/crypto event but fail temporal settlement checks; retest only the settlement-horizon parser on crypto.",
            "commandHint": "Run a crypto-only narrow scan after changing only settlement-horizon parsing. Keep semantic, spread, fee, and threshold rules unchanged.",
            "commands": [
                "npm run --silent bill:prediction-category-drilldown",
                "npm run --silent bill:prediction-narrow-scan -- --category crypto",
                "npm run --silent bill:prediction-evidence-triage",
                "npm run --silent bill:prediction-no-edge-ledger",
            ],
        }

    if (
        "macro-rates" in categories
        and ("macro" in next_action or crypto_current_form_rejected or "line-mismatch" in (reject_reasons.get("macro-rates") or {}))
    ):
        return {
            "id": "macro-rates-line-parser-retest",
            "category": "macro-rates",
            "oneVariable": "rates line parser",
            "hypothesis": "Macro/rates fillable quotes are present, but line/outcome parsing rejects most candidates; retest only the rates line parser.",
            "commandHint": "Run a macro-rates-only narrow scan after changing only line parsing. Keep market-type, temporal, spread, fee, and threshold rules unchanged.",
            "commands": [
                "npm run --silent bill:kalshi-fillability-snapshot",
                "npm run --silent bill:prediction-category-drilldown",
                "npm run --silent bill:prediction-narrow-scan -- --category macro-rates",
                "npm run --silent bill:prediction-evidence-triage",
                "npm run --silent bill:prediction-no-edge-ledger",
            ],
            "noEdgeReason": "crypto-settlement-horizon-parser-current-form rejected" if crypto_current_form_rejected else None,
        }
    return {}


def prediction_actions(
    prediction: dict[str, Any],
    category_drilldown: dict[str, Any],
    prediction_no_edge: dict[str, Any],
    storage: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    storage = storage or {}
    review = prediction.get("resolvedOutcomeReview") if isinstance(prediction.get("resolvedOutcomeReview"), dict) else {}
    review_decision = review.get("decision", "missing")
    category_universe = current_category_universe(category_drilldown)
    category_names = [str(item.get("category")) for item in category_universe["categories"] if item.get("category")]
    for index, test in enumerate(prediction.get("nextTests") or [], start=1):
        if not isinstance(test, dict):
            continue
        test_id = str(test.get("id") or f"prediction-test-{index}")
        commands = PREDICTION_COMMANDS.get(test_id, ["inspect prediction-evidence-triage.latest.json before running anything"])
        deferred_commands: list[str] = []
        storage_blocked = False
        if test_id == "targeted-clob-persistence-capture":
            token_ids = [
                str(item.get("tokenId"))
                for item in (test.get("eligibleTokens") or [])[:3]
                if isinstance(item, dict) and item.get("tokenId")
            ]
            if token_ids:
                token_args = " ".join(f"--token-id {token_id}" for token_id in token_ids)
                commands = [
                    "npm run --silent bill:prediction-research-watchlist",
                    f"npm run --silent bill:polymarket-clob-recorder -- --duration-sec 120 --max-assets 8 --max-output-mb 128 --min-free-gb 20 {token_args}",
                    "npm run --silent bill:polymarket-clob-persistence",
                    "npm run --silent bill:polymarket-clob-edge-gate",
                    "npm run --silent bill:prediction-evidence-triage",
                ]
        elif test_id == "prediction-forward-event-clob-capture":
            command_hint = str(test.get("commandHint") or "").strip()
            if "bill:polymarket-clob-recorder" in command_hint:
                commands = [
                    command_hint,
                    "npm run --silent bill:prediction-event-paper-promotion-gate",
                    "npm run --silent bill:prediction-evidence-triage",
                    "npm run --silent bill:next-research-actions",
                ]
            if storage.get("predictionCaptureStorageBlocked") is True:
                deferred_commands = commands
                storage_blocked = True
                commands = [
                    "npm run --silent bill:hermes-storage-audit",
                    "npm run --silent bill:obsidian-sync",
                    "inspect .rumbling-hedge/state/hermes-storage-audit.latest.json before running prediction CLOB capture",
                ]
                test = {
                    **test,
                    "commandHint": (
                        f"Storage preflight blocked: free {storage.get('freeGb')}GB < "
                        f"{storage.get('minPredictionCaptureFreeGb')}GB. Refresh Hermes storage audit before recorder."
                    ),
                }
        retest = {}
        if test_id == "narrow-cross-venue-normalization":
            retest = narrow_single_variable_retest(prediction_no_edge, category_universe)
            if retest:
                test_id = str(retest["id"])
                commands = retest["commands"]
                test = {
                    **test,
                    "oneVariable": retest["oneVariable"],
                    "hypothesis": retest["hypothesis"],
                    "commandHint": retest["commandHint"],
                }
        blockers = [
            "prediction paper/live promotion is blocked",
            f"resolved-outcome review decision: {review_decision}",
            "requires spread, fees, CLOB persistence, directional hit rate, and fillability gates",
        ]
        action = base_action(
            action_id=test_id,
            lane="prediction-markets",
            priority=30 + index,
            source_artifact=".rumbling-hedge/state/prediction-evidence-triage.latest.json",
            test=test,
            commands=commands,
            promotion_gate=str(test.get("promotionRule") or "no prediction paper promotion without review.readyForPaper"),
            blockers=blockers,
        )
        if storage_blocked:
            action["storageGate"] = storage
            action["storageBlocked"] = True
            action["deferredCommands"] = deferred_commands
            action["promotionBlockers"] = list(dict.fromkeys([
                *action["promotionBlockers"],
                "storage-free-space-below-prediction-capture-floor",
            ]))
        if test_id == "narrow-cross-venue-normalization" and category_names:
            fillable_names = [
                str(item.get("category"))
                for item in category_universe["categories"]
                if item.get("category") and item.get("fillabilityGuided")
            ]
            action["currentCategoryUniverse"] = category_universe
            action["commandHint"] = (
                "Use the latest cleaned category drilldown before scanning. Current narrow lanes: "
                + ", ".join(category_names)
                + (f". Fillability-guided lanes: {', '.join(fillable_names)}" if fillable_names else "")
                + ". Compare watch count and blocker mix without lowering thresholds."
            )
        elif retest:
            action["replacesTestId"] = "narrow-cross-venue-normalization"
            action["selectedCategory"] = retest["category"]
            action["currentCategoryUniverse"] = category_universe
            if retest.get("noEdgeReason"):
                action["previousVariableRejected"] = retest["noEdgeReason"]
            if retest.get("actionKind"):
                action["actionKind"] = retest["actionKind"]
                action["priority"] = 39
            action["noEdgeMemory"] = {
                "source": ".rumbling-hedge/research/prediction-no-edge-ledger/latest.json",
                "entryId": "narrow-category-cross-venue-current-universe",
                "verdict": "needs-more-data",
            }
        actions.append(action)
    return actions


def prediction_event_watch_actions(
    watch_review: dict[str, Any],
    manual_review: dict[str, Any] | None = None,
    market_mapping: dict[str, Any] | None = None,
    mapping_refinement: dict[str, Any] | None = None,
    clob_targets: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Surface manual event-lag watch windows as explicit research tasks.

    A watch-ready sensitivity artifact is not a promotion signal. It is a
    request to inspect the specific windows before spending more recorder time
    or discussing paper trading.
    """
    watch_windows = watch_review.get("watchWindows") if isinstance(watch_review.get("watchWindows"), list) else []
    if not watch_windows or watch_review.get("watchReady") is not True:
        return []
    manual_review = manual_review or {}
    manual_review_complete = (
        manual_review.get("decision") in {"research-only-manual-review-no-paper", "research-only-manual-review-watch"}
        and int(manual_review.get("reviewedWindowCount") or 0) >= len(watch_windows)
    )

    summary = []
    for item in watch_windows[:5]:
        if not isinstance(item, dict):
            continue
        summary.append({
            "externalId": item.get("externalId"),
            "question": item.get("question"),
            "eventIso": item.get("eventIso"),
            "variable": item.get("variable"),
            "value": item.get("value"),
            "horizonMinutes": item.get("horizonMinutes"),
            "midMove": item.get("midMove"),
            "preSpread": item.get("preSpread"),
            "postDelaySec": item.get("postDelaySec"),
        })

    if not summary:
        return []

    market_mapping = market_mapping or {}
    mapping_refinement = mapping_refinement or {}
    clob_targets = clob_targets or {}
    mapping_plan_blockers = [
        str(item)
        for item in market_mapping.get("blockers", [])
        if item is not None
    ] if isinstance(market_mapping.get("blockers"), list) else []
    refinement_blockers = [
        str(item)
        for item in mapping_refinement.get("blockers", [])
        if item is not None
    ] if isinstance(mapping_refinement.get("blockers"), list) else []
    manual_review_blockers = [
        str(item)
        for item in manual_review.get("blockers", [])
        if item is not None
    ] if isinstance(manual_review.get("blockers"), list) else []
    forward_capture_status_blockers = [
        item
        for item in manual_review_blockers
        if item.startswith("forward-public-clob-capture-")
    ] or ["forward-public-clob-capture-still-required"]
    promotion_blockers = list(dict.fromkeys([
        "manual-review-found-no-paper-grade-event-lag-window",
        "event-market-mapping-or-spread-quality-not-paper-grade",
        *forward_capture_status_blockers,
        *mapping_plan_blockers,
        *refinement_blockers,
    ]))
    family_fanout = market_mapping.get("headlineFamilyFanout")
    if not isinstance(family_fanout, list):
        family_fanout = []
    fanout_sample = []
    for item in family_fanout[:3]:
        if not isinstance(item, dict):
            continue
        fanout_sample.append({
            "headline": item.get("headline"),
            "headlineEventFamilies": item.get("headlineEventFamilies"),
            "headlineActors": item.get("headlineActors"),
            "marketActorSets": item.get("marketActorSets"),
            "candidateCount": item.get("candidateCount"),
            "candidateExternalIds": item.get("candidateExternalIds"),
        })
    counterparty_fanout = market_mapping.get("ambiguousHeadlineCounterpartyFanout")
    if not isinstance(counterparty_fanout, list):
        counterparty_fanout = [
            item
            for item in family_fanout
            if isinstance(item, dict) and item.get("counterpartyAmbiguous") is True
        ]
    excluded_mapping_count = int(clob_targets.get("excludedMappingCandidateCount") or 0)
    mapping_exclusion_reasons = (
        clob_targets.get("excludedMappingReasonCounts")
        if isinstance(clob_targets.get("excludedMappingReasonCounts"), dict)
        else {}
    )
    token_specific_candidates = int(clob_targets.get("tokenSpecificCandidateCount") or 0)
    target_count = int(clob_targets.get("targetCount") or 0)
    mapping_exclusion_summary = {
        "targetCount": target_count,
        "tokenSpecificCandidateCount": token_specific_candidates,
        "excludedMappingCandidateCount": excluded_mapping_count,
        "excludedMappingReasonCounts": mapping_exclusion_reasons,
        "mappingBlockers": (
            clob_targets.get("mappingBlockers")
            if isinstance(clob_targets.get("mappingBlockers"), list)
            else mapping_plan_blockers
        ),
    }
    if excluded_mapping_count > 0:
        promotion_blockers = list(dict.fromkeys([
            *promotion_blockers,
            "ambiguous-mapping-candidates-excluded-from-token-capture",
        ]))
    forward_plan = (
        clob_targets.get("forwardCapturePlan")
        if isinstance(clob_targets.get("forwardCapturePlan"), dict)
        else {}
    )
    forward_command = str(forward_plan.get("command") or "").strip()
    review_lead_command = str(forward_plan.get("reviewLeadCommand") or "").strip()
    preferred_forward_command = review_lead_command or forward_command
    capture_commands = [
        "npm run --silent bill:prediction-event-market-mapping-plan",
        "npm run --silent bill:prediction-event-mapping-refinement",
        "npm run --silent bill:prediction-event-clob-capture-targets",
    ]
    if target_count > 0:
        capture_commands.append("npm run --silent bill:prediction-event-capture-cycle -- --run-recorder --duration-sec 900 --max-assets 15 --max-output-mb 128 --min-free-gb 20")
    elif forward_plan.get("required") is True and preferred_forward_command:
        capture_commands.append(preferred_forward_command)
        promotion_blockers = list(dict.fromkeys([
            *promotion_blockers,
            "deadline-ladder-forward-capture-required-before-paper-review"
            if review_lead_command
            else "standing-forward-capture-required-before-token-specific-capture",
        ]))
    capture_commands.extend([
        "npm run --silent bill:prediction-event-paper-promotion-gate",
        "npm run --silent bill:prediction-evidence-triage",
        "npm run --silent bill:next-research-actions",
    ])

    if manual_review_complete and manual_review.get("decision") == "research-only-manual-review-no-paper":
        return [{
            "id": "prediction-event-mapping-refinement-after-manual-review",
            "lane": "prediction-markets",
            "priority": 30 if excluded_mapping_count > 0 else 33,
            "sourceArtifact": ".rumbling-hedge/state/prediction-event-lag-manual-review.latest.json",
            "oneVariable": "event-market mapping quality",
            "hypothesis": "The current event-lag watch windows did not survive manual paper review; improve mapping and forward capture instead of lowering repricing thresholds.",
            "commandHint": "Manual review is already complete and rejected paper use. Start with ambiguous headline-to-market mapping repair, then validate token-specific capture targets; change only mapping quality or source capture quality next.",
            "commands": capture_commands,
            "promotionGate": "Manual review rejected current watch windows for paper; only fresh forward capture plus improved no-lookahead mapping can reopen paper discussion.",
            "promotionBlockers": promotion_blockers,
            "forwardCapturePlan": {
                "required": bool_value(forward_plan.get("required")),
                "reason": forward_plan.get("reason"),
                "command": forward_plan.get("command"),
                "reviewLeadCommand": forward_plan.get("reviewLeadCommand"),
                "preferredCommand": preferred_forward_command,
                "usedReviewLeadCommand": bool(review_lead_command),
                "usedInsteadOfTargetSpecificCapture": target_count == 0 and bool_value(forward_plan.get("required")),
            },
            "manualReviewDecision": manual_review.get("decision"),
            "manualReviewCounts": manual_review.get("decisionCounts") if isinstance(manual_review.get("decisionCounts"), dict) else {},
            "mappingPlanDecision": market_mapping.get("decision", "missing"),
            "mappingPlanBlockers": mapping_plan_blockers,
            "mappingPlanAmbiguousHeadlineCount": market_mapping.get("ambiguousHeadlineCount", 0),
            "mappingPlanAmbiguousCounterpartyHeadlineCount": market_mapping.get("ambiguousCounterpartyHeadlineCount", 0),
            "mappingPlanAmbiguousCounterpartyFanoutCount": len(counterparty_fanout),
            "mappingExclusionSummary": mapping_exclusion_summary,
            "headlineFamilyFanoutSample": fanout_sample,
            "mappingRefinementDecision": mapping_refinement.get("decision", "missing"),
            "mappingRefinementBlockers": refinement_blockers,
            "mappingRefinementQualityCounts": (
                mapping_refinement.get("mappingQualityCounts")
                if isinstance(mapping_refinement.get("mappingQualityCounts"), dict)
                else {}
            ),
            "watchWindowSummary": summary,
            "readyForPaper": False,
            "readyForExecution": False,
            "writesOrders": False,
            "touchesBroker": False,
            "researchOnly": True,
            "operatorApprovalRequiredBeforeExecution": True,
        }]

    blockers = [
        "manual-review-required-before-forward-capture-or-paper-discussion",
        "strict event-lag replay remains blocked",
        "watch windows are sensitivity evidence only",
        "requires fresh forward public CLOB capture before/through future news windows",
    ]
    if isinstance(watch_review.get("blockers"), list):
        blockers = list(dict.fromkeys(blockers + [str(item) for item in watch_review["blockers"]]))

    return [{
        "id": "prediction-event-lag-watch-window-review",
        "lane": "prediction-markets",
        "priority": 33,
        "sourceArtifact": ".rumbling-hedge/state/prediction-event-lag-watch-review.latest.json",
        "oneVariable": "manual review of threshold-sensitive event-lag windows",
        "hypothesis": "The two sensitivity-only event-lag windows may reveal a usable news-to-CLOB response pattern, but only if manual review confirms no lookahead, clean mapping, and realistic fillability.",
        "commandHint": "Review the listed windows and write a keep/reject note before running more capture or paper-readiness checks. Do not lower thresholds or promote from this artifact.",
        "commands": [
            "npm run --silent bill:prediction-event-lag-watch-review",
            "inspect .rumbling-hedge/state/prediction-event-lag-watch-review.latest.json and write a manual keep/reject note in Obsidian",
            "npm run --silent bill:prediction-event-clob-capture-targets",
            "npm run --silent bill:prediction-event-capture-cycle -- --run-recorder --duration-sec 900 --max-assets 15 --max-output-mb 128 --min-free-gb 20",
            "npm run --silent bill:prediction-event-paper-promotion-gate",
            "npm run --silent bill:prediction-evidence-triage",
            "npm run --silent bill:next-research-actions",
        ],
        "promotionGate": "No prediction paper promotion until strict no-lookahead replay, manual watch review, forward capture, fillability, and resolved-label gates pass.",
        "promotionBlockers": blockers,
        "watchWindowCount": len(watch_windows),
        "watchWindowSummary": summary,
        "eventLagDecision": watch_review.get("decision", "missing"),
        "readyForPaper": False,
        "readyForExecution": False,
        "writesOrders": False,
        "touchesBroker": False,
        "researchOnly": True,
        "operatorApprovalRequiredBeforeExecution": True,
    }]


def alpha_frontier_has_reviewed_youtube(alpha_frontier: dict[str, Any]) -> bool:
    items = alpha_frontier.get("frontier") if isinstance(alpha_frontier.get("frontier"), list) else []
    return any(
        isinstance(item, dict)
        and str(item.get("id") or "").startswith("futures-youtube-")
        and item.get("researchOnly") is True
        for item in items
    )


def seed_actions(seed_triage: dict[str, Any], *, suppress_youtube_extraction: bool = False) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    queued_targets = (
        seed_triage.get("queuedYouTubeResearcherTargets")
        if isinstance(seed_triage.get("queuedYouTubeResearcherTargets"), list)
        else []
    )
    target_ids = [
        str(item.get("id"))
        for item in queued_targets
        if isinstance(item, dict) and item.get("id")
    ]
    if target_ids:
        latest = (
            seed_triage.get("queuedYouTubeLatestRun")
            if isinstance(seed_triage.get("queuedYouTubeLatestRun"), dict)
            else {}
        )
        latest_results = latest.get("targetResults") if isinstance(latest.get("targetResults"), list) else []
        latest_target_ids = {
            str(item.get("targetId"))
            for item in latest_results
            if isinstance(item, dict) and item.get("targetId")
        }
        latest_processed_same_targets = bool(latest_target_ids) and set(target_ids).issubset(latest_target_ids)
        latest_zero_yield = (
            latest.get("present") is True
            and latest.get("status") == "degraded"
            and int(latest.get("chunksCollected") or 0) == 0
            and int(latest.get("strategyHypothesesCount") or 0) == 0
            and latest_processed_same_targets
        )
        if latest_zero_yield:
            actions.append({
                "id": "seed-refresh-youtube-target-list",
                "lane": "research-seeds",
                "priority": 49,
                "sourceArtifact": ".rumbling-hedge/state/research-seed-triage.latest.json",
                "targetManifest": ".rumbling-hedge/state/research-seed-youtube-targets.latest.json",
                "queuedTargetCount": len(target_ids),
                "sampleTargetIds": target_ids[:5],
                "oneVariable": "source target list",
                "hypothesis": "The current queued videos have already yielded no novel transcript chunks; a fresh target list is required before another extraction run.",
                "commandHint": "Do not rerun the same queued YouTube extraction. Add fresh, futures/prediction-market-specific targets or convert existing notes into machine-testable hypothesis cards.",
                "commands": [
                    "npm run --silent bill:research-seed-triage",
                    "npm run --silent bill:research-seed-target-refresh-plan",
                    "inspect /Users/brain/Documents/memorybrain/Research-Catalog/youtube-queue.md and add new machine-testable targets before rerunning researcher-run",
                    "npm run --silent bill:next-research-actions",
                ],
                "promotionGate": "queued YouTube seed needs new transcript-derived explicit rules before any Backtrader/OOS replay",
                "promotionBlockers": [
                    "latest queued-video researcher run was degraded",
                    "same target ids produced zero novel chunks",
                    "no explicit entry/stop/target/risk rules extracted yet",
                ],
                "latestRun": {
                    "runId": latest.get("runId"),
                    "status": latest.get("status"),
                    "chunksCollected": latest.get("chunksCollected"),
                    "strategyHypothesesCount": latest.get("strategyHypothesesCount"),
                    "blockers": latest.get("blockers") if isinstance(latest.get("blockers"), list) else [],
                },
                "writesOrders": False,
                "touchesBroker": False,
                "researchOnly": True,
                "operatorApprovalRequiredBeforeExecution": True,
            })
            return actions
        if suppress_youtube_extraction:
            return actions
        target_args = " ".join(f"--target {target_id}" for target_id in target_ids[:5])
        actions.append({
            "id": "seed-extract-queued-youtube-transcripts",
            "lane": "research-seeds",
            "priority": 49,
            "sourceArtifact": ".rumbling-hedge/state/research-seed-triage.latest.json",
            "targetManifest": ".rumbling-hedge/state/research-seed-youtube-targets.latest.json",
            "queuedTargetCount": len(target_ids),
            "sampleTargetIds": target_ids[:5],
            "oneVariable": "source transcript extraction",
            "hypothesis": "Queued videos become useful only after transcript extraction produces explicit rules and contrary tests.",
            "commandHint": "Run the bounded researcher against only queued YouTube targets, then refresh seed triage and no-edge evidence. Do not run local replay until explicit rules exist.",
            "commands": [
                "npm run --silent bill:research-seed-triage",
                (
                    "npm run --silent bill:researcher-run -- "
                    "--targets .rumbling-hedge/state/research-seed-youtube-targets.latest.json "
                    f"{target_args} --skip-judge --skip-embed"
                ),
                "npm run --silent bill:researcher-report",
                "npm run --silent bill:research-seed-triage",
                "npm run --silent bill:next-research-actions",
            ],
            "promotionGate": "queued YouTube seed needs transcript-derived explicit rules before any Backtrader/OOS replay",
            "promotionBlockers": [
                "video is narrative source only",
                "no explicit entry/stop/target/risk rules extracted yet",
                "no local OOS, cost/slippage, or no-edge review",
            ],
            "writesOrders": False,
            "touchesBroker": False,
            "researchOnly": True,
            "operatorApprovalRequiredBeforeExecution": True,
        })
    for index, item in enumerate(seed_triage.get("nextBuildQueue") or [], start=1):
        if not isinstance(item, dict):
            continue
        strategy_id = str(item.get("inferredStrategyId") or "unmapped")
        actions.append({
            "id": f"seed-replay-{strategy_id}-{index}",
            "lane": "research-seeds",
            "priority": 50 + index,
            "sourceArtifact": ".rumbling-hedge/state/research-seed-triage.latest.json",
            "sourceId": item.get("sourceId"),
            "strategyId": strategy_id,
            "title": item.get("title"),
            "commands": [
                "npm run --silent bill:backtrader-research",
                "npm run --silent bill:futures-cost-slippage-gate || true",
                "npm run --silent bill:futures-evidence-triage || true",
            ],
            "promotionGate": "candidate seed must create fresh local OOS evidence and pass cost/slippage before retest priority increases",
            "promotionBlockers": item.get("blockers") or ["not approved by live-readiness gates"],
            "writesOrders": False,
            "researchOnly": True,
            "operatorApprovalRequiredBeforeExecution": True,
        })
    return actions


def alpha_frontier_actions(
    frontier_payload: dict[str, Any],
    prediction_event_clob_targets: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    prediction_event_clob_targets = prediction_event_clob_targets or {}
    actions: list[dict[str, Any]] = []
    items = frontier_payload.get("frontier") if isinstance(frontier_payload.get("frontier"), list) else []
    for item in items:
        if not isinstance(item, dict):
            continue
        action_id = str(item.get("id") or "")
        if not action_id:
            continue
        lane = str(item.get("lane") or "alpha-frontier")
        research_steps = [
            str(step)
            for step in (item.get("researchSteps") if isinstance(item.get("researchSteps"), list) else [])
            if step
        ]
        commands = [str(command) for command in (item.get("commands") or ["npm run --silent bill:alpha-frontier-queue"])]
        command_hint = str(item.get("commandHint") or "").strip()
        if command_hint == "missing":
            command_hint = ""
        if not command_hint:
            if research_steps:
                command_hint = f"Manual one-variable research step required: {research_steps[0]}"
            elif commands == ["npm run --silent bill:alpha-frontier-queue"]:
                command_hint = "This item only refreshes the frontier automatically; create a focused research artifact before promotion review."
            else:
                command_hint = "Run the listed research commands, then refresh alpha-frontier and evidence triage before any promotion review."
        blockers = [
            "execution remains locked",
            "frontier item is new-feature research only",
            "requires explicit OOS/paper/demo promotion gates before execution",
        ] + [str(blocker) for blocker in (item.get("blockedBy") or [])]
        action = base_action(
            action_id=action_id,
            lane=lane,
            priority=int(item.get("priority") or 70),
            source_artifact=".rumbling-hedge/state/alpha-frontier-queue.latest.json",
            test={**item, "commandHint": command_hint},
            commands=commands,
            promotion_gate=str(item.get("promotionGate") or "frontier item needs a dedicated evidence gate before promotion"),
            blockers=blockers,
        ) | {
            "dataAvailable": bool_value(item.get("dataAvailable")),
            "dataPaths": item.get("dataPaths") if isinstance(item.get("dataPaths"), list) else [],
            "researchSteps": research_steps,
        }
        forward_plan = (
            prediction_event_clob_targets.get("forwardCapturePlan")
            if isinstance(prediction_event_clob_targets.get("forwardCapturePlan"), dict)
            else {}
        )
        if action_id == "prediction-news-first-event-lag-study" and forward_plan.get("required") is True:
            forward_command = str(forward_plan.get("reviewLeadCommand") or forward_plan.get("command") or "").strip()
            if forward_command:
                commands = list(action["commands"])
                if forward_command not in commands:
                    insert_at = 0
                    for idx, command in enumerate(commands):
                        if "bill:prediction-event-clob-capture-targets" in command:
                            insert_at = idx + 1
                            break
                    commands.insert(insert_at, forward_command)
                action["commands"] = commands
            action["forwardCapturePlan"] = {
                "required": True,
                "reason": forward_plan.get("reason"),
                "command": forward_plan.get("command"),
                "reviewLeadCommand": forward_plan.get("reviewLeadCommand"),
                "preferredCommand": forward_command,
                "unrecoverablePreEventTargetCount": prediction_event_clob_targets.get("unrecoverablePreEventTargetCount"),
                "preEventRecoverableTargetCount": prediction_event_clob_targets.get("preEventRecoverableTargetCount"),
            }
            existing_hint = str(action.get("commandHint") or item.get("commandHint") or "").strip()
            if existing_hint == "missing":
                existing_hint = ""
            forward_hint = "Forward capture is required because mapped headlines are already older than the pre-event window; run standing CLOB recording before future news windows."
            action["commandHint"] = f"{existing_hint} {forward_hint}".strip()
        actions.append(action)
    return actions


def locked_env_command(command: str) -> str:
    return (
        "BILL_ENABLE_FUTURES_DEMO_EXECUTION=false "
        "RH_TOPSTEP_READ_ONLY=true "
        "RH_LIVE_EXECUTION_ENABLED=false "
        f"{command}"
    )


def control_actions(
    live: dict[str, Any],
    data_freshness: dict[str, Any],
    worktree: dict[str, Any],
    open_session_proof: dict[str, Any] | None = None,
    broker_parity_plan: dict[str, Any] | None = None,
    session_safety: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    blockers = live.get("blockers") if isinstance(live.get("blockers"), list) else []
    source_blockers = worktree.get("sourceCleanBlockers") if isinstance(worktree.get("sourceCleanBlockers"), list) else []
    open_session_proof = open_session_proof or {}
    session_summary = topstep_session_safety_summary(session_safety)
    proof_paused = bool_value(session_summary.get("pauseBrokerTouchingProofs"))
    proof_state = open_session_proof.get("stateSummary") if isinstance(open_session_proof.get("stateSummary"), dict) else {}
    broker_parity_plan = broker_parity_plan or {}
    broker_next_window = (
        broker_parity_plan.get("nextOpenSessionProofWindow")
        if isinstance(broker_parity_plan.get("nextOpenSessionProofWindow"), dict)
        else {}
    )
    proof_next_window = (
        proof_state.get("nextOpenSessionProofWindow")
        if isinstance(proof_state.get("nextOpenSessionProofWindow"), dict)
        else {}
    )
    next_proof_window = broker_next_window or proof_next_window
    if blockers or source_blockers:
        proof_commands = (
            [
                "npm run --silent bill:futures-broker-parity-plan",
                "npm run --silent bill:realtime-data-preflight || true",
            ]
            if proof_paused
            else [
                "npm run --silent bill:open-session-data-proof",
                locked_env_command("npm run --silent bill:open-session-data-proof -- --run-data-only"),
            ]
        )
        actions.append({
            "id": "control-plane-clearance-before-demo",
            "lane": "control-plane",
            "priority": 1,
            "sourceArtifact": ".rumbling-hedge/state/live-readiness-gate.latest.json",
            "commands": [
                "npm run --silent bill:realtime-data-preflight || true",
                "npm run --silent bill:data-freshness-gate || true",
                *proof_commands,
                *([] if proof_paused else [
                    "BILL_INCLUDE_DATABENTO_OPTIONAL_PROOF=true BILL_ENABLE_FUTURES_DEMO_EXECUTION=false RH_TOPSTEP_READ_ONLY=true RH_LIVE_EXECUTION_ENABLED=false npm run --silent bill:open-session-data-proof -- --run-data-only --include-databento-optional-proof"
                ]),
                "npm run --silent bill:hermes-storage-audit",
                "npm run --silent bill:codex-automation-audit",
                "npm run --silent bill:worktree-consolidation || true",
                "npm run --silent bill:sibling-worktree-intake",
                "npm run --silent bill:source-intake-manifest",
                "npm run --silent bill:source-hygiene-plan",
                "npm run --silent bill:source-packet-review",
                "npm run --silent bill:data-intake-manifest",
                "npm run --silent bill:verify-execution-quarantine",
                "npm run --silent bill:execution-intake-manifest",
                "npm run --silent bill:live-readiness-gate || true",
                *([] if proof_paused else ["npm run --silent bill:clearance-evidence"]),
                "npm run --silent bill:clearance-handoff",
                "npm run --silent bill:alpha-research-direction-audit",
                "npm run --silent bill:current-alpha-watch",
                "npm run --silent bill:goal-completion-audit",
                "npm run --silent bill:obsidian-sync",
            ],
            "promotionGate": "demo/live remains blocked until live-readiness blockers are empty",
            "promotionBlockers": blockers + source_blockers,
            "dataFreshness": {
                "verdict": data_freshness.get("verdict", "missing"),
                "action": data_freshness.get("action", "missing"),
            },
            "nextWindow": next_proof_window,
            "dataOnlyProof": {
                "mode": open_session_proof.get("mode", "missing"),
                "executionGradeDataProofPassed": bool_value(open_session_proof.get("executionGradeDataProofPassed")),
                "plannedStepIds": open_session_proof.get("plannedStepIds") if isinstance(open_session_proof.get("plannedStepIds"), list) else [],
                "runCommand": None if proof_paused else locked_env_command("npm run --silent bill:open-session-data-proof -- --run-data-only"),
                "optionalDatabentoRunCommand": None if proof_paused else "BILL_INCLUDE_DATABENTO_OPTIONAL_PROOF=true " + locked_env_command("npm run --silent bill:open-session-data-proof -- --run-data-only --include-databento-optional-proof"),
                "proofCommandsPausedReason": session_summary.get("reason") if proof_paused else None,
                "preferredDataPath": open_session_proof.get("preferredDataPath", "topstepx_projectx"),
                "includeDatabentoOptionalProof": bool_value(open_session_proof.get("includeDatabentoOptionalProof")),
                "skippedOptionalStepIds": open_session_proof.get("skippedOptionalStepIds") if isinstance(open_session_proof.get("skippedOptionalStepIds"), list) else [],
                "pausedByTopstepSessionSafety": proof_paused,
                "topstepSessionSafety": session_summary,
                "writesOrders": False,
                "touchesBroker": False if proof_paused else bool_value(open_session_proof.get("touchesBroker")),
                "brokerTouchMode": None if proof_paused else open_session_proof.get("brokerTouchMode"),
                "brokerReadOnlyStepIncluded": bool_value(open_session_proof.get("brokerReadOnlyStepIncluded")),
                "movesFunds": False,
            },
            "writesOrders": False,
            "touchesBroker": False,
            "researchOnly": True,
            "operatorApprovalRequiredBeforeExecution": True,
        })
    return actions


def research_data_quality_summary(data_quality: dict[str, Any]) -> dict[str, Any]:
    datasets = data_quality.get("datasets") if isinstance(data_quality.get("datasets"), list) else []
    return {
        "present": bool(data_quality),
        "pass": bool_value(data_quality.get("pass")),
        "failingDatasets": data_quality.get("failingDatasets") if isinstance(data_quality.get("failingDatasets"), list) else [],
        "datasets": [
            {
                "name": Path(str(item.get("path", ""))).name,
                "rows": item.get("rows"),
                "endTs": item.get("endTs"),
                "pass": bool_value(item.get("pass")),
                "failingChecks": item.get("failingChecks") if isinstance(item.get("failingChecks"), list) else [],
            }
            for item in datasets
            if isinstance(item, dict)
        ],
    }


def action_digest(actions: list[dict[str, Any]], limit: int = 8) -> list[dict[str, Any]]:
    return [
        {
            "id": action.get("id"),
            "lane": action.get("lane"),
            "priority": action.get("priority"),
            "oneVariable": action.get("oneVariable"),
            "firstCommand": action.get("firstCommand"),
            "command": action.get("firstCommand"),
            "commands": action.get("commands") if isinstance(action.get("commands"), list) else [],
            "storageBlocked": bool_value(action.get("storageBlocked")),
            "writesOrders": bool_value(action.get("writesOrders")),
            "touchesBroker": bool_value(action.get("touchesBroker")),
            "researchOnly": bool_value(action.get("researchOnly")),
        }
        for action in actions[:limit]
    ]


def build_actions(args: argparse.Namespace) -> dict[str, Any]:
    futures = read_json(Path(args.futures_triage))
    prediction = read_json(Path(args.prediction_triage))
    seed_triage = read_json(Path(args.research_seed_triage))
    live = read_json(Path(args.live_readiness))
    data_freshness = read_json(Path(args.data_freshness))
    data_quality = read_json(Path(getattr(args, "futures_data_quality", STATE / "futures-data-quality.latest.json")))
    worktree = read_json(Path(args.worktree))
    positioning = read_json(Path(getattr(args, "cftc_positioning", STATE / "cftc-tff-positioning.latest.json")))
    cot_research = read_json(Path(getattr(args, "cot_regime_filter", STATE / "cot-regime-filter-research.latest.json")))
    futures_no_edge_path = getattr(args, "futures_no_edge", None)
    futures_no_edge = read_json(Path(futures_no_edge_path)) if futures_no_edge_path else {}
    topstep_daily_learning_path = getattr(args, "topstep_daily_learning", None)
    topstep_daily_learning = read_json(Path(topstep_daily_learning_path)) if topstep_daily_learning_path else {}
    category_drilldown = read_json(Path(getattr(args, "prediction_category_drilldown", STATE / "prediction-category-drilldown.latest.json")))
    prediction_no_edge = read_json(Path(getattr(args, "prediction_no_edge", ROOT / ".rumbling-hedge/research/prediction-no-edge-ledger/latest.json")))
    prediction_event_lag_watch_review = read_json(Path(getattr(args, "prediction_event_lag_watch_review", STATE / "prediction-event-lag-watch-review.latest.json")))
    prediction_event_lag_manual_review = read_json(Path(getattr(args, "prediction_event_lag_manual_review", STATE / "prediction-event-lag-manual-review.latest.json")))
    prediction_event_market_mapping = read_json(Path(getattr(args, "prediction_event_market_mapping", STATE / "prediction-event-market-mapping-plan.latest.json")))
    prediction_event_mapping_refinement = read_json(Path(getattr(args, "prediction_event_mapping_refinement", STATE / "prediction-event-mapping-refinement.latest.json")))
    alpha_frontier = read_json(Path(getattr(args, "alpha_frontier", STATE / "alpha-frontier-queue.latest.json")))
    prediction_event_clob_targets = read_json(Path(getattr(args, "prediction_event_clob_targets", STATE / "prediction-event-clob-capture-targets.latest.json")))
    open_session_proof = read_json(Path(getattr(args, "open_session_data_proof", STATE / "bill-open-session-data-proof.latest.json")))
    broker_parity_plan_path = getattr(args, "futures_broker_parity_plan", None)
    broker_parity_plan = read_json(Path(broker_parity_plan_path)) if broker_parity_plan_path else {}
    session_safety_path = getattr(args, "topstep_session_safety", None)
    session_safety = read_json(Path(session_safety_path)) if session_safety_path else {}
    storage = storage_gate(args, live)

    actions = (
        control_actions(live, data_freshness, worktree, open_session_proof, broker_parity_plan, session_safety)
        + futures_actions(futures, session_safety)
        + topstep_learning_actions(topstep_daily_learning)
        + futures_positioning_actions(positioning, cot_research, futures_no_edge)
        + prediction_actions(prediction, category_drilldown, prediction_no_edge, storage)
        + prediction_event_watch_actions(
            prediction_event_lag_watch_review,
            prediction_event_lag_manual_review,
            prediction_event_market_mapping,
            prediction_event_mapping_refinement,
            prediction_event_clob_targets,
        )
        + alpha_frontier_actions(alpha_frontier, prediction_event_clob_targets)
        + seed_actions(seed_triage, suppress_youtube_extraction=alpha_frontier_has_reviewed_youtube(alpha_frontier))
    )
    actions = [finalize_action(action) for action in actions]
    actions.sort(key=lambda item: int(item.get("priority", 999)))
    lead_action = actions[0] if actions else {}
    lead_commands = [str(command) for command in (lead_action.get("commands") or [])]
    blockers_present = bool(
        (live.get("blockers") if isinstance(live.get("blockers"), list) else [])
        or (worktree.get("sourceCleanBlockers") if isinstance(worktree.get("sourceCleanBlockers"), list) else [])
    )

    return {
        "command": "bill-next-research-actions",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "decision": "research-queue-visible-execution-locked" if actions else "no-research-actions-visible-execution-locked",
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "readyForExecution": False,
        "readyForDemoExpansion": False,
        "readyForLive": False,
        "blocked": blockers_present,
        "priorityLanes": ["control-plane", "futures", "prediction-markets", "alpha-frontier", "research-seeds"],
        "nextActions": action_digest(actions, limit=20),
        "queue": action_digest(actions, limit=20),
        "commands": lead_commands,
        "leadActionId": lead_action.get("id"),
        "leadLane": lead_action.get("lane"),
        "gateSnapshot": {
            "readyForLive": bool_value(live.get("readyForLive")),
            "readyForDemoExpansion": bool_value(live.get("readyForDemoExpansion")),
            "liveBlockers": live.get("blockers") or [],
            "dataFreshnessVerdict": data_freshness.get("verdict", "missing"),
            "dataFreshnessAction": data_freshness.get("action", "missing"),
            "storageGate": storage,
            "futuresResearchDataQuality": research_data_quality_summary(data_quality),
            "sourceCleanBlockers": worktree.get("sourceCleanBlockers") or [],
            "futuresDecision": futures.get("decision", "missing"),
            "topstepDailyLearning": {
                "present": bool(topstep_daily_learning),
                "learningStatus": topstep_daily_learning.get("learningStatus", "missing"),
                "issueCount": topstep_daily_learning.get("issueCount", 0),
                "operatorReportedPnl": topstep_daily_learning.get("operatorReportedPnl")
                if isinstance(topstep_daily_learning.get("operatorReportedPnl"), dict)
                else {},
                "accountSizing": topstep_daily_learning.get("accountSizing")
                if isinstance(topstep_daily_learning.get("accountSizing"), dict)
                else {},
                "readyForExecution": bool_value(topstep_daily_learning.get("readyForExecution")),
                "readyForDemoExpansion": bool_value(topstep_daily_learning.get("readyForDemoExpansion")),
            },
            "topstepSessionSafety": topstep_session_safety_summary(session_safety),
            "predictionDecision": prediction.get("decision", "missing"),
            "predictionEventLagWatch": {
                "watchReady": bool_value(prediction_event_lag_watch_review.get("watchReady")),
                "watchWindowCount": len(prediction_event_lag_watch_review.get("watchWindows") or [])
                if isinstance(prediction_event_lag_watch_review.get("watchWindows"), list)
                else 0,
                "readyForPaper": bool_value(prediction_event_lag_watch_review.get("readyForPaper")),
                "readyForExecution": bool_value(prediction_event_lag_watch_review.get("readyForExecution")),
                "decision": prediction_event_lag_watch_review.get("decision", "missing"),
            },
            "predictionEventLagManualReview": {
                "present": bool(prediction_event_lag_manual_review),
                "decision": prediction_event_lag_manual_review.get("decision", "missing"),
                "reviewedWindowCount": prediction_event_lag_manual_review.get("reviewedWindowCount", 0),
                "decisionCounts": (
                    prediction_event_lag_manual_review.get("decisionCounts")
                    if isinstance(prediction_event_lag_manual_review.get("decisionCounts"), dict)
                    else {}
                ),
                "readyForPaper": bool_value(prediction_event_lag_manual_review.get("readyForPaper")),
                "readyForExecution": bool_value(prediction_event_lag_manual_review.get("readyForExecution")),
            },
            "predictionEventMarketMapping": {
                "decision": prediction_event_market_mapping.get("decision", "missing"),
                "blockers": (
                    prediction_event_market_mapping.get("blockers")
                    if isinstance(prediction_event_market_mapping.get("blockers"), list)
                    else []
                ),
                "ambiguousHeadlineCount": prediction_event_market_mapping.get("ambiguousHeadlineCount", 0),
            },
            "predictionEventMappingRefinement": {
                "decision": prediction_event_mapping_refinement.get("decision", "missing"),
                "blockers": (
                    prediction_event_mapping_refinement.get("blockers")
                    if isinstance(prediction_event_mapping_refinement.get("blockers"), list)
                    else []
                ),
                "mappingQualityCounts": (
                    prediction_event_mapping_refinement.get("mappingQualityCounts")
                    if isinstance(prediction_event_mapping_refinement.get("mappingQualityCounts"), dict)
                    else {}
                ),
            },
            "predictionCategoryLanes": [
                item.get("category")
                for item in current_category_universe(category_drilldown).get("categories", [])
                if item.get("category")
            ],
            "cftcTffFreshForWeeklyResearch": positioning.get("freshForWeeklyResearch", False),
            "cftcTffLatestReportDate": positioning.get("latestReportDate", "missing"),
        },
        "actions": actions,
        "hardRules": [
            "This queue never approves orders.",
            "Run commands exactly as listed or create a new artifact explaining why a command changed.",
            "Do not lower thresholds to manufacture candidates.",
            "A green research command is not promotion unless the named promotion gate also passes.",
        ],
    }


def render_markdown(payload: dict[str, Any]) -> str:
    gate = payload["gateSnapshot"]
    generated_date = str(payload.get("generatedAt") or datetime.now(timezone.utc).date().isoformat())[:10]
    lines = [
        f"# Bill Next Research Actions - {generated_date}",
        "",
        "Parent hub: [[BILL-CONTROL-HUB]]",
        "",
        "Research-only queue. This page does not approve orders.",
        "",
        "## Gate Snapshot",
        "",
        f"- Ready for live: `{gate['readyForLive']}`",
        f"- Ready for demo expansion: `{gate['readyForDemoExpansion']}`",
        f"- Data freshness: `{gate['dataFreshnessVerdict']}` / `{gate['dataFreshnessAction']}`",
        f"- Futures research data quality: `{gate.get('futuresResearchDataQuality')}`",
        f"- Topstep daily learning: `{gate.get('topstepDailyLearning')}`",
        f"- Prediction category lanes: `{gate.get('predictionCategoryLanes', [])}`",
        f"- Prediction event-lag watch: `{gate.get('predictionEventLagWatch')}`",
        f"- Prediction event-lag manual review: `{gate.get('predictionEventLagManualReview')}`",
        f"- CFTC TFF positioning fresh: `{gate.get('cftcTffFreshForWeeklyResearch')}` latest `{gate.get('cftcTffLatestReportDate')}`",
        f"- Live blockers: `{gate['liveBlockers']}`",
        f"- Source blockers: `{gate['sourceCleanBlockers']}`",
        "",
        "## Actions",
        "",
    ]
    for action in payload.get("actions") or []:
        lines.append(f"### {action.get('priority')}. {action.get('id')}")
        lines.append("")
        lines.append(f"- Lane: `{action.get('lane')}`")
        lines.append(f"- Source artifact: `{action.get('sourceArtifact')}`")
        if action.get("currentCategoryUniverse"):
            lines.append(f"- Current category universe: `{action.get('currentCategoryUniverse')}`")
        if action.get("watchWindowSummary"):
            lines.append(f"- Watch windows: `{action.get('watchWindowSummary')}`")
        lines.append(f"- Promotion gate: {action.get('promotionGate')}")
        lines.append(f"- Promotion blockers: `{action.get('promotionBlockers')}`")
        lines.append("- Commands:")
        for command in action.get("commands") or []:
            lines.append(f"  - `{command}`")
        lines.append("")
    lines.extend(["## Hard Rules", ""])
    for rule in payload.get("hardRules") or []:
        lines.append(f"- {rule}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the Bill/Hermes next research action queue.")
    parser.add_argument("--futures-triage", default=str(STATE / "futures-evidence-triage.latest.json"))
    parser.add_argument("--prediction-triage", default=str(STATE / "prediction-evidence-triage.latest.json"))
    parser.add_argument("--research-seed-triage", default=str(STATE / "research-seed-triage.latest.json"))
    parser.add_argument("--live-readiness", default=str(STATE / "live-readiness-gate.latest.json"))
    parser.add_argument("--data-freshness", default=str(STATE / "data-freshness-gate.latest.json"))
    parser.add_argument("--futures-data-quality", default=str(STATE / "futures-data-quality.latest.json"))
    parser.add_argument("--worktree", default=str(STATE / "worktree-consolidation.latest.json"))
    parser.add_argument("--cftc-positioning", default=str(STATE / "cftc-tff-positioning.latest.json"))
    parser.add_argument("--cot-regime-filter", default=str(STATE / "cot-regime-filter-research.latest.json"))
    parser.add_argument("--futures-no-edge", default=str(ROOT / ".rumbling-hedge/research/futures-no-edge-ledger/latest.json"))
    parser.add_argument("--topstep-daily-learning", default=str(STATE / "topstep-daily-learning.latest.json"))
    parser.add_argument("--prediction-category-drilldown", default=str(STATE / "prediction-category-drilldown.latest.json"))
    parser.add_argument("--prediction-no-edge", default=str(ROOT / ".rumbling-hedge/research/prediction-no-edge-ledger/latest.json"))
    parser.add_argument("--prediction-event-lag-watch-review", default=str(STATE / "prediction-event-lag-watch-review.latest.json"))
    parser.add_argument("--prediction-event-lag-manual-review", default=str(STATE / "prediction-event-lag-manual-review.latest.json"))
    parser.add_argument("--prediction-event-market-mapping", default=str(STATE / "prediction-event-market-mapping-plan.latest.json"))
    parser.add_argument("--prediction-event-mapping-refinement", default=str(STATE / "prediction-event-mapping-refinement.latest.json"))
    parser.add_argument("--alpha-frontier", default=str(STATE / "alpha-frontier-queue.latest.json"))
    parser.add_argument("--prediction-event-clob-targets", default=str(STATE / "prediction-event-clob-capture-targets.latest.json"))
    parser.add_argument("--open-session-data-proof", default=str(STATE / "bill-open-session-data-proof.latest.json"))
    parser.add_argument("--futures-broker-parity-plan", default=str(STATE / "futures-broker-parity-plan.latest.json"))
    parser.add_argument("--topstep-session-safety", default=str(TOPSTEP_SESSION_SAFETY))
    parser.add_argument("--storage-free-gb", type=float, default=None)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=None)
    args = parser.parse_args()

    payload = build_actions(args)
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
