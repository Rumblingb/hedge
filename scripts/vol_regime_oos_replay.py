#!/usr/bin/env python3
"""Research-only purged OOS replay for the NQ 60m volatility-regime candidate.

The broad walk-forward matrix can be expensive and opaque. This script narrows
the evidence question to the only fresh Backtrader full-sample survivor:
`wq-vol-regime-60m`. It has no broker imports, no credentials, and writes only
research artifacts.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from dataclasses import dataclass
from datetime import datetime, time, timezone
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / ".rumbling-hedge" / "state"


@dataclass(frozen=True)
class Bar:
    ts: datetime
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class Params:
    stop_points: float
    target_points: float
    exit_bars: int
    short_lookback: int = 10
    long_lookback: int = 20
    short_threshold: float = 1.6
    long_threshold: float = 0.8


def parse_ts(raw: str) -> datetime:
    value = raw.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def load_bars(path: Path, symbol: str, session_start: time, session_end: time) -> list[Bar]:
    bars: list[Bar] = []
    with path.open(newline="") as fh:
        for row in csv.DictReader(fh):
            if row.get("symbol") != symbol:
                continue
            ts = parse_ts(row["ts"])
            if not (session_start <= ts.time() <= session_end):
                continue
            try:
                bars.append(Bar(
                    ts=ts,
                    symbol=symbol,
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row.get("volume") or 0),
                ))
            except (KeyError, ValueError):
                continue
    return sorted(bars, key=lambda bar: bar.ts)


def unique_dates(bars: list[Bar]) -> list[str]:
    return sorted({bar.ts.date().isoformat() for bar in bars})


def rolling_windows(dates: list[str], train_days: int, test_days: int, embargo_days: int, max_windows: int) -> list[dict]:
    windows: list[dict] = []
    span = train_days + embargo_days + test_days
    for start in range(0, max(0, len(dates) - span + 1), test_days):
        train = dates[start:start + train_days]
        embargo = dates[start + train_days:start + train_days + embargo_days]
        test = dates[start + train_days + embargo_days:start + span]
        if len(train) == train_days and len(test) == test_days:
            windows.append({
                "trainStart": train[0],
                "trainEnd": train[-1],
                "embargoDates": embargo,
                "testStart": test[0],
                "testEnd": test[-1],
            })
    return windows[-max_windows:] if max_windows > 0 else windows


def stdev(values: list[float]) -> float:
    return statistics.pstdev(values) if len(values) >= 2 else 0.0


def summarize(rs: list[float]) -> dict:
    wins = [value for value in rs if value > 0]
    losses = [value for value in rs if value <= 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for value in rs:
        equity += value
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    avg = sum(rs) / len(rs) if rs else 0.0
    std = statistics.pstdev(rs) if len(rs) >= 2 else 0.0
    return {
        "trades": len(rs),
        "wins": len(wins),
        "losses": len(losses),
        "winRate": round(len(wins) / len(rs), 4) if rs else 0.0,
        "netR": round(sum(rs), 4),
        "avgR": round(avg, 4),
        "profitFactor": round(gross_win / gross_loss, 4) if gross_loss > 0 else (999.0 if gross_win > 0 else 0.0),
        "sharpePerTrade": round(avg / std, 4) if std > 0 else 0.0,
        "maxDrawdownR": round(max_dd, 4),
    }


def close_trade(side: int, entry: float, exit_price: float, params: Params, contracts: int, mult: float, commission: float) -> float:
    gross_points = (exit_price - entry) * side
    net_dollars = gross_points * mult * contracts - (2 * commission * contracts)
    risk_dollars = max(0.01, params.stop_points * mult * contracts)
    return net_dollars / risk_dollars


def simulate(bars: list[Bar], entry_start: str, entry_end: str, params: Params, contracts: int, mult: float, commission: float, signal_mode: str) -> dict:
    rs: list[float] = []
    trades: list[dict] = []
    position: dict | None = None
    pending_side = 0

    for idx, bar in enumerate(bars):
        day = bar.ts.date().isoformat()

        if pending_side and position is None:
            position = {
                "side": pending_side,
                "entry": bar.open,
                "entryIdx": idx,
                "entryTs": bar.ts.isoformat(),
            }
            pending_side = 0

        if position is not None:
            side = int(position["side"])
            entry = float(position["entry"])
            bars_held = idx - int(position["entryIdx"])
            stop = entry - params.stop_points if side == 1 else entry + params.stop_points
            target = entry + params.target_points if side == 1 else entry - params.target_points
            exit_price = None
            reason = ""

            if side == 1:
                hit_stop = bar.low <= stop
                hit_target = bar.high >= target
            else:
                hit_stop = bar.high >= stop
                hit_target = bar.low <= target

            if hit_stop and hit_target:
                exit_price = stop
                reason = "both_hit_stop_first"
            elif hit_stop:
                exit_price = stop
                reason = "stop"
            elif hit_target:
                exit_price = target
                reason = "target"
            elif bars_held >= params.exit_bars:
                exit_price = bar.close
                reason = "time_exit"
            elif idx == len(bars) - 1:
                exit_price = bar.close
                reason = "forced_end"

            if exit_price is not None:
                r = close_trade(side, entry, exit_price, params, contracts, mult, commission)
                rs.append(r)
                trades.append({
                    "entryTs": position["entryTs"],
                    "exitTs": bar.ts.isoformat(),
                    "side": "long" if side == 1 else "short",
                    "entry": round(entry, 4),
                    "exit": round(exit_price, 4),
                    "r": round(r, 4),
                    "reason": reason,
                })
                position = None
                continue

        if position is not None or pending_side:
            continue
        if not (entry_start <= day <= entry_end):
            continue
        if idx + 1 >= len(bars) or idx < params.long_lookback:
            continue

        closes = [item.close for item in bars]
        short_vol = stdev(closes[idx - params.short_lookback + 1:idx + 1])
        long_vol = stdev(closes[idx - params.long_lookback + 1:idx + 1])
        if long_vol <= 0 or not math.isfinite(long_vol):
            continue
        ratio = short_vol / long_vol
        if ratio >= params.short_threshold:
            pending_side = -1
        elif ratio <= params.long_threshold:
            pending_side = 1
        if pending_side and signal_mode == "inverse":
            pending_side *= -1

    return {
        **summarize(rs),
        "tradesDetail": trades,
    }


def score_train(summary: dict) -> float:
    if summary["trades"] < 8:
        return -999.0
    return float(summary["netR"]) + float(summary["profitFactor"]) * 0.25 - float(summary["maxDrawdownR"]) * 0.5


def parse_list(raw: str, cast):
    return [cast(item.strip()) for item in raw.split(",") if item.strip()]


def run(args) -> dict:
    bars = load_bars(Path(args.csv), args.symbol, time.fromisoformat(args.session_start), time.fromisoformat(args.session_end))
    dates = unique_dates(bars)
    windows = rolling_windows(dates, args.train_days, args.test_days, args.embargo_days, args.max_windows)
    grid = [
        Params(stop, target, args.exit_bars)
        for stop in parse_list(args.stop_points, float)
        for target in parse_list(args.target_points, float)
    ]

    window_rows = []
    all_oos_rs: list[float] = []
    for index, window in enumerate(windows, start=1):
        train_rows = []
        for params in grid:
            train = simulate(bars, window["trainStart"], window["trainEnd"], params, args.contracts, args.mult, args.commission, args.signal_mode)
            train_rows.append((score_train(train), params, train))
        train_rows.sort(key=lambda item: item[0], reverse=True)
        _, selected, train_summary = train_rows[0]
        test_summary = simulate(bars, window["testStart"], window["testEnd"], selected, args.contracts, args.mult, args.commission, args.signal_mode)
        all_oos_rs.extend([float(trade["r"]) for trade in test_summary["tradesDetail"]])
        window_rows.append({
            "window": index,
            **window,
            "selected": {
                "stopPoints": selected.stop_points,
                "targetPoints": selected.target_points,
                "exitBars": selected.exit_bars,
                "shortLookback": selected.short_lookback,
                "longLookback": selected.long_lookback,
                "shortThreshold": selected.short_threshold,
                "longThreshold": selected.long_threshold,
            },
            "train": {key: value for key, value in train_summary.items() if key != "tradesDetail"},
            "test": {key: value for key, value in test_summary.items() if key != "tradesDetail"},
        })

    profitable = sum(1 for row in window_rows if row["test"]["netR"] > 0)
    aggregate = summarize(all_oos_rs)
    blockers = []
    if len(windows) < 3:
        blockers.append("fewer than 3 OOS windows")
    if profitable / max(1, len(windows)) < 0.67:
        blockers.append("profitable OOS window ratio below 67%")
    if aggregate["trades"] < 20:
        blockers.append("OOS trade count below 20")
    if aggregate["netR"] <= 0:
        blockers.append("aggregate OOS netR is not positive")
    if aggregate["profitFactor"] < 1.25:
        blockers.append("aggregate OOS profit factor below 1.25")
    if aggregate["avgR"] <= 0:
        blockers.append("aggregate OOS expectancy is not positive")

    return {
        "command": "vol-regime-oos-replay",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "researchOnly": True,
        "writesOrders": False,
        "strategy": "wq-vol-regime-60m",
        "signalMode": args.signal_mode,
        "csvPath": str(Path(args.csv).resolve()),
        "inputs": vars(args),
        "windows": window_rows,
        "aggregateOos": aggregate,
        "profitableWindows": profitable,
        "windowsEvaluated": len(windows),
        "status": "candidate-needs-shadow" if not blockers else "reject-current-oos",
        "blockers": blockers,
        "decision": "Research-only. Never route from this artifact; require live-readiness and daily approval.",
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Research-only purged OOS replay for NQ 60m vol-regime.")
    parser.add_argument("--csv", default="data/free/ALL-6MARKETS-60m-60d-normalized.csv")
    parser.add_argument("--symbol", default="NQ")
    parser.add_argument("--session-start", default="14:30")
    parser.add_argument("--session-end", default="21:00")
    parser.add_argument("--train-days", type=int, default=20)
    parser.add_argument("--test-days", type=int, default=5)
    parser.add_argument("--embargo-days", type=int, default=1)
    parser.add_argument("--max-windows", type=int, default=6)
    parser.add_argument("--contracts", type=int, default=1)
    parser.add_argument("--stop-points", default="8,12,16,20")
    parser.add_argument("--target-points", default="12,16,24,32")
    parser.add_argument("--exit-bars", type=int, default=8)
    parser.add_argument("--mult", type=float, default=2.0)
    parser.add_argument("--commission", type=float, default=0.74)
    parser.add_argument("--signal-mode", choices=["normal", "inverse"], default="normal")
    parser.add_argument("--output", default=str(STATE_DIR / "vol-regime-oos-replay.latest.json"))
    args = parser.parse_args(list(argv) if argv is not None else None)

    payload = run(args)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps({
        "wrote": str(out),
        "status": payload["status"],
        "windowsEvaluated": payload["windowsEvaluated"],
        "aggregateOos": payload["aggregateOos"],
        "blockers": payload["blockers"],
        "researchOnly": payload["researchOnly"],
        "writesOrders": payload["writesOrders"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
