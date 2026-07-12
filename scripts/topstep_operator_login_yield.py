#!/usr/bin/env python3
"""Operator login-yield switch for TopstepX "multiple sessions detected".

Flips the standing session-safety control every broker-touching proof honors.
  --engage   pause broker-touching crons + drop local token cache (operator logs in as sole session)
  --release  clear the pause, mark warning operator-cleared (proof loop resumes)
  (no flag)  print status
"""
from __future__ import annotations
import argparse, json, sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
SAFETY = STATE / "topstep-session-safety.latest.json"
TOKEN_CACHE = STATE / "topstep-auth-token.json"
HOLD_UNTIL_OPERATOR_CONFIRMATION = "operator-confirms-topstep-session-warning-cleared"

def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}

def now_iso() -> str: return datetime.now(timezone.utc).isoformat()
def today() -> str: return datetime.now(timezone.utc).date().isoformat()

def write_safety(payload: dict[str, Any]) -> None:
    SAFETY.parent.mkdir(parents=True, exist_ok=True)
    tmp = SAFETY.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    tmp.replace(SAFETY)

def drop_token_cache() -> bool:
    if TOKEN_CACHE.exists():
        TOKEN_CACHE.unlink(); return True
    return False

def engage() -> dict[str, Any]:
    safe_until = HOLD_UNTIL_OPERATOR_CONFIRMATION
    write_safety({
        "generatedAt": now_iso(),
        "topstepMultipleSessionsDetected": True,
        "pauseBrokerTouchingProofs": True,
        "reason": "Operator login-yield engaged: broker-touching crons stood down so operator can log into TopstepX as sole session.",
        "lastMitigation": "operator-login-yield --engage: dropped topstep-auth-token.json and paused broker-touching proofs.",
        "safeUntil": safe_until,
        "writesOrders": False, "touchesBroker": False, "movesFunds": False,
        "readyForExecution": False, "researchOnly": True,
        "operatorConfirmedTopstepWarningCleared": False, "operatorLoginYield": True,
    })
    return {"action": "engage", "tokenCacheDropped": drop_token_cache(), "safeUntil": safe_until,
            "next": "Log into TopstepX now. When done: npm run bill:topstep-login-yield -- --release"}

def refresh_hold() -> dict[str, Any]:
    current = read_json(SAFETY)
    paused = bool(current.get("pauseBrokerTouchingProofs")) or bool(current.get("topstepMultipleSessionsDetected"))
    if not paused:
        return {
            "action": "refresh-hold",
            "updated": False,
            "reason": "session-safety hold is not active; refusing to create one implicitly",
        }
    current.update({
        "generatedAt": now_iso(),
        "topstepMultipleSessionsDetected": True,
        "pauseBrokerTouchingProofs": True,
        "safeUntil": HOLD_UNTIL_OPERATOR_CONFIRMATION,
        "writesOrders": False,
        "touchesBroker": False,
        "movesFunds": False,
        "readyForExecution": False,
        "researchOnly": True,
        "operatorConfirmedTopstepWarningCleared": False,
        "operatorLoginYield": True,
    })
    write_safety(current)
    return {
        "action": "refresh-hold",
        "updated": True,
        "tokenCacheDropped": False,
        "safeUntil": HOLD_UNTIL_OPERATOR_CONFIRMATION,
        "next": "Keep broker-touching proofs paused until the operator explicitly runs --release.",
    }

def release() -> dict[str, Any]:
    write_safety({
        "generatedAt": now_iso(),
        "topstepMultipleSessionsDetected": False,
        "pauseBrokerTouchingProofs": False,
        "reason": "Operator finished manual TopstepX login; session-safety pause released.",
        "lastMitigation": "operator-login-yield --release",
        "safeUntil": f"operator-confirmed-{today()}",
        "writesOrders": False, "touchesBroker": False, "movesFunds": False,
        "readyForExecution": False, "researchOnly": True,
        "operatorConfirmedTopstepWarningCleared": True, "operatorLoginYield": False,
    })
    return {"action": "release", "next": "Broker-touching read-only proofs resume on next cron tick."}

def status() -> dict[str, Any]:
    s = read_json(SAFETY)
    paused = bool(s.get("pauseBrokerTouchingProofs")) or bool(s.get("topstepMultipleSessionsDetected"))
    return {"action": "status", "paused": paused, "operatorLoginYield": bool(s.get("operatorLoginYield")),
            "tokenCachePresent": TOKEN_CACHE.exists(), "reason": s.get("reason", "missing"),
            "safeUntil": s.get("safeUntil"), "generatedAt": s.get("generatedAt")}

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    g = p.add_mutually_exclusive_group()
    g.add_argument("--engage", action="store_true")
    g.add_argument("--release", action="store_true")
    g.add_argument("--refresh-hold", action="store_true")
    a = p.parse_args()
    r = engage() if a.engage else release() if a.release else refresh_hold() if a.refresh_hold else status()
    print(json.dumps(r, indent=2)); return 0

if __name__ == "__main__":
    sys.exit(main())
