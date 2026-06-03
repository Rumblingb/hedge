#!/usr/bin/env python3
"""Write concrete futures data requirements before demo expansion.

Research-only. This turns current data blockers into a checklist of required
data sources, minimum history, and proof artifacts. It does not fetch data,
route orders, or approve Topstep demo expansion.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
OUT = STATE / "futures-data-requirements.latest.json"
VAULT = Path.home() / "Documents/memorybrain"
CURRENT_DATA_PARITY = STATE / "futures-nq-current-data-parity.latest.json"
HISTORICAL_COVERAGE = STATE / "futures-nq-historical-coverage-audit.latest.json"
HISTORICAL_REPLAY = STATE / "futures-nq-historical-session-replay.latest.json"
HISTORICAL_WALKFORWARD = STATE / "futures-nq-historical-session-walkforward.latest.json"
HISTORICAL_COST_STRESS = STATE / "futures-nq-historical-session-cost-stress.latest.json"
TOPSTEP_MARKET_DATA_SMOKE = STATE / "topstep-market-data-smoke.latest.json"
TOPSTEP_BROKER_LOCAL_BAR_PARITY = STATE / "topstep-broker-local-bar-parity.latest.json"
TOPSTEP_READONLY_BAR_ARCHIVE = STATE / "topstep-readonly-bar-archive.latest.json"
TOPSTEP_REALTIME_PROOF = STATE / "topstep-realtime-proof.latest.json"
TRADING_TIMEZONE = ZoneInfo(os.environ.get("BILL_TRADING_TIMEZONE", "Europe/London"))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def current_utc_date() -> str:
    return datetime.now(timezone.utc).astimezone(TRADING_TIMEZONE).date().isoformat()


def default_markdown_path() -> Path:
    return VAULT / "Agent-Hermes" / f"futures-data-requirements-{current_utc_date()}.md"


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def requirement(
    *,
    req_id: str,
    title: str,
    status: str,
    current: dict[str, Any],
    needed: dict[str, Any],
    proof_commands: list[str],
    blocks: list[str],
) -> dict[str, Any]:
    return {
        "id": req_id,
        "title": title,
        "status": status,
        "current": current,
        "needed": needed,
        "proofCommands": proof_commands,
        "blocks": blocks,
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
    }


def build_requirements(
    *,
    external_audit: dict[str, Any],
    session_audit: dict[str, Any],
    data_freshness: dict[str, Any],
    live_readiness: dict[str, Any],
    current_data_parity: dict[str, Any] | None = None,
    historical_coverage: dict[str, Any] | None = None,
    historical_replay: dict[str, Any] | None = None,
    historical_walkforward: dict[str, Any] | None = None,
    historical_cost_stress: dict[str, Any] | None = None,
    topstep_market_data_smoke: dict[str, Any] | None = None,
    topstep_broker_local_bar_parity: dict[str, Any] | None = None,
    topstep_readonly_bar_archive: dict[str, Any] | None = None,
    topstep_realtime_proof: dict[str, Any] | None = None,
) -> dict[str, Any]:
    nq_local = external_audit.get("nqLocalParity") if isinstance(external_audit.get("nqLocalParity"), dict) else {}
    nq_source = external_audit.get("nqSourceParity") if isinstance(external_audit.get("nqSourceParity"), dict) else {}
    current_data_parity = current_data_parity or {}
    historical_coverage = historical_coverage or {}
    historical_replay = historical_replay or {}
    historical_walkforward = historical_walkforward or {}
    historical_cost_stress = historical_cost_stress or {}
    topstep_market_data_smoke = topstep_market_data_smoke or {}
    topstep_bar_source_ok = bool(topstep_market_data_smoke.get("brokerCurrentBarsProofPassed"))
    topstep_broker_local_bar_parity = topstep_broker_local_bar_parity or {}
    broker_local_parity_checked = bool(topstep_broker_local_bar_parity.get("brokerParityChecked"))
    broker_local_parity_passed = bool(topstep_broker_local_bar_parity.get("brokerParityPassed"))
    topstep_readonly_bar_archive = topstep_readonly_bar_archive or {}
    topstep_realtime_proof = topstep_realtime_proof or {}
    archive_nq_sessions = int(topstep_readonly_bar_archive.get("nqArchiveRthSessionCount") or 0)
    archive_depth_ready = bool(topstep_readonly_bar_archive.get("brokerBarArchiveReadyForResearchDepth"))
    archive_symbols = topstep_readonly_bar_archive.get("symbols") if isinstance(topstep_readonly_bar_archive.get("symbols"), dict) else {}
    archive_nq = archive_symbols.get("NQ") if isinstance(archive_symbols.get("NQ"), dict) else {}
    archive_nq_rows = int(archive_nq.get("rowCount") or 0)
    topstep_direct_broker_source_ok = (
        topstep_bar_source_ok
        and topstep_readonly_bar_archive.get("status") == "PASS"
        and archive_nq_rows > 0
    )
    session_count = int(session_audit.get("sessionCount") or 0)
    broker_relevant_session_count = max(session_count, archive_nq_sessions)
    verdict = data_freshness.get("verdict") or data_freshness.get("status")
    action = data_freshness.get("action")
    freshness_allows_trades = verdict in {"PASS", "FRESH"} and action == "allow_trades"
    topstep_realtime_proof_ready = bool(topstep_realtime_proof.get("readyForExecutionDataProof"))
    blockers = live_readiness.get("blockers") if isinstance(live_readiness.get("blockers"), list) else []
    clean_current_pairs = int(current_data_parity.get("cleanLocalResearchPairCount") or 0)
    best_current_pair = current_data_parity.get("bestCurrentLocalResearchPair") if isinstance(current_data_parity.get("bestCurrentLocalResearchPair"), dict) else {}
    broker_parity_checked = bool(current_data_parity.get("brokerParityChecked"))
    historical_best = historical_coverage.get("bestHistoricalOosCandidate") if isinstance(historical_coverage.get("bestHistoricalOosCandidate"), dict) else {}
    historical_session_count = int(historical_best.get("sessionCount") or 0)
    historical_source_parity = historical_best.get("sourceParity") if isinstance(historical_best.get("sourceParity"), dict) else {}
    historical_depth_ok = (
        historical_session_count >= 60
        and bool(historical_best.get("usableForHistoricalOosResearch"))
        and bool(historical_best.get("preferredForPromotionReview"))
        and bool(historical_source_parity.get("ok"))
    )
    historical_replay_oos = historical_replay.get("oosStats") if isinstance(historical_replay.get("oosStats"), dict) else {}
    historical_replay_ok = (
        historical_replay.get("decision") == "research-only-historical-session-replay-watch"
        and int(historical_replay_oos.get("trades") or 0) >= 20
        and float(historical_replay_oos.get("netR") or 0) > 0
        and float(historical_replay_oos.get("profitFactor") or 0) > 1
    )
    historical_walkforward_ok = (
        historical_walkforward.get("decision") == "research-only-historical-session-walkforward-watch"
        and int(historical_walkforward.get("foldCount") or 0) >= 5
        and float(historical_walkforward.get("positiveFoldShare") or 0) >= 0.6
    )
    historical_cost_ok = (
        historical_cost_stress.get("decision") == "research-only-historical-session-cost-stress-watch"
        and int(historical_cost_stress.get("survivingCaseCount") or 0) == int(historical_cost_stress.get("caseCount") or -1)
        and int(historical_cost_stress.get("caseCount") or 0) > 0
    )
    requirements = [
        requirement(
            req_id="nq-current-internal-local-parity",
            title="Current NQ research files must be internally consistent",
            status="pass" if clean_current_pairs > 0 else "blocked",
            current={
                "decision": current_data_parity.get("decision"),
                "cleanLocalResearchPairCount": clean_current_pairs,
                "bestCurrentLocalResearchPair": best_current_pair.get("pairId"),
                "brokerParityChecked": broker_parity_checked,
            },
            needed={
                "minimumCleanLocalResearchPairs": 1,
                "maxOHLCVDiffOnOverlap": 0.01,
                "brokerParityRequiredSeparately": True,
            },
            proof_commands=["npm run --silent bill:futures-nq-current-data-parity"],
            blocks=["current research replay source selection"],
        ),
        requirement(
            req_id="topstep-current-market-data-bars",
            title="TopstepX must return read-only current NQ/MNQ bars",
            status="pass" if topstep_bar_source_ok else "blocked",
            current={
                "status": topstep_market_data_smoke.get("status"),
                "brokerCurrentBarsProofPassed": topstep_market_data_smoke.get("brokerCurrentBarsProofPassed"),
                "symbols": topstep_market_data_smoke.get("symbols") or {},
                "brokerTouchMode": topstep_market_data_smoke.get("brokerTouchMode"),
            },
            needed={
                "nqBars": True,
                "mnqBars": True,
                "readOnlyBrokerTouchAllowed": True,
                "ordersAllowed": False,
                "clearsRealtimeFreshness": False,
            },
            proof_commands=[
                "BILL_ENABLE_FUTURES_DEMO_EXECUTION=false RH_TOPSTEP_READ_ONLY=true RH_LIVE_EXECUTION_ENABLED=false npm run --silent bill:topstep-market-data-smoke"
            ],
            blocks=["broker-current bar source proof", "current local-vs-broker parity follow-up"],
        ),
        requirement(
            req_id="topstep-readonly-bar-archive",
            title="TopstepX read-only bars should accumulate into a broker-relevant session archive",
            status="pass" if topstep_readonly_bar_archive.get("status") == "PASS" else "blocked",
            current={
                "status": topstep_readonly_bar_archive.get("status"),
                "nqArchiveRthSessionCount": archive_nq_sessions,
                "nqArchiveSessionCount": topstep_readonly_bar_archive.get("nqArchiveSessionCount"),
                "brokerBarArchiveReadyForResearchDepth": archive_depth_ready,
                "archiveDir": topstep_readonly_bar_archive.get("archiveDir"),
                "symbols": topstep_readonly_bar_archive.get("symbols") or {},
                "brokerTouchMode": topstep_readonly_bar_archive.get("brokerTouchMode"),
            },
            needed={
                "readOnlyBrokerTouchAllowed": True,
                "ordersAllowed": False,
                "minimumSessionsForResearch": 20,
                "preferredSessionsForPromotionReview": 60,
                "clearsRealtimeFreshness": False,
            },
            proof_commands=[
                "BILL_ENABLE_FUTURES_DEMO_EXECUTION=false RH_TOPSTEP_READ_ONLY=true RH_LIVE_EXECUTION_ENABLED=false npm run --silent bill:topstep-readonly-bar-archive"
            ],
            blocks=["broker-relevant current-session depth accumulation"],
        ),
        requirement(
            req_id="nq-current-local-or-broker-parity",
            title="Current NQ 1m data must be broker-grade or overlap broker/local bars",
            status="pass" if (broker_local_parity_passed and topstep_bar_source_ok) or topstep_direct_broker_source_ok else "blocked",
            current={
                "ok": bool(nq_local.get("ok")),
                "overlapRows": nq_local.get("overlapRows"),
                "reason": nq_local.get("reason") or nq_local.get("error"),
                "localInternalParityDecision": current_data_parity.get("decision"),
                "localInternalCleanPairCount": clean_current_pairs,
                "brokerParityChecked": broker_parity_checked,
                "topstepDirectBrokerSourceOk": topstep_direct_broker_source_ok,
                "topstepArchiveNqRows": archive_nq_rows,
                "topstepCurrentBarsProofPassed": topstep_bar_source_ok,
                "topstepBrokerLocalBarParityChecked": broker_local_parity_checked,
                "topstepBrokerLocalBarParityPassed": broker_local_parity_passed,
                "topstepBrokerLocalBarParityStatus": topstep_broker_local_bar_parity.get("status"),
            },
            needed={
                "minimumOverlapRows": 5,
                "maxOhlcAbsDiff": 0.25,
                "source": "current broker-grade TopstepX NQ 1m bars or broker-reconciled local NQ 1m bars",
            },
            proof_commands=[
                "BILL_ENABLE_FUTURES_DEMO_EXECUTION=false RH_TOPSTEP_READ_ONLY=true RH_LIVE_EXECUTION_ENABLED=false npm run --silent bill:topstep-market-data-smoke",
                "BILL_ENABLE_FUTURES_DEMO_EXECUTION=false RH_TOPSTEP_READ_ONLY=true RH_LIVE_EXECUTION_ENABLED=false npm run --silent bill:topstep-broker-local-bar-parity",
                "npm run --silent bill:external-alpha-data-audit",
                "npm run --silent bill:futures-nq-session-structure-audit",
            ],
            blocks=["Topstep demo expansion", "current NQ session replay", "slippage/sizing evidence"],
        ),
        requirement(
            req_id="nq-source-build-parity",
            title="External NQ feature files must match their source CSVs",
            status="pass" if nq_source.get("ok") else "blocked",
            current={"ok": bool(nq_source.get("ok")), "checks": nq_source.get("checks") or []},
            needed={"allChecksOk": True, "maxOHLCVDiff": 0.01},
            proof_commands=["npm run --silent bill:external-alpha-data-audit"],
            blocks=["external historical source-build smoke tests"],
        ),
        requirement(
            req_id="nq-historical-session-oos-depth",
            title="Historical NQ session/ORB research needs independent OOS evidence",
            status="pass" if historical_depth_ok and historical_replay_ok and historical_walkforward_ok and historical_cost_ok else "blocked",
            current={
                "coverageDecision": historical_coverage.get("decision"),
                "bestHistoricalOosCandidate": historical_best.get("datasetId"),
                "historicalSessionCount": historical_session_count,
                "sourceParityOk": bool(historical_source_parity.get("ok")),
                "replayDecision": historical_replay.get("decision"),
                "replayOosStats": historical_replay_oos,
                "walkforwardDecision": historical_walkforward.get("decision"),
                "walkforwardFoldCount": historical_walkforward.get("foldCount"),
                "walkforwardPositiveFoldShare": historical_walkforward.get("positiveFoldShare"),
                "costStressDecision": historical_cost_stress.get("decision"),
                "costStressSurvivingCases": historical_cost_stress.get("survivingCaseCount"),
                "costStressCaseCount": historical_cost_stress.get("caseCount"),
            },
            needed={
                "minimumHistoricalSessionsForPromotionReview": 60,
                "minimumOosTrades": 20,
                "minimumWalkforwardFolds": 5,
                "minimumPositiveFoldShare": 0.6,
                "allCostStressCasesSurvive": True,
                "brokerParityRequiredSeparately": True,
            },
            proof_commands=[
                "npm run --silent bill:futures-nq-historical-coverage-audit",
                "npm run --silent bill:futures-nq-historical-session-replay",
                "npm run --silent bill:futures-nq-historical-session-walkforward",
                "npm run --silent bill:futures-nq-historical-session-cost-stress",
            ],
            blocks=["historical OOS research promotion review", "sizing research"],
        ),
        requirement(
            req_id="nq-current-session-depth-for-demo",
            title="Current NQ session research needs enough broker-relevant sessions",
            status="pass" if broker_relevant_session_count >= 20 and (broker_local_parity_passed or topstep_direct_broker_source_ok) else "blocked",
            current={
                "sessionCount": session_count,
                "brokerRelevantSessionCount": broker_relevant_session_count,
                "topstepArchiveRthSessionCount": archive_nq_sessions,
                "topstepArchiveNqRows": archive_nq_rows,
                "topstepDirectBrokerSourceOk": topstep_direct_broker_source_ok,
                "topstepArchiveStatus": topstep_readonly_bar_archive.get("status"),
                "decision": session_audit.get("decision"),
                "range": session_audit.get("range"),
                "brokerParityChecked": broker_parity_checked,
                "topstepBrokerLocalBarParityPassed": broker_local_parity_passed,
                "currentNqParityOk": bool(nq_local.get("ok")),
            },
            needed={
                "minimumSessionsForResearch": 20,
                "preferredSessionsForPromotionReview": 60,
                "currentBrokerOrBrokerReconciledBarsRequired": True,
            },
            proof_commands=[
                "npm run --silent bill:futures-nq-session-structure-audit",
                "BILL_ENABLE_FUTURES_DEMO_EXECUTION=false RH_TOPSTEP_READ_ONLY=true RH_LIVE_EXECUTION_ENABLED=false npm run --silent bill:topstep-readonly-bar-archive",
            ],
            blocks=["current NQ replay", "Topstep demo expansion"],
        ),
        requirement(
            req_id="futures-execution-grade-realtime",
            title="Realtime futures data must be execution-grade before routing",
            status="pass" if freshness_allows_trades else "blocked",
            current={
                "verdict": verdict,
                "action": action,
                "topstepRealtimeProofStatus": topstep_realtime_proof.get("status"),
                "topstepRealtimeProofReady": topstep_realtime_proof_ready,
                "topstepRealtimeWritesCanonicalQuoteState": topstep_realtime_proof.get("writesRealtimeQuoteState"),
                "topstepRealtimeSymbols": topstep_realtime_proof.get("symbols") or {},
            },
            needed={
                "executionGrade": True,
                "fallbackYahooDelayedAllowed": False,
                "marketOpenSmokeRequired": True,
                "canonicalRealtimeQuoteSource": "topstep_realtime or databento_realtime",
            },
            proof_commands=[
                "BILL_ENABLE_FUTURES_DEMO_EXECUTION=false RH_TOPSTEP_READ_ONLY=true RH_LIVE_EXECUTION_ENABLED=false npm run --silent bill:topstep-realtime-proof",
                "BILL_ENABLE_FUTURES_DEMO_EXECUTION=false RH_TOPSTEP_READ_ONLY=true RH_LIVE_EXECUTION_ENABLED=false npm run --silent bill:topstep-realtime-bridge",
                "npm run --silent bill:realtime-data-preflight || true",
                "npm run --silent bill:databento-realtime-smoke",
                "npm run --silent bill:data-freshness-gate || true",
            ],
            blocks=["master bridge routing", "Topstep demo submission", "live-readiness gate"],
        ),
    ]
    blocked = [item for item in requirements if item["status"] != "pass"]
    passed = [item for item in requirements if item["status"] == "pass"]
    topstep_bar_requirement = next((item for item in requirements if item["id"] == "topstep-current-market-data-bars"), {})
    execution_grade_requirement = next((item for item in requirements if item["id"] == "futures-execution-grade-realtime"), {})
    return {
        "command": "futures-data-requirements",
        "generatedAt": now_iso(),
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "readyForExecution": False,
        "readyForDemoExpansion": False,
        "requirements": requirements,
        "blockedCount": len(blocked),
        "blockedRequirementIds": [item["id"] for item in blocked],
        "passCount": len(requirements) - len(blocked),
        "passedRequirementIds": [item["id"] for item in passed],
        "brokerL1BarsProofPassed": topstep_bar_requirement.get("status") == "pass",
        "topstepRealtimeProofPassed": topstep_realtime_proof_ready,
        "executionGradeRealtimeProofPassed": execution_grade_requirement.get("status") == "pass",
        "dataOnlyReady": False,
        "liveReadinessBlockers": blockers,
        "decision": "research-only-data-requirements-not-cleared" if blocked else "research-only-data-requirements-cleared",
        "nextAction": (
            "Acquire/rebuild current broker-grade NQ 1m history and rerun parity/session/OOS gates before any demo expansion."
            if blocked
            else "Proceed to research-only purged OOS session replay; execution remains separately gated."
        ),
    }


def render_markdown(payload: dict[str, Any]) -> str:
    generated_date = str(payload.get("generatedAt") or current_utc_date())[:10]
    lines = [
        f"# Futures Data Requirements - {generated_date}",
        "",
        "Parent hub: [[BILL-CONTROL-HUB]]",
        "",
        "Research-only data checklist. This page does not approve Topstep demo or live trading.",
        "",
        "## Summary",
        "",
        f"- Decision: `{payload.get('decision')}`",
        f"- Passed: `{payload.get('passCount')}`",
        f"- Blocked: `{payload.get('blockedCount')}`",
        f"- Blocked ids: `{payload.get('blockedRequirementIds', [])}`",
        f"- Broker L1 bars proof passed: `{payload.get('brokerL1BarsProofPassed')}`",
        f"- Execution-grade realtime proof passed: `{payload.get('executionGradeRealtimeProofPassed')}`",
        f"- Ready for execution: `{payload.get('readyForExecution')}`",
        f"- Ready for demo expansion: `{payload.get('readyForDemoExpansion')}`",
        "",
        "## Requirements",
        "",
    ]
    for item in payload.get("requirements") or []:
        lines.extend([
            f"### {item.get('id')}",
            "",
            f"- Title: {item.get('title')}",
            f"- Status: `{item.get('status')}`",
            f"- Current: `{item.get('current')}`",
            f"- Needed: `{item.get('needed')}`",
            f"- Blocks: `{item.get('blocks')}`",
            "- Proof commands:",
        ])
        for command in item.get("proofCommands") or []:
            lines.append(f"  - `{command}`")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    payload = build_requirements(
        external_audit=read_json(STATE / "external-alpha-data-audit.latest.json"),
        session_audit=read_json(STATE / "futures-nq-session-structure-audit.latest.json"),
        data_freshness=read_json(STATE / "data-freshness-gate.latest.json"),
        live_readiness=read_json(STATE / "live-readiness-gate.latest.json"),
        current_data_parity=read_json(CURRENT_DATA_PARITY),
        historical_coverage=read_json(HISTORICAL_COVERAGE),
        historical_replay=read_json(HISTORICAL_REPLAY),
        historical_walkforward=read_json(HISTORICAL_WALKFORWARD),
        historical_cost_stress=read_json(HISTORICAL_COST_STRESS),
        topstep_market_data_smoke=read_json(TOPSTEP_MARKET_DATA_SMOKE),
        topstep_broker_local_bar_parity=read_json(TOPSTEP_BROKER_LOCAL_BAR_PARITY),
        topstep_readonly_bar_archive=read_json(TOPSTEP_READONLY_BAR_ARCHIVE),
        topstep_realtime_proof=read_json(TOPSTEP_REALTIME_PROOF),
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    markdown = default_markdown_path()
    markdown.parent.mkdir(parents=True, exist_ok=True)
    markdown.write_text(render_markdown(payload))
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
