#!/usr/bin/env python3
"""
Trade Performance Analyzer — periodic MAE/MFE analysis + optimization recommendations.

Reads trade-journal.jsonl, computes per-group statistics, suggests optimal
SL/TP levels based on MAE/MFE patterns, and outputs a structured JSON report.

CLI:
    python3 trade_performance_analyzer.py              # full analysis
    python3 trade_performance_analyzer.py --min-trades 10   # filter groups
    python3 trade_performance_analyzer.py --pretty          # pretty-print output
"""

import argparse
import json
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

HOME = Path.home()
STATE_DIR = HOME / ".rumbling-hedge" / "state"
JOURNAL_PATH = STATE_DIR / "trade-journal.jsonl"
REPORT_PATH = STATE_DIR / "trade-performance-report.latest.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_trades() -> List[Dict[str, Any]]:
    """Load all trade records from the journal JSONL."""
    trades = []
    if not JOURNAL_PATH.exists():
        return trades
    for line in JOURNAL_PATH.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
            trades.append(record)
        except json.JSONDecodeError:
            pass
    return trades


def compute_group_stats(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute aggregate statistics for a group of trades."""
    if not trades:
        return {
            "count": 0,
            "win_rate": 0.0,
            "avg_pnl_dollars": 0.0,
            "avg_pnl_pts": 0.0,
            "profit_factor": 0.0,
            "avg_mae_pts": 0.0,
            "avg_mfe_pts": 0.0,
            "avg_duration_minutes": 0.0,
            "median_mae_pts": 0.0,
            "median_mfe_pts": 0.0,
            "optimal_sl_suggestion_pts": 0.0,
            "optimal_tp_suggestion_pts": 0.0,
            "total_pnl_dollars": 0.0,
        }

    total = len(trades)
    wins = [t for t in trades if t.get("pnl_dollars", 0) >= 0]
    losses = [t for t in trades if t.get("pnl_dollars", 0) < 0]
    win_count = len(wins)
    win_rate = win_count / total if total > 0 else 0.0

    pnls = [t.get("pnl_dollars", 0) for t in trades]
    avg_pnl = statistics.mean(pnls) if pnls else 0.0

    pts_pnls = [t.get("pnl_pts", 0) for t in trades]
    avg_pnl_pts = statistics.mean(pts_pnls) if pts_pnls else 0.0

    # Profit factor = gross profit / gross loss (absolute)
    gross_profit = sum(t.get("pnl_dollars", 0) for t in wins)
    gross_loss = abs(sum(t.get("pnl_dollars", 0) for t in losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)

    maes = [t.get("mae_pts", 0) for t in trades]
    mfes = [t.get("mfe_pts", 0) for t in trades]
    durations = [t.get("duration_minutes", 0) for t in trades]

    avg_mae = statistics.mean(maes) if maes else 0.0
    avg_mfe = statistics.mean(mfes) if mfes else 0.0
    avg_duration = statistics.mean(durations) if durations else 0.0

    # Median MAE/MFE for SL/TP suggestions
    sorted_maes = sorted(maes)
    sorted_mfes = sorted(mfes)
    median_mae = statistics.median(sorted_maes) if sorted_maes else 0.0
    median_mfe = statistics.median(sorted_mfes) if sorted_mfes else 0.0

    # SL suggestion: median MAE * 1.2 (covers ~80% of trades)
    sl_suggestion = median_mae * 1.2 if median_mae > 0 else 0.0

    # TP suggestion: median MFE of winning trades * 0.8
    win_mfes = [t.get("mfe_pts", 0) for t in wins]
    win_median_mfe = statistics.median(sorted(win_mfes)) if win_mfes else 0.0
    tp_suggestion = win_median_mfe * 0.8 if win_median_mfe > 0 else 0.0

    # SL coverage: what percentage of trades would the suggested SL cover?
    sl_covered = sum(1 for m in maes if m <= sl_suggestion)
    sl_coverage = sl_covered / total if total > 0 else 0.0

    return {
        "count": total,
        "win_rate": round(win_rate, 4),
        "avg_pnl_dollars": round(avg_pnl, 2),
        "avg_pnl_pts": round(avg_pnl_pts, 2),
        "profit_factor": round(profit_factor, 2),
        "avg_mae_pts": round(avg_mae, 2),
        "avg_mfe_pts": round(avg_mfe, 2),
        "avg_duration_minutes": round(avg_duration, 1),
        "median_mae_pts": round(median_mae, 2),
        "median_mfe_pts": round(median_mfe, 2),
        "optimal_sl_suggestion_pts": round(sl_suggestion, 2),
        "optimal_tp_suggestion_pts": round(tp_suggestion, 2),
        "sl_coverage_pct": round(sl_coverage * 100, 1),
        "total_pnl_dollars": round(sum(pnls), 2),
        "win_count": win_count,
        "loss_count": len(losses),
    }


def analyze(min_trades: int = 5) -> Dict[str, Any]:
    """Run full performance analysis."""
    trades = load_trades()
    total = len(trades)

    if total == 0:
        return {
            "timestamp": now_iso(),
            "total_trades": 0,
            "overall_win_rate": 0.0,
            "avg_pnl_dollars": 0.0,
            "profit_factor": 0.0,
            "optimal_sl_suggestion_pts": 0.0,
            "optimal_tp_suggestion_pts": 0.0,
            "summary": "No trades in journal yet.",
            "by_session": {},
            "by_regime": {},
            "by_day": {},
            "by_direction": {},
            "recommendations": [],
        }

    # Overall stats
    overall = compute_group_stats(trades)

    # Group by session
    by_session: Dict[str, List[Dict[str, Any]]] = {}
    for t in trades:
        session = t.get("session", "UNKNOWN")
        by_session.setdefault(session, []).append(t)

    session_stats = {}
    for session, group in sorted(by_session.items()):
        if len(group) >= min_trades:
            session_stats[session] = compute_group_stats(group)

    # Group by regime
    by_regime: Dict[str, List[Dict[str, Any]]] = {}
    for t in trades:
        regime = t.get("regime", "normal")
        by_regime.setdefault(regime, []).append(t)

    regime_stats = {}
    for regime, group in sorted(by_regime.items()):
        if len(group) >= min_trades:
            regime_stats[regime] = compute_group_stats(group)

    # Group by day of week
    by_day: Dict[str, List[Dict[str, Any]]] = {}
    for t in trades:
        day = t.get("day_of_week", "UNKNOWN")
        by_day.setdefault(day, []).append(t)

    day_stats = {}
    for day, group in sorted(by_day.items()):
        if len(group) >= min_trades:
            day_stats[day] = compute_group_stats(group)

    # Group by direction
    by_direction: Dict[str, List[Dict[str, Any]]] = {}
    for t in trades:
        direction = t.get("direction", "UNKNOWN")
        by_direction.setdefault(direction, []).append(t)

    direction_stats = {}
    for direction, group in sorted(by_direction.items()):
        if len(group) >= min_trades:
            direction_stats[direction] = compute_group_stats(group)

    # Generate recommendations
    recommendations = generate_recommendations(
        overall, session_stats, regime_stats, day_stats, direction_stats
    )

    # Build summary
    summary = build_summary(overall, recommendations)

    return {
        "timestamp": now_iso(),
        "total_trades": total,
        "overall_win_rate": overall["win_rate"],
        "avg_pnl_dollars": overall["avg_pnl_dollars"],
        "profit_factor": overall["profit_factor"],
        "optimal_sl_suggestion_pts": overall["optimal_sl_suggestion_pts"],
        "optimal_tp_suggestion_pts": overall["optimal_tp_suggestion_pts"],
        "summary": summary,
        "by_session": session_stats,
        "by_regime": regime_stats,
        "by_day": day_stats,
        "by_direction": direction_stats,
        "recommendations": recommendations,
    }


def generate_recommendations(
    overall: Dict[str, Any],
    by_session: Dict[str, Dict[str, Any]],
    by_regime: Dict[str, Dict[str, Any]],
    by_day: Dict[str, Dict[str, Any]],
    by_direction: Dict[str, Dict[str, Any]],
) -> List[str]:
    """Generate actionable recommendations based on analysis."""
    recs = []

    total = overall["count"]
    if total < 3:
        recs.append("Collect more trades before drawing conclusions (minimum 3 recommended).")
        return recs

    # SL recommendation
    if overall["sl_coverage_pct"] < 80:
        recs.append(
            f"Tighten stop-loss to {overall['optimal_sl_suggestion_pts']:.1f} pts "
            f"(covers {overall['sl_coverage_pct']:.0f}% of MAE values). "
            f"Current suggestion is 1.2x median MAE."
        )
    else:
        recs.append(
            f"Stop-loss at {overall['optimal_sl_suggestion_pts']:.1f} pts is well-calibrated "
            f"(covers {overall['sl_coverage_pct']:.0f}% of MAE values)."
        )

    # TP recommendation
    if overall["optimal_tp_suggestion_pts"] > 0:
        recs.append(
            f"Consider take-profit at {overall['optimal_tp_suggestion_pts']:.1f} pts "
            f"(0.8x median MFE of winning trades)."
        )

    # Win rate warning
    if overall["win_rate"] < 0.35:
        recs.append(
            f"CRITICAL: Win rate is only {overall['win_rate']:.1%}. "
            f"Review entry criteria and market regime filters."
        )
    elif overall["win_rate"] < 0.45:
        recs.append(
            f"Win rate of {overall['win_rate']:.1%} is below target. "
            f"Consider increasing minimum R:R requirement."
        )

    # Profit factor warning
    if overall["profit_factor"] < 1.0:
        recs.append(
            f"CRITICAL: Profit factor is {overall['profit_factor']:.2f} (< 1.0). "
            f"Strategy is losing money. Reduce size or pause trading."
        )
    elif overall["profit_factor"] < 1.5:
        recs.append(
            f"Profit factor of {overall['profit_factor']:.2f} is marginal. "
            f"Aim for > 1.5 by improving exit timing."
        )

    # Session-specific
    worst_session = None
    worst_win_rate = 1.0
    best_session = None
    best_win_rate = 0.0

    for session, stats in by_session.items():
        if stats["count"] >= 3:
            if stats["win_rate"] < worst_win_rate:
                worst_win_rate = stats["win_rate"]
                worst_session = session
            if stats["win_rate"] > best_win_rate:
                best_win_rate = stats["win_rate"]
                best_session = session

    if worst_session and worst_win_rate < 0.4:
        wstats = by_session.get(worst_session, {})
        recs.append(
            f"Avoid {worst_session} session: win rate {worst_win_rate:.1%} "
            f"({wstats.get('count', 0)} trades). Consider paper trading only."
        )
    if best_session and best_win_rate > 0.5:
        recs.append(
            f"Best session is {best_session}: win rate {best_win_rate:.1%}. "
            f"Prioritize this session for live trading."
        )

    # Direction bias
    long_stats = by_direction.get("LONG", {})
    short_stats = by_direction.get("SHORT", {})
    if long_stats and short_stats:
        long_wr = long_stats.get("win_rate", 0)
        short_wr = short_stats.get("win_rate", 0)
        if abs(long_wr - short_wr) > 0.15:
            better = "LONG" if long_wr > short_wr else "SHORT"
            recs.append(
                f"Direction bias detected: {better} trades perform significantly better. "
                f"(LONG: {long_wr:.1%}, SHORT: {short_wr:.1%})"
            )

    # Day-specific
    worst_day = None
    worst_day_wr = 1.0
    for day, stats in by_day.items():
        if stats["count"] >= 3 and stats["win_rate"] < worst_day_wr:
            worst_day_wr = stats["win_rate"]
            worst_day = day
    if worst_day and worst_day_wr < 0.3:
        recs.append(f"Consider skipping {worst_day}s: win rate only {worst_day_wr:.1%}.")

    # Duration analysis
    if overall["avg_duration_minutes"] > 20:
        recs.append(
            f"Average trade duration is {overall['avg_duration_minutes']:.0f} min. "
            f"Consider tightening time-stops to reduce exposure."
        )

    if overall["avg_mae_pts"] > overall["avg_mfe_pts"] * 1.5:
        recs.append(
            "MAE is significantly larger than MFE. Trades are being held through "
            "large drawdowns. Consider earlier exits or tighter stops."
        )

    return recs


def build_summary(overall: Dict[str, Any], recommendations: List[str]) -> str:
    """Build a human-readable summary string."""
    total = overall["count"]
    if total == 0:
        return "No trades in journal."

    parts = [
        f"{total} trades analyzed.",
        f"Win rate: {overall['win_rate']:.1%}",
        f"Avg PnL: ${overall['avg_pnl_dollars']:.2f}",
        f"Profit factor: {overall['profit_factor']:.2f}",
        f"Optimal SL: {overall['optimal_sl_suggestion_pts']:.1f} pts",
        f"Optimal TP: {overall['optimal_tp_suggestion_pts']:.1f} pts",
    ]

    if recommendations:
        urgent = [r for r in recommendations if "CRITICAL" in r]
        if urgent:
            parts.append(f"WARNING: {len(urgent)} critical issue(s) found.")

    return " | ".join(parts)


def run(min_trades: int = 5, pretty: bool = False) -> Dict[str, Any]:
    """Run analysis and save report."""
    report = analyze(min_trades)
    output = report

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(output, indent=2 if pretty else None, default=str))

    if pretty:
        print(json.dumps(output, indent=2, default=str))
    else:
        print(f"Analysis complete. {report['total_trades']} trades. "
              f"Report saved to {REPORT_PATH}")
        if report["recommendations"]:
            for r in report["recommendations"]:
                print(f"  -> {r}")

    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Trade Performance Analyzer — MAE/MFE analysis + optimization"
    )
    parser.add_argument("--min-trades", type=int, default=5,
                        help="Minimum trades required per group for analysis (default: 5)")
    parser.add_argument("--pretty", action="store_true",
                        help="Pretty-print JSON output")

    args = parser.parse_args()
    run(min_trades=args.min_trades, pretty=args.pretty)


if __name__ == "__main__":
    main()
