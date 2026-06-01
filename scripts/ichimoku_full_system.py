#!/usr/bin/env python3
"""
Full Ichimoku Kinko Hyo System — All 6 Signals
=================================================
Complete implementation of the Japanese Ichimoku system 
as a NQ/ES trend filter and standalone signal generator.

6 Signals:
1. TK Cross   — Tenkan crosses Kijun = trend change
2. Price/Cloud — Price above/below cloud = trend direction
3. Cloud Twist  — Senkou A crosses Senkou B = trend reversal
4. Chikou Confirm — Chikou above/below price 26 bars ago = confirmation
5. Kumo Breakout  — Price breaks through cloud = strong trend
6. Kijun Bounce   — Price bounces off Kijun in trend = re-entry

Standard Ichimoku periods:
- Tenkan-sen: 9 bars (fast)
- Kijun-sen: 26 bars (slow) 
- Senkou B: 52 bars (cloud edge)
- Chikou: 26 bars behind

Output: ~/.rumbling-hedge/state/ichimoku-signal.latest.json
"""
import json, os, sys
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = Path(os.environ.get("BILL_STATE_DIR", str(ROOT / ".rumbling-hedge/state"))).expanduser()
STATE_DIR.mkdir(parents=True, exist_ok=True)
STATE_FILE = STATE_DIR / "ichimoku-signal.latest.json"

DATA_DIR = Path("/Users/brain/hedge/data/free")

PERIODS = {"tenkan": 9, "kijun": 26, "senkou_b": 52, "chikou": 26}

def log(msg):
    ts = datetime.now(timezone.utc).isoformat()
    print(f"[{ts}] {msg}")

def load_data(symbol: str = "NQ", timeframe: str = "60m") -> Optional[pd.DataFrame]:
    files = [
        DATA_DIR / f"{symbol}-{timeframe}-60d.csv",
        DATA_DIR / f"{symbol}-{timeframe}-21d.csv",
        DATA_DIR / f"{symbol}-{timeframe}-5d.csv",
    ]
    for p in files:
        if p.exists():
            df = pd.read_csv(p)
            if "time" in df.columns:
                df["time"] = pd.to_datetime(df["time"])
            elif "ts" in df.columns:
                df.rename(columns={"ts": "time"}, inplace=True)
                df["time"] = pd.to_datetime(df["time"])
            return df
    return None

def donchian(high: np.ndarray, low: np.ndarray, period: int) -> np.ndarray:
    """Donchian midpoint: (highest high + lowest low) / 2 over period"""
    hh = pd.Series(high).rolling(period).max().values
    ll = pd.Series(low).rolling(period).min().values
    return (hh + ll) / 2

def compute_ichimoku(df: pd.DataFrame) -> Dict:
    """Compute all Ichimoku components"""
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    
    n = len(highs)
    
    # 1. Tenkan-sen (Conversion Line): (9-period high + 9-period low) / 2
    tenkan_hi = pd.Series(highs).rolling(PERIODS["tenkan"]).max().values
    tenkan_lo = pd.Series(lows).rolling(PERIODS["tenkan"]).min().values
    tenkan = (tenkan_hi + tenkan_lo) / 2
    
    # 2. Kijun-sen (Base Line): (26-period high + 26-period low) / 2
    kijun_hi = pd.Series(highs).rolling(PERIODS["kijun"]).max().values
    kijun_lo = pd.Series(lows).rolling(PERIODS["kijun"]).min().values
    kijun = (kijun_hi + kijun_lo) / 2
    
    # 3. Senkou A (Leading Span A): (Tenkan + Kijun) / 2, shifted 26 bars forward
    senkou_a = np.full(n, np.nan)
    for i in range(n):
        if not np.isnan(tenkan[i]) and not np.isnan(kijun[i]):
            shift_idx = i + PERIODS["kijun"]
            if shift_idx < n:
                senkou_a[shift_idx] = (tenkan[i] + kijun[i]) / 2
    
    # 4. Senkou B (Leading Span B): Donchian(52) shifted 26 forward
    donchian_52 = donchian(highs, lows, PERIODS["senkou_b"])
    senkou_b = np.full(n, np.nan)
    for i in range(n):
        if not np.isnan(donchian_52[i]):
            shift_idx = i + PERIODS["kijun"]
            if shift_idx < n:
                senkou_b[shift_idx] = donchian_52[i]
    
    # 5. Chikou Span (Lagging Span): close shifted 26 bars BACK
    chikou = np.full(n, np.nan)
    for i in range(PERIODS["chikou"], n):
        chikou[i - PERIODS["chikou"]] = closes[i]
    
    # Cloud (Kumo): between Senkou A and Senkou B
    cloud_top = np.where(senkou_a > senkou_b, senkou_a, senkou_b)
    cloud_bottom = np.where(senkou_a < senkou_b, senkou_a, senkou_b)
    
    return {
        "tenkan": tenkan,
        "kijun": kijun,
        "senkou_a": senkou_a,
        "senkou_b": senkou_b,
        "chikou": chikou,
        "cloud_top": cloud_top,
        "cloud_bottom": cloud_bottom,
    }

