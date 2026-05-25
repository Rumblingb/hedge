#!/usr/bin/env python3
"""
Donchian(50) Breakout Signal — NQ/ES
======================================
Classic Turtle Trading system adapted from Donchian_ASX Test 75.
50-bar channel breakout on NQ 60m data.

Strategy:
- BUY when high[0] > highest high of last 50 bars (channel breakout)
- SELL when low[0] < lowest low of last 50 bars
- Exit: close when price reverts to 20-bar SMA or opposite breakout occurs
- Sizing: Fixed position (single contract NQ per signal)

Output: ~/.rumbling-hedge/state/donchian-signal.latest.json
"""
import json, os, sys
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict

STATE_DIR = Path(os.path.expanduser("~/.rumbling-hedge/state"))
STATE_DIR.mkdir(parents=True, exist_ok=True)
STATE_FILE = STATE_DIR / "donchian-signal.latest.json"

DATA_DIR = Path("/Users/brain/hedge/data/free")
LOOKBACK = 50
EXIT_SMA = 20

def log(msg):
    ts = datetime.now(timezone.utc).isoformat()
    print(f"[{ts}] {msg}")

def load_data(symbol: str = "NQ", timeframe: str = "60m") -> Optional[pd.DataFrame]:
    """Load OHLCV data"""
    files = [
        DATA_DIR / f"{symbol}-{timeframe}-60d.csv",
        DATA_DIR / f"{symbol}-{timeframe}-21d.csv",
        DATA_DIR / f"{symbol}-{timeframe}-5d.csv",
        DATA_DIR / f"{symbol}-{timeframe}-1d.csv",
        DATA_DIR / f"../{symbol}-{timeframe}.csv",
    ]
    for p in files:
        if p.exists():
            df = pd.read_csv(p)
            # Handle both 'time' and 'ts' column names
            if "time" in df.columns:
                df["time"] = pd.to_datetime(df["time"])
            elif "ts" in df.columns:
                df.rename(columns={"ts": "time"}, inplace=True)
                df["time"] = pd.to_datetime(df["time"])
            return df
    return None

def run(symbol: str = "NQ", timeframe: str = "60m") -> Optional[Dict]:
    log(f"Donchian({LOOKBACK}) Breakout — {symbol} {timeframe}")
    
    df = load_data(symbol, timeframe)
    if df is None or len(df) < LOOKBACK + 5:
        log(f"❌ Insufficient data for {symbol} {timeframe}")
        return None
    
    log(f"Loaded {len(df)} bars")
    
    closes = df["close"].values
    highs = df["high"].values
    lows = df["low"].values
    
    # Donchian channel
    highest_high = np.array([np.max(highs[max(0, i-LOOKBACK):i+1]) for i in range(len(highs))])
    lowest_low = np.array([np.min(lows[max(0, i-LOOKBACK):i+1]) for i in range(len(highs))])
    middle = (highest_high + lowest_low) / 2
    
    # Exit SMA
    exit_sma = pd.Series(closes).rolling(EXIT_SMA).mean().values
    
    current_high = float(highs[-1])
    current_low = float(lows[-1])
    current_close = float(closes[-1])
    prev_close = float(closes[-2])
    
    current_hi = float(highest_high[-1])
    current_lo = float(lowest_low[-1])
    current_mid = float(middle[-1])
    current_exit_sma = float(exit_sma[-1])
    
    # Previous bar channel for entry check
    prev_hi = float(highest_high[-2])
    prev_lo = float(lowest_low[-2])
    
    channel_width = current_hi - current_lo
    channel_width_pct = (channel_width / current_mid) * 100 if current_mid > 0 else 0
    
    # Entry signal
    entry_signal = "HOLD"
    direction = "neutral"
    entry_price = None
    stop_price = None
    target_price = None
    
    if current_high > prev_hi:  # New 50-bar high → buy
        entry_signal = "LONG_ENTRY"
        direction = "long"
        entry_price = current_high  # Buy at market / breakout level
        stop_price = current_lo  # Below channel = stop
        # Target: 2x channel width (Turtle variant)
        target_price = entry_price + channel_width * 2
        log(f"🚀 BREAKOUT LONG at {current_high:,.1f}")
        
    elif current_low < prev_lo:  # New 50-bar low → sell
        entry_signal = "SHORT_ENTRY"
        direction = "short"
        entry_price = current_low  # Sell at market
        stop_price = current_hi  # Above channel = stop
        target_price = entry_price - channel_width * 2
        log(f"🔻 BREAKOUT SHORT at {current_low:,.1f}")
    
    # Exit signal (for existing positions)
    exit_signal = "HOLD"
    
    if direction == "long" and current_close < current_exit_sma:
        exit_signal = "EXIT_LONG"
        log(f"Exit LONG: price {current_close:,.1f} < SMA({EXIT_SMA}) {current_exit_sma:,.1f}")
    elif direction == "short" and current_close > current_exit_sma:
        exit_signal = "EXIT_SHORT"
        log(f"Exit SHORT: price {current_close:,.1f} > SMA({EXIT_SMA}) {current_exit_sma:,.1f}")
    
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "strategy": f"Donchian({LOOKBACK}) Breakout",
        "symbol": symbol,
        "timeframe": timeframe,
        "price": {
            "close": round(current_close, 2),
            "high": round(current_high, 2),
            "low": round(current_low, 2),
        },
        "donchian_channel": {
            "high": round(current_hi, 2),
            "mid": round(current_mid, 2),
            "low": round(current_lo, 2),
            "width_pts": round(channel_width, 2),
            "width_pct": round(channel_width_pct, 2),
        },
        "exit_sma": round(current_exit_sma, 2),
        "entry_signal": entry_signal,
        "direction": direction,
        "entry_price": round(entry_price, 2) if entry_price else None,
        "stop_loss": round(stop_price, 2) if stop_price else None,
        "target": round(target_price, 2) if target_price else None,
        "risk_reward": round(abs(target_price - entry_price) / abs(stop_price - entry_price), 2) 
                       if entry_price and stop_price and abs(stop_price - entry_price) > 0 else None,
        "exit_signal": exit_signal,
        "source": "donchian-turtle-trading-ported",
    }
    
    with open(STATE_FILE, "w") as f:
        json.dump(output, f, indent=2)
    
    log(f"✅ Written to {STATE_FILE}")
    log(f"  → Channel: {current_hi:,.1f} / {current_mid:,.1f} / {current_lo:,.1f}")
    log(f"  → Width: {channel_width_pct:.2f}%")
    log(f"  → Signal: {entry_signal}")
    if entry_price:
        log(f"  → Entry: {entry_price:,.1f} | Stop: {stop_price:,.1f} | Target: {target_price:,.1f}")
    
    return output

if __name__ == "__main__":
    symbol = sys.argv[1] if len(sys.argv) > 1 else "NQ"
    timeframe = sys.argv[2] if len(sys.argv) > 2 else "60m"
    run(symbol, timeframe)
