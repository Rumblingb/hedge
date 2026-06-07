#!/usr/bin/env python3
"""Build a read-only Topstep demo trade-learning artifact.

This script turns local Topstep submission/reconciliation artifacts and the
Obsidian operating/mistakes logs into daily learning evidence. It never logs in
to a broker, submits orders, changes flags, or treats manual/operator claims as
proof unless they are present in machine artifacts.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
VAULT = Path.home() / "Documents" / "memorybrain"
HERMES = VAULT / "Agent-Hermes"
TRADING = VAULT / "Trading" / "Topstep-100K"
OUT = STATE / "topstep-daily-learning.latest.json"
POINT_VALUES = {
    "MNQ": 2.0,
    "CON.F.US.MNQ": 2.0,
    "NQ": 20.0,
    "CON.F.US.ENQ": 20.0,
    "ES": 50.0,
    "MES": 5.0,
}
ACCOUNT_SIZING_POLICY = {
    "liveChallengeSizingAccount": "50K",
    "demoCalibrationAccount": "100K",
    "sizingSourceOfTruth": ".rumbling-hedge/state/prop-firm-payout-plan.latest.json",
    "challengeInstrument": "MNQ",
    "fundedInstrument": "MNQ",
    "demoCalibrationUse": "context-and-failure-learning-only",
    "hardRule": "Do not copy 100K demo contract sizing into the 50K challenge or funded account.",
}
OPERATOR_CONTEXT_RE = re.compile(r"operator[- ]reported", re.IGNORECASE)
OPERATOR_NET_UP_RE = re.compile(r"(?:up|profit)\s+\$?(?P<up>[0-9,]+(?:\.[0-9]+)?)", re.IGNORECASE)
OPERATOR_LOSS_RE = re.compile(
    r"(?:(?P<day_before>[A-Za-z]+)\s+)?(?:losing day|loss)(?:\s+(?P<day_after>[A-Za-z]+))?\s*-?\$?(?P<loss>[0-9,]+(?:\.[0-9]+)?)",
    re.IGNORECASE,
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def current_local_date() -> str:
    return datetime.now().astimezone().date().isoformat()


def default_operating_log() -> Path:
    return TRADING / f"{datetime.now(timezone.utc):%Y-%m}-operating-log.md"


def default_markdown_path() -> Path:
    return HERMES / f"topstep-daily-learning-{current_local_date()}.md"


def read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text())
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def read_text(path: Path) -> str:
    try:
        return path.read_text(errors="ignore")
    except Exception:
        return ""


def parse_trade_journal_jsonl(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def parse_money(value: str) -> float:
    return float(value.replace(",", ""))


def symbol_from_trade_id(trade_id: str | None) -> str:
    if not trade_id:
        return ""
    match = re.match(r"^(?:LONG|SHORT)-(?P<symbol>.+?)-\d{8}-\d{6}-\d{8}-\d{6}$", trade_id)
    return match.group("symbol") if match else ""


def target_trade_date(reconciliation: dict[str, Any], generated_at: str | None) -> str | None:
    for value in (reconciliation.get("ts"), generated_at):
        if isinstance(value, str) and re.match(r"^\d{4}-\d{2}-\d{2}", value):
            return value[:10]
    return None


def parse_operator_pnl_claims(text: str) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    for line in text.splitlines():
        if not OPERATOR_CONTEXT_RE.search(line):
            continue
        net_match = OPERATOR_NET_UP_RE.search(line)
        loss_match = OPERATOR_LOSS_RE.search(line)
        if not net_match or not loss_match:
            continue
        loss_day = (loss_match.group("day_before") or loss_match.group("day_after") or "").strip(" :-")
        claims.append({
            "reportedNetUpDollars": parse_money(net_match.group("up")),
            "reportedLosingDayDollars": -abs(parse_money(loss_match.group("loss"))),
            "reportedLosingDayLabel": loss_day or None,
            "source": "operator-note",
            "brokerProof": False,
            "promotionUse": "context-only-until-broker-reconciled",
        })
    return claims


def parse_topstep_submissions(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    header_re = re.compile(r"^### Topstep Demo — (?P<ts>[^\n]+)")
    signal_re = re.compile(
        r"Signal: `(?P<signal>[^`]+)` \| Side: (?P<side>\w+) \| Entry: \$(?P<entry>[0-9.]+) "
        r"\| SL: \$(?P<stop>[0-9.]+) \| TP: \$(?P<target>[0-9.]+)"
    )
    order_re = re.compile(r"Entry Order: (?P<order>\d+)")
    result_re = re.compile(r"Result: (?P<result>\S+)")
    strategy_re = re.compile(r"Strategy: (?P<strategy>\S+)")
    for line in text.splitlines():
        header = header_re.match(line)
        if header:
            if current:
                rows.append(current)
            current = {"ts": header.group("ts").strip()}
            continue
        if current is None:
            continue
        if match := signal_re.search(line):
            current.update({
                "signal": match.group("signal"),
                "side": match.group("side").lower(),
                "entry": float(match.group("entry")),
                "stop": float(match.group("stop")),
                "target": float(match.group("target")),
            })
        elif match := strategy_re.search(line):
            current["strategy"] = match.group("strategy")
        elif match := order_re.search(line):
            current["entryOrder"] = int(match.group("order"))
        elif match := result_re.search(line):
            current["result"] = match.group("result")
    if current:
        rows.append(current)
    return rows


def parse_operating_fills(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    fill_re = re.compile(r"FILL: (?P<symbol>\S+) (?P<side>BUY|SELL) (?P<size>\d+) @ \$(?P<price>[0-9.]+)")
    current_ts: str | None = None
    header_re = re.compile(r"^### Position Check — (?P<ts>[^\n]+)")
    for line in text.splitlines():
        if match := header_re.match(line):
            current_ts = match.group("ts").strip()
            continue
        if match := fill_re.search(line):
            rows.append({
                "ts": current_ts,
                "symbol": match.group("symbol"),
                "side": match.group("side"),
                "size": int(match.group("size")),
                "price": float(match.group("price")),
            })
    return rows


def symbol_point_value(symbol: str) -> float:
    for key, value in POINT_VALUES.items():
        if key in symbol:
            return value
    return 1.0


def trade_pnl_points(trade: dict[str, Any]) -> float:
    direction = str(trade.get("direction", "")).upper()
    entry = float(trade.get("entry_price") or 0)
    exit_price = float(trade.get("exit_price") or 0)
    if direction == "LONG":
        return exit_price - entry
    if direction == "SHORT":
        return entry - exit_price
    return 0.0


def summarize_reconciled_trades(reconciliation: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    trades = reconciliation.get("matched_trade_summary")
    if not isinstance(trades, list):
        return rows
    for trade in trades:
        if not isinstance(trade, dict):
            continue
        points = trade_pnl_points(trade)
        size = int(trade.get("size") or 0)
        symbol = str(trade.get("symbol") or "")
        rows.append({
            "direction": str(trade.get("direction") or "UNKNOWN").upper(),
            "symbol": symbol,
            "size": size,
            "entryTs": trade.get("entry_ts"),
            "exitTs": trade.get("exit_ts"),
            "entryPrice": trade.get("entry_price"),
            "exitPrice": trade.get("exit_price"),
            "pnlPoints": round(points, 4),
            "pnlDollarsEstimate": round(points * size * symbol_point_value(symbol), 2),
        })
    return rows


def summarize_journal_trades(trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for trade in trades:
        if not isinstance(trade, dict):
            continue
        points = float(trade.get("pnl_pts") or trade_pnl_points(trade))
        size = int(trade.get("size") or 0)
        symbol = str(trade.get("symbol") or symbol_from_trade_id(str(trade.get("trade_id") or "")))
        rows.append({
            "direction": str(trade.get("direction") or "UNKNOWN").upper(),
            "symbol": symbol,
            "size": size,
            "entryTs": trade.get("entry_ts"),
            "exitTs": trade.get("exit_ts"),
            "entryPrice": trade.get("entry_price"),
            "exitPrice": trade.get("exit_price"),
            "pnlPoints": round(points, 4),
            "pnlDollarsEstimate": round(float(trade.get("pnl_dollars") or points * size * symbol_point_value(symbol)), 2),
            "source": trade.get("source") or "trade-journal",
            "tradeId": trade.get("trade_id"),
            "session": trade.get("session"),
            "dayOfWeek": trade.get("day_of_week"),
            "maePts": trade.get("mae_pts"),
            "mfePts": trade.get("mfe_pts"),
            "observationOnly": bool(trade.get("observationOnly")),
            "brokerProof": bool(trade.get("brokerProof")),
            "promotionUse": trade.get("promotionUse"),
        })
    return rows


def latest_submission_side(submission: dict[str, Any], operating_submissions: list[dict[str, Any]]) -> str | None:
    side = submission.get("side")
    if side:
        return str(side).lower()
    for row in reversed(operating_submissions):
        if row.get("side"):
            return str(row["side"]).lower()
    return None


def build_learning(
    *,
    operating_log_text: str,
    mistakes_text: str,
    reconciliation: dict[str, Any],
    submission: dict[str, Any],
    guardrails: dict[str, Any],
    watchdog: dict[str, Any],
    trade_journal_rows: list[dict[str, Any]] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    operating_submissions = parse_topstep_submissions(operating_log_text)
    operating_fills = parse_operating_fills(operating_log_text)
    operator_pnl_claims = parse_operator_pnl_claims("\n".join([operating_log_text, mistakes_text]))
    reconciliation_trades = summarize_reconciled_trades(reconciliation)
    journal_trades_all = summarize_journal_trades(trade_journal_rows or [])
    daily_date = target_trade_date(reconciliation, generated_at)
    journal_trades = [
        row for row in journal_trades_all
        if not daily_date or str(row.get("entryTs") or "").startswith(daily_date)
    ]
    reconciled_trades = reconciliation_trades or journal_trades
    intended_side = latest_submission_side(submission, operating_submissions)
    realized_directions = sorted({row["direction"].lower() for row in reconciled_trades if row.get("direction")})
    total_size = sum(int(row.get("size") or 0) for row in reconciled_trades)
    max_contracts = int((guardrails.get("limits") or {}).get("max_contracts") or 0)
    bridge_config = guardrails.get("bridge_config") if isinstance(guardrails.get("bridge_config"), dict) else {}
    tp_bracket_type = bridge_config.get("tp_bracket_type")
    sl_hit_total = watchdog.get("sl_hit_total")
    tp_hit_total = watchdog.get("tp_hit_total")
    broker_flat = reconciliation.get("broker_flat")
    open_positions = reconciliation.get("open_positions")

    issues: list[dict[str, Any]] = []
    if broker_flat is False or int(open_positions or 0) > 0:
        issues.append({
            "id": "broker-open-position-active",
            "severity": "P0",
            "detail": f"read-only reconciliation reports broker_flat={broker_flat}, open_positions={open_positions}",
        })
    if intended_side and realized_directions and intended_side not in realized_directions:
        issues.append({
            "id": "intended-vs-reconciled-side-mismatch",
            "severity": "P1",
            "detail": f"latest submission intended {intended_side}, broker reconciliation matched {realized_directions}",
        })
    if max_contracts and total_size > max_contracts:
        issues.append({
            "id": "reconciled-size-exceeds-current-max-contracts",
            "severity": "P1",
            "detail": f"matched trade size total {total_size} exceeds max_contracts {max_contracts}",
        })
    if tp_bracket_type not in (None, 1):
        issues.append({
            "id": "guardrail-tp-bracket-type-stale",
            "severity": "P1",
            "detail": f"guardrails say tp_bracket_type={tp_bracket_type}; mistakes/bridge evidence says TP must be type=1 Limit",
        })
    if isinstance(sl_hit_total, int) and isinstance(tp_hit_total, int) and sl_hit_total > 0 and tp_hit_total == 0:
        issues.append({
            "id": "demo-day-all-stops-no-targets",
            "severity": "P2",
            "detail": f"watchdog reports sl_hit_total={sl_hit_total}, tp_hit_total={tp_hit_total}",
        })
    if "BILL_ENABLE_FUTURES_DEMO_EXECUTION=true" in mistakes_text:
        issues.append({
            "id": "prior-env-drift-recorded-in-mistakes",
            "severity": "P2",
            "detail": "mistakes log records prior demo execution env drift; daily plan gate must remain authoritative",
        })
    if operator_pnl_claims and not reconciliation.get("account_pnl_verified"):
        issues.append({
            "id": "operator-pnl-claim-needs-broker-proof",
            "severity": "P2",
            "detail": "operator-reported account P&L is useful learning context but cannot clear demo/live promotion until broker-native P&L evidence matches it",
        })
    if journal_trades and not reconciliation_trades and any(row.get("observationOnly") for row in journal_trades):
        issues.append({
            "id": "journal-observation-needs-broker-proof",
            "severity": "P2",
            "detail": "session-shadow trade observations are captured for learning, but promotion still requires broker-native reconciliation",
        })

    next_actions = [
        "Treat this as learning evidence only; do not promote strategy, size, bridge, or routing from it.",
        "Keep 50K MNQ-first policy as the live/challenge sizing source of truth; 100K demo results are calibration context only.",
        "Reconcile intended side vs broker matched side before enabling any demo route.",
        "Require daily plan approval and execution-grade data before any future automated demo route.",
    ]
    if tp_bracket_type != 1:
        next_actions.insert(2, "Refresh guardrails so TP bracket type is type=1 Limit everywhere.")
    else:
        next_actions.insert(2, "Keep guardrail TP bracket type pinned to type=1 Limit and do not use stale state artifacts.")

    total_pnl_estimate = round(sum(float(row.get("pnlDollarsEstimate") or 0) for row in reconciled_trades), 2)
    learning_status = "blocked-from-promotion" if issues else "learning-visible-no-critical-local-issue"
    return {
        "command": "topstep-daily-learning",
        "generatedAt": generated_at or now_iso(),
        "decision": "demo-learning-visible-execution-locked",
        "learningStatus": learning_status,
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "movesFunds": False,
        "readyForExecution": False,
        "readyForDemoExpansion": False,
        "readyForLive": False,
        "inputs": {
            "usesBrokerApi": False,
            "usesLocalArtifactsOnly": True,
        },
        "submissionSummary": {
            "latestSide": intended_side,
            "latestSignal": submission.get("signal") or submission.get("last_signal"),
            "latestStrategy": submission.get("strategy"),
            "latestSubmitted": submission.get("submitted"),
            "operatingLogSubmissionCount": len(operating_submissions),
        },
        "brokerReconciliation": {
            "ts": reconciliation.get("ts"),
            "brokerFlat": reconciliation.get("broker_flat"),
            "openPositions": reconciliation.get("open_positions"),
            "fillsToday": reconciliation.get("fills_today"),
            "matchedTrades": reconciliation.get("matched_trades"),
            "realizedDirections": realized_directions,
            "totalMatchedSize": total_size,
            "estimatedPnlDollars": total_pnl_estimate,
            "tradeEvidenceSource": "reconciliation-summary" if reconciliation_trades else "trade-journal",
            "tradeJournalCount": len(journal_trades),
        },
        "operatorReportedPnl": {
            "claimCount": len(operator_pnl_claims),
            "claims": operator_pnl_claims[-5:],
            "brokerProofRequired": bool(operator_pnl_claims),
            "promotionUse": "context-only-until-broker-reconciled" if operator_pnl_claims else "none",
        },
        "accountSizing": ACCOUNT_SIZING_POLICY,
        "watchdog": {
            "slHitTotal": sl_hit_total,
            "tpHitTotal": tp_hit_total,
            "lastFlatStatus": watchdog.get("last_flat_status"),
            "checkCount": watchdog.get("check_count"),
        },
        "guardrails": {
            "maxContracts": max_contracts,
            "tpBracketType": tp_bracket_type,
            "slBracketType": bridge_config.get("sl_bracket_type"),
            "readOnly": ((guardrails.get("mode") or {}).get("read_only")),
            "demoOnlyRequired": ((guardrails.get("mode") or {}).get("demo_only_required")),
        },
        "operatingLog": {
            "submissionCount": len(operating_submissions),
            "fillLineCount": len(operating_fills),
            "latestSubmissions": operating_submissions[-3:],
        },
        "tradeJournal": {
            "rowCount": len(journal_trades),
            "totalRowCount": len(journal_trades_all),
            "dailyDate": daily_date,
            "latest": journal_trades[-5:],
        },
        "reconciledTrades": reconciled_trades,
        "issues": issues,
        "issueCount": len(issues),
        "mustUpdateMistakes": any(item["severity"] in {"P0", "P1"} for item in issues),
        "nextActions": next_actions,
    }


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Topstep Daily Learning",
        "",
        f"Generated: `{payload.get('generatedAt')}`",
        "",
        f"- Decision: `{payload.get('decision')}`",
        f"- Learning status: `{payload.get('learningStatus')}`",
        f"- Research only: `{payload.get('researchOnly')}`",
        f"- Writes orders: `{payload.get('writesOrders')}`",
        f"- Touches broker: `{payload.get('touchesBroker')}`",
        f"- Ready for demo expansion: `{payload.get('readyForDemoExpansion')}`",
        "",
        "## Reconciliation",
        "",
        f"- Broker flat: `{payload.get('brokerReconciliation', {}).get('brokerFlat')}`",
        f"- Matched trades: `{payload.get('brokerReconciliation', {}).get('matchedTrades')}`",
        f"- Realized directions: `{payload.get('brokerReconciliation', {}).get('realizedDirections')}`",
        f"- Estimated matched P&L: `{payload.get('brokerReconciliation', {}).get('estimatedPnlDollars')}`",
        f"- Operator-reported P&L claims: `{payload.get('operatorReportedPnl', {}).get('claims')}`",
        f"- Operator P&L promotion use: `{payload.get('operatorReportedPnl', {}).get('promotionUse')}`",
        f"- Account sizing policy: `{payload.get('accountSizing')}`",
        "",
        "## Issues",
        "",
    ]
    issues = payload.get("issues") if isinstance(payload.get("issues"), list) else []
    if not issues:
        lines.append("- None detected from local artifacts.")
    else:
        for item in issues:
            lines.append(f"- `{item.get('severity')}` `{item.get('id')}`: {item.get('detail')}")
    lines.extend([
        "",
        "## Next Actions",
        "",
    ])
    for action in payload.get("nextActions", []):
        lines.append(f"- {action}")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Topstep demo daily learning artifact from local evidence")
    parser.add_argument("--operating-log", default=str(default_operating_log()))
    parser.add_argument("--mistakes", default=str(TRADING / "mistakes.md"))
    parser.add_argument("--reconciliation", default=str(STATE / "topstep-broker-reconciliation.latest.json"))
    parser.add_argument("--submission", default=str(STATE / "topstep-demo-submission.latest.json"))
    parser.add_argument("--guardrails", default=str(STATE / "topstep-100k-guardrails.json"))
    parser.add_argument("--watchdog", default=str(STATE / "topstep-demo-watchdog.json"))
    parser.add_argument("--trade-journal", default=str(STATE / "trade-journal.jsonl"))
    parser.add_argument("--output", default=str(OUT))
    parser.add_argument("--markdown", default=str(default_markdown_path()))
    args = parser.parse_args()

    payload = build_learning(
        operating_log_text=read_text(Path(args.operating_log)),
        mistakes_text=read_text(Path(args.mistakes)),
        reconciliation=read_json(Path(args.reconciliation)),
        submission=read_json(Path(args.submission)),
        guardrails=read_json(Path(args.guardrails)),
        watchdog=read_json(Path(args.watchdog)),
        trade_journal_rows=parse_trade_journal_jsonl(read_text(Path(args.trade_journal))),
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n")
    markdown = Path(args.markdown)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    markdown.write_text(render_markdown(payload))
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
