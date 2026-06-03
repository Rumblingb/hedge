#!/usr/bin/env python3
"""Refresh Bill six-market futures research CSVs from Yahoo Finance.

This is a research-data refresh, not an execution data feed. It rebuilds the
normalized 15m/30m/60m CSVs used by strategy research and writes provenance so
freshness gates can tell what happened. Realtime execution still requires the
separate realtime quote bridge to be non-fallback and fresh.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "free"
STATE_DIR = ROOT / ".rumbling-hedge" / "state"
DEFAULT_OUTPUT = STATE_DIR / "futures-research-data-refresh.latest.json"

SYMBOLS = {
    "NQ": "NQ=F",
    "ES": "ES=F",
    "CL": "CL=F",
    "GC": "GC=F",
    "6E": "6E=F",
    "ZN": "ZN=F",
}

INTERVALS = ("1m", "15m", "30m", "60m")
DEFAULT_PERIOD_BY_INTERVAL = {
    "1m": "5d",
    "15m": "60d",
    "30m": "60d",
    "60m": "60d",
}


def iso_utc(value: Any) -> str:
    ts = value.to_pydatetime() if hasattr(value, "to_pydatetime") else value
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", ".000Z")


def finite_number(value: Any) -> float | None:
    try:
        out = float(value)
        return out if math.isfinite(out) else None
    except Exception:
        return None


def fetch_symbol(label: str, ticker: str, interval: str, period: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    import yfinance as yf  # type: ignore

    frame = yf.download(
        ticker,
        period=period,
        interval=interval,
        progress=False,
        auto_adjust=False,
        threads=False,
    )
    rows: list[dict[str, Any]] = []
    if frame is None or frame.empty:
        return rows, {"symbol": label, "ticker": ticker, "interval": interval, "rows": 0, "status": "empty"}

    # yfinance can return a multi-index when a ticker list is used; normalize defensively.
    if hasattr(frame.columns, "nlevels") and frame.columns.nlevels > 1:
        frame.columns = [col[0] for col in frame.columns]

    for idx, row in frame.iterrows():
        open_ = finite_number(row.get("Open"))
        high = finite_number(row.get("High"))
        low = finite_number(row.get("Low"))
        close = finite_number(row.get("Close"))
        volume = finite_number(row.get("Volume"))
        if None in (open_, high, low, close):
            continue
        rows.append({
            "ts": iso_utc(idx),
            "symbol": label,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": int(volume or 0),
        })

    rows.sort(key=lambda item: item["ts"])
    latest = rows[-1]["ts"] if rows else None
    zero_tail = bool(rows) and all(item["volume"] == 0 for item in rows[-3:])
    return rows, {
        "symbol": label,
        "ticker": ticker,
        "interval": interval,
        "rows": len(rows),
        "latestTs": latest,
        "zeroVolumeTail": zero_tail,
        "status": "ok" if rows else "empty",
    }


def write_csv_atomic(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", newline="", dir=str(path.parent), delete=False) as fh:
        tmp = Path(fh.name)
        writer = csv.DictWriter(fh, fieldnames=["ts", "symbol", "open", "high", "low", "close", "volume"])
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(path)


def write_per_symbol_csvs(
    interval: str,
    period: str,
    rows_by_symbol: dict[str, list[dict[str, Any]]],
    write_files: bool,
) -> list[dict[str, Any]]:
    outputs: list[dict[str, Any]] = []
    for symbol, rows in sorted(rows_by_symbol.items()):
        out_path = DATA_DIR / f"{symbol}-{interval}-{period}.csv"
        wrote = bool(write_files and rows)
        if wrote:
            write_csv_atomic(out_path, sorted(rows, key=lambda item: item["ts"]))
        outputs.append({
            "symbol": symbol,
            "outputPath": str(out_path),
            "rows": len(rows),
            "latestTs": rows[-1]["ts"] if rows else None,
            "source": "fresh-fetch",
            "wroteFile": wrote,
        })
    return outputs


def read_existing_symbol_rows(path: Path, wanted_symbols: set[str]) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    summaries: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return rows, summaries
    with path.open(newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            symbol = row.get("symbol", "")
            if symbol not in wanted_symbols:
                continue
            item = {
                "ts": row.get("ts", ""),
                "symbol": symbol,
                "open": finite_number(row.get("open")),
                "high": finite_number(row.get("high")),
                "low": finite_number(row.get("low")),
                "close": finite_number(row.get("close")),
                "volume": int(finite_number(row.get("volume")) or 0),
            }
            if None in (item["open"], item["high"], item["low"], item["close"]) or not item["ts"]:
                continue
            rows.append(item)
            summary = summaries.setdefault(symbol, {
                "symbol": symbol,
                "ticker": SYMBOLS.get(symbol, "unknown"),
                "rows": 0,
                "latestTs": None,
                "zeroVolumeTail": False,
                "status": "ok-from-existing-cache",
                "sourceFallback": "existing-csv",
            })
            summary["rows"] += 1
            if not summary["latestTs"] or item["ts"] > summary["latestTs"]:
                summary["latestTs"] = item["ts"]
    for symbol, summary in summaries.items():
        tail = [item for item in rows if item["symbol"] == symbol][-3:]
        summary["zeroVolumeTail"] = bool(tail) and all(item["volume"] == 0 for item in tail)
    return rows, summaries


def refresh_interval(interval: str, period: str | None, write_files: bool) -> dict[str, Any]:
    effective_period = period or DEFAULT_PERIOD_BY_INTERVAL[interval]
    all_rows: list[dict[str, Any]] = []
    fresh_rows_by_symbol: dict[str, list[dict[str, Any]]] = {}
    symbols: list[dict[str, Any]] = []
    for label, ticker in SYMBOLS.items():
        rows, summary = fetch_symbol(label, ticker, interval, effective_period)
        if rows:
            fresh_rows_by_symbol[label] = sorted(rows, key=lambda item: item["ts"])
        all_rows.extend(rows)
        symbols.append(summary)
    all_rows.sort(key=lambda item: (item["ts"], item["symbol"]))
    out_path = DATA_DIR / f"ALL-6MARKETS-{interval}-{effective_period}-normalized.csv"
    missing_symbols = [item["symbol"] for item in symbols if item.get("status") != "ok" or int(item.get("rows") or 0) <= 0]
    recovered_symbols: list[str] = []
    if missing_symbols:
        cached_rows, cached_summaries = read_existing_symbol_rows(out_path, set(missing_symbols))
        for label in list(missing_symbols):
            summary = cached_summaries.get(label)
            if not summary:
                continue
            all_rows.extend([row for row in cached_rows if row["symbol"] == label])
            for idx, item in enumerate(symbols):
                if item.get("symbol") == label:
                    symbols[idx] = {**item, **summary, "interval": interval}
                    break
            recovered_symbols.append(label)
        all_rows.sort(key=lambda item: (item["ts"], item["symbol"]))
        missing_symbols = [
            item["symbol"]
            for item in symbols
            if item.get("status") not in {"ok", "ok-from-existing-cache"} or int(item.get("rows") or 0) <= 0
        ]
    complete_symbol_set = not missing_symbols
    if write_files and all_rows and complete_symbol_set:
        write_csv_atomic(out_path, all_rows)
    per_symbol_files = write_per_symbol_csvs(interval, effective_period, fresh_rows_by_symbol, write_files)
    latest_ts = max((item.get("latestTs") for item in symbols if item.get("latestTs")), default=None)
    return {
        "interval": interval,
        "period": effective_period,
        "outputPath": str(out_path),
        "perSymbolFiles": per_symbol_files,
        "rows": len(all_rows),
        "latestTs": latest_ts,
        "symbols": symbols,
        "missingSymbols": missing_symbols,
        "recoveredSymbols": recovered_symbols,
        "completeSymbolSet": complete_symbol_set,
        "zeroVolumeTailSymbols": [item["symbol"] for item in symbols if item.get("zeroVolumeTail")],
        "wroteFile": bool(write_files and all_rows and complete_symbol_set),
        "wrotePerSymbolFiles": [item["symbol"] for item in per_symbol_files if item["wroteFile"]],
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    intervals = args.intervals or list(INTERVALS)
    items = [refresh_interval(interval, args.period, not args.dry_run) for interval in intervals]
    blockers: list[str] = []
    warnings: list[str] = []
    for item in items:
        if item["rows"] <= 0:
            blockers.append(f"{item['interval']} produced no rows")
        if item["missingSymbols"]:
            blockers.append(f"{item['interval']} missing symbols: {', '.join(item['missingSymbols'])}")
        if item["zeroVolumeTailSymbols"]:
            warnings.append(f"{item['interval']} zero-volume tail: {', '.join(item['zeroVolumeTailSymbols'])}")
    return {
        "command": "refresh-futures-research-data",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "source": "yahoo-finance-chart-via-yfinance",
        "period": args.period or "interval-defaults",
        "dryRun": args.dry_run,
        "status": "PASS" if not blockers else "BLOCKED",
        "readyForExecution": False,
        "blockers": blockers,
        "warnings": warnings,
        "items": items,
        "hardRules": [
            "These CSVs are research bars, not execution-grade realtime data.",
            "Realtime demo/live routing still requires data-freshness-gate to pass without delayed fallback.",
            "Zero-volume tails cannot confirm DOM, volume, or flow features.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh six-market futures research CSVs.")
    parser.add_argument("--period", default=None)
    parser.add_argument("--interval", dest="intervals", action="append", choices=INTERVALS)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    payload = build_report(args)
    DEFAULT_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
