#!/usr/bin/env python3
"""
QRS/RSRS Session Bias Signal
=============================
Rolling OLS regression of HIGH ~ LOW prices to derive a directional bias signal.

RSRS (Resistance-Support Relative Strength) model:
  HIGH_t = alpha + beta * LOW_t + epsilon_t

- Beta > 1: resistance rising faster than support → bullish pressure
- Beta < 1: support falling faster than resistance → bearish pressure
- Z-score beta over rolling window for standardized signal

Output: ~/.rumbling-hedge/state/qrs-bias-signal.latest.json
"""

import os
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

# Config
ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.environ.get("BILL_DATA_DIR") or (ROOT / "data" / "free"))
STATE_DIR = Path(os.environ.get("BILL_STATE_DIR") or os.environ.get("RH_STATE_DIR") or (ROOT / ".rumbling-hedge" / "state"))
OUTPUT_FILE = STATE_DIR / "qrs-bias-signal.latest.json"
ROLLING_WINDOW = 30  # bars for OLS regression
ZSCORE_WINDOW = 200  # bars for z-score normalization
BULLISH_THRESHOLD = 2.0
BEARISH_THRESHOLD = -2.0

# Data file candidates (prefer most data)
DATA_CANDIDATES = [
    "NQ-60m-60d.csv",
    "NQ-60m-30d.csv",
    "NQ-60m-21d.csv",
    "NQ-60m-5d.csv",
    "NQ-60m-1d.csv",
]
STALE_MINUTES = 90


def safety_metadata(reason: str = "research-only") -> dict:
    return {
        "researchOnly": True,
        "advisoryOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "tradable_signal": False,
        "promoted_for_execution": False,
        "readyForExecution": False,
        "execution_role": "diagnostic_only",
        "execution_block_reason": reason,
    }


