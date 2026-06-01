#!/usr/bin/env python3
"""Write concrete futures data requirements before demo expansion.

Research-only. This turns current data blockers into a checklist of required
data sources, minimum history, and proof artifacts. It does not fetch data,
route orders, or approve Topstep demo expansion.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
OUT = STATE / "futures-data-requirements.latest.json"
VAULT = Path.home() / "Documents/memorybrain"
CURRENT_DATA_PARITY = STATE / "futures-nq-current-data-parity.latest.json"
HISTORICAL_COVERAGE = STATE / "futures-nq-historical-coverage-audit.latest.json"
HISTORICAL_REPLAY = STATE / "futures-nq-historical-session-replay.latest.json"
HISTORICAL_WALKFORWARD = STATE / "futures-nq-historical-session-walkforward.latest.json"
HISTORICAL_COST_STRESS = STATE / "futures-nq-historical-session-cost-stress.latest.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def current_utc_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


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
) -> dict[str, Any]:
    nq_local = external_audit.get("nqLocalParity") if isinstance(external_audit.get("nqLocalParity"), dict) else {}
    nq_source = external_audit.get("nqSourceParity") if isinstance(external_audit.get("nqSourceParity"), dict) else {}
    current_data_parity = current_data_parity or {}
    historical_coverage = historical_coverage or {}
    historical_replay = historical_replay or {}
    historical_walkforward = historical_walkforward or {}
    historical_cost_stress = historical_cost_stress or {}
    session_count = int(session_audit.get("sessionCount") or 0)
    verdict = data_freshness.get("verdict") or data_freshness.get("status")
    action = data_freshness.get("action")
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
            req_id="nq-current-local-or-broker-parity",
            title="Current NQ 1m data must overlap broker/local bars",
            status="pass" if nq_local.get("ok") and broker_parity_checked else "blocked",
            current={
                "ok": bool(nq_local.get("ok")),
                "overlapRows": nq_local.get("overlapRows"),
                "reason": nq_local.get("reason") or nq_local.get("error"),
                "localInternalParityDecision": current_data_parity.get("decision"),
                "localInternalCleanPairCount": clean_current_pairs,
                "brokerParityChecked": broker_parity_checked,
            },
            needed={
                "minimumOverlapRows": 100,
                "maxCloseAbsDiff": 0.01,
                "source": "current broker-grade or broker-reconciled NQ 1m bars",
            },
            proof_commands=[
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
            status="pass" if session_count >= 20 and nq_local.get("ok") and broker_parity_checked else "blocked",
            current={
                "sessionCount": session_count,
                "decision": session_audit.get("decision"),
                "range": session_audit.get("range"),
                "brokerParityChecked": broker_parity_checked,
                "currentNqParityOk": bool(nq_local.get("ok")),
            },
            needed={
                "minimumSessionsForResearch": 20,
                "preferredSessionsForPromotionReview": 60,
                "currentBrokerOrBrokerReconciledBarsRequired": True,
            },
            proof_commands=["npm run --silent bill:futures-nq-session-structure-audit"],
            blocks=["current NQ replay", "Topstep demo expansion"],
        ),
        requirement(
            req_id="futures-execution-grade-realtime",
            title="Realtime futures data must be execution-grade before routing",
            status="pass" if verdict == "FRESH" and action != "block_all_trades" else "blocked",
            current={"verdict": verdict, "action": action},
            needed={
                "executionGrade": True,
                "fallbackYahooDelayedAllowed": False,
                "marketOpenSmokeRequired": True,
            },
            proof_commands=[
                "npm run --silent bill:realtime-data-preflight || true",
                "npm run --silent bill:databento-realtime-smoke",
                "npm run --silent bill:data-freshness-gate || true",
            ],
            blocks=["master bridge routing", "Topstep demo submission", "live-readiness gate"],
        ),
    ]
    blocked = [item for item in requirements if item["status"] != "pass"]
    return {
        "command": "futures-data-requirements",
        "generatedAt": now_iso(),
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "readyForDemoExpansion": False,
        "requirements": requirements,
        "blockedCount": len(blocked),
        "passCount": len(requirements) - len(blocked),
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
