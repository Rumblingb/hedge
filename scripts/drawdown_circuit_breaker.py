#!/usr/bin/env python3
"""
Drawdown Circuit Breaker — Multi-Tier Progressive Risk Degradation
===================================================================

Replaces the binary block/pass checks in brain_cortex.run_risk_council()
with a stateful, progressive tier system that adapts to equity, tracks
cooldowns, and provides structured degradation.

Tiers (escalating severity):
  GREEN  — Normal operation. Full sizing.
  YELLOW — Caution. 75% sizing multiplier.
  ORANGE — Warning. 40% sizing multiplier.
  RED    — Danger. 15% sizing multiplier, single contract only.
  BLACK  — Kill switch. All trading halted.

Inputs:
  - trade-journal.jsonl (realized P&L)
  - risk-state.json (existing guardrail state)
  - Account balance (from Topstep API or env)

Outputs:
  - drawdown-circuit-breaker.latest.json (consumed by brain_cortex)

Usage:
    python3 drawdown_circuit_breaker.py [--state-dir PATH] [--balance AMOUNT]
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_STATE_DIR = Path(
    os.environ.get("BILL_STATE_DIR", os.path.expanduser("~/hedge/.rumbling-hedge/state"))
).expanduser()
JOURNAL_NAME = "trade-journal.jsonl"
RISK_STATE_NAME = "risk-state.json"
OUTPUT_NAME = "drawdown-circuit-breaker.latest.json"

# ── Tier Definitions ──────────────────────────────────────────────────────
# Thresholds are fractions of account equity (dynamic) or absolute USD (fallback).

TIER_GREEN = "GREEN"
TIER_YELLOW = "YELLOW"
TIER_ORANGE = "ORANGE"
TIER_RED = "RED"
TIER_BLACK = "BLACK"

# Sizing multiplier per tier
TIER_MULTIPLIERS = {
    TIER_GREEN: 1.0,
    TIER_YELLOW: 0.75,
    TIER_ORANGE: 0.40,
    TIER_RED: 0.15,
    TIER_BLACK: 0.0,
}

# Max contracts per tier
TIER_MAX_CONTRACTS = {
    TIER_GREEN: 3,
    TIER_YELLOW: 2,
    TIER_ORANGE: 1,
    TIER_RED: 1,
    TIER_BLACK: 0,
}

# Cooldown minutes after tier change (forced pause)
TIER_COOLDOWN_MINUTES = {
    TIER_GREEN: 0,
    TIER_YELLOW: 15,
    TIER_ORANGE: 30,
    TIER_RED: 60,
    TIER_BLACK: 0,  # permanent until manual reset
}

# Default account settings (overridden by risk-state.json or --balance)
DEFAULT_BALANCE = 100_000.0
DEFAULT_DAILY_LOSS_LIMIT = 500.0
DEFAULT_CUMULATIVE_LOSS_LIMIT = 2_000.0
POINT_VALUE_MNQ = 2.0  # $2 per point per MNQ contract


# ── Helpers ────────────────────────────────────────────────────────────────

def _load_json(path: Path) -> Optional[Dict]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _load_journal(state_dir: Path) -> List[Dict]:
    """Load all trades from the journal."""
    journal_path = state_dir / JOURNAL_NAME
    if not journal_path.exists():
        return []
    trades = []
    for line in journal_path.read_text().strip().splitlines():
        try:
            trades.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return trades


def _is_today_et(ts_str: str) -> bool:
    """Check if a UTC timestamp falls on today's date in Eastern Time."""
    try:
        ts = datetime.fromisoformat(ts_str)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        # ET is UTC-4 (EDT) or UTC-5 (EST). Use -4 as default.
        et = ts + timedelta(hours=-4)
        now_et = datetime.now(timezone.utc) + timedelta(hours=-4)
        return et.date() == now_et.date()
    except (ValueError, TypeError):
        return False


