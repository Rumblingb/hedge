#!/usr/bin/env python3
"""Compare read-only TopstepX NQ bars against local research CSV bars.

This is a broker/local parity proof, not an execution-data proof. It calls only
TopstepX market-data endpoints through ``topstep_market_data_smoke`` helpers and
then compares overlapping 1m OHLC bars against local Yahoo/yfinance research
CSVs. Volume is reported as reference only because vendor aggregation can
differ.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import topstep_market_data_smoke as topstep_md  # noqa: E402

STATE = ROOT / ".rumbling-hedge" / "state"
OUT = STATE / "topstep-broker-local-bar-parity.latest.json"
DEFAULT_LOCAL_PATHS = [
    ROOT / "data/free/NQ-1m-5d.csv",
    ROOT / "data/free/ALL-6MARKETS-1m-5d-normalized.csv",
]

SAFE_ENV = {
    "BILL_ENABLE_FUTURES_DEMO_EXECUTION": "false",
    "RH_TOPSTEP_READ_ONLY": "true",
    "RH_LIVE_EXECUTION_ENABLED": "false",
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_ts(value: Any) -> datetime | None:
    try:
        ts = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc).replace(second=0, microsecond=0)


def iso_minute(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).replace(second=0, microsecond=0).isoformat().replace("+00:00", "Z")


def to_float(value: Any) -> float | None:
    try:
        return float(value)
    except Exception:
        return None


def local_rows(path: Path, symbol: str) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return rows
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if (row.get("symbol") or symbol) != symbol:
                continue
            ts = parse_ts(row.get("ts"))
            if not ts:
                continue
            values = {
                "open": to_float(row.get("open")),
                "high": to_float(row.get("high")),
                "low": to_float(row.get("low")),
                "close": to_float(row.get("close")),
                "volume": to_float(row.get("volume")),
            }
            if any(values[key] is None for key in ["open", "high", "low", "close"]):
                continue
            rows[iso_minute(ts)] = {"ts": iso_minute(ts), **values}
    return rows


def broker_rows(bars: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for bar in bars:
        if not isinstance(bar, dict):
            continue
        ts = parse_ts(bar.get("t"))
        if not ts:
            continue
        values = {
            "open": to_float(bar.get("o")),
            "high": to_float(bar.get("h")),
            "low": to_float(bar.get("l")),
            "close": to_float(bar.get("c")),
            "volume": to_float(bar.get("v")),
        }
        if any(values[key] is None for key in ["open", "high", "low", "close"]):
            continue
        rows[iso_minute(ts)] = {"ts": iso_minute(ts), **values}
    return rows


def range_summary(rows: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"rows": 0, "min": None, "max": None}
    keys = sorted(rows)
    return {"rows": len(rows), "min": keys[0], "max": keys[-1]}


def compare_rows(
    *,
    broker: dict[str, dict[str, Any]],
    local: dict[str, dict[str, Any]],
    path: Path,
    price_tolerance: float,
    min_overlap: int,
    exclude_latest_overlap_bars: int = 1,
) -> dict[str, Any]:
    overlap = sorted(set(broker) & set(local))
    stable_overlap = overlap
    excluded_latest = []
    if exclude_latest_overlap_bars > 0 and len(overlap) > min_overlap + exclude_latest_overlap_bars:
        stable_overlap = overlap[:-exclude_latest_overlap_bars]
        excluded_latest = overlap[-exclude_latest_overlap_bars:]
    diffs: list[dict[str, Any]] = []
    max_ohlc = 0.0
    max_close = 0.0
    max_volume = 0.0

    raw_max_ohlc = 0.0
    raw_max_close = 0.0
    for ts in overlap:
        b = broker[ts]
        l = local[ts]
        for key in ["open", "high", "low", "close"]:
            diff = abs(float(b[key]) - float(l[key]))
            raw_max_ohlc = max(raw_max_ohlc, diff)
            if key == "close":
                raw_max_close = max(raw_max_close, diff)

    for ts in stable_overlap:
        b = broker[ts]
        l = local[ts]
        row = {"ts": ts}
        for key in ["open", "high", "low", "close"]:
            diff = abs(float(b[key]) - float(l[key]))
            row[f"{key}Diff"] = round(diff, 6)
            max_ohlc = max(max_ohlc, diff)
            if key == "close":
                max_close = max(max_close, diff)
        if b.get("volume") is not None and l.get("volume") is not None:
            volume_diff = abs(float(b["volume"]) - float(l["volume"]))
            row["volumeDiff"] = round(volume_diff, 6)
            max_volume = max(max_volume, volume_diff)
        if any(float(row[f"{key}Diff"]) > price_tolerance for key in ["open", "high", "low", "close"]):
            row["broker"] = {key: b[key] for key in ["open", "high", "low", "close", "volume"]}
            row["local"] = {key: l[key] for key in ["open", "high", "low", "close", "volume"]}
            diffs.append(row)
    ok = len(stable_overlap) >= min_overlap and max_ohlc <= price_tolerance
    return {
        "path": str(path),
        "exists": path.exists(),
        "localRange": range_summary(local),
        "rawOverlapRows": len(overlap),
        "stableOverlapRows": len(stable_overlap),
        "overlapRows": len(stable_overlap),
        "overlapMinTs": overlap[0] if overlap else None,
        "overlapMaxTs": overlap[-1] if overlap else None,
        "stableOverlapMinTs": stable_overlap[0] if stable_overlap else None,
        "stableOverlapMaxTs": stable_overlap[-1] if stable_overlap else None,
        "excludedLatestOverlapRows": [
            {
                "ts": ts,
                "broker": {key: broker[ts].get(key) for key in ["open", "high", "low", "close", "volume"]},
                "local": {key: local[ts].get(key) for key in ["open", "high", "low", "close", "volume"]},
            }
            for ts in excluded_latest
        ],
        "excludeLatestOverlapBars": exclude_latest_overlap_bars,
        "rawMaxOhlcAbsDiff": round(raw_max_ohlc, 6),
        "rawMaxCloseAbsDiff": round(raw_max_close, 6),
        "maxOhlcAbsDiff": round(max_ohlc, 6),
        "maxCloseAbsDiff": round(max_close, 6),
        "maxVolumeAbsDiffReferenceOnly": round(max_volume, 6),
        "mismatchSample": diffs[:8],
        "ok": ok,
        "reason": "ok" if ok else "insufficient-overlap-or-price-diff",
    }


def fetch_broker_nq_bars(args: argparse.Namespace) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    token = topstep_md.login()
    contracts = topstep_md.search_contracts(token, args.search_text, live=args.live)
    contract = topstep_md.pick_active_contract(contracts, "F.US.ENQ")
    if not contract:
        return [], None
    end = utc_now()
    start = end - timedelta(minutes=args.lookback_minutes)
    bars = topstep_md.retrieve_bars(
        token,
        str(contract["id"]),
        start=start,
        end=end,
        unit_number=1,
        limit=args.limit,
        live=args.live,
    )
    return bars, contract


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    blockers = topstep_md.safety_blockers()
    report: dict[str, Any] = {
        "command": "topstep-broker-local-bar-parity",
        "generatedAt": utc_now().isoformat(),
        "researchOnly": True,
        "writesOrders": False,
        "placesOrders": False,
        "modifiesOrders": False,
        "cancelsOrders": False,
        "touchesBroker": True,
        "brokerTouchMode": "read-only-market-data",
        "readyForExecution": False,
        "readyForDemoExpansion": False,
        "readyForLive": False,
        "safeEnv": dict(SAFE_ENV),
        "topstepSessionSafety": topstep_md.topstep_session_safety_summary(),
        "symbol": "NQ",
        "priceTolerance": args.price_tolerance,
        "minimumOverlapRows": args.min_overlap,
        "blockers": blockers,
        "comparisons": [],
    }
    if blockers:
        report["status"] = "BLOCKED_BY_SAFETY_ENV"
        report["brokerParityChecked"] = False
        report["brokerParityPassed"] = False
        return report

    try:
        broker_bar_list, contract = fetch_broker_nq_bars(args)
        broker = broker_rows(broker_bar_list)
        local_paths = [Path(item).resolve() for item in (args.local_csv or DEFAULT_LOCAL_PATHS)]
        comparisons = [
            compare_rows(
                broker=broker,
                local=local_rows(path, "NQ"),
                path=path,
                price_tolerance=args.price_tolerance,
                min_overlap=args.min_overlap,
                exclude_latest_overlap_bars=args.exclude_latest_overlap_bars,
            )
            for path in local_paths
        ]
        report.update(
            {
                "status": "PASS" if any(item["ok"] for item in comparisons) else "BLOCKED",
                "brokerParityChecked": True,
                "brokerParityPassed": any(item["ok"] for item in comparisons),
                "brokerContract": {
                    "id": contract.get("id"),
                    "name": contract.get("name"),
                    "description": contract.get("description"),
                    "tickSize": contract.get("tickSize"),
                    "tickValue": contract.get("tickValue"),
                    "activeContract": contract.get("activeContract"),
                    "symbolId": contract.get("symbolId"),
                }
                if contract
                else None,
                "brokerRange": range_summary(broker),
                "comparisons": comparisons,
                "promotionRule": (
                    "Broker/local OHLC parity can support research data selection only. "
                    "It does not clear execution-grade realtime, DOM/depth/order-flow, OOS, source hygiene, or route approval."
                ),
            }
        )
    except Exception as exc:
        report.update(
            {
                "status": "ERROR",
                "brokerParityChecked": False,
                "brokerParityPassed": False,
                "error": str(exc),
            }
        )
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--search-text", default="NQ")
    parser.add_argument("--lookback-minutes", type=int, default=120)
    parser.add_argument("--limit", type=int, default=240)
    parser.add_argument("--price-tolerance", type=float, default=0.25)
    parser.add_argument("--min-overlap", type=int, default=5)
    parser.add_argument("--exclude-latest-overlap-bars", type=int, default=1)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--local-csv", action="append")
    return parser.parse_args()


def main() -> int:
    payload = build_report(parse_args())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload.get("brokerParityPassed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
