#!/usr/bin/env python3
"""Lane B — ES ORB 15m forward test on Topstep practice account 23268236.

Forward-tests the ES ORB 15m edge (backtest PF 1.385, n=538) on its own
practice account so its fills never mix with Lane A's NQ stack. Reuses the
canonical strategy + gates from master_bridge and routes through the guarded
topstep_demo_bridge with per-lane env overrides (account, contract MES,
signal path), so every safety layer there (live-account deny, pre-submit
position check, OCO + orphan guard, partial-fill handling) applies unchanged.

Fail-closed firewall: in addition to the standard daily-plan tokens, the plan
must contain the machine line `BILL_LANE_B_ROUTE_APPROVAL: APPROVED`.
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone, date
from pathlib import Path

HOME = os.environ["HOME"]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import master_bridge as mb  # canonical strategies + firewall + helpers

LANE = "lane-b"
LANE_ACCOUNT_ID = "23268236"          # 50KTC-V2-DLL-507159-28339015
LANE_CONTRACT = "CON.F.US.MES.M26"    # Micro E-mini S&P 500 June 2026
LANE_MAX_TRADES_PER_DAY = 2
STATE_DIR = Path(HOME) / "hedge" / ".rumbling-hedge" / "state"
LANE_SIGNAL_PATH = STATE_DIR / f"master-signal.{LANE_ACCOUNT_ID}.latest.json"
LANE_COUNT_PATH = STATE_DIR / f"lane-b-trade-count.json"


def lane_token_blockers():
    daily_text = mb.read_text_safe(mb.today_daily_plan_path())
    control_lines = mb.machine_control_lines(daily_text)
    if "BILL_LANE_B_ROUTE_APPROVAL: APPROVED" not in control_lines:
        return ["daily plan lacks BILL_LANE_B_ROUTE_APPROVAL: APPROVED"]
    return []


def trades_today():
    try:
        data = json.loads(LANE_COUNT_PATH.read_text())
        if data.get("date") == date.today().isoformat():
            return int(data.get("count", 0))
    except Exception:
        pass
    return 0


def record_trade():
    LANE_COUNT_PATH.write_text(json.dumps({"date": date.today().isoformat(),
                                           "count": trades_today() + 1}))


def main():
    now = datetime.now(timezone.utc)
    print(f"── Lane B (ES ORB 15m → MES @ {LANE_ACCOUNT_ID}) — {now:%Y-%m-%d %H:%M} UTC")

    # 1. Firewall: standard execution firewall + lane token, all fail-closed.
    firewall = mb.execution_firewall_decision()
    blockers = list(firewall.get("blockers") or []) + lane_token_blockers()
    if trades_today() >= LANE_MAX_TRADES_PER_DAY:
        blockers.append(f"lane-b trade cap reached ({LANE_MAX_TRADES_PER_DAY}/day)")
    if blockers:
        print("⛔ Lane B blocked:")
        for b in blockers:
            print(f"   - {b}")
        return 0

    # 2. Data freshness (ES realtime quote must be execution grade).
    es_check = mb.check_freshness("ES=F")
    if es_check.get("status") != "PASS":
        print(f"⛔ Lane B blocked: ES data not execution-grade ({es_check.get('reason')})")
        return 0

    # 3. Signal: ES ORB on 15m bars only (one edge, one lane).
    sig = mb.run_strategy("ES orb-breakout (15m)", "ES-15m-60d.csv",
                          lambda b: mb.orb_breakout(b, 12, 14), min_bars=30, symbol="ES")
    if not sig:
        print("⏸️ Lane B: no ES ORB signal")
        return 0

    # 4. Hand off to the guarded bridge with per-lane routing.
    signal_payload = {
        "ts": now.isoformat(),
        "signal": f"{sig['side']}@es-orb-15m",
        "strategy": "es-orb-15m",
        "side": sig["side"],
        "entry": sig["entry"],
        "stop": sig["stop"],
        "target": sig["target"],
        "rr": sig.get("rr"),
        "contracts": 1,
        "route": "topstep_demo",
        "status": "pending_topstep_demo_submission",
        "submitted": None,
        "lane": LANE,
        "execution_firewall": firewall,
    }
    LANE_SIGNAL_PATH.write_text(json.dumps(signal_payload, indent=2) + "\n")

    env = {
        **os.environ,
        "RH_TOPSTEP_ROUTE_ACCOUNT_ID": LANE_ACCOUNT_ID,
        "RH_TOPSTEP_ROUTE_CONTRACT": LANE_CONTRACT,
        "RH_TOPSTEP_ROUTE_SIGNAL_PATH": str(LANE_SIGNAL_PATH),
    }
    bridge = Path(HOME) / ".hermes/scripts/topstep_demo_bridge.py"
    result = subprocess.run([sys.executable, str(bridge)],
                            capture_output=True, text=True, timeout=90, env=env)
    for line in result.stdout.splitlines():
        print(f"  [LaneB] {line}")
    receipt_path = STATE_DIR / f"topstep-demo-submission.{LANE_ACCOUNT_ID}.latest.json"
    try:
        receipt = json.loads(receipt_path.read_text())
        if receipt.get("submitted"):
            record_trade()
            print(f"✅ Lane B submitted: {receipt.get('signal')} "
                  f"(order {((receipt.get('detail') or {}).get('entry_order_id'))})")
    except Exception:
        pass
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