def _compute_daily_pnl(trades: List[Dict]) -> float:
    """Sum PnL for today's trades (in USD)."""
    total = 0.0
    for t in trades:
        if _is_today_et(t.get("exit_ts", t.get("entry_ts", ""))):
            total += float(t.get("pnl_dollars", 0))
    return total


def _compute_daily_trade_count(trades: List[Dict]) -> int:
    """Count today's trades."""
    return sum(1 for t in trades if _is_today_et(t.get("exit_ts", t.get("entry_ts", ""))))


def _compute_consecutive_losses(trades: List[Dict]) -> int:
    """Count consecutive losses from most recent trade backward."""
    count = 0
    for t in reversed(trades):
        pnl = float(t.get("pnl_dollars", 0))
        if pnl < 0:
            count += 1
        else:
            break
    return count


def _compute_cumulative_pnl(trades: List[Dict]) -> float:
    """Sum PnL across all trades in journal."""
    return sum(float(t.get("pnl_dollars", 0)) for t in trades)


def _compute_max_drawdown(trades: List[Dict]) -> float:
    """Compute the maximum peak-to-trough drawdown in USD from trade sequence."""
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for t in trades:
        equity += float(t.get("pnl_dollars", 0))
        peak = max(peak, equity)
        dd = peak - equity
        max_dd = max(max_dd, dd)
    return max_dd


def _compute_session_stats(trades: List[Dict]) -> Dict[str, Dict]:
    """Compute per-session P&L stats for today."""
    sessions: Dict[str, Dict] = {}
    for t in trades:
        if not _is_today_et(t.get("exit_ts", t.get("entry_ts", ""))):
            continue
        sess = t.get("session", "UNKNOWN")
        if sess not in sessions:
            sessions[sess] = {"pnl": 0.0, "trades": 0, "losses": 0}
        sessions[sess]["pnl"] += float(t.get("pnl_dollars", 0))
        sessions[sess]["trades"] += 1
        if float(t.get("pnl_dollars", 0)) < 0:
            sessions[sess]["losses"] += 1
    return sessions


def _compute_win_rate(trades: List[Dict], window: int = 20) -> float:
    """Win rate over the last N trades."""
    recent = trades[-window:] if len(trades) >= window else trades
    if not recent:
        return 0.0
    wins = sum(1 for t in recent if float(t.get("pnl_dollars", 0)) > 0)
    return wins / len(recent)


def _compute_avg_win_loss(trades: List[Dict], window: int = 20) -> Tuple[float, float]:
    """Average win and average loss over last N trades."""
    recent = trades[-window:] if len(trades) >= window else trades
    wins = [float(t.get("pnl_dollars", 0)) for t in recent if float(t.get("pnl_dollars", 0)) > 0]
    losses = [abs(float(t.get("pnl_dollars", 0))) for t in recent if float(t.get("pnl_dollars", 0)) < 0]
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0
    return avg_win, avg_loss


# ── Tier Classification ────────────────────────────────────────────────────

