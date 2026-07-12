#!/usr/bin/env python3
"""Lane B — ES ORB-3m forward test on Topstep practice account 23268236.

Forward-tests the ES ORB-3m edge on its own practice account so its fills never
mix with Lane A's NQ stack. The 3m config is the SAME structurally-confirmed edge
as NQ's blessed nq-orb-3m-vt16 — validated on 20yr ES (2000-2019): PF>=1.5 +
positive net across dot-com/GFC/QE regime blocks, 5/5 walkforward, shuffle-robust
(loop-research/es20yr-orb-robustness.json, founder-approved demo 2026-06-13).
Replaces the earlier 15m testbed (PF 1.385). Signals come from the faithful
generator scripts/orb3m_es_signal.py; routing goes through the guarded
topstep_demo_bridge with per-lane env overrides (account, contract MES, signal
path), so every safety layer there (live-account deny, pre-submit position check,
OCO + orphan guard, partial-fill handling) applies unchanged.

Bounded experiment: ES ORB-3m is structurally confirmed in backtest but NOT yet
blessed — it must prove FORWARD in demo before any live consideration ($3k gate).
So routing is fail-closed behind FOUR bounds: (1) daily-plan token
`BILL_LANE_B_ROUTE_APPROVAL: APPROVED`, (2) standard execution firewall,
(3) 2-trade/day cap, (4) the es-orb3m-demo loss budget in
config/experiment-budgets.json — when forward realized loss breaches it, the lane
stops. DEMO-only: no live execution flag is touched anywhere in this path.
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
LANE_CONTRACT = "CON.F.US.MES.U26"    # Micro E-mini S&P 500 September 2026 (rolled 2026-06-13)
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


ES_ORB3M_EXPERIMENT_ID = "es-orb3m-demo"


def es_orb3m_budget_blockers():
    """Fail-closed bounded-experiment guard for ES ORB-3m (candidate, not blessed).

    Blocks routing unless an active es-orb3m-demo experiment budget exists and its
    forward realized loss is still within budget. Reuses the parity gate's journal
    accounting. Session-agnostic and additive: this can only block, never trade.
    """
    try:
        from config_parity_gate import _experiment_consumed_usd, _read_json, BUDGETS
        exps = _read_json(BUDGETS).get("experiments", [])
        exp = next((e for e in exps
                    if e.get("id") == ES_ORB3M_EXPERIMENT_ID and e.get("status") == "active"), None)
        if not exp:
            return [f"es-orb3m experiment '{ES_ORB3M_EXPERIMENT_ID}' not active in experiment-budgets.json"]
        consumed = _experiment_consumed_usd(exp)  # realized PnL since started_ts (<=0 = losses)
        budget = float(exp.get("budget_usd", 0) or 0)
        remaining = budget + min(consumed, 0.0)
        if remaining <= 0:
            return [f"es-orb3m experiment EXHAUSTED (consumed ${consumed:,.2f} vs ${budget:,.2f} budget)"]
        return []
    except Exception as e:
        # Fail CLOSED for an unproven candidate: if the budget check itself fails,
        # do not route.
        return [f"es-orb3m budget guard error (fail-closed): {e}"]


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
    print(f"── Lane B (ES ORB-3m → MES @ {LANE_ACCOUNT_ID}) — {now:%Y-%m-%d %H:%M} UTC")

    # 1. Firewall: standard execution firewall + lane token, all fail-closed.
    firewall = mb.execution_firewall_decision()
    blockers = list(firewall.get("blockers") or []) + lane_token_blockers()
    if trades_today() >= LANE_MAX_TRADES_PER_DAY:
        blockers.append(f"lane-b trade cap reached ({LANE_MAX_TRADES_PER_DAY}/day)")
    blockers += es_orb3m_budget_blockers()
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

    # 3. Signal: ES ORB-3m via the faithful generator (validated on 20yr ES,
    #    2026-06-13). Replaces the weaker 15m testbed (PF 1.385) with the
    #    structurally-confirmed 3m config. Generator writes es-orb3m-signal;
    #    we read it back and require it to be FRESH (this run) before routing.
    gen = Path(HOME) / "hedge" / "scripts" / "orb3m_es_signal.py"
    es_sig_path = STATE_DIR / "es-orb3m-signal.latest.json"
    subprocess.run([sys.executable, str(gen)], capture_output=True, text=True, timeout=90)
    sig = None
    try:
        cand = json.loads(es_sig_path.read_text())
        sig_ts = datetime.fromisoformat(str(cand.get("ts")).replace("Z", "+00:00"))
        if cand.get("tradable_signal") and (now - sig_ts).total_seconds() <= 600:
            sig = cand
    except Exception:
        sig = None
    if not sig:
        print("⏸️ Lane B: no fresh ES ORB-3m signal")
        return 0

    # 4. Hand off to the guarded bridge with per-lane routing.
    signal_payload = {
        "ts": now.isoformat(),
        "signal": f"{sig['side']}@es-orb3m-vt16",
        "strategy": "es-orb3m-vt16",
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
