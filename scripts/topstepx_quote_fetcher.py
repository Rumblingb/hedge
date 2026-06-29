#!/usr/bin/env python3
"""TopstepX/ProjectX real-time quote fetcher for NQ/ES.

Connects to the ProjectX SignalR market-data hub, subscribes to contract
quotes, and returns structured price data. Does NOT place, modify, or cancel
orders. This is the PRIMARY real-time data source for the bridge, replacing
Databento.

Usage:
    python3 scripts/topstepx_quote_fetcher.py [--quiet] [--include-es]
    python3 scripts/topstepx_quote_fetcher.py --check  # freshness check

Output format (stdout JSON):
    {
        "timestamp": "2026-06-29T15:10:00.123456+00:00",
        "source": "topstep_realtime",
        "price_nq": 20123.5,
        "price_es": 5512.25,
        "bid_nq": 20123.25,
        "ask_nq": 20123.75,
        "bid_es": 5512.0,
        "ask_es": 5512.5,
        "volume_nq": 12345,
        "volume_es": 6789,
        "update_mode_nq": "broker_realtime_signalr",
        "update_mode_es": "broker_realtime_signalr",
        "latency_ms": 42,
        "contract_nq": "CON.F.US.MNQ.U26",
        "contract_es": "CON.F.US.EP.U26"
    }
"""

from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

# Safe env overrides: the quote fetcher is purely read-only (SignalR market hub only).
# Override safety gates so we can connect without placing orders.
os.environ.setdefault("BILL_ENABLE_FUTURES_DEMO_EXECUTION", "false")
os.environ.setdefault("RH_TOPSTEP_READ_ONLY", "true")
os.environ.setdefault("RH_LIVE_EXECUTION_ENABLED", "false")

import topstep_market_data_smoke as md  # noqa: E402

STATE = ROOT / ".rumbling-hedge" / "state"
STATE_FILE = STATE / "realtime-quote.latest.json"
MARKET_HUB_URL = "wss://rtc.topstepx.com/hubs/market"
RECORD_SEPARATOR = "\x1e"
QUOTE_COLLECTION_TIMEOUT_SECONDS = 8.0
FRESH_SECONDS = 60

# Contract specs: (label, search_text, symbol_id)
NQ_SPEC = ("NQ", "NQ", "F.US.MNQ")  # Use MNQ for contract search (Micro)
ES_SPEC = ("ES", "ES", "F.US.EP")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def signalr_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, separators=(",", ":")) + RECORD_SEPARATOR


def parse_signalr_records(raw: str | bytes) -> list[dict[str, Any]]:
    text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
    records: list[dict[str, Any]] = []
    for item in text.split(RECORD_SEPARATOR):
        if not item:
            continue
        try:
            parsed = json.loads(item)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            records.append(parsed)
    return records


def subscribe_messages(contract_id: str, start_invocation: int) -> tuple[list[str], int]:
    """Build SignalR subscription messages for quotes + trades for a contract."""
    messages: list[str] = []
    invocation = start_invocation
    for target in ["SubscribeContractQuotes", "SubscribeContractTrades"]:
        messages.append(
            signalr_payload({
                "type": 1,
                "invocationId": str(invocation),
                "target": target,
                "arguments": [contract_id],
            })
        )
        invocation += 1
    return messages, invocation


