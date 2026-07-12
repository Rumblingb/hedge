#!/usr/bin/env python3
"""
multitf_confirmation.py — Multi-timeframe confirmation signal for NQ futures.

Fetches 1m and 5m bars from Yahoo Finance, computes:
- 5m trend: EMA(8) vs EMA(21) on close (uptrend/downtrend/flat within 0.1%)
- 1m slope: linear regression of last 5 closes via numpy polyfit

Output: JSON signal with direction (-1/0/1), confidence (0-1), and details.
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np
import yfinance as yf


DEFAULT_STATE_DIR = Path(os.environ.get("BILL_STATE_DIR", str(Path.home() / "hedge" / ".rumbling-hedge" / "state")))


def compute_ema(data: np.ndarray, span: int) -> np.ndarray:
    """Compute exponential moving average over a 1-D array."""
    if len(data) < span:
        return data
    alpha = 2.0 / (span + 1)
    ema = np.empty_like(data)
    ema[0] = data[0]
    for i in range(1, len(data)):
        ema[i] = alpha * data[i] + (1 - alpha) * ema[i - 1]
    return ema


def determine_5m_trend(closes: np.ndarray) -> Tuple[str, float]:
    """
    Determine 5-minute trend from EMA(8) vs EMA(21).

    Returns (trend_label, diff_pct) where:
      - trend_label: 'uptrend', 'downtrend', or 'flat'
      - diff_pct:    (EMA8 - EMA21) / EMA21
    """
    if len(closes) < 21:
        return ("flat", 0.0)

    ema8 = compute_ema(closes, 8)
    ema21 = compute_ema(closes, 21)
    diff_pct = float((ema8[-1] - ema21[-1]) / ema21[-1])

    if diff_pct > 0.001:
        return ("uptrend", diff_pct)
    elif diff_pct < -0.001:
        return ("downtrend", diff_pct)
    return ("flat", diff_pct)


def compute_1m_slope(closes: np.ndarray) -> float:
    """
    Linear regression slope of the last 5 closes via numpy polyfit.
    Returns raw slope (price change per bar).
    """
    if len(closes) < 5:
        return 0.0
    recent = closes[-5:]
    x = np.arange(len(recent), dtype=float)
    slope, _ = np.polyfit(x, recent, 1)
    return float(slope)


def fetch_bars(ticker: str, interval: str, period: str) -> Optional[np.ndarray]:
    """
    Fetch OHLCV bars from Yahoo Finance.
    Returns close-prices as a numpy array, or None on failure.
    """
    try:
        df = yf.download(
            ticker,
            interval=interval,
            period=period,
            progress=False,
            auto_adjust=True,
        )
        if df is None or df.empty:
            return None
        # yfinance with auto_adjust=True returns a MultiIndex column frame;
        # df["Close"] is a single-column DataFrame → to_numpy gives (N,1).
        return df["Close"].to_numpy().ravel()
    except Exception:
        return None


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def compute_signal(
    ticker: str = "NQ=F",
    period_5m: str = "5d",
    period_1m: str = "1d",
) -> Dict[str, Any]:
    """
    Compute the multi-timeframe confirmation signal.

    Returns a dict structured as:
        {
            "timestamp":      "<ISO-8601 UTC>",
            "direction":      -1 | 0 | 1,
            "confidence":     0.0 .. 1.0,
            "signal_name":    "multitf_confirmation",
            "details": {
                "confirmation":        "bullish" | "bearish" | "neutral",
                "5m_trend":            "uptrend" | "downtrend" | "flat",
                "1m_slope":            float,
                "confidence_modifier": float
            },
            "error": null | "<message>"
        }
    """
    result: Dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "direction": 0,
        "confidence": 0.0,
        "signal_name": "multitf_confirmation",
        "details": {
            "confirmation": "neutral",
            "5m_trend": "flat",
            "1m_slope": 0.0,
            "confidence_modifier": 0.0,
        },
        "error": None,
    }
    result = with_advisory_contract(result)

    # ── fetch data ──────────────────────────────────────────────────
    closes_5m = fetch_bars(ticker, "5m", period_5m)
    if closes_5m is None or len(closes_5m) < 21:
        result["error"] = (
            f"Failed to fetch sufficient 5m bars for {ticker} "
            f"(got {len(closes_5m) if closes_5m is not None else 0})"
        )
        return result

    closes_1m = fetch_bars(ticker, "1m", period_1m)
    if closes_1m is None or len(closes_1m) < 5:
        result["error"] = (
            f"Failed to fetch sufficient 1m bars for {ticker} "
            f"(got {len(closes_1m) if closes_1m is not None else 0})"
        )
        return result

    # ── 5m trend ────────────────────────────────────────────────────
    trend_5m, trend_diff_pct = determine_5m_trend(closes_5m)
    result["details"]["5m_trend"] = trend_5m

    # ── 1m slope ────────────────────────────────────────────────────
    slope_1m = compute_1m_slope(closes_1m)
    result["details"]["1m_slope"] = round(slope_1m, 6)

    # Normalise slope by average price for cross-scale comparability
    avg_price_1m = float(np.mean(closes_1m[-5:]))
    slope_norm = slope_1m / avg_price_1m if avg_price_1m > 0 else 0.0

    # ── slope signal ────────────────────────────────────────────────
    if slope_norm > 0.0001:            # >  0.01% / bar
        slope_signal = "bullish"
    elif slope_norm < -0.0001:         # < -0.01% / bar
        slope_signal = "bearish"
    else:
        slope_signal = "flat"

    # ── combine 5m + 1m → direction + confirmation ──────────────────
    if trend_5m == "uptrend" and slope_signal == "bullish":
        result["direction"] = 1
        result["details"]["confirmation"] = "bullish"
    elif trend_5m == "downtrend" and slope_signal == "bearish":
        result["direction"] = -1
        result["details"]["confirmation"] = "bearish"
    elif trend_5m == "uptrend" and slope_signal == "flat":
        result["direction"] = 1
        result["details"]["confirmation"] = "bullish"
    elif trend_5m == "downtrend" and slope_signal == "flat":
        result["direction"] = -1
        result["details"]["confirmation"] = "bearish"
    elif trend_5m == "flat" and slope_signal == "bullish":
        result["direction"] = 1
        result["details"]["confirmation"] = "bullish"
    elif trend_5m == "flat" and slope_signal == "bearish":
        result["direction"] = -1
        result["details"]["confirmation"] = "bearish"
    else:
        # Conflict: uptrend+bearish, downtrend+bullish, or both flat
        result["direction"] = 0
        result["details"]["confirmation"] = "neutral"

    # ── confidence ──────────────────────────────────────────────────
    if result["direction"] != 0:
        # Agreement: scale each component's strength to [0, 1]
        # Trend strength:  2 % diff  → 1.0
        # Slope strength: 0.05 % / bar → 1.0
        trend_weight = _clamp(abs(trend_diff_pct) / 0.02, 0.0, 1.0)
        slope_weight = _clamp(abs(slope_norm) / 0.0005, 0.0, 1.0)
        result["confidence"] = round((trend_weight + slope_weight) / 2.0, 4)
    else:
        # Disagreement or flat: confidence reflects the weaker signal
        trend_weight = _clamp(abs(trend_diff_pct) / 0.02, 0.0, 1.0)
        slope_weight = _clamp(abs(slope_norm) / 0.0005, 0.0, 1.0)
        result["confidence"] = round(min(trend_weight, slope_weight) * 0.3, 4)

    # Raw product for downstream compositing
    result["details"]["confidence_modifier"] = round(
        abs(trend_diff_pct) * abs(slope_norm), 8
    )

    return result


def with_advisory_contract(signal: Dict[str, Any]) -> Dict[str, Any]:
    """Mark this confirmation as research/advisory only."""
    signal.update({
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "tradable_signal": False,
        "promoted_for_execution": False,
        "readyForExecution": False,
        "execution_role": "diagnostic_only",
        "limitations": [
            "Multi-timeframe confirmation may describe direction but is not a tradable signal by itself",
            "Must not approve sizing, demo, live, funding, or broker routing without promotion gates",
        ],
    })
    return signal


# ── CLI ────────────────────────────────────────────────────────────────
def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Multi-timeframe confirmation signal for NQ futures"
    )
    parser.add_argument(
        "--ticker", default="NQ=F",
        help="Yahoo Finance ticker (default: NQ=F)"
    )
    parser.add_argument(
        "--period-5m", default="5d",
        help="Lookback period for 5m bars (default: 5d)"
    )
    parser.add_argument(
        "--period-1m", default="1d",
        help="Lookback period for 1m bars (default: 1d)"
    )
    parser.add_argument(
        "--pretty", action="store_true",
        help="Pretty-print JSON output"
    )
    parser.add_argument(
        "--state-dir",
        default=str(DEFAULT_STATE_DIR),
        help=f"Directory for multitf-confirmation.latest.json (default: {DEFAULT_STATE_DIR})",
    )

    args = parser.parse_args()
    signal = compute_signal(
        ticker=args.ticker,
        period_5m=args.period_5m,
        period_1m=args.period_1m,
    )
    indent = 2 if args.pretty else None
    print(json.dumps(signal, indent=indent))
    state_dir = Path(args.state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "multitf-confirmation.latest.json").write_text(json.dumps(signal, indent=2) + "\n")


if __name__ == "__main__":
    main()
