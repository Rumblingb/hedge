#!/usr/bin/env python3
"""
Position Sizing Engine — Multi-Factor Contract Calculation
===========================================================

Replaces the simple Yang & Deng formula (risk_aware_sizing.py) with a
multi-factor engine that considers:

1. Half-Kelly Criterion (edge-based optimal sizing)
2. Equity Risk Budget (% of account at risk per trade)
3. ATR Volatility Adjustment (stop distance sizing)
4. Drawdown Scaling (reduce size during DD periods)
5. Correlation Penalty (reduce for correlated instruments)
6. Circuit Breaker Override (from drawdown_circuit_breaker.py)

Formula:
    kelly_size = f* = (p*b - q) / b, where b=payoff_ratio, p=win_rate, q=1-p
    half_kelly = clip(f* / 2, 0, max_f)
    
    equity_budget = (account * risk_pct) / (stop_distance_pts * point_value)
    
    vol_adjusted = equity_budget * (target_atr / current_atr)
    
    dd_scaled    = vol_adjusted * circuit_breaker.multiplier
    
    final        = max(1, floor(dd_scaled)) if signal, else 0

Inputs:
  - drawdown-circuit-breaker.latest.json (tier, multiplier)
  - risk-aware-sizing.latest.json (signal strength, vol regime)
  - trade-journal.jsonl (historical win rate, payoff ratio)
  - risk-state.json (account limits)

Outputs:
  - position-sizing-engine.latest.json

Usage:
    python3 position_sizing_engine.py [--state-dir PATH]
"""

import argparse
import json
import math
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STATE_DIR = Path(os.environ.get("BILL_STATE_DIR", str(REPO_ROOT / ".rumbling-hedge/state"))).expanduser()
JOURNAL_NAME = "trade-journal.jsonl"
RISK_STATE_NAME = "risk-state.json"
BREAKER_NAME = "drawdown-circuit-breaker.latest.json"
OLD_SIZING_NAME = "risk-aware-sizing.latest.json"
OUTPUT_NAME = "position-sizing-engine.latest.json"

# ── Configuration ──────────────────────────────────────────────────────────

DEFAULT_BALANCE = 100_000.0
RISK_PER_TRADE_PCT = 0.01        # 1% of equity at risk per trade
HALF_KELLY_CAP = 0.25            # Never risk more than 25% of Kelly
MIN_KELLY_TRADES = 10            # Need at least 10 trades for Kelly estimate
POINT_VALUE_MNQ = 2.0            # $2 per point per MNQ contract
POINT_VALUE_NQ = 20.0            # $20 per point per NQ contract
DEFAULT_ATR = 15.0               # Default ATR for NQ 15m in points
TARGET_RR = 1.5                  # Minimum reward:risk ratio
MAX_CONTRACTS_MNQ = 5            # Hard cap for MNQ
MAX_CONTRACTS_NQ = 2             # Hard cap for NQ
MIN_CONFIDENCE = 0.30            # Minimum confidence to trade


def point_value_for_instrument(instrument: str) -> float:
    symbol = (instrument or "MNQ").upper()
    if symbol == "NQ":
        return POINT_VALUE_NQ
    return POINT_VALUE_MNQ


# ── Helpers ────────────────────────────────────────────────────────────────

def _load_json(path: Path) -> Optional[Dict]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _load_journal(state_dir: Path) -> List[Dict]:
    path = state_dir / JOURNAL_NAME
    if not path.exists():
        return []
    trades = []
    for line in path.read_text().strip().splitlines():
        try:
            trades.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return trades