def evaluate_signals(ichi: Dict, closes: np.ndarray, highs: np.ndarray, lows: np.ndarray) -> List[Dict]:
    """Evaluate all 6 Ichimoku signals at current bar"""
    n = len(closes)
    signals = []
    
    cp = closes[-1]
    tenkan_curr = ichi["tenkan"][-1]
    kijun_curr = ichi["kijun"][-1]
    tenkan_prev = ichi["tenkan"][-2]
    kijun_prev = ichi["kijun"][-2]
    
    sa = ichi["senkou_a"]
    sb = ichi["senkou_b"]
    sa_curr = sa[-1]
    sb_curr = sb[-1]
    sa_prev = sa[-2]
    sb_prev = sb[-2]
    
    chikou_curr = ichi["chikou"][-1]
    close_26ago = closes[-PERIODS["chikou"]] if n > PERIODS["chikou"] else None
    
    ct = ichi["cloud_top"]
    cb = ichi["cloud_bottom"]
    ct_curr = ct[-1] if not np.isnan(ct[-1]) else None
    cb_curr = cb[-1] if not np.isnan(cb[-1]) else None
    
    # --- Signal 1: TK Cross ---
    if not np.isnan(tenkan_curr) and not np.isnan(kijun_curr) and not np.isnan(tenkan_prev) and not np.isnan(kijun_prev):
        if tenkan_prev <= kijun_prev and tenkan_curr > kijun_curr:
            signals.append({"type": "TK_CROSS_BULLISH", "strength": 0.65,
                           "reason": f"Tenkan ({tenkan_curr:,.1f}) crossed above Kijun ({kijun_curr:,.1f})"})
        elif tenkan_prev >= kijun_prev and tenkan_curr < kijun_curr:
            signals.append({"type": "TK_CROSS_BEARISH", "strength": 0.65,
                           "reason": f"Tenkan ({tenkan_curr:,.1f}) crossed below Kijun ({kijun_curr:,.1f})"})
    
    # --- Signal 2: Price vs Cloud ---
    if ct_curr is not None and cb_curr is not None:
        if cp > ct_curr:
            signals.append({"type": "ABOVE_CLOUD", "strength": 0.50,
                           "reason": f"Price {cp:,.1f} above cloud top {ct_curr:,.1f}"})
        elif cp < cb_curr:
            signals.append({"type": "BELOW_CLOUD", "strength": 0.50,
                           "reason": f"Price {cp:,.1f} below cloud bottom {cb_curr:,.1f}"})
        else:
            signals.append({"type": "IN_CLOUD", "strength": 0.20,
                           "reason": f"Price {cp:,.1f} inside cloud ({cb_curr:,.1f}-{ct_curr:,.1f})"})
    
    # --- Signal 3: Cloud Twist ---
    if not np.isnan(sa_curr) and not np.isnan(sb_curr) and not np.isnan(sa_prev) and not np.isnan(sb_prev):
        if sa_prev <= sb_prev and sa_curr > sb_curr:
            signals.append({"type": "CLOUD_TWIST_BULLISH", "strength": 0.70,
                           "reason": "Senkou A crossed above Senkou B (cloud turns green)"})
        elif sa_prev >= sb_prev and sa_curr < sb_curr:
            signals.append({"type": "CLOUD_TWIST_BEARISH", "strength": 0.70,
                           "reason": "Senkou A crossed below Senkou B (cloud turns red)"})
    
    # --- Signal 4: Chikou Confirmation ---
    if chikou_curr is not None and close_26ago is not None and not np.isnan(chikou_curr):
        if chikou_curr > close_26ago:
            signals.append({"type": "CHIKOU_BULLISH", "strength": 0.55,
                           "reason": f"Chikou ({chikou_curr:,.1f}) above price 26 ago ({close_26ago:,.1f})"})
        else:
            signals.append({"type": "CHIKOU_BEARISH", "strength": 0.55,
                           "reason": f"Chikou ({chikou_curr:,.1f}) below price 26 ago ({close_26ago:,.1f})"})
    
    # --- Signal 5: Kumo Breakout ---
    curr_high = highs[-1]
    curr_low = lows[-1]
    if ct_curr is not None and cb_curr is not None:
        prev_high = highs[-2]
        prev_low = lows[-2]
        
        # Price was in/under cloud and now broke above
        if prev_high <= ct_curr and curr_high > ct_curr:
            signals.append({"type": "KUMO_BREAKOUT_BULLISH", "strength": 0.75,
                           "reason": f"Price broke above cloud top {ct_curr:,.1f}"})
        # Price was in/above cloud and now broke below
        if prev_low >= cb_curr and curr_low < cb_curr:
            signals.append({"type": "KUMO_BREAKOUT_BEARISH", "strength": 0.75,
                           "reason": f"Price broke below cloud bottom {cb_curr:,.1f}"})
    
    # --- Signal 6: Kijun Bounce ---
    if not np.isnan(kijun_curr):
        # Price approaching/bouncing off Kijun in uptrend
        if cp > kijun_curr and cp < kijun_curr * 1.01:  # Within 1% above Kijun
            signals.append({"type": "KIJUN_BOUNCE_BULLISH", "strength": 0.60,
                           "reason": f"Price bouncing off Kijun support {kijun_curr:,.1f}"})
        # Price approaching/bouncing off Kijun in downtrend
        if cp < kijun_curr and cp > kijun_curr * 0.99:  # Within 1% below Kijun
            signals.append({"type": "KIJUN_BOUNCE_BEARISH", "strength": 0.60,
                           "reason": f"Price rejecting at Kijun resistance {kijun_curr:,.1f}"})
    
    return signals

