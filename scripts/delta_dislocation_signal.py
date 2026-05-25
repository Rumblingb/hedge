#!/usr/bin/env python3
"""
Delta Dislocation Signal — DOM Divergence Detector
====================================================

Concept (from @matfinog orderflow video):
When price moves UP but cumulative volume delta moves DOWN, that's a bearish
divergence — the aggressive buying is losing conviction.
When price moves DOWN but delta moves UP, that's a bullish divergence.

This script reads the existing DOM proxy state and computes a simple
divergence signal based on the relationship between price direction
and cumulative volume delta direction.

Input:  ~/.rumbling-hedge/state/dom-proxy-signal.latest.json
Output: ~/.rumbling-hedge/state/delta-dislocation.latest.json
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

# ── Config ──────────────────────────────────────────────────────────────
STATE_DIR = Path(os.path.expanduser("~/.rumbling-hedge/state"))
DOM_PROXY_FILE = STATE_DIR / "dom-proxy-signal.latest.json"
OUTPUT_FILE = STATE_DIR / "delta-dislocation.latest.json"
STATE_DIR.mkdir(parents=True, exist_ok=True)

# Thresholds for direction classification
PRICE_Z_THRESHOLD = 0.2   # |price_z| below this = flat
DELTA_Z_THRESHOLD = 0.2   # |delta_z| below this = flat


def _classify_direction(z_score: float, threshold: float) -> str:
    """Classify a z-score into direction: 'up', 'down', or 'flat'."""
    if z_score > threshold:
        return "up"
    elif z_score < -threshold:
        return "down"
    else:
        return "flat"


def compute_divergence_signal(dom_proxy: dict) -> dict:
    """Compute delta dislocation signal from DOM proxy state.

    Logic:
      - Price UP + Delta DOWN  → bearish divergence (signal negative)
      - Price DOWN + Delta UP  → bullish divergence (signal positive)
      - Otherwise              → neutral (0.0)

    Signal strength scales with the magnitude of the divergence.
    """
    price_z = dom_proxy.get("current_price_z", 0.0)
    delta_z = dom_proxy.get("current_delta_z", 0.0)
    divergence = dom_proxy.get("divergence", 0.0)

    price_direction = _classify_direction(price_z, PRICE_Z_THRESHOLD)
    delta_direction = _classify_direction(delta_z, DELTA_Z_THRESHOLD)

    # Compute signal strength: base magnitude from 0.3-0.5 scaled by
    # how strong the divergence is.
    max_raw = 3.0  # cap for normalization
    raw_strength = min(abs(divergence), max_raw) / max_raw  # 0.0 to 1.0

    if price_direction == "up" and delta_direction == "down":
        # Bearish divergence: price rising but delta falling
        signal = -0.3 - (0.2 * raw_strength)  # range: -0.3 to -0.5
        interpretation = (
            f"BEARISH DIVERGENCE: Price moving up (z={price_z:.2f}) while "
            f"cumulative delta moving down (z={delta_z:.2f}) — "
            f"aggressive buying losing conviction. Divergence={divergence:.2f}"
        )
    elif price_direction == "down" and delta_direction == "up":
        # Bullish divergence: price falling but delta rising
        signal = 0.3 + (0.2 * raw_strength)  # range: +0.3 to +0.5
        interpretation = (
            f"BULLISH DIVERGENCE: Price moving down (z={price_z:.2f}) while "
            f"cumulative delta moving up (z={delta_z:.2f}) — "
            f"selling pressure absorbing. Divergence={divergence:.2f}"
        )
    else:
        signal = 0.0
        interpretation = (
            f"NEUTRAL: No clear divergence. "
            f"Price={price_direction} (z={price_z:.2f}), "
            f"Delta={delta_direction} (z={delta_z:.2f})"
        )

    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "delta_signal": round(signal, 4),
        "price_direction": price_direction,
        "delta_direction": delta_direction,
        "price_z": round(price_z, 2),
        "delta_z": round(delta_z, 2),
        "raw_divergence": round(divergence, 2),
        "interpretation": interpretation,
        "method": "delta_dislocation",
        "source": str(DOM_PROXY_FILE),
    }


def main() -> None:
    print("🔀 Delta Dislocation Signal — DOM Divergence Detector")
    print("=" * 55)

    if not DOM_PROXY_FILE.exists():
        print(f"❌ DOM proxy state not found: {DOM_PROXY_FILE}")
        print("   Producing neutral fallback signal.")

        fallback = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "delta_signal": 0.0,
            "price_direction": "unknown",
            "delta_direction": "unknown",
            "price_z": 0.0,
            "delta_z": 0.0,
            "raw_divergence": 0.0,
            "interpretation": "No DOM proxy data available — neutral fallback.",
            "method": "delta_dislocation_fallback",
            "source": str(DOM_PROXY_FILE),
        }
        with open(OUTPUT_FILE, "w") as f:
            json.dump(fallback, f, indent=2)
        print(f"✅ Fallback written to {OUTPUT_FILE}")
        return

    with open(DOM_PROXY_FILE) as f:
        dom_proxy = json.load(f)

    signal = compute_divergence_signal(dom_proxy)

    print(f"\nPrice direction:    {signal['price_direction']:>6s} (z={signal['price_z']:+.2f})")
    print(f"Delta direction:    {signal['delta_direction']:>6s} (z={signal['delta_z']:+.2f})")
    print(f"Raw divergence:     {signal['raw_divergence']:+.2f}")
    print(f"Delta signal:       {signal['delta_signal']:+.4f}")
    print(f"\n{signal['interpretation']}")

    with open(OUTPUT_FILE, "w") as f:
        json.dump(signal, f, indent=2)

    print(f"\n✅ Written to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