def _compute_win_rate_payoff(trades: List[Dict], window: int = 30) -> Tuple[float, float, float]:
    """Compute win rate, avg win, avg loss from last N trades.
    Returns: (win_rate, avg_win, avg_loss)
    """
    recent = trades[-window:] if len(trades) >= window else trades
    if not recent:
        return 0.5, 1.0, 1.0  # neutral prior

    wins = [float(t.get("pnl_dollars", 0)) for t in recent if float(t.get("pnl_dollars", 0)) > 0]
    losses = [abs(float(t.get("pnl_dollars", 0))) for t in recent if float(t.get("pnl_dollars", 0)) < 0]

    win_rate = len(wins) / len(recent) if recent else 0.5
    avg_win = sum(wins) / len(wins) if wins else 1.0
    avg_loss = sum(losses) / len(losses) if losses else 1.0

    return win_rate, avg_win, avg_loss


def _compute_atr_from_journal(trades: List[Dict]) -> float:
    """Estimate ATR from journal entry ATR values."""
    atrs = [float(t.get("atr_at_entry", 0)) for t in trades if t.get("atr_at_entry")]
    if atrs:
        # Use recent 10 trades
        recent = atrs[-10:]
        return sum(recent) / len(recent)
    return DEFAULT_ATR


# ── Kelly Criterion ────────────────────────────────────────────────────────

def half_kelly(win_rate: float, payoff_ratio: float) -> float:
    """Compute half-Kelly fraction.
    
    Kelly criterion: f* = (p*b - q) / b
    where p = win rate, b = avg_win/avg_loss (payoff ratio), q = 1-p
    
    Half-Kelly: f*/2, capped at HALF_KELLY_CAP.
    """
    if payoff_ratio <= 0 or win_rate <= 0:
        return 0.0

    p = win_rate
    q = 1.0 - p
    b = payoff_ratio

    f_star = (p * b - q) / b

    # Negative Kelly = no edge
    if f_star <= 0:
        return 0.0

    half_f = f_star / 2.0
    return min(half_f, HALF_KELLY_CAP)


# ── Equity Budget ──────────────────────────────────────────────────────────

def equity_budget_size(
    balance: float,
    risk_pct: float,
    stop_distance_pts: float,
    point_value: float,
) -> float:
    """Contracts from equity risk budget.
    
    Risk amount = balance * risk_pct
    Contracts = risk_amount / (stop_distance * point_value)
    """
    if stop_distance_pts <= 0 or point_value <= 0:
        return 0.0

    risk_amount = balance * risk_pct
    contracts = risk_amount / (stop_distance_pts * point_value)
    return contracts


# ── Volatility Adjustment ──────────────────────────────────────────────────

def vol_adjust(current_atr: float, target_atr: float = DEFAULT_ATR) -> float:
    """Adjust sizing inversely to current volatility vs target.
    
    When vol is high (ATR > target), reduce size.
    When vol is low (ATR < target), can increase slightly (capped).
    """
    if target_atr <= 0:
        return 1.0
    
    ratio = target_atr / current_atr
    # Clamp to [0.5, 1.3] — don't over-lever in low vol, don't collapse in high vol
    return max(0.5, min(ratio, 1.3))


# ── Drawdown Scaling ──────────────────────────────────────────────────────

def drawdown_scale(breaker: Optional[Dict]) -> Tuple[float, int]:
    """Get sizing multiplier and max contracts from circuit breaker.
    
    Returns: (multiplier, max_contracts)
    """
    if not breaker:
        return 1.0, MAX_CONTRACTS_MNQ

    mult = breaker.get("sizing_multiplier", 1.0)
    max_c = breaker.get("max_contracts", MAX_CONTRACTS_MNQ)
    return mult, max_c


# ── Correlation Penalty ─────────────────────────────────────────────────────

