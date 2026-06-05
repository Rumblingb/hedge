#!/usr/bin/env python3
"""
Verify the Bill/Hermes fund OS handoff against the user's explicit objective.

This is not a trading gate. It is a completion and handoff audit for agents:
what is organized, what is guarded, and what is still unsafe or uncovered.
"""

from __future__ import annotations

import csv
import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


HOME = Path.home()
ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / ".rumbling-hedge" / "state"
DOCS_RESEARCH = ROOT / "docs" / "research"
OBSIDIAN_HERMES = HOME / "Documents" / "memorybrain" / "Agent-Hermes"
HERMES_CRON = HOME / ".hermes" / "cron" / "jobs.json"
N8N_DB = HOME / ".n8n" / "database.sqlite"
FUTURES_NO_EDGE = ROOT / ".rumbling-hedge" / "research" / "futures-no-edge-ledger" / "latest.json"
PREDICTION_NO_EDGE = ROOT / ".rumbling-hedge" / "research" / "prediction-no-edge-ledger" / "latest.json"
DATABENTO_SMOKE = STATE_DIR / "databento-realtime-smoke.latest.json"
HERMES_STORAGE_AUDIT = STATE_DIR / "hermes-storage-audit.latest.json"
BILL_CLEARANCE_HANDOFF = STATE_DIR / "bill-clearance-handoff.latest.json"
BILL_CLEARANCE_EVIDENCE = STATE_DIR / "bill-clearance-evidence.latest.json"


@dataclass
class Check:
    requirement: str
    status: str
    evidence: str
    action: str = ""


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def add(checks: list[Check], requirement: str, ok: bool, evidence: str, action: str = "") -> None:
    checks.append(Check(requirement, "PASS" if ok else "BLOCKED", evidence, "" if ok else action))


def warn(checks: list[Check], requirement: str, evidence: str, action: str = "") -> None:
    checks.append(Check(requirement, "WARN", evidence, action))


def file_exists(checks: list[Check], requirement: str, path: Path, action: str) -> None:
    add(checks, requirement, path.exists(), str(path), action)


def read_text(path: Path) -> str:
    try:
        return path.read_text(errors="ignore")
    except Exception:
        return ""


def compact_list(values: object, limit: int = 4) -> str:
    if not isinstance(values, list):
        return str(values)
    preview = values[:limit]
    suffix = "" if len(values) <= limit else f" +{len(values) - limit} more"
    return f"{preview}{suffix}"


def ledger_evidence(path: Path, fields: tuple[str, ...]) -> str:
    data = read_json(path)
    pieces = [f"path={path}"]
    for field in fields:
        pieces.append(f"{field}={data.get(field, 'missing')}")
    return " ".join(pieces)


