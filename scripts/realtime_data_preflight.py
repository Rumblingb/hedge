#!/usr/bin/env python3
"""Summarize whether the futures realtime data path can be execution-grade.

This script is read-only: it checks local config, runtime prerequisites, and
current state artifacts. It does not connect to market data vendors and it does
not write orders.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / ".rumbling-hedge" / "state"
OUTPUT_PATH = STATE_DIR / "realtime-data-preflight.latest.json"
BILL_ENV = Path.home() / "Library" / "Application Support" / "AgentPay" / "bill" / "bill.env"
REALTIME_STATE = STATE_DIR / "realtime-quote.latest.json"
DATA_FRESHNESS_STATE = STATE_DIR / "data-freshness-gate.latest.json"
TOPSTEP_REALTIME_PROOF_STATE = STATE_DIR / "topstep-realtime-proof.latest.json"
DATABENTO_SMOKE_STATE = STATE_DIR / "databento-realtime-smoke.latest.json"
CRON_WRAPPER = ROOT / "scripts" / "realtime_cron.sh"

SECRET_KEYS = {
    "RH_TOPSTEP_API_KEY",
    "RH_TOPSTEP_USERNAME",
    "TV_SESSION",
    "TV_SESSION_SIGN",
    "TV_ECUID",
    "TV_DEVICE",
    "TV_BACKEND",
    "TV_BACKEND_SIGN",
}

DATABENTO_DATASET = "GLBX.MDP3"
DATABENTO_SCHEMA = "mbp-1"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :]
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        if key:
            values[key] = value
    return values


def safe_env_presence(env_values: dict[str, str], key: str) -> dict[str, Any]:
    value = os.environ.get(key) or env_values.get(key) or ""
    return {
        "key": key,
        "present": bool(value),
        "source": "process" if os.environ.get(key) else ("bill.env" if env_values.get(key) else "missing"),
    }


def env_value_source(env_values: dict[str, str], key: str) -> tuple[str, str | None]:
    if os.environ.get(key) is not None:
        return "process", os.environ.get(key)
    if env_values.get(key) is not None:
        return "bill.env", env_values.get(key)
    return "missing", None


def truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def non_secret_config_value(env_values: dict[str, str], key: str, default: str | None = None) -> dict[str, Any]:
    source, value = env_value_source(env_values, key)
    return {
        "key": key,
        "present": value is not None,
        "source": source,
        "value": value if value is not None else default,
        "usesDefault": value is None and default is not None,
    }


def module_available(module_name: str) -> dict[str, Any]:
    spec = importlib.util.find_spec(module_name)
    return {
        "module": module_name,
        "available": spec is not None,
        "origin": spec.origin if spec else None,
    }


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"_readError": str(exc)}


def parse_ts(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def state_summary(path: Path, now: datetime) -> dict[str, Any]:
    payload = read_json(path)
    if payload is None:
        return {"path": str(path), "present": False}
    ts = parse_ts(payload.get("timestamp") or payload.get("bridge_generated_at"))
    age = (now - ts).total_seconds() if ts else None
    return {
        "path": str(path),
        "present": True,
        "ageSeconds": round(age, 1) if age is not None else None,
        "source": payload.get("source"),
        "originalSource": payload.get("original_source"),
        "executionGrade": payload.get("execution_grade"),
        "executionBlockReason": payload.get("execution_block_reason"),
        "priceNqPresent": payload.get("price_nq") is not None,
        "priceEsPresent": payload.get("price_es") is not None,
        "readError": payload.get("_readError"),
    }


def freshness_summary(path: Path) -> dict[str, Any]:
    payload = read_json(path)
    if payload is None:
        return {"path": str(path), "present": False}
    return {
        "path": str(path),
        "present": True,
        "verdict": payload.get("verdict"),
        "action": payload.get("action"),
        "checks": [
            {
                "symbol": check.get("symbol"),
                "status": check.get("status"),
                "source": check.get("source"),
                "updateMode": check.get("update_mode"),
                "reason": check.get("reason"),
            }
            for check in payload.get("checks", [])
            if isinstance(check, dict)
        ],
        "readError": payload.get("_readError"),
    }


def topstep_realtime_proof_summary(path: Path, now: datetime) -> dict[str, Any]:
    payload = read_json(path)
    if payload is None:
        return {"path": str(path), "present": False}
    ts = parse_ts(payload.get("generatedAt"))
    age = (now - ts).total_seconds() if ts else None
    symbols = payload.get("symbols") if isinstance(payload.get("symbols"), dict) else {}
    return {
        "path": str(path),
        "present": True,
        "status": payload.get("status"),
        "readyForExecutionDataProof": bool(payload.get("readyForExecutionDataProof")),
        "ageSeconds": round(age, 1) if age is not None else None,
        "symbols": {
            label: {
                "quotes": item.get("quotes"),
                "trades": item.get("trades"),
                "depth": item.get("depth"),
                "lastQuoteTimestamp": item.get("lastQuoteTimestamp"),
            }
            for label, item in symbols.items()
            if isinstance(item, dict)
        },
        "writesOrders": payload.get("writesOrders"),
        "touchesBroker": payload.get("touchesBroker"),
        "writesRealtimeQuoteState": payload.get("writesRealtimeQuoteState"),
        "readError": payload.get("_readError"),
    }


def databento_smoke_summary(path: Path) -> dict[str, Any]:
    payload = read_json(path)
    if payload is None:
        return {"path": str(path), "present": False}
    quote_summary = payload.get("quoteSummary") if isinstance(payload.get("quoteSummary"), dict) else {}
    session = payload.get("session") if isinstance(payload.get("session"), dict) else {}
    return {
        "path": str(path),
        "present": True,
        "status": payload.get("status"),
        "readyForExecutionDataProof": bool(payload.get("readyForExecutionDataProof")),
        "reason": quote_summary.get("reason"),
        "sessionLikelyOpen": session.get("likelyOpen"),
        "sessionReason": session.get("reason"),
        "writesOrders": payload.get("writesOrders"),
        "touchesBroker": payload.get("touchesBroker"),
        "writesRealtimeQuoteState": payload.get("writesRealtimeQuoteState"),
        "readError": payload.get("_readError"),
    }


def databento_live_summary(env_values: dict[str, str], module_summary: dict[str, Any]) -> dict[str, Any]:
    explicitly_enabled = truthy(os.environ.get("BILL_DATABENTO_REALTIME_ENABLED") or env_values.get("BILL_DATABENTO_REALTIME_ENABLED"))
    has_key = bool(os.environ.get("DATABENTO_API_KEY") or env_values.get("DATABENTO_API_KEY"))
    module_ok = bool(module_summary.get("available"))
    can_attempt = explicitly_enabled and has_key and module_ok
    if can_attempt:
        status = "ready-to-attempt-live-data"
    elif explicitly_enabled and not has_key:
        status = "blocked-missing-api-key"
    elif explicitly_enabled and not module_ok:
        status = "blocked-module-missing"
    else:
        status = "disabled-until-explicit-opt-in"

    return {
        "status": status,
        "role": "retired-compatibility-only; TopstepX/ProjectX SignalR is preferred",
        "explicitlyEnabled": explicitly_enabled,
        "credentialPresent": has_key,
        "module": module_summary,
        "canAttemptLiveFetch": can_attempt,
        "dataset": non_secret_config_value(env_values, "BILL_DATABENTO_DATASET", DATABENTO_DATASET),
        "schema": non_secret_config_value(env_values, "BILL_DATABENTO_SCHEMA", DATABENTO_SCHEMA),
        "safeDataOnlyCommand": (
            "BILL_ENABLE_FUTURES_DEMO_EXECUTION=false RH_TOPSTEP_READ_ONLY=true "
            "RH_LIVE_EXECUTION_ENABLED=false .venv/bin/python scripts/realtime_data_bridge.py --quiet --databento-only"
        ),
    }


def wrapper_summary(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "present": False}
    text = path.read_text(encoding="utf-8", errors="replace")
    return {
        "path": str(path),
        "present": True,
        "usesVenvPython": ".venv/bin/python" in text,
        "forcesFuturesDemoDisabled": "BILL_ENABLE_FUTURES_DEMO_EXECUTION=false" in text,
        "forcesTopstepReadOnly": "RH_TOPSTEP_READ_ONLY=true" in text,
        "forcesLiveExecutionDisabled": "RH_LIVE_EXECUTION_ENABLED=false" in text,
    }


def build_report(now: datetime | None = None) -> dict[str, Any]:
    now = now or utc_now()
    env_values = parse_env_file(BILL_ENV)
    realtime = state_summary(REALTIME_STATE, now)
    freshness = freshness_summary(DATA_FRESHNESS_STATE)
    topstep_realtime = topstep_realtime_proof_summary(TOPSTEP_REALTIME_PROOF_STATE, now)
    databento_smoke = databento_smoke_summary(DATABENTO_SMOKE_STATE)
    databento_module = module_available("databento")
    databento_live = databento_live_summary(env_values, databento_module)
    wrapper = wrapper_summary(CRON_WRAPPER)

    env_presence = [safe_env_presence(env_values, key) for key in sorted(SECRET_KEYS)]
    env_present = {item["key"]: item["present"] for item in env_presence}
    freshness_pass = freshness.get("verdict") == "PASS" and freshness.get("action") == "allow_trades"
    realtime_grade = realtime.get("executionGrade") is True
    wrapper_safe = all(
        wrapper.get(key) is True
        for key in ["usesVenvPython", "forcesFuturesDemoDisabled", "forcesTopstepReadOnly", "forcesLiveExecutionDisabled"]
    )

    blockers: list[str] = []
    if not wrapper_safe:
        blockers.append("realtime cron wrapper is missing one or more safety/runtime guarantees")
    if not (env_present.get("RH_TOPSTEP_API_KEY") and env_present.get("RH_TOPSTEP_USERNAME")):
        blockers.append("TopstepX API credentials are not available to the realtime data path")
    if not realtime.get("present"):
        blockers.append("realtime quote state is missing")
    if realtime.get("present") and not realtime_grade:
        reason = realtime.get("executionBlockReason") or f"source={realtime.get('source')} is not marked execution-grade"
        blockers.append(str(reason))
    if not freshness_pass:
        freshness_blocker = f"data freshness gate is {freshness.get('verdict') or 'missing'}"
        if databento_smoke.get("status") == "NO_QUOTES_MARKET_CLOSED":
            freshness_blocker += " (expected until open-session proof; Databento smoke reports market closed)"
        blockers.append(freshness_blocker)
    if topstep_realtime.get("readyForExecutionDataProof") and not (realtime_grade and freshness_pass):
        blockers.append("TopstepX realtime proof is visible, but canonical realtime quote state/freshness is not yet promoted")

    ready = len(blockers) == 0
    return {
        "command": "realtime-data-preflight",
        "generatedAt": now.isoformat(),
        "readyForExecutionData": ready,
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "decision": "execution-data-ready" if ready else "block-execution-data",
        "blockers": blockers,
        "runtime": {
            "pythonExecutable": sys.executable,
            "cronWrapper": wrapper,
        },
        "dataSources": {
            "preferredExecutionDataPath": "topstepx_projectx_signalr",
            "topstepRealtimeProof": topstep_realtime,
            "databentoRole": "optional-secondary-depth-research",
            "databentoRealtimeSmoke": databento_smoke,
            "databentoLive": databento_live,
            "alpacaSandbox": {
                "status": "available-via-plugin-manifest",
                "role": "equities-options-crypto-research-and-paper-sandbox",
                "notFor": "Topstep futures broker truth or futures route approval",
                "executionAuthority": False,
            },
        },
        "configPresence": env_presence,
        "state": {
            "realtimeQuote": realtime,
            "dataFreshnessGate": freshness,
        },
        "proofTiming": {
            "marketClosed": databento_smoke.get("status") == "NO_QUOTES_MARKET_CLOSED",
            "nextAction": "Refresh TopstepX realtime bridge and data freshness evidence.",
            "safeEnv": {
                "BILL_ENABLE_FUTURES_DEMO_EXECUTION": "false",
                "RH_TOPSTEP_READ_ONLY": "true",
                "RH_LIVE_EXECUTION_ENABLED": "false",
            },
        },
        "nextActions": [
            "Keep futures execution locked while data freshness is blocked.",
            "Use TradingView only if update modes are realtime, not delayed.",
            "Prefer TopstepX/ProjectX SignalR for broker-relevant futures realtime proof; promote it only through the canonical bridge.",
            "When proof is available, run the read-only TopstepX realtime bridge so realtime-quote.latest.json uses source=topstep_realtime.",
            "Do not treat Yahoo/yfinance research bars as execution-grade realtime data.",
        ],
    }


def main() -> int:
    report = build_report()
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["readyForExecutionData"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
