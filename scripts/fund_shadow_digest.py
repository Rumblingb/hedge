#!/usr/bin/env python3
"""fund_shadow_digest.py — READ-ONLY: consolidate fund shadow state into ONE Obsidian note
+ ONE n8n-consumable JSON. Deterministic (Obsidian records, code routes). Touches no broker.

Pulls: mtf-shadow-signal, agentic-fund-controller, combine-preflight, topstep-lanes.
Writes:
  - Vault note  : Agent-Hermes/bill-fund-shadow-digest.md (overwritten = current status)
  - n8n feed    : .rumbling-hedge/state/fund-digest.n8n.json (flat, webhook/poll friendly)
"""
import json
from datetime import datetime, timezone
from pathlib import Path

STATE = Path.home() / "hedge" / ".rumbling-hedge" / "state"
VAULT = Path.home() / "Documents" / "memorybrain" / "Agent-Hermes"
NOTE = VAULT / "bill-fund-shadow-digest.md"
N8N = STATE / "fund-digest.n8n.json"


def load(name):
    try:
        return json.loads((STATE / name).read_text())
    except Exception:
        return {}


def main():
    now = datetime.now(timezone.utc).isoformat()
    mtf = load("mtf-shadow-signal.latest.json")
    ctrl = load("agentic-fund-controller.latest.json")
    pre = load("combine-preflight.latest.json")
    lanes = load("topstep-lanes.latest.json")

    posture = (ctrl.get("volRegimePosture") or {})
    summary = (ctrl.get("summary") or {})

    # --- flat n8n feed ---
    mtf_rows = []
    for sym, s in (mtf.get("signals") or {}).items():
        for tf, v in (s.get("by_timeframe") or {}).items():
            if isinstance(v, dict) and "BREAKOUT" in str(v.get("status", "")):
                mtf_rows.append({"symbol": sym, "tf": tf, "side": v.get("side"),
                                 "status": v.get("status"),
                                 "pullback_entry": v.get("pullback_entry"),
                                 "breakout_close": v.get("breakout_close")})
    feed = {
        "generatedAt": now,
        "vol_regime_posture": posture.get("posture"),
        "vol_atr_pct": posture.get("atr_pct"),
        "next_action": ctrl.get("nextAction"),
        "candidates_needing_verification": summary.get("needs_verification"),
        "candidates_data_blocked": summary.get("data_blocked"),
        "combine_preflight_verdict": pre.get("verdict"),
        "combine_preflight_blockers": pre.get("blockers"),
        "mtf_shadow_breakouts": mtf_rows,
        "lanes": [{"role": l.get("role"), "account_id": l.get("account_id"),
                   "balance": l.get("balance"), "can_trade": l.get("can_trade")}
                  for l in (lanes.get("lanes") or [])],
        "researchOnly": True, "writesOrders": False, "touchesBroker": False,
        "movesFunds": False, "readyForExecution": False,
        "readyForDemoExpansion": False, "readyForLive": False,
    }
    N8N.write_text(json.dumps(feed, indent=2) + "\n")

    # --- Obsidian note ---
    lines = [
        "# Bill Fund — Shadow Digest",
        "Parent: [[BILL-CONTROL-HUB]] · Auto-written read-only; records, does not approve.",
        f"\n> Updated: {now}\n",
        "## Vol-regime posture",
        f"- **{posture.get('posture','?')}** — {posture.get('reason','')} (ATR pct {posture.get('atr_pct')})",
        "\n## Next action",
        f"- {ctrl.get('nextAction','(none)')}",
        "\n## Candidate readiness",
        f"- needs-verification: {summary.get('needs_verification')} · data-blocked: {summary.get('data_blocked')} · "
        f"fails-oos: {summary.get('fails_oos')} · fails-screen: {summary.get('fails_screen')}",
        "\n## Combine preflight (testbed-a / 6 MNQ)",
        f"- **{pre.get('verdict','?')}** — blockers: {pre.get('blockers') or 'none'}",
        "\n## MTF execution shadow (HTF breakout + 1m entry/exit)",
    ]
    if mtf_rows:
        lines.append("| Sym | TF | Side | Pullback entry | Breakout close |")
        lines.append("|---|---|---|---|---|")
        for r in mtf_rows:
            lines.append(f"| {r['symbol']} | {r['tf']} | {r['side']} | {r['pullback_entry']} | {r['breakout_close']} |")
    else:
        lines.append("- no breakout in the latest session")
    lines += [
        "\n## Lanes",
        "| Role | Account | Balance | canTrade |",
        "|---|---|---|---|",
    ]
    for l in (lanes.get("lanes") or []):
        lines.append(f"| {l.get('role')} | {l.get('account_id')} | {l.get('balance')} | {l.get('can_trade')} |")
    lines += [
        "\n---",
        "Sources: mtf-shadow-signal, agentic-fund-controller, combine-preflight, topstep-lanes (all read-only).",
        "n8n feed: `.rumbling-hedge/state/fund-digest.n8n.json` · command center :8766 `/api/full`.",
    ]
    try:
        NOTE.parent.mkdir(parents=True, exist_ok=True)
        NOTE.write_text("\n".join(lines) + "\n")
        wrote_note = str(NOTE)
    except Exception as e:
        wrote_note = f"vault-write-skipped: {e}"

    print(json.dumps({"n8n_feed": str(N8N), "vault_note": wrote_note,
                      "mtf_breakouts": len(mtf_rows), "posture": posture.get("posture")}, indent=2))


if __name__ == "__main__":
    main()
