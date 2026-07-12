#!/usr/bin/env python3
"""Read-only TopstepX/ProjectX market-data smoke for current NQ/MNQ bars.

This script authenticates only after execution locks are present, then calls
read-only market-data endpoints:

- POST /api/Contract/search
- POST /api/History/retrieveBars

It never places, modifies, or cancels orders. The output is proof material for
broker-current bar parity only; it does not approve demo/live routing.
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
OUT = STATE / "topstep-market-data-smoke.latest.json"
TOPSTEP_SESSION_SAFETY = STATE / "topstep-session-safety.latest.json"
ENV_PATH = Path.home() / "Library/Application Support/AgentPay/bill/bill.env"
API_BASE = "https://api.topstepx.com"

SAFE_ENV = {
    "BILL_ENABLE_FUTURES_DEMO_EXECUTION": "false",
    "RH_TOPSTEP_READ_ONLY": "true",
    "RH_LIVE_EXECUTION_ENABLED": "false",
}


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def load_topstep_session_safety(path: Path | None = None) -> dict[str, Any]:
    path = path or TOPSTEP_SESSION_SAFETY
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def topstep_session_safety_paused(data: dict[str, Any] | None = None) -> bool:
    safety = data if isinstance(data, dict) else load_topstep_session_safety()
    return (
        truthy(safety.get("topstepMultipleSessionsDetected"))
        or truthy(safety.get("pauseBrokerTouchingProofs"))
    )


def topstep_session_safety_summary(data: dict[str, Any] | None = None) -> dict[str, Any]:
    safety = data if isinstance(data, dict) else load_topstep_session_safety()
    paused = topstep_session_safety_paused(safety)
    override = truthy(read_secure("BILL_ALLOW_TOPSTEP_BROKER_SESSION_PROOF"))
    return {
        "statePath": str(TOPSTEP_SESSION_SAFETY),
        "active": paused,
        "pauseBrokerTouchingProofs": paused,
        "overrideEnv": "BILL_ALLOW_TOPSTEP_BROKER_SESSION_PROOF",
        "overrideEnabled": override,
        "safeUntil": safety.get("safeUntil"),
        "reason": safety.get("reason"),
    }


def read_secure(key: str) -> str | None:
    if os.environ.get(key):
        return os.environ[key]
    if not ENV_PATH.exists():
        return None
    for raw_line in ENV_PATH.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :]
        if "=" not in line:
            continue
        name, _, value = line.partition("=")
        if name.strip() == key:
            return value.strip().strip("'\"")
    return None


def safety_blockers() -> list[str]:
    blockers: list[str] = []
    if not truthy(read_secure("RH_TOPSTEP_READ_ONLY")):
        blockers.append("RH_TOPSTEP_READ_ONLY must be true for market-data smoke")
    if truthy(read_secure("BILL_ENABLE_FUTURES_DEMO_EXECUTION")):
        blockers.append("BILL_ENABLE_FUTURES_DEMO_EXECUTION must be false")
    if truthy(read_secure("RH_LIVE_EXECUTION_ENABLED")):
        blockers.append("RH_LIVE_EXECUTION_ENABLED must be false")
    if truthy(read_secure("RH_KILL_SWITCH")) or truthy(read_secure("BILL_KILL_SWITCH")):
        blockers.append("kill switch is enabled; do not touch broker/API until operator reviews")
    session_safety = topstep_session_safety_summary()
    if session_safety["active"] and not session_safety["overrideEnabled"]:
        blockers.append(
            "Topstep session safety is active after a multiple-session warning; "
            "do not open ProjectX/TopstepX broker sessions until the operator clears it "
            "or sets BILL_ALLOW_TOPSTEP_BROKER_SESSION_PROOF=true for a deliberate proof window"
        )
    return blockers


def request_json(path: str, body: dict[str, Any], token: str | None = None) -> dict[str, Any]:
    headers = {"Content-Type": "application/json", "accept": "text/plain"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        f"{API_BASE}{path}",
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        payload = response.read().decode("utf-8")
    data = json.loads(payload)
    return data if isinstance(data, dict) else {}


def login() -> str:
    # Shared token cache: one loginKey per ~20h machine-wide. Topstep counts
    # each login as a session; per-run logins collided with the operator's
    # manual LIVE session and triggered "multiple sessions detected".
    try:
        import importlib.util as _ilu
        _spec = _ilu.spec_from_file_location(
            "topstep_auth_cache",
            "/Users/brain/.hermes/scripts/topstep_auth_cache.py",
        )
        _mod = _ilu.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        return _mod.get_token()
    except Exception:
        pass
    api_key = read_secure("RH_TOPSTEP_API_KEY")
    username = read_secure("RH_TOPSTEP_USERNAME")
    if not api_key:
        raise RuntimeError("RH_TOPSTEP_API_KEY missing")
    if not username:
        raise RuntimeError("RH_TOPSTEP_USERNAME missing")
    data = request_json(
        "/api/Auth/loginKey",
        {
            "apiKey": api_key,
            "userName": username,
            "applicationId": 0,
            "applicationVersion": "1.0.0",
        },
    )
    if not data.get("success"):
        raise RuntimeError(f"Topstep login failed: {data.get('errorMessage') or 'unknown error'}")
    token = data.get("token")
    if not token:
        raise RuntimeError("Topstep login returned no token")
    return str(token)


def search_contracts(token: str, search_text: str, *, live: bool = False) -> list[dict[str, Any]]:
    data = request_json("/api/Contract/search", {"searchText": search_text, "live": live}, token)
    contracts = data.get("contracts")
    return contracts if isinstance(contracts, list) else []


def pick_active_contract(contracts: list[dict[str, Any]], symbol_id: str) -> dict[str, Any] | None:
    matches = [
        contract
        for contract in contracts
        if isinstance(contract, dict)
        and contract.get("symbolId") == symbol_id
        and contract.get("activeContract") is True
        and contract.get("id")
    ]
    if not matches:
        matches = [
            contract
            for contract in contracts
            if isinstance(contract, dict)
            and contract.get("symbolId") == symbol_id
            and contract.get("id")
        ]
    return matches[0] if matches else None


def retrieve_bars(
    token: str,
    contract_id: str,
    *,
    start: datetime,
    end: datetime,
    unit_number: int,
    limit: int,
    live: bool = False,
) -> list[dict[str, Any]]:
    data = request_json(
        "/api/History/retrieveBars",
        {
            "contractId": contract_id,
            "live": live,
            "startTime": start.isoformat().replace("+00:00", "Z"),
            "endTime": end.isoformat().replace("+00:00", "Z"),
            "unit": 2,
            "unitNumber": unit_number,
            "limit": limit,
            "includePartialBar": False,
        },
        token,
    )
    bars = data.get("bars")
    return bars if isinstance(bars, list) else []


def parse_bar_ts(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def summarize_bars(bars: list[dict[str, Any]], end: datetime) -> dict[str, Any]:
    timestamps = [parse_bar_ts(bar.get("t")) for bar in bars if isinstance(bar, dict)]
    timestamps = [ts for ts in timestamps if ts is not None]
    newest = max(timestamps) if timestamps else None
    newest_age = (end - newest).total_seconds() if newest else None
    return {
        "barCount": len(bars),
        "newestBarTs": newest.isoformat() if newest else None,
        "newestBarAgeSeconds": round(newest_age, 1) if newest_age is not None else None,
        "hasOhlcv": all(
            all(key in bar and bar.get(key) is not None for key in ["t", "o", "h", "l", "c", "v"])
            for bar in bars
            if isinstance(bar, dict)
        )
        if bars
        else False,
        "sample": bars[:2],
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    started = now_utc()
    blockers = safety_blockers()
    report: dict[str, Any] = {
        "command": "topstep-market-data-smoke",
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
        "safeEnv": dict(SAFE_ENV),
        "topstepSessionSafety": topstep_session_safety_summary(),
        "officialDocs": {
            "contractSearch": "https://gateway.docs.projectx.com/docs/api-reference/market-data/search-contracts/",
            "retrieveBars": "https://gateway.docs.projectx.com/docs/api-reference/market-data/retrieve-bars/",
        },
        "symbols": {},
        "blockers": blockers,
    }
    if blockers:
        report["status"] = "BLOCKED_BY_SAFETY_ENV"
        report["brokerCurrentBarsProofPassed"] = False
        return report

    try:
        token = login()
        contracts = search_contracts(token, args.search_text, live=args.live)
        end = now_utc()
        start = end - timedelta(minutes=args.lookback_minutes)
        contract_summary = {
            "returned": len(contracts),
            "selectedSearchText": args.search_text,
            "live": args.live,
        }
        for label, symbol_id in [("NQ", "F.US.ENQ"), ("MNQ", "F.US.MNQ")]:
            contract = pick_active_contract(contracts, symbol_id)
            if not contract:
                report["symbols"][label] = {
                    "status": "NO_ACTIVE_CONTRACT",
                    "symbolId": symbol_id,
                    "barSummary": summarize_bars([], end),
                }
                continue
            bars = retrieve_bars(
                token,
                str(contract.get("id")),
                start=start,
                end=end,
                unit_number=args.unit_number,
                limit=args.limit,
                live=args.live,
            )
            summary = summarize_bars(bars, end)
            report["symbols"][label] = {
                "status": "BARS_OK" if summary["barCount"] > 0 and summary["hasOhlcv"] else "NO_BARS",
                "contract": {
                    "id": contract.get("id"),
                    "name": contract.get("name"),
                    "description": contract.get("description"),
                    "tickSize": contract.get("tickSize"),
                    "tickValue": contract.get("tickValue"),
                    "activeContract": contract.get("activeContract"),
                    "symbolId": contract.get("symbolId"),
                },
                "barSummary": summary,
            }
        ok_symbols = [
            label
            for label, item in report["symbols"].items()
            if isinstance(item, dict) and item.get("status") == "BARS_OK"
        ]
        report["contractSearch"] = contract_summary
        report["status"] = "BARS_OK" if len(ok_symbols) == len(report["symbols"]) and ok_symbols else "PARTIAL_OR_NO_BARS"
        report["brokerCurrentBarsProofPassed"] = report["status"] == "BARS_OK"
        report["promotionRule"] = (
            "Broker-current bars proof is only one data requirement. It does not clear realtime freshness, "
            "DOM/depth/order-flow, OOS, source hygiene, daily approval, or execution firewall gates."
        )
    except Exception as exc:
        report["status"] = "ERROR"
        report["error"] = str(exc)
        report["brokerCurrentBarsProofPassed"] = False
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--search-text", default="NQ")
    parser.add_argument("--lookback-minutes", type=int, default=45)
    parser.add_argument("--unit-number", type=int, default=1)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--live", action="store_true", help="Use live data subscription instead of sim data")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = build_report(args)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload.get("brokerCurrentBarsProofPassed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