def latest_csv_ts(path: Path) -> str | None:
    if not path.exists():
        return None
    latest: str | None = None
    with path.open(newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            ts = row.get("ts")
            if ts and (latest is None or ts > latest):
                latest = ts
    return latest


def ts_age_minutes(ts: str | None) -> float | None:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds() / 60
    except Exception:
        return None


def parse_ts(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def is_weekend_after_futures_close(now: datetime) -> bool:
    # Completion audit uses this only for research data handoff freshness. Live
    # routing remains governed by the realtime data-freshness gate.
    weekday = now.weekday()
    if weekday == 4 and now.hour >= 21:
        return True
    if weekday == 5:
        return True
    if weekday == 6 and now.hour < 22:
        return True
    return False


def closed_market_bar_ok(ts: str | None, interval_minutes: int, now: datetime | None = None) -> bool:
    latest = parse_ts(ts)
    now = now or datetime.now(timezone.utc)
    if not latest or not is_weekend_after_futures_close(now):
        return False
    if latest.weekday() != 4:
        return False
    friday_close_minutes = 21 * 60
    latest_minutes = latest.hour * 60 + latest.minute
    tolerance = max(interval_minutes, 15) + 15
    return latest_minutes >= friday_close_minutes - tolerance


def research_data_fresh_enough(ts: str | None, max_age_minutes: int, interval_minutes: int, now: datetime | None = None) -> tuple[bool, str]:
    age = ts_age_minutes(ts)
    if age is not None and age <= max_age_minutes:
        return True, f"latest={ts} age_minutes={age}"
    if closed_market_bar_ok(ts, interval_minutes, now):
        return True, f"latest={ts} age_minutes={age} closed_market_bar_ok=True"
    return False, f"latest={ts} age_minutes={age} closed_market_bar_ok=False"


def audit_shadow_signal(checks: list[Check], filename: str, expected_evidence: str | set[str]) -> None:
    path = STATE_DIR / filename
    data = read_json(path)
    allowed_evidence = {expected_evidence} if isinstance(expected_evidence, str) else expected_evidence
    ok = (
        path.exists()
        and data.get("promoted_for_execution") is False
        and data.get("tradable_signal") is False
        and data.get("evidence_level") in allowed_evidence
    )
    evidence = (
        f"{path} promoted={data.get('promoted_for_execution')} "
        f"tradable={data.get('tradable_signal')} evidence={data.get('evidence_level')}"
    )
    add(
        checks,
        f"{filename} cannot affect execution unless promoted",
        ok,
        evidence,
        "Re-run the generator after patching it to emit shadow-only execution fields.",
    )


def databento_smoke_safe(data: dict) -> bool:
    session = data.get("session") if isinstance(data.get("session"), dict) else {}
    return (
        data.get("researchOnly") is True
        and data.get("writesOrders") is False
        and data.get("touchesBroker") is False
        and data.get("writesRealtimeQuoteState") is False
        and data.get("readyForExecutionDataProof") in {True, False}
        and data.get("status") in {"PASS", "NO_QUOTES", "NO_QUOTES_MARKET_CLOSED", "BLOCKED"}
        and bool(session.get("market"))
        and bool(session.get("reason"))
    )


def hermes_storage_audit_safe(data: dict) -> bool:
    return (
        data.get("researchOnly") is True
        and data.get("writesOrders") is False
        and data.get("touchesBroker") is False
        and data.get("movesFiles") is False
        and data.get("deletesFiles") is False
        and isinstance(data.get("entries"), list)
        and isinstance(data.get("topCandidates"), list)
    )


def clearance_handoff_safe(data: dict) -> bool:
    return (
        data.get("researchOnly") is True
        and data.get("writesOrders") is False
        and data.get("touchesBroker") is False
        and data.get("readyForExecution") is False
        and data.get("decision") == "KEEP_EXECUTION_LOCKED"
        and isinstance(data.get("gates"), dict)
        and isinstance(data.get("lanes"), dict)
        and isinstance(data.get("nextActions"), list)
    )


def clearance_evidence_safe(data: dict) -> bool:
    return (
        data.get("researchOnly") is True
        and data.get("writesOrders") is False
        and data.get("touchesBroker") is False
        and data.get("movesFunds") is False
        and data.get("readyForExecution") is False
        and data.get("status") in {"PASS", "BLOCKED"}
        and isinstance(data.get("results"), list)
    )


def funding_helper_guarded(active_path: Path, retired_path: Path | None = None, *, active_required: bool = False) -> bool:
    path = active_path if active_path.exists() else retired_path
    if path is None or not path.exists():
        return not active_required
    text = read_text(path)
    return (
        "HERMES_ALLOW_POLYMARKET_FUNDING" in text
        and "I_UNDERSTAND_THIS_MOVES_FUNDS" in text
        and "process.exit(2)" in text
        and "BLOCKED" in text
    )


def pass_fail(ok: bool) -> str:
    return "pass" if ok else "blocked"


def build_fund_expansion_ladder(
    *,
    source_hygiene: dict,
    realtime_preflight: dict,
    futures_requirements: dict,
    futures_broker_parity: dict,
    live_readiness: dict,
    prediction_paper_gate: dict,
    prediction_capture: dict,
    runtime_architecture: dict,
    next_actions: dict,
) -> dict:
    """Build the research-to-capital ladder without approving any execution."""
    source_clean = source_hygiene.get("sourceHygieneCleared") is True or source_hygiene.get("sourceClean") is True
    futures_data_ready = (
        realtime_preflight.get("readyForExecutionData") is True
        and futures_requirements.get("readyForDemoExpansion") is True
    )
    futures_broker_ready = (
        futures_broker_parity.get("readyForDemoExpansion") is True
        or futures_broker_parity.get("brokerParityCleared") is True
    )
    futures_demo_ready = (
        source_clean
        and futures_data_ready
        and futures_broker_ready
        and live_readiness.get("readyForDemoExpansion") is True
    )
    prediction_paper_ready = (
        prediction_paper_gate.get("readyForPaper") is True
        and prediction_capture.get("readyForPaper") is True
        and prediction_capture.get("paperPromotionEvidencePassed") is True
    )
    runtime_safe = (
        runtime_architecture.get("researchOnly") is True
        and runtime_architecture.get("readyForExecution") is False
        and runtime_architecture.get("warnings") in ([], None)
    )
    queue_safe = (
        next_actions.get("researchOnly") is True
        and next_actions.get("writesOrders") is False
        and next_actions.get("touchesBroker") is False
    )
    futures_month_ready = futures_demo_ready and live_readiness.get("oneMonthProfitableDemo") is True
    prediction_trader_ready = prediction_paper_ready and prediction_paper_gate.get("readyForExecution") is True
    copy_trade_ready = futures_month_ready and prediction_trader_ready and live_readiness.get("copyTradingApproved") is True
    brokerage_ready = copy_trade_ready and live_readiness.get("brokerageExpansionApproved") is True
    options_ready = brokerage_ready and live_readiness.get("optionsExpansionApproved") is True

    ladder = [
        {
            "id": "l0-research-only-control-plane",
            "label": "Research-only control plane",
            "status": pass_fail(runtime_safe and queue_safe),
            "promotionRule": "Research agents may propose one-variable tests; deterministic gates own promotion and execution.",
            "evidence": {
                "runtimeSafe": runtime_safe,
                "queueSafe": queue_safe,
            },
            "noTradeIsValid": True,
        },
        {
            "id": "l1-futures-topstep-demo",
            "label": "Futures prop-firm demo",
            "status": pass_fail(futures_demo_ready),
            "promotionRule": "Only after source hygiene, current/broker parity, execution-grade data, live-readiness, and daily approval all pass.",
            "evidence": {
                "sourceClean": source_clean,
                "futuresDataReady": futures_data_ready,
                "brokerParityReady": futures_broker_ready,
                "readyForDemoExpansion": live_readiness.get("readyForDemoExpansion"),
            },
            "blockedBy": [
                item
                for item, ok in {
                    "source-hygiene": source_clean,
                    "execution-grade-data": futures_data_ready,
                    "broker-current-parity": futures_broker_ready,
                    "live-readiness-demo-expansion": live_readiness.get("readyForDemoExpansion") is True,
                }.items()
                if not ok
            ],
        },
        {
            "id": "l2-prediction-paper",
            "label": "Prediction-market paper/watch",
            "status": pass_fail(prediction_paper_ready),
            "promotionRule": "Only after no-lookahead event windows, clean mapping, fillability, resolved labels, and post-spread edge pass.",
            "evidence": {
                "paperGateDecision": prediction_paper_gate.get("decision"),
                "paperGateBlockedIds": prediction_paper_gate.get("blockedIds", []),
                "captureReadyForPaper": prediction_capture.get("readyForPaper"),
                "paperPromotionEvidencePassed": prediction_capture.get("paperPromotionEvidencePassed"),
            },
        },
        {
            "id": "l3-prediction-trader",
            "label": "Prediction-market trader",
            "status": pass_fail(prediction_trader_ready),
            "promotionRule": "Only after paper evidence clears and execution/funding firewalls are intentionally approved.",
            "evidence": {
                "predictionPaperReady": prediction_paper_ready,
                "paperGateReadyForExecution": prediction_paper_gate.get("readyForExecution"),
            },
        },
        {
            "id": "l4-copy-trading-and-brokerage",
            "label": "Copy trading then brokerage",
            "status": pass_fail(copy_trade_ready and brokerage_ready),
            "promotionRule": "Only after a profitable month, clean fills, payout discipline, source hygiene, and copy/broker approvals.",
            "evidence": {
                "futuresMonthReady": futures_month_ready,
                "predictionTraderReady": prediction_trader_ready,
                "copyTradingApproved": live_readiness.get("copyTradingApproved"),
                "brokerageExpansionApproved": live_readiness.get("brokerageExpansionApproved"),
            },
        },
        {
            "id": "l5-options-expansion",
            "label": "Options expansion",
            "status": pass_fail(options_ready),
            "promotionRule": "Options remain a risk/regime overlay until futures, prediction, copy, and brokerage operations are proven.",
            "evidence": {
                "brokerageReady": brokerage_ready,
                "optionsExpansionApproved": live_readiness.get("optionsExpansionApproved"),
            },
        },
    ]
    return {
        "decision": "fund-promotion-contract-research-only-execution-locked",
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "movesFunds": False,
        "readyForExecution": False,
        "readyForDemoExpansion": futures_demo_ready,
        "readyForPaper": prediction_paper_ready,
        "currentStage": "research-only-control-plane",
        "nextStage": "futures-topstep-demo" if futures_demo_ready else "clear-futures-demo-gates",
        "portfolioIntent": {
            "mix": ["high-win-rate edges", "high-return convex/repricing edges"],
            "compoundRule": "Compound only after gates pass and payouts are realized; no-trade days preserve capital and are valid outcomes.",
            "primaryLanes": ["futures", "prediction-markets"],
            "laterLanes": ["copy-trading", "brokerage", "options"],
        },
        "ladder": ladder,
    }


def cron_summary() -> dict:
    data = read_json(HERMES_CRON)
    jobs = data.get("jobs", data) if isinstance(data, dict) else data
    if isinstance(jobs, dict):
        jobs = list(jobs.values())
    if not isinstance(jobs, list):
        jobs = []
    enabled = [j for j in jobs if isinstance(j, dict) and j.get("enabled") is True]
    execution_terms = ("pickmytrade", "lucidflex", "60m_exec_bridge", "agentic_fund", "execute", "bridge")
    risky = []
    for job in enabled:
        hay = f"{job.get('name', '')} {job.get('prompt', '')}".lower()
        if any(term in hay for term in execution_terms):
            risky.append({
                "id": job.get("id"),
                "name": job.get("name"),
                "schedule": job.get("schedule"),
                "prompt": str(job.get("prompt", "")),
                "promptPreview": str(job.get("prompt", ""))[:260],
            })
    return {"path": str(HERMES_CRON), "enabledCount": len(enabled), "enabledExecutionAdjacent": risky}


def cron_validator_cleared(data: dict) -> bool:
    return (
        (data.get("cleared") is True or data.get("cronTrustCleared") is True)
        and int(data.get("blockingIssueCount") or 0) == 0
        and int(data.get("activeDirtyExecutionLiveScriptReferenceCount") or 0) == 0
        and int(data.get("quarantinedScriptReferenceCount") or 0) == 0
        and int(data.get("activeTradingAgentBackedCount") or 0) == 0
        and int(data.get("noAgentMetadataMismatchCount") or 0) == 0
    )


def cron_prompts_shadow_aligned(cron: dict, validator: dict | None = None) -> tuple[bool, str]:
    validator = validator or {}
    if cron_validator_cleared(validator):
        evidence = (
            f"validatorCleared=True blockingIssueCount={validator.get('blockingIssueCount')} "
            f"activeDirtyExecutionLiveScriptReferenceCount={validator.get('activeDirtyExecutionLiveScriptReferenceCount')} "
            f"quarantinedScriptReferenceCount={validator.get('quarantinedScriptReferenceCount')} "
            f"enabledExecutionAdjacent={len(cron.get('enabledExecutionAdjacent', []))}"
        )
        return True, evidence
    risky = cron.get("enabledExecutionAdjacent", [])
    hay = "\n".join(str(job.get("prompt", job.get("promptPreview", ""))).lower() for job in risky)
    required = [
        "shadow",
        "guarded topstep demo bridge",
        "bill_enable_lucidflex_execution=true",
        "bill_enable_agentic_fund_execution=true",
    ]
    missing = [term for term in required if term not in hay]
    old_phrases = [
        "submits trades via pickmytrade",
        "submits to pickmytrade",
        "both $50k lucidflex",
    ]
    stale = [phrase for phrase in old_phrases if phrase in hay]
    ok = not missing and not stale
    evidence = f"validatorCleared=False missing={missing} stale={stale} enabledExecutionAdjacent={len(risky)}"
    return ok, evidence


def n8n_summary() -> dict:
    out = {"db": str(N8N_DB), "workflows": [], "errors": []}
    if not N8N_DB.exists():
        out["errors"].append("n8n database missing")
        return out
    try:
        con = sqlite3.connect(str(N8N_DB))
        con.row_factory = sqlite3.Row
        rows = con.execute("select id, name, active from workflow_entity order by name").fetchall()
        out["workflows"] = [dict(row) for row in rows]
        con.close()
    except Exception as exc:
        out["errors"].append(str(exc))
    return out


def build_audit() -> dict:
    checks: list[Check] = []

    file_exists(checks, "Canonical Phase 2 fund OS document exists", ROOT / "docs" / "BILL_FUND_OS_PHASE2_2026_05_26.md", "Create/update the Phase 2 operating-system doc.")
    file_exists(checks, "Research handoff README exists for weaker agents", DOCS_RESEARCH / "README.md", "Create docs/research/README.md with start-here rules.")
    file_exists(checks, "Corpus inventory exists", DOCS_RESEARCH / "bill-corpus-audit-2026-05-26.md", "Run scripts/bill_corpus_audit.py.")
    file_exists(checks, "Corpus JSON exists for machine use", STATE_DIR / "bill-corpus-audit.latest.json", "Run scripts/bill_corpus_audit.py.")
    file_exists(checks, "Obsidian pointer exists", OBSIDIAN_HERMES / "bill-fund-os-phase2-2026-05-26.md", "Write a vault pointer to the canonical repo doc.")
    clearance_handoff = read_json(BILL_CLEARANCE_HANDOFF)
    add(
        checks,
        "Current clearance handoff exists and keeps execution locked",
        BILL_CLEARANCE_HANDOFF.exists() and clearance_handoff_safe(clearance_handoff),
        (
            f"{BILL_CLEARANCE_HANDOFF} decision={clearance_handoff.get('decision')} "
            f"readyForExecution={clearance_handoff.get('readyForExecution')}"
        ),
        "Run npm run bill:clearance-handoff after refreshing gates.",
    )
    clearance_evidence = read_json(BILL_CLEARANCE_EVIDENCE)
    add(
        checks,
        "Current clearance evidence exists and is non-executing",
        BILL_CLEARANCE_EVIDENCE.exists() and clearance_evidence_safe(clearance_evidence),
        (
            f"{BILL_CLEARANCE_EVIDENCE} status={clearance_evidence.get('status')} "
            f"allCommandsPassed={clearance_evidence.get('allCommandsPassed')} "
            f"failed={clearance_evidence.get('failedCommandIds')}"
        ),
        "Run npm run bill:clearance-evidence after refreshing gates.",
    )

    corpus = read_json(STATE_DIR / "bill-corpus-audit.latest.json")
    roots = corpus.get("roots", [])
    present_roots = {r.get("label") for r in roots if r.get("present")}
    needed_roots = {
        "repo_docs", "repo_scripts", "repo_src", "repo_state", "repo_research",
        "obsidian_hermes", "obsidian_shared", "obsidian_trading",
        "hermes_scripts", "hermes_cron", "downloads",
        "seagate_features", "seagate_alpha_manifests", "seagate_local_archives",
        "seagate_rumbling", "seagate_rumbling_cold_archives", "seagate_rumbling_cold_strategy",
    }
    add(
        checks,
        "Corpus covers repo, Hermes, Obsidian, Downloads, and Seagate roots",
        needed_roots.issubset(present_roots),
        f"present={sorted(present_roots)}",
        f"Missing roots: {sorted(needed_roots - present_roots)}",
    )

    audit_shadow_signal(checks, "dom-proxy-signal.latest.json", "proxy_shadow_only")
    audit_shadow_signal(checks, "kalman-pairs-signal.latest.json", "research_shadow_only")
    audit_shadow_signal(checks, "whale-flow-signal.latest.json", {"no_live_data_shadow_only", "weekly_cot_shadow_only"})

    rolling = read_json(STATE_DIR / "rolling-window-params.latest.json")
    add(
        checks,
        "Rolling optimizer is shadow-only and finite",
        rolling.get("promoted_for_execution") is False and all(
            isinstance(w.get("score"), (int, float)) for w in rolling.get("windows", {}).values()
        ),
        f"{STATE_DIR / 'rolling-window-params.latest.json'} promoted={rolling.get('promoted_for_execution')}",
        "Re-run rolling_window_optimizer.py after NaN guard patch.",
    )

    sixty_ts = latest_csv_ts(ROOT / "data" / "free" / "ALL-6MARKETS-60m-60d-normalized.csv")
    fifteen_ts = latest_csv_ts(ROOT / "data" / "free" / "ALL-6MARKETS-15m-60d-normalized.csv")
    sixty_ok, sixty_evidence = research_data_fresh_enough(sixty_ts, 180, 60)
    fifteen_ok, fifteen_evidence = research_data_fresh_enough(fifteen_ts, 180, 15)
    add(checks, "60m data is fresh enough for research evaluation", sixty_ok, sixty_evidence, "Refresh 60m research data before any research run.")
    add(checks, "15m data is fresh enough for research evaluation", fifteen_ok, fifteen_evidence, "Refresh 15m research data before ORB/DOM-proxy/15m research matters.")

    realtime_preflight = read_json(STATE_DIR / "realtime-data-preflight.latest.json")
    preflight_path = STATE_DIR / "realtime-data-preflight.latest.json"
    preflight_present = preflight_path.exists()
    preflight_safe = (
        preflight_present
        and realtime_preflight.get("writesOrders") is False
        and realtime_preflight.get("touchesBroker") is False
        and realtime_preflight.get("researchOnly") is True
    )
    add(
        checks,
        "Realtime data preflight exists and is read-only",
        preflight_safe,
        (
            f"{preflight_path} readyForExecutionData={realtime_preflight.get('readyForExecutionData')} "
            f"decision={realtime_preflight.get('decision')} blockers={compact_list(realtime_preflight.get('blockers'))}"
        ),
        "Run npm run bill:realtime-data-preflight and keep it broker/order read-only.",
    )
    if preflight_present and realtime_preflight.get("readyForExecutionData") is not True:
        warn(
            checks,
            "Realtime execution data remains blocked",
            (
                f"decision={realtime_preflight.get('decision')} "
                f"blockers={compact_list(realtime_preflight.get('blockers'))}"
            ),
            "Do not route futures demo/live orders until realtime preflight is green from execution-grade data.",
        )

    databento_smoke = read_json(DATABENTO_SMOKE)
    add(
        checks,
        "Databento realtime smoke artifact exists and is research-only",
        DATABENTO_SMOKE.exists() and databento_smoke_safe(databento_smoke),
        (
            f"{DATABENTO_SMOKE} status={databento_smoke.get('status')} "
            f"readyForExecutionDataProof={databento_smoke.get('readyForExecutionDataProof')} "
            f"writesRealtimeQuoteState={databento_smoke.get('writesRealtimeQuoteState')} "
            f"session={(databento_smoke.get('session') or {}).get('reason')}"
        ),
        "Run npm run bill:databento-realtime-smoke and keep it separate from realtime-quote.latest.json.",
    )
    if DATABENTO_SMOKE.exists() and databento_smoke.get("readyForExecutionDataProof") is not True:
        warn(
            checks,
            "Databento live quote proof remains unavailable",
            (
                f"status={databento_smoke.get('status')} "
                f"reason={(databento_smoke.get('quoteSummary') or {}).get('reason')}"
            ),
            "Retry the smoke during an active CME Globex session before attempting a canonical Databento realtime bridge write.",
        )

    realtime_bridge = read_text(ROOT / "scripts" / "realtime_data_bridge.py")
    env_example = read_text(ROOT / ".env.example") + "\n" + read_text(ROOT / "ops" / "mac-mini" / "env" / "bill.env.example")
    add(
        checks,
        "Databento realtime bridge is explicit and default-off",
        (
            "BILL_DATABENTO_REALTIME_ENABLED" in realtime_bridge
            and "db.Live" in realtime_bridge
            and "execution_grade" in realtime_bridge
            and "BILL_DATABENTO_REALTIME_ENABLED=false" in env_example
        ),
        str(ROOT / "scripts" / "realtime_data_bridge.py"),
        "Keep Databento realtime disabled by default and require explicit env plus green preflight before execution use.",
    )

    funding_scripts = [
        (ROOT / "scripts" / "deposit-clob.ts", ROOT / ".retired" / "deposit-clob.ts", False),
        (ROOT / "scripts" / "deposit-simple.ts", ROOT / ".retired" / "deposit-simple.ts", False),
        (ROOT / "scripts" / "fund-and-trade.ts", ROOT / ".retired" / "fund-and-trade.ts", False),
        (ROOT / "scripts" / "wire-up.ts", None, True),
        (ROOT / "scripts" / "swap-and-fund.ts", None, True),
    ]
    funding_guarded = all(
        funding_helper_guarded(active_path, retired_path, active_required=active_required)
        for active_path, retired_path, active_required in funding_scripts
    )
    add(
        checks,
        "Prediction funding helpers fail closed unless explicitly approved",
        funding_guarded and (ROOT / "scripts" / "verify_prediction_funding_firewall.py").exists(),
        f"scripts={len(funding_scripts)} verifier={ROOT / 'scripts' / 'verify_prediction_funding_firewall.py'}",
        "Patch all funding helpers and run npm run bill:verify-prediction-funding-firewall.",
    )

    futures_triage = read_json(STATE_DIR / "futures-evidence-triage.latest.json")
    futures_triage_present = (STATE_DIR / "futures-evidence-triage.latest.json").exists()
    add(
        checks,
        "Futures evidence triage artifact exists",
        futures_triage_present,
        f"{STATE_DIR / 'futures-evidence-triage.latest.json'} decision={futures_triage.get('decision')}",
        "Run npm run bill:futures-evidence-triage.",
    )
    if futures_triage_present and futures_triage.get("readyForDemoExpansion") is not True:
        warn(
            checks,
            "Futures strategy lane remains research-only",
            (
                f"decision={futures_triage.get('decision')} "
                f"liveBlockers={compact_list((futures_triage.get('liveReadiness') or {}).get('blockers'))}"
            ),
            "Do not promote full-sample survivors; require OOS, walk-forward, stress, cost/slippage, and live-readiness gates.",
        )

    prediction_triage = read_json(STATE_DIR / "prediction-evidence-triage.latest.json")
    prediction_triage_present = (STATE_DIR / "prediction-evidence-triage.latest.json").exists()
    add(
        checks,
        "Prediction-market evidence triage artifact exists",
        prediction_triage_present,
        f"{STATE_DIR / 'prediction-evidence-triage.latest.json'} decision={prediction_triage.get('decision')}",
        "Run npm run bill:prediction-evidence-triage.",
    )
    if prediction_triage_present and prediction_triage.get("readyForPaper") is not True:
        clob_gate = prediction_triage.get("clobEdgeGate") or {}
        watchlist = prediction_triage.get("watchlist") or {}
        warn(
            checks,
            "Prediction-market lane remains research-only",
            (
                f"decision={prediction_triage.get('decision')} clobStatus={clob_gate.get('status')} "
                f"watchCount={watchlist.get('watchCount')} readyForPaper={prediction_triage.get('readyForPaper')}"
            ),
            "Keep prediction execution in paper/skipped mode until market-specific resolved-history and calibration gates pass.",
        )

    kalshi_fillability = read_json(STATE_DIR / "kalshi-fillability-snapshot.latest.json")
    kalshi_fillability_safe = (
        kalshi_fillability.get("researchOnly") is True
        and kalshi_fillability.get("writesOrders") is False
        and kalshi_fillability.get("touchesBroker") is False
        and kalshi_fillability.get("promoted_for_execution") is False
        and kalshi_fillability.get("tradable_signal") is False
    )
    add(
        checks,
        "Kalshi fillability snapshot is present and research-only",
        kalshi_fillability_safe,
        (
            f"{STATE_DIR / 'kalshi-fillability-snapshot.latest.json'} "
            f"marketsInspected={kalshi_fillability.get('marketsInspected')} "
            f"executablePublicQuotes={kalshi_fillability.get('executablePublicQuotes')} "
            f"bucketCounts={kalshi_fillability.get('bucketCounts')}"
        ),
        "Run npm run bill:kalshi-fillability-snapshot and keep it public-data/read-only.",
    )

    futures_no_edge = read_json(FUTURES_NO_EDGE)
    prediction_no_edge = read_json(PREDICTION_NO_EDGE)
    add(
        checks,
        "Futures no-edge memory is present",
        FUTURES_NO_EDGE.exists() and futures_no_edge.get("promotableCount", 0) == 0,
        ledger_evidence(FUTURES_NO_EDGE, ("count", "noEdgeCount", "needsNewFeatureCount", "promotableCount")),
        "Run npm run bill:futures-no-edge-ledger before retesting old futures ideas.",
    )
    add(
        checks,
        "Prediction no-edge memory is present",
        PREDICTION_NO_EDGE.exists() and prediction_no_edge.get("promotableCount", 0) == 0,
        ledger_evidence(PREDICTION_NO_EDGE, ("count", "noEdgeCount", "needsMoreDataCount", "promotableCount")),
        "Run npm run bill:prediction-no-edge-ledger before retesting old prediction-market ideas.",
    )

    closed_loop = read_json(STATE_DIR / "bill-research-closed-loop-contract.latest.json")
    execution_boundary = closed_loop.get("executionBoundary") or {}
    add(
        checks,
        "Research loop separates LLM research from deterministic execution",
        (
            closed_loop.get("readyForExecution") is False
            and closed_loop.get("researchOnly") is True
            and closed_loop.get("writesOrders") is False
            and execution_boundary.get("deterministicCodeRoutes") is True
            and execution_boundary.get("llmMayRoute") is False
        ),
        (
            f"{STATE_DIR / 'bill-research-closed-loop-contract.latest.json'} "
            f"readyForExecution={closed_loop.get('readyForExecution')} "
            f"researchOnly={closed_loop.get('researchOnly')} "
            f"deterministicCodeRoutes={execution_boundary.get('deterministicCodeRoutes')} "
            f"llmMayRoute={execution_boundary.get('llmMayRoute')}"
        ),
        "Run npm run bill:research-closed-loop-contract and keep LLMs out of live routing.",
    )

    cftc_positioning = read_json(STATE_DIR / "cftc-tff-positioning.latest.json")
    cftc_safe = (
        cftc_positioning.get("researchOnly") is True
        and cftc_positioning.get("writesOrders") is False
        and cftc_positioning.get("touchesBroker") is False
        and cftc_positioning.get("promoted_for_execution") is False
        and cftc_positioning.get("tradable_signal") is False
    )
    add(
        checks,
        "CFTC TFF positioning intake is fresh and research-only",
        cftc_safe and cftc_positioning.get("freshForWeeklyResearch") is True,
        (
            f"{STATE_DIR / 'cftc-tff-positioning.latest.json'} "
            f"freshForWeeklyResearch={cftc_positioning.get('freshForWeeklyResearch')} "
            f"latestReportDate={cftc_positioning.get('latestReportDate')} "
            f"markets={sorted((cftc_positioning.get('markets') or {}).keys())} "
            f"tradable={cftc_positioning.get('tradable_signal')}"
        ),
        "Run npm run bill:cftc-tff-positioning and keep COT as a weekly research/regime feature only.",
    )

    worktree = read_json(STATE_DIR / "worktree-consolidation.latest.json")
    canonical = {}
    for item in worktree.get("worktrees", []) if isinstance(worktree.get("worktrees"), list) else []:
        if item.get("path") == str(ROOT):
            canonical = item
            break
    add(
        checks,
        "Worktree consolidation artifact exists",
        (STATE_DIR / "worktree-consolidation.latest.json").exists(),
        f"posture={worktree.get('posture')} sourceCleanBlockers={compact_list(worktree.get('sourceCleanBlockers'))}",
        "Run npm run bill:worktree-consolidation.",
    )
    if worktree.get("sourceCleanBlockers"):
        warn(
            checks,
            "Source tree remains too dirty for live-money clearance",
            (
                f"canonicalDirtyFiles={canonical.get('dirtyFiles')} "
                f"categories={canonical.get('categories')} "
                f"blockers={compact_list(worktree.get('sourceCleanBlockers'))}"
            ),
            "Finish, verify, and intentionally commit/stage bounded source changes before any live-money clearance.",
        )

    hermes_storage = read_json(HERMES_STORAGE_AUDIT)
    add(
        checks,
        "Hermes runtime storage audit exists and is manifest-only",
        HERMES_STORAGE_AUDIT.exists() and hermes_storage_audit_safe(hermes_storage),
        (
            f"{HERMES_STORAGE_AUDIT} totalSize={hermes_storage.get('totalSize')} "
            f"archiveCandidateSize={hermes_storage.get('archiveCandidateSize')} "
            f"movesFiles={hermes_storage.get('movesFiles')} deletesFiles={hermes_storage.get('deletesFiles')}"
        ),
        "Run npm run bill:hermes-storage-audit before any Hermes runtime cleanup.",
    )
    if HERMES_STORAGE_AUDIT.exists() and hermes_storage.get("archiveCandidateBytes", 0) > 0:
        warn(
            checks,
            "Hermes runtime has archive candidates but cleanup is not executed",
            (
                f"archiveCandidateSize={hermes_storage.get('archiveCandidateSize')} "
                f"topCandidates={compact_list(hermes_storage.get('topCandidates'))}"
            ),
            "Only archive/delete after operator approval, inactive-profile review, and verified Seagate copy/checksum.",
        )

    bridge = read_text(ROOT / "scripts" / "master_bridge.py")
    add(
        checks,
        "Master bridge reads canonical state and ignores unpromoted overlays",
        "CANONICAL_STATE_DIR" in bridge and "promoted_execution_overlay" in bridge and "Topstep demo route capped" in bridge,
        str(ROOT / "scripts" / "master_bridge.py"),
        "Patch master_bridge.py to use canonical state and explicit promotion flags.",
    )

    legacy_bridge = (HOME / ".hermes" / "scripts" / "master_bridge.py").read_text(errors="ignore")
    add(
        checks,
        "Hermes master bridge delegates to canonical repo bridge",
        "CANONICAL_BRIDGE" in legacy_bridge and "os.execv" in legacy_bridge,
        str(HOME / ".hermes" / "scripts" / "master_bridge.py"),
        "Patch ~/.hermes/scripts/master_bridge.py to delegate to ~/hedge/scripts/master_bridge.py.",
    )

    lucid_bridge = (ROOT / "scripts" / "60m_exec_bridge.py").read_text(errors="ignore")
    hermes_lucid_bridge = (HOME / ".hermes" / "scripts" / "60m_exec_bridge.py").read_text(errors="ignore")
    add(
        checks,
        "Legacy LucidFlex bridge defaults to shadow-only",
        "BILL_ENABLE_LUCIDFLEX_EXECUTION" in lucid_bridge and "BILL_ENABLE_LUCIDFLEX_EXECUTION" in hermes_lucid_bridge,
        "repo and Hermes 60m_exec_bridge.py",
        "Patch both 60m_exec_bridge.py copies to require BILL_ENABLE_LUCIDFLEX_EXECUTION=true.",
    )

    agentic = (ROOT / "scripts" / "agentic_fund.sh").read_text(errors="ignore")
    hermes_agentic = (HOME / ".hermes" / "scripts" / "agentic_fund.sh").read_text(errors="ignore")
    add(
        checks,
        "Agentic fund cycle defaults to shadow-only and canonical state",
        "BILL_ENABLE_AGENTIC_FUND_EXECUTION" in agentic and "/Users/brain/hedge/.rumbling-hedge/state" in agentic and "BILL_ENABLE_AGENTIC_FUND_EXECUTION" in hermes_agentic,
        "repo and Hermes agentic_fund.sh",
        "Patch both agentic_fund.sh copies to use canonical state and skip bridge by default.",
    )

    cron = cron_summary()
    cron_validator = read_json(STATE_DIR / "cron-state-validator.latest.json")
    cron_ok, cron_evidence = cron_prompts_shadow_aligned(cron, cron_validator)
    add(
        checks,
        "Hermes cron state is validator-cleared or prompts describe shadow/guarded execution posture",
        cron_ok,
        cron_evidence,
        "Run npm run bill:cron-state-validator or update ~/.hermes/cron/jobs.json prompts so agents do not inherit stale execution language.",
    )

    n8n = n8n_summary()
    active_bill_n8n = [w for w in n8n.get("workflows", []) if "bill" in str(w.get("name", "")).lower() and int(w.get("active", 0) or 0) == 1]
    add(
        checks,
        "n8n has no hidden active Bill execution workflow",
        len(active_bill_n8n) == 0,
        f"workflows={n8n.get('workflows')}",
        "Review n8n database workflows before relying on n8n for trading automation.",
    )

    readiness = read_json(STATE_DIR / "live-readiness-gate.latest.json")
    ready = readiness.get("readyForLive") is True and readiness.get("readyForDemoExpansion") is True
    readiness_evidence = (
        f"{STATE_DIR / 'live-readiness-gate.latest.json'} "
        f"readyForLive={readiness.get('readyForLive')} "
        f"readyForDemoExpansion={readiness.get('readyForDemoExpansion')} "
        f"blockers={readiness.get('blockers')}"
    )
    if ready:
        add(checks, "Trading expansion gate evaluated", True, readiness_evidence)
        trading_status = "READY"
    elif isinstance(readiness.get("blockers"), list) and readiness.get("blockers"):
        warn(
            checks,
            "Trading expansion gate evaluated and remains red",
            readiness_evidence,
            "Do not increase size, accounts, or autonomy until live-readiness blockers clear.",
        )
        trading_status = "BLOCKED_BY_EVIDENCE"
    else:
        add(
            checks,
            "Trading expansion gate evaluated",
            False,
            readiness_evidence,
            "Run npm run bill:live-readiness-gate and inspect blockers.",
        )
        trading_status = "UNKNOWN"

    fund_promotion_contract = build_fund_expansion_ladder(
        source_hygiene=read_json(STATE_DIR / "bill-source-hygiene-plan.latest.json"),
        realtime_preflight=realtime_preflight,
        futures_requirements=read_json(STATE_DIR / "futures-data-requirements.latest.json"),
        futures_broker_parity=read_json(STATE_DIR / "futures-broker-parity-plan.latest.json"),
        live_readiness=readiness,
        prediction_paper_gate=read_json(STATE_DIR / "prediction-event-paper-promotion-gate.latest.json"),
        prediction_capture=read_json(STATE_DIR / "prediction-event-capture-cycle.latest.json"),
        runtime_architecture=read_json(STATE_DIR / "bill-runtime-architecture-audit.latest.json"),
        next_actions=read_json(STATE_DIR / "bill-next-research-actions.latest.json"),
    )
    add(
        checks,
        "Fund expansion ladder is explicit and execution-locked",
        (
            fund_promotion_contract.get("researchOnly") is True
            and fund_promotion_contract.get("writesOrders") is False
            and fund_promotion_contract.get("touchesBroker") is False
            and fund_promotion_contract.get("readyForExecution") is False
            and isinstance(fund_promotion_contract.get("ladder"), list)
        ),
        (
            f"decision={fund_promotion_contract.get('decision')} "
            f"readyForDemoExpansion={fund_promotion_contract.get('readyForDemoExpansion')} "
            f"readyForPaper={fund_promotion_contract.get('readyForPaper')} "
            f"stages={[item.get('id') for item in fund_promotion_contract.get('ladder', [])]}"
        ),
        "Patch the fund promotion contract before giving weaker agents expansion instructions.",
    )

    blocked = [asdict(c) for c in checks if c.status == "BLOCKED"]
    warnings = [asdict(c) for c in checks if c.status == "WARN"]
    overall_status = "HANDOFF_COMPLETE" if not blocked else "NOT_COMPLETE"
    if overall_status == "HANDOFF_COMPLETE" and trading_status == "BLOCKED_BY_EVIDENCE":
        overall_status = "HANDOFF_COMPLETE_TRADING_BLOCKED"
    return {
        "command": "bill-fund-os-completion-audit",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "objective": "Clean, separated, evidence-driven Bill/Hermes fund operating system and handoff for weaker agents.",
        "completionCriteria": [
            "Relevant repo, Hermes, Obsidian, Downloads, and Seagate roots are inventoried.",
            "Canonical research and handoff docs exist.",
            "A current clearance handoff exists for weaker agents and keeps execution locked.",
            "Current governance/firewall evidence is recorded by a non-executing verifier.",
            "Proxy/research signals are shadow-only unless explicitly promoted.",
            "Execution paths default to guarded/canonical routes and cannot use stale legacy state by accident.",
            "n8n/Hermes scheduler state is inspected and documented.",
            "Fresh data checks and contrary OOS evidence are recorded.",
            "Execution-grade realtime data is explicitly preflighted before demo/live use.",
            "Databento live quote smoke is recorded separately from canonical realtime quote state.",
            "Prediction-market funding helpers are fail-closed unless explicitly approved.",
            "Prediction-market fillability snapshots are public-data, read-only, and non-tradable.",
            "Futures and prediction no-edge ledgers prevent retesting stale ideas as if they were new alpha.",
            "Fresh CFTC TFF positioning is available only as a weekly research/regime feature.",
            "LLM research loops are separated from deterministic execution routes.",
            "Dirty source/worktree state is visible before live-money clearance.",
            "Hermes runtime storage pressure is manifest-only audited before cleanup.",
            "The futures/prediction/copy-trading/brokerage/options expansion ladder is explicit and execution-locked.",
            "Trading expansion remains blocked when gates fail.",
        ],
        "overallStatus": overall_status,
        "tradingReadinessStatus": trading_status,
        "checks": [asdict(c) for c in checks],
        "blocked": blocked,
        "warnings": warnings,
        "cron": cron,
        "cronValidator": cron_validator,
        "n8n": n8n,
        "fundPromotionContract": fund_promotion_contract,
    }


def write_markdown(audit: dict) -> Path:
    path = DOCS_RESEARCH / "bill-fund-os-completion-audit-2026-05-26.md"
    DOCS_RESEARCH.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Bill Fund OS Completion Audit — 2026-05-26",
        "",
        f"Overall status: `{audit['overallStatus']}`",
        f"Trading readiness status: `{audit['tradingReadinessStatus']}`",
        "",
        "This maps the founder request to concrete artifacts and gates. Handoff completion does not authorize trading; trading stays blocked whenever live-readiness gates are red.",
        "",
        "## Completion Criteria",
        "",
    ]
    for criterion in audit["completionCriteria"]:
        lines.append(f"- {criterion}")
    lines.extend([
        "",
        "## Prompt-To-Artifact Checklist",
        "",
        "| Requirement | Status | Evidence | Action |",
        "|---|---:|---|---|",
    ])
    for check in audit["checks"]:
        lines.append(f"| {check['requirement']} | `{check['status']}` | `{check['evidence']}` | {check['action']} |")
    lines.extend([
        "",
        "## Hermes Cron Risk",
        "",
        f"- Jobs file: `{audit['cron']['path']}`",
        f"- Enabled jobs: `{audit['cron']['enabledCount']}`",
        f"- Enabled execution-adjacent jobs: `{len(audit['cron']['enabledExecutionAdjacent'])}`",
        "",
    ])
    for job in audit["cron"]["enabledExecutionAdjacent"]:
        lines.append(f"- `{job.get('name')}` (`{job.get('id')}`): {job.get('promptPreview')}")
    contract = audit.get("fundPromotionContract") if isinstance(audit.get("fundPromotionContract"), dict) else {}
    lines.extend([
        "",
        "## Fund Promotion Contract",
        "",
        f"- Decision: `{contract.get('decision', 'missing')}`",
        f"- Current stage: `{contract.get('currentStage', 'missing')}`",
        f"- Next stage: `{contract.get('nextStage', 'missing')}`",
        f"- Ready for demo expansion: `{contract.get('readyForDemoExpansion', 'missing')}`",
        f"- Ready for prediction paper: `{contract.get('readyForPaper', 'missing')}`",
        "",
    ])
    for item in contract.get("ladder", []) if isinstance(contract.get("ladder"), list) else []:
        lines.append(
            f"- `{item.get('id')}` — `{item.get('status')}`: {item.get('promotionRule')}"
        )
    lines.extend([
        "",
        "## n8n State",
        "",
        f"- DB: `{audit['n8n']['db']}`",
        f"- Workflows: `{json.dumps(audit['n8n'].get('workflows', []))}`",
        "",
        "## Missing/Blocked",
        "",
    ])
    if audit["blocked"]:
        for item in audit["blocked"]:
            lines.append(f"- `{item['requirement']}` — {item['action']}")
    else:
        lines.append("- None.")
    lines.extend([
        "",
        "## Warnings",
        "",
    ])
    if audit.get("warnings"):
        for item in audit["warnings"]:
            lines.append(f"- `{item['requirement']}` — {item['action']}")
    else:
        lines.append("- None.")
    path.write_text("\n".join(lines) + "\n")
    return path


def main() -> int:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    audit = build_audit()
    out_json = STATE_DIR / "bill-fund-os-completion-audit.latest.json"
    out_json.write_text(json.dumps(audit, indent=2) + "\n")
    out_md = write_markdown(audit)
    print(json.dumps({
        "overallStatus": audit["overallStatus"],
        "blockedCount": len(audit["blocked"]),
        "warningCount": len(audit["warnings"]),
        "tradingReadinessStatus": audit["tradingReadinessStatus"],
        "json": str(out_json),
        "markdown": str(out_md),
    }, indent=2))
    return 0 if not audit["blocked"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
