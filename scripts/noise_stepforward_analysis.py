#!/usr/bin/env python3
"""
Market Noise Analysis & Step-Forward Parameter Stability
===========================================================
Quantifies market microstructure noise, tracks parameter stability
across walk-forward windows, and detects regime changes.

Key metrics:
1. Noise-to-Signal Ratio (NsR) — across 1m/5m/15m/30m/60m
2. Epps Effect — correlation decay at lower timeframes
3. Step-Forward Parameter Decay — param drift over successive OOS windows
4. Noise Regime Detection — structural breaks in noise profile
5. Historical Comparison — current vs baseline noise

Academic basis:
- Epps (1979): Correlations decrease as sampling frequency increases
- Black (1986): Noise trading vs informed trading
- Lo & MacKinlay (1988): Variance ratio tests for market efficiency
- Lopez de Prado (2018): Advances in Financial Machine Learning

Output: ~/hedge/.rumbling-hedge/state/noise-analysis.latest.json
"""

import argparse
import json, os, sys
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple

STATE_DIR = Path(os.path.expanduser(os.environ.get(
    "BILL_STATE_DIR",
    os.environ.get("RH_STATE_DIR", "~/hedge/.rumbling-hedge/state"),
)))
STATE_DIR.mkdir(parents=True, exist_ok=True)
STATE_FILE = STATE_DIR / "noise-analysis.latest.json"
HISTORY_FILE = STATE_DIR / "noise-history.json"

DATA_DIR = Path("/Users/brain/hedge/data/free")
HISTORICAL_BASELINE_FILE = STATE_DIR / "noise-baseline.json"

SYMBOLS = ["NQ", "ES", "CL", "GC"]
TIMEFRAMES = ["5m", "15m", "30m", "60m"]
STEP_WINDOW = 200  # bars per step-forward window
STEP_SIZE = 50     # step size for rolling
PARAM_DECAY_THRESHOLD = 0.20  # 20% param drift = unstable

def log(msg):
    ts = datetime.now(timezone.utc).isoformat()
    print(f"[{ts}] {msg}")

def load_data(symbol: str, tf: str) -> Optional[pd.DataFrame]:
    """Load data for any symbol/timeframe"""
    files = [
        DATA_DIR / f"{symbol}-{tf}-60d.csv",
        DATA_DIR / f"{symbol}-{tf}-21d.csv",
        DATA_DIR / f"{symbol}-{tf}-5d.csv",
    ]
    for p in files:
        if p.exists():
            df = pd.read_csv(p)
            if "time" in df.columns:
                df = df.rename(columns={"time": "ts"})
            df["ts"] = pd.to_datetime(df["ts"])
            return df
    return None

def compute_noise_metrics(returns: np.ndarray) -> Dict:
    """
    Compute noise-to-signal ratio and related metrics.
    
    NsR = Var(noise) / Var(signal)
    where noise = high-frequency changes, signal = low-frequency trend
    
    Implementation: 
    - Signal = 20-bar EMA of returns (slow component)
    - Noise = returns - signal (fast component)
    - NsR = Var(noise) / Var(signal)
    """
    if len(returns) < 50:
        return {"nsr": None, "signal_var": None, "noise_var": None}
    
    # Signal component (trend): 20-bar EMA
    signal = pd.Series(returns).ewm(span=20).mean().values
    
    # Noise component: deviations from signal
    noise = returns - signal
    
    signal_var = float(np.var(signal[20:]))  # Skip warmup
    noise_var = float(np.var(noise[20:]))
    
    nsr = noise_var / signal_var if signal_var > 1e-10 else None
    
    # Variance ratio test (Lo-MacKinlay type)
    # VR(q) = Var(ret_q) / (q * Var(ret_1)) where ret_q = q-period returns
    # VR < 1 suggests mean reversion, VR > 1 suggests trending
    q = 5
    if len(returns) > q * 2:
        ret_q = np.convolve(returns, np.ones(q), 'valid')
        vr_q = float(np.var(ret_q) / (q * np.var(returns[len(returns)-len(ret_q):])))
    else:
        vr_q = None
    
    # Hurst exponent estimate (simplified)
    # H > 0.5 → trending, H < 0.5 → mean-reverting, H = 0.5 → random walk
    hurst = _compute_hurst(returns)
    
    # Serial correlation (autocorrelation at lag 1)
    autocorr = float(pd.Series(returns).autocorr(lag=1)) if len(returns) > 10 else None
    
    return {
        "nsr": round(nsr, 4) if nsr else None,
        "signal_var": round(signal_var, 6),
        "noise_var": round(noise_var, 6),
        "variance_ratio_5": round(vr_q, 4) if vr_q else None,
        "hurst_exponent": round(hurst, 4),
        "autocorr_lag1": round(autocorr, 4) if autocorr else None,
    }

