#!/usr/bin/env python3
"""Write a compact research-only quality snapshot for Bill futures datasets."""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge/state"
DEFAULT_DATASETS = [
    ROOT / "data/free/ALL-6MARKETS-15m-60d-normalized.csv",
    ROOT / "data/free/ALL-6MARKETS-30m-60d-normalized.csv",
    ROOT / "data/free/ALL-6MARKETS-60m-60d-normalized.csv",
]
DEFAULT_OUTPUT = STATE / "futures-data-quality.latest.json"


def normalize_threshold(value: float) -> float:
    return value / 100 if 1 < value <= 100 else value


def parse_ts(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def inspect_dataset(
    path: Path,
    min_coverage: float,
    max_end_lag_minutes: float,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    rows_by_symbol: dict[str, list[datetime]] = defaultdict(list)
    total_rows = 0
    malformed_rows = 0
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            symbol = (row.get("symbol") or "").strip()
            ts = parse_ts((row.get("ts") or "").strip())
            if not symbol or ts is None:
                malformed_rows += 1
                continue
            rows_by_symbol[symbol].append(ts)
            total_rows += 1

    symbols = sorted(rows_by_symbol)
    all_ts = [ts for values in rows_by_symbol.values() for ts in values]
    latest = max(all_ts) if all_ts else None
    earliest = min(all_ts) if all_ts else None
    if latest and latest.tzinfo is None:
        latest = latest.replace(tzinfo=timezone.utc)
    if earliest and earliest.tzinfo is None:
        earliest = earliest.replace(tzinfo=timezone.utc)
    dataset_end_age_minutes = (now - latest).total_seconds() / 60 if latest else float("inf")
    max_rows = max((len(values) for values in rows_by_symbol.values()), default=0)
    symbol_quality = []
    for symbol in symbols:
        values = sorted(rows_by_symbol[symbol])
        end_lag = (latest - values[-1]).total_seconds() / 60 if latest and values else float("inf")
        coverage = len(values) / max_rows if max_rows else 0.0
        symbol_quality.append({
            "symbol": symbol,
            "rows": len(values),
            "coveragePct": round(coverage, 6),
            "startTs": values[0].isoformat().replace("+00:00", "Z") if values else None,
            "endTs": values[-1].isoformat().replace("+00:00", "Z") if values else None,
            "endLagMinutes": round(end_lag, 2) if end_lag != float("inf") else None,
        })

    failing = []
    if total_rows == 0:
        failing.append("hasRows")
    if malformed_rows:
        failing.append("malformedRows")
    if any(item["coveragePct"] < min_coverage for item in symbol_quality):
        failing.append("minCoveragePct")
    if any((item["endLagMinutes"] is None or item["endLagMinutes"] > max_end_lag_minutes) for item in symbol_quality):
        failing.append("maxSymbolEndLagMinutes")
    if dataset_end_age_minutes > max_end_lag_minutes:
        failing.append("maxDatasetEndAgeMinutes")

    return {
        "path": str(path),
        "exists": path.exists(),
        "rows": total_rows,
        "malformedRows": malformed_rows,
        "symbols": symbols,
        "startTs": earliest.isoformat().replace("+00:00", "Z") if earliest else None,
        "endTs": latest.isoformat().replace("+00:00", "Z") if latest else None,
        "datasetEndAgeMinutes": (
            round(dataset_end_age_minutes, 2)
            if dataset_end_age_minutes != float("inf")
            else None
        ),
        "symbolQuality": symbol_quality,
        "failingChecks": failing,
        "pass": not failing,
    }


def build_snapshot(
    paths: list[Path],
    min_coverage: float,
    max_end_lag_minutes: float,
    now: datetime | None = None,
) -> dict[str, Any]:
    min_coverage = normalize_threshold(min_coverage)
    now = now or datetime.now(timezone.utc)
    datasets = [
        inspect_dataset(path, min_coverage, max_end_lag_minutes, now)
        for path in paths
    ]
    return {
        "command": "futures-data-quality",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "researchOnly": True,
        "writesOrders": False,
        "minCoveragePct": min_coverage,
        "maxEndLagMinutes": max_end_lag_minutes,
        "datasets": datasets,
        "pass": all(item["pass"] for item in datasets),
        "failingDatasets": [item["path"] for item in datasets if not item["pass"]],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-coverage", type=float, default=0.95)
    parser.add_argument("--max-end-lag-minutes", type=float, default=3000)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("datasets", nargs="*")
    args = parser.parse_args()

    paths = [Path(item).resolve() for item in args.datasets] if args.datasets else DEFAULT_DATASETS
    snapshot = build_snapshot(paths, args.min_coverage, args.max_end_lag_minutes)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n")
    print(json.dumps(snapshot, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