def classify_tier(
    balance: float,
    daily_pnl: float,
    cumulative_pnl: float,
    max_drawdown: float,
    consecutive_losses: int,
    win_rate: float,
    daily_trades: int,
    daily_loss_limit: float,
    cumulative_loss_limit: float,
    emergency_stop_active: bool = False,
) -> Tuple[str, str]:
    """Determine the current circuit breaker tier and reason.
    
    Returns: (tier, reason)
    """
    # ── BLACK tier checks ──
    # Emergency stop file
    if emergency_stop_active:
        return TIER_BLACK, "EMERGENCY_STOP file present"

    # Cumulative loss limit breached
    if cumulative_pnl <= -cumulative_loss_limit:
        return TIER_BLACK, f"Cumulative loss limit: ${cumulative_pnl:.0f} <= -${cumulative_loss_limit:.0f}"

    # Daily loss limit breached
    if daily_pnl <= -daily_loss_limit:
        return TIER_BLACK, f"Daily loss limit: ${daily_pnl:.0f} <= -${daily_loss_limit:.0f}"

    # 10% equity drawdown
    equity_dd_pct = max_drawdown / balance if balance > 0 else 0
    if equity_dd_pct >= 0.10:
        return TIER_BLACK, f"10% equity drawdown: {equity_dd_pct:.1%}"

    # ── RED tier checks ──
    if consecutive_losses >= 3:
        return TIER_RED, f"{consecutive_losses} consecutive losses"

    # Daily PnL near limit (80% consumed)
    if daily_pnl <= -(daily_loss_limit * 0.80):
        return TIER_RED, f"Daily PnL near limit: ${daily_pnl:.0f} (80% of -${daily_loss_limit:.0f})"

    # Win rate below 35% over last 20 trades (edge deterioration)
    if len(trades_global) >= 10 and win_rate < 0.35:
        return TIER_RED, f"Win rate decay: {win_rate:.1%} over last 20 trades"

    # 5% equity drawdown
    if equity_dd_pct >= 0.05:
        return TIER_RED, f"5% equity drawdown: {equity_dd_pct:.1%}"

    # ── ORANGE tier checks ──
    if consecutive_losses >= 2:
        return TIER_ORANGE, f"{consecutive_losses} consecutive losses"

    # Daily PnL moderate loss (50% consumed)
    if daily_pnl <= -(daily_loss_limit * 0.50):
        return TIER_ORANGE, f"Daily PnL moderate: ${daily_pnl:.0f} (50% of -${daily_loss_limit:.0f})"

    # Win rate below 45%
    if len(trades_global) >= 10 and win_rate < 0.45:
        return TIER_ORANGE, f"Win rate declining: {win_rate:.1%}"

    # 3% equity drawdown
    if equity_dd_pct >= 0.03:
        return TIER_ORANGE, f"3% equity drawdown: {equity_dd_pct:.1%}"

    # Overtrading
    if daily_trades >= 5:
        return TIER_ORANGE, f"Overtrading: {daily_trades} trades today"

    # ── YELLOW tier checks ──
    if daily_pnl <= -(daily_loss_limit * 0.25):
        return TIER_YELLOW, f"Daily PnL caution: ${daily_pnl:.0f} (25% of -${daily_loss_limit:.0f})"

    if daily_trades >= 3:
        return TIER_YELLOW, f"Elevated trade count: {daily_trades} trades"

    # 1.5% equity drawdown
    if equity_dd_pct >= 0.015:
        return TIER_YELLOW, f"1.5% equity drawdown: {equity_dd_pct:.1%}"

    # ── GREEN ──
    return TIER_GREEN, "All clear"


# ── Cooldown Tracking ──────────────────────────────────────────────────────

def _load_coolback_state(state_dir: Path) -> Dict:
    """Load previous circuit breaker state for cooldown comparison."""
    path = state_dir / OUTPUT_NAME
    prev = _load_json(path)
    return prev if prev else {}


def _is_in_cooldown(prev_state: Dict, current_tier: str, now: datetime) -> Tuple[bool, str]:
    """Check if we're in cooldown from a recent tier escalation."""
    prev_tier = prev_state.get("tier", TIER_GREEN)
    prev_changed = prev_state.get("tier_changed_utc")

    if not prev_changed:
        return False, ""

    # Only cooldown if tier escalated (higher severity)
    tier_order = [TIER_GREEN, TIER_YELLOW, TIER_ORANGE, TIER_RED, TIER_BLACK]
    prev_idx = tier_order.index(prev_tier) if prev_tier in tier_order else 0
    curr_idx = tier_order.index(current_tier) if current_tier in tier_order else 0

    if curr_idx <= prev_idx:
        return False, ""  # No escalation, no cooldown

    try:
        changed_at = datetime.fromisoformat(prev_changed)
        if changed_at.tzinfo is None:
            changed_at = changed_at.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return False, ""

    cooldown_minutes = TIER_COOLDOWN_MINUTES.get(current_tier, 0)
    if cooldown_minutes <= 0:
        return False, ""

    cooldown_end = changed_at + timedelta(minutes=cooldown_minutes)
    if now < cooldown_end:
        remaining = (cooldown_end - now).total_seconds() / 60
        return True, f"Cooldown active: {remaining:.0f}m remaining (escalated to {current_tier})"

    return False, ""


