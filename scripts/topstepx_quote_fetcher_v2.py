#!/usr/bin/env python3
"""TopstepX/ProjectX real-time quote fetcher — tsxapipy backend.

Replaces the raw-websocket SignalR code in topstepx_quote_fetcher.py with
the tsxapipy library (DataStream + APIClient). Reads credentials from
bill.env automatically. Produces the same JSON output format.

Usage:
    python3 scripts/topstepx_quote_fetcher_v2.py [--quiet] [--include-es]
    python3 scripts/topstepx_quote_fetcher_v2.py --check

Output format (stdout JSON):
    {
        "timestamp": "2026-06-29T15:10:00.123456+00:00",
        "source": "topstep_realtime",
        "price_nq": 20123.5,
        "price_es": 5512.25,
        "bid_nq": 20123.25,
        "ask_nq": 20123.75,
        ...
    }

Dependencies: tsxapipy (pip install -e /Users/brain/tsxapi4py)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import Event
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

os.environ.setdefault("TRADING_ENVIRONMENT", "LIVE")
os.environ.setdefault("BILL_ENABLE_FUTURES_DEMO_EXECUTION", "false")
os.environ.setdefault("RH_TOPSTEP_READ_ONLY", "true")
os.environ.setdefault("RH_LIVE_EXECUTION_ENABLED", "false")

STATE = ROOT / ".rumbling-hedge" / "state"
STATE_FILE = STATE / "realtime-quote.latest.json"
QUOTE_COLLECTION_TIMEOUT_SECONDS = 12.0
FRESH_SECONDS = 60
# NQ/ES symbol IDs resolved dynamically via contract search

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("topstepx_quote_fetcher_v2")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _resolve_contracts(token: str) -> dict[str, dict[str, Any]]:
    from tsxapipy import APIClient
    from datetime import timezone as tz
    now = datetime.now(tz.utc)
    client = APIClient(initial_token=token, token_acquired_at=now)
    contracts: dict[str, dict[str, Any]] = {}
    try:
        raw = client.search_contracts("MNQ")
        for c in raw:
            sid = (getattr(c, "symbol_id", None) or "")
            if "MNQ" in sid.upper():
                contracts["NQ"] = {"id": str(c.id), "name": c.name or "", "symbolId": sid}
                break
    except Exception as e:
        logger.warning("NQ contract search failed: %s", e)
    try:
        raw = client.search_contracts("ES")
        for c in raw:
            sid = (getattr(c, "symbol_id", None) or "")
            if "EP" in sid.upper():
                contracts["ES"] = {"id": str(c.id), "name": c.name or "", "symbolId": sid}
                break
    except Exception as e:
        logger.warning("ES contract search failed: %s", e)
    return contracts


def fetch_quotes_via_tsxapipy(
    include_es: bool = True,
    timeout: float = QUOTE_COLLECTION_TIMEOUT_SECONDS,
    quiet: bool = False,
) -> dict[str, Any] | None:
    # Shared machine-wide token only — never tsxapipy.authenticate() (loginKey).
    from topstep_tsxapi_client import get_api_client, get_shared_token
    from tsxapipy.real_time.data_stream import DataStream
    t0 = time.time()

    try:
        import topstep_market_data_smoke as topstep_md

        blockers = topstep_md.safety_blockers()
        if blockers:
            if not quiet:
                print(f"[tsxapi] Blocked by safety: {blockers}", file=sys.stderr)
            return None
    except Exception as e:
        if not quiet:
            print(f"[tsxapi] Safety check failed: {e}", file=sys.stderr)
        return None

    try:
        token = get_shared_token()
        api_client = get_api_client()
    except Exception as e:
        if not quiet:
            print(f"[tsxapi] Shared-cache auth failed: {e}", file=sys.stderr)
        return None
    if not token:
        if not quiet:
            print("[tsxapi] Auth returned empty token", file=sys.stderr)
        return None

    contracts = _resolve_contracts(token)
    if "NQ" not in contracts:
        if not quiet:
            print("[tsxapi] Could not resolve NQ contract", file=sys.stderr)
        return None

    specs = [("NQ", contracts["NQ"])]
    if include_es and "ES" in contracts:
        specs.append(("ES", contracts["ES"]))

    collected: dict[str, dict[str, Any]] = {}
    per_symbol_timeout = max(timeout / max(len(specs), 1), 4.0)

    for label, contract in specs:
        contract_id = contract["id"]
        quote_event = Event()
        latest_quote: dict[str, Any] = {}

        def on_quote(q: dict[str, Any]) -> None:
            nonlocal latest_quote
            latest_quote = q
            quote_event.set()

        def on_error(e: Any) -> None:
            if not quiet:
                print(f"[tsxapi] Stream error for {label}: {e}", file=sys.stderr)

        stream = DataStream(
            api_client=api_client,
            contract_id_to_subscribe=contract_id,
            on_quote_callback=on_quote,
            on_error_callback=on_error,
            auto_subscribe_quotes=True,
            auto_subscribe_trades=False,
            auto_subscribe_depth=False,
        )
        if not stream.start():
            if not quiet:
                print(f"[tsxapi] Failed to start DataStream for {label}", file=sys.stderr)
            continue

        got_quote = quote_event.wait(timeout=per_symbol_timeout)
        stream.stop()

        if got_quote and latest_quote:
            collected[label] = {
                "contract_id": contract_id,
                "contract_name": contract.get("name"),
                "contract_symbol": contract.get("symbolId"),
                "quote": latest_quote,
            }

    if not collected:
        if not quiet:
            print("[tsxapi] No quotes collected", file=sys.stderr)
        return None

    elapsed_ms = round((time.time() - t0) * 1000)
    nq_data = collected.get("NQ", {})
    es_data = collected.get("ES", {})
    nq_quote = nq_data.get("quote", {}) or {}
    es_quote = es_data.get("quote", {}) or {}

    def qp(q: dict[str, Any]) -> float | None:
        if q.get("lastPrice") is not None:
            return float(q["lastPrice"])
        bid = q.get("bestBid")
        ask = q.get("bestAsk")
        if bid is not None and ask is not None:
            return (float(bid) + float(ask)) / 2
        if bid is not None:
            return float(bid)
        if ask is not None:
            return float(ask)
        return None

    return {
        "timestamp": now_utc().isoformat(),
        "source": "topstep_realtime",
        "original_source": "topstep_realtime",
        "execution_grade": True,
        "execution_block_reason": None,
        "price_nq": qp(nq_quote),
        "price_es": qp(es_quote),
        "bid_nq": nq_quote.get("bestBid"),
        "ask_nq": nq_quote.get("bestAsk"),
        "bid_es": es_quote.get("bestBid"),
        "ask_es": es_quote.get("bestAsk"),
        "volume_nq": nq_quote.get("volume"),
        "volume_es": es_quote.get("volume"),
        "contract_nq": nq_data.get("contract_id"),
        "contract_es": es_data.get("contract_id"),
        "update_mode_nq": "broker_realtime_signalr",
        "update_mode_es": "broker_realtime_signalr",
        "latency_ms": elapsed_ms,
        "provider": "tsxapipy (ProjectX / TopstepX)",
    }


def parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def check_state_freshness(state_file: Path = STATE_FILE, max_age_seconds: int = FRESH_SECONDS) -> dict[str, Any]:
    now = now_utc()
    if not state_file.exists():
        return {"timestamp": now.isoformat(), "stateFile": str(state_file), "fresh": False, "source": None, "execution_grade": False, "age_seconds": None, "reason": "state file missing"}
    try:
        payload = json.loads(state_file.read_text())
    except Exception as exc:
        return {"timestamp": now.isoformat(), "stateFile": str(state_file), "fresh": False, "source": None, "execution_grade": False, "age_seconds": None, "reason": f"state file unreadable: {exc.__class__.__name__}"}
    quote_ts = parse_timestamp(payload.get("timestamp"))
    age = None if quote_ts is None else (now - quote_ts).total_seconds()
    fresh = payload.get("source") == "topstep_realtime" and payload.get("execution_grade") is True and payload.get("price_nq") is not None and age is not None and age <= max_age_seconds
    reasons = []
    if payload.get("source") != "topstep_realtime": reasons.append("source is not topstep_realtime")
    if payload.get("execution_grade") is not True: reasons.append("execution_grade is not true")
    if payload.get("price_nq") is None: reasons.append("price_nq missing")
    if age is None: reasons.append("timestamp missing or invalid")
    elif age > max_age_seconds: reasons.append(f"stale by {round(age - max_age_seconds, 1)}s")
    return {"timestamp": now.isoformat(), "stateFile": str(state_file), "fresh": fresh, "source": payload.get("source"), "execution_grade": payload.get("execution_grade"), "price_nq": payload.get("price_nq"), "price_es": payload.get("price_es"), "contract_nq": payload.get("contract_nq"), "contract_es": payload.get("contract_es"), "age_seconds": None if age is None else round(age, 3), "max_age_seconds": max_age_seconds, "reason": "fresh topstep realtime state" if fresh else "; ".join(reasons)}


def main() -> int:
    parser = argparse.ArgumentParser(description="TopstepX/ProjectX real-time quote fetcher (tsxapipy backend)")
    parser.add_argument("--quiet", "-q", action="store_true", help="Suppress stderr output")
    parser.add_argument("--include-es", action="store_true", default=True, help="Include ES quotes (default: true)")
    parser.add_argument("--check", action="store_true", help="Check cached quote freshness without opening a TopstepX session")
    parser.add_argument("--max-age-seconds", type=int, default=FRESH_SECONDS, help=f"Freshness threshold for --check (default: {FRESH_SECONDS})")
    args = parser.parse_args()
    if args.check:
        result = check_state_freshness(max_age_seconds=args.max_age_seconds)
        print(json.dumps(result, indent=2, default=str))
        return 0 if result["fresh"] else 1
    result = fetch_quotes_via_tsxapipy(include_es=args.include_es, quiet=args.quiet, timeout=QUOTE_COLLECTION_TIMEOUT_SECONDS)
    if result is None:
        print(json.dumps({"timestamp": now_utc().isoformat(), "source": "none", "error": "tsxapipy real-time data fetch failed", "price_nq": None, "price_es": None}))
        return 1
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
