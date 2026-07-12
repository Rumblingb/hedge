#!/usr/bin/env python3
"""
Vol Regime Gate — Volatility Regime Detector for NQ Futures
============================================================

Fetches 5-minute NQ data from Yahoo Finance, computes ATR(14) on the 5m bars,
compares current ATR to a 20-period rolling median ATR, and outputs a
volatility regime with a confidence multiplier.

Usage:
    python3 vol_regime_gate.py [--state-dir PATH]

Output: Standard signal JSON printed to stdout and written to state dir.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


import numpy as np
import yfinance as yf

# ── Config ──────────────────────────────────────────────────────────────
SYMBOL = "NQ=F"
INTERVAL = "5m"
PERIOD = "5d"  # Yahoo limit for 5m bars
ATR_PERIOD = 14
MEDIAN_PERIOD = 20

DEFAULT_STATE_DIR = Path(os.environ.get("BILL_STATE_DIR", os.path.expanduser("~/hedge/.rumbling-hedge/state")))


# ── Core Logic ───────────────────────────────────────────────────────────

def compute_atr(high: np.ndarray, low: np.ndarray, close: np.ndarray,
                period: int = 14) -> np.ndarray:
    """
    Compute Average True Range (ATR) using Wilder's smoothing method.
    Returns an array of same length, with NaN for indices < period.
    """
    n = len(high)
    if n < 2:
        return np.full(n, np.nan)

    prev_close = np.roll(close, 1)
    prev_close[0] = close[0]  # first bar uses its own close

    tr = np.maximum(
        high - low,
        np.maximum(
            np.abs(high - prev_close),
            np.abs(low - prev_close)
        )
    )

    atr = np.full(n, np.nan)
    # First TR is simple average
    if n >= period:
        atr[period - 1] = np.mean(tr[:period])
        # Wilder's smoothing for the rest
        for i in range(period, n):
            atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period

    return atr


def rolling_median(values: np.ndarray, window: int) -> np.ndarray:
    """
    Compute rolling median over `window` periods.
    Returns array of same length, with NaN where window is incomplete.
    """
    n = len(values)
    result = np.full(n, np.nan)
    for i in range(window - 1, n):
        result[i] = np.median(values[i - window + 1 : i + 1])
    return result


def classify_regime(ratio: float) -> str:
    """
    Classify volatility regime based on current ATR vs median ATR ratio.

    - ratio > 1.5  → HIGH (explosive)
    - ratio > 1.2  → ELEVATED
    - ratio > 0.8  → NORMAL
    - ratio > 0.6  → LOW
    - ratio <= 0.6 → SUPPRESSED
    """
    if ratio > 1.5:
        return "HIGH"
    elif ratio > 1.2:
        return "ELEVATED"
    elif ratio > 0.8:
        return "NORMAL"
    elif ratio > 0.6:
        return "LOW"
    else:
        return "SUPPRESSED"


def confidence_from_regime(regime: str, ratio: float) -> float:
    """
    Derive a confidence multiplier from the regime and ratio.

    HIGH/SUPPRESSED regimes reduce confidence (markets are unstable or dead),
    NORMAL gives full confidence, ELEVATED/LOW are intermediate.
    """
    base = {
        "HIGH": 0.6,
        "ELEVATED": 0.8,
        "NORMAL": 1.0,
        "LOW": 0.75,
        "SUPPRESSED": 0.5,
    }[regime]

    # Adjust for how far from NORMAL we are
    deviation = abs(ratio - 1.0)
    penalty = min(deviation * 0.3, 0.3)  # cap penalty at 0.3
    multiplier = max(base - penalty, 0.1)

    return round(multiplier, 4)


# ── Main ─────────────────────────────────────────────────────────────────

def generate_signal(state_dir: Path) -> dict:
    """
    Fetch NQ data, compute ATR/regime, and return a standard signal dict.
    """
    # Fetch data
    ticker = yf.Ticker(SYMBOL)
    df = ticker.history(period=PERIOD, interval=INTERVAL)

    if df.empty:
        return with_advisory_contract({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "direction": 0,
            "confidence": 0.0,
            "signal_name": "vol_regime_gate",
            "details": {
                "regime": "UNKNOWN",
                "current_atr": None,
                "median_atr": None,
                "confidence_multiplier": 0.0,
            },
            "error": f"No data returned for {SYMBOL}",
        })

    high = df["High"].values
    low = df["Low"].values
    close = df["Close"].values

    # Compute ATR
    atr = compute_atr(high, low, close, ATR_PERIOD)
    current_atr = atr[-1]

    if np.isnan(current_atr) or len(atr) < ATR_PERIOD + MEDIAN_PERIOD:
        return with_advisory_contract({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "direction": 0,
            "confidence": 0.0,
            "signal_name": "vol_regime_gate",
            "details": {
                "regime": "INSUFFICIENT_DATA",
                "current_atr": None if np.isnan(current_atr) else float(current_atr),
                "median_atr": None,
                "confidence_multiplier": 0.0,
            },
            "error": "Insufficient bars to compute ATR and median",
        })

    # Compute rolling median of ATR (exclude current bar for look-back)
    median_atr_vals = rolling_median(atr, MEDIAN_PERIOD)
    median_atr = median_atr_vals[-1]

    if np.isnan(median_atr):
        median_atr = current_atr  # fallback: assume normal regime

    # Compute ratio and regime
    ratio = current_atr / median_atr if median_atr > 0 else 1.0
    regime = classify_regime(ratio)
    confidence_multiplier = confidence_from_regime(regime, ratio)

    return with_advisory_contract({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "direction": 0,
        "confidence": float(confidence_multiplier),
        "signal_name": "vol_regime_gate",
        "details": {
            "regime": regime,
            "current_atr": round(float(current_atr), 6),
            "median_atr": round(float(median_atr), 6),
            "confidence_multiplier": confidence_multiplier,
        },
        "error": None,
    })


def with_advisory_contract(signal: dict) -> dict:
    """Mark this signal as advisory context, never route approval."""
    signal.update({
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "tradable_signal": False,
        "promoted_for_execution": False,
        "readyForExecution": False,
        "execution_role": "diagnostic_only",
        "limitations": [
            "Volatility regime is an advisory confidence input, not an order or route approval",
            "Must be combined with OOS evidence, execution-grade data, and daily route approval before use",
        ],
    })
    return signal


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Vol Regime Gate — NQ volatility regime detector"
    )
    parser.add_argument(
        "--state-dir",
        type=str,
        default=None,
        help="Path to state directory (default: ~/.rumbling-hedge/state)",
    )
    args = parser.parse_args()

    state_dir = Path(args.state_dir) if args.state_dir else DEFAULT_STATE_DIR
    state_dir.mkdir(parents=True, exist_ok=True)

    signal = generate_signal(state_dir)

    # Print to stdout
    print(json.dumps(signal, indent=2))

    # Write to state file
    output_file = state_dir / "vol-regime-gate.latest.json"
    with open(output_file, "w") as f:
        json.dump(signal, f, indent=2)
    print(f"\nWritten to {output_file}", file=sys.stderr)


if __name__ == "__main__":
    main()
