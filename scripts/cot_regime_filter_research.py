#!/usr/bin/env python3
"""Research-only replay of CFTC/TFF positioning as a futures regime filter.

The goal is deliberately narrow: keep the existing Backtrader strategy
families and parameters fixed, then add only one weekly COT positioning gate.
This script has no broker imports, no credentials, and no order side effects.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import backtrader as bt

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import backtrader_research_loop as btloop
from scripts.cftc_tff_positioning_ingest import MARKETS, classify_regime


STATE_DIR = ROOT / ".rumbling-hedge" / "state"
RESEARCH_DIR = ROOT / ".rumbling-hedge" / "research" / "cot"
RESULT_DIR = RESEARCH_DIR / "results"
DEFAULT_COT_CSV = RESEARCH_DIR / "tff-current-core-futures.csv"
DEFAULT_OUTPUT = STATE_DIR / "cot-regime-filter-research.latest.json"

COT_PARAMS = (
    ("cot_regimes", {}),
    ("cot_policy", "block-opposite-extreme"),
)


@dataclass(frozen=True)
class CotRegime:
    reportDate: str
    availableDate: str
    regime: str
    dealerNetPct: float
    leveragedMoneyNetPct: float
    dealerZ52: float
    leveragedMoneyZ52: float


def parse_cot_date(value: str | None) -> date | None:
    if not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    if text.endswith(".000"):
        text = text[:-4]
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        try:
            return datetime.strptime(text[:10], "%Y-%m-%d").date()
        except ValueError:
            return None


def parse_bar_datetime(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def row_value(row: dict[str, Any], *keys: str) -> str | None:
    lowered = {str(key).lower(): value for key, value in row.items()}
    for key in keys:
        value = row.get(key)
        if value not in (None, "", "."):
            return str(value)
        value = lowered.get(key.lower())
        if value not in (None, "", "."):
            return str(value)
    return None


def as_float(row: dict[str, Any], *keys: str) -> float:
    value = row_value(row, *keys)
    if value in (None, "", "."):
        return 0.0
    try:
        out = float(str(value).replace(",", "").strip())
        return out if math.isfinite(out) else 0.0
    except ValueError:
        return 0.0


def net_pct(row: dict[str, Any], long_keys: tuple[str, ...], short_keys: tuple[str, ...]) -> float:
    open_interest = as_float(row, "open_interest_all", "Open_Interest_All")
    if open_interest <= 0:
        return 0.0
    return (as_float(row, *long_keys) - as_float(row, *short_keys)) / open_interest * 100.0


def rolling_z(values: list[float]) -> float:
    if len(values) < 5:
        return 0.0
    std = statistics.stdev(values)
    if std == 0:
        return 0.0
    return (values[-1] - statistics.mean(values)) / std


def contract_name(row: dict[str, Any]) -> str:
    return row_value(row, "contract_market_name", "Market_and_Exchange_Names") or ""


def read_cot_regimes(path: Path, symbol: str, release_lag_days: int) -> list[CotRegime]:
    target = MARKETS.get(symbol)
    if not target:
        raise ValueError(f"unsupported COT symbol: {symbol}")
    if not path.exists():
        raise FileNotFoundError(path)

    with path.open(newline="") as fh:
        rows = list(csv.DictReader(fh))

    filtered: list[tuple[date, dict[str, Any]]] = []
    for row in rows:
        name = contract_name(row)
        if target not in name:
            continue
        report_date = parse_cot_date(row_value(row, "report_date_as_yyyy_mm_dd", "Report_Date_as_YYYY-MM-DD"))
        if report_date is None:
            continue
        filtered.append((report_date, row))
    filtered.sort(key=lambda item: item[0])

    regimes: list[CotRegime] = []
    dealer_series: list[float] = []
    lev_series: list[float] = []
    for report_date, row in filtered:
        dealer = net_pct(
            row,
            ("dealer_positions_long_all", "Dealer_Positions_Long_All"),
            ("dealer_positions_short_all", "Dealer_Positions_Short_All"),
        )
        leveraged = net_pct(
            row,
            ("lev_money_positions_long", "lev_money_positions_long_all", "Lev_Money_Positions_Long_All"),
            ("lev_money_positions_short", "lev_money_positions_short_all", "Lev_Money_Positions_Short_All"),
        )
        dealer_series.append(dealer)
        lev_series.append(leveraged)
        dealer_window = dealer_series[-52:]
        lev_window = lev_series[-52:]
        dealer_z = rolling_z(dealer_window)
        lev_z = rolling_z(lev_window)
        regimes.append(CotRegime(
            reportDate=report_date.isoformat(),
            availableDate=(report_date + timedelta(days=release_lag_days)).isoformat(),
            regime=classify_regime(dealer_z, lev_z),
            dealerNetPct=round(dealer, 4),
            leveragedMoneyNetPct=round(leveraged, 4),
            dealerZ52=round(dealer_z, 4),
            leveragedMoneyZ52=round(lev_z, 4),
        ))
    return regimes


def latest_regime_for(bar_date: date, regimes: list[CotRegime]) -> CotRegime | None:
    selected: CotRegime | None = None
    for regime in regimes:
        available = date.fromisoformat(regime.availableDate)
        if available <= bar_date:
            selected = regime
        else:
            break
    return selected


def feed_date_map(feed_path: Path, regimes: list[CotRegime]) -> dict[str, dict[str, Any]]:
    mapped: dict[str, dict[str, Any]] = {}
    with feed_path.open(newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            dt = datetime.strptime(row["datetime"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            key = dt.date().isoformat()
            if key in mapped:
                continue
            regime = latest_regime_for(dt.date(), regimes)
            if regime is not None:
                mapped[key] = asdict(regime)
    return mapped


def policy_allows(regime: dict[str, Any] | None, side: int, policy: str) -> bool:
    if not regime:
        return policy != "align-extreme-only"

    name = str(regime.get("regime") or "neutral-positioning")
    dealer_z = float(regime.get("dealerZ52") or 0.0)
    leveraged_z = float(regime.get("leveragedMoneyZ52") or 0.0)
    risk_on = (
        name in {"risk-on-confirmed-by-leveraged-money", "dealer-short-contrarian-support"}
        or (dealer_z <= -1.5 and leveraged_z >= 0.0)
    )
    risk_off = (
        name in {"risk-off-confirmed-by-leveraged-money", "dealer-long-contrarian-resistance"}
        or (dealer_z >= 1.5 and leveraged_z <= 0.0)
    )

    if policy == "block-opposite-extreme":
        if side > 0:
            return not risk_off
        return not risk_on
    if policy == "align-extreme-only":
        return risk_on if side > 0 else risk_off
    raise ValueError(f"unknown COT policy: {policy}")


def make_cot_strategy(base_cls: type[bt.Strategy]) -> type[bt.Strategy]:
    class COTGatedStrategy(base_cls):
        params = COT_PARAMS

        def __init__(self):
            super().__init__()
            self.cot_blocked_long = 0
            self.cot_blocked_short = 0
            self.cot_allowed_long = 0
            self.cot_allowed_short = 0

        def current_cot_regime(self) -> dict[str, Any] | None:
            dt = bt.num2date(self.data.datetime[0]).date().isoformat()
            return (self.p.cot_regimes or {}).get(dt)

        def enter_long(self) -> None:
            if policy_allows(self.current_cot_regime(), 1, self.p.cot_policy):
                self.cot_allowed_long += 1
                super().enter_long()
            else:
                self.cot_blocked_long += 1

        def enter_short(self) -> None:
            if policy_allows(self.current_cot_regime(), -1, self.p.cot_policy):
                self.cot_allowed_short += 1
                super().enter_short()
            else:
                self.cot_blocked_short += 1

    COTGatedStrategy.__name__ = f"COTGated{base_cls.__name__}"
    return COTGatedStrategy


def run_cot_one(
    spec: btloop.StrategySpec,
    feed_path: Path,
    cot_map: dict[str, dict[str, Any]],
    policy: str,
    contracts: int,
    stop_points: float,
    target_points: float,
    mult: float,
    commission: float,
    cash: float,
) -> dict[str, Any]:
    cerebro = bt.Cerebro(stdstats=False)
    cerebro.adddata(btloop.data_feed(feed_path, spec.timeframe_minutes))
    cerebro.addstrategy(
        make_cot_strategy(spec.strategy_class),
        cot_regimes=cot_map,
        cot_policy=policy,
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
        "closedTrades": total,
        "won": won,
        "lost": lost,
        "winRate": round(won / total, 4) if total else 0.0,
        "pnlDollars": round(pnl, 2),
        "totalR": round(pnl / risk_dollars, 4),
        "avgR": round((pnl / risk_dollars) / total, 4) if total else 0.0,
        "maxDrawdownPct": round(float(strat.analyzers.drawdown.get_analysis().get("max", {}).get("drawdown", 0) or 0), 4),
        "cotBlockedLong": int(getattr(strat, "cot_blocked_long", 0)),
        "cotBlockedShort": int(getattr(strat, "cot_blocked_short", 0)),
        "cotAllowedLong": int(getattr(strat, "cot_allowed_long", 0)),
        "cotAllowedShort": int(getattr(strat, "cot_allowed_short", 0)),
    }


def parse_list(raw: str, cast):
    return [cast(part.strip()) for part in raw.split(",") if part.strip()]


def coverage_summary(feeds: dict[str, str], cot_maps: dict[str, dict[str, dict[str, Any]]], regimes: list[CotRegime]) -> dict[str, Any]:
    feed_dates: set[str] = set()
    mapped_dates: set[str] = set()
    regimes_seen: dict[str, int] = {}
    for strategy_id, feed in feeds.items():
        with Path(feed).open(newline="") as fh:
            for row in csv.DictReader(fh):
                dt = datetime.strptime(row["datetime"], "%Y-%m-%d %H:%M:%S").date().isoformat()
                feed_dates.add(dt)
        for item in cot_maps.get(strategy_id, {}).values():
            mapped_dates.add(str(item.get("availableDate")))
            name = str(item.get("regime") or "missing")
            regimes_seen[name] = regimes_seen.get(name, 0) + 1
    return {
        "cotRecords": len(regimes),
        "feedTradingDates": len(feed_dates),
        "mappedTradingDates": len({key for mapping in cot_maps.values() for key in mapping.keys()}),
        "unmappedTradingDates": max(0, len(feed_dates) - len({key for mapping in cot_maps.values() for key in mapping.keys()})),
        "latestReportDate": regimes[-1].reportDate if regimes else None,
        "latestAvailableDate": regimes[-1].availableDate if regimes else None,
        "releaseLagDays": None,
        "regimeObservations": regimes_seen,
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc)
    session_start = time.fromisoformat(args.session_start)
    session_end = time.fromisoformat(args.session_end)
    contracts = parse_list(args.contracts, int)
    stops = parse_list(args.stop_points, float)
    targets = parse_list(args.target_points, float)
    policies = parse_list(args.policies, str)
    regimes = read_cot_regimes(Path(args.cot_csv), args.symbol, args.release_lag_days)

    feeds: dict[str, str] = {}
    cot_maps: dict[str, dict[str, dict[str, Any]]] = {}
    rows: list[dict[str, Any]] = []
    for spec in btloop.default_specs():
        if not spec.csv_path.exists():
            rows.append({
                "strategy": spec.strategy_id,
                "error": f"missing csv: {spec.csv_path}",
                "researchOnly": True,
            })
            continue
        feed_path = btloop.ny_session_filter(spec.csv_path, args.symbol, session_start, session_end)
        feeds[spec.strategy_id] = str(feed_path)
        cot_map = feed_date_map(feed_path, regimes)
        cot_maps[spec.strategy_id] = cot_map
        for contract_count in contracts:
            for stop_points in stops:
                for target_points in targets:
                    base = btloop.run_one(
                        spec,
                        feed_path,
                        contract_count,
                        stop_points,
                        target_points,
                        args.mult,
                        args.commission,
                        args.cash,
                    )
                    for policy in policies:
                        filtered = run_cot_one(
                            spec,
                            feed_path,
                            cot_map,
                            policy,
                            contract_count,
                            stop_points,
                            target_points,
                            args.mult,
                            args.commission,
                            args.cash,
                        )
                        trade_reduction = 0.0
                        if base.get("closedTrades"):
                            trade_reduction = 1.0 - (filtered["closedTrades"] / max(1, int(base["closedTrades"])))
                        rows.append({
                            "strategy": spec.strategy_id,
                            "timeframeMinutes": spec.timeframe_minutes,
                            "policy": policy,
                            "contracts": contract_count,
                            "stopPoints": stop_points,
                            "targetPoints": target_points,
                            "baseClosedTrades": base.get("closedTrades", 0),
                            "filteredClosedTrades": filtered["closedTrades"],
                            "baseWinRate": base.get("winRate", 0.0),
                            "filteredWinRate": filtered["winRate"],
                            "baseTotalR": base.get("totalR", 0.0),
                            "filteredTotalR": filtered["totalR"],
                            "deltaTotalR": round(filtered["totalR"] - float(base.get("totalR", 0.0)), 4),
                            "baseAvgR": base.get("avgR", 0.0),
                            "filteredAvgR": filtered["avgR"],
                            "deltaAvgR": round(filtered["avgR"] - float(base.get("avgR", 0.0)), 4),
                            "baseMaxDrawdownPct": base.get("maxDrawdownPct", 0.0),
                            "filteredMaxDrawdownPct": filtered["maxDrawdownPct"],
                            "tradeReductionPct": round(trade_reduction, 4),
                            "cotBlockedLong": filtered["cotBlockedLong"],
                            "cotBlockedShort": filtered["cotBlockedShort"],
                            "cotAllowedLong": filtered["cotAllowedLong"],
                            "cotAllowedShort": filtered["cotAllowedShort"],
                            "researchOnly": True,
                        })

    improved = [
        row for row in rows
        if not row.get("error")
        and row.get("filteredClosedTrades", 0) >= args.min_trades
        and row.get("deltaTotalR", 0.0) > 0
        and row.get("filteredTotalR", 0.0) > 0
    ]
    improved.sort(key=lambda row: (row["deltaTotalR"], row["filteredTotalR"]), reverse=True)
    coverage = coverage_summary(feeds, cot_maps, regimes)
    coverage["releaseLagDays"] = args.release_lag_days
    return {
        "command": "cot-regime-filter-research",
        "generatedAt": generated_at.isoformat(),
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "promoted_for_execution": False,
        "tradable_signal": False,
        "readyForExecution": False,
        "executionIsolation": {
            "hasBrokerCredentials": False,
            "writesOrders": False,
            "allowedOutputs": [str(STATE_DIR), str(RESEARCH_DIR), str(RESULT_DIR), str(btloop.FEED_DIR)],
        },
        "inputs": {
            "symbol": args.symbol,
            "cotCsv": str(Path(args.cot_csv).resolve()),
            "sessionUtc": f"{args.session_start}-{args.session_end}",
            "contracts": args.contracts,
            "stopPoints": args.stop_points,
            "targetPoints": args.target_points,
            "policies": policies,
            "releaseLagDays": args.release_lag_days,
            "minTradesForImprovement": args.min_trades,
            "multiplier": args.mult,
            "commission": args.commission,
            "oneVariable": "weekly CFTC TFF positioning gate",
        },
        "cotCoverage": coverage,
        "summary": {
            "rows": len(rows),
            "improvedPositiveRows": len(improved),
            "decision": "research-only-retain-for-oos-review" if improved else "research-only-no-positive-full-sample-improvement",
            "promotionGate": (
                "No promotion from this artifact. Requires purged OOS, walk-forward, cost/slippage, "
                "data freshness, source cleanliness, and explicit daily plan approval."
            ),
            "bestImprovedRows": improved[:5],
        },
        "feeds": feeds,
        "results": sorted(rows, key=lambda row: (str(row.get("strategy")), str(row.get("policy")), -float(row.get("deltaTotalR", 0.0)))),
    }


def write_outputs(report: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    generated = str(report["generatedAt"]).replace(":", "").replace("+", "Z")
    csv_path = RESULT_DIR / f"cot-regime-filter-research-{generated}.csv"
    rows = report.get("results") if isinstance(report.get("results"), list) else []
    if rows:
        fieldnames = sorted({key for row in rows for key in row.keys()})
        with csv_path.open("w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
    report["csvPath"] = str(csv_path)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Research-only COT regime filter replay for futures strategies.")
    parser.add_argument("--symbol", default="NQ")
    parser.add_argument("--cot-csv", default=str(DEFAULT_COT_CSV))
    parser.add_argument("--session-start", default="14:30")
    parser.add_argument("--session-end", default="21:00")
    parser.add_argument("--contracts", default="1")
    parser.add_argument("--stop-points", default="12,16,20")
    parser.add_argument("--target-points", default="16,24,32")
    parser.add_argument("--policies", default="block-opposite-extreme,align-extreme-only")
    parser.add_argument("--release-lag-days", type=int, default=3)
    parser.add_argument("--min-trades", type=int, default=10)
    parser.add_argument("--mult", type=float, default=2.0)
    parser.add_argument("--commission", type=float, default=0.74)
    parser.add_argument("--cash", type=float, default=100000.0)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(list(argv) if argv is not None else None)

    report = build_report(args)
    write_outputs(report, Path(args.output))
    print(json.dumps({
        "researchOnly": report["researchOnly"],
        "readyForExecution": report["readyForExecution"],
        "rows": report["summary"]["rows"],
        "improvedPositiveRows": report["summary"]["improvedPositiveRows"],
        "decision": report["summary"]["decision"],
        "json": str(Path(args.output)),
        "csv": report.get("csvPath"),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
