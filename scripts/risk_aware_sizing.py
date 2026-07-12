#!/usr/bin/env python3
"""
Risk-Aware Position Sizing — Yang & Deng (2026) Vol-Normalized Formula
======================================================================

Reads arbitration.latest.json and noise-analysis.latest.json from the
state directory, computes volatility-normalized contract sizing with a
tail-risk penalty, and emits a standard signal JSON.

Formula (Yang & Deng, 2026):
    raw_position = signal_strength / conditional_vol
    conditional_vol = nsr / 100 * 1.5
    recommended_contracts = clip(raw_position * risk_penalty, -max_c, max_c)

where signal_strength is the weighted_dir from arbitration and nsr is the
current noise-to-signal ratio from the noise-analysis for the matched symbol.

Usage:
    python3 risk_aware_sizing.py [--state-dir PATH]

Output: Standard signal JSON written to <state-dir>/risk-aware-sizing.latest.json
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict


# ── Configuration ─────────────────────────────────────────────────────────
DEFAULT_STATE_DIR = Path(os.environ.get("BILL_STATE_DIR", os.path.expanduser("~/hedge/.rumbling-hedge/state")))
MAX_CONTRACTS = 1.0               # hard cap on contracts (each side) — 1-contract research/demo envelope per Topstep policy (was 3.0; corrected 2026-06-09)
CONDITIONAL_VOL_SCALAR = 1.5      # Yang & Deng scalar
TAIL_RISK_PENALTY = 0.5           # applied in high_vol / extreme_vol regimes
SIGNAL_NAME = "risk_aware_sizing"
DIRECTION = 0                     # sizing-only signal, direction is neutral

# Regime values that trigger the tail-risk penalty.
HIGH_RISK_REGIMES = frozenset({
    "high_vol",
    "extreme_vol",
    "high_noise",   # matches actual noise-analysis regime value
})


# ── Helpers ───────────────────────────────────────────────────────────────

def _resolve_symbol(arbitration: Dict) -> str:
    """Return the lowercase symbol key used in noise-analysis details."""
    sym = arbitration.get("symbol", "NQ")
    return sym.lower()


def _load_json(path: Path) -> Optional[Dict]:
    """Load and parse a JSON file, returning None on any failure."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _load_arbitration(state_dir: Path) -> Optional[Dict]:
    return _load_json(state_dir / "arbitration.latest.json")


def _load_noise_analysis(state_dir: Path) -> Optional[Dict]:
    return _load_json(state_dir / "noise-analysis.latest.json")


def _extract_signal_strength(arbitration: Dict) -> float:
    """Extract the weighted direction as raw signal strength."""
    return float(arbitration.get("weighted_dir", 0.0))


def _extract_nsr(noise: Dict, symbol: str) -> float:
    """Extract current NSR for the given symbol from noise-analysis."""
    details = noise.get("details", {})
    symbol_key = f"{symbol}_noise"
    symbol_data = details.get(symbol_key, {})
    nsr = symbol_data.get("current_nsr")
    if nsr is None:
        return 0.0
    return float(nsr)


def _extract_regime(noise: Dict, symbol: str) -> str:
    """Extract the volatility regime for the given symbol."""
    details = noise.get("details", {})
    symbol_key = f"{symbol}_noise"
    symbol_data = details.get(symbol_key, {})
    return str(symbol_data.get("regime", "unknown")).lower()


def _compute_conditional_vol(nsr: float) -> float:
    """Yang & Deng conditional volatility: nsr/100 * 1.5"""
    if nsr <= 0:
        return 0.001  # floor to avoid division by zero
    return (nsr / 100.0) * CONDITIONAL_VOL_SCALAR


def _compute_risk_penalty(regime: str) -> float:
    """Return 0.5 in high-risk regimes, else 1.0."""
    if regime in HIGH_RISK_REGIMES:
        return TAIL_RISK_PENALTY
    return 1.0


def _clip(value: float, lower: float, upper: float) -> float:
    return max(lower, min(value, upper))


# ── Core Logic ────────────────────────────────────────────────────────────

def compute_sizing(state_dir: Path) -> Dict:
    """Run the full sizing computation and return the signal dict."""

    # 1. Load state files
    arbitration = _load_arbitration(state_dir)
    noise = _load_noise_analysis(state_dir)

    # Graceful fallback when files are missing
    signal_strength = 0.0
    nsr = 0.0
    regime = "unknown"
    errors = []

    if arbitration is None:
        errors.append("arbitration.latest.json not found or unreadable")
    else:
        signal_strength = _extract_signal_strength(arbitration)

    symbol = _resolve_symbol(arbitration) if arbitration else "nq"

    if noise is None:
        errors.append("noise-analysis.latest.json not found or unreadable")
    else:
        nsr = _extract_nsr(noise, symbol)
        regime = _extract_regime(noise, symbol)

    if errors:
        conditional_vol = 0.0
        vol_normalized = 0.0
        risk_penalty = 0.0
        final_sizing = 0.0
        recommended_contracts = 0.0
    else:
        # 2. Yang & Deng vol-normalized sizing
        conditional_vol = _compute_conditional_vol(nsr)
        vol_normalized = signal_strength / conditional_vol if conditional_vol > 0 else 0.0

        # 3. Tail-risk penalty
        risk_penalty = _compute_risk_penalty(regime)

        # 4. Final clipped sizing
        final_sizing = vol_normalized * risk_penalty
        recommended_contracts = _clip(final_sizing, -MAX_CONTRACTS, MAX_CONTRACTS)

    # 5. Build signal dict
    signal = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "direction": DIRECTION,
        "confidence": round(abs(recommended_contracts) / MAX_CONTRACTS, 4),
        "signal_name": SIGNAL_NAME,
        "details": {
            "symbol": symbol.upper(),
            "signal_strength": round(signal_strength, 6),
            "nsr": round(nsr, 6),
            "conditional_vol": round(conditional_vol, 6),
            "vol_normalized": round(vol_normalized, 6),
            "regime": regime,
            "risk_penalty": risk_penalty,
            "final_sizing": round(final_sizing, 6),
            "recommended_contracts": round(recommended_contracts, 4),
            "max_contracts": MAX_CONTRACTS,
            "errors": errors,
            "fail_closed": bool(errors),
        },
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "tradable_signal": False,
        "promoted_for_execution": False,
        "readyForExecution": False,
        "execution_role": "diagnostic_only",
        "limitations": [
            "Sizing output is advisory and may not route or submit orders",
            "Recommended contracts are capped diagnostics until Topstep/demo promotion gates explicitly pass",
        ],
    }

    return signal


def _write_output(signal: Dict, state_dir: Path) -> None:
    """Write signal JSON to the state directory."""
    state_dir.mkdir(parents=True, exist_ok=True)
    output_file = state_dir / "risk-aware-sizing.latest.json"
    with open(output_file, "w") as f:
        json.dump(signal, f, indent=2)
    print(f"Written to {output_file}", file=sys.stderr)


# ── CLI ───────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Risk-Aware Position Sizing (Yang & Deng 2026)"
    )
    parser.add_argument(
        "--state-dir",
        type=str,
        default=None,
        help=f"Path to state directory (default: {DEFAULT_STATE_DIR})",
    )
    args = parser.parse_args()

    state_dir = Path(args.state_dir) if args.state_dir else DEFAULT_STATE_DIR

    signal = compute_sizing(state_dir)

    # Print to stdout
    print(json.dumps(signal, indent=2))

    # Write to state file
    _write_output(signal, state_dir)


if __name__ == "__main__":
    main()
