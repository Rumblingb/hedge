#!/usr/bin/env python3
"""Research-only Databento live data smoke.

This proves whether the Mac can receive execution-grade NQ/ES live quotes from
Databento without writing the canonical realtime quote state and without
touching any broker/order route.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, time, timezone
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.realtime_data_bridge import DATABENTO_DATASET, DATABENTO_SCHEMA, fetch_databento_realtime

STATE = ROOT / ".rumbling-hedge" / "state"
DEFAULT_OUTPUT = STATE / "databento-realtime-smoke.latest.json"

SAFETY_ENV = {
    "BILL_ENABLE_FUTURES_DEMO_EXECUTION": "false",
    "RH_TOPSTEP_READ_ONLY": "true",
    "RH_LIVE_EXECUTION_ENABLED": "false",
}
RESEARCH_ENV_KEYS = tuple(SAFETY_ENV) + (
    "BILL_DATABENTO_REALTIME_ENABLED",
    "BILL_DATABENTO_DATASET",
    "BILL_DATABENTO_SCHEMA",
)

EASTERN = ZoneInfo("America/New_York")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def globex_equity_index_session(now: datetime | None = None) -> dict[str, Any]:
    """Approximate CME Globex session for NQ/ES.

    NQ/ES trade nearly 24h from Sunday evening through Friday afternoon, with a
    daily maintenance break around 17:00-18:00 New York time. This is only a
    smoke-test hint, not an exchange holiday calendar.
    """
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    eastern = now.astimezone(EASTERN)
    weekday = eastern.weekday()  # Monday=0, Sunday=6
    local_t = eastern.time()

    likely_open = True
    reason = "within normal Globex equity-index session"
    if weekday == 5:
        likely_open = False
        reason = "Saturday Globex closure"
    elif weekday == 6 and local_t < time(18, 0):
        likely_open = False
        reason = "Sunday before the usual 18:00 ET Globex open"
    elif weekday == 4 and local_t >= time(17, 0):
        likely_open = False
        reason = "Friday after the usual 17:00 ET Globex close"
    elif weekday in {0, 1, 2, 3, 6} and time(17, 0) <= local_t < time(18, 0):
        likely_open = False
        reason = "daily Globex maintenance break around 17:00-18:00 ET"

    return {
        "market": "CME Globex equity-index futures",
        "timezone": "America/New_York",
        "utcTimestamp": now.astimezone(timezone.utc).isoformat(),
        "easternTimestamp": eastern.isoformat(),
        "likelyOpen": likely_open,
        "reason": reason,
        "holidayCalendarApplied": False,
    }


def force_data_only_env() -> None:
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


def summarize_quote(result: dict[str, Any] | None, session: dict[str, Any]) -> dict[str, Any]:
    if result is None:
        closed = session.get("likelyOpen") is False
        return {
            "status": "NO_QUOTES_MARKET_CLOSED" if closed else "NO_QUOTES",
            "readyForExecutionDataProof": False,
            "reason": (
                f"Databento did not produce both NQ/ES quotes inside the smoke timeout; market likely closed: {session.get('reason')}."
                if closed
                else "Databento did not produce both NQ/ES quotes inside the smoke timeout."
            ),
        }

    execution_grade = result.get("execution_grade") is True
    has_prices = result.get("price_nq") is not None and result.get("price_es") is not None
    source_ok = result.get("source") == "databento_realtime"
    passed = bool(execution_grade and has_prices and source_ok)
    return {
        "status": "PASS" if passed else "BLOCKED",
        "readyForExecutionDataProof": passed,
        "source": result.get("source"),
        "executionGrade": execution_grade,
        "executionBlockReason": result.get("execution_block_reason"),
        "priceNqPresent": result.get("price_nq") is not None,
        "priceEsPresent": result.get("price_es") is not None,
        "bidAskNqPresent": result.get("bid_nq") is not None and result.get("ask_nq") is not None,
        "bidAskEsPresent": result.get("bid_es") is not None and result.get("ask_es") is not None,
        "eventTsNq": result.get("event_ts_nq"),
        "eventTsEs": result.get("event_ts_es"),
        "latencyMs": result.get("latency_ms"),
        "dataset": result.get("databento_dataset"),
        "schema": result.get("databento_schema"),
        "reason": None if passed else "Databento quote payload did not satisfy source/execution-grade/price checks.",
    }


def build_report(
    *,
    timeout_seconds: float,
    fetcher: Callable[..., dict[str, Any] | None] = fetch_databento_realtime,
    now: datetime | None = None,
) -> dict[str, Any]:
    previous_env = {key: os.environ.get(key) for key in RESEARCH_ENV_KEYS}
    force_data_only_env()
    started = utc_now()
    session = globex_equity_index_session(now)
    try:
        result = fetcher(quiet=True, timeout_seconds=timeout_seconds)
        databento_opt_in = {
            "BILL_DATABENTO_REALTIME_ENABLED": os.environ.get("BILL_DATABENTO_REALTIME_ENABLED"),
            "BILL_DATABENTO_DATASET": os.environ.get("BILL_DATABENTO_DATASET"),
            "BILL_DATABENTO_SCHEMA": os.environ.get("BILL_DATABENTO_SCHEMA"),
        }
    finally:
        restore_env(previous_env)
    summary = summarize_quote(result, session)
    return {
        "command": "databento-realtime-smoke",
        "generatedAt": utc_now(),
        "startedAt": started,
        "timeoutSeconds": timeout_seconds,
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "writesRealtimeQuoteState": False,
        "safeEnv": dict(SAFETY_ENV),
        "databentoProcessOptIn": databento_opt_in,
        "session": session,
        "status": summary["status"],
        "readyForExecutionDataProof": summary["readyForExecutionDataProof"],
        "quoteSummary": summary,
        "promotionRule": (
            "This smoke alone does not approve trading. The bridge must later write "
            "realtime-quote.latest.json with source=databento_realtime and "
            "execution_grade=true, and data_freshness_gate must return PASS."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a research-only Databento live quote smoke.")
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