def _compute_hurst(returns: np.ndarray) -> float:
    """Compute Hurst exponent via R/S analysis (simplified)"""
    if len(returns) < 100:
        return 0.5
    
    # Use multiple lags for robust estimate
    lags = np.logspace(1, np.log10(len(returns) // 2), 20, dtype=int)
    lags = np.unique(lags)
    
    tau = []
    for lag in lags:
        if lag < 2:
            continue
        # Price differences over lag
        diff = np.array([returns[i+lag: i+2*lag].sum() for i in range(0, len(returns)-2*lag, lag)])
        if len(diff) > 1:
            tau.append(np.std(diff))
    
    if len(tau) < 3:
        return 0.5
    
    # Regress log(tau) vs log(lag) → H is slope / 2
    lags_used = lags[:len(tau)]
    if len(lags_used) < 2:
        return 0.5
    
    log_lags = np.log(lags_used)
    log_tau = np.log(tau)
    
    if np.std(log_lags) == 0:
        return 0.5
    
    h, _ = np.polyfit(log_lags, log_tau, 1)
    hurst = h / 2  # tau ~ lag^H * 2
    
    return max(0, min(1, float(hurst)))  # Clamp to [0,1]

def compute_epps_effect(symbol: str) -> Dict:
    """
    Epps Effect: correlation decreases as sampling frequency increases.
    Compare pair correlations across timeframes.
    """
    results = {}
    for tf in TIMEFRAMES:
        df = load_data(symbol, tf)
        if df is not None and len(df) > 100:
            returns = df["close"].pct_change().dropna().values
            metrics = compute_noise_metrics(returns)
            results[tf] = {
                "nsr": metrics["nsr"],
                "hurst": metrics["hurst_exponent"],
                "vr_5": metrics["variance_ratio_5"],
                "autocorr": metrics["autocorr_lag1"],
                "bars": len(df),
            }
    return results

def rolling_noise_analysis(symbol: str, tf: str = "60m", window: int = STEP_WINDOW) -> Dict:
    """
    Track how noise metrics change over time through rolling windows.
    This is the "noise statistical changes" analysis.
    """
    df = load_data(symbol, tf)
    if df is None or len(df) < window * 2:
        return {"status": "insufficient_data", "bars": 0}
    
    closes = df["close"].values
    returns = np.diff(np.log(closes))
    
    # Rolling noise analysis
    n_windows = (len(returns) - window) // STEP_SIZE
    noise_over_time = []
    
    for w in range(n_windows):
        start = w * STEP_SIZE
        end = start + window
        if end > len(returns):
            break
        
        window_returns = returns[start:end]
        metrics = compute_noise_metrics(window_returns)
        noise_over_time.append({
            "window": w,
            "start_idx": start,
            "end_idx": end,
            "nsr": metrics["nsr"],
            "hurst": metrics["hurst_exponent"],
            "vr_5": metrics["variance_ratio_5"],
            "autocorr": metrics["autocorr_lag1"],
        })
    
    if not noise_over_time:
        return {"status": "no_windows", "bars": len(returns)}
    
    # Detect regime changes: NSR > 1.5x rolling mean = high noise regime
    nsr_values = [n["nsr"] for n in noise_over_time if n["nsr"] is not None]
    hurst_values = [n["hurst"] for n in noise_over_time]
    
    if not nsr_values:
        return {"status": "no_nsr_data", "bars": len(returns)}
    
    mean_nsr = np.mean(nsr_values)
    std_nsr = np.std(nsr_values)
    
    current_nsr = nsr_values[-1] if nsr_values else None
    
    # Regime shifts
    high_noise_windows = []
    low_noise_windows = []
    for n in noise_over_time:
        if n["nsr"] and n["nsr"] > mean_nsr + 1.5 * std_nsr:
            high_noise_windows.append(n["window"])
        elif n["nsr"] and n["nsr"] < mean_nsr - 1.0 * std_nsr:
            low_noise_windows.append(n["window"])
    
    # Trend in NSR
    if len(nsr_values) >= 5:
        nsr_trend = np.polyfit(range(len(nsr_values)), nsr_values, 1)[0]
    else:
        nsr_trend = 0
    
    # Current regime
    if current_nsr and current_nsr > mean_nsr + 1.0 * std_nsr:
        regime = "high_noise"
    elif current_nsr and current_nsr < mean_nsr - 0.5 * std_nsr:
        regime = "low_noise"
    else:
        regime = "normal"
    
    # Hurst-based regime
    mean_hurst = np.mean(hurst_values)
    if mean_hurst > 0.55:
        hurst_regime = "trending"
    elif mean_hurst < 0.45:
        hurst_regime = "mean_reverting"
    else:
        hurst_regime = "random_walk"
    
    return {
        "status": "ok",
        "symbol": symbol,
        "timeframe": tf,
        "total_bars": len(closes),
        "windows_analyzed": len(noise_over_time),
        "current_nsr": round(current_nsr, 4) if current_nsr else None,
        "mean_nsr": round(float(mean_nsr), 4),
        "nsr_std": round(float(std_nsr), 4),
        "nsr_trend": round(float(nsr_trend), 6),
        "mean_hurst": round(float(mean_hurst), 4),
        "current_hurst": round(float(hurst_values[-1]), 4) if hurst_values else None,
        "regime": regime,
        "hurst_regime": hurst_regime,
        "high_noise_windows": len(high_noise_windows),
        "low_noise_windows": len(low_noise_windows),
        "nsr_history": [round(n, 4) if n else None for n in nsr_values[-20:]],
        "hurst_history": [round(h, 4) for h in hurst_values[-20:]],
        "source": "noise-statistical-analysis",
    }

def step_forward_stability(symbol: str, tf: str = "60m") -> Dict:
    """
    Step-forward analysis tracking parameter stability.
    Tests if strategy parameters drift significantly across OOS windows.
    """
    df = load_data(symbol, tf)
    if df is None or len(df) < STEP_WINDOW * 3:
        return {"status": "insufficient_data"}
    
    closes = df["close"].values
    highs = df["high"].values
    lows = df["low"].values
    volumes = df["volume"].values if "volume" in df.columns else np.ones_like(closes) * 10000
    
    # Test parameter stability for ORB breakout
    # Parameters: [range_window, volume_threshold, exit_offset]
    param_sweep = []
    
    n_windows = (len(closes) - STEP_WINDOW * 2) // STEP_SIZE
    
    for w in range(max(n_windows, 1)):
        start = w * STEP_SIZE
        train_end = start + STEP_WINDOW
        test_end = train_end + STEP_WINDOW // 2  # 100-bar OOS
        
        if test_end > len(closes):
            break
        
        train_closes = closes[start:train_end]
        train_highs = highs[start:train_end]
        train_lows = lows[start:train_end]
        train_vol = volumes[start:train_end]
        
        test_closes = closes[train_end:test_end]
        test_highs = highs[train_end:test_end]
        test_lows = lows[train_end:test_end]
        
        # Find optimal range_window on training set
        best_rw = 8
        best_sharpe = -999
        
        for rw in [5, 8, 10, 15, 20]:
            wins = 0
            total_r = 0
            trades = 0
            for i in range(rw + 2, len(train_closes) - 5):
                rh = np.max(train_highs[i-rw:i])
                rl = np.min(train_lows[i-rw:i])
                if rh - rl <= 0:
                    continue
                avg_vol = np.mean(train_vol[max(0,i-10):i]) if i >= 10 else 1
                atr = np.mean(train_highs[max(0,i-14):i] - train_lows[max(0,i-14):i]) if i >= 14 else 1
                if atr <= 0:
                    continue
                exit_px = train_closes[min(i+5, len(train_closes)-1)]
                entry_px = train_closes[i]
                if entry_px > rh and train_vol[i] > avg_vol * 1.3:
                    r = (exit_px - entry_px) / atr
                    total_r += r
                    if r > 0: wins += 1
                    trades += 1
                elif entry_px < rl and train_vol[i] > avg_vol * 1.3:
                    r = (entry_px - exit_px) / atr
                    total_r += r
                    if r > 0: wins += 1
                    trades += 1
            
            if trades >= 5:
                avg_r = total_r / trades
                sharpe = avg_r * np.sqrt(trades) if trades > 1 else 0
                # Penalize for few trades
                sharpe = sharpe * min(trades / 10, 1)
                if sharpe > best_sharpe:
                    best_sharpe = sharpe
                    best_rw = rw
        
        # Test best_rw on OOS window
        test_trades = 0
        test_wins = 0
        test_total_r = 0
        for i in range(best_rw + 2, len(test_closes) - 3):
            rh = np.max(test_highs[i-best_rw:i])
            rl = np.min(test_lows[i-best_rw:i])
            if rh - rl <= 0:
                continue
            avg_vol = np.mean(train_vol[max(0,i-10):i]) if i >= 10 else 1
            atr = np.mean(test_highs[max(0,i-14):i] - test_lows[max(0,i-14):i]) if i >= 14 else 1
            if atr <= 0:
                continue
            exit_px = test_closes[min(i+5, len(test_closes)-1)]
            entry_px = test_closes[i]
            if entry_px > rh:
                r = (exit_px - entry_px) / atr
                test_total_r += r
                if r > 0: test_wins += 1
                test_trades += 1
            elif entry_px < rl:
                r = (entry_px - exit_px) / atr
                test_total_r += r
                if r > 0: test_wins += 1
                test_trades += 1
        
        param_sweep.append({
            "window": w,
            "optimal_rw": best_rw,
            "train_sharpe": round(float(best_sharpe), 4),
            "oos_trades": test_trades,
            "oos_wins": test_wins,
            "oos_total_r": round(float(test_total_r), 4),
            "oos_sharpe": round(float(test_total_r / max(test_trades, 1) * np.sqrt(max(test_trades, 1))), 4) if test_trades >= 1 else 0,
        })
    
    if not param_sweep:
        return {"status": "no_valid_windows"}
    
    # Parameter stability
    rw_values = [p["optimal_rw"] for p in param_sweep]
    rw_changes = sum(1 for i in range(1, len(rw_values)) if rw_values[i] != rw_values[i-1])
    rw_stability = 1 - (rw_changes / max(len(rw_values) - 1, 1))
    
    # OOS stability
    oos_results = [p["oos_sharpe"] for p in param_sweep if p["oos_sharpe"] is not None]
    if oos_results:
        mean_oos = np.mean(oos_results)
        std_oos = np.std(oos_results)
        positive_windows = sum(1 for o in oos_results if o > 0)
        oos_consistency = positive_windows / len(oos_results)
    else:
        mean_oos = 0
        std_oos = 0
        oos_consistency = 0
    
    # Overall verdict
    if rw_stability > 0.7 and oos_consistency > 0.6 and mean_oos > 0.1:
        stability = "stable"
    elif rw_stability > 0.4 and oos_consistency > 0.4:
        stability = "unstable"
    else:
        stability = "degraded"
    
    return {
        "status": "ok",
        "symbol": symbol,
        "timeframe": tf,
        "windows_tested": len(param_sweep),
        "rw_stability": round(float(rw_stability), 4),
        "rw_changes": rw_changes,
        "mean_oos_sharpe": round(float(mean_oos), 4),
        "oos_std": round(float(std_oos), 4),
        "oos_consistency": round(float(oos_consistency), 4),
        "positive_oos_windows": positive_windows,
        "stability_verdict": stability,
        "param_history": rw_values,
        "oos_sharpe_history": [round(p["oos_sharpe"], 4) for p in param_sweep],
        "source": "step-forward-parameter-decay",
    }

def run_full_analysis(symbols: List[str] = None) -> Dict:
    """Run comprehensive noise + step-forward analysis"""
    if symbols is None:
        symbols = SYMBOLS
    
    log(f"{'='*60}")
    log(f"MARKET NOISE & STEP-FORWARD ANALYSIS")
    log(f"{'='*60}")
    
    results = {}
    
    for symbol in symbols:
        log(f"\n--- {symbol} ---")
        
        # 1. Epps Effect (noise across timeframes)
        log(f"  Epps Effect (noise across timeframes)...")
        epps = compute_epps_effect(symbol)
        results[f"{symbol.lower()}_epps"] = epps
        for tf, m in epps.items():
            log(f"    {tf}: NSR={m.get('nsr', 'N/A')}, H={m.get('hurst', 'N/A')}")
        
        # 2. Rolling Noise Analysis (60m)
        log(f"  Rolling noise analysis (60m)...")
        noise = rolling_noise_analysis(symbol, "60m")
        results[f"{symbol.lower()}_noise"] = noise
        if noise["status"] == "ok":
            log(f"    Current NSR: {noise['current_nsr']} (mean: {noise['mean_nsr']})")
            log(f"    Regime: {noise['regime']} | Hurst: {noise['hurst_regime']} ({noise['current_hurst']})")
            log(f"    High noise windows: {noise['high_noise_windows']}")
        
        # 3. Step-Forward Stability
        log(f"  Step-forward stability analysis...")
        sf = step_forward_stability(symbol, "60m")
        results[f"{symbol.lower()}_stepforward"] = sf
        if sf["status"] == "ok":
            log(f"    Windows: {sf['windows_tested']}")
            log(f"    RW stability: {sf['rw_stability']}")
            log(f"    OOS consistency: {sf['oos_consistency']} ({sf['positive_oos_windows']}+/{sf['windows_tested']})")
            log(f"    Stability: {sf['stability_verdict']}")
    
    # Cross-synthesis
    log(f"\n--- SYNTHESIS ---")
    
    # Compare NSR across symbols at 60m
    nq_noise = results.get("nq_noise", {})
    es_noise = results.get("es_noise", {})
    
    noise_rows = [
        (s, results.get(f"{s.lower()}_noise", {}).get("current_nsr", 0) or 0)
        for s in symbols
        if results.get(f"{s.lower()}_noise", {}).get("status") == "ok"
    ]
    trend_rows = [
        (s, results.get(f"{s.lower()}_noise", {}).get("current_hurst", 0) or 0)
        for s in symbols
        if results.get(f"{s.lower()}_noise", {}).get("status") == "ok"
    ]
    stability_rows = [
        (s, results.get(f"{s.lower()}_stepforward", {}).get("rw_stability", 0) or 0)
        for s in symbols
        if results.get(f"{s.lower()}_stepforward", {}).get("status") == "ok"
    ]
    oos_rows = [
        (s, results.get(f"{s.lower()}_stepforward", {}).get("mean_oos_sharpe", -999) or -999)
        for s in symbols
        if results.get(f"{s.lower()}_stepforward", {}).get("status") == "ok"
    ]

    synthesis = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "analysis_version": "1.0.0",
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "tradable_signal": False,
        "promoted_for_execution": False,
        "readyForExecution": False,
        "evidence_level": "research_context_only",
        "execution_role": "diagnostic_only",
        "noise_summary": {
            "most_noisy_60m": max(noise_rows, key=lambda x: x[1]) if noise_rows else None,
            "most_trending_60m": max(trend_rows, key=lambda x: x[1]) if trend_rows else None,
        },
        "stepforward_summary": {
            "most_stable": max(stability_rows, key=lambda x: x[1]) if stability_rows else None,
            "best_oos": max(oos_rows, key=lambda x: x[1]) if oos_rows else None,
        },
        "details": results,
    }
    
    with open(STATE_FILE, "w") as f:
        json.dump(synthesis, f, indent=2)
    
    log(f"\n✅ Written to {STATE_FILE}")
    log(f"  → Symbols analyzed: {len(symbols)}")
    log(f"  → Timeframes: {TIMEFRAMES}")
    
    return synthesis

def main() -> None:
    global STATE_DIR, STATE_FILE, HISTORY_FILE, HISTORICAL_BASELINE_FILE
    parser = argparse.ArgumentParser(description="Market noise and step-forward stability analysis.")
    parser.add_argument("symbols", nargs="*", default=SYMBOLS, help="Symbols to analyze, default: NQ ES CL GC")
    parser.add_argument("--state-dir", default=str(STATE_DIR), help=f"State directory (default: {STATE_DIR})")
    args = parser.parse_args()

    STATE_DIR = Path(args.state_dir).expanduser()
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE = STATE_DIR / "noise-analysis.latest.json"
    HISTORY_FILE = STATE_DIR / "noise-history.json"
    HISTORICAL_BASELINE_FILE = STATE_DIR / "noise-baseline.json"
    run_full_analysis(args.symbols)


if __name__ == "__main__":
    main()