def correlation_penalty(
    signal_direction: float,
    existing_positions: Dict[str, Dict],
) -> float:
    """Reduce sizing when adding to correlated positions.
    
    NQ and ES are ~0.9 correlated, so adding in same direction is roughly
    doubling exposure. Apply 0.6x penalty if already positioned same direction.
    """
    if not existing_positions:
        return 1.0

    same_direction_exposure = 0
    for instrument, pos in existing_positions.items():
        side = pos.get("side", "").lower()
        qty = int(pos.get("qty", 0))
        
        if side == "long" and signal_direction > 0.15:
            same_direction_exposure += qty
        elif side == "short" and signal_direction < -0.15:
            same_direction_exposure += qty

    if same_direction_exposure >= 2:
        return 0.5
    elif same_direction_exposure >= 1:
        return 0.7
    return 1.0


# ── Main Logic ─────────────────────────────────────────────────────────────

def compute_sizing(state_dir: Path, balance_override: Optional[float] = None) -> Dict:
    """Compute the full position sizing recommendation."""
    now = datetime.now(timezone.utc)

    # Load all inputs
    breaker = _load_json(state_dir / BREAKER_NAME)
    old_sizing = _load_json(state_dir / OLD_SIZING_NAME)
    risk_state = _load_json(state_dir / RISK_STATE_NAME)
    journal = _load_journal(state_dir)
    instrument = "MNQ"
    if risk_state:
        instrument = risk_state.get("instrument", "MNQ")
    point_value = point_value_for_instrument(instrument)

    # Balance
    balance = balance_override or DEFAULT_BALANCE

    # Historical performance
    win_rate, avg_win, avg_loss = _compute_win_rate_payoff(journal, window=30)
    payoff_ratio = avg_win / avg_loss if avg_loss > 0 else 1.0
    current_atr = _compute_atr_from_journal(journal)

    # Signal from old sizing module (vol-normalized direction)
    signal_strength = 0.0
    signal_direction = 0.0  # +1 long, -1 short, 0 flat
    vol_regime = "normal"
    if old_sizing:
        details = old_sizing.get("details", {})
        signal_strength = details.get("signal_strength", 0.0)
        vol_regime = details.get("regime", "normal")
        signal_direction = 1.0 if signal_strength > 0.15 else (-1.0 if signal_strength < -0.15 else 0.0)

    # Confidence from signal
    if old_sizing and "confidence" in old_sizing:
        raw_confidence = old_sizing["confidence"]
    else:
        raw_confidence = abs(signal_strength) if signal_strength else 0.0

    # ── Factor 1: Half-Kelly ──
    kelly_enough_data = len(journal) >= MIN_KELLY_TRADES
    if kelly_enough_data:
        kelly_fraction = half_kelly(win_rate, payoff_ratio)
        kelly_contracts = kelly_fraction * balance / (current_atr * point_value)
    else:
        kelly_fraction = 0.0
        kelly_contracts = 1.0  # Default to 1 until enough data
    kelly_contracts = max(0, kelly_contracts)

    # ── Factor 2: Equity Budget ──
    stop_distance = current_atr * TARGET_RR  # Stop at 1.5x ATR
    budget_contracts = equity_budget_size(
        balance=balance,
        risk_pct=RISK_PER_TRADE_PCT,
        stop_distance_pts=stop_distance,
        point_value=point_value,
    )

    # ── Factor 3: Volatility Adjustment ──
    vol_mult = vol_adjust(current_atr)

    # ── Factor 4: Circuit Breaker Override ──
    breaker_mult, breaker_max = drawdown_scale(breaker)

    # ── Factor 5: Correlation Penalty ──
    # Read position map from risk state if available
    existing_positions = {}
    if risk_state:
        existing_positions = risk_state.get("positions", {})
    corr_mult = correlation_penalty(signal_direction, existing_positions)

    # ── Combine: use MINIMUM of Kelly and Budget as base ──
    if kelly_enough_data:
        base_contracts = min(kelly_contracts, budget_contracts)
        base_source = "min(kelly, budget)"
    else:
        base_contracts = budget_contracts
        base_source = "budget_only"

    # Apply multipliers sequentially
    adjusted = base_contracts * vol_mult * breaker_mult * corr_mult

    # Confidence gate
    if raw_confidence < MIN_CONFIDENCE or signal_direction == 0:
        adjusted = 0.0
        gate_reason = f"confidence {raw_confidence:.2f} < {MIN_CONFIDENCE}"
    else:
        gate_reason = "pass"

    # Floor to integer, min 1 if signal exists
    final_contracts = int(max(0, math.floor(adjusted)))
    
    # Hard cap
    final_contracts = min(final_contracts, breaker_max, MAX_CONTRACTS_MNQ)

    max_for_instrument = MAX_CONTRACTS_NQ if instrument == "NQ" else MAX_CONTRACTS_MNQ
    final_contracts = min(final_contracts, max_for_instrument)

    # ── Risk per trade in USD ──
    risk_per_trade_usd = final_contracts * stop_distance * point_value
    risk_per_trade_pct = risk_per_trade_usd / balance * 100 if balance > 0 else 0

    # ── Build output ──
    result = {
        "timestamp": now.isoformat(),
        "signal_name": "position_sizing_engine",
        "direction": int(signal_direction),
        "confidence": round(raw_confidence, 4),
        "recommended_contracts": final_contracts,
        "risk_per_trade_usd": round(risk_per_trade_usd, 2),
        "risk_per_trade_pct": round(risk_per_trade_pct, 2),
        "factors": {
            "kelly": {
                "fraction": round(kelly_fraction, 6),
                "contracts": round(kelly_contracts, 2),
                "enough_data": kelly_enough_data,
                "note": f"Win rate: {win_rate:.1%}, Payoff: {payoff_ratio:.2f}" if kelly_enough_data else f"Need {MIN_KELLY_TRADES} trades (have {len(journal)})",
            },
            "equity_budget": {
                "risk_pct": RISK_PER_TRADE_PCT,
                "risk_amount_usd": round(balance * RISK_PER_TRADE_PCT, 2),
                "stop_distance_pts": round(stop_distance, 2),
                "contracts": round(budget_contracts, 2),
                "source": base_source,
            },
            "volatility": {
                "current_atr": round(current_atr, 2),
                "target_atr": DEFAULT_ATR,
                "multiplier": round(vol_mult, 4),
            },
            "circuit_breaker": {
                "tier": breaker.get("tier", "UNKNOWN") if breaker else "UNKNOWN",
                "multiplier": breaker_mult,
                "max_contracts": breaker_max,
            },
            "correlation": {
                "multiplier": corr_mult,
                "existing_positions": len(existing_positions),
            },
        },
        "gates": {
            "confidence_gate": gate_reason,
            "confidence_value": round(raw_confidence, 4),
            "min_confidence": MIN_CONFIDENCE,
        },
        "limits": {
            "max_contracts_mnq": MAX_CONTRACTS_MNQ,
            "max_contracts_nq": MAX_CONTRACTS_NQ,
            "breaker_max": breaker_max,
            "instrument": instrument,
            "point_value": point_value,
        },
        "regime": vol_regime,
        "errors": [],
    }

    return result


def _write_output(signal: Dict, state_dir: Path) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    output_file = state_dir / OUTPUT_NAME
    with open(output_file, "w") as f:
        json.dump(signal, f, indent=2)
    print(f"Written to {output_file}", file=sys.stderr)


# ── CLI ────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Position Sizing Engine — Multi-Factor Contract Calculation"
    )
    parser.add_argument(
        "--state-dir", type=str, default=None,
        help=f"Path to state directory (default: {DEFAULT_STATE_DIR})"
    )
    parser.add_argument(
        "--balance", type=float, default=None,
        help="Account balance override"
    )
    args = parser.parse_args()

    state_dir = Path(args.state_dir) if args.state_dir else DEFAULT_STATE_DIR

    result = compute_sizing(state_dir, balance_override=args.balance)

    print(json.dumps(result, indent=2))
    _write_output(result, state_dir)


if __name__ == "__main__":
    main()
