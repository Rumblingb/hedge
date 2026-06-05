#!/usr/bin/env python3
"""Research-only one-variable entry/exit hypothesis tests for NQ.

This script reads local CSV bars, writes deterministic research artifacts, and
never touches broker, order, route, funding, or execution paths.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
RESEARCH = ROOT / ".rumbling-hedge" / "research" / "entry-hypotheses"
DEFAULT_15M = ROOT / "data" / "free" / "NQ-15m-60d.csv"
DEFAULT_30M = ROOT / "data" / "free" / "NQ-30m-60d.csv"
DEFAULT_1M = ROOT / "data" / "free" / "NQ-1m-5d.csv"
DEFAULT_DATASETS = [
    {
        "id": "nq_long_2022_2025",
        "symbol": "NQ",
        "bars15m": ROOT / "data" / "free" / "NQ-2022-2025-15m.csv",
        "bars30m": ROOT / "data" / "free" / "NQ-2022-2025-30m.csv",
        "bars1m": ROOT / "data" / "free" / "NQ-1m-3yr.csv",
    },
    {
        "id": "nq_current_60d",
        "symbol": "NQ",
        "bars15m": DEFAULT_15M,
        "bars30m": DEFAULT_30M,
        "bars1m": DEFAULT_1M,
    },
    {
        "id": "es_long_2000_2019",
        "symbol": "ES",
        "bars15m": ROOT / "data" / "free" / "ES-2000-2019-15m.csv",
        "bars30m": ROOT / "data" / "free" / "ES-2000-2019-30m.csv",
        "bars1m": None,
    },
]
DEFAULT_OUTPUT = STATE / "entry-hypothesis-research.latest.json"
DEFAULT_MARKDOWN = Path.home() / "Documents" / "memorybrain" / "Agent-Hermes" / "entry-hypothesis-research.md"


RESEARCH_ONLY = True
WRITES_ORDERS = False
TOUCHES_BROKER = False
MOVES_FUNDS = False


@dataclass(frozen=True)
class Bar:
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class Trade:
    hypothesis: str
    entry_time: datetime
    side: str
    entry: float
    exit_time: datetime
    exit: float
    stop: float
    target: float
    points: float
    cost_points: float
    net_points: float
    reason: str


@dataclass(frozen=True)
class LowerIndex:
    bars: list[Bar]
    times: list[datetime]


def parse_ts(raw: str) -> datetime:
    text = raw.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def load_bars(path: Path) -> list[Bar]:
    rows: list[Bar] = []
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            try:
                rows.append(
                    Bar(
                        ts=parse_ts(row.get("ts") or row.get("timestamp") or row.get("time") or ""),
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        volume=float(row.get("volume") or 0),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
    rows.sort(key=lambda bar: bar.ts)
    return rows


def aggregate_minutes(bars: list[Bar], minutes: int) -> list[Bar]:
    buckets: dict[datetime, list[Bar]] = {}
    for bar in bars:
        minute = (bar.ts.minute // minutes) * minutes
        key = bar.ts.replace(minute=minute, second=0, microsecond=0)
        buckets.setdefault(key, []).append(bar)
    out: list[Bar] = []
    for ts, group in sorted(buckets.items()):
        if len(group) < minutes:
            continue
        out.append(
            Bar(
                ts=ts,
                open=group[0].open,
                high=max(item.high for item in group),
                low=min(item.low for item in group),
                close=group[-1].close,
                volume=sum(item.volume for item in group),
            )
        )
    return out


def lower_index(bars: list[Bar]) -> LowerIndex:
    return LowerIndex(bars=bars, times=[bar.ts for bar in bars])


def ny_session(ts: datetime) -> str:
    # UTC conversion is fixed for the current June data window. This is a
    # research classifier, not an execution calendar.
    hour = ts.hour
    minute = ts.minute
    value = hour * 60 + minute
    if 13 * 60 + 30 <= value < 16 * 60:
        return "ny_morning"
    if 16 * 60 <= value < 20 * 60:
        return "ny_afternoon"
    return "other"


def bullish_signal(prev: Bar, bar: Bar) -> bool:
    return ny_session(bar.ts) == "ny_morning" and bar.close > bar.open and bar.close > prev.high


def bearish_signal(prev: Bar, bar: Bar) -> bool:
    return ny_session(bar.ts) == "ny_morning" and bar.close < bar.open and bar.close < prev.low


def atr_like(bars: list[Bar], index: int, lookback: int = 8) -> float:
    start = max(0, index - lookback)
    sample = bars[start:index] or bars[max(0, index - 1):index]
    ranges = [bar.high - bar.low for bar in sample]
    return sum(ranges) / len(ranges) if ranges else 30.0


def find_lower_window(lower: LowerIndex, start: datetime, end: datetime) -> list[Bar]:
    start_index = bisect.bisect_left(lower.times, start)
    end_index = bisect.bisect_left(lower.times, end)
    return lower.bars[start_index:end_index]


def exit_trade(
    *,
    hypothesis: str,
    side: str,
    entry_bar: Bar,
    future: list[Bar],
    entry: float,
    stop_points: float,
    target_points: float,
    hold_bars: int,
    cost_points: float,
) -> Trade:
    direction = 1 if side == "long" else -1
    stop = entry - direction * stop_points
    target = entry + direction * target_points
    exit_bar = future[min(len(future) - 1, max(0, hold_bars - 1))]
    exit_price = exit_bar.close
    reason = "hold"
    for bar in future[:hold_bars]:
        if side == "long":
            if bar.low <= stop:
                exit_bar = bar
                exit_price = stop
                reason = "stop"
                break
            if bar.high >= target:
                exit_bar = bar
                exit_price = target
                reason = "target"
                break
        else:
            if bar.high >= stop:
                exit_bar = bar
                exit_price = stop
                reason = "stop"
                break
            if bar.low <= target:
                exit_bar = bar
                exit_price = target
                reason = "target"
                break
    points = direction * (exit_price - entry)
    return Trade(
        hypothesis=hypothesis,
        entry_time=entry_bar.ts,
        side=side,
        entry=round(entry, 4),
        exit_time=exit_bar.ts,
        exit=round(exit_price, 4),
        stop=round(stop, 4),
        target=round(target, 4),
        points=round(points, 4),
        cost_points=cost_points,
        net_points=round(points - cost_points, 4),
        reason=reason,
    )


def run_baseline(bars15: list[Bar], *, cost_points: float) -> list[Trade]:
    trades: list[Trade] = []
    for index in range(1, len(bars15) - 8):
        bar = bars15[index]
        if not bullish_signal(bars15[index - 1], bar):
            continue
        risk = max(10.0, min(80.0, atr_like(bars15, index) * 0.75))
        trades.append(
            exit_trade(
                hypothesis="baseline_15m_bullish_breakout_next_bar",
                side="long",
                entry_bar=bars15[index + 1],
                future=bars15[index + 1:index + 9],
                entry=bars15[index + 1].open,
                stop_points=risk,
                target_points=risk * 1.5,
                hold_bars=8,
                cost_points=cost_points,
            )
        )
    return trades


def run_lower_red_pullback(
    bars15: list[Bar],
    lower: LowerIndex,
    *,
    hypothesis: str,
    cost_points: float,
) -> tuple[list[Trade], int, int]:
    trades: list[Trade] = []
    signal_count = 0
    covered = 0
    for index in range(1, len(bars15) - 8):
        bar = bars15[index]
        if not bullish_signal(bars15[index - 1], bar):
            continue
        signal_count += 1
        window = find_lower_window(lower, bar.ts, bars15[index + 1].ts)
        if not window:
            continue
        covered += 1
        red = next((item for item in window if item.close < item.open), None)
        if red is None:
            continue
        risk = max(10.0, min(80.0, atr_like(bars15, index) * 0.75))
        trades.append(
            exit_trade(
                hypothesis=hypothesis,
                side="long",
                entry_bar=red,
                future=bars15[index + 1:index + 9],
                entry=red.close,
                stop_points=risk,
                target_points=risk * 1.5,
                hold_bars=8,
                cost_points=cost_points,
            )
        )
    return trades, signal_count, covered


def run_bearish_asymmetry(bars15: list[Bar], *, cost_points: float) -> list[Trade]:
    trades: list[Trade] = []
    for index in range(1, len(bars15) - 8):
        bar = bars15[index]
        if not bearish_signal(bars15[index - 1], bar):
            continue
        risk = max(10.0, min(80.0, atr_like(bars15, index) * 0.75))
        trades.append(
            exit_trade(
                hypothesis="bearish_asymmetry_short_mirror",
                side="short",
                entry_bar=bars15[index + 1],
                future=bars15[index + 1:index + 9],
                entry=bars15[index + 1].open,
                stop_points=risk,
                target_points=risk * 1.5,
                hold_bars=8,
                cost_points=cost_points,
            )
        )
    return trades


def run_fakeout_filter(bars15: list[Bar], *, cost_points: float) -> tuple[list[Trade], int]:
    trades: list[Trade] = []
    skipped = 0
    for index in range(1, len(bars15) - 8):
        bar = bars15[index]
        if not bullish_signal(bars15[index - 1], bar):
            continue
        wick = bar.high - max(bar.open, bar.close)
        body = abs(bar.close - bar.open)
        if body <= 0 or wick / body > 1.2:
            skipped += 1
            continue
        risk = max(10.0, min(80.0, atr_like(bars15, index) * 0.75))
        trades.append(
            exit_trade(
                hypothesis="fakeout_retrace_filter_skip_large_upper_wick",
                side="long",
                entry_bar=bars15[index + 1],
                future=bars15[index + 1:index + 9],
                entry=bars15[index + 1].open,
                stop_points=risk,
                target_points=risk * 1.5,
                hold_bars=8,
                cost_points=cost_points,
            )
        )
    return trades, skipped


def run_variable_hold_target(bars15: list[Bar], *, cost_points: float) -> list[Trade]:
    trades: list[Trade] = []
    daily_net: dict[str, float] = {}
    for index in range(1, len(bars15) - 8):
        bar = bars15[index]
        day = bar.ts.date().isoformat()
        if daily_net.get(day, 0.0) >= 150.0:
            continue
        if not bullish_signal(bars15[index - 1], bar):
            continue
        risk = max(10.0, min(80.0, atr_like(bars15, index) * 0.75))
        hold = 4 if daily_net.get(day, 0.0) < 0 else 8
        target_mult = 1.0 if daily_net.get(day, 0.0) < 0 else 1.5
        trade = exit_trade(
            hypothesis="variable_daily_target_hold_logic",
            side="long",
            entry_bar=bars15[index + 1],
            future=bars15[index + 1:index + 9],
            entry=bars15[index + 1].open,
            stop_points=risk,
            target_points=risk * target_mult,
            hold_bars=hold,
            cost_points=cost_points,
        )
        daily_net[day] = daily_net.get(day, 0.0) + trade.net_points
        trades.append(trade)
    return trades


def max_drawdown(values: Iterable[float]) -> float:
    peak = 0.0
    equity = 0.0
    max_dd = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    return max_dd


def summarize_trades(trades: list[Trade]) -> dict[str, Any]:
    wins = [trade.net_points for trade in trades if trade.net_points > 0]
    losses = [trade.net_points for trade in trades if trade.net_points < 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    return {
        "tradeCount": len(trades),
        "netPoints": round(sum(trade.net_points for trade in trades), 4),
        "winRate": round(len(wins) / len(trades), 6) if trades else 0.0,
        "profitFactor": round(gross_win / gross_loss, 6) if gross_loss else (999.0 if gross_win else 0.0),
        "maxDrawdownPoints": round(max_drawdown(trade.net_points for trade in trades), 4),
        "avgNetPoints": round(sum(trade.net_points for trade in trades) / len(trades), 4) if trades else 0.0,
    }


def split_trades(trades: list[Trade], train_fraction: float) -> tuple[list[Trade], list[Trade]]:
    if not trades:
        return [], []
    ordered = sorted(trades, key=lambda trade: trade.entry_time)
    split_index = max(1, min(len(ordered) - 1, int(len(ordered) * train_fraction)))
    return ordered[:split_index], ordered[split_index:]


def cost_stress(trades: list[Trade], extra_costs: list[float]) -> list[dict[str, Any]]:
    rows = []
    for extra in extra_costs:
        stressed = [
            Trade(
                **{
                    **trade.__dict__,
                    "net_points": round(trade.net_points - extra, 4),
                    "cost_points": round(trade.cost_points + extra, 4),
                }
            )
            for trade in trades
        ]
        rows.append({"extraCostPoints": extra, **summarize_trades(stressed)})
    return rows


def blockers_for(summary: dict[str, Any], coverage_pct: float) -> list[str]:
    blockers: list[str] = []
    if summary["oos"]["tradeCount"] < 30:
        blockers.append("too-few-oos-trades")
    if summary["oos"]["netPoints"] <= 0:
        blockers.append("oos-net-not-positive-after-costs")
    if summary["oos"]["profitFactor"] < 1.25:
        blockers.append("oos-profit-factor-too-low")
    if summary["oos"]["maxDrawdownPoints"] > max(250.0, abs(summary["oos"]["netPoints"]) * 1.5):
        blockers.append("oos-drawdown-too-high")
    if coverage_pct < 50.0:
        blockers.append("coverage-too-thin")
    if any(row["netPoints"] <= 0 or row["profitFactor"] < 1.1 for row in summary["costStress"]):
        blockers.append("cost-stress-not-robust")
    blockers.extend(["not-broker-grade-current-session-proof", "not-demo-or-execution-evidence"])
    return blockers


def hypothesis_summary(
    hypothesis_id: str,
    trades: list[Trade],
    *,
    signal_count: int,
    covered_count: int,
    train_fraction: float,
    extra_costs: list[float],
    notes: list[str],
) -> dict[str, Any]:
    train, oos = split_trades(trades, train_fraction)
    coverage_pct = round((covered_count / signal_count) * 100, 4) if signal_count else 0.0
    summary = {
        "id": hypothesis_id,
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "readyForExecution": False,
        "signalCount": signal_count,
        "coverageCount": covered_count,
        "coveragePct": coverage_pct,
        "train": summarize_trades(train),
        "oos": summarize_trades(oos),
        "costStress": cost_stress(oos, extra_costs),
        "notes": notes,
    }
    summary["blockers"] = blockers_for(summary, coverage_pct)
    summary["evidenceGrade"] = (
        "research-candidate-watch"
        if summary["oos"]["tradeCount"] >= 30
        and summary["oos"]["netPoints"] > 0
        and summary["oos"]["profitFactor"] >= 1.25
        and "cost-stress-not-robust" not in summary["blockers"]
        else "research-only-blocked"
    )
    return summary


def trade_dict(trade: Trade) -> dict[str, Any]:
    return {
        **trade.__dict__,
        "entry_time": trade.entry_time.isoformat(),
        "exit_time": trade.exit_time.isoformat(),
    }


def evaluate_dataset(
    *,
    dataset_id: str,
    symbol: str,
    bars15: list[Bar],
    bars30: list[Bar],
    bars1: list[Bar],
    cost: float,
    train_fraction: float,
    extra_costs: list[float],
) -> dict[str, Any]:
    bars3 = aggregate_minutes(bars1, 3) if bars1 else []
    index1 = lower_index(bars1) if bars1 else None
    index3 = lower_index(bars3) if bars3 else None
    lower_available = index1 is not None and index3 is not None
    baseline = run_baseline(bars15, cost_points=cost)
    signal_count = len(baseline)
    if lower_available:
        red1, signal_count, covered1 = run_lower_red_pullback(
            bars15,
            index1,
            hypothesis="long_on_1m_red_candle_after_15m_bullish_signal",
            cost_points=cost,
        )
        red3, _, covered3 = run_lower_red_pullback(
            bars15,
            index3,
            hypothesis="long_on_3m_red_candle_after_15m_bullish_signal",
            cost_points=cost,
        )
    else:
        red1, covered1 = [], 0
        red3, covered3 = [], 0
    bearish = run_bearish_asymmetry(bars15, cost_points=cost)
    fakeout, skipped = run_fakeout_filter(bars15, cost_points=cost)
    variable = run_variable_hold_target(bars15, cost_points=cost)
    signal_count = signal_count or len(baseline)

    hypotheses: list[dict[str, Any]] = [
        hypothesis_summary(
            "baseline_15m_bullish_breakout_next_bar",
            baseline,
            signal_count=len(baseline),
            covered_count=len(baseline),
            train_fraction=train_fraction,
            extra_costs=extra_costs,
            notes=["Baseline for one-variable comparisons; NY morning bullish breakout only."],
        )
    ]
    lower_notes = (
        ["Changes entry timing only; lower-timeframe data is available for this historical slice."]
        if lower_available
        else ["Skipped: no overlapping 1m lower-timeframe file for this dataset."]
    )
    hypotheses.append(
        hypothesis_summary(
            "long_on_1m_red_candle_after_15m_bullish_signal",
            red1,
            signal_count=signal_count,
            covered_count=covered1,
            train_fraction=train_fraction,
            extra_costs=extra_costs,
            notes=lower_notes,
        )
    )
    hypotheses.append(
        hypothesis_summary(
            "long_on_3m_red_candle_after_15m_bullish_signal",
            red3,
            signal_count=signal_count,
            covered_count=covered3,
            train_fraction=train_fraction,
            extra_costs=extra_costs,
            notes=lower_notes + ["3m bars are aggregated from local 1m data when available."],
        )
    )
    hypotheses.extend([
        hypothesis_summary(
            "bearish_asymmetry_short_mirror",
            bearish,
            signal_count=len(bearish),
            covered_count=len(bearish),
            train_fraction=train_fraction,
            extra_costs=extra_costs,
            notes=["Tests whether bearish mirror behaves differently from long NQ breakout logic."],
        ),
        hypothesis_summary(
            "fakeout_retrace_filter_skip_large_upper_wick",
            fakeout,
            signal_count=len(baseline),
            covered_count=len(fakeout),
            train_fraction=train_fraction,
            extra_costs=extra_costs,
            notes=[f"Skips {skipped} bullish breakouts with large upper wick; changes filter only."],
        ),
        hypothesis_summary(
            "variable_daily_target_hold_logic",
            variable,
            signal_count=len(baseline),
            covered_count=len(variable),
            train_fraction=train_fraction,
            extra_costs=extra_costs,
            notes=["Changes daily target/hold behavior only; does not change entry signal."],
        ),
    ])
    best = max(hypotheses, key=lambda row: (row["evidenceGrade"] == "research-candidate-watch", row["oos"]["profitFactor"], row["oos"]["netPoints"], row["oos"]["tradeCount"])) if hypotheses else None
    return {
        "id": dataset_id,
        "symbol": symbol,
        "bars15m": len(bars15),
        "bars30m": len(bars30),
        "bars1m": len(bars1),
        "bars3m": len(bars3),
        "first15m": bars15[0].ts.isoformat() if bars15 else "",
        "last15m": bars15[-1].ts.isoformat() if bars15 else "",
        "bestResearchWatch": best,
        "hypotheses": hypotheses,
        "tradeSamples": {
            "baseline": [trade_dict(trade) for trade in baseline[:5]],
            "red1m": [trade_dict(trade) for trade in red1[:5]],
            "red3m": [trade_dict(trade) for trade in red3[:5]],
        },
    }


def parse_dataset_specs(raw: str | None) -> list[dict[str, Any]]:
    if not raw:
        return DEFAULT_DATASETS
    specs = []
    for chunk in raw.split(";"):
        if not chunk.strip():
            continue
        parts = chunk.split(",")
        if len(parts) < 4:
            continue
        specs.append(
            {
                "id": parts[0],
                "symbol": parts[1],
                "bars15m": Path(parts[2]),
                "bars30m": Path(parts[3]),
                "bars1m": Path(parts[4]) if len(parts) > 4 and parts[4] else None,
            }
        )
    return specs


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    cost = float(args.cost_points)
    train_fraction = float(args.train_fraction)
    extra_costs = [float(item) for item in str(args.extra_costs).split(",") if item.strip()]
    dataset_payloads: list[dict[str, Any]] = []
    for spec in parse_dataset_specs(args.datasets):
        bars15 = load_bars(Path(spec["bars15m"]))
        bars30 = load_bars(Path(spec["bars30m"]))
        bars1 = load_bars(Path(spec["bars1m"])) if spec.get("bars1m") else []
        dataset_payloads.append(
            evaluate_dataset(
                dataset_id=str(spec["id"]),
                symbol=str(spec["symbol"]),
                bars15=bars15,
                bars30=bars30,
                bars1=bars1,
                cost=cost,
                train_fraction=train_fraction,
                extra_costs=extra_costs,
            )
        )
    all_rows = [row for dataset in dataset_payloads for row in dataset["hypotheses"]]
    candidate_counts: dict[str, int] = {}
    for row in all_rows:
        if row["evidenceGrade"] == "research-candidate-watch":
            candidate_counts[row["id"]] = candidate_counts.get(row["id"], 0) + 1
    for row in all_rows:
        if row["evidenceGrade"] == "research-candidate-watch" and candidate_counts.get(row["id"], 0) < 2:
            row["blockers"].append("not-cross-dataset-robust")
            row["evidenceGrade"] = "research-only-blocked"
    for dataset in dataset_payloads:
        dataset["bestResearchWatch"] = max(
            dataset["hypotheses"],
            key=lambda row: (
                row["evidenceGrade"] == "research-candidate-watch",
                row["oos"]["profitFactor"],
                row["oos"]["netPoints"],
                row["oos"]["tradeCount"],
            ),
        ) if dataset["hypotheses"] else None
    best = max(
        all_rows,
        key=lambda row: (
            row["evidenceGrade"] == "research-candidate-watch",
            row["oos"]["profitFactor"],
            row["oos"]["netPoints"],
            row["oos"]["tradeCount"],
        ),
    ) if all_rows else None
    return {
        "command": "entry-hypothesis-research",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "decision": "research-only-entry-hypotheses-not-promotable",
        "researchOnly": RESEARCH_ONLY,
        "writesOrders": WRITES_ORDERS,
        "touchesBroker": TOUCHES_BROKER,
        "movesFunds": MOVES_FUNDS,
        "readyForExecution": False,
        "readyForDemoExpansion": False,
        "data": {
            "datasetCount": len(dataset_payloads),
            "datasets": [
                {
                    "id": dataset["id"],
                    "symbol": dataset["symbol"],
                    "bars15m": dataset["bars15m"],
                    "bars30m": dataset["bars30m"],
                    "bars1m": dataset["bars1m"],
                    "bars3m": dataset["bars3m"],
                    "first15m": dataset["first15m"],
                    "last15m": dataset["last15m"],
                }
                for dataset in dataset_payloads
            ],
        },
        "method": {
            "trainFraction": train_fraction,
            "costPointsPerRoundTrip": cost,
            "extraCostStressPoints": extra_costs,
            "session": "NY morning UTC approximation",
            "instrument": "NQ/ES research bars",
        },
        "bestResearchWatch": best,
        "datasets": dataset_payloads,
        "hypotheses": all_rows,
        "globalBlockers": [
            "research-only-local-csv-evidence",
            "historical-sources-do-not-clear-current-broker-parity",
            "single-dataset-winners-are-overfit-risk-until-confirmed-across-current-nq-and-independent-history",
            "requires-broker-grade-overlapping-1m-3m-15m-data",
            "requires-purged-walkforward-before-demo-shadow",
            "requires-no-edge-ledger-update-for-rejected-branches",
        ],
    }


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Entry Hypothesis Research",
        "",
        f"- Decision: `{payload['decision']}`",
        f"- Ready for execution: `{payload['readyForExecution']}`",
        f"- Ready for demo expansion: `{payload['readyForDemoExpansion']}`",
        f"- Data: `{payload['data']}`",
        "",
        "## Results",
        "",
        "| Hypothesis | OOS Trades | OOS Net | OOS PF | OOS DD | Coverage | Grade | Blockers |",
        "|---|---:|---:|---:|---:|---:|---|---|",
    ]
    for item in payload["hypotheses"]:
        lines.append(
            "| {id} | {trades} | {net} | {pf} | {dd} | {coverage}% | {grade} | {blockers} |".format(
                id=item["id"],
                trades=item["oos"]["tradeCount"],
                net=item["oos"]["netPoints"],
                pf=item["oos"]["profitFactor"],
                dd=item["oos"]["maxDrawdownPoints"],
                coverage=item["coveragePct"],
                grade=item["evidenceGrade"],
                blockers=", ".join(item["blockers"]),
            )
        )
    lines.extend(["", "## Research Read", ""])
    best = payload.get("bestResearchWatch") or {}
    lines.append(
        f"Best watch by current scoring is `{best.get('id')}`, but every branch remains research-only and blocked from demo/live promotion."
    )
    lines.append("")
    lines.append("Next step: rerun the entry-timing branches on broker-grade overlapping Topstep/ProjectX 1m/3m/15m data, then add rejected branches to the no-edge ledger.")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run research-only entry hypothesis tests.")
    parser.add_argument("--nq-15m", default=str(DEFAULT_15M))
    parser.add_argument("--nq-30m", default=str(DEFAULT_30M))
    parser.add_argument("--nq-1m", default=str(DEFAULT_1M))
    parser.add_argument(
        "--datasets",
        default=None,
        help="Optional semicolon list id,symbol,15m,30m,1m. Default uses NQ long/current and ES long local historical files.",
    )
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))
    parser.add_argument("--train-fraction", default="0.7")
    parser.add_argument("--cost-points", default="1.0")
    parser.add_argument("--extra-costs", default="1,2,4")
    args = parser.parse_args()

    payload = build_report(args)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")

    RESEARCH.mkdir(parents=True, exist_ok=True)
    (RESEARCH / "entry-hypothesis-research.latest.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")

    markdown = Path(args.markdown)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    markdown.write_text(render_markdown(payload), encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