def parse_bar_time(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def is_fresh_bar(value: str, now: datetime | None = None) -> bool:
    ts = parse_bar_time(value)
    if ts is None:
        return False
    now_utc = now or datetime.now(timezone.utc)
    return (now_utc - ts).total_seconds() <= STALE_MINUTES * 60


def ols_slope(x: list[float], y: list[float]) -> float:
    """Simple OLS slope: y = alpha + beta * x."""
    n = len(x)
    if n < 2:
        return 0.0
    x_mean = sum(x) / n
    y_mean = sum(y) / n
    ss_xx = sum((xi - x_mean) ** 2 for xi in x)
    ss_xy = sum((xi - x_mean) * (yi - y_mean) for xi, yi in zip(x, y))
    if ss_xx == 0:
        return 0.0
    return ss_xy / ss_xx


def ols_intercept(x: list[float], y: list[float], slope: float) -> float:
    """OLS intercept: alpha = y_mean - beta * x_mean."""
    n = len(x)
    if n == 0:
        return 0.0
    return sum(y) / n - slope * (sum(x) / n)


def r_squared(x: list[float], y: list[float], slope: float, intercept: float) -> float:
    """Coefficient of determination R²."""
    n = len(x)
    if n < 2:
        return 0.0
    y_mean = sum(y) / n
    ss_tot = sum((yi - y_mean) ** 2 for yi in y)
    ss_res = sum((yi - (intercept + slope * xi)) ** 2 for xi, yi in zip(x, y))
    if ss_tot == 0:
        return 0.0
    return 1.0 - ss_res / ss_tot


def z_score(value: float, history: list[float]) -> float:
    """Z-score of value against history."""
    n = len(history)
    if n < 2:
        return 0.0
    mean = sum(history) / n
    variance = sum((v - mean) ** 2 for v in history) / (n - 1)
    std = math.sqrt(variance)
    if std == 0:
        return 0.0
    return (value - mean) / std


def load_data() -> list[dict]:
    """Load NQ 60m OHLCV data, return list of bars."""
    for fname in DATA_CANDIDATES:
        fpath = DATA_DIR / fname
        if fpath.exists():
            print(f"[QRS] Loading {fpath.name} ({fpath.stat().st_size:,} bytes)")
            bars = []
            with open(fpath) as f:
                header = next(f).strip().split(",")
                for line in f:
                    parts = line.strip().split(",")
                    if len(parts) < 5:
                        continue
                    try:
                        bar = dict(zip(header, parts))
                        high = float(bar["high"])
                        low = float(bar["low"])
                        close = float(bar["close"])
                        if high > 0 and low > 0 and close > 0:
                            bars.append({
                                "ts": bar["ts"],
                                "open": float(bar["open"]),
                                "high": high,
                                "low": low,
                                "close": close,
                                "volume": float(bar.get("volume", 0) or 0),
                            })
                    except (ValueError, KeyError):
                        continue
            print(f"[QRS] Loaded {len(bars)} valid bars")
            return bars
    print("[QRS] ERROR: No data file found", file=sys.stderr)
    sys.exit(1)


def compute_signal(bars: list[dict]) -> dict:
    """Compute RSRS beta, rolling z-score, and session bias signal."""
    if len(bars) < ROLLING_WINDOW:
        return {
            "error": f"Insufficient data: {len(bars)} bars, need {ROLLING_WINDOW}",
            "signal": "neutral",
            "z_score": 0.0,
            **safety_metadata("insufficient-data"),
        }

    lows = [b["low"] for b in bars]
    highs = [b["high"] for b in bars]

    # Compute rolling betas
    betas = []
    r2_values = []
    for i in range(ROLLING_WINDOW, len(bars)):
        window_low = lows[i - ROLLING_WINDOW:i]
        window_high = highs[i - ROLLING_WINDOW:i]
        beta = ols_slope(window_low, window_high)
        alpha = ols_intercept(window_low, window_high, beta)
        r2 = r_squared(window_low, window_high, beta, alpha)
        betas.append(beta)
        r2_values.append(r2)

    if len(betas) < 2:
        return {
            "error": "Insufficient rolling windows",
            "signal": "neutral",
            "z_score": 0.0,
            **safety_metadata("insufficient-rolling-windows"),
        }

    # Current beta and its z-score
    current_beta = betas[-1]
    current_r2 = r2_values[-1]

    # Z-score over available beta history (up to ZSCORE_WINDOW)
    beta_history = betas[-min(len(betas), ZSCORE_WINDOW):]
    z = z_score(current_beta, beta_history)

    # Signal determination
    if z >= BULLISH_THRESHOLD:
        signal = "bullish"
    elif z <= BEARISH_THRESHOLD:
        signal = "bearish"
    else:
        signal = "neutral"

    # R² distribution stats
    r2_history = r2_values[-min(len(r2_values), ZSCORE_WINDOW):]
    r2_mean = sum(r2_history) / len(r2_history) if r2_history else 0
    r2_min = min(r2_history) if r2_history else 0

    # Beta stats
    beta_mean = sum(beta_history) / len(beta_history)
    beta_std = math.sqrt(sum((b - beta_mean) ** 2 for b in beta_history) / max(len(beta_history) - 1, 1))

    # Confidence: high R² = strong linear relationship = reliable signal
    confidence = min(current_r2 / max(r2_mean, 0.01), 2.0)  # capped at 2x

    result = {
        "signal": signal,
        "z_score": round(z, 4),
        "beta": round(current_beta, 6),
        "beta_mean": round(beta_mean, 6),
        "beta_std": round(beta_std, 6),
        "r_squared": round(current_r2, 4),
        "r_squared_mean": round(r2_mean, 4),
        "confidence": round(confidence, 4),
        "thresholds": {
            "bullish": BULLISH_THRESHOLD,
            "bearish": BEARISH_THRESHOLD,
        },
        "window": ROLLING_WINDOW,
        "zscore_lookback": len(beta_history),
        "total_bars": len(bars),
        "data_range": f"{bars[0]['ts']} → {bars[-1]['ts']}",
        "last_bar": bars[-1]["ts"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": "RSRS_QRS_v1",
        **safety_metadata(),
    }

    return result


def main():
    print("[QRS] Starting QRS/RSRS Session Bias computation...")
    bars = load_data()

    if not bars:
        print("[QRS] No bars loaded, exiting", file=sys.stderr)
        sys.exit(1)

    result = compute_signal(bars)
    last_bar = str(result.get("last_bar") or bars[-1].get("ts") or "")
    data_fresh = is_fresh_bar(last_bar)
    result["data_fresh"] = data_fresh
    if not data_fresh:
        if result.get("signal") != "neutral":
            result["raw_research_signal"] = {
                "signal": result.get("signal"),
                "z_score": result.get("z_score"),
                "beta": result.get("beta"),
                "r_squared": result.get("r_squared"),
                "confidence": result.get("confidence"),
            }
        result["signal"] = "neutral"
        result["confidence"] = 0.0
        result.update(safety_metadata("stale-data-research-only"))
    print(
        f"[QRS] Signal: {result['signal']} | Z: {result.get('z_score')} | "
        f"Beta: {result.get('beta', 'N/A')} | R²: {result.get('r_squared', 'N/A')}"
    )

    # Write state file
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(result, f, indent=2)
    print(f"[QRS] State written: {OUTPUT_FILE}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