# ── Recovery Logic ─────────────────────────────────────────────────────────

def _compute_recovery_boost(prev_tier: str, consecutive_wins: int) -> float:
    """After a severe tier, consecutive wins should gradually restore sizing.
    
    Returns a boost multiplier (0.0 to 1.0) that's OR'd with the tier multiplier.
    """
    if consecutive_wins <= 0:
        return 0.0
    # Each win restores 10% of the lost multiplier
    return min(consecutive_wins * 0.10, 0.50)


def _count_consecutive_wins(trades: List[Dict]) -> int:
    """Count consecutive wins from most recent trade backward."""
    count = 0
    for t in reversed(trades):
        pnl = float(t.get("pnl_dollars", 0))
        if pnl > 0:
            count += 1
        else:
            break
    return count


# ── Main Logic ─────────────────────────────────────────────────────────────

trades_global: List[Dict] = []  # Module-level for tier classification access


def compute_breaker(state_dir: Path, balance_override: Optional[float] = None) -> Dict:
    """Compute the full circuit breaker state."""
    global trades_global

    now = datetime.now(timezone.utc)

    # Load data
    journal = _load_journal(state_dir)
    trades_global = journal
    risk_state = _load_json(state_dir / RISK_STATE_NAME)

    # Determine account balance
    balance = balance_override
    if balance is None and risk_state:
        # Try to infer from risk state or use default
        balance = DEFAULT_BALANCE
    
    if balance is None:
        balance = DEFAULT_BALANCE

    # Read limits from risk state or defaults
    limits = {}
    if risk_state and "limits" in risk_state:
        limits = risk_state["limits"]

    daily_loss_limit = limits.get("daily_loss_usd", DEFAULT_DAILY_LOSS_LIMIT)
    cumulative_loss_limit = limits.get("cumulative_loss_usd", DEFAULT_CUMULATIVE_LOSS_LIMIT)

    # Compute metrics
    daily_pnl = _compute_daily_pnl(journal)
    cumulative_pnl = _compute_cumulative_pnl(journal)
    max_drawdown = _compute_max_drawdown(journal)
    consecutive_losses = _compute_consecutive_losses(journal)
    consecutive_wins = _count_consecutive_wins(journal)
    daily_trades = _compute_daily_trade_count(journal)
    win_rate = _compute_win_rate(journal)
    avg_win, avg_loss = _compute_avg_win_loss(journal)
    session_stats = _compute_session_stats(journal)

    # Classify tier
    tier, reason = classify_tier(
        balance=balance,
        daily_pnl=daily_pnl,
        cumulative_pnl=cumulative_pnl,
        max_drawdown=max_drawdown,
        consecutive_losses=consecutive_losses,
        win_rate=win_rate,
        daily_trades=daily_trades,
        daily_loss_limit=daily_loss_limit,
        cumulative_loss_limit=cumulative_loss_limit,
        emergency_stop_active=(state_dir / "EMERGENCY_STOP").exists(),
    )

    # Check cooldown from escalation
    prev_state = _load_coolback_state(state_dir)
    in_cooldown, cooldown_reason = _is_in_cooldown(prev_state, tier, now)

    # Recovery boost (after hitting orange/red, wins gradually restore)
    prev_tier = prev_state.get("tier", TIER_GREEN)
    recovery_boost = _compute_recovery_boost(prev_tier, consecutive_wins)

    # Compute effective multiplier
    base_mult = TIER_MULTIPLIERS[tier]
    effective_mult = base_mult + (recovery_boost * (1.0 - base_mult))

    # If in cooldown, cap at previous tier's multiplier
    if in_cooldown:
        prev_mult = TIER_MULTIPLIERS.get(prev_tier, 1.0)
        effective_mult = min(effective_mult, prev_mult)

    # Max contracts for current tier
    max_contracts = TIER_MAX_CONTRACTS[tier]

    # Daily loss budget remaining
    daily_budget_remaining = max(0, daily_loss_limit + daily_pnl)  # daily_pnl is negative on loss
    daily_budget_pct = (daily_budget_remaining / daily_loss_limit * 100) if daily_loss_limit > 0 else 100

    # Build output
    result = {
        "timestamp": now.isoformat(),
        "tier": tier,
        "reason": reason,
        "sizing_multiplier": round(effective_mult, 4),
        "max_contracts": max_contracts,
        "cooldown_active": in_cooldown,
        "cooldown_reason": cooldown_reason,
        "recovery_boost": round(recovery_boost, 4),
        "metrics": {
            "balance": round(balance, 2),
            "daily_pnl": round(daily_pnl, 2),
            "cumulative_pnl": round(cumulative_pnl, 2),
            "max_drawdown_usd": round(max_drawdown, 2),
            "max_drawdown_pct": round(max_drawdown / balance * 100, 2) if balance > 0 else 0,
            "consecutive_losses": consecutive_losses,
            "consecutive_wins": consecutive_wins,
            "daily_trades": daily_trades,
            "win_rate": round(win_rate, 4),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "payoff_ratio": round(avg_win / avg_loss, 2) if avg_loss > 0 else 0,
            "daily_budget_remaining": round(daily_budget_remaining, 2),
            "daily_budget_pct": round(daily_budget_pct, 1),
        },
        "limits": {
            "daily_loss_usd": daily_loss_limit,
            "cumulative_loss_usd": cumulative_loss_limit,
            "max_trades_per_day": limits.get("max_trades_per_day", 5),
        },
        "sessions_today": session_stats,
        "tier_history": {
            "previous_tier": prev_tier,
            "tier_changed_utc": prev_state.get("tier_changed_utc"),
            "escalated": tier != prev_tier,
        },
    }

    return result


