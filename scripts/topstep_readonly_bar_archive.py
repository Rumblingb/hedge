#!/usr/bin/env python3
"""Append read-only TopstepX current NQ/MNQ bars to a local research archive.

This uses the same safety checks and market-data helpers as
``topstep_market_data_smoke``. It is intentionally not an execution-data feed:
it never submits, modifies, cancels, sizes, funds, or routes orders. The archive
exists so current-session broker-relevant bar evidence can accumulate over time
instead of living only as one-off smoke snapshots.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import topstep_market_data_smoke as topstep_md  # noqa: E402

STATE = ROOT / ".rumbling-hedge" / "state"
ARCHIVE_DIR = ROOT / ".rumbling-hedge" / "research" / "topstep-readonly-bars"
OUT = STATE / "topstep-readonly-bar-archive.latest.json"
EASTERN = ZoneInfo("America/New_York")

SAFE_ENV = {
    "BILL_ENABLE_FUTURES_DEMO_EXECUTION": "false",
    "RH_TOPSTEP_READ_ONLY": "true",
    "RH_LIVE_EXECUTION_ENABLED": "false",
}

SYMBOLS = [("NQ", "F.US.ENQ"), ("MNQ", "F.US.MNQ")]
CSV_FIELDS = ["ts", "symbol", "open", "high", "low", "close", "volume", "source", "contractId"]


def now_utc() -> datetime:
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


def bar_row(symbol: str, contract_id: str, bar: dict[str, Any]) -> dict[str, Any] | None:
    ts = parse_ts(bar.get("t"))
    if not ts:
        return None
    values = {
        "open": to_float(bar.get("o")),
        "high": to_float(bar.get("h")),
        "low": to_float(bar.get("l")),
        "close": to_float(bar.get("c")),
        "volume": to_float(bar.get("v")),
    }
    if any(values[key] is None for key in ["open", "high", "low", "close"]):
        return None
    return {
        "ts": iso_minute(ts),
        "symbol": symbol,
        **values,
        "source": "topstep-readonly-market-data",
        "contractId": contract_id,
    }


def csv_path(archive_dir: Path, symbol: str) -> Path:
    return archive_dir / f"{symbol}-1m-topstep-readonly.csv"


def read_archive(path: Path) -> dict[tuple[str, str], dict[str, Any]]:
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    if not path.exists():
        return rows
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            ts = str(row.get("ts") or "")
            symbol = str(row.get("symbol") or "")
            if ts and symbol:
                rows[(ts, symbol)] = row
    return rows


def write_archive(path: Path, rows: dict[tuple[str, str], dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = [rows[key] for key in sorted(rows)]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in ordered:
            writer.writerow({field: row.get(field, "") for field in CSV_FIELDS})


def row_range(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"rows": 0, "min": None, "max": None}
    timestamps = sorted(str(row.get("ts")) for row in rows if row.get("ts"))
    return {"rows": len(rows), "min": timestamps[0] if timestamps else None, "max": timestamps[-1] if timestamps else None}


def session_counts(rows: list[dict[str, Any]]) -> dict[str, Any]:
    all_dates: set[str] = set()
    rth_dates: set[str] = set()
    for row in rows:
        ts = parse_ts(row.get("ts"))
        if not ts:
            continue
        eastern = ts.astimezone(EASTERN)
        date_key = eastern.date().isoformat()
        all_dates.add(date_key)
        if (eastern.hour, eastern.minute) >= (9, 30) and (eastern.hour, eastern.minute) < (16, 0):
            rth_dates.add(date_key)
    return {
        "sessionCount": len(all_dates),
        "rthSessionCount": len(rth_dates),
        "sessionDates": sorted(all_dates)[-10:],
        "rthSessionDates": sorted(rth_dates)[-10:],
    }


def append_symbol_archive(
    *,
    archive_dir: Path,
    symbol: str,
    contract_id: str,
    bars: list[dict[str, Any]],
    dry_run: bool = False,
) -> dict[str, Any]:
    path = csv_path(archive_dir, symbol)
    existing = read_archive(path)
    before = len(existing)
    normalized = [row for bar in bars if (row := bar_row(symbol, contract_id, bar))]
    for row in normalized:
        existing[(str(row["ts"]), symbol)] = row
    after = len(existing)
    if not dry_run:
        write_archive(path, existing)
    archived_rows = list(existing.values())
    return {
        "symbol": symbol,
        "csvPath": str(path),
        "fetchedRows": len(bars),
        "validFetchedRows": len(normalized),
        "existingRows": before,
        "rowCount": after,
        "addedRows": max(0, after - before),
        "dryRun": dry_run,
        "range": row_range(archived_rows),
        **session_counts(archived_rows),
    }


def fetch_symbol_bars(
    *,
    token: str,
    contracts: list[dict[str, Any]],
    symbol: str,
    symbol_id: str,
    start: datetime,
    end: datetime,
    limit: int,
    live: bool,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    contract = topstep_md.pick_active_contract(contracts, symbol_id)
    if not contract:
        return [], None
    bars = topstep_md.retrieve_bars(
        token,
        str(contract.get("id")),
        start=start,
        end=end,
        unit_number=1,
        limit=limit,
        live=live,
    )
    return bars, contract


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    started = now_utc()
    blockers = topstep_md.safety_blockers()
    archive_dir = Path(args.archive_dir).resolve()
    report: dict[str, Any] = {
        "command": "topstep-readonly-bar-archive",
        "generatedAt": started.isoformat(),
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
        "archiveDir": str(archive_dir),
        "minimumSessionsForResearch": args.min_sessions,
        "preferredSessionsForPromotionReview": args.preferred_sessions,
        "blockers": blockers,
        "symbols": {},
    }
    if blockers:
        report["status"] = "BLOCKED_BY_SAFETY_ENV"
        report["brokerBarArchiveReadyForResearchDepth"] = False
        return report

    try:
        token = topstep_md.login()
        contracts = topstep_md.search_contracts(token, args.search_text, live=args.live)
        end = now_utc()
        start = end - timedelta(minutes=args.lookback_minutes)
        for symbol, symbol_id in SYMBOLS:
            bars, contract = fetch_symbol_bars(
                token=token,
                contracts=contracts,
                symbol=symbol,
                symbol_id=symbol_id,
                start=start,
                end=end,
                limit=args.limit,
                live=args.live,
            )
            if not contract:
                report["symbols"][symbol] = {
                    "status": "NO_ACTIVE_CONTRACT",
                    "symbolId": symbol_id,
                    "fetchedRows": 0,
                    "validFetchedRows": 0,
                }
                continue
            summary = append_symbol_archive(
                archive_dir=archive_dir,
                symbol=symbol,
                contract_id=str(contract.get("id")),
                bars=bars,
                dry_run=args.dry_run,
            )
            report["symbols"][symbol] = {
                "status": "ARCHIVED" if summary["validFetchedRows"] > 0 else "NO_BARS",
                "contract": {
                    "id": contract.get("id"),
                    "name": contract.get("name"),
                    "description": contract.get("description"),
                    "tickSize": contract.get("tickSize"),
                    "tickValue": contract.get("tickValue"),
                    "activeContract": contract.get("activeContract"),
                    "symbolId": contract.get("symbolId"),
                },
                **summary,
            }
        nq = report["symbols"].get("NQ") if isinstance(report["symbols"].get("NQ"), dict) else {}
        nq_sessions = int(nq.get("rthSessionCount") or 0)
        report["nqArchiveRthSessionCount"] = nq_sessions
        report["nqArchiveSessionCount"] = int(nq.get("sessionCount") or 0)
        report["brokerBarArchiveReadyForResearchDepth"] = nq_sessions >= args.min_sessions
        report["status"] = "PASS" if any(
            isinstance(item, dict) and item.get("status") == "ARCHIVED"
            for item in report["symbols"].values()
        ) else "NO_BARS"
        report["promotionRule"] = (
            "This archive can build broker-relevant current-session bar depth over time. "
            "It does not clear execution-grade realtime data, DOM/depth/order-flow, OOS, source hygiene, daily approval, or route firewalls."
        )
    except Exception as exc:
        report["status"] = "ERROR"
        report["error"] = str(exc)
        report["brokerBarArchiveReadyForResearchDepth"] = False
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--search-text", default="NQ")
    parser.add_argument("--lookback-minutes", type=int, default=240)
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--archive-dir", default=str(ARCHIVE_DIR))
    parser.add_argument("--min-sessions", type=int, default=20)
    parser.add_argument("--preferred-sessions", type=int, default=60)
    parser.add_argument("--live", action="store_true", help="Use live data subscription instead of sim data")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = build_report(args)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload.get("status") in {"PASS", "NO_BARS"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
