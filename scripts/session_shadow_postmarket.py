#!/usr/bin/env python3
"""
session_shadow_postmarket.py — Post-market session shadow aggregator.
Runs at 21:00 BST (16:00 ET) after NY close.
Aggregates trades, runs first-trade post-mortem, writes to Obsidian.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
SHADOW_DIR = STATE / "session-shadows"
OBSIDIAN_HERMES = Path.home() / "Documents" / "memorybrain" / "Agent-Hermes"
OBSIDIAN_SHARED = Path.home() / "Documents" / "memorybrain" / "Agent-Shared"

def read_json(path):
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}

def trade_belongs_to_session(trade, date_str):
    for key in ("entry_time", "timestamp", "exit_time"):
        value = trade.get(key)
        if isinstance(value, str) and value.startswith(date_str):
            return True
    return False

def get_last_trades(date_str):
    """Pull the latest trades from the operating log or trade journal."""
    journal = read_json(STATE / "trade-journal.latest.json")
    if journal and isinstance(journal, list):
        session_trades = [trade for trade in journal if isinstance(trade, dict) and trade_belongs_to_session(trade, date_str)]
        return session_trades[-10:]
    
    # Fallback: read from daily learning
    learning = read_json(STATE / "topstep-daily-learning.latest.json")
    if learning:
        trades = learning.get("trades", [])
        return [trade for trade in trades if isinstance(trade, dict) and trade_belongs_to_session(trade, date_str)]
    return []

def calculate_session_stats(trades):
    """Calculate aggregate session stats from trade list."""
    if not trades:
        return {
            "total_trades": 0, "wins": 0, "losses": 0, "scratches": 0,
            "net_points": 0, "win_rate": 0, "avg_r": 0,
        }
    
    wins = sum(1 for t in trades if t.get("outcome") == "win" or t.get("points", 0) > 0)
    losses = sum(1 for t in trades if t.get("outcome") == "loss" or t.get("points", 0) < 0)
    scratches = sum(1 for t in trades if t.get("outcome") == "scratch" or t.get("points", 0) == 0)
    total_pts = sum(t.get("points", 0) for t in trades)
    
    return {
        "total_trades": len(trades),
        "wins": wins, "losses": losses, "scratches": scratches,
        "net_points": round(total_pts, 2),
        "win_rate": round(wins / len(trades) * 100, 1) if trades else 0,
        "avg_r": round(total_pts / len(trades), 2) if trades else 0,
    }

def first_trade_postmortem(trades):
    """Analyze the first trade of the session for learning data."""
    if not trades:
        return {
            "outcome": "no_trades",
            "lesson": "No trades executed this session — valid when no clear signal",
            "bias_correct": None,
            "timing_correct": None,
        }
    
    first = trades[0]
    outcome = "win" if first.get("points", 0) > 0 else "loss" if first.get("points", 0) < 0 else "scratch"
    
    # Determine lesson based on outcome
    if outcome == "loss":
        # Categorize the failure
        if first.get("post_mortem"):
            pm = first["post_mortem"]
            if pm.get("bias_wrong"):
                lesson = f"Bias was wrong. Pre-market thesis was {pm.get('intended_direction')} but market moved opposite."
            elif pm.get("timing_early"):
                lesson = f"Entry was too early by {pm.get('bars_premature', '?')} bars. Wait for 1-3m pullback confirmation."
            elif pm.get("stop_too_tight"):
                lesson = "Stop was too tight for the session's average range. Increase ATR multiplier."
            elif pm.get("target_too_far"):
                lesson = "Target was too far. Market gave partial move but not full target."
            else:
                lesson = f"Trade lost ({first.get('points', 0)} pts). Review entry timing and bias."
        else:
            lesson = f"First trade lost ({first.get('points', 0)} pts). Check: bias correct? timing correct? stop placement?"
    elif outcome == "win":
        lesson = f"First trade won ({first.get('points', 0)} pts). Leading indicators confirmed the direction."
    else:
        lesson = "First trade scratched. Entry was fine but exit triggered early."
    
    return {
        "outcome": outcome,
        "entry_price": first.get("entry"),
        "exit_price": first.get("exit"),
        "points": first.get("points"),
        "lesson": lesson,
        "bias_correct": None,  # Filled by human or auto from pre-market comparison
        "timing_correct": None,
    }

def build_postmarket_shadow(now=None):
    """Build and save the post-market session shadow."""
    now = now or datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    
    # Load pre-market shadow
    pre_shadow = read_json(SHADOW_DIR / f"session-{date_str}.json")
    if not pre_shadow:
        print(f"⚠ No pre-market shadow found for {date_str}. Creating post-only.")
        pre_shadow = {"session_date": date_str, "premarket": {}, "plan": {}}
    
    # Get trades
    trades = get_last_trades(date_str)
    
    # Run post-mortem
    pm = first_trade_postmortem(trades)
    stats = calculate_session_stats(trades)
    
    # Build full shadow
    shadow = {
        **pre_shadow,
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "readyForExecution": False,
        "readyForDemoExpansion": False,
        "operator_read": "Postmarket session shadow is learning memory only; it does not approve routing.",
        "trades": trades,
        "post_mortem": {
            **pm,
            "session_stats": stats,
            "total_trades": stats["total_trades"],
            "adjustments_for_next_session": [],
        },
        "postmarket_generated_at": now.isoformat(),
    }
    
    # Save
    path = SHADOW_DIR / f"session-{date_str}.json"
    with open(path, "w") as f:
        json.dump(shadow, f, indent=2, default=str)
    
    # Write Obsidian daily note
    obsidian_path = OBSIDIAN_HERMES / "daily" / f"{date_str}.md"
    trade_summary = ""
    for i, t in enumerate(trades[-5:], 1):
        pts = t.get("points", 0)
        marker = "WIN" if pts > 0 else "LOSS" if pts < 0 else "SCRATCH"
        trade_summary += f"  Trade {i}: {marker} {pts:+.1f} pts ({t.get('side', '?')} at {t.get('entry', '?')})\n"
    
    shadow_note = f"""
## Session Shadow — {date_str}
**Bias**: {pre_shadow.get('plan', {}).get('bias', 'not set')}
**Session type**: {pre_shadow.get('session_type', 'full')}

### Trades
{trade_summary or '  No trades recorded'}

### First Trade Post-Mortem
- Outcome: {pm.get('outcome', 'N/A')}
- Lesson: {pm.get('lesson', 'N/A')}

### Stats
- Net points: {stats['net_points']:+.1f}
- Win rate: {stats['win_rate']}%
- Total trades: {stats['total_trades']}

### Session Shadow File
File: `file://{path}`
"""
    
    # Check if Obsidian daily exists, append if so
    if obsidian_path.exists():
        with open(obsidian_path, "a") as f:
            f.write(shadow_note)
    else:
        with open(obsidian_path, "w") as f:
            f.write(shadow_note)
    
    print(f"Post-market shadow written: {path}")
    print(f"   Trades: {stats['total_trades']} ({stats['wins']}W/{stats['losses']}L)")
    print(f"   Net: {stats['net_points']:+.1f} pts")
    print(f"   First trade: {pm['outcome']} — {pm['lesson'][:80]}")
    print(f"   Obsidian note updated: {obsidian_path}")
    
    return shadow

if __name__ == "__main__":
    build_postmarket_shadow()