def try_websocket(url: str, messages: list[str], timeout: float) -> bytes | None:
    """Open a WebSocket, send messages, collect responses."""
    try:
        import websocket  # noqa: F811
    except ImportError:
        return None

    collected: list[bytes] = []
    end_by = time.time() + timeout
    received_any = [False]

    def on_message(ws: Any, raw: bytes | str) -> None:
        if isinstance(raw, str):
            raw = raw.encode("utf-8")
        collected.append(raw)
        decoded = raw.decode("utf-8", errors="replace")
        # Check for quote data — we have enough after first quote + trade
        if "GatewayQuote" in decoded:
            received_any[0] = True

    def on_error(ws: Any, error: Any) -> None:
        pass  # Silently handle — we'll timeout if needed

    def on_close(ws: Any, close_status_code: Any, close_msg: Any) -> None:
        pass

    try:
        ws = websocket.WebSocket(sslopt={"cert_reqs": ssl.CERT_NONE})
        ws.settimeout(min(timeout, 15))
        ws.connect(url, timeout=min(timeout, 15))
    except ImportError:
        return None
    except Exception:
        return None

    # SignalR handshake: client MUST initiate with protocol negotiation
    try:
        handshake_msg = signalr_payload({"protocol": "json", "version": 1})
        ws.send(handshake_msg)
    except Exception:
        try: ws.close()
        except Exception: pass
        return None

    # Wait for handshake response (should be {} or 0-length)
    nego_end = time.time() + 5
    handshake_done = False
    handshake_response = b""
    while time.time() < nego_end:
        try:
            ws.settimeout(2)
            raw = ws.recv()
            if isinstance(raw, (bytes, str)):
                handshake_response += raw if isinstance(raw, bytes) else raw.encode("utf-8")
                records = parse_signalr_records(handshake_response)
                for rec in records:
                    if rec == {} or rec.get("type") == 6:
                        handshake_done = True
                        break
                if handshake_done:
                    break
        except Exception:
            break

    if not handshake_done:
        try:
            ws.close()
        except Exception:
            pass
        return None

    # Send all subscription messages
    for msg in messages:
        try:
            ws.send(msg)
        except Exception:
            break

    # Collect data until timeout or enough
    while time.time() < end_by:
        try:
            remaining = max(0.1, end_by - time.time())
            ws.settimeout(remaining)
            raw = ws.recv()
            if isinstance(raw, (bytes, str)):
                raw_bytes = raw if isinstance(raw, bytes) else raw.encode("utf-8")
                collected.append(raw_bytes)
        except Exception:
            break

    try:
        ws.close()
    except Exception:
        pass

    if not collected:
        return None
    return b"".join(collected)


def extract_quote(raw: bytes, contract_id: str) -> dict[str, Any] | None:
    """Extract the most recent GatewayQuote for a specific contract."""
    records = parse_signalr_records(raw)
    best_quote: dict[str, Any] | None = None
    for rec in records:
        if rec.get("type") != 1 or rec.get("target") != "GatewayQuote":
            continue
        args = rec.get("arguments")
        if not isinstance(args, list) or len(args) < 2:
            continue
        if str(args[0]) != contract_id:
            continue
        data = args[1] if isinstance(args[1], dict) else {}
        best_quote = data  # Last one wins (most recent)
    return best_quote


def collect_quotes(token: str, label: str, spec: tuple[str, ...],
                   url: str, timeout: float) -> dict[str, Any] | None:
    """Collect real-time quote for one symbol via SignalR."""
    search_text = spec[1]
    symbol_id = spec[2]

    contracts = md.search_contracts(token, search_text, live=False)
    contract = md.pick_active_contract(contracts, symbol_id)
    if not contract:
        return None

    contract_id = str(contract["id"])
    messages, _ = subscribe_messages(contract_id, 1)
    raw = try_websocket(url, messages, timeout)
    if not raw:
        return None

    quote = extract_quote(raw, contract_id)
    if not quote:
        return None

    return {
        "label": label,
        "contract_id": contract_id,
        "contract_name": contract.get("name"),
        "contract_symbol": contract.get("symbolId"),
        "quote": quote,
    }


def fetch_topstepx_quotes(quiet: bool = False, include_es: bool = True,
                          timeout: float = QUOTE_COLLECTION_TIMEOUT_SECONDS) -> dict[str, Any] | None:
    """Fetch real-time NQ (and optionally ES) quotes from TopstepX/ProjectX.

    Returns structured quote data matching the realtime_data_bridge format,
    or None if all sources fail.
    """
    t0 = time.time()

    # Check safety blockers first
    blockers = md.safety_blockers()
    if blockers:
        if not quiet:
            print(f"[topstepx] Safety blockers: {'; '.join(blockers)}", file=sys.stderr)
        return None

    try:
        token = md.login()
    except Exception as e:
        if not quiet:
            print(f"[topstepx] Login failed: {e}", file=sys.stderr)
        return None

    # Build the SignalR URL with auth token
    encoded_token = quote(token, safe="")
    url = f"{MARKET_HUB_URL}?access_token={encoded_token}"

    specs = [NQ_SPEC]
    if include_es:
        specs.append(ES_SPEC)

    results: dict[str, dict[str, Any]] = {}
    per_symbol_timeout = max(timeout / max(len(specs), 1), 3.0)

    for spec in specs:
        label = spec[0]
        try:
            result = collect_quotes(token, label, spec, url, per_symbol_timeout)
            if result:
                results[label] = result
        except Exception as e:
            if not quiet:
                print(f"[topstepx] {label} quote failed: {e}", file=sys.stderr)

    if not results:
        if not quiet:
            print("[topstepx] No quotes collected from any symbol", file=sys.stderr)
        return None

    elapsed_ms = round((time.time() - t0) * 1000)
    nq_data = results.get("NQ", {})
    es_data = results.get("ES", {})

    nq_quote = nq_data.get("quote", {}) if nq_data else {}
    es_quote = es_data.get("quote", {}) if es_data else {}

    def quote_price(quote: dict[str, Any]) -> float | None:
        if quote.get("lastPrice") is not None:
            return float(quote["lastPrice"])
        bid = quote.get("bestBid")
        ask = quote.get("bestAsk")
        if bid is not None and ask is not None:
            return (float(bid) + float(ask)) / 2
        if bid is not None:
            return float(bid)
        if ask is not None:
            return float(ask)
        return None

    output = {
        "timestamp": now_utc().isoformat(),
        "source": "topstep_realtime",
        "original_source": "topstep_realtime",
        "execution_grade": True,
        "execution_block_reason": None,
        "price_nq": quote_price(nq_quote),
        "price_es": quote_price(es_quote),
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
        "provider": "ProjectX / TopstepX",
    }

    return output


def parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def check_state_freshness(state_file: Path = STATE_FILE, max_age_seconds: int = FRESH_SECONDS) -> dict[str, Any]:
    """Inspect the cached TopstepX quote state without opening a broker session."""
    now = now_utc()
    if not state_file.exists():
        return {
            "timestamp": now.isoformat(),
            "stateFile": str(state_file),
            "fresh": False,
            "source": None,
            "execution_grade": False,
            "age_seconds": None,
            "reason": "state file missing",
        }

    try:
        payload = json.loads(state_file.read_text())
    except Exception as exc:
        return {
            "timestamp": now.isoformat(),
            "stateFile": str(state_file),
            "fresh": False,
            "source": None,
            "execution_grade": False,
            "age_seconds": None,
            "reason": f"state file unreadable: {exc.__class__.__name__}",
        }

    quote_ts = parse_timestamp(payload.get("timestamp"))
    age_seconds = None if quote_ts is None else (now - quote_ts).total_seconds()
    source = payload.get("source")
    execution_grade = payload.get("execution_grade") is True
    has_price = payload.get("price_nq") is not None
    fresh = (
        source == "topstep_realtime"
        and execution_grade
        and has_price
        and age_seconds is not None
        and age_seconds <= max_age_seconds
    )
    reasons: list[str] = []
    if source != "topstep_realtime":
        reasons.append("source is not topstep_realtime")
    if not execution_grade:
        reasons.append("execution_grade is not true")
    if not has_price:
        reasons.append("price_nq missing")
    if age_seconds is None:
        reasons.append("timestamp missing or invalid")
    elif age_seconds > max_age_seconds:
        reasons.append(f"stale by {round(age_seconds - max_age_seconds, 1)}s")

    return {
        "timestamp": now.isoformat(),
        "stateFile": str(state_file),
        "fresh": fresh,
        "source": source,
        "execution_grade": execution_grade,
        "price_nq": payload.get("price_nq"),
        "price_es": payload.get("price_es"),
        "contract_nq": payload.get("contract_nq"),
        "contract_es": payload.get("contract_es"),
        "age_seconds": None if age_seconds is None else round(age_seconds, 3),
        "max_age_seconds": max_age_seconds,
        "reason": "fresh topstep realtime state" if fresh else "; ".join(reasons),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="TopstepX/ProjectX real-time quote fetcher")
    parser.add_argument("--quiet", "-q", action="store_true", help="Suppress stderr output")
    parser.add_argument("--include-es", action="store_true", default=True,
                        help="Include ES quotes (default: true)")
    parser.add_argument("--check", action="store_true",
                        help="Check cached quote freshness without opening a TopstepX session")
    parser.add_argument("--max-age-seconds", type=int, default=FRESH_SECONDS,
                        help=f"Freshness threshold for --check (default: {FRESH_SECONDS})")
    args = parser.parse_args()

    if args.check:
        result = check_state_freshness(max_age_seconds=args.max_age_seconds)
        print(json.dumps(result, indent=2, default=str))
        return 0 if result["fresh"] else 1

    result = fetch_topstepx_quotes(quiet=args.quiet, include_es=args.include_es)

    if result is None:
        print(json.dumps({
            "timestamp": now_utc().isoformat(),
            "source": "none",
            "error": "TopstepX real-time data fetch failed",
            "price_nq": None,
            "price_es": None,
        }))
        return 1

    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
