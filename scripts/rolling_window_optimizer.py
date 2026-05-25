#!/usr/bin/env python3
"""
Rolling Window Optimizer — Adaptive Lookback Parameters

The biggest single optimization available: different market regimes need
different lookback windows. A 60-bar ORB that works in trending markets
fails in ranging markets. This module dynamically selects the optimal
window based on recent strategy performance across multiple window sizes.

Integration: Produces JSON consumed by master_bridge.py and strategy fusion.
Output: ~/.rumbling-hedge/state/rolling-window-params.latest.json
"""

import json
import os
import sys
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Tuple, Optional

# ── Config ──────────────────────────────────────────────────────────────
STATE_DIR = Path(os.path.expanduser("~/.rumbling-hedge/state"))
STATE_FILE = STATE_DIR / "rolling-window-params.latest.json"
STATE_DIR.mkdir(parents=True, exist_ok=True)

# Window candidates — each is (name, lookback_bars, exit_bars, atr_mult)
WINDOW_CANDIDATES = {
    "fast":     {"lookback": 8,  "exit_bars": 3,  "atr_stop": 1.0, "atr_target": 1.5, "desc": "Fast scalping"},
    "medium":   {"lookback": 14, "exit_bars": 5,  "atr_stop": 1.5, "atr_target": 2.0, "desc": "Standard swing"},
    "slow":     {"lookback": 21, "exit_bars": 8,  "atr_stop": 2.0, "atr_target": 3.0, "desc": "Trend riding"},
    "macro":    {"lookback": 50, "exit_bars": 12, "atr_stop": 2.5, "atr_target": 4.0, "desc": "Macro moves"},
}

# History window for performance evaluation (bars)
EVAL_WINDOW = 60

# Regime-to-window mapping (fallback when no performance data)
REGIME_DEFAULT = {
    "trending-bull": "slow",
    "trending-bear": "slow",
    "ranging":       "fast",
    "breakout":      "medium",
    "volatile":      "macro",
    "quiet":         "fast",
    "reversal":      "medium",
    "news":          "macro",
}


def fetch_recent_bars() -> Optional[pd.DataFrame]:
    """Load the most recent NQ 60m data."""
    candidates = list(Path("/Users/brain/hedge/data/free").glob("*60m*60d*.csv"))
    candidates.extend(Path("/Users/brain/hedge/data/free").glob("*60m*.csv"))
    
    if not candidates:
        # Try NQ=F from Yahoo directly
        return None
    
    # Use the most recent file
    latest = max(candidates, key=lambda p: p.stat().st_mtime)
    if "NQ" not in latest.name and "ALL" not in latest.name:
        # Try another file
        for c in sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True):
            if "NQ" in c.name or "ALL" in c.name:
                latest = c
                break
    
    try:
        df = pd.read_csv(latest)
        if "symbol" in df.columns:
            df = df[df["symbol"] == "NQ"] if "NQ" in df["symbol"].values else df
        df["ts"] = pd.to_datetime(df["ts"])
        df = df.sort_values("ts")
        print(f"Loaded {len(df)} bars from {latest.name}")
        return df
    except Exception as e:
        print(f"Failed to load bars: {e}")
        return None


def compute_regime(bars: pd.DataFrame) -> str:
    """Simple regime detection from recent bars."""
    if bars is None or len(bars) < 20:
        return "unknown"
    
    closes = bars["close"].values[-60:] if len(bars) >= 60 else bars["close"].values
    returns = np.diff(np.log(closes))
    
    vol = np.std(returns) * np.sqrt(252 * 6.5)  # Annualized vol
    recent_returns = returns[-20:] if len(returns) >= 20 else returns
    trend = np.mean(recent_returns) * 20  # 20-period momentum
    
    # ATR-based range measure
    if all(c in bars.columns for c in ["high", "low", "close"]):
        recent = bars.tail(20)
        true_ranges = np.maximum(
            recent["high"].values - recent["low"].values,
            np.maximum(
                np.abs(recent["high"].values - recent["close"].shift(1).values),
                np.abs(recent["low"].values - recent["close"].shift(1).values),
            )
        )[~np.isnan(np.abs(recent["high"].values - recent["close"].shift(1).values))]
        avg_range = np.mean(true_ranges[-10:]) if len(true_ranges) >= 10 else 0
        atr_pct = avg_range / closes[-1] * 100 if closes[-1] != 0 else 0
    else:
        atr_pct = 0.2  # default
    
    # Classify
    if vol > 0.4:
        if abs(trend) > 0.02:
            return "trending-bull" if trend > 0 else "trending-bear"
        else:
            return "volatile"
    elif abs(trend) > 0.01:
        return "trending-bull" if trend > 0 else "trending-bear"
    elif atr_pct < 0.15:
        return "quiet"
    else:
        return "ranging"