def _write_output(signal: Dict, state_dir: Path, prev_tier: str) -> None:
    """Write output and update tier change timestamp if needed."""
    state_dir.mkdir(parents=True, exist_ok=True)
    output_file = state_dir / OUTPUT_NAME

    # Update tier change timestamp on escalation/de-escalation
    if signal["tier"] != prev_tier:
        signal["tier_history"]["tier_changed_utc"] = signal["timestamp"]

    with open(output_file, "w") as f:
        json.dump(signal, f, indent=2)

    print(f"Written to {output_file}", file=sys.stderr)


# ── CLI ────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Drawdown Circuit Breaker — Progressive Risk Degradation"
    )
    parser.add_argument(
        "--state-dir", type=str, default=None,
        help=f"Path to state directory (default: {DEFAULT_STATE_DIR})"
    )
    parser.add_argument(
        "--balance", type=float, default=None,
        help="Account balance override (default: from risk-state.json or $100K)"
    )
    args = parser.parse_args()

    state_dir = Path(args.state_dir) if args.state_dir else DEFAULT_STATE_DIR

    # Read previous tier for comparison
    prev_state = _load_coolback_state(state_dir)
    prev_tier = prev_state.get("tier", TIER_GREEN)

    result = compute_breaker(state_dir, balance_override=args.balance)

    # Print to stdout
    print(json.dumps(result, indent=2))

    # Write to state file
    _write_output(result, state_dir, prev_tier)


if __name__ == "__main__":
    main()
