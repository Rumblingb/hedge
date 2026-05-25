#!/usr/bin/env python3
"""
VWAP Agent — Volume-Weighted Average Price Mean Reversion Signal
=================================================================
Distance from VWAP as a mean-reversion signal for NQ/ES.

Theory: In mean-reversion regimes (Hurst < 0.3), price extremes 
relative to VWAP revert. Entry at 2+ standard deviation extremes.
"""
import json, os, sys
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime, timezone

HOME = os.environ["HOME"]
STATE_DIR = Path(HOME) / ".rumbling-hedge" / "state"
DATA_DIR = Path(HOME) / "hedge" / "data" / "free"

def load_bars(symbol, timeframe, days=5):
    """Load OHLCV data, compute VWAP, return bars with VWAP."""
    for suffix in ["-60d.csv", "-21d.csv", "-5d.csv", "-1d.csv"]:
        p = DATA_DIR / f"{symbol}-{timeframe}{suffix}"
        if p.exists():
            df = pd.read_csv(p)
            if "ts" in df.columns and "time" not in df.columns:
                df = df.rename(columns={"ts": "time"})
            df["time"] = pd.to_datetime(df["time"])
            df = df.sort_values("time")
            df["typical"] = (df["high"] + df["low"] + df["close"]) / 3
            df["vwap"] = (df["typical"] * df["volume"]).rolling(20).sum() / df["volume"].rolling(20).sum()
            df["vwap_std"] = df["typical"].rolling(20).std()
            df["vwap_z"] = (df["close"] - df["vwap"]) / df["vwap_std"]
            # Replace inf/nan
            df["vwap_z"] = df["vwap_z"].replace([np.inf, -np.inf], np.nan).fillna(0)
            return df
    return None

def compute_signal(df):
    """Generate VWAP mean-reversion signal."""
    if df is None or len(df) < 25:
        return {"direction": "neutral", "confidence": 0.0, "z_score": 0, "vwap": 0, "close": 0}
    
    last = df.iloc[-1]
    z = last.get("vwap_z", 0) if not pd.isna(last.get("vwap_z")) else 0
    vwap = last.get("vwap", 0) if not pd.isna(last.get("vwap")) else 0
    close = last.get("close", 0)
    
    # Mean reversion signals
    if z > 2.0 and close > vwap:
        # Price far ABOVE VWAP -> expect reversion DOWN
        return {"direction": "short", "confidence": min(0.7, 0.5 + abs(z) * 0.1),
                "z_score": round(z, 2), "vwap": round(vwap, 2), "close": round(close, 2)}
    elif z < -2.0 and close < vwap:
        # Price far BELOW VWAP -> expect reversion UP
        return {"direction": "long", "confidence": min(0.7, 0.5 + abs(z) * 0.1),
                "z_score": round(z, 2), "vwap": round(vwap, 2), "close": round(close, 2)}
    elif abs(z) > 1.5:
        # Moderate extreme -> weaker signal
        if z > 0:
            return {"direction": "short", "confidence": 0.55,
                    "z_score": round(z, 2), "vwap": round(vwap, 2), "close": round(close, 2)}
        else:
            return {"direction": "long", "confidence": 0.55,
                    "z_score": round(z, 2), "vwap": round(vwap, 2), "close": round(close, 2)}
    
    return {"direction": "neutral", "confidence": 0.0, "z_score": round(z, 2),
            "vwap": round(vwap, 2), "close": round(close, 2)}

def main():
    results = {}
    for symbol in ["NQ", "ES"]:
        df = load_bars(symbol, "60m", 60)
        signal = compute_signal(df)
        results[symbol] = signal
        
        # Historical VWAP z-score stats
        if df is not None and len(df) > 25:
            zs = df["vwap_z"].dropna()
            results[f"{symbol}_z_mean"] = round(float(zs.mean()), 2)
            results[f"{symbol}_z_std"] = round(float(zs.std()), 2)
            results[f"{symbol}_z_5pct"] = round(float(zs.quantile(0.05)), 2)
            results[f"{symbol}_z_95pct"] = round(float(zs.quantile(0.95)), 2)
    
    results["generated_at"] = datetime.now(timezone.utc).isoformat()
    
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    out = STATE_DIR / "vwap-signal.latest.json"
    out.write_text(json.dumps(results, indent=2))
    
    # Print summary
    for sym in ["NQ", "ES"]:
        s = results.get(sym, {})
        print(f"{sym}: {s.get('direction', 'neutral')} (z={s.get('z_score',0):+.2f}, conf={s.get('confidence',0):.2f})")
        print(f"  VWAP=${s.get('vwap',0):.0f}, Close=${s.get('close',0):.0f}")
    print(f"✅ Written to {out}")

if __name__ == "__main__":
    main()
