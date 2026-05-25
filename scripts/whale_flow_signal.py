#!/usr/bin/env python3
"""
Whale Flow Signal Generator — Institutional Money Flow Overlay

Treats large-position moves as information signals: when whales buy/sell
in size, they may have information the market hasn't priced.

Data sources:
  1. Options unusual activity (NQ/SPX — volume/OI > 3×)
  2. Insider trades (SEC Form 4 — executives buying own stock)
  3. Institutional holdings changes (13F — hedge fund position changes)
  4. CME COT data (futures — commercial vs speculative positioning)

Output: ~/.rumbling-hedge/state/whale-flow-signal.latest.json
Consumed by: strategy-fusion engine as pre-trade confirmation overlay.
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── Config ──────────────────────────────────────────────────────────────
STATE_DIR = Path(os.path.expanduser("~/.rumbling-hedge/state"))
STATE_FILE = STATE_DIR / "whale-flow-signal.latest.json"
STATE_DIR.mkdir(parents=True, exist_ok=True)

# Symbols to scan for options unusual activity
SCAN_SYMBOLS = ["SPY", "QQQ", "SPX", "NDX", "IWM"]

# ── Helper ──────────────────────────────────────────────────────────────

def run_tool(tool_name: str, args: dict) -> dict:
    """Call a Hermes MCP tool via subprocess JSON-RPC pattern.
    Falls back gracefully on failure — this script is informational, not critical.
    """
    # Try using the hermes_tools pattern from execute_code
    try:
        # Build a mini-script that calls the tool
        import_cmd = f"from hermes_tools import {tool_name}"
        exec(import_cmd)
    except ImportError:
        pass
    return {"error": f"Cannot call {tool_name} directly — using fallback"}


def fetch_options_unusual() -> dict:
    """Collect options unusual activity across scan symbols."""
    results = {"calls": [], "puts": [], "symbols_scanned": SCAN_SYMBOLS}
    
    for symbol in SCAN_SYMBOLS:
        # We'll use a REST call pattern — can't import hermes_tools directly in script
        # so we use the available MCP tools indirectly
        try:
            result = subprocess.run(
                ["curl", "-s",
                 f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=5d",
                 "-H", "User-Agent: Mozilla/5.0"],
                capture_output=True, text=True, timeout=15
            )
            if result.returncode == 0:
                results[f"{symbol}_price_data"] = "fetched"
        except:
            pass
    
    return results


def calculate_whale_composite(options_signal: float, insider_signal: float,
                               institutional_signal: float = 0.0) -> dict:
    """Combine multiple whale flow signals into a composite.
    
    Returns:
        direction: "bullish" | "bearish" | "neutral"
        confidence: 0.0-1.0
        components: breakdown of individual signals
    """
    signals = [
        ("options_unusual", options_signal, 0.5),   # 50% weight
        ("insider_trades", insider_signal, 0.3),      # 30% weight
        ("institutional_13f", institutional_signal, 0.2),  # 20% weight
    ]
    
    composite = sum(s * w for _, s, w in signals) / sum(w for _, _, w in signals)
    
    if composite > 0.3:
        direction = "bullish"
        confidence = min(abs(composite), 1.0)
    elif composite < -0.3:
        direction = "bearish"
        confidence = min(abs(composite), 1.0)
    else:
        direction = "neutral"
        confidence = 0.0
    
    return {
        "direction": direction,
        "confidence": round(confidence, 3),
        "composite_score": round(composite, 3),
        "components": {name: {"score": round(s, 3), "weight": w}
                       for name, s, w in signals},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def compute_fallback_signal() -> dict:
    """Compute a reasonable signal using available data.
    
    When direct API calls aren't available, use price action + volume
    extremes as a proxy for institutional interest.
    """
    # Default: neutral — no data means no signal
    return {
        "direction": "neutral",
        "confidence": 0.0,
        "composite_score": 0.0,
        "components": {
            "options_unusual": {"score": 0.0, "weight": 0.5, "status": "no_data"},
            "insider_trades": {"score": 0.0, "weight": 0.3, "status": "no_data"},
            "institutional_13f": {"score": 0.0, "weight": 0.2, "status": "no_data"},
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "method": "fallback_no_data",
    }


# ── Main ────────────────────────────────────────────────────────────────

def main():
    print("🐋 Whale Flow Signal Generator — running...")
    
    # Try to fetch options unusual activity
    options_data = fetch_options_unusual()
    
    # For now, produce a neutral signal (placeholder until MCP tools
    # are accessible from standalone scripts — see integration note below)
    signal = compute_fallback_signal()
    
    # Save state
    with open(STATE_FILE, "w") as f:
        json.dump(signal, f, indent=2)
    
    print(f"✅ Signal written to {STATE_FILE}")
    print(f"   Direction: {signal['direction']}")
    print(f"   Confidence: {signal['confidence']}")
    print(f"   Method: {signal.get('method', 'live')}")
    print()
    print("── Integration Note ──")
    print("This script runs standalone via cron. To get live data:")
    print("  Phase 1 (now):     File-based fallback, neutral signal")
    print("  Phase 2 (next):    Add curl-based COT data from CFTC.gov")
    print("  Phase 3 (soon):    Wire into strategy-fusion as pre-trade gate")
    print("  Phase 4:           Add block trade scanning from CME")
    print()
    print("Consumer: strategy-fusion engine reads .whale-flow-signal.latest.json")
    print("Signal: When direction matches strategy → full size")
    print("         When direction contradicts → halve size")
    print("         When neutral → standard execution")


if __name__ == "__main__":
    main()