def run(symbol: str = "NQ", timeframe: str = "60m") -> Optional[Dict]:
    log(f"Full Ichimoku System — {symbol} {timeframe}")
    
    df = load_data(symbol, timeframe)
    if df is None or len(df) < max(PERIODS.values()) + 10:
        log(f"❌ Insufficient data")
        return None
    
    log(f"Loaded {len(df)} bars")
    
    closes = df["close"].values
    highs = df["high"].values
    lows = df["low"].values
    
    ichi = compute_ichimoku(df)
    signals = evaluate_signals(ichi, closes, highs, lows)
    
    # Compute trend from signals
    bullish_signals = sum(1 for s in signals if "BULLISH" in s["type"] or 
                          s["type"] in ("ABOVE_CLOUD", "KIJUN_BOUNCE_BULLISH"))
    bearish_signals = sum(1 for s in signals if "BEARISH" in s["type"] or
                          s["type"] in ("BELOW_CLOUD", "KIJUN_BOUNCE_BEARISH"))
    
    if bullish_signals > bearish_signals:
        trend = "bullish"
        strength = min(bullish_signals / max(bearish_signals, 1) * 0.15, 0.75)
    elif bearish_signals > bullish_signals:
        trend = "bearish"
        strength = min(bearish_signals / max(bullish_signals, 1) * 0.15, 0.75)
    else:
        trend = "neutral"
        strength = 0.0
    
    cp = closes[-1]
    cp_prev = closes[-2]
    change_pts = cp - cp_prev
    change_pct = (change_pts / cp_prev) * 100
    
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol,
        "timeframe": timeframe,
        "price": round(cp, 2),
        "change_pct": round(change_pct, 2),
        "ichimoku": {
            "tenkan": round(float(ichi["tenkan"][-1]), 2) if not np.isnan(ichi["tenkan"][-1]) else None,
            "kijun": round(float(ichi["kijun"][-1]), 2) if not np.isnan(ichi["kijun"][-1]) else None,
            "senkou_a": round(float(ichi["senkou_a"][-1]), 2) if not np.isnan(ichi["senkou_a"][-1]) else None,
            "senkou_b": round(float(ichi["senkou_b"][-1]), 2) if not np.isnan(ichi["senkou_b"][-1]) else None,
            "cloud_top": round(float(np.nanmax([ichi["senkou_a"][-1], ichi["senkou_b"][-1]])), 2) 
                         if not np.isnan(ichi["senkou_a"][-1]) and not np.isnan(ichi["senkou_b"][-1]) else None,
            "cloud_bottom": round(float(np.nanmin([ichi["senkou_a"][-1], ichi["senkou_b"][-1]])), 2) 
                            if not np.isnan(ichi["senkou_a"][-1]) and not np.isnan(ichi["senkou_b"][-1]) else None,
        },
        "signals": signals,
        "signal_count": len(signals),
        "bullish_signals": bullish_signals,
        "bearish_signals": bearish_signals,
        "trend": trend,
        "trend_strength": round(strength, 3),
        "action": "HOLD",
        "direction": trend,
        "source": "ichimoku-full-system",
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "tradable_signal": False,
        "promoted_for_execution": False,
        "readyForExecution": False,
        "evidence_level": "research_shadow_only",
        "execution_role": "diagnostic_only",
    }
    
    # Determine action
    breakout_signals = [s for s in signals if "BREAKOUT" in s["type"] or "TWIST" in s["type"]]
    cross_signals = [s for s in signals if "CROSS" in s["type"]]
    
    if any("BULLISH" in s["type"] for s in breakout_signals):
        output["action"] = "ENTRY_LONG"
    elif any("BEARISH" in s["type"] for s in breakout_signals):
        output["action"] = "ENTRY_SHORT"
    elif any("CROSS_BULLISH" in s["type"] for s in cross_signals):
        output["action"] = "PREP_LONG"
    elif any("CROSS_BEARISH" in s["type"] for s in cross_signals):
        output["action"] = "PREP_SHORT"
    
    symbol_state_file = STATE_DIR / f"ichimoku-{symbol.lower()}-signal.latest.json"
    with open(symbol_state_file, "w") as f:
        json.dump(output, f, indent=2)

    # Generic state file is the NQ signal consumed by brain_cortex.
    if symbol.upper() == "NQ":
        with open(STATE_FILE, "w") as f:
            json.dump(output, f, indent=2)
        written_path = STATE_FILE
    else:
        written_path = symbol_state_file
    
    log(f"✅ Written to {written_path}")
    log(f"  → Tenkan: {output['ichimoku']['tenkan']} | Kijun: {output['ichimoku']['kijun']}")
    log(f"  → Cloud: {output['ichimoku']['cloud_bottom']} - {output['ichimoku']['cloud_top']}")
    log(f"  → Signals: {len(signals)} ({bullish_signals}B/{bearish_signals}S)")
    log(f"  → Trend: {trend} (strength: {strength:.2f})")
    log(f"  → Action: {output['action']}")
    
    for s in signals:
        log(f"    {s['type']} ({s['strength']}): {s['reason']}")
    
    return output

if __name__ == "__main__":
    symbol = sys.argv[1] if len(sys.argv) > 1 else "NQ"
    timeframe = sys.argv[2] if len(sys.argv) > 2 else "60m"
    run(symbol, timeframe)
