#!/usr/bin/env python3
"""Build Bill/Hermes premarket risk posture from existing control artifacts.

This is a deterministic control-plane artifact. It does not fetch live data,
touch brokers, route orders, size orders for execution, fund accounts, or ask
an LLM for permission. Its job is to turn daily plan, macro calendar, news
availability, source hygiene, Topstep safety, and strategy evidence into a
single fail-closed premarket read for humans and weaker agents.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import macro_context


STATE = ROOT / ".rumbling-hedge" / "state"
VAULT = Path.home() / "Documents" / "memorybrain"
HERMES = VAULT / "Agent-Hermes"
DEFAULT_OUTPUT = STATE / "premarket-risk-brief.latest.json"
LOCAL_TZ = ZoneInfo("Europe/London")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def local_now(now: datetime | None = None) -> datetime:
    return (now or datetime.now(timezone.utc)).astimezone(LOCAL_TZ)


def default_markdown_path(now: datetime | None = None) -> Path:
    stamp = local_now(now).date().isoformat()
    return HERMES / f"premarket-risk-brief-{stamp}.md"


def read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text())
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def read_text(path: Path) -> str:
    try:
        return path.read_text()
    except Exception:
        return ""


def bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on", "pass", "green", "approved"}
    return False


def daily_plan_path(now: datetime | None = None) -> Path:
    stamp = local_now(now).date().isoformat()
    return HERMES / "daily" / f"{stamp}-bill-trading-plan.md"


def parse_daily_plan(text: str) -> dict[str, Any]:
    route = "UNKNOWN"
    broker = "UNKNOWN"
    no_orders = "No new Bill/Hermes orders approved" in text or "No new orders approved" in text
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("BILL_ROUTE_APPROVAL:"):
            route = stripped.split(":", 1)[1].strip().upper()
        if stripped.startswith("BROKER_RECONCILIATION:"):
            broker = stripped.split(":", 1)[1].strip().upper()
    return {
        "present": bool(text.strip()),
        "routeApproval": route,
        "brokerReconciliation": broker,
        "dailyMentionsNoOrders": no_orders,
    }


def risk_item(kind: str, severity: str, reason: str, evidence: Any = None) -> dict[str, Any]:
    return {
        "kind": kind,
        "severity": severity,
        "reason": reason,
        "evidence": evidence,
    }


def macro_risk(now: datetime) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    today_event = macro_context.today_events(now)
    upcoming = macro_context.next_3_days_events(now)
    risks: list[dict[str, Any]] = []
    if today_event:
        lower = today_event.lower()
        if "fomc" in lower:
            risks.append(risk_item("red-folder-macro", "hard", f"{today_event} today; no algo trading into FOMC risk", today_event))
        elif any(term in lower for term in ("cpi", "nfp", "jobs", "ppi")):
            risks.append(risk_item("red-folder-macro", "reduce", f"{today_event} today; reduce size or no-trade near release", today_event))
        else:
            risks.append(risk_item("macro-calendar", "watch", f"{today_event} today; keep macro context visible", today_event))
    return risks, {
        "todayEvent": today_event,
        "nextThreeDays": upcoming,
        "tradingDate": macro_context.current_trading_date(now).isoformat(),
    }


def extract_strategy_watch(alpha_direction: dict[str, Any], futures_triage: dict[str, Any], sizing: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    next_test = alpha_direction.get("nextOneVariableTest") if isinstance(alpha_direction.get("nextOneVariableTest"), dict) else {}
    if next_test:
        rows.append({
            "id": next_test.get("id"),
            "lane": next_test.get("lane"),
            "oneVariable": next_test.get("oneVariable"),
            "status": "research-watch-only",
            "command": next_test.get("command"),
        })
    for item in futures_triage.get("nextTests") or []:
        if not isinstance(item, dict):
            continue
        rows.append({
            "id": item.get("id"),
            "lane": "futures",
            "oneVariable": item.get("oneVariable"),
            "status": "research-watch-only",
            "command": item.get("firstCommand") or item.get("command"),
        })
    best_profile = sizing.get("bestProfileId")
    if best_profile:
        rows.append({
            "id": f"50k-sizing-{best_profile}",
            "lane": "risk",
            "oneVariable": sizing.get("oneVariable", "position sizing only"),
            "status": "policy-watch-only",
            "command": "npm run --silent bill:futures-nq-sizing-overlay",
        })
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for row in rows:
        key = str(row.get("id") or row.get("command") or row)
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out[:8]


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    generated_at = now_iso()
    now = datetime.fromisoformat(generated_at)
    daily_path = Path(args.daily_plan) if args.daily_plan else daily_plan_path(now)
    daily = parse_daily_plan(read_text(daily_path))
    goal = read_json(Path(args.goal_audit))
    handoff = read_json(Path(args.clearance_handoff))
    source = read_json(Path(args.source_hygiene))
    source_intake = read_json(Path(args.source_intake))
    data_freshness = read_json(Path(args.data_freshness))
    signal_quality = read_json(Path(args.signal_quality))
    topstep_safety = read_json(Path(args.topstep_session_safety))
    finnhub = read_json(Path(args.finnhub_news))
    rss_news = read_json(Path(args.prediction_news_rss))
    alpha_direction = read_json(Path(args.alpha_direction))
    futures_triage = read_json(Path(args.futures_triage))
    sizing = read_json(Path(args.sizing_overlay))
    topstep_learning = read_json(Path(args.topstep_learning))

    risks: list[dict[str, Any]] = []
    macro_risks, macro = macro_risk(now)
    risks.extend(macro_risks)

    if daily.get("routeApproval") != "APPROVED":
        risks.append(risk_item("daily-plan", "hard", "daily plan does not approve Bill/Hermes routing", daily))
    if daily.get("brokerReconciliation") != "GREEN":
        risks.append(risk_item("broker-reconciliation", "hard", "broker reconciliation is not GREEN", daily))
    if daily.get("dailyMentionsNoOrders"):
        risks.append(risk_item("daily-plan-no-orders", "hard", "daily plan explicitly says no new orders are approved", None))

    if handoff.get("decision") and handoff.get("decision") != "CLEAR_FOR_EXECUTION":
        risks.append(risk_item("clearance-handoff", "hard", f"handoff decision is {handoff.get('decision')}", handoff.get("decision")))
    if int(goal.get("blockedCount") or 0) > 0:
        risks.append(risk_item("goal-audit", "hard", "goal completion audit still has blockers", goal.get("blockedIds", [])))
    source_goal_blocked = "source-hygiene-not-cleared" in (goal.get("blockedIds") or [])
    source_intake_clean = source_intake.get("sourceClean") is True and int(source_intake.get("dirtyStatusCount") or 0) == 0
    source_intake_backlog = int(source_intake.get("reviewBacklogCount") or 0)
    source_execution_dirty = int(source_intake.get("executionLiveDirtyCount") or 0)
    if source_goal_blocked or not source_intake_clean or source_intake_backlog > 0 or source_execution_dirty > 0:
        risks.append(risk_item("source-hygiene", "hard", "source hygiene/intake is not cleared", {
            "sourceGoalBlocked": source_goal_blocked,
            "sourceIntakeDecision": source_intake.get("decision"),
            "sourceClean": source_intake.get("sourceClean"),
            "dirtyStatusCount": source_intake.get("dirtyStatusCount"),
            "reviewBacklogCount": source_intake.get("reviewBacklogCount"),
            "executionLiveDirtyCount": source_intake.get("executionLiveDirtyCount"),
            "planBlockers": source.get("sourceCleanBlockers", []),
        }))
    elif source and source.get("sourceHygieneCleared") is False:
        risks.append(risk_item("source-hygiene-review-plan", "watch", "source plan remains review-only, but canonical intake is clean", {
            "sourceIntakeDecision": source_intake.get("decision"),
            "sourcePlanDecision": source.get("decision"),
            "nextReductionOrder": source.get("nextReductionOrder", [])[:4],
        }))
    if bool_value(topstep_safety.get("pauseBrokerTouchingProofs")) or bool_value(topstep_safety.get("topstepMultipleSessionsDetected")):
        risks.append(risk_item("topstep-session-safety", "hard", "Topstep multiple-session safety is active", topstep_safety.get("reason")))
    if data_freshness.get("action") == "block_all_trades" or data_freshness.get("verdict") == "STALE":
        risks.append(risk_item("data-freshness", "hard", "futures realtime/current data freshness gate blocks trades", data_freshness))

    signal_blockers = signal_quality.get("blockers") if isinstance(signal_quality.get("blockers"), list) else []
    signal_warnings = signal_quality.get("warnings") if isinstance(signal_quality.get("warnings"), list) else []
    if signal_blockers:
        risks.append(risk_item("signal-quality", "hard", "signal quality has blockers", signal_blockers[:8]))
    if signal_warnings:
        risks.append(risk_item("signal-quality-warning", "reduce", "signal quality has warnings", signal_warnings[:8]))

    if finnhub.get("status") == "BLOCKED_NO_DATA":
        risks.append(risk_item("news-source", "reduce", "Finnhub news/calendar source has no usable data", finnhub.get("fetchErrors")))
    if rss_news.get("status") == "PASS":
        risks.append(risk_item("prediction-news-rss", "watch", "prediction event RSS context is available", rss_news.get("newsCount")))

    hard = [item for item in risks if item["severity"] == "hard"]
    reduce = [item for item in risks if item["severity"] == "reduce"]
    decision = "NO_TRADE_ALGO" if hard else "REDUCED_SIZE_WATCH" if reduce else "NORMAL_WATCH"
    if_daily_clears = 0 if hard else 1 if reduce else 2

    payload = {
        "command": "premarket-risk-brief",
        "generatedAt": generated_at,
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "movesFunds": False,
        "readyForExecution": False,
        "readyForDemoExpansion": False,
        "decision": decision,
        "operatorRead": (
            "NO_TRADE_ALGO means deterministic Bill/Hermes algos must not route. "
            "Watch-only strategy notes are context and do not override the daily plan."
        ),
        "dailyPlan": {
            "path": str(daily_path),
            **daily,
        },
        "macro": macro,
        "riskCounts": {
            "hard": len(hard),
            "reduce": len(reduce),
            "watch": sum(1 for item in risks if item["severity"] == "watch"),
        },
        "risks": risks,
        "sizingPosture": {
            "accountTruth": "50K Topstep challenge/funded policy; 100K demo is calibration only",
            "instrument": "MNQ",
            "algoMaxContracts": 0,
            "manualWatchMaxContractsIfDailyPlanClears": if_daily_clears,
            "sizingSource": ".rumbling-hedge/state/futures-nq-sizing-overlay.latest.json",
            "rule": "0 contracts while any hard gate is active; 1 MNQ on reduced-risk days after manual daily-plan clearance; 2 MNQ max watch only when gates are clean.",
        },
        "strategyUseForDay": {
            "status": "watch-only" if hard else "manual-review-required",
            "candidates": extract_strategy_watch(alpha_direction, futures_triage, sizing),
            "doNotUse": [
                "full-sample-only Backtrader winners without OOS",
                "research-only shadow cron outputs",
                "prediction candidates before paper-promotion gate",
                "100K demo sizing copied into 50K challenge",
            ],
        },
        "context": {
            "goalBlockedIds": goal.get("blockedIds", []),
            "handoffDecision": handoff.get("decision"),
            "sourceIntakeDecision": source_intake.get("decision"),
            "sourceIntakeClean": source_intake.get("sourceClean"),
            "topstepDailyLearningDecision": topstep_learning.get("decision"),
            "finnhubStatus": finnhub.get("status"),
            "predictionNewsRssStatus": rss_news.get("status"),
            "signalQualityDecision": signal_quality.get("decision"),
        },
    }
    return payload


def render_markdown(payload: dict[str, Any]) -> str:
    risks = payload.get("risks") if isinstance(payload.get("risks"), list) else []
    candidates = (payload.get("strategyUseForDay") or {}).get("candidates") if isinstance(payload.get("strategyUseForDay"), dict) else []
    lines = [
        f"# Premarket Risk Brief - {str(payload.get('generatedAt', ''))[:10]}",
        "",
        "Parent hub: [[BILL-CONTROL-HUB]]",
        "",
        "Deterministic risk posture. This does not approve orders, demo expansion, paper trading, funding, broker access, or live trading.",
        "",
        "## Decision",
        "",
        f"- Decision: `{payload.get('decision')}`",
        f"- Ready for execution: `{payload.get('readyForExecution')}`",
        f"- Writes orders: `{payload.get('writesOrders')}`",
        f"- Touches broker: `{payload.get('touchesBroker')}`",
        f"- Operator read: {payload.get('operatorRead')}",
        "",
        "## Sizing Posture",
        "",
    ]
    sizing = payload.get("sizingPosture") if isinstance(payload.get("sizingPosture"), dict) else {}
    for key in ("accountTruth", "instrument", "algoMaxContracts", "manualWatchMaxContractsIfDailyPlanClears", "rule"):
        lines.append(f"- {key}: `{sizing.get(key)}`")
    lines.extend(["", "## Macro / Red Folder", ""])
    macro = payload.get("macro") if isinstance(payload.get("macro"), dict) else {}
    lines.append(f"- Trading date: `{macro.get('tradingDate')}`")
    lines.append(f"- Today event: `{macro.get('todayEvent')}`")
    lines.append(f"- Next events: `{macro.get('nextThreeDays')}`")
    lines.extend(["", "## Risks", ""])
    if risks:
        for item in risks:
            lines.append(f"- `{item.get('severity')}` `{item.get('kind')}` - {item.get('reason')}")
    else:
        lines.append("- none")
    lines.extend(["", "## Strategy Use For Day", ""])
    lines.append(f"- Status: `{(payload.get('strategyUseForDay') or {}).get('status')}`")
    if candidates:
        for item in candidates:
            if not isinstance(item, dict):
                continue
            lines.append(f"- `{item.get('id')}` lane `{item.get('lane')}` status `{item.get('status')}` oneVariable `{item.get('oneVariable')}`")
    else:
        lines.append("- no candidates")
    lines.extend(["", "## Hard Rules", ""])
    for item in (payload.get("strategyUseForDay") or {}).get("doNotUse", []):
        lines.append(f"- Do not use: {item}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build deterministic Bill/Hermes premarket risk posture.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=None)
    parser.add_argument("--daily-plan", default=None)
    parser.add_argument("--goal-audit", default=str(STATE / "bill-goal-completion-audit.latest.json"))
    parser.add_argument("--clearance-handoff", default=str(STATE / "bill-clearance-handoff.latest.json"))
    parser.add_argument("--source-hygiene", default=str(STATE / "bill-source-hygiene-plan.latest.json"))
    parser.add_argument("--source-intake", default=str(STATE / "bill-source-intake-manifest.latest.json"))
    parser.add_argument("--data-freshness", default=str(STATE / "data-freshness-gate.latest.json"))
    parser.add_argument("--signal-quality", default=str(STATE / "signal-quality-advisor.latest.json"))
    parser.add_argument("--topstep-session-safety", default=str(STATE / "topstep-session-safety.latest.json"))
    parser.add_argument("--finnhub-news", default=str(STATE / "finnhub-news.latest.json"))
    parser.add_argument("--prediction-news-rss", default=str(STATE / "prediction-event-news-rss.latest.json"))
    parser.add_argument("--alpha-direction", default=str(STATE / "alpha-research-direction-audit.latest.json"))
    parser.add_argument("--futures-triage", default=str(STATE / "futures-evidence-triage.latest.json"))
    parser.add_argument("--sizing-overlay", default=str(STATE / "futures-nq-sizing-overlay.latest.json"))
    parser.add_argument("--topstep-learning", default=str(STATE / "topstep-daily-learning.latest.json"))
    args = parser.parse_args()

    payload = build_payload(args)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    markdown = Path(args.markdown) if args.markdown else default_markdown_path()
    markdown.parent.mkdir(parents=True, exist_ok=True)
    markdown.write_text(render_markdown(payload), encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
