#!/usr/bin/env python3
"""Read-only TopstepX/ProjectX DOM (order-book) + tape capture.

This script connects only to the ProjectX market SignalR hub (read-only) and
subscribes to contract quotes/trades/market depth for a configurable window.
It records the full depth ladder, the trade tape, symbol/contract/venue
context, and the replay window (start/end timestamps) into repo state so the
research fabric can evaluate real order-book evidence instead of the OHLCV
DOM proxy.

Safety:
- Only ever connects to the market hub (wss://rtc.topstepx.com/hubs/market).
- Never touches the user/order hubs and never places, modifies, or cancels
  orders (account_mode is always "read-only-market-data").
- Honors the same safety_blockers() checks as topstep_realtime_proof.py /
  topstep_market_data_smoke.py (RH_TOPSTEP_READ_ONLY, kill switches, session
  safety, etc).
- Hard-capped runtime via --duration-sec (default 60s) plus a connect/recv
  timeout so a stuck socket cannot hang the cron job.
- If the market is closed / no events arrive, exits cleanly with status
  "no-data" rather than crashing or fabricating evidence.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import topstep_market_data_smoke as topstep_md  # noqa: E402


STATE = ROOT / ".rumbling-hedge" / "state"
CAPTURE_ROOT = STATE / "dom-capture"
SUMMARY_OUT = CAPTURE_ROOT.parent / "dom-capture.latest.json"
MARKET_HUB_URL = "wss://rtc.topstepx.com/hubs/market"
RECORD_SEPARATOR = "\x1e"
EVENT_TARGETS = {"GatewayQuote", "GatewayTrade", "GatewayDepth"}
VENUE = "topstepx-market-hub"
ACCOUNT_MODE = "read-only-market-data"
TAPE_SAMPLE_LIMIT = 10
RETENTION_DAYS = 7


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def split_signalr_records(raw: str | bytes) -> list[str]:
    text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
    return [part for part in text.split(RECORD_SEPARATOR) if part]


def parse_signalr_records(raw: str | bytes) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for item in split_signalr_records(raw):
        try:
            parsed = json.loads(item)
        except json.JSONDecodeError:
            records.append({"type": "unparseable", "raw": item[:120]})
            continue
        records.append(parsed if isinstance(parsed, dict) else {"type": "non-object", "raw": parsed})
    return records


def signalr_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, separators=(",", ":")) + RECORD_SEPARATOR


def subscribe_messages(contract_id: str, start_invocation: int) -> tuple[list[str], int]:
    messages: list[str] = []
    invocation = start_invocation
    for target in ["SubscribeContractQuotes", "SubscribeContractTrades", "SubscribeContractMarketDepth"]:
        messages.append(
            signalr_payload(
                {
                    "type": 1,
                    "invocationId": str(invocation),
                    "target": target,
                    "arguments": [contract_id],
                }
            )
        )
        invocation += 1
    return messages, invocation


def import_websocket_connector():
    try:
        import websocket
    except Exception as exc:  # pragma: no cover - import availability varies by host
        raise RuntimeError("websocket-client python module is required for DOM capture") from exc
    return websocket.create_connection


def select_contract(token: str, search_text: str, symbol_id: str, live: bool) -> dict[str, Any] | None:
    contracts = topstep_md.search_contracts(token, search_text, live=live)
    return topstep_md.pick_active_contract(contracts, symbol_id)


def parse_event_timestamp(value: Any) -> str | None:
    if isinstance(value, dict):
        for key in ["timestamp", "lastUpdated", "creationTimestamp", "updateTimestamp"]:
            if value.get(key):
                return str(value[key])
    return None


def best_bid_ask_from_depth(levels: list[dict[str, Any]]) -> dict[str, Any]:
    """Best-effort extraction of best bid/ask price+size from accumulated depth levels.

    ProjectX GatewayDepth events use a `type` field for side/action
    (commonly 1=Bid, 2=Ask plus add/update/remove variants). We keep the
    latest seen price/volume per (type, price) and derive best bid (max
    price among bid-type levels) and best ask (min price among ask-type
    levels).
    """
    bids: dict[float, float] = {}
    asks: dict[float, float] = {}
    # Best-of-book event types (3/4/9/10) are chronological top-of-book
    # updates, so the latest one wins; max/min over the window would report
    # a crossed book.
    last_best_bid: float | None = None
    last_best_bid_size: float | None = None
    last_best_ask: float | None = None
    last_best_ask_size: float | None = None
    for level in levels:
        price = level.get("price")
        volume = level.get("volume", level.get("currentVolume"))
        dom_type = level.get("type")
        if price is None:
            continue
        try:
            price_f = float(price)
        except (TypeError, ValueError):
            continue
        try:
            volume_f = float(volume) if volume is not None else 0.0
        except (TypeError, ValueError):
            volume_f = 0.0
        # ProjectX DomType: 1=Ask, 2=Bid, 3=BestAsk, 4=BestBid, 5=Trade,
        # 6=Reset, 7=Low, 8=High, 9=NewBestBid, 10=NewBestAsk. Observed NQ
        # streams publish mostly 3/4/5, so include the best-bid/ask variants.
        if dom_type in (2, 4, 9, "2", "4", "9", "Bid", "bid", "BestBid", "NewBestBid"):
            if dom_type in (4, 9, "4", "9", "BestBid", "NewBestBid") and volume_f > 0:
                last_best_bid = price_f
                last_best_bid_size = volume_f
            if volume_f <= 0:
                bids.pop(price_f, None)
            else:
                bids[price_f] = volume_f
        elif dom_type in (1, 3, 10, "1", "3", "10", "Ask", "ask", "Offer", "offer", "BestAsk", "NewBestAsk"):
            if dom_type in (3, 10, "3", "10", "BestAsk", "NewBestAsk") and volume_f > 0:
                last_best_ask = price_f
                last_best_ask_size = volume_f
            if volume_f <= 0:
                asks.pop(price_f, None)
            else:
                asks[price_f] = volume_f

    best_bid = last_best_bid if last_best_bid is not None else (max(bids) if bids else None)
    best_ask = last_best_ask if last_best_ask is not None else (min(asks) if asks else None)
    bid_size = last_best_bid_size if last_best_bid is not None else (bids.get(best_bid) if best_bid is not None else None)
    ask_size = last_best_ask_size if last_best_ask is not None else (asks.get(best_ask) if best_ask is not None else None)
    return {
        "best_bid": best_bid,
        "best_ask": best_ask,
        "bid_size": bid_size,
        "ask_size": ask_size,
        "ladder_levels": len(bids) + len(asks),
        "bid_levels": len(bids),
        "ask_levels": len(asks),
    }


def rotate_old_captures(retention_days: int = RETENTION_DAYS) -> list[str]:
    removed: list[str] = []
    if not CAPTURE_ROOT.exists():
        return removed
    cutoff = now_utc() - timedelta(days=retention_days)
    for child in CAPTURE_ROOT.iterdir():
        if not child.is_dir():
            continue
        try:
            day = datetime.strptime(child.name, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if day < cutoff:
            shutil.rmtree(child, ignore_errors=True)
            removed.append(str(child))
    return removed


def build_summary(
    *,
    status: str,
    symbol: str,
    contract: dict[str, Any] | None,
    window_start: datetime,
    window_end: datetime,
    capture_path: str | None,
    depth_events: int,
    trade_events: int,
    quote_events: int,
    depth_levels: list[dict[str, Any]],
    tape_sample: list[dict[str, Any]],
    blockers: list[str],
    error: str | None = None,
) -> dict[str, Any]:
    bbo = best_bid_ask_from_depth(depth_levels) if depth_levels else {
        "best_bid": None,
        "best_ask": None,
        "bid_size": None,
        "ask_size": None,
        "ladder_levels": 0,
        "bid_levels": 0,
        "ask_levels": 0,
    }
    summary: dict[str, Any] = {
        "command": "topstep-dom-capture",
        "ts": now_utc().isoformat(),
        "status": status,
        "symbol": symbol,
        "contract_id": contract.get("id") if contract else None,
        "contract_name": contract.get("name") if contract else None,
        "venue": VENUE,
        "account_mode": ACCOUNT_MODE,
        "window_start": window_start.isoformat(),
        "window_end": window_end.isoformat(),
        "depth_events": depth_events,
        "trade_events": trade_events,
        "quote_events": quote_events,
        "best_bid": bbo["best_bid"],
        "best_ask": bbo["best_ask"],
        "bid_size": bbo["bid_size"],
        "ask_size": bbo["ask_size"],
        "ladder_levels": bbo["ladder_levels"],
        "bid_levels": bbo["bid_levels"],
        "ask_levels": bbo["ask_levels"],
        "tape_sample": tape_sample[-TAPE_SAMPLE_LIMIT:],
        "capture_path": capture_path,
        "writesOrders": False,
        "touchesBroker": True,
        "researchOnly": True,
        "brokerTouchMode": ACCOUNT_MODE,
        "blockers": blockers,
    }
    if error:
        summary["error"] = error
    return summary


def write_summary(summary: dict[str, Any]) -> None:
    SUMMARY_OUT.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_OUT.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_capture(args: argparse.Namespace) -> dict[str, Any]:
    started = now_utc()
    removed = rotate_old_captures()

    blockers = topstep_md.safety_blockers()
    if blockers:
        summary = build_summary(
            status="blocked-by-safety-env",
            symbol=args.symbol,
            contract=None,
            window_start=started,
            window_end=now_utc(),
            capture_path=None,
            depth_events=0,
            trade_events=0,
            quote_events=0,
            depth_levels=[],
            tape_sample=[],
            blockers=blockers,
        )
        summary["removedCaptureDirs"] = removed
        return summary

    try:
        token = topstep_md.login()
    except Exception as exc:
        summary = build_summary(
            status="error",
            symbol=args.symbol,
            contract=None,
            window_start=started,
            window_end=now_utc(),
            capture_path=None,
            depth_events=0,
            trade_events=0,
            quote_events=0,
            depth_levels=[],
            tape_sample=[],
            blockers=[],
            error=f"login failed: {exc}",
        )
        summary["removedCaptureDirs"] = removed
        return summary

    try:
        contract = select_contract(token, args.search_text, args.symbol_id, live=args.live)
    except Exception as exc:
        summary = build_summary(
            status="error",
            symbol=args.symbol,
            contract=None,
            window_start=started,
            window_end=now_utc(),
            capture_path=None,
            depth_events=0,
            trade_events=0,
            quote_events=0,
            depth_levels=[],
            tape_sample=[],
            blockers=[],
            error=f"contract search failed: {exc}",
        )
        summary["removedCaptureDirs"] = removed
        return summary

    if not contract:
        summary = build_summary(
            status="no-data",
            symbol=args.symbol,
            contract=None,
            window_start=started,
            window_end=now_utc(),
            capture_path=None,
            depth_events=0,
            trade_events=0,
            quote_events=0,
            depth_levels=[],
            tape_sample=[],
            blockers=[f"no active {args.symbol} contract returned from read-only contract search"],
        )
        summary["removedCaptureDirs"] = removed
        return summary

    contract_id = str(contract.get("id"))
    day_dir = CAPTURE_ROOT / started.strftime("%Y-%m-%d")
    day_dir.mkdir(parents=True, exist_ok=True)
    capture_file = day_dir / f"{args.symbol}-{int(started.timestamp())}.jsonl"

    depth_events = 0
    trade_events = 0
    quote_events = 0
    depth_levels: list[dict[str, Any]] = []
    tape_sample: list[dict[str, Any]] = []
    last_error: str | None = None

    connector = import_websocket_connector()
    url = f"{MARKET_HUB_URL}?access_token={quote(token)}"
    ws = connector(url, timeout=args.connect_timeout_sec)
    fh = capture_file.open("a", encoding="utf-8")
    try:
        ws.settimeout(args.recv_timeout_sec)
        ws.send(signalr_payload({"protocol": "json", "version": 1}))
        invocation = 1
        messages, invocation = subscribe_messages(contract_id, invocation)
        for message in messages:
            ws.send(message)

        # Header line for replay context.
        fh.write(json.dumps({
            "_meta": True,
            "symbol": args.symbol,
            "contract_id": contract_id,
            "contract_name": contract.get("name"),
            "venue": VENUE,
            "account_mode": ACCOUNT_MODE,
            "window_start": started.isoformat(),
        }) + "\n")
        fh.flush()

        deadline = time.monotonic() + args.duration_sec
        while time.monotonic() < deadline:
            try:
                raw = ws.recv()
            except Exception as exc:
                last_error = str(exc)
                continue
            for record in parse_signalr_records(raw):
                if record.get("type") != 1 or record.get("target") not in EVENT_TARGETS:
                    continue
                args_field = record.get("arguments")
                if not isinstance(args_field, list) or len(args_field) < 2:
                    continue
                if str(args_field[0]) != contract_id:
                    continue
                # Depth/trade payloads arrive as a list of levels, quotes as a dict.
                data = args_field[1] if isinstance(args_field[1], (dict, list)) else {}
                target = record.get("target")
                event = {
                    "recv_at": now_utc().isoformat(),
                    "target": target,
                    "data": data,
                }
                fh.write(json.dumps(event) + "\n")

                if target == "GatewayQuote":
                    quote_events += 1
                elif target == "GatewayTrade":
                    trade_events += 1
                    items = data if isinstance(data, list) else [data]
                    for trade in items:
                        if not isinstance(trade, dict):
                            continue
                        tape_sample.append({
                            "timestamp": parse_event_timestamp(trade) or trade.get("timestamp"),
                            "price": trade.get("price"),
                            "volume": trade.get("volume"),
                            "type": trade.get("type"),
                        })
                        if len(tape_sample) > TAPE_SAMPLE_LIMIT * 4:
                            tape_sample = tape_sample[-TAPE_SAMPLE_LIMIT * 4:]
                elif target == "GatewayDepth":
                    depth_events += 1
                    items = data if isinstance(data, list) else [data]
                    for level in items:
                        if not isinstance(level, dict):
                            continue
                        depth_levels.append(level)
                    if len(depth_levels) > 2000:
                        depth_levels = depth_levels[-2000:]
            fh.flush()
    finally:
        fh.close()
        try:
            ws.close()
        except Exception:
            pass

    ended = now_utc()
    if depth_events == 0 and trade_events == 0 and quote_events == 0:
        status = "no-data"
        capture_blockers = ["no GatewayQuote/GatewayTrade/GatewayDepth events observed in capture window"]
        if last_error:
            capture_blockers.append(f"last recv error: {last_error}")
    else:
        status = "ok"
        capture_blockers = []
        if last_error:
            capture_blockers.append(f"last recv error (non-fatal): {last_error}")

    summary = build_summary(
        status=status,
        symbol=args.symbol,
        contract=contract,
        window_start=started,
        window_end=ended,
        capture_path=str(capture_file),
        depth_events=depth_events,
        trade_events=trade_events,
        quote_events=quote_events,
        depth_levels=depth_levels,
        tape_sample=tape_sample,
        blockers=capture_blockers,
    )
    summary["removedCaptureDirs"] = removed
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="NQ")
    parser.add_argument("--search-text", default="NQ")
    parser.add_argument("--symbol-id", default="F.US.ENQ")
    parser.add_argument("--duration-sec", type=float, default=60.0)
    parser.add_argument("--connect-timeout-sec", type=float, default=10.0)
    parser.add_argument("--recv-timeout-sec", type=float, default=2.0)
    parser.add_argument("--live", action="store_true", help="Use live subscription context instead of sim context")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary = run_capture(args)
    write_summary(summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary.get("status") in {"ok", "no-data"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
