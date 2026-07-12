#!/usr/bin/env python3
"""Demo lane monitor — read-only progress tracker for the prop-firm campaign.

Reads config/demo-lanes.json (canonical demo + testing beds), pulls balances,
today's half-turns and open positions per account from TopstepX (read-only),
and writes .rumbling-hedge/state/topstep-lanes.latest.json with:
  - per lane: balance, baseline delta, live-gate progress ($3K rule),
    today's round trips + realized PnL, open position count, canTrade
  - campaign: which lane (if any) has cleared the live gate

Never places or modifies orders. Uses the shared validated token cache.
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.expanduser("~/.hermes/scripts"))
from topstep_auth_cache import get_token  # noqa: E402

import requests  # noqa: E402

ROOT = Path.home() / "hedge"
CONFIG = ROOT / "config/demo-lanes.json"
OUT = ROOT / ".rumbling-hedge/state/topstep-lanes.latest.json"
API = "https://api.topstepx.com"


def post(path, body, headers):
    r = requests.post(f"{API}{path}", json=body, headers=headers, timeout=15)
    r.raise_for_status()
    return r.json()


def main():
    cfg = json.loads(CONFIG.read_text())
    gate = float(cfg.get("live_gate_usd", 3000))
    headers = {"Authorization": f"Bearer {get_token()}",
               "Content-Type": "application/json"}

    accounts = {a["id"]: a for a in post(
        "/api/Account/search", {"onlyActiveAccounts": False}, headers
    ).get("accounts", [])}

    day_start = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00Z")
    now_iso = datetime.now(timezone.utc).isoformat()

    lanes_out = []
    gate_cleared = []
    for lane in cfg.get("lanes", []):
        aid = lane["account_id"]
        acct = accounts.get(aid, {})
        balance = float(acct.get("balance", 0) or 0)
        baseline = float(lane.get("baseline_balance", 0) or 0)
        delta = round(balance - baseline, 2)

        halfturns = post("/api/Trade/search",
                         {"accountId": aid, "startTimestamp": day_start},
                         headers).get("trades", [])
        closed = [h for h in halfturns if h.get("profitAndLoss") is not None]
        realized_today = round(sum(float(h["profitAndLoss"]) for h in closed), 2)
        open_positions = post("/api/Position/searchOpen",
                              {"accountId": aid}, headers).get("positions", [])

        progress = round(delta / gate, 4) if gate else None
        cleared = delta >= gate
        if cleared:
            gate_cleared.append(aid)
        lanes_out.append({
            "account_id": aid,
            "account_name": acct.get("name") or lane.get("account_name"),
            "role": lane.get("role"),
            "strategy": lane.get("strategy"),
            "can_trade": bool(acct.get("canTrade")),
            "is_visible": bool(acct.get("isVisible")),
            "simulated": acct.get("simulated") is True,
            "balance": balance,
            "baseline_balance": baseline,
            "delta_usd": delta,
            "live_gate_usd": gate,
            "live_gate_progress": progress,
            "live_gate_cleared": cleared,
            "round_trips_today": len(closed),
            "realized_pnl_today": realized_today,
            "open_positions": len(open_positions),
        })
        print(f"{lane.get('role','?'):11s} {aid} bal={balance:>10,.2f} "
              f"Δ={delta:>+9,.2f} gate {progress if progress is not None else 0:+.1%} "
              f"today: {len(closed)} closed {realized_today:+,.2f} "
              f"open={len(open_positions)} canTrade={bool(acct.get('canTrade'))}")

    out = {
        "ts": now_iso,
        "research_only": True,
        "writes_orders": False,
        "live_gate_usd": gate,
        "live_gate_cleared_accounts": gate_cleared,
        "live_consideration_unlocked": bool(gate_cleared),
        "lanes": lanes_out,
    }
    OUT.write_text(json.dumps(out, indent=2) + "\n")
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
