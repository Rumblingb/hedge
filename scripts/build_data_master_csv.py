#!/usr/bin/env python3
"""Build a machine-readable Bill Data Master CSV from local datasets.

Hermes maintains excellent Obsidian prose catalogs. This script makes the same
inventory usable by agents and pipelines: one CSV row per dataset with path,
schema, row count, date range, inferred symbols, trust tier, and blockers. It is
read-only except for writing the catalog artifacts.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
VAULT = Path.home() / "Documents" / "memorybrain"
HERMES = VAULT / "Agent-Hermes"
DEFAULT_OUTPUT = STATE / "bill-data-master.csv"
DEFAULT_JSON = STATE / "bill-data-master.latest.json"
DEFAULT_MARKDOWN = HERMES / f"bill-data-master-csv-{datetime.now(timezone.utc).date().isoformat()}.md"
DEFAULT_ROOTS = (ROOT / "data" / "free", ROOT / "data" / "research")
DATE_TERMS = ("date", "time", "timestamp", "datetime", "ts")
SYMBOL_TERMS = ("symbol", "ticker", "instrument", "market", "asset")
KNOWN_SYMBOLS = (
    "NQ", "ES", "GC", "CL", "6E", "ZN", "SI", "NG", "HG", "RTY", "YM", "VIX", "SPX", "BTC", "ETH", "GOLD",
    "EURUSD", "EURGBP", "EURJPY", "EURCHF",
)


@dataclass
class DatasetRow:
    relative_path: str
    absolute_path: str
    size_mb: float
    rows: int
    column_count: int
    columns: list[str]
    date_column: str | None
    date_min: str | None
    date_max: str | None
    symbol_column: str | None
    symbols: list[str]
    timeframe: str
    trust_tier: str
    usage: str
    blockers: list[str]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def open_text(path: Path):
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8", errors="replace", newline="")
    return path.open("r", encoding="utf-8", errors="replace", newline="")


def find_column(columns: list[str], terms: Iterable[str]) -> str | None:
    for column in columns:
        lower = column.strip().lower()
        if any(term in lower for term in terms):
            return column
    return None


def infer_symbols(path: Path, symbol_column: str | None, columns: list[str], first_rows: list[list[str]]) -> list[str]:
    symbols: set[str] = set()
    if symbol_column and symbol_column in columns:
        idx = columns.index(symbol_column)
        for row in first_rows:
            if idx < len(row) and row[idx].strip():
                symbols.add(row[idx].strip().upper())
    name = path.name.upper()
    for symbol in KNOWN_SYMBOLS:
        if name.startswith(f"{symbol}-") or name.startswith(f"{symbol}_") or f"-{symbol}-" in name:
            symbols.add(symbol)
    if name.startswith("ALL-6MARKETS"):
        symbols.update({"NQ", "ES", "GC", "CL", "6E", "ZN"})
    if name.startswith("ALL-2MARKETS"):
        symbols.update({"NQ", "ES"})
    return sorted(symbols)


def infer_timeframe(path: Path, columns: list[str]) -> str:
    name = path.name.lower()
    patterns = [
        ("1min", ("1min", "1-min", "1m-")),
        ("15min", ("15m", "15-min", "15minute")),
        ("30min", ("30m", "30-min", "30minute")),
        ("60min", ("60m", "1h", "60-min", "hour")),
        ("5min", ("5m", "5-min", "5minute")),
        ("4h", ("4h", "240m")),
        ("daily", ("daily", "1d", "day")),
        ("weekly", ("weekly", "1w")),
        ("tick", ("tick",)),
    ]
    for label, needles in patterns:
        if any(needle in name for needle in needles):
            return label
    lowered_columns = {column.lower() for column in columns}
    if "date" in lowered_columns and not any("time" in column for column in lowered_columns):
        return "daily"
    return "unknown"


def classify_tier(path: Path, rows: int, date_min: str | None, date_max: str | None, symbols: list[str], timeframe: str) -> tuple[str, str, list[str]]:
    name = path.name
    blockers: list[str] = []
    if rows <= 0:
        blockers.append("empty-or-unreadable")
    if not date_min or not date_max:
        blockers.append("date-range-missing")
    if not symbols:
        blockers.append("symbol-missing")
    if "futures-daily-with-features-24tickers" in name:
        blockers.append("most-tickers-have-empty-datetime-use-feature-research-only")
    if "SP-tick-2000-2019" in name:
        blockers.append("volume-mostly-zero-quote-ticks-not-trade-volume")
    if "VIX-daily-2004-2020" in name:
        blockers.append("stale-ends-2020")
    if "longterm" in name and set(symbols) == {"ES", "NQ"}:
        blockers.append("cross-symbol-non-overlap-normalized-research-only")
    if any(symbol in {"EURUSD", "EURGBP", "EURJPY", "EURCHF"} for symbol in symbols):
        blockers.append("cash-fx-proxy-not-futures-contract")

    if blockers:
        tier = "silver-research" if rows > 1000 and date_min else "quarantine-review"
    elif rows >= 100_000 and timeframe in {"1min", "5min", "15min", "60min", "tick"}:
        tier = "gold-walkforward"
    elif rows >= 2_000 and timeframe in {"daily", "60min", "4h"}:
        tier = "gold-research"
    elif rows >= 500:
        tier = "silver-research"
    else:
        tier = "bronze-context"

    if tier.startswith("gold"):
        usage = "walkforward-or-regime-research"
    elif tier == "silver-research":
        usage = "research-with-blocker-review"
    elif tier == "bronze-context":
        usage = "context-only"
    else:
        usage = "manual-review-before-use"
    return tier, usage, blockers


def analyze_csv(path: Path) -> DatasetRow:
    first_rows: list[list[str]] = []
    last_row: list[str] | None = None
    rows = 0
    columns: list[str] = []
    try:
        with open_text(path) as handle:
            reader = csv.reader(handle)
            columns = next(reader)
            for row in reader:
                if not row:
                    continue
                rows += 1
                if len(first_rows) < 5:
                    first_rows.append(row)
                last_row = row
    except Exception:
        columns = []

    date_column = find_column(columns, DATE_TERMS)
    symbol_column = find_column(columns, SYMBOL_TERMS)
    date_min: str | None = None
    date_max: str | None = None
    if date_column and date_column in columns:
        idx = columns.index(date_column)
        for row in first_rows:
            if idx < len(row) and row[idx].strip():
                date_min = row[idx].strip()
                break
        if last_row and idx < len(last_row) and last_row[idx].strip():
            date_max = last_row[idx].strip()
    symbols = infer_symbols(path, symbol_column, columns, first_rows)
    timeframe = infer_timeframe(path, columns)
    tier, usage, blockers = classify_tier(path, rows, date_min, date_max, symbols, timeframe)
    return DatasetRow(
        relative_path=str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
        absolute_path=str(path),
        size_mb=round(path.stat().st_size / (1024 * 1024), 3),
        rows=rows,
        column_count=len(columns),
        columns=columns,
        date_column=date_column,
        date_min=date_min,
        date_max=date_max,
        symbol_column=symbol_column,
        symbols=symbols,
        timeframe=timeframe,
        trust_tier=tier,
        usage=usage,
        blockers=blockers,
    )


def find_csvs(roots: list[Path]) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        files.extend(path for path in root.rglob("*") if path.is_file() and path.suffix in {".csv", ".gz"})
    return sorted(files)


def write_csv(path: Path, rows: list[DatasetRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "relative_path", "absolute_path", "size_mb", "rows", "column_count", "date_column", "date_min", "date_max",
        "symbol_column", "symbols", "timeframe", "trust_tier", "usage", "blockers", "columns",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({
                "relative_path": row.relative_path,
                "absolute_path": row.absolute_path,
                "size_mb": row.size_mb,
                "rows": row.rows,
                "column_count": row.column_count,
                "date_column": row.date_column or "",
                "date_min": row.date_min or "",
                "date_max": row.date_max or "",
                "symbol_column": row.symbol_column or "",
                "symbols": "|".join(row.symbols),
                "timeframe": row.timeframe,
                "trust_tier": row.trust_tier,
                "usage": row.usage,
                "blockers": "|".join(row.blockers),
                "columns": "|".join(row.columns),
            })


def build_payload(rows: list[DatasetRow], output: Path) -> dict[str, Any]:
    by_tier: dict[str, int] = {}
    for row in rows:
        by_tier[row.trust_tier] = by_tier.get(row.trust_tier, 0) + 1
    top = sorted(rows, key=lambda row: (row.trust_tier.startswith("gold"), row.rows, row.size_mb), reverse=True)[:20]
    return {
        "command": "build-data-master-csv",
        "generatedAt": utc_now(),
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "movesFunds": False,
        "outputCsv": str(output),
        "datasetCount": len(rows),
        "tierCounts": by_tier,
        "topDatasets": [
            {
                "path": row.relative_path,
                "rows": row.rows,
                "symbols": row.symbols,
                "timeframe": row.timeframe,
                "trustTier": row.trust_tier,
                "blockers": row.blockers,
            }
            for row in top
        ],
        "hardRules": [
            "This catalog is data inventory only; it does not approve strategy promotion or execution.",
            "Datasets with missing dates, symbol gaps, stale coverage, or source-specific caveats stay research-only.",
            "Broker-relevant current bars still come from TopstepX/ProjectX proof artifacts, not historical CSV catalogs.",
        ],
    }


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Bill Data Master CSV",
        "",
        f"Generated: `{payload.get('generatedAt')}`",
        f"Output CSV: `{payload.get('outputCsv')}`",
        f"Dataset count: `{payload.get('datasetCount')}`",
        "",
        "## Tier Counts",
        "",
    ]
    for tier, count in sorted((payload.get("tierCounts") or {}).items()):
        lines.append(f"- `{tier}`: `{count}`")
    lines.extend(["", "## Top Datasets", ""])
    for item in payload.get("topDatasets", []):
        lines.append(f"- `{item.get('path')}` rows `{item.get('rows')}` tier `{item.get('trustTier')}` blockers `{item.get('blockers')}`")
    lines.extend(["", "## Hard Rules", ""])
    for rule in payload.get("hardRules", []):
        lines.append(f"- {rule}")
    lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Bill Data Master CSV.")
    parser.add_argument("--root", action="append", default=None, help="Dataset root to scan. May be repeated.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--json", default=str(DEFAULT_JSON))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))
    parser.add_argument("--compact", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    roots = [Path(item).expanduser() for item in args.root] if args.root else list(DEFAULT_ROOTS)
    rows = [analyze_csv(path) for path in find_csvs(roots)]
    output = Path(args.output)
    json_path = Path(args.json)
    markdown = Path(args.markdown)
    write_csv(output, rows)
    payload = build_payload(rows, output)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    markdown.write_text(render_markdown(payload))
    if args.compact:
        print(json.dumps({
            "datasetCount": payload["datasetCount"],
            "tierCounts": payload["tierCounts"],
            "outputCsv": payload["outputCsv"],
        }, sort_keys=True))
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
