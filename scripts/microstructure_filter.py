#!/usr/bin/env python3
"""
microstructure_filter.py
------------------------
1m NQ (Nasdaq-100 futures proxy via QQQ) bars from Yahoo Finance.

Computes:
  - tick_frequency: proxy via unique close-price changes per bar
    (fraction of rolling 20-bar window where close differs from prior close)
  - volume_regime: current bar volume vs 20-bar rolling mean volume
    (LOW / NORMAL / HIGH)

Classifies spread regime as TIGHT / NORMAL / WIDE from the two signals.

Output (JSON):
{
  "timestamp": <str ISO-8601>,
  "direction": 0,
  "confidence": <float 0..1>,
  "signal_name": "microstructure_filter",
  "details": {
    "filter_verdict": "TIGHT" | "NORMAL" | "WIDE",
    "confidence_modifier": <float -1..+1>,
    "tick_frequency": <float 0..1>,
    "volume_regime": "LOW" | "NORMAL" | "HIGH"
  },
  "error": null
}

Requires: yfinance, pandas (Python >= 3.9)
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEFAULT_TICKER = "QQQ"          # Nasdaq-100 ETF (liquid proxy for NQ futures)
WINDOW = 20                     # rolling lookback for tick frequency & volume mean
VOLUME_HIGH_MULT = 1.5          # volume > 1.5x mean  -> HIGH
VOLUME_LOW_MULT  = 0.5          # volume < 0.5x mean  -> LOW
DEFAULT_STATE_DIR = Path.home() / ".rumbling-hedge" / "state"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def fetch_1m_bars(ticker: str, lookback_minutes: int = 120) -> pd.DataFrame:
    """Download 1-minute OHLCV bars.  Returns a DataFrame with DatetimeIndex."""
    # yfinance 1m data is only available for ~7 days; use 'period' param
    period_days = max(5, (lookback_minutes // 390) + 2)  # ~390 trading mins/day
    period_str = f"{period_days}d"

    df = yf.download(
        ticker,
        interval="1m",
        period=period_str,
        progress=False,
        auto_adjust=True,
    )

    if df.empty:
        raise RuntimeError(f"No 1m data returned for {ticker}")

    # Flatten MultiIndex columns if present (e.g. ('Close', 'QQQ') -> 'Close')
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    # Ensure we have the columns we need
    required = {"Open", "High", "Low", "Close", "Volume"}
    missing = required - set(df.columns)
    if missing:
        raise RuntimeError(f"Missing columns: {missing}")

    # Keep only the last lookback_minutes bars (plus window for warmup)
    df = df.iloc[-(lookback_minutes + WINDOW):]
    return df


def compute_tick_frequency(df: pd.DataFrame) -> pd.Series:
    """
    Tick frequency proxy: fraction of bars in the rolling WINDOW where
    close differs from the previous bar's close.

    Returns a Series in [0, 1]; higher = more price-change events = tighter.
    """
    close = df["Close"]
    changed = close.diff().fillna(0.0).abs() > 1e-9   # True if price moved
    tick_freq = changed.rolling(WINDOW, min_periods=1).mean()
    return tick_freq


def compute_volume_regime(df: pd.DataFrame) -> pd.Series:
    """
    Classify each bar's volume relative to its 20-bar rolling mean.

    Returns a Series of strings: 'LOW', 'NORMAL', 'HIGH'.
    """
    vol = df["Volume"]
    vol_mean = vol.rolling(WINDOW, min_periods=5).mean()
    ratio = vol / vol_mean.replace(0, float("nan"))

    regime = pd.Series("NORMAL", index=df.index, dtype=str)
    regime[ratio > VOLUME_HIGH_MULT] = "HIGH"
    regime[ratio < VOLUME_LOW_MULT]   = "LOW"
    return regime


def classify_spread(tick_freq: float, vol_regime: str) -> str:
    """
    Combine tick frequency and volume regime into a spread classification.

    Heuristic:
      - TIGHT:  high tick frequency (>= 0.65), volume normal or above
      - WIDE:   low tick frequency (< 0.40)  OR  volume is LOW
      - NORMAL: everything else
    """
    if tick_freq >= 0.65 and vol_regime in ("NORMAL", "HIGH"):
        return "TIGHT"
    if tick_freq < 0.40 or vol_regime == "LOW":
        return "WIDE"
    return "NORMAL"


def confidence_modifier(tick_freq: float, vol_regime: str) -> float:
    """
    Map the microstructure signals to a confidence modifier in [-1, +1].

    Positive = favourable for execution (tight / liquid conditions).
    Negative = unfavourable (wide / illiquid conditions).
    """
    # Base from tick frequency: map [0, 1] -> [-0.6, +0.6]
    base = (tick_freq - 0.5) * 1.2

    # Volume bonus / penalty
    if vol_regime == "HIGH":
        vol_adj = +0.3
    elif vol_regime == "LOW":
        vol_adj = -0.3
    else:
        vol_adj = 0.0

    return max(-1.0, min(1.0, base + vol_adj))


def latest_signal(df: pd.DataFrame) -> dict:
    """Compute the signal for the most recent bar and return the output dict."""
    tick_freq_series = compute_tick_frequency(df)
    vol_regime_series = compute_volume_regime(df)

    idx = df.index[-1]
    tick_freq = float(tick_freq_series.iloc[-1])
    vol_regime = str(vol_regime_series.iloc[-1])
    verdict = classify_spread(tick_freq, vol_regime)
    conf_mod = round(confidence_modifier(tick_freq, vol_regime), 4)

    # Overall confidence: map modifier from [-1,1] -> [0,1]
    confidence = round((conf_mod + 1.0) / 2.0, 4)

    return with_advisory_contract({
        "timestamp": pd.Timestamp(idx).isoformat(),
        "direction": 0,
        "confidence": confidence,
        "signal_name": "microstructure_filter",
        "details": {
            "filter_verdict": verdict,
            "confidence_modifier": conf_mod,
            "tick_frequency": round(tick_freq, 4),
            "volume_regime": vol_regime,
        },
        "error": None,
    })


def with_advisory_contract(signal: dict) -> dict:
    """Mark this microstructure proxy as advisory context only."""
    signal.update({
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "tradable_signal": False,
        "promoted_for_execution": False,
        "readyForExecution": False,
        "execution_role": "diagnostic_only",
        "limitations": [
            "Yahoo 1m bar microstructure is a proxy input, not execution-grade order flow",
            "May not approve sizing, demo, live, funding, broker, or route decisions",
        ],
    })
    return signal


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Microstructure filter — 1m NQ proxy spread regime signal"
    )
    parser.add_argument(
        "--ticker", default=DEFAULT_TICKER,
        help=f"Yahoo ticker (default: {DEFAULT_TICKER})"
    )
    parser.add_argument(
        "--lookback", type=int, default=120,
        help="Minutes of 1m bars to fetch (default: 120)"
    )
    parser.add_argument(
        "--pretty", action="store_true",
        help="Pretty-print JSON output"
    )
    parser.add_argument(
        "--raw", action="store_true",
        help="Emit raw latest-bar values (tick_freq, vol_regime, verdict) only"
    )
    parser.add_argument(
        "--state-dir",
        default=str(DEFAULT_STATE_DIR),
        help=f"Directory for microstructure-filter.latest.json (default: {DEFAULT_STATE_DIR})",
    )
    args = parser.parse_args()

    try:
        df = fetch_1m_bars(args.ticker, args.lookback)
        signal = latest_signal(df)
    except Exception as exc:
        signal = with_advisory_contract({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "direction": 0,
            "confidence": 0.0,
            "signal_name": "microstructure_filter",
            "details": {
                "filter_verdict": "NORMAL",
                "confidence_modifier": 0.0,
                "tick_frequency": 0.0,
                "volume_regime": "NORMAL",
            },
            "error": str(exc),
        })

    indent = 2 if args.pretty else None
    if args.raw and signal["error"] is None:
        d = signal["details"]
        print(f"tick_frequency={d['tick_frequency']:.4f} "
              f"volume_regime={d['volume_regime']} "
              f"verdict={d['filter_verdict']} "
              f"conf_mod={d['confidence_modifier']:.4f}")
    else:
        print(json.dumps(signal, indent=indent, default=str))
    state_dir = Path(args.state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "microstructure-filter.latest.json").write_text(json.dumps(signal, indent=2, default=str) + "\n")


if __name__ == "__main__":
    main()
