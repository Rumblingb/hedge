#!/usr/bin/env python3
"""
Research-only Backtrader harness for Bill/Hermes futures strategy testing.

This script intentionally has no broker credentials, no Topstep imports, and no
order-routing side effects. It converts the existing normalized CSVs into
session-filtered Backtrader feeds, runs controlled stop/target/size sweeps, and
writes artifacts for the research loop to review.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import dataclass
from datetime import datetime, time, timezone
from pathlib import Path
from typing import Iterable

import backtrader as bt


ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / ".rumbling-hedge" / "state"
WORK_DIR = ROOT / ".rumbling-hedge" / "backtrader"
FEED_DIR = WORK_DIR / "feeds"
RESULT_DIR = WORK_DIR / "results"


@dataclass(frozen=True)
class StrategySpec:
    strategy_id: str
    strategy_class: type[bt.Strategy]
    csv_path: Path
    timeframe_minutes: int
    params: dict[str, float | int]


BASE_PARAMS = (
    ("contracts", 1),
    ("stop_points", 16.0),
    ("target_points", 24.0),
    ("exit_bars", 8),
    ("risk_dollars_per_contract", 32.0),
)


def parse_list(raw: str, cast):
    return [cast(part.strip()) for part in raw.split(",") if part.strip()]


def parse_ts(raw: str) -> datetime:
    value = raw.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def ny_session_filter(csv_path: Path, symbol: str, start: time, end: time) -> Path:
    FEED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = FEED_DIR / f"{csv_path.stem}.{symbol}.{start.strftime('%H%M')}-{end.strftime('%H%M')}.bt.csv"
    with csv_path.open(newline="") as src, out_path.open("w", newline="") as dst:
        reader = csv.DictReader(src)
        writer = csv.writer(dst)
        writer.writerow(["datetime", "open", "high", "low", "close", "volume"])
        for row in reader:
            if row.get("symbol") != symbol:
                continue
            dt = parse_ts(row["ts"])
            if not (start <= dt.time() <= end):
                continue
            writer.writerow([
                dt.strftime("%Y-%m-%d %H:%M:%S"),
                row["open"],
                row["high"],
                row["low"],
                row["close"],
                row.get("volume", "0") or "0",
            ])
    return out_path


class ResearchBase(bt.Strategy):
    params = BASE_PARAMS

    def __init__(self):
        self.entry_order = None
        self.stop_order = None
        self.target_order = None
        self.entry_bar = None
        self.entry_side = 0
        self.last_trade_date = None

    def can_enter(self) -> bool:
        return not self.position and self.entry_order is None and self.stop_order is None and self.target_order is None

    def enter_long(self) -> None:
        if self.can_enter():
            self.entry_order = self.buy(size=self.p.contracts)
            self.entry_side = 1

    def enter_short(self) -> None:
        if self.can_enter():
            self.entry_order = self.sell(size=self.p.contracts)
            self.entry_side = -1

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status == order.Completed and order == self.entry_order:
            self.entry_order = None
            self.entry_bar = len(self)
            entry = order.executed.price
            size = abs(order.executed.size)
            if order.isbuy():
                stop = entry - float(self.p.stop_points)
                target = entry + float(self.p.target_points)
                self.stop_order = self.sell(size=size, exectype=bt.Order.Stop, price=stop)
                self.target_order = self.sell(size=size, exectype=bt.Order.Limit, price=target, oco=self.stop_order)
            else:
                stop = entry + float(self.p.stop_points)
                target = entry - float(self.p.target_points)
                self.stop_order = self.buy(size=size, exectype=bt.Order.Stop, price=stop)
                self.target_order = self.buy(size=size, exectype=bt.Order.Limit, price=target, oco=self.stop_order)
            return

        if order.status == order.Completed and order in [self.stop_order, self.target_order]:
            self.stop_order = None
            self.target_order = None
            self.entry_bar = None
            self.entry_side = 0
            return

        if order.status in [order.Canceled, order.Margin, order.Rejected]:
            if order == self.entry_order:
                self.entry_order = None
                self.entry_side = 0
            if order == self.stop_order:
                self.stop_order = None
            if order == self.target_order:
                self.target_order = None

    def time_exit_if_needed(self) -> bool:
        if not self.position or self.entry_bar is None:
            return False
        if len(self) - self.entry_bar < int(self.p.exit_bars):
            return False
        for order in [self.stop_order, self.target_order]:
            if order is not None:
                self.cancel(order)
        self.stop_order = None
        self.target_order = None
        self.close()
        self.entry_bar = None
        self.entry_side = 0
        return True


class ORBBreakout(ResearchBase):
    params = BASE_PARAMS + (
        ("range_window", 8),
        ("volume_threshold", 1.3),
        ("volume_lookback", 10),
    )

    def __init__(self):
        super().__init__()
        self.session_date = None
        self.session_count = 0
        self.range_high = None
        self.range_low = None
        self.volumes: list[float] = []

    def next(self):
        if self.time_exit_if_needed():
            return

        dt = bt.num2date(self.data.datetime[0]).date()
        if dt != self.session_date:
            self.session_date = dt
            self.session_count = 0
            self.range_high = None
            self.range_low = None
            self.volumes = []

        self.session_count += 1
        volume = float(self.data.volume[0] or 0)
        self.volumes.append(volume)
        if len(self.volumes) > int(self.p.volume_lookback):
            self.volumes.pop(0)

        if self.session_count <= int(self.p.range_window):
            high = float(self.data.high[0])
            low = float(self.data.low[0])
            self.range_high = high if self.range_high is None else max(self.range_high, high)
            self.range_low = low if self.range_low is None else min(self.range_low, low)
            return

        if not self.can_enter() or self.last_trade_date == dt:
            return
        if not self.range_high or not self.range_low or len(self.volumes) < 2:
            return

        avg_vol = sum(self.volumes[:-1]) / max(1, len(self.volumes) - 1)
        if avg_vol <= 0 or volume < avg_vol * float(self.p.volume_threshold):
            return

        close = float(self.data.close[0])
        if close > self.range_high:
            self.last_trade_date = dt
            self.enter_long()
        elif close < self.range_low:
            self.last_trade_date = dt
            self.enter_short()


class WQTrendMomentum(ResearchBase):
    params = BASE_PARAMS + (
        ("short_sma", 20),
        ("long_sma", 60),
        ("volume_threshold", 1.3),
        ("volume_lookback", 20),
    )

    def __init__(self):
        super().__init__()
        self.fast = bt.ind.SMA(self.data.close, period=int(self.p.short_sma))
        self.slow = bt.ind.SMA(self.data.close, period=int(self.p.long_sma))
        self.vol_sma = bt.ind.SMA(self.data.volume, period=int(self.p.volume_lookback))

    def next(self):
        if self.time_exit_if_needed() or not self.can_enter():
            return
        if not math.isfinite(float(self.vol_sma[0])) or float(self.vol_sma[0]) <= 0:
            return
        if float(self.data.volume[0]) < float(self.vol_sma[0]) * float(self.p.volume_threshold):
            return
        if self.fast[0] > self.slow[0]:
            self.enter_long()
        elif self.fast[0] < self.slow[0]:
            self.enter_short()


class WQVolRegime(ResearchBase):
    params = BASE_PARAMS + (
        ("short_lookback", 10),
        ("long_lookback", 20),
        ("short_threshold", 1.6),
        ("long_threshold", 0.8),
    )

    def __init__(self):
        super().__init__()
        self.short_vol = bt.ind.StdDev(self.data.close, period=int(self.p.short_lookback))
        self.long_vol = bt.ind.StdDev(self.data.close, period=int(self.p.long_lookback))

    def next(self):
        if self.time_exit_if_needed() or not self.can_enter():
            return
        long_vol = float(self.long_vol[0])
        if not math.isfinite(long_vol) or long_vol <= 0:
            return
        ratio = float(self.short_vol[0]) / long_vol
        if ratio >= float(self.p.short_threshold):
            self.enter_short()
        elif ratio <= float(self.p.long_threshold):
            self.enter_long()


def data_feed(path: Path, timeframe_minutes: int):
    return bt.feeds.GenericCSVData(
        dataname=str(path),
        dtformat="%Y-%m-%d %H:%M:%S",
        datetime=0,
        open=1,
        high=2,
        low=3,
        close=4,
        volume=5,
        openinterest=-1,
        header=1,
        timeframe=bt.TimeFrame.Minutes,
        compression=timeframe_minutes,
    )


def run_one(spec: StrategySpec, feed_path: Path, contracts: int, stop_points: float, target_points: float, mult: float, commission: float, cash: float):
    cerebro = bt.Cerebro(stdstats=False)
    cerebro.adddata(data_feed(feed_path, spec.timeframe_minutes))
    cerebro.addstrategy(
        spec.strategy_class,
        contracts=contracts,
        stop_points=stop_points,
        target_points=target_points,
        exit_bars=int(spec.params.get("exit_bars", 8)),
        risk_dollars_per_contract=max(0.01, stop_points * mult),
        **{k: v for k, v in spec.params.items() if k != "exit_bars"},
    )
    cerebro.broker.setcash(cash)
    cerebro.broker.setcommission(
        commission=commission,
        margin=1000.0,
        mult=mult,
        commtype=bt.CommInfoBase.COMM_FIXED,
        stocklike=False,
    )
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    start_value = cerebro.broker.getvalue()
    results = cerebro.run()
    end_value = cerebro.broker.getvalue()
    strat = results[0]
    trades = strat.analyzers.trades.get_analysis()
    total = int(trades.get("total", {}).get("closed", 0) or 0)
    won = int(trades.get("won", {}).get("total", 0) or 0)
    lost = int(trades.get("lost", {}).get("total", 0) or 0)
    pnl = end_value - start_value
    risk_dollars = max(0.01, contracts * stop_points * mult)
    return {
        "strategy": spec.strategy_id,
        "timeframeMinutes": spec.timeframe_minutes,
        "contracts": contracts,
        "stopPoints": stop_points,
        "targetPoints": target_points,
        "closedTrades": total,
        "won": won,
        "lost": lost,
        "winRate": round(won / total, 4) if total else 0.0,
        "pnlDollars": round(pnl, 2),
        "totalR": round(pnl / risk_dollars, 4),
        "avgR": round((pnl / risk_dollars) / total, 4) if total else 0.0,
        "maxDrawdownPct": round(float(strat.analyzers.drawdown.get_analysis().get("max", {}).get("drawdown", 0) or 0), 4),
        "researchOnly": True,
    }


def default_specs() -> list[StrategySpec]:
    free = ROOT / "data" / "free"
    return [
        StrategySpec(
            "orb-breakout-15m",
            ORBBreakout,
            free / "ALL-6MARKETS-15m-60d-normalized.csv",
            15,
            {"range_window": 8, "volume_threshold": 1.3, "exit_bars": 8},
        ),
        StrategySpec(
            "orb-breakout-30m",
            ORBBreakout,
            free / "ALL-6MARKETS-30m-60d-normalized.csv",
            30,
            {"range_window": 8, "volume_threshold": 1.3, "exit_bars": 8},
        ),
        StrategySpec(
            "wq-trend-mom-30m",
            WQTrendMomentum,
            free / "ALL-6MARKETS-30m-60d-normalized.csv",
            30,
            {"short_sma": 20, "long_sma": 60, "volume_threshold": 1.3, "exit_bars": 8},
        ),
        StrategySpec(
            "wq-vol-regime-60m",
            WQVolRegime,
            free / "ALL-6MARKETS-60m-60d-normalized.csv",
            60,
            {"short_lookback": 10, "long_lookback": 20, "short_threshold": 1.6, "long_threshold": 0.8, "exit_bars": 8},
        ),
    ]


def write_outputs(results: list[dict], feeds: dict[str, str], args) -> Path:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).isoformat()
    payload = {
        "command": "backtrader-research-loop",
        "generatedAt": generated_at,
        "researchOnly": True,
        "executionIsolation": {
            "hasBrokerCredentials": False,
            "writesOrders": False,
            "allowedOutputs": [str(STATE_DIR), str(RESULT_DIR), str(FEED_DIR)],
        },
        "inputs": {
            "symbol": args.symbol,
            "sessionUtc": f"{args.session_start}-{args.session_end}",
            "contracts": args.contracts,
            "stopPoints": args.stop_points,
            "targetPoints": args.target_points,
            "multiplier": args.mult,
            "commission": args.commission,
        },
        "feeds": feeds,
        "results": sorted(results, key=lambda row: (row["strategy"], -row["totalR"])),
    }
    latest = STATE_DIR / "backtrader-research.latest.json"
    latest.write_text(json.dumps(payload, indent=2) + "\n")

    csv_path = RESULT_DIR / f"backtrader-research-{generated_at.replace(':', '').replace('+', 'Z')}.csv"
    if results:
        with csv_path.open("w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(results[0].keys()))
            writer.writeheader()
            writer.writerows(results)
    payload["csvPath"] = str(csv_path)
    latest.write_text(json.dumps(payload, indent=2) + "\n")
    return latest


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run research-only Backtrader sweeps for Bill futures strategies.")
    parser.add_argument("--symbol", default="NQ")
    parser.add_argument("--session-start", default="14:30")
    parser.add_argument("--session-end", default="21:00")
    parser.add_argument("--contracts", default="1", help="Comma-separated contract sizes to research.")
    parser.add_argument("--stop-points", default="12,16,20", help="Comma-separated stop distances in index points.")
    parser.add_argument("--target-points", default="16,24,32", help="Comma-separated target distances in index points.")
    parser.add_argument("--mult", type=float, default=2.0, help="Dollar multiplier per point. MNQ=2, NQ=20.")
    parser.add_argument("--commission", type=float, default=0.74, help="Commission per side per contract.")
    parser.add_argument("--cash", type=float, default=100000.0)
    args = parser.parse_args(list(argv) if argv is not None else None)

    session_start = time.fromisoformat(args.session_start)
    session_end = time.fromisoformat(args.session_end)
    contracts = parse_list(args.contracts, int)
    stops = parse_list(args.stop_points, float)
    targets = parse_list(args.target_points, float)

    feeds: dict[str, str] = {}
    rows: list[dict] = []
    for spec in default_specs():
        if not spec.csv_path.exists():
            rows.append({"strategy": spec.strategy_id, "error": f"missing csv: {spec.csv_path}", "researchOnly": True})
            continue
        feed_path = ny_session_filter(spec.csv_path, args.symbol, session_start, session_end)
        feeds[spec.strategy_id] = str(feed_path)
        for contract_count in contracts:
            for stop_points in stops:
                for target_points in targets:
                    rows.append(run_one(spec, feed_path, contract_count, stop_points, target_points, args.mult, args.commission, args.cash))

    latest = write_outputs(rows, feeds, args)
    print(f"wrote {latest}")
    print(f"rows={len(rows)} research_only=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
