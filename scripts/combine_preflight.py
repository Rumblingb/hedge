#!/usr/bin/env python3
"""combine_preflight.py — HARD pre-trade gate for the combine go-live.

Aggregates the must-be-green conditions into ONE pass/fail an operator (or cron) runs
before routing. Exit 0 = clear to route; exit 1 = BLOCKED with reasons. Read-only,
routes nothing. Complements the in-bridge execution firewall with a standalone,
human-runnable checklist tuned to the combine lane (testbed-a 23268236, 6 MNQ).

Checks: FOMC firewall, execution-grade feed freshness, broker-flat + fresh reconciliation,
target-account canTrade, daily-plan route approval token.
"""
import json
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

REPO = Path.home() / "hedge"
STATE = REPO / ".rumbling-hedge" / "state"
VAULT = Path.home() / "Documents" / "memorybrain" / "Agent-Hermes" / "daily"
TARGET_ACCOUNT_ID = 23268236            # testbed-a (50K combine)
TARGET_ACCOUNT_NAME = "50KTC-V2-DLL-507159-28339015"

# FOMC firewall — keep in sync with master_bridge.FOMC_DATES.
FOMC_DATES = {
    date(2026, 1, 28), date(2026, 1, 29), date(2026, 3, 17), date(2026, 3, 18),
    date(2026, 5, 6), date(2026, 5, 7), date(2026, 5, 19),
    date(2026, 6, 16), date(2026, 6, 17), date(2026, 7, 28), date(2026, 7, 29),
    date(2026, 9, 15), date(2026, 9, 16), date(2026, 11, 3), date(2026, 11, 4),
    date(2026, 12, 15), date(2026, 12, 16),
}

FEED_MAX_AGE_S = 90
RECON_MAX_AGE_S = 1800   # 30 min


def load(p):
    try:
        return json.loads(Path(p).read_text())
    except Exception:
        return None


def age_s(p):
    try:
        return time.time() - Path(p).stat().st_mtime
    except Exception:
        return None


def check_fomc():
    today = datetime.now(timezone.utc).date()
    if today in FOMC_DATES:
        return False, f"FOMC firewall — {today} is an FOMC date; trading blocked by design"
    return True, f"not an FOMC date ({today})"


def check_feed():
    q = load(STATE / "realtime-quote.latest.json") or {}
    a = age_s(STATE / "realtime-quote.latest.json")
    if not q.get("execution_grade"):
        return False, f"feed NOT execution-grade (source={q.get('source')}, reason={q.get('execution_block_reason')})"
    if q.get("source") != "topstep_realtime":
        return False, f"feed source is {q.get('source')}, expected topstep_realtime"
    if a is None or a > FEED_MAX_AGE_S:
        return False, f"feed stale ({a:.0f}s > {FEED_MAX_AGE_S}s)"
    return True, f"execution-grade topstep_realtime, {a:.0f}s old (NQ {q.get('price_nq')})"


def check_flat_and_recon():
    r = load(STATE / "topstep-broker-reconciliation.latest.json") or {}
    a = age_s(STATE / "topstep-broker-reconciliation.latest.json")
    if not r.get("broker_flat"):
        return False, f"NOT flat (open_positions={r.get('open_positions')})"
    if (r.get("open_positions") or 0) != 0:
        return False, f"open positions = {r.get('open_positions')}"
    if a is None or a > RECON_MAX_AGE_S:
        return False, f"reconciliation stale ({(a or 0)/60:.0f}min > {RECON_MAX_AGE_S/60:.0f}min) — refresh before routing"
    return True, f"broker_flat, 0 positions, recon {a/60:.0f}min old"


def check_account():
    lanes = load(STATE / "topstep-lanes.latest.json") or {}
    rows = lanes.get("lanes") if isinstance(lanes, dict) else lanes
    for lane in (rows or []):
        if lane.get("account_id") == TARGET_ACCOUNT_ID or lane.get("accountId") == TARGET_ACCOUNT_ID:
            can = lane.get("can_trade", lane.get("canTrade"))
            if can:
                return True, f"testbed-a {TARGET_ACCOUNT_ID} can_trade=True bal={lane.get('balance')}"
            return False, f"testbed-a {TARGET_ACCOUNT_ID} can_trade=False"
    return None, f"testbed-a {TARGET_ACCOUNT_ID} not found in lanes monitor (run topstep_lanes_monitor.py)"


def check_plan_approval():
    plan = VAULT / f"{datetime.now(timezone.utc).date().isoformat()}-bill-trading-plan.md"
    if not plan.exists():
        return None, "today's daily plan not found"
    text = plan.read_text(errors="ignore")
    approved = "BILL_ROUTE_APPROVAL: APPROVED" in text
    green = "BROKER_RECONCILIATION: GREEN" in text
    if approved and green:
        return True, "plan tokens APPROVED + GREEN present"
    return False, f"plan tokens missing (APPROVED={approved}, GREEN={green}) — operator must write them"


def main():
    checks = [
        ("FOMC firewall", check_fomc()),
        ("Execution-grade feed", check_feed()),
        ("Flat + fresh reconciliation", check_flat_and_recon()),
        ("Target account canTrade", check_account()),
        ("Daily-plan route approval", check_plan_approval()),
    ]
    hard_fail = [name for name, (ok, _) in checks if ok is False]
    unknown = [name for name, (ok, _) in checks if ok is None]
    record = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "lane": "combine / testbed-a 23268236 / 6 MNQ nq-orb-3m",
        "checks": [{"check": n, "pass": ok, "detail": d} for n, (ok, d) in checks],
        "verdict": "CLEAR" if not hard_fail and not unknown else ("BLOCKED" if hard_fail else "UNKNOWN"),
        "blockers": hard_fail, "unknowns": unknown,
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "movesFunds": False,
        "readyForExecution": False,
        "readyForDemoExpansion": False,
        "readyForLive": False,
        "authority": "preflight-evidence-only; deterministic routing gates remain authoritative",
    }
    (STATE / "combine-preflight.latest.json").write_text(json.dumps(record, indent=2) + "\n")
    print(f"\n=== COMBINE PREFLIGHT — {record['verdict']} ===")
    for n, (ok, d) in checks:
        icon = "PASS" if ok else ("BLOCK" if ok is False else "?")
        print(f"  [{icon:>5}] {n}: {d}")
    print()
    return 0 if record["verdict"] == "CLEAR" else 1


if __name__ == "__main__":
    sys.exit(main())
