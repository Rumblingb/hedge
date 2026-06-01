#!/usr/bin/env python3
"""
Fetch CFTC Traders in Financial Futures positioning for core futures.

This is a read-only research intake. It writes weekly CFTC/TFF context into the
canonical Bill state tree so futures strategies can use positioning as a gate or
research feature, never as an execution directive.
"""

from __future__ import annotations

import csv
import json
import statistics
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / ".rumbling-hedge" / "state"
RESEARCH_DIR = ROOT / ".rumbling-hedge" / "research" / "cot"
OUTPUT_JSON = STATE_DIR / "cftc-tff-positioning.latest.json"
OUTPUT_CSV = RESEARCH_DIR / "tff-current-core-futures.csv"
SODA_ENDPOINT = "https://publicreporting.cftc.gov/resource/gpe5-46if.json"

MARKETS = {
    "ES": "E-MINI S&P 500",
    "NQ": "NASDAQ-100 Consolidated",
    "ZN": "UST 10Y NOTE",
}


@dataclass
class MarketPositioning:
    symbol: str
    contractMarketName: str
    reportDate: str
    records: int
    openInterest: float
    dealerNetPct: float
    assetManagerNetPct: float
    leveragedMoneyNetPct: float
    dealerZ52: float
    assetManagerZ52: float
    leveragedMoneyZ52: float
    positioningRegime: str
    researchUse: str


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.replace("Z", "+00:00")
    if text.endswith(".000"):
        text = text[:-4]
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def as_float(row: dict[str, Any], key: str) -> float:
    value = row.get(key)
    if value in (None, "", "."):
        return 0.0
    return float(value)


def net_pct(row: dict[str, Any], long_key: str, short_key: str) -> float:
    oi = as_float(row, "open_interest_all")
    if oi <= 0:
        return 0.0
    return (as_float(row, long_key) - as_float(row, short_key)) / oi * 100.0


def zscore(values: list[float]) -> float:
    if len(values) < 5:
        return 0.0
    std = statistics.stdev(values)
    if std == 0:
        return 0.0
    return (values[-1] - statistics.mean(values)) / std


def normalize_report_date(row: dict[str, Any]) -> str:
    dt = parse_dt(row.get("report_date_as_yyyy_mm_dd"))
    return dt.date().isoformat() if dt else str(row.get("report_date_as_yyyy_mm_dd") or "unknown")


def classify_regime(dealer_z: float, lev_z: float) -> str:
    if dealer_z <= -1.5 and lev_z >= 0.5:
        return "risk-on-confirmed-by-leveraged-money"
    if dealer_z <= -1.5:
        return "dealer-short-contrarian-support"
    if dealer_z >= 1.5 and lev_z <= -0.5:
        return "risk-off-confirmed-by-leveraged-money"
    if dealer_z >= 1.5:
        return "dealer-long-contrarian-resistance"
    if abs(lev_z) >= 1.5:
        return "leveraged-money-extreme"
    return "neutral-positioning"


def build_market_positioning(symbol: str, contract_market_name: str, rows: list[dict[str, Any]]) -> MarketPositioning | None:
    filtered = [row for row in rows if row.get("contract_market_name") == contract_market_name]
    filtered.sort(key=lambda row: row.get("report_date_as_yyyy_mm_dd", ""))
    if not filtered:
        return None

    latest = filtered[-1]
    window = filtered[-52:] if len(filtered) > 52 else filtered
    dealer_series = [net_pct(row, "dealer_positions_long_all", "dealer_positions_short_all") for row in window]
    asset_manager_series = [net_pct(row, "asset_mgr_positions_long_all", "asset_mgr_positions_short_all") for row in window]
    leveraged_money_series = [net_pct(row, "lev_money_positions_long_all", "lev_money_positions_short_all") for row in window]

    dealer_z = zscore(dealer_series)
    asset_manager_z = zscore(asset_manager_series)
    leveraged_money_z = zscore(leveraged_money_series)

    return MarketPositioning(
        symbol=symbol,
        contractMarketName=contract_market_name,
        reportDate=normalize_report_date(latest),
        records=len(filtered),
        openInterest=round(as_float(latest, "open_interest_all"), 0),
        dealerNetPct=round(dealer_series[-1], 3),
        assetManagerNetPct=round(asset_manager_series[-1], 3),
        leveragedMoneyNetPct=round(leveraged_money_series[-1], 3),
        dealerZ52=round(dealer_z, 3),
        assetManagerZ52=round(asset_manager_z, 3),
        leveragedMoneyZ52=round(leveraged_money_z, 3),
        positioningRegime=classify_regime(dealer_z, leveraged_money_z),
        researchUse="weekly regime/risk gate only; not an entry signal",
    )


