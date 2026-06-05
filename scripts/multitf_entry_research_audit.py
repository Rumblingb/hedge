#!/usr/bin/env python3
"""Audit multi-timeframe entry research claims.

This reads the trade-level result from ``multi_tf_entry_backtest.py`` and turns
it into a promotion-safe artifact. The goal is to preserve promising findings
without letting narrative tables bypass OOS, cost, data-coverage, or daily-plan
gates.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
DEFAULT_INPUT = ROOT / ".rumbling-hedge" / "research" / "multi-tf-entry" / "results.json"
DEFAULT_OUTPUT = STATE / "multitf-entry-research-audit.latest.json"
DEFAULT_MARKDOWN = Path.home() / "Documents" / "memorybrain" / "Agent-Hermes" / "multitf-entry-research-audit.md"


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def pct(value: float) -> float:
    return round(value * 100, 4)


def safe_div(num: float, den: float) -> float:
    return num / den if den else 0.0


def build_audit(result: dict[str, Any], *, input_path: Path) -> dict[str, Any]:
    trades = result.get("trades") if isinstance(result.get("trades"), list) else []
    baseline = result.get("baseline") if isinstance(result.get("baseline"), dict) else {}
    multi_tf = result.get("multi_tf") if isinstance(result.get("multi_tf"), dict) else {}

    total_trades = len(trades)
    no_lower_tf = sum(1 for trade in trades if trade.get("reason") == "no_1m_data")
    lower_tf_decision = total_trades - no_lower_tf
    pullback_confirmed = sum(1 for trade in trades if trade.get("reason") == "pullback_confirmed")
    improved = sum(1 for trade in trades if trade.get("improved"))

    baseline_total = float(baseline.get("total_r") or 0)
    multitf_total = float(multi_tf.get("total_r") or 0)
    delta = multitf_total - baseline_total
    delta_pct = safe_div(delta, abs(baseline_total)) if baseline_total else 0.0
    baseline_pf = float(baseline.get("pf") or 0)
    multitf_pf = float(multi_tf.get("pf") or 0)

    trade_times = [str(trade.get("entry_time")) for trade in trades if trade.get("entry_time")]
    if trade_times:
        first_trade = min(trade_times)
        last_trade = max(trade_times)
        unique_days = len({trade_time[:10] for trade_time in trade_times})
    else:
        first_trade = ""
        last_trade = ""
        unique_days = 0

    blockers: list[str] = []
    if not trades:
        blockers.append("missing-trade-level-results")
    if lower_tf_decision < 50:
        blockers.append("too-few-lower-timeframe-decisions")
    if safe_div(lower_tf_decision, total_trades) < 0.25:
        blockers.append("lower-timeframe-coverage-too-thin")
    if pullback_confirmed < 50:
        blockers.append("too-few-pullback-confirmations")
    if delta <= 0:
        blockers.append("multi-tf-delta-not-positive")
    if multitf_pf <= baseline_pf:
        blockers.append("profit-factor-not-improved")
    blockers.extend(
        [
            "not-run-through-purged-oos-promotion-gate",
            "not-cost-slippage-stressed",
            "not-broker-grade-topstep-depth-cleared",
        ]
    )

    evidence_grade = "promising-research" if delta > 0 and multitf_pf > baseline_pf else "weak-or-negative"
    if "lower-timeframe-coverage-too-thin" in blockers:
        evidence_grade = "promising-but-coverage-thin"

    return {
        "command": "multitf-entry-research-audit",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "inputPath": str(input_path),
        "decision": "research-only-multitf-entry-not-promotable",
        "evidenceGrade": evidence_grade,
        "researchOnly": True,
        "touchesBroker": False,
        "writesOrders": False,
        "readyForDemoExpansion": False,
        "readyForExecution": False,
        "summary": {
            "baselineTotalPoints": round(baseline_total, 4),
            "multiTfTotalPoints": round(multitf_total, 4),
            "deltaPoints": round(delta, 4),
            "deltaPct": pct(delta_pct),
            "baselineProfitFactor": round(baseline_pf, 6),
            "multiTfProfitFactor": round(multitf_pf, 6),
            "baselineWinRate": pct(float(baseline.get("wr") or 0)),
            "multiTfWinRate": pct(float(multi_tf.get("wr") or 0)),
            "totalTrades": total_trades,
            "lowerTimeframeDecisionTrades": lower_tf_decision,
            "lowerTimeframeCoveragePct": pct(safe_div(lower_tf_decision, total_trades)),
            "pullbackConfirmedTrades": pullback_confirmed,
            "pullbackConfirmedPct": pct(safe_div(pullback_confirmed, total_trades)),
            "improvedTrades": improved,
            "improvedPct": pct(safe_div(improved, total_trades)),
            "uniqueDays": unique_days,
            "firstTradeTime": first_trade,
            "lastTradeTime": last_trade,
        },
        "blockers": blockers,
        "operatorRead": (
            "Multi-timeframe pullback entry is a valid one-variable research branch, "
            "but this artifact cannot promote a strategy. Current results are mostly "
            "15m baseline fallback rows unless lower-timeframe coverage improves."
        ),
        "nextResearchSteps": [
            "Run the same entry timing rule on broker-grade Topstep 1m/3m/15m overlapping bars.",
            "Evaluate only one variable at a time: entry timing first, then bearish asymmetry, then fakeout filter.",
            "Require purged OOS, cost/slippage stress, and per-session fold evidence before demo-shadow discussion.",
            "Keep higher timeframe direction as the signal source; lower timeframe candles may only improve entry timing.",
        ],
    }


def render_markdown(payload: dict[str, Any]) -> str:
    summary = payload.get("summary") or {}
    lines = [
        "# Multi-TF Entry Research Audit",
        "",
        f"- Decision: `{payload.get('decision')}`",
        f"- Evidence grade: `{payload.get('evidenceGrade')}`",
        f"- Ready for execution: `{payload.get('readyForExecution')}`",
        f"- Ready for demo expansion: `{payload.get('readyForDemoExpansion')}`",
        f"- Input: `{payload.get('inputPath')}`",
        "",
        "## Verified Result",
        "",
        f"- Baseline total points: `{summary.get('baselineTotalPoints')}`",
        f"- Multi-TF total points: `{summary.get('multiTfTotalPoints')}`",
        f"- Delta: `{summary.get('deltaPoints')}` points / `{summary.get('deltaPct')}`%",
        f"- Profit factor: `{summary.get('baselineProfitFactor')}` -> `{summary.get('multiTfProfitFactor')}`",
        f"- Lower-timeframe decision coverage: `{summary.get('lowerTimeframeDecisionTrades')}/{summary.get('totalTrades')}` trades (`{summary.get('lowerTimeframeCoveragePct')}`%)",
        f"- Pullback confirmations: `{summary.get('pullbackConfirmedTrades')}` (`{summary.get('pullbackConfirmedPct')}`%)",
        f"- Improved trades: `{summary.get('improvedTrades')}` (`{summary.get('improvedPct')}`%)",
        f"- Sample: `{summary.get('uniqueDays')}` days, `{summary.get('firstTradeTime')}` to `{summary.get('lastTradeTime')}`",
        "",
        "## Blockers",
        "",
    ]
    for blocker in payload.get("blockers") or []:
        lines.append(f"- `{blocker}`")
    lines.extend(["", "## Next Research Steps", ""])
    for step in payload.get("nextResearchSteps") or []:
        lines.append(f"- {step}")
    lines.append("")
    lines.append(payload.get("operatorRead") or "")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit multi-TF entry research output.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))
    args = parser.parse_args()

    input_path = Path(args.input)
    payload = build_audit(read_json(input_path), input_path=input_path)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")

    markdown = Path(args.markdown)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    markdown.write_text(render_markdown(payload), encoding="utf-8")

    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
