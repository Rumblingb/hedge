#!/usr/bin/env python3
"""Research-only fixed-rule NQ historical session replay.

Uses the best NQ historical source from the coverage audit and runs one simple
opening-range first-break rule with a chronological train/OOS split. This is a
measurement artifact, not a strategy optimizer or execution approval.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, time, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import polars as pl


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge/state"
COVERAGE = STATE / "futures-nq-historical-coverage-audit.latest.json"
OUT = STATE / "futures-nq-historical-session-replay.latest.json"
VAULT = Path.home() / "Documents/memorybrain"

UTC = ZoneInfo("UTC")
NEW_YORK = ZoneInfo("America/New_York")
NY_SESSION_START = time(9, 30)
NY_SESSION_END = time(16, 0)
FABERVAALE_EXIT = time(15, 0)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def current_utc_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def default_markdown_path() -> Path:
    return VAULT / "Agent-Hermes" / f"futures-nq-historical-session-replay-{current_utc_date()}.md"


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def as_new_york(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(NEW_YORK)


def in_ny_session(value: datetime) -> bool:
    stamp = as_new_york(value).time()
    return NY_SESSION_START <= stamp <= NY_SESSION_END


def session_date(value: datetime) -> str:
    return as_new_york(value).date().isoformat()


def load_frame(path: Path) -> pl.DataFrame:
    if path.suffix == ".parquet":
        return pl.scan_parquet(path).select(["ts", "open", "high", "low", "close", "volume"]).sort("ts").collect()
    frame = pl.scan_csv(path)
    columns = frame.collect_schema().names()
    lower_map = {column.lower(): column for column in columns}
    return (
        frame
        .select([
            pl.col(lower_map.get("ts") or lower_map.get("datetime") or "ts").str.to_datetime(strict=False, time_zone="UTC").alias("ts"),
            pl.col(lower_map.get("open", "open")).cast(pl.Float64).alias("open"),
            pl.col(lower_map.get("high", "high")).cast(pl.Float64).alias("high"),
            pl.col(lower_map.get("low", "low")).cast(pl.Float64).alias("low"),
            pl.col(lower_map.get("close", "close")).cast(pl.Float64).alias("close"),
            pl.col(lower_map.get("volume", "volume")).cast(pl.Float64).alias("volume"),
        ])
        .sort("ts")
        .collect()
    )


def choose_input(coverage: dict[str, Any], explicit: str | None) -> tuple[Path | None, dict[str, Any], list[str]]:
    if explicit:
        return Path(explicit), {"datasetId": "explicit-input", "path": explicit}, []
    best = coverage.get("bestHistoricalOosCandidate") if isinstance(coverage.get("bestHistoricalOosCandidate"), dict) else {}
    blockers: list[str] = []
    if coverage.get("decision") != "research-only-historical-nq-source-ready":
        blockers.append("historical-coverage-not-ready")
    path_text = str(best.get("path") or "")
    if not path_text:
        blockers.append("missing-best-historical-source-path")
        return None, best, blockers
    return Path(path_text), best, blockers


def replay_sessions(
    frame: pl.DataFrame,
    *,
    cadence_minutes: int,
    opening_range_minutes: int,
    cost_points: float,
    min_session_rows: int,
) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = {}
    for row in frame.to_dicts():
        ts = row["ts"]
        if isinstance(ts, datetime) and in_ny_session(ts):
            buckets.setdefault(session_date(ts), []).append(row)
    opening_bars = max(1, int(round(opening_range_minutes / cadence_minutes)))
    trades: list[dict[str, Any]] = []
    for day, rows in sorted(buckets.items()):
        rows = sorted(rows, key=lambda item: item["ts"])
        if len(rows) < max(min_session_rows, opening_bars + 2):
            continue
        opening = rows[:opening_bars]
        after = rows[opening_bars:]
        or_high = max(float(row["high"]) for row in opening)
        or_low = min(float(row["low"]) for row in opening)
        risk = or_high - or_low
        if risk <= 0:
            continue
        first_break: dict[str, Any] | None = None
        for row in after:
            high = float(row["high"])
            low = float(row["low"])
            if high > or_high:
                first_break = {"direction": "long", "ts": str(row["ts"]), "entry": or_high}
                break
            if low < or_low:
                first_break = {"direction": "short", "ts": str(row["ts"]), "entry": or_low}
                break
        if not first_break:
            continue
        close = float(rows[-1]["close"])
        if first_break["direction"] == "long":
            gross_r = (close - or_high) / risk
        else:
            gross_r = (or_low - close) / risk
        cost_r = cost_points / risk
        trades.append({
            "date": day,
            "direction": first_break["direction"],
            "breakTs": first_break["ts"],
            "openingRangePoints": round(risk, 4),
            "sessionClose": round(close, 4),
            "grossR": round(gross_r, 6),
            "costR": round(cost_r, 6),
            "netR": round(gross_r - cost_r, 6),
        })
    return trades


def replay_fabervaale_orb_sessions(
    frame: pl.DataFrame,
    *,
    cadence_minutes: int,
    opening_range_minutes: int,
    cost_points: float,
    min_session_rows: int,
) -> tuple[list[dict[str, Any]], list[str]]:
    blockers: list[str] = []
    if cadence_minutes > 5:
        blockers.append("cadence-too-coarse-for-fabervaale-5m-close")
    buckets: dict[str, list[dict[str, Any]]] = {}
    for row in frame.to_dicts():
        ts = row["ts"]
        if isinstance(ts, datetime) and in_ny_session(ts):
            buckets.setdefault(session_date(ts), []).append(row)
    opening_bars = max(1, int(round(opening_range_minutes / cadence_minutes)))
    trades: list[dict[str, Any]] = []
    for day, rows in sorted(buckets.items()):
        rows = sorted(rows, key=lambda item: item["ts"])
        if len(rows) < max(min_session_rows, opening_bars + 2):
            continue
        opening = rows[:opening_bars]
        after = rows[opening_bars:]
        or_high = max(float(row["high"]) for row in opening)
        or_low = min(float(row["low"]) for row in opening)
        risk = or_high - or_low
        if risk <= 0:
            continue
        entry_row = None
        for row in after:
            ts = row["ts"]
            if not isinstance(ts, datetime) or as_new_york(ts).time() > FABERVAALE_EXIT:
                break
            if float(row["close"]) > or_high:
                entry_row = row
                break
        if not entry_row:
            continue
        entry = or_high
        stop = or_low
        target = entry + risk
        exit_price = None
        exit_reason = "time-exit-15ny"
        for row in after[after.index(entry_row):]:
            ts = row["ts"]
            if not isinstance(ts, datetime):
                continue
            if as_new_york(ts).time() > FABERVAALE_EXIT:
                break
            low = float(row["low"])
            high = float(row["high"])
            if low <= stop and high >= target:
                exit_price = stop
                exit_reason = "ambiguous-stop-first"
                break
            if low <= stop:
                exit_price = stop
                exit_reason = "stop"
                break
            if high >= target:
                exit_price = target
                exit_reason = "target-1r"
                break
            exit_price = float(row["close"])
        if exit_price is None:
            exit_price = float(entry_row["close"])
        gross_r = (exit_price - entry) / risk
        cost_r = cost_points / risk
        trades.append({
            "date": day,
            "direction": "long",
            "breakTs": str(entry_row["ts"]),
            "openingRangePoints": round(risk, 4),
            "entry": round(entry, 4),
            "stop": round(stop, 4),
            "target": round(target, 4),
            "exitPrice": round(exit_price, 4),
            "exitReason": exit_reason,
            "grossR": round(gross_r, 6),
            "costR": round(cost_r, 6),
            "netR": round(gross_r - cost_r, 6),
        })
    return trades, blockers


def stats(trades: list[dict[str, Any]]) -> dict[str, Any]:
    net = [float(item["netR"]) for item in trades]
    wins = [value for value in net if value > 0]
    losses = [value for value in net if value <= 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    return {
        "trades": len(trades),
        "netR": round(sum(net), 6),
        "avgR": round(sum(net) / len(net), 6) if net else None,
        "winRate": round(len(wins) / len(net), 6) if net else None,
        "profitFactor": round(gross_win / gross_loss, 6) if gross_loss else (None if not gross_win else 999.0),
        "wins": len(wins),
        "losses": len(losses),
    }


def build_replay(
    *,
    coverage: dict[str, Any],
    input_path: str | None = None,
    cadence_minutes: int | None = None,
    opening_range_minutes: int = 30,
    cost_points: float = 2.0,
    train_fraction: float = 0.6,
    strategy: str = "first-break-session-close",
) -> dict[str, Any]:
    path, source, blockers = choose_input(coverage, input_path)
    if path is None or not path.exists():
        blockers.append("input-file-missing")
        trades: list[dict[str, Any]] = []
    else:
        cadence = cadence_minutes or int(source.get("cadenceMinutes") or 15)
        min_rows = 120 if cadence <= 1 else 50 if cadence <= 5 else 18
        if strategy == "fabervaale-orb":
            trades, strategy_blockers = replay_fabervaale_orb_sessions(
                load_frame(path),
                cadence_minutes=cadence,
                opening_range_minutes=opening_range_minutes,
                cost_points=cost_points,
                min_session_rows=min_rows,
            )
            blockers.extend(strategy_blockers)
        else:
            trades = replay_sessions(load_frame(path), cadence_minutes=cadence, opening_range_minutes=opening_range_minutes, cost_points=cost_points, min_session_rows=min_rows)
    split_idx = max(1, min(len(trades), int(len(trades) * train_fraction))) if trades else 0
    train = trades[:split_idx]
    oos = trades[split_idx:]
    train_stats = stats(train)
    oos_stats = stats(oos)
    if len(trades) < 20:
        blockers.append("too-few-trades-for-historical-replay")
    if oos_stats["trades"] < 10:
        blockers.append("too-few-oos-trades")
    if oos_stats["trades"] and (float(oos_stats["netR"]) <= 0 or (oos_stats["profitFactor"] or 0) < 1.2):
        blockers.append("oos-edge-below-contract-after-cost")
    decision = "research-only-historical-session-replay-blocked" if blockers else "research-only-historical-session-replay-watch"
    return {
        "command": "futures-nq-historical-session-replay",
        "generatedAt": now_iso(),
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "readyForDemoExpansion": False,
        "readyForExecution": False,
        "source": source,
        "strategy": strategy,
        "inputPath": str(path) if path else None,
        "openingRangeMinutes": opening_range_minutes,
        "costPoints": cost_points,
        "trainFraction": train_fraction,
        "tradeCount": len(trades),
        "trainStats": train_stats,
        "oosStats": oos_stats,
        "trades": trades,
        "sampleTrades": trades[:20],
        "blockers": sorted(set(blockers)),
        "decision": decision,
        "nextAction": (
            "Do not promote; choose a genuinely different feature or acquire better current data."
            if blockers
            else "Keep as research watch only; next require purged walk-forward, cost/slippage, live-data parity, and no-edge ledger review."
        ),
        "hardRules": [
            "This fixed-rule replay is not optimized and is not execution evidence.",
            "A positive OOS read cannot approve Topstep demo without current data parity, realtime freshness, and promotion gates.",
            "Do not tune opening range, costs, or split after seeing the result in this artifact.",
        ],
    }


def render_markdown(payload: dict[str, Any]) -> str:
    generated_date = str(payload.get("generatedAt") or current_utc_date())[:10]
    lines = [
        f"# Futures NQ Historical Session Replay - {generated_date}",
        "",
        "Parent hub: [[BILL-CONTROL-HUB]]",
        "",
        "Research-only fixed-rule replay. This page does not approve Topstep demo or live trading.",
        "",
        "## Summary",
        "",
        f"- Decision: `{payload.get('decision')}`",
        f"- Source: `{(payload.get('source') or {}).get('datasetId')}`",
        f"- Strategy: `{payload.get('strategy')}`",
        f"- Trades: `{payload.get('tradeCount')}`",
        f"- Train stats: `{payload.get('trainStats')}`",
        f"- OOS stats: `{payload.get('oosStats')}`",
        f"- Blockers: `{payload.get('blockers')}`",
        "",
        "## Hard Rules",
        "",
    ]
    for rule in payload.get("hardRules") or []:
        lines.append(f"- {rule}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run research-only NQ historical session replay.")
    parser.add_argument("--coverage", default=str(COVERAGE))
    parser.add_argument("--input", default="")
    parser.add_argument("--cadence-minutes", type=int, default=0)
    parser.add_argument("--opening-range-minutes", type=int, default=30)
    parser.add_argument("--cost-points", type=float, default=2.0)
    parser.add_argument("--train-fraction", type=float, default=0.6)
    parser.add_argument("--strategy", choices=["first-break-session-close", "fabervaale-orb"], default="first-break-session-close")
    parser.add_argument("--output", default=str(OUT))
    parser.add_argument("--markdown", default=str(default_markdown_path()))
    args = parser.parse_args()
    payload = build_replay(
        coverage=read_json(Path(args.coverage)),
        input_path=args.input or None,
        cadence_minutes=args.cadence_minutes or None,
        opening_range_minutes=args.opening_range_minutes,
        cost_points=args.cost_points,
        train_fraction=args.train_fraction,
        strategy=args.strategy,
    )
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    md = Path(args.markdown)
    md.parent.mkdir(parents=True, exist_ok=True)
    md.write_text(render_markdown(payload))
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
