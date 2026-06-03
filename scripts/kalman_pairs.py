#!/usr/bin/env python3
"""
Kalman Filter NQ/ES Pairs Trader — Dynamic Hedge Ratio + Z-Score Entry

NQ (Nasdaq) and ES (S&P 500) are 95%+ correlated. When they diverge
temporarily, it represents a statistical arbitrage opportunity.

This module:
1. Estimates the time-varying hedge ratio using a Kalman filter
2. Computes spread z-scores for entry/exit signals
3. Generates long-NQ/short-ES (or reverse) pair trade signals

The Kalman filter adapts to changing correlations — essential given
Nasdaq vs S&P500 relative strength regimes (tech rallies vs value).

Output: ~/hedge/.rumbling-hedge/state/kalman-pairs-signal.latest.json
"""

import json, os, sys
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime, timezone
from typing import Tuple, Optional

# ── Config ──────────────────────────────────────────────────────────────
STATE_DIR = Path(os.environ.get("BILL_STATE_DIR", os.path.expanduser("~/hedge/.rumbling-hedge/state")))
STATE_FILE = STATE_DIR / "kalman-pairs-signal.latest.json"
TOPSTEP_BAR_DIR = Path("/Users/brain/hedge/.rumbling-hedge/research/topstep-readonly-bars")
STATE_DIR.mkdir(parents=True, exist_ok=True)

# Kalman filter parameters
DELTA = 0.0001  # Process noise (how fast hedge ratio changes)
V = 0.001       # Measurement noise (observation uncertainty)
Z_ENTRY = 2.0   # Z-score threshold for entry
Z_EXIT = 0.5    # Z-score threshold for exit
Z_STOP = 3.5    # Stop-loss z-score
STALE_BAR_SECONDS = 2 * 60 * 60

# Lookback for spread normalization
SPREAD_LOOKBACK = 100


class KalmanFilter:
    """Simple 1D Kalman filter for dynamic hedge ratio estimation.
    
    State: β (hedge ratio) — random walk
    Observation: NQ_t = α + β_t * ES_t + ε_t
    """
    
    def __init__(self, delta=DELTA, v=V):
        self.delta = delta
        self.v = v
        self.beta = 0.0      # Initial hedge ratio estimate
        self.P = 1.0         # Initial covariance
        self.R = v           # Measurement noise covariance
        self.Q = delta       # Process noise covariance
        self.history = []    # Track beta over time
    
    def update(self, nq_price: float, es_price: float) -> Tuple[float, float]:
        """Update the filter with new NQ and ES prices.
        Returns: (hedge_ratio, residual)
        """
        # Predict
        beta_pred = self.beta
        P_pred = self.P + self.Q
        
        # Observation: NQ_price = beta * ES_price + residual
        # Kalman gain
        K = P_pred * es_price / (es_price * P_pred * es_price + self.R)
        
        # Innovation (prediction error)
        residual = nq_price - beta_pred * es_price
        
        # Update
        self.beta = beta_pred + K * residual
        self.P = (1 - K * es_price) * P_pred
        
        self.history.append(self.beta)
        return self.beta, residual


def _load_topstep_symbol(symbol: str) -> Optional[pd.Series]:
    path = TOPSTEP_BAR_DIR / f"{symbol}-1m-topstep-readonly.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path)
    if "symbol" in df.columns:
        df = df[df["symbol"] == symbol].copy()
    if len(df) < 30:
        return None
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df = df.sort_values("ts")
    return df.set_index("ts")["close"]


