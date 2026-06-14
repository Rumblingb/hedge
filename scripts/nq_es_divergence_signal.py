#!/usr/bin/env python3
"""
NQ vs ES Divergence Signal
============================
Detects systematic divergence between NQ (Nasdaq-100) and ES (S&P 500) e-mini futures.

When they diverge, it reveals:
- NQ leading while ES lags → tech/rate-driven move (growth rotation)
- ES leading while NQ lags → value/macro-driven move (value rotation)
- Ratio extreme → mean reversion opportunity

Computes: rolling ratio z-score of NQ/ES, delta divergence, regime classification.

State file: ~/.rumbling-hedge/state/nq-es-divergence-signal.latest.json
"""
import json
import os
import sys
import csv
import numpy as np
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, List

STATE_DIR = Path.home() / ".rumbling-hedge" / "state"
STATE_DIR.mkdir(parents=True, exist_ok=True)
STATE_FILE = STATE_DIR / "nq-es-divergence-signal.latest.json"

DATA_DIR = Path.home() / "hedge" / "data" / "free"

# Lookback windows for divergence detection (bars at 15m)
LOOKBACK_SHORT = 6   # ~1.5h
LOOKBACK_MEDIUM = 26  # ~6.5h
LOOKBACK_LONG = 64    # ~16h

# Divergence thresholds (z-score)
DIVERGENCE_THRESHOLD = 2.0
EXTREME_DIVERGENCE = 3.0


def load_close_prices(symbol: str, timeframe: str = "15m") -> Optional[np.ndarray]:
    """Load close prices for a symbol from CSV."""
    # Try the 60d file first (most recent)
    candidates = [
        DATA_DIR / f"{symbol}-{timeframe}-60d.csv",
        DATA_DIR / f"{symbol}-{timeframe}-30d.csv",
        DATA_DIR / f"{symbol}-{timeframe}-90d.csv",
    ]
    for path in candidates:
        if path.exists():
            try:
                closes: List[float] = []
                with open(str(path), "r") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        try:
                            closes.append(float(row["close"]))
                        except (KeyError, ValueError):
                            continue
                if len(closes) > LOOKBACK_LONG:
                    return np.array(closes)
            except Exception:
                continue
    return None


def compute_divergence(nq_prices: np.ndarray, es_prices: np.ndarray) -> dict:
    """Compute NQ/ES ratio, rolling z-score divergence, regime classification."""
    min_len = min(len(nq_prices), len(es_prices))
    nq = nq_prices[-min_len:]
    es = es_prices[-min_len:]

    ratio = nq / es

    results = {}
    for name, lb in [("short", LOOKBACK_SHORT), ("medium", LOOKBACK_MEDIUM), ("long", LOOKBACK_LONG)]:
        if min_len < lb + 1:
            results[name] = {"z_score": 0.0, "signal": "neutral", "diverged": False}
            continue
        recent = ratio[-lb:]
        mean = float(np.mean(recent))
        std = float(np.std(recent))
        z = (ratio[-1] - mean) / (std + 1e-10)

        if z > DIVERGENCE_THRESHOLD:
            signal = "nq_overextended"
        elif z < -DIVERGENCE_THRESHOLD:
            signal = "es_overextended"
        else:
            signal = "neutral"

        results[name] = {
            "z_score": round(float(z), 3),
            "signal": signal,
            "diverged": abs(z) > DIVERGENCE_THRESHOLD,
            "extreme": abs(z) > EXTREME_DIVERGENCE,
            "lookback_bars": lb,
        }

    med_z = results.get("medium", {}).get("z_score", 0)
    short_z = results.get("short", {}).get("z_score", 0)

    if abs(med_z) < 1.0 and abs(short_z) < 1.0:
        regime = "aligned"
    elif med_z > 1.5 and short_z > 1.0:
        regime = "nq_leading"
    elif med_z < -1.5 and short_z < -1.0:
        regime = "es_leading"
    elif abs(med_z) > 2.0 and abs(short_z) < 0.5:
        regime = "ratio_reversion_imminent"
    else:
        regime = "transitioning"

    return {
        "current_ratio": round(float(ratio[-1]), 4),
        "ratio_change_pct": round(float((ratio[-1] / ratio[-2] - 1) * 100), 3) if min_len >= 2 else 0,
        "lookbacks": results,
        "regime": regime,
        "total_bars": min_len,
    }


def run(symbol: str = "NQ", timeframe: str = "15m") -> dict:
    nq_prices = load_close_prices("NQ", timeframe)
    es_prices = load_close_prices("ES", timeframe)

    if nq_prices is None or es_prices is None:
        missing = []
        if nq_prices is None:
            missing.append("NQ")
        if es_prices is None:
            missing.append("ES")
        output = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "signal_name": "nq_es_divergence",
            "direction": 0.0,
            "confidence": 0.0,
            "regime": "unknown",
            "edge_classification": "neutral",
            "error": f"missing_data: {missing}",
            "details": {},
        }
        STATE_FILE.write_text(json.dumps(output, indent=2) + "\n")
        return output

    div = compute_divergence(nq_prices, es_prices)
    med_z = div["lookbacks"].get("medium", {}).get("z_score", 0)

    # Classify edge direction
    regime = div["regime"]
    if regime == "aligned":
        edge = "neutral"
    elif regime == "nq_leading":
        edge = "bearish_nq_inclined"  # NQ overextended relative to ES
    elif regime == "es_leading":
        edge = "bullish_nq_inclined"  # ES leading value rotation, NQ may catch up
    elif regime == "ratio_reversion_imminent":
        edge = "bearish_nq_inclined" if med_z > 0 else "bullish_nq_inclined"
    else:
        edge = "neutral"

    # Direction: positive → NQ bullish relative to ES (or ES leading → NQ catch-up)
    direction = 0.0
    if edge == "bearish_nq_inclined":
        direction = -0.3
    elif edge == "bullish_nq_inclined":
        direction = 0.3

    confidence = min(abs(med_z) / 3.0, 0.95)

    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "signal_name": "nq_es_divergence",
        "direction": direction,
        "confidence": round(float(confidence), 3),
        "regime": regime,
        "edge_classification": edge,
        "error": None,
        "details": {
            "symbol_pair": f"{symbol}/ES",
            "timeframe": timeframe,
            "data_bars_nq": len(nq_prices),
            "data_bars_es": len(es_prices),
            "current_ratio": div["current_ratio"],
            "ratio_change_pct": div["ratio_change_pct"],
            "medium_z": med_z,
            "short_z": div["lookbacks"].get("short", {}).get("z_score", 0),
        },
    }

    STATE_FILE.write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(output, indent=2))
    return output


if __name__ == "__main__":
    run()
