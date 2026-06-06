#!/usr/bin/env python3
"""
session_shadow_trade_logger.py — Trade event logger for session shadow.
Called by the bridge or manually when a trade is placed.
Logs each trade to the session shadow and a running journal.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
SHADOW_DIR = STATE / "session-shadows"
JOURNAL_PATH = STATE / "trade-journal.latest.json"

def read_json(path):
    try:
        return json.loads(path.read_text())
    except Exception:
        return {} if "session" not in str(path) else []

def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(payload, f, indent=2, default=str)

def read_journal():
    if not JOURNAL_PATH.exists():
        return []
    try:
        journal = json.loads(JOURNAL_PATH.read_text())
        return journal if isinstance(journal, list) else []
    except Exception:
        return []

def log_trade(trade_data, now=None):
    """
    Log a trade. Call this when a trade is placed.
    
    Expected trade_data format:
    {
        "side": "long" or "short",
        "entry": 30174.25,
        "entry_time": "2026-06-08T14:35:00Z",
        "symbol": "NQ" or "MNQ",
        "contracts": 1,
        "strategy_id": "orb-breakout-15m",
        "confidence": 0.58,
        "leading_indicators": {
            "microprice_imbalance": 0.7,
            "hmm_regime": "trending-bull",
            "cot_aligned": true
        }
    }
    """
    now = now or datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    
    # Load today's session shadow
    shadow_path = SHADOW_DIR / f"session-{date_str}.json"
    shadow = read_json(shadow_path)
    
    if not shadow:
        print(f"WARN No session shadow found for {date_str}. Create one with session_shadow_premarket.py first.")
        return False
    
    # Build trade record
    trade = {
        "trade_number": len(shadow.get("trades", [])) + 1,
        "timestamp": now.isoformat(),
        "side": trade_data.get("side"),
        "entry": trade_data.get("entry"),
        "entry_time": trade_data.get("entry_time", now.isoformat()),
        "symbol": trade_data.get("symbol", "NQ"),
        "contracts": trade_data.get("contracts", 1),
        "strategy_id": trade_data.get("strategy_id", "unknown"),
        "confidence": trade_data.get("confidence"),
        "leading_indicators": trade_data.get("leading_indicators", {}),
        "intent_notes": trade_data.get("intent_notes", ""),
        "mistake_tags": trade_data.get("mistake_tags", []),
        "stop": trade_data.get("stop"),
        "target": trade_data.get("target"),
        "exit": None,
        "exit_time": None,
        "points": None,
        "outcome": "open",
        "post_mortem": {},
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "readyForExecution": False,
        "operator_read": "Trade logger records observations only; it never places, modifies, or approves orders.",
    }
    
    # Add to shadow
    if "trades" not in shadow:
        shadow["trades"] = []
    shadow["trades"].append(trade)
    
    write_json(shadow_path, shadow)
    
    # Also append to running journal
    journal = read_journal()
    
    journal.append(trade)
    write_json(JOURNAL_PATH, journal[-1000:])  # Keep last 1000
    
    print(f"OK Trade #{trade['trade_number']} logged: {trade['side']} at {trade['entry']}")
    return True

def close_trade(exit_price, exit_time=None, outcome=None, now=None):
    """
    Close the most recent open trade.
    """
    now = now or datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    
    shadow_path = SHADOW_DIR / f"session-{date_str}.json"
    shadow = read_json(shadow_path)
    
    if not shadow or not shadow.get("trades"):
        print("WARN No trades to close.")
        return False
    
    # Find the last open trade
    for trade in reversed(shadow["trades"]):
        if trade.get("outcome") == "open":
            trade["exit"] = exit_price
            trade["exit_time"] = (exit_time or now.isoformat())
            trade["points"] = round(
                (exit_price - trade["entry"]) if trade["side"] == "long" 
                else (trade["entry"] - exit_price), 2
            )
            trade["outcome"] = outcome or ("win" if trade["points"] > 0 else "loss" if trade["points"] < 0 else "scratch")
            
            # Default post-mortem
            trade["post_mortem"] = {
                "bias_correct": None,
                "timing_correct": None,
                "notes": ""
            }

            write_json(shadow_path, shadow)
            journal = read_journal()
            for journal_trade in reversed(journal):
                if (
                    journal_trade.get("trade_number") == trade.get("trade_number")
                    and journal_trade.get("entry_time") == trade.get("entry_time")
                    and journal_trade.get("symbol") == trade.get("symbol")
                ):
                    journal_trade.update({
                        "exit": trade["exit"],
                        "exit_time": trade["exit_time"],
                        "points": trade["points"],
                        "outcome": trade["outcome"],
                        "post_mortem": trade["post_mortem"],
                    })
                    break
            write_json(JOURNAL_PATH, journal[-1000:])
            
            print(f"OK Trade #{trade['trade_number']} closed: {trade['points']:+.1f} pts ({trade['outcome']})")
            return True
    
    print("WARN No open trades found to close.")
    return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  Log trade:  python session_shadow_trade_logger.py log '{\"side\":\"long\",\"entry\":30174}'")
        print("  Close trade: python session_shadow_trade_logger.py close <exit_price> [outcome]")
        sys.exit(1)
    
    action = sys.argv[1]
    if action == "log" and len(sys.argv) >= 3:
        data = json.loads(sys.argv[2])
        raise SystemExit(0 if log_trade(data) else 1)
    elif action == "close":
        if len(sys.argv) < 3:
            print("Close trade requires an exit price.")
            raise SystemExit(1)
        exit_price = float(sys.argv[2])
        outcome = sys.argv[3] if len(sys.argv) >= 4 else None
        raise SystemExit(0 if close_trade(exit_price, outcome=outcome) else 1)
    else:
        print("Unknown action. Use 'log' or 'close'.")
