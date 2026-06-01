#!/usr/bin/env python3
"""
Read-only Kalshi fillability snapshot for prediction-market research.

This fetches public open-market quotes for repeated macro/crypto/election
series and records whether the current universe has tight, two-sided books.
It does not authenticate, place orders, or approve paper/live routing.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / ".rumbling-hedge" / "state"
OUTPUT_JSON = STATE_DIR / "kalshi-fillability-snapshot.latest.json"
KALSHI_BASE = "https://api.elections.kalshi.com/trade-api/v2"
DEFAULT_SERIES = [
    "KXFED",
    "KXCPI",
    "KXBTC",
    "KXETH",
    "KXSPY",
    "KXNASDAQ100",
    "KXPRES",
    "KXHOUSE",
    "KXSENATE",
]


@dataclass
class FillabilityRow:
    ticker: str
    seriesTicker: str
    title: str
    yesBid: float | None
    yesAsk: float | None
    lastPrice: float | None
    spreadPct: float | None
    executable: bool
    bucket: str
    liquidityDollars: float
    openInterest: float
    reason: str


def to_float(value: Any) -> float | None:
    if isinstance(value, (int, float)) and value == value:
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def is_combo_like(title: str, ticker: str = "") -> bool:
    lowered = title.lower()
    return ticker.startswith("KXMVE") or title.count(",") >= 2 or "parlay" in lowered or "combo" in lowered


def bucket_for_spread(spread_pct: float | None) -> str:
    if spread_pct is None:
        return "no-two-sided-book"
    if spread_pct <= 2:
        return "tight"
    if spread_pct <= 5:
        return "usable"
    if spread_pct <= 15:
        return "wide"
    return "too-wide"


def infer_series_ticker(market: dict[str, Any]) -> str:
    explicit = str(market.get("series_ticker") or "").strip()
    if explicit:
        return explicit
    ticker = str(market.get("ticker") or "")
    return ticker.split("-", 1)[0] if "-" in ticker else ticker


def row_from_market(market: dict[str, Any]) -> FillabilityRow:
    ticker = str(market.get("ticker") or "unknown")
    title = str(market.get("title") or market.get("subtitle") or ticker)
    bid = to_float(market.get("yes_bid_dollars") if market.get("yes_bid_dollars") is not None else market.get("yes_bid"))
    ask = to_float(market.get("yes_ask_dollars") if market.get("yes_ask_dollars") is not None else market.get("yes_ask"))
    last = to_float(market.get("last_price_dollars") if market.get("last_price_dollars") is not None else market.get("last_price"))
    liquidity = to_float(market.get("liquidity_dollars") if market.get("liquidity_dollars") is not None else market.get("liquidity")) or 0.0
    open_interest = to_float(market.get("open_interest")) or 0.0
    has_book = bid is not None and ask is not None and 0 < bid <= ask < 1
    spread_pct = round((ask - bid) * 100, 3) if has_book else None
    bucket = bucket_for_spread(spread_pct)
    combo = is_combo_like(title, ticker)
    executable = has_book and not combo and bucket in {"tight", "usable"} and ask is not None and 0.01 <= ask <= 0.99
    if combo:
        reason = "combo-like market excluded"
    elif not has_book:
        reason = "missing valid two-sided book"
    elif bucket not in {"tight", "usable"}:
        reason = f"spread bucket {bucket}"
    else:
        reason = "two-sided public quote"
    return FillabilityRow(
        ticker=ticker,
        seriesTicker=infer_series_ticker(market),
        title=title,
        yesBid=bid,
        yesAsk=ask,
        lastPrice=last,
        spreadPct=spread_pct,
        executable=executable,
        bucket=bucket,
        liquidityDollars=round(liquidity, 2),
        openInterest=round(open_interest, 2),
        reason=reason,
    )


def fetch_series_markets(series_ticker: str, limit: int = 100) -> list[dict[str, Any]]:
    params = urllib.parse.urlencode({
        "status": "open",
        "series_ticker": series_ticker,
        "limit": str(limit),
    })
    request = urllib.request.Request(
        f"{KALSHI_BASE}/markets?{params}",
        headers={"accept": "application/json", "user-agent": "bill-hermes-kalshi-fillability/1.0"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload.get("markets") or []


def build_snapshot(rows: list[FillabilityRow], errors: list[dict[str, str]] | None = None) -> dict[str, Any]:
    errors = errors or []
    executable_rows = [row for row in rows if row.executable]
    bucket_counts: dict[str, int] = {}
    for row in rows:
        bucket_counts[row.bucket] = bucket_counts.get(row.bucket, 0) + 1
    top = sorted(
        executable_rows,
        key=lambda row: (
            row.spreadPct if row.spreadPct is not None else 999,
            -(row.liquidityDollars + row.openInterest),
        ),
    )[:20]
    return {
        "command": "kalshi-fillability-snapshot",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "source": {
            "name": "Kalshi public market API",
            "baseUrl": KALSHI_BASE,
            "documentation": "https://docs.kalshi.com/api-reference/market/get-markets",
        },
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "requiresAuth": False,
        "promoted_for_execution": False,
        "tradable_signal": False,
        "readyForPaper": False,
        "marketsInspected": len(rows),
        "executablePublicQuotes": len(executable_rows),
        "bucketCounts": bucket_counts,
        "seriesErrors": errors,
        "topExecutable": [asdict(row) for row in top],
        "decision": "research-only; fillability evidence only",
        "nextActions": [
            "Use this snapshot to choose narrow prediction categories with real two-sided books.",
            "Do not paper/live trade from this artifact.",
            "Join any candidate to resolved-outcome history, CLOB/persistence evidence, fees, and settlement wording before promotion.",
        ],
    }


def main() -> int:
    rows: list[FillabilityRow] = []
    errors: list[dict[str, str]] = []
    for series in DEFAULT_SERIES:
        try:
            rows.extend(row_from_market(market) for market in fetch_series_markets(series))
        except Exception as exc:
            errors.append({"series": series, "error": f"{type(exc).__name__}: {exc}"})

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    snapshot = build_snapshot(rows, errors)
    OUTPUT_JSON.write_text(json.dumps(snapshot, indent=2) + "\n")
    print(json.dumps({
        "marketsInspected": snapshot["marketsInspected"],
        "executablePublicQuotes": snapshot["executablePublicQuotes"],
        "bucketCounts": snapshot["bucketCounts"],
        "seriesErrors": snapshot["seriesErrors"],
        "json": str(OUTPUT_JSON),
        "researchOnly": snapshot["researchOnly"],
        "writesOrders": snapshot["writesOrders"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
