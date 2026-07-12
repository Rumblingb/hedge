#!/usr/bin/env python3
"""orb_shadow_run.py — READ-ONLY shadow of the master strategy bridge.

Reproduces master_bridge.main()'s strategy evaluation + pick_best WITHOUT the
FOMC early-return and WITHOUT any order path. Writes a shadow-signal artifact so
the operator can watch what the bridge *would* route on live ProjectX-fed bars,
on days when execution is blocked (e.g. FOMC 2026-06-16/17).

Routes NOTHING. Touches no broker. Safe to run any time.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import master_bridge as mb

STATE_DIR = mb.STATE_DIR
SHADOW_LATEST = STATE_DIR / "orb-shadow-signal.latest.json"
SHADOW_LOG = Path(mb.HOME) / "hedge" / ".rumbling-hedge" / "logs" / "orb-shadow.jsonl"


def evaluate():
    signals = []
    # Mirror master_bridge.main() NQ + ES orb-breakout legs (read-only).
    signals.append(mb.run_strategy("NQ orb-breakout (60m)", "NQ-60m-60d.csv", lambda b: mb.orb_breakout(b, 8, 14), min_bars=12))
    signals.append(mb.run_strategy("NQ orb-breakout (30m)", "NQ-30m-60d.csv", lambda b: mb.orb_breakout(b, 12, 13)))
    signals.append(mb.run_strategy("NQ orb-breakout (15m)", "NQ-15m-60d.csv", lambda b: mb.orb_breakout(b, 12, 14)))
    signals.append(mb.run_strategy("NQ orb-breakout (5m)", "NQ-5m-5d.csv", lambda b: mb.orb_breakout(b, 12, 8), min_bars=30))
    signals.append(mb.run_strategy("ES orb-breakout (60m)", "ES-60m-60d.csv", lambda b: mb.orb_breakout(b, 12, 14), min_bars=16, symbol="ES"))
    best = mb.pick_best(signals)

    now = datetime.now(timezone.utc).isoformat()
    try:
        session = mb.detect_session()
    except Exception:
        session = None

    if best is None:
        record = {"ts": now, "mode": "shadow_only", "submitted": False,
                  "session": session, "signal": None,
                  "reason": "no orb entry across NQ/ES timeframes"}
    else:
        record = {
            "ts": now, "mode": "shadow_only", "submitted": False, "session": session,
            "signal": f"{best['side']}@{best['strategy']}",
            "strategy": best["strategy"], "side": best["side"],
            "entry": round(best["entry"], 2), "stop": round(best["stop"], 2),
            "target": round(best["target"], 2), "rr": round(best["rr"], 2),
            "confidence": best.get("confidence"),
            "would_route_contracts": mb.calc_position(best),
            "note": "SHADOW — execution blocked (FOMC/locked). No order sent.",
        }

    record.update({
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "movesFunds": False,
        "readyForExecution": False,
        "readyForDemoExpansion": False,
        "readyForLive": False,
    })

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    SHADOW_LATEST.write_text(json.dumps(record, indent=2) + "\n")
    SHADOW_LOG.parent.mkdir(parents=True, exist_ok=True)
    with SHADOW_LOG.open("a") as fh:
        fh.write(json.dumps(record) + "\n")
    return record


if __name__ == "__main__":
    rec = evaluate()
    print(json.dumps(rec, indent=2))