def evaluate_windows(bars: pd.DataFrame) -> Dict[str, float]:
    """Evaluate each window candidate on recent data using ORB-like logic."""
    if bars is None or len(bars) < 30:
        return {}
    
    scores = {}
    closes = bars["close"].values
    highs = bars["high"].values if "high" in bars.columns else closes
    lows = bars["low"].values if "low" in bars.columns else closes
    
    for wname, wcfg in WINDOW_CANDIDATES.items():
        lb = wcfg["lookback"]
        eb = wcfg["exit_bars"]
        
        trades = []
        for i in range(lb, min(len(closes) - eb, len(closes) - 1)):
            window_high = np.max(highs[i-lb:i])
            window_low = np.min(lows[i-lb:i])
            entry = closes[i]
            
            # Long breakout
            if entry > window_high * 1.001:  # 0.1% above range high
                exit_price = closes[min(i + eb, len(closes) - 1)]
                r = (exit_price - entry) / (np.std(closes[i-20:i]) + 1e-10)
                trades.append(r)
            
            # Short breakout
            elif entry < window_low * 0.999:
                exit_price = closes[min(i + eb, len(closes) - 1)]
                r = (entry - exit_price) / (np.std(closes[i-20:i]) + 1e-10)
                trades.append(r)
        
        if len(trades) >= 3:
            win_rate = sum(1 for t in trades if t > 0) / len(trades)
            avg_r = np.mean(trades)
            scores[wname] = win_rate * avg_r * np.sqrt(len(trades))
        else:
            scores[wname] = 0.0
    
    return scores


def select_best_window(regime: str, scores: Dict[str, float]) -> Tuple[str, dict]:
    """Select the best window based on performance scores and regime fallback."""
    if scores and max(scores.values()) > 0:
        best = max(scores, key=scores.get)
        if scores[best] > 0.5:  # meaningful edge detected
            return best, WINDOW_CANDIDATES[best]
    
    # Fall back to regime default
    default = REGIME_DEFAULT.get(regime, "medium")
    return default, WINDOW_CANDIDATES[default]


def main():
    print("📐 Rolling Window Optimizer")
    print("=" * 50)
    
    # 1. Load data
    bars = fetch_recent_bars()
    
    # 2. Detect regime
    regime = compute_regime(bars)
    print(f"Current regime: {regime}")
    
    # 3. Evaluate windows
    scores = evaluate_windows(bars)
    print("\nWindow scores:")
    for wname, score in sorted(scores.items(), key=lambda x: -x[1]):
        print(f"  {wname:8s} ({WINDOW_CANDIDATES[wname]['desc']:15s}): score={score:.3f}")
    
    # 4. Select best
    best_name, best_params = select_best_window(regime, scores)
    print(f"\nSelected window: {best_name} ({best_params['desc']})")
    
    # 5. Build output
    output = {
        "selected": best_name,
        "parameters": best_params,
        "regime": regime,
        "scores": {k: round(v, 4) for k, v in sorted(scores.items(), key=lambda x: -x[1])},
        "candidates_available": list(WINDOW_CANDIDATES.keys()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "method": "performance_scores" if scores and max(scores.values()) > 0.5 else f"regime_fallback_{regime}",
    }
    
    with open(STATE_FILE, "w") as f:
        json.dump(output, f, indent=2)
    
    print(f"\n✅ Written to {STATE_FILE}")
    print(f"  → Consumed by: master_bridge.py, strategy-fusion engine")
    print(f"  → Effect: {'Adaptive lookback' if output['method'] != 'regime_fallback' else 'Regime-based default'}")


if __name__ == "__main__":
    main()
