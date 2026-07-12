#!/usr/bin/env python3
"""Explain why simple strategy entry conditions do or do not fire on bars.

This is a research diagnostic for local CSV bars only. It does not fetch data,
route orders, touch brokers, size positions, or mutate trading state.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


CHICAGO = ZoneInfo("America/Chicago")
ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
DEFAULT_INPUT = ROOT / "data/free/NQ-5m-3yr.csv"
DEFAULT_OUTPUT = STATE / "strategy-diagnostic.latest.json"
DEFAULT_RANGE_WINDOW = 12
DEFAULT_VOL_THRESHOLD = 1.3
DEFAULT_SMA_SHORT = 20
DEFAULT_SMA_LONG = 60


def parse_ts(value: str) -> datetime:
    ts = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def load_bars(path: Path, *, max_rows: int | None = None) -> list[dict[str, Any]]:
    bars: list[dict[str, Any]] = []
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            ts = str(row.get("ts") or row.get("timestamp") or row.get("date") or "")
            symbol = str(row.get("symbol") or "NQ").upper()
            if not ts:
                continue
            bars.append(
                {
                    "ts": ts,
                    "symbol": symbol,
                    "open": to_float(row.get("open") or row.get("o")),
                    "high": to_float(row.get("high") or row.get("h")),
                    "low": to_float(row.get("low") or row.get("l")),
                    "close": to_float(row.get("close") or row.get("c")),
                    "volume": to_float(row.get("volume") or row.get("v")),
                }
            )
    bars.sort(key=lambda item: str(item["ts"]))
    if max_rows and max_rows > 0:
        return bars[-max_rows:]
    return bars


def session_key(ts_str: str, symbol: str) -> str:
    dt = parse_ts(ts_str).astimezone(CHICAGO)
    return f"{dt.date().isoformat()}:{symbol}"


def group_sessions(bars: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    sessions: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for bar in bars:
        sessions[session_key(str(bar["ts"]), str(bar["symbol"]))].append(bar)
    return dict(sessions)


def analyze_orb(
    sessions: dict[str, list[dict[str, Any]]],
    *,
    range_window: int = DEFAULT_RANGE_WINDOW,
    vol_threshold: float = DEFAULT_VOL_THRESHOLD,
) -> dict[str, Any]:
    counts = {
        "barsEvaluated": 0,
        "symbolPass": 0,
        "rangeWindowPass": 0,
        "volumePass": 0,
        "breakoutPass": 0,
    }
    for session_bars in sessions.values():
        if not session_bars:
            continue
        symbol = str(session_bars[0]["symbol"])
        if symbol not in {"ES", "NQ", "MNQ", "MES"}:
            continue
        for index, bar in enumerate(session_bars):
            counts["barsEvaluated"] += 1
            if index < range_window:
                continue
            counts["symbolPass"] += 1
            opening = session_bars[:range_window]
            range_high = max(float(item["high"]) for item in opening)
            range_low = min(float(item["low"]) for item in opening)
            counts["rangeWindowPass"] += 1
            recent = session_bars[max(0, index - 20) : index]
            avg_volume = sum(float(item["volume"]) for item in recent) / len(recent) if recent else 0.0
            if avg_volume <= 0 or float(bar["volume"]) < avg_volume * vol_threshold:
                continue
            counts["volumePass"] += 1
            if float(bar["close"]) > range_high or float(bar["close"]) < range_low:
                counts["breakoutPass"] += 1
    return {
        "name": "orb-breakout",
        "rangeWindow": range_window,
        "volumeThreshold": vol_threshold,
        **counts,
    }


def analyze_wq_trend_momentum(
    sessions: dict[str, list[dict[str, Any]]],
    *,
    sma_short: int = DEFAULT_SMA_SHORT,
    sma_long: int = DEFAULT_SMA_LONG,
    min_spread_pct: float = 0.001,
) -> dict[str, Any]:
    eligible_bars = 0
    signals = 0
    for session_bars in sessions.values():
        for index in range(sma_long, len(session_bars)):
            eligible_bars += 1
            short = sum(float(item["close"]) for item in session_bars[index - sma_short : index]) / sma_short
            long = sum(float(item["close"]) for item in session_bars[index - sma_long : index]) / sma_long
            if long and abs(short - long) / long > min_spread_pct:
                signals += 1
    return {
        "name": "wq-trend-momentum",
        "smaShort": sma_short,
        "smaLong": sma_long,
        "eligibleBars": eligible_bars,
        "signals": signals,
        "minSpreadPct": min_spread_pct,
    }


def session_summary(sessions: dict[str, list[dict[str, Any]]], limit: int = 5) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for key in sorted(sessions)[:limit]:
        session_bars = sessions[key]
        if not session_bars:
            continue
        first = session_bars[0]
        first_ts = parse_ts(str(first["ts"]))
        summaries.append(
            {
                "session": key,
                "barCount": len(session_bars),
                "firstTimestamp": first_ts.isoformat(),
                "firstChicagoHour": first_ts.astimezone(CHICAGO).hour,
                "sample": session_bars[:3],
            }
        )
    return summaries


def build_report(path: Path, *, session_limit: int = 5, max_rows: int | None = None) -> dict[str, Any]:
    bars = load_bars(path, max_rows=max_rows)
    sessions = group_sessions(bars)
    session_sizes = [len(items) for items in sessions.values()]
    return {
        "command": "strategy-diagnostic",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "decision": "research-only-strategy-diagnostic",
        "inputPath": str(path),
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "movesFunds": False,
        "readyForExecution": False,
        "readyForDemoExpansion": False,
        "readyForLive": False,
        "barCount": len(bars),
        "sessionCount": len(sessions),
        "sessionBarCountMin": min(session_sizes) if session_sizes else 0,
        "sessionBarCountMax": max(session_sizes) if session_sizes else 0,
        "diagnostics": {
            "orbBreakout": analyze_orb(sessions),
            "wqTrendMomentum": analyze_wq_trend_momentum(sessions),
            "sessions": session_summary(sessions, session_limit),
        },
        "operatorRead": (
            "Research-only local CSV diagnostic. Counts failed entry conditions; "
            "does not approve strategy promotion, demo expansion, or execution."
        ),
        "promotionBlockers": [
            "diagnostic-only-no-execution-authority",
            "requires broker-grade OOS replay before any strategy promotion",
            "requires cost/slippage stress and source hygiene clearance",
        ],
    }


def render_text(report: dict[str, Any]) -> str:
    orb = report["diagnostics"]["orbBreakout"]
    wq = report["diagnostics"]["wqTrendMomentum"]
    lines = [
        "Strategy Diagnostic",
        f"Input: {report['inputPath']}",
        f"Bars: {report['barCount']} Sessions: {report['sessionCount']}",
        "",
        "ORB Breakout:",
        f"  Bars evaluated: {orb['barsEvaluated']}",
        f"  Symbol pass: {orb['symbolPass']}",
        f"  Range-window pass: {orb['rangeWindowPass']}",
        f"  Volume pass: {orb['volumePass']}",
        f"  Breakout pass: {orb['breakoutPass']}",
        "",
        "WQ Trend Momentum:",
        f"  Eligible bars: {wq['eligibleBars']}",
        f"  Signals: {wq['signals']}",
        "",
        report["operatorRead"],
    ]
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="Local OHLCV CSV with ts/date, symbol, open/high/low/close/volume columns.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Optional JSON artifact path.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON instead of text.")
    parser.add_argument("--session-limit", type=int, default=5)
    parser.add_argument("--max-rows", type=int, default=50000, help="Analyze only the last N rows; 0 means all rows.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(Path(args.input), session_limit=args.session_limit, max_rows=args.max_rows or None)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_text(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
