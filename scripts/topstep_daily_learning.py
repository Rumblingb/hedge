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
    generated_at: str | None = None,
) -> dict[str, Any]:
    operating_submissions = parse_topstep_submissions(operating_log_text)
    operating_fills = parse_operating_fills(operating_log_text)
    reconciled_trades = summarize_reconciled_trades(reconciliation)
    intended_side = latest_submission_side(submission, operating_submissions)
    realized_directions = sorted({row["direction"].lower() for row in reconciled_trades if row.get("direction")})
    total_size = sum(int(row.get("size") or 0) for row in reconciled_trades)
    max_contracts = int((guardrails.get("limits") or {}).get("max_contracts") or 0)
    bridge_config = guardrails.get("bridge_config") if isinstance(guardrails.get("bridge_config"), dict) else {}
    tp_bracket_type = bridge_config.get("tp_bracket_type")
    sl_hit_total = watchdog.get("sl_hit_total")
    tp_hit_total = watchdog.get("tp_hit_total")

    issues: list[dict[str, Any]] = []
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

    next_actions = [
        "Treat this as learning evidence only; do not promote strategy, size, bridge, or routing from it.",
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
        },
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
        "reconciledTrades": reconciled_trades,
        "issues": issues,
        "issueCount": len(issues),
        "mustUpdateMistakes": any(item["severity"] == "P1" for item in issues),
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
