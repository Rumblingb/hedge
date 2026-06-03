#!/usr/bin/env python3
"""Read-only TopstepX/ProjectX realtime market-data proof.

This script connects only to the ProjectX market SignalR hub and subscribes to
contract quotes/trades/depth. It never uses the user hub and never places,
modifies, or cancels orders. The output is evidence for the realtime data
blocker; it does not write the canonical execution quote state.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import topstep_market_data_smoke as topstep_md  # noqa: E402


STATE = ROOT / ".rumbling-hedge" / "state"
OUT = STATE / "topstep-realtime-proof.latest.json"
REALTIME_QUOTE_OUT = STATE / "realtime-quote.latest.json"
LEGACY_STATE = Path.home() / ".rumbling-hedge" / "state"
MARKET_HUB_URL = "wss://rtc.topstepx.com/hubs/market"
RECORD_SEPARATOR = "\x1e"
EVENT_TARGETS = {"GatewayQuote", "GatewayTrade", "GatewayDepth"}
BASE_CONTRACT_SPECS = [("NQ", "NQ", "F.US.ENQ"), ("MNQ", "NQ", "F.US.MNQ")]
ES_CONTRACT_SPECS = [("ES", "ES", "F.US.EP")]


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


def parse_event_timestamp(value: Any) -> str | None:
    if isinstance(value, dict):
        for key in ["timestamp", "lastUpdated", "creationTimestamp", "updateTimestamp"]:
            if value.get(key):
                return str(value[key])
    return None


def parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def blank_event_summary(contract: dict[str, Any]) -> dict[str, Any]:
    return {
        "contractId": contract.get("id"),
        "symbolId": contract.get("symbolId"),
        "name": contract.get("name"),
        "quotes": 0,
        "trades": 0,
        "depth": 0,
        "lastQuoteTimestamp": None,
        "lastTradeTimestamp": None,
        "lastDepthTimestamp": None,
        "lastQuoteSample": None,
        "lastTradeSample": None,
        "lastDepthSample": None,
    }


def summarize_record(record: dict[str, Any], contracts_by_id: dict[str, str], symbols: dict[str, dict[str, Any]]) -> bool:
    if record.get("type") != 1 or record.get("target") not in EVENT_TARGETS:
        return False
    args = record.get("arguments")
    if not isinstance(args, list) or len(args) < 2:
        return False
    contract_id = str(args[0])
    label = contracts_by_id.get(contract_id)
    if not label:
        return False
    data = args[1] if isinstance(args[1], dict) else {}
    summary = symbols[label]
    target = record.get("target")
    if target == "GatewayQuote":
        summary["quotes"] += 1
        summary["lastQuoteTimestamp"] = parse_event_timestamp(data)
        summary["lastQuoteSample"] = compact_sample(data, ["symbol", "symbolName", "lastPrice", "bestBid", "bestAsk", "volume", "timestamp"])
    elif target == "GatewayTrade":
        summary["trades"] += 1
        summary["lastTradeTimestamp"] = parse_event_timestamp(data)
        summary["lastTradeSample"] = compact_sample(data, ["symbolId", "price", "volume", "timestamp"])
    elif target == "GatewayDepth":
        summary["depth"] += 1
        summary["lastDepthTimestamp"] = parse_event_timestamp(data)
        summary["lastDepthSample"] = compact_sample(data, ["timestamp", "type", "price", "volume", "currentVolume"])
    return True


def compact_sample(data: dict[str, Any], keys: list[str]) -> dict[str, Any]:
    return {key: data.get(key) for key in keys if key in data}


def contract_specs(include_es: bool) -> list[tuple[str, str, str]]:
    return BASE_CONTRACT_SPECS + (ES_CONTRACT_SPECS if include_es else [])


def select_contracts(token: str, search_text: str, live: bool, include_es: bool = False) -> dict[str, dict[str, Any]]:
    contracts_by_search: dict[str, list[dict[str, Any]]] = {}
    selected: dict[str, dict[str, Any]] = {}
    for label, search, symbol_id in contract_specs(include_es):
        if search not in contracts_by_search:
            contracts_by_search[search] = topstep_md.search_contracts(token, search_text if search == "NQ" else search, live=live)
        contracts = contracts_by_search[search]
        contract = topstep_md.pick_active_contract(contracts, symbol_id)
        if contract:
            selected[label] = contract
    return selected


def build_realtime_quote_state(report: dict[str, Any], generated_at: str) -> dict[str, Any] | None:
    symbols = report.get("symbols") if isinstance(report.get("symbols"), dict) else {}
    nq = symbols.get("NQ") if isinstance(symbols.get("NQ"), dict) else {}
    es = symbols.get("ES") if isinstance(symbols.get("ES"), dict) else {}
    nq_quote = nq.get("lastQuoteSample") if isinstance(nq.get("lastQuoteSample"), dict) else {}
    es_quote = es.get("lastQuoteSample") if isinstance(es.get("lastQuoteSample"), dict) else {}
    nq_price = quote_price(nq_quote)
    es_price = quote_price(es_quote)
    if nq_price is None or es_price is None:
        return None
    quote_times = [
        parse_dt(nq.get("lastQuoteTimestamp")),
        parse_dt(es.get("lastQuoteTimestamp")),
    ]
    quote_times = [item for item in quote_times if item is not None]
    timestamp = min(quote_times).isoformat() if quote_times else generated_at
    return {
        "timestamp": timestamp,
        "bridge_generated_at": generated_at,
        "source": "topstep_realtime",
        "original_source": "topstep_realtime",
        "execution_grade": True,
        "execution_block_reason": None,
        "update_mode_nq": "broker_realtime_signalr",
        "update_mode_es": "broker_realtime_signalr",
        "price_nq": nq_price,
        "price_es": es_price,
        "bid_nq": nq_quote.get("bestBid"),
        "ask_nq": nq_quote.get("bestAsk"),
        "bid_es": es_quote.get("bestBid"),
        "ask_es": es_quote.get("bestAsk"),
        "volume_nq": nq_quote.get("volume"),
        "volume_es": es_quote.get("volume"),
        "provider": "ProjectX / TopstepX",
        "brokerTouchMode": report.get("brokerTouchMode"),
        "researchOnly": True,
        "writesOrders": False,
        "placesOrders": False,
        "modifiesOrders": False,
        "cancelsOrders": False,
        "readyForExecution": False,
        "proofStatePath": str(OUT),
        "promotionRule": (
            "Execution remains blocked unless daily route approval, broker reconciliation, source hygiene, "
            "strategy gates, and execution firewalls also pass."
        ),
    }


def quote_price(sample: dict[str, Any]) -> float | int | None:
    if sample.get("lastPrice") is not None:
        return sample.get("lastPrice")
    bid = sample.get("bestBid")
    ask = sample.get("bestAsk")
    if bid is None and ask is None:
        return None
    if bid is None:
        return ask
    if ask is None:
        return bid
    try:
        return (float(bid) + float(ask)) / 2
    except (TypeError, ValueError):
        return None


def write_realtime_quote_state(payload: dict[str, Any]) -> None:
    REALTIME_QUOTE_OUT.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    REALTIME_QUOTE_OUT.write_text(text, encoding="utf-8")
    LEGACY_STATE.mkdir(parents=True, exist_ok=True)
    (LEGACY_STATE / "realtime-quote.latest.json").write_text(text, encoding="utf-8")


def build_report(args: argparse.Namespace, connector: Any | None = None) -> dict[str, Any]:
    started = now_utc()
    blockers = topstep_md.safety_blockers()
    report: dict[str, Any] = {
        "command": "topstep-realtime-proof",
        "generatedAt": started.isoformat(),
        "researchOnly": True,
        "writesOrders": False,
        "placesOrders": False,
        "modifiesOrders": False,
        "cancelsOrders": False,
        "touchesBroker": True,
        "brokerTouchMode": "read-only-market-realtime",
        "writesRealtimeQuoteState": bool(getattr(args, "write_realtime_quote_state", False)),
        "readyForExecution": False,
        "readyForDemoExpansion": False,
        "durationSeconds": args.duration_sec,
        "safeEnv": dict(topstep_md.SAFE_ENV),
        "officialDocs": {
            "projectxRealtime": "https://gateway.docs.projectx.com/docs/realtime/",
        },
        "symbols": {},
        "blockers": blockers,
        "topstepSessionSafety": topstep_md.topstep_session_safety_summary(),
    }
    if blockers:
        report["status"] = "BLOCKED_BY_SAFETY_ENV"
        report["readyForExecutionDataProof"] = False
        return report

    try:
        token = topstep_md.login()
        selected = select_contracts(token, args.search_text, live=args.live, include_es=bool(getattr(args, "include_es", False)))
        if not selected:
            report["status"] = "NO_ACTIVE_CONTRACTS"
            report["readyForExecutionDataProof"] = False
            report["blockers"].append("no active NQ/MNQ contracts returned from read-only contract search")
            return report

        for label, contract in selected.items():
            report["symbols"][label] = blank_event_summary(contract)

        contracts_by_id = {str(contract.get("id")): label for label, contract in selected.items()}
        connector = connector or import_websocket_connector()
        url = f"{MARKET_HUB_URL}?access_token={quote(token)}"
        ws = connector(url, timeout=args.connect_timeout_sec)
        try:
            ws.settimeout(args.recv_timeout_sec)
            ws.send(signalr_payload({"protocol": "json", "version": 1}))
            invocation = 1
            for contract in selected.values():
                messages, invocation = subscribe_messages(str(contract.get("id")), invocation)
                for message in messages:
                    ws.send(message)

            deadline = time.monotonic() + args.duration_sec
            raw_messages = 0
            parsed_messages = 0
            market_events = 0
            completions = []
            last_error = None
            while time.monotonic() < deadline:
                try:
                    raw = ws.recv()
                except Exception as exc:
                    last_error = str(exc)
                    continue
                raw_messages += 1
                for record in parse_signalr_records(raw):
                    parsed_messages += 1
                    if record.get("type") == 3:
                        completions.append({key: record.get(key) for key in ["invocationId", "error", "result"] if key in record})
                    if summarize_record(record, contracts_by_id, report["symbols"]):
                        market_events += 1

            quote_ready = all(int(item.get("quotes") or 0) > 0 for item in report["symbols"].values())
            any_market = any(
                int(item.get("quotes") or 0) + int(item.get("trades") or 0) + int(item.get("depth") or 0) > 0
                for item in report["symbols"].values()
            )
            report.update(
                {
                    "status": "PASS" if quote_ready else ("CONNECTED_NO_QUOTES" if any_market else "CONNECTED_NO_MARKET_EVENTS"),
                    "readyForExecutionDataProof": quote_ready,
                    "connected": True,
                    "rawMessageCount": raw_messages,
                    "parsedMessageCount": parsed_messages,
                    "marketEventCount": market_events,
                    "completionMessages": completions[-10:],
                    "lastReceiveError": last_error,
                    "promotionRule": (
                        "This proves read-only ProjectX realtime availability only. It does not clear execution until "
                        "the canonical realtime bridge writes source=topstep_realtime, execution_grade=true and the "
                        "data_freshness_gate passes with execution locks still disabled."
                    ),
                }
            )
            if not quote_ready:
                report["blockers"].append("topstep realtime quote events were not observed for every selected contract")
            if getattr(args, "write_realtime_quote_state", False):
                quote_state = build_realtime_quote_state(report, report["generatedAt"])
                if quote_state:
                    write_realtime_quote_state(quote_state)
                    report["canonicalRealtimeQuoteStateWritten"] = True
                    report["canonicalRealtimeQuoteStatePath"] = str(REALTIME_QUOTE_OUT)
                    report["canonicalRealtimeQuoteSource"] = quote_state["source"]
                else:
                    report["canonicalRealtimeQuoteStateWritten"] = False
                    report["blockers"].append("canonical quote state requires NQ and ES quote samples")
        finally:
            try:
                ws.close()
            except Exception:
                pass
    except Exception as exc:
        report["status"] = "ERROR"
        report["error"] = str(exc)
        report["readyForExecutionDataProof"] = False
    return report


def import_websocket_connector():
    try:
        import websocket
    except Exception as exc:  # pragma: no cover - import availability varies by host
        raise RuntimeError("websocket-client python module is required for ProjectX realtime proof") from exc
    return websocket.create_connection


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--search-text", default="NQ")
    parser.add_argument("--duration-sec", type=float, default=30.0)
    parser.add_argument("--connect-timeout-sec", type=float, default=10.0)
    parser.add_argument("--recv-timeout-sec", type=float, default=2.0)
    parser.add_argument("--live", action="store_true", help="Use live subscription context instead of sim context")
    parser.add_argument("--include-es", action="store_true", help="Also subscribe to ES for canonical NQ/ES freshness")
    parser.add_argument("--write-realtime-quote-state", action="store_true", help="Write canonical realtime-quote.latest.json from NQ/ES ProjectX quotes")
    return parser.parse_args()


def main() -> int:
    payload = build_report(parse_args())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload.get("readyForExecutionDataProof") else 1


if __name__ == "__main__":
    raise SystemExit(main())