def load_topstep_pair_data() -> Optional[Tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """Load current read-only broker-grade NQ/ES bars when both legs exist."""
    nq = _load_topstep_symbol("NQ")
    es = _load_topstep_symbol("ES")
    if nq is None or es is None:
        return None

    common_idx = nq.index.intersection(es.index)
    if len(common_idx) < 30:
        return None

    nq_aligned = nq.loc[common_idx].values
    es_aligned = es.loc[common_idx].values
    ts_array = np.array([pd.Timestamp(t).timestamp() for t in common_idx])
    print(f"Loaded {len(nq_aligned)} aligned Topstep read-only NQ/ES bars")
    return nq_aligned, es_aligned, ts_array


def load_pair_data() -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Load NQ and ES prices, preferring current read-only broker-grade bars."""
    topstep_pair = load_topstep_pair_data()
    if topstep_pair is not None:
        return topstep_pair

    if os.environ.get("BILL_ALLOW_STALE_KALMAN_FREE_FALLBACK") != "true":
        raise ValueError(
            "missing current read-only Topstep NQ/ES pair archive; "
            "set BILL_ALLOW_STALE_KALMAN_FREE_FALLBACK=true for offline research only"
        )

    # Offline research fallback only. Active crons should not emit stale free-CSV
    # pair signals because they look current to downstream readers.
    data_dir = Path("/Users/brain/hedge/data/free")
    
    # Try 60m data first (best edge)
    for pattern in ["*60m*60d*", "*60m*", "*15m*60d*", "*15m*"]:
        candidates = list(data_dir.glob(pattern))
        for c in sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True):
            if "ALL" not in c.name and "NQ" not in c.name and "2MARKETS" not in c.name:
                continue
            try:
                df = pd.read_csv(c)
                if "symbol" not in df.columns:
                    continue
                nq = df[df["symbol"] == "NQ"].copy()
                es = df[df["symbol"] == "ES"].copy()
                
                if len(nq) < 30 or len(es) < 30:
                    continue
                
                # Align on timestamps
                nq = nq.set_index("ts")["close"]
                es = es.set_index("ts")["close"]
                
                # Find common timestamps
                common_idx = nq.index.intersection(es.index)
                nq_aligned = nq.loc[common_idx].values
                es_aligned = es.loc[common_idx].values
                
                if len(nq_aligned) >= 30:
                    print(f"Loaded {len(nq_aligned)} aligned bars from {c.name}")
                    try:
                        ts_array = np.array([pd.Timestamp(t).timestamp() for t in common_idx])
                    except:
                        ts_array = np.arange(len(nq_aligned))
                    return nq_aligned, es_aligned, ts_array
            except Exception as e:
                continue
    
    raise ValueError("Could not find aligned NQ/ES data")


def compute_spread(nq: np.ndarray, es: np.ndarray, betas: np.ndarray) -> np.ndarray:
    """Compute the spread = NQ - β * ES (i.e., the residual)."""
    return nq - betas * es


def compute_zscore(spread: np.ndarray) -> np.ndarray:
    """Compute rolling z-score of the spread."""
    if len(spread) < SPREAD_LOOKBACK:
        lookback = len(spread) // 2
    else:
        lookback = SPREAD_LOOKBACK
    
    mean = np.mean(spread[-lookback:])
    std = np.std(spread[-lookback:])
    
    if std < 1e-10:
        return np.zeros_like(spread)
    
    return (spread - mean) / std


def main():
    print("🔗 Kalman Filter NQ/ES Pairs Trader")
    print("=" * 45)
    
    # 1. Load data
    try:
        nq_prices, es_prices, timestamps = load_pair_data()
    except ValueError as e:
        print(f"❌ {e}")
        empty = {
            "action": "NO_EVIDENCE",
            "direction": "neutral",
            "confidence": 0.0,
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "method": "kalman_dynamic_hedge",
            "evidence_level": "research_shadow_only",
            "researchOnly": True,
            "writesOrders": False,
            "touchesBroker": False,
            "tradable_signal": False,
            "promoted_for_execution": False,
            "readyForExecution": False,
            "execution_role": "diagnostic_only",
            "source_data_stale": True,
            "stale_threshold_seconds": STALE_BAR_SECONDS,
            "operator_read": (
                "Research-only pair-spread diagnostic. Missing current broker-grade pair "
                "data is neutral/no-evidence, not trade confirmation."
            ),
            "limitations": [
                "Missing current aligned NQ/ES data means no pair-trade evidence is available",
                "Neutral fallback must not be interpreted as confirmation",
            ],
        }
        with open(STATE_FILE, "w") as f:
            json.dump(empty, f, indent=2)
        return
    
    # 2. Run Kalman filter over all data
    kf = KalmanFilter()
    residuals = []
    betas = []
    
    for i in range(len(nq_prices)):
        beta, residual = kf.update(nq_prices[i], es_prices[i])
        residuals.append(residual)
        betas.append(beta)
    
    residuals = np.array(residuals)
    betas = np.array(betas)
    
    # 3. Compute spread z-score
    z_scores = compute_zscore(residuals)
    
    # 4. Generate signals
    current_z = z_scores[-1]
    prev_z = z_scores[-2] if len(z_scores) > 1 else 0
    
    # Entry logic
    if current_z > Z_ENTRY and prev_z <= Z_ENTRY:
        direction = "short_nq_long_es"  # NQ overpriced relative to ES
        action = "ENTER"
        confidence = min((current_z - Z_ENTRY) / 1.0, 1.0)
    elif current_z < -Z_ENTRY and prev_z >= -Z_ENTRY:
        direction = "long_nq_short_es"   # NQ underpriced relative to ES
        action = "ENTER"
        confidence = min((abs(current_z) - Z_ENTRY) / 1.0, 1.0)
    elif abs(current_z) < Z_EXIT:
        action = "EXIT"
        direction = "neutral"
        confidence = 0.0
    elif abs(current_z) > Z_STOP:
        action = "STOP_LOSS"
        direction = "neutral"
        confidence = 1.0
    else:
        action = "HOLD"
        # Direction based on position if we're in one
        if current_z > 0:
            direction = "short_nq_long_es"
        else:
            direction = "long_nq_short_es"
        confidence = 0.0
    
    # STOP_LOSS check overrides
    if abs(current_z) > Z_STOP:
        action = "STOP_LOSS"
        direction = "neutral"
        confidence = 1.0
    
    # Current beta interpretation
    beta_current = betas[-1]
    beta_recent_mean = np.mean(betas[-20:]) if len(betas) >= 20 else beta_current
    beta_trend = (beta_current / beta_recent_mean - 1) * 100  # % change in hedge ratio
    last_bar_time = None
    source_data_age_seconds = None
    source_data_stale = True
    if len(timestamps) and float(timestamps[-1]) > 1_000_000_000:
        last_dt = datetime.fromtimestamp(float(timestamps[-1]), tz=timezone.utc)
        last_bar_time = last_dt.isoformat()
        source_data_age_seconds = max(0, int((datetime.now(timezone.utc) - last_dt).total_seconds()))
        source_data_stale = source_data_age_seconds > STALE_BAR_SECONDS
    
    # Summary stats
    stats = {
        "nq_price": round(nq_prices[-1], 2),
        "es_price": round(es_prices[-1], 2),
        "hedge_ratio": round(beta_current, 4),
        "beta_trend_pct": round(beta_trend, 2),
        "residual": round(residuals[-1], 2),
        "z_score": round(current_z, 2),
        "nq_points_per_es": round(beta_current, 2),
        "lookback_bars": min(SPREAD_LOOKBACK, len(residuals)),
    }
    
    print(f"\nNQ={stats['nq_price']} | ES={stats['es_price']}")
    print(f"Hedge Ratio β: {stats['hedge_ratio']:.4f} (trend: {stats['beta_trend_pct']:+.2f}%)")
    print(f"Spread z-score: {stats['z_score']:.2f}")
    print(f"Action: {action} | Direction: {direction}")
    
    # Historical beta chart (last 30)
    print(f"\nRecent β values: ", end="")
    for b in betas[-30:]:
        print(f"{b:.2f} ", end="")
    print()
    
    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "direction": direction,
        "confidence": round(confidence, 4),
        "stats": stats,
        "entry_signal": {
            "threshold_entry": Z_ENTRY,
            "threshold_exit": Z_EXIT,
            "threshold_stop": Z_STOP,
        },
        "beta_history": [round(b, 4) for b in betas[-50:]],
        "z_history": [round(z, 2) for z in z_scores[-50:]],
        "total_bars": len(nq_prices),
        "method": "kalman_dynamic_hedge",
        "evidence_level": "research_shadow_only",
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "tradable_signal": False,
        "promoted_for_execution": False,
        "readyForExecution": False,
        "execution_role": "diagnostic_only",
        "operator_read": (
            "Research-only NQ/ES pair-spread diagnostic. It does not authorize "
            "single-leg futures orders or Topstep demo routing."
        ),
        "last_bar_time": last_bar_time,
        "source_data_age_seconds": source_data_age_seconds,
        "source_data_stale": source_data_stale,
        "stale_threshold_seconds": STALE_BAR_SECONDS,
        "limitations": [
            "Requires pair execution and spread/slippage modeling before trading",
            "Must not confirm or size single-leg Topstep demo orders without promotion evidence"
        ],
    }
    
    with open(STATE_FILE, "w") as f:
        json.dump(output, f, indent=2)
    
    print(f"\n✅ Written to {STATE_FILE}")
    print(f"  → Operator read: {output['operator_read']}")
    if last_bar_time:
        print(f"  → Last source bar: {last_bar_time} (age={source_data_age_seconds}s)")
    if output["source_data_stale"]:
        print("  → STALE OR UNVERIFIED SOURCE DATA: diagnostic only; not pair-trade evidence.")
    print("  → NOT A TRADE SIGNAL: writesOrders=false, promoted_for_execution=false")
    print(f"  → Strategy: {action}")
    print(f"  → Trade: {'Waiting for z-score divergence' if action == 'HOLD' else direction}")
    print(f"  → Beta trend: {'NQ getting relatively stronger' if beta_trend > 0 else 'NQ getting relatively weaker'}")
    
    # Analyze recent performance
    if len(z_scores) >= 100:
        recent_z = z_scores[-100:]
        crossovers = np.sum(np.abs(np.diff(np.sign(recent_z))) > 0) // 2  # zero-crossings
        print(f"\n  100-bar stats: {crossovers} zero-crossings, "
              f"max z={np.max(np.abs(recent_z)):.2f}")


if __name__ == "__main__":
    main()
