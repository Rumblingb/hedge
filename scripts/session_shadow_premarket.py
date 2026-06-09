#!/usr/bin/env python3
"""
session_shadow_premarket.py — Pre-market session shadow generator.
Runs at 14:25 BST (09:25 ET) before NY open.
Outputs structured JSON with bias, conviction, leading indicator state, and trading plan.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
SHADOW_DIR = STATE / "session-shadows"
SHADOW_DIR.mkdir(parents=True, exist_ok=True)

def read_json(path):
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}

def get_market_regime():
    """Read HMM regime from fusion engine state or compute it."""
    # Read the latest regime summary if it exists
    regime = read_json(STATE / "regime-summary.json")
    if regime:
        return regime.get("regime", "unknown")
    return "unknown"

def get_topstep_quotes():
    """Read latest TopstepX realtime quotes."""
    quotes = read_json(STATE / "realtime-quote.latest.json")
    if not quotes:
        return {"nq": None, "es": None, "source": "unavailable"}
    return {
        "nq": {
            "bid": quotes.get("bid_nq"),
            "ask": quotes.get("ask_nq"),
            "price": quotes.get("price_nq"),
            "bid_size": quotes.get("bid_size_nq") or quotes.get("bidSizeNq") or quotes.get("bidSize"),
            "ask_size": quotes.get("ask_size_nq") or quotes.get("askSizeNq") or quotes.get("askSize"),
        },
        "es": {
            "bid": quotes.get("bid_es"),
            "ask": quotes.get("ask_es"),
            "price": quotes.get("price_es"),
            "bid_size": quotes.get("bid_size_es") or quotes.get("bidSizeEs"),
            "ask_size": quotes.get("ask_size_es") or quotes.get("askSizeEs"),
        },
        "source": quotes.get("source", "unknown"),
        "execution_grade": quotes.get("execution_grade", False),
        "timestamp": quotes.get("timestamp", ""),
    }

def infer_session_type(now):
    """Return a conservative session label without pretending to know holidays."""
    if now.weekday() >= 5:
        return "weekend"
    return "regular"

def get_last_session_postmortem():
    """Read the post-mortem from the previous session to carry forward learnings."""
    shadows = sorted(SHADOW_DIR.glob("session-*.json"))
    if not shadows:
        return {"first_trade_lesson": "first session — no prior data"}
    
    last = read_json(shadows[-1])
    lesson = "first session — no prior data"
    if last and isinstance(last, dict):
        pm = last.get("post_mortem")
        if pm and isinstance(pm, dict):
            first_outcome = pm.get("first_trade_outcome") or pm.get("outcome")
            first_lesson = pm.get("first_trade_lesson") or pm.get("lesson")
            if first_outcome == "loss" and first_lesson:
                lesson = f"PREVIOUS LESSON: {first_lesson}"
    
    return {"first_trade_lesson": lesson}

def estimate_microprice_imbalance(quotes):
    """Estimate order-book imbalance only when size data exists.

    Bid/ask prices alone cannot prove pressure. Returning ``None`` is safer
    than creating a fake confirmation signal from a spread midpoint.
    """
    if not quotes.get("nq") or not quotes["nq"].get("bid") or not quotes["nq"].get("ask"):
        return None
    nq = quotes["nq"]
    bid = nq.get("bid")
    ask = nq.get("ask")
    bid_size = nq.get("bid_size")
    ask_size = nq.get("ask_size")
    if bid and ask and ask > bid and bid_size and ask_size and (bid_size + ask_size) > 0:
        return round((bid_size - ask_size) / (bid_size + ask_size), 4)
    return None

def build_premarket_shadow(now=None):
    """Build and save the pre-market session shadow."""
    now = now or datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    day_of_week = now.strftime("%A")
    session_type = infer_session_type(now)
    
    # Gather data
    quotes = get_topstep_quotes()
    regime = get_market_regime()
    lesson = get_last_session_postmortem()
    microprice_imb = estimate_microprice_imbalance(quotes)
    
    shadow = {
        "session_date": date_str,
        "day_of_week": day_of_week,
        "session_type": session_type,
        "generated_at": now.isoformat(),
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "readyForExecution": False,
        "readyForDemoExpansion": False,
        "operator_read": "Session shadow records context and learning only; it does not approve routing.",
        
        "premarket": {
            "topstep_quotes": quotes,
            "hmm_regime": regime,
            "microprice_imbalance": microprice_imb,
            "last_session_lesson": lesson["first_trade_lesson"],
        },
        
        "plan": {
            "bias": "neutral",  # Will be filled by premarket-brief or manually
            "conviction": "low",
            "max_algo_contracts": 0,
            "max_manual_watch_contracts_if_daily_and_broker_cleared": 1,
            "max_trades": 2 if session_type != "regular" else 3,
            "session_loss_limit_pts": 50,
            "session_profit_lock_pts": 150,
            "route_approval_required": True,
            "broker_reconciliation_required": True,
            "notes": [],
        },
        
        "trades": [],
        "post_mortem": None,
    }
    
    # Save
    path = SHADOW_DIR / f"session-{date_str}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(shadow, f, indent=2, default=str)
    
    print(f"Pre-market shadow written: {path}")
    print(f"   Date: {date_str} ({day_of_week}, {session_type})")
    nq_quote = quotes.get("nq") if isinstance(quotes.get("nq"), dict) else {}
    print(f"   NQ: {nq_quote.get('price', 'N/A')}")
    print(f"   Regime: {regime}")
    print(f"   Microprice imbalance: {microprice_imb}")
    print(f"   Previous lesson: {lesson['first_trade_lesson'][:80]}")
    
    return shadow

if __name__ == "__main__":
    build_premarket_shadow()