def fetch_tff_rows(markets: dict[str, str] = MARKETS, limit: int = 420) -> list[dict[str, Any]]:
    names = ",".join(f"'{name}'" for name in markets.values())
    params = urllib.parse.urlencode({
        "$limit": str(limit),
        "$order": "report_date_as_yyyy_mm_dd DESC",
        "$where": f"contract_market_name in({names})",
    })
    req = urllib.request.Request(
        f"{SODA_ENDPOINT}?{params}",
        headers={"User-Agent": "bill-hermes-cftc-tff-positioning/1.0"},
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("")
        return
    fields = sorted({key for row in rows for key in row.keys()})
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def build_report(rows: list[dict[str, Any]], generated_at: datetime | None = None) -> dict[str, Any]:
    generated_at = generated_at or datetime.now(timezone.utc)
    markets: dict[str, Any] = {}
    latest_dates: list[datetime] = []
    missing: list[str] = []

    for symbol, contract_name in MARKETS.items():
        result = build_market_positioning(symbol, contract_name, rows)
        if result is None:
            missing.append(symbol)
            continue
        markets[symbol] = asdict(result)
        dt = parse_dt(result.reportDate)
        if dt:
            latest_dates.append(dt)

    latest_dt = max(latest_dates) if latest_dates else None
    age_days = None
    if latest_dt:
        age_days = round((generated_at - latest_dt).total_seconds() / 86400.0, 2)

    blockers = []
    if missing:
        blockers.append(f"missing markets: {', '.join(missing)}")
    if age_days is None:
        blockers.append("no report date found")
    elif age_days > 14:
        blockers.append(f"CFTC TFF data is stale for weekly research: age_days={age_days}")

    return {
        "command": "cftc-tff-positioning-ingest",
        "generatedAt": generated_at.isoformat(),
        "source": {
            "name": "CFTC Public Reporting Environment TFF Futures Only",
            "endpoint": SODA_ENDPOINT,
            "datasetId": "gpe5-46if",
            "documentation": "https://publicreporting.cftc.gov/stories/s/TFF-Futures-Only/98ig-3k9y/",
        },
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "promoted_for_execution": False,
        "tradable_signal": False,
        "evidence_level": "weekly_cftc_positioning_research_only",
        "readyForExecution": False,
        "freshForWeeklyResearch": not blockers,
        "latestReportDate": latest_dt.date().isoformat() if latest_dt else None,
        "latestAgeDays": age_days,
        "rowsRead": len(rows),
        "markets": markets,
        "blockers": blockers,
        "nextActions": [
            "Use COT only as a weekly regime/risk feature in futures OOS tests.",
            "Do not route or size live/demo orders directly from COT positioning.",
            "Retest one strategy family at a time with COT as the only added variable.",
        ],
    }


def main() -> int:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    RESEARCH_DIR.mkdir(parents=True, exist_ok=True)
    rows = fetch_tff_rows()
    write_csv(rows, OUTPUT_CSV)
    report = build_report(rows)
    report["csv"] = str(OUTPUT_CSV)
    OUTPUT_JSON.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({
        "freshForWeeklyResearch": report["freshForWeeklyResearch"],
        "latestReportDate": report["latestReportDate"],
        "latestAgeDays": report["latestAgeDays"],
        "rowsRead": report["rowsRead"],
        "markets": sorted(report["markets"].keys()),
        "blockers": report["blockers"],
        "json": str(OUTPUT_JSON),
        "csv": str(OUTPUT_CSV),
    }, indent=2))
    return 0 if report["freshForWeeklyResearch"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
