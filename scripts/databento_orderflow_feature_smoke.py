#!/usr/bin/env python3
"""Research-only Databento top-of-book feature smoke.

This is the first safe step toward replacing the OHLCV DOM proxy. It reads a
Databento quote snapshot, computes book-feature candidates, and writes a
separate research artifact. It never writes canonical realtime quote state and
never approves execution.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.databento_realtime_smoke import SAFETY_ENV, globex_equity_index_session
from scripts.realtime_data_bridge import DATABENTO_DATASET, DATABENTO_SCHEMA, fetch_databento_realtime

STATE = ROOT / ".rumbling-hedge" / "state"
DEFAULT_OUTPUT = STATE / "databento-orderflow-feature-smoke.latest.json"
RESEARCH_ENV_KEYS = tuple(SAFETY_ENV) + (
    "BILL_DATABENTO_REALTIME_ENABLED",
    "BILL_DATABENTO_DATASET",
    "BILL_DATABENTO_SCHEMA",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def force_research_env() -> None:
    for key, value in SAFETY_ENV.items():
        os.environ[key] = value
    os.environ.setdefault("BILL_DATABENTO_REALTIME_ENABLED", "true")
    os.environ.setdefault("BILL_DATABENTO_DATASET", DATABENTO_DATASET)
    os.environ.setdefault("BILL_DATABENTO_SCHEMA", DATABENTO_SCHEMA)


def restore_env(previous: dict[str, str | None]) -> None:
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def number(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def symbol_features(quote: dict[str, Any], symbol: str) -> dict[str, Any]:
    key = symbol.lower()
    bid = number(quote.get(f"bid_{key}"))
    ask = number(quote.get(f"ask_{key}"))
    bid_size = number(quote.get(f"bid_size_{key}"))
    ask_size = number(quote.get(f"ask_size_{key}"))
    mid = round((bid + ask) / 2, 6) if bid is not None and ask is not None else number(quote.get(f"price_{key}"))
    spread = round(ask - bid, 6) if bid is not None and ask is not None else None
    spread_bps = round((spread / mid) * 10_000, 6) if spread is not None and mid else None
    total_size = (bid_size or 0.0) + (ask_size or 0.0)
    imbalance = round(((bid_size or 0.0) - (ask_size or 0.0)) / total_size, 6) if total_size > 0 else None
    return {
        "symbol": symbol.upper(),
        "mid": mid,
        "bid": bid,
        "ask": ask,
        "spread": spread,
        "spreadBps": spread_bps,
        "bidSize": bid_size,
        "askSize": ask_size,
        "level1SizeImbalance": imbalance,
        "hasBidAsk": bid is not None and ask is not None,
        "hasDepthSize": bid_size is not None and ask_size is not None,
        "eventTs": quote.get(f"event_ts_{key}"),
    }


def build_features(quote: dict[str, Any]) -> dict[str, Any]:
    rows = [symbol_features(quote, "NQ"), symbol_features(quote, "ES")]
    complete_bid_ask = all(row["hasBidAsk"] for row in rows)
    complete_depth = all(row["hasDepthSize"] for row in rows)
    return {
        "snapshotOnly": True,
        "featureFamily": "databento-top-of-book-mbp1",
        "rows": rows,
        "completeBidAsk": complete_bid_ask,
        "completeDepthSize": complete_depth,
        "researchUsable": complete_bid_ask,
        "domProxyReplacementReady": False,
        "reason": (
            "snapshot has bid/ask and depth sizes; next step is rolling capture plus OOS comparison against no-DOM baseline"
            if complete_bid_ask and complete_depth
            else "snapshot is missing bid/ask or depth-size fields needed for order-flow features"
        ),
    }


def build_report(
    *,
    timeout_seconds: float,
    fetcher: Callable[..., dict[str, Any] | None] = fetch_databento_realtime,
    now: datetime | None = None,
) -> dict[str, Any]:
    previous_env = {key: os.environ.get(key) for key in RESEARCH_ENV_KEYS}
    force_research_env()
    session = globex_equity_index_session(now)
    try:
        quote = fetcher(quiet=True, timeout_seconds=timeout_seconds)
        databento_opt_in = {
            "BILL_DATABENTO_REALTIME_ENABLED": os.environ.get("BILL_DATABENTO_REALTIME_ENABLED"),
            "BILL_DATABENTO_DATASET": os.environ.get("BILL_DATABENTO_DATASET"),
            "BILL_DATABENTO_SCHEMA": os.environ.get("BILL_DATABENTO_SCHEMA"),
        }
    finally:
        restore_env(previous_env)
    quote_ok = bool(quote and quote.get("source") == "databento_realtime" and quote.get("execution_grade") is True)
    if quote and quote_ok:
        features = build_features(quote)
        status = "WATCH_RESEARCH_ONLY" if features["researchUsable"] else "BLOCKED"
    else:
        features = {
            "snapshotOnly": True,
            "featureFamily": "databento-top-of-book-mbp1",
            "rows": [],
            "completeBidAsk": False,
            "completeDepthSize": False,
            "researchUsable": False,
            "domProxyReplacementReady": False,
            "reason": (
                f"Databento feature smoke could not get an execution-grade quote; market likely closed: {session.get('reason')}"
                if session.get("likelyOpen") is False
                else "Databento feature smoke could not get an execution-grade quote inside the timeout"
            ),
        }
        status = "NO_QUOTES_MARKET_CLOSED" if session.get("likelyOpen") is False else "NO_QUOTES"
    return {
        "command": "databento-orderflow-feature-smoke",
        "generatedAt": utc_now(),
        "timeoutSeconds": timeout_seconds,
        "status": status,
        "decision": "research-only-orderflow-feature-visible-execution-locked",
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "writesRealtimeQuoteState": False,
        "readyForExecution": False,
        "readyForDemoExpansion": False,
        "safeEnv": dict(SAFETY_ENV),
        "databentoProcessOptIn": databento_opt_in,
        "session": session,
        "quoteSummary": {
            "source": quote.get("source") if isinstance(quote, dict) else None,
            "executionGrade": quote.get("execution_grade") if isinstance(quote, dict) else False,
            "executionBlockReason": quote.get("execution_block_reason") if isinstance(quote, dict) else None,
            "latencyMs": quote.get("latency_ms") if isinstance(quote, dict) else None,
        },
        "features": features,
        "promotionRule": (
            "This artifact can only prove research-feature availability. DOM proxy replacement still requires rolling capture, "
            "no-lookahead replay, OOS comparison versus no-DOM baseline, costs, broker/current parity, and daily route approval."
        ),
        "nextCommands": [
            "npm run --silent bill:databento-realtime-smoke -- --timeout-sec 20",
            "npm run --silent bill:databento-orderflow-feature-smoke -- --timeout-sec 20",
            "npm run --silent bill:futures-evidence-triage",
            "npm run --silent bill:alpha-frontier-queue",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a research-only Databento order-flow feature smoke.")
    parser.add_argument("--timeout-sec", type=float, default=8.0)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    payload = build_report(timeout_seconds=args.timeout_sec)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
