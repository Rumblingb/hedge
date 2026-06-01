#!/usr/bin/env python3
"""
vol_noise_scalp.py — Misango Vol-Targeted Noise Area Breakout for NQ/ES

Based on: "Intraday Momentum Breakout Strategy: A Volatility-Targeted Approach
to E-mini Futures Trading" (Misango, 2026, Arithmax Research)

KEY PARAMETERS (from paper):
  Noise Area:    UB = price + P75(intraday_range_lookback)
                 LB = price - P25(intraday_range_lookback)
                 intraday_range = H - L (high-low range per bar)
  Lookback:      90 days (paper), adapted to available data
  Confirmation:  τ = 2 bars (price must stay beyond boundary for 2 bars)
  Volume:        V_t > P50(rolling 20-bar volume) — volume threshold
  Trend Filter:  Optional 50-period MA alignment
  Target Vol:    3% daily portfolio volatility
  Position Size: N = (σ_target × w × V_portfolio) / (σ_instrument × C_value)
  Leverage:      [1x, 8x] bounds
  Session:       9:30 AM - 3:00 PM ET (paper) → adapted for London/Asia/NY
  Exit:          Session close (mandatory), momentum failure (re-entry into noise
                 area after 3-bar min hold), max 78 bars, optional trailing stop
  Transaction:   1 tick slippage/side. ES=$12.50/tick, NQ=$5.00/tick.
                 Commission $4.20/RT contract.

OUR ADAPTATION (3 MNQ max, London/Asia/NY):
  - Noise Area as breakout filter for session scalps
  - Vol targeting for position sizing (cap at 3 MNQ)
  - Session-aware vol targets (Asia lower, London/NY higher)
  - Scale-out: TP1/TP2/trail

Usage:
  python3 vol_noise_scalp.py [--csv PATH] [--symbol NQ|ES] [--tf 5|15|30|60]
                             [--lookback-bars N] [--dry-run]
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

# === CONSTANTS ===
ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.environ.get("BILL_DATA_DIR") or (ROOT / "data" / "free"))
STATE_DIR = Path(os.environ.get("BILL_STATE_DIR") or os.environ.get("RH_STATE_DIR") or (ROOT / ".rumbling-hedge" / "state"))
TICK_VALUES = {"ES": 12.50, "NQ": 5.00, "MNQ": 0.50}
COMMISSION_RT = 4.20  # per contract round-trip
TARGET_VOL_DAILY = 0.03  # 3% daily
MAX_LEVERAGE = 8.0
MIN_LEVERAGE = 1.0
MAX_CONTRACTS_MNQ = 3  # our constraint (Topstep 100K)
MAX_DAILY_LOSS_PCT = 0.05  # 5%
MIN_HOLD_BARS = 3
MAX_HOLD_BARS = 78
CONFIRMATION_BARS = 2  # tau = 2

# Session windows in UTC
SESSIONS = {
    "asia":   {"start_h": 0,  "start_m": 0,  "end_h": 7,  "end_m": 0},   # 00:00-07:00 UTC
    "london": {"start_h": 7,  "start_m": 0,  "end_h": 13, "end_m": 30},  # 07:00-13:30 UTC
    "ny":     {"start_h": 13, "start_m": 30, "end_h": 20, "end_m": 0},   # 13:30-20:00 UTC
}

# Session-specific vol multipliers (Asia quieter)
SESSION_VOL_MULT = {"asia": 0.6, "london": 1.0, "ny": 1.2}


def safety_metadata(reason: str = "research-only-backtest") -> dict:
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


def load_data(csv_path: str, symbol: str) -> pd.DataFrame:
    """Load CSV, filter by symbol, parse timestamps."""
    df = pd.read_csv(csv_path, parse_dates=["ts"])
    df = df[df["symbol"] == symbol].copy()
    df = df.sort_values("ts").reset_index(drop=True)
    df["date"] = df["ts"].dt.date
    df["hour_utc"] = df["ts"].dt.hour
    df["minute_utc"] = df["ts"].dt.minute
    return df


def compute_noise_area(df: pd.DataFrame, lookback_bars: int) -> pd.DataFrame:
    """
    Compute Noise Area boundaries per Misango Eq (1):
      UB_t = p_t + P75(intraday_range_{t-LB:t})
      LB_t = p_t - P25(intraday_range_{t-LB:t})
    where intraday_range = high - low

    KEY INSIGHT: The boundary at time t is SET at t, but breakouts are
    detected by comparing FUTURE prices (at t+τ) against this historical
    boundary. So we also precompute ub_ref and lb_ref = the boundary
    referenced τ bars in the past, which is what signal generation compares against.
    """
    df = df.copy()
    df["intraday_range"] = df["high"] - df["low"]

    min_periods = max(20, lookback_bars // 3)

    # Rolling percentiles over lookback window
    df["range_p75"] = df["intraday_range"].rolling(lookback_bars, min_periods=min_periods).quantile(0.75)
    df["range_p25"] = df["intraday_range"].rolling(lookback_bars, min_periods=min_periods).quantile(0.25)

    # Noise area boundaries (current — for display/exit reference)
    df["ub"] = df["close"] + df["range_p75"]
    df["lb"] = df["close"] - df["range_p25"]
    df["noise_width"] = df["range_p75"] + df["range_p25"]

    # Historical boundaries for breakout detection (τ bars ago)
    tau = CONFIRMATION_BARS
    df["ub_ref"] = df["close"].shift(tau) + df["range_p75"].shift(tau)
    df["lb_ref"] = df["close"].shift(tau) - df["range_p25"].shift(tau)

    return df


def compute_volume_threshold(df: pd.DataFrame, vol_lookback: int = 20) -> pd.DataFrame:
    """Volume threshold: P50 of rolling 20-bar volume."""
    df = df.copy()
    df["vol_p50"] = df["volume"].rolling(vol_lookback, min_periods=5).median()
    return df


def compute_trend_filter(df: pd.DataFrame, ma_period: int = 50) -> pd.DataFrame:
    """Optional 50-period MA trend filter."""
    df = df.copy()
    df["ma50"] = df["close"].rolling(ma_period, min_periods=ma_period).mean()
    df["trend_up"] = df["close"] > df["ma50"]
    df["trend_down"] = df["close"] < df["ma50"]
    return df


def compute_ewma_vol(df: pd.DataFrame, span: int = 20) -> pd.DataFrame:
    """EWMA volatility (20-bar span) for position sizing."""
    df = df.copy()
    df["returns"] = df["close"].pct_change()
    df["ewma_vol"] = df["returns"].ewm(span=span).std()
    return df


def detect_session(hour_utc: int, minute_utc: int) -> str:
    """Classify bar into session."""
    t = hour_utc * 60 + minute_utc
    for name, win in SESSIONS.items():
        start = win["start_h"] * 60 + win["start_m"]
        end = win["end_h"] * 60 + win["end_m"]
        if start <= t < end:
            return name
    return "off_session"


def generate_signals(df: pd.DataFrame, use_trend_filter: bool = True,
                     use_volume_filter: bool = True) -> pd.DataFrame:
    """
    Generate Misango signals per Eq (2):
      +1 if close_{t-τ:t} > UB_ref (historical boundary set τ bars ago) AND V_t > V_th
      -1 if close_{t-τ:t} < LB_ref AND V_t > V_th
       0 otherwise

    KEY: UB_ref is computed as close_{t-τ} + P75(range_{t-τ}), which is the
    boundary that was set τ bars in the past. Price must break through this
    historical boundary and STAY above for τ bars (confirmation).
    """
    df = df.copy()
    df["signal_raw"] = 0

    tau = CONFIRMATION_BARS
    start_idx = tau + 1  # need at least tau+1 bars before signal

    for i in range(start_idx, len(df)):
        # The reference boundary was set tau bars ago
        ub_val = df.iloc[i - tau].get("ub_ref", np.nan)
        lb_val = df.iloc[i - tau].get("lb_ref", np.nan)

        if pd.isna(ub_val) or pd.isna(lb_val):
            continue

        # Require all closes from (i-tau) through i to be beyond the boundary
        closes = df.iloc[i - tau:i + 1]["close"].values

        # LONG: all closes above ub_ref
        if all(c > ub_val for c in closes):
            if use_volume_filter:
                vol_th = df.iloc[i].get("vol_p50", 0)
                if not pd.isna(vol_th) and vol_th > 0:
                    if df.iloc[i]["volume"] <= vol_th:
                        continue
            if use_trend_filter:
                if not df.iloc[i].get("trend_up", True):
                    continue
            df.iloc[i, df.columns.get_loc("signal_raw")] = 1

        # SHORT: all closes below lb_ref
        elif all(c < lb_val for c in closes):
            if use_volume_filter:
                vol_th = df.iloc[i].get("vol_p50", 0)
                if not pd.isna(vol_th) and vol_th > 0:
                    if df.iloc[i]["volume"] <= vol_th:
                        continue
            if use_trend_filter:
                if not df.iloc[i].get("trend_down", True):
                    continue
            df.iloc[i, df.columns.get_loc("signal_raw")] = -1

    return df


def position_sizing(df: pd.DataFrame, portfolio_value: float,
                    symbol: str, max_contracts: int = MAX_CONTRACTS_MNQ) -> pd.DataFrame:
    """
    Volatility-targeted position sizing per Misango Eq (3):
      N = (σ_target × capital) / (σ_instrument × C_value)
    Capped at max_contracts.
    """
    df = df.copy()
    df["contracts"] = 0

    multiplier = 2.0 if symbol == "NQ" else 50.0  # NQ=$20/pt but we use MNQ=2pt
    if symbol == "NQ":
        multiplier = 2.0  # MNQ multiplier ($2/point)

    for i in range(len(df)):
        if df.iloc[i]["signal_raw"] == 0:
            continue
        ewma_v = df.iloc[i].get("ewma_vol", None)
        if ewma_v is None or pd.isna(ewma_v) or ewma_v <= 0:
            df.iloc[i, df.columns.get_loc("contracts")] = 1
            continue

        # σ_instrument in dollar terms
        price = df.iloc[i]["close"]
        contract_value = price * multiplier
        sigma_dollar = ewma_v * contract_value  # daily $ vol per contract

        if sigma_dollar <= 0:
            n = 1
        else:
            n = (TARGET_VOL_DAILY * portfolio_value) / sigma_dollar

        # Apply leverage bounds
        leverage = (n * contract_value) / portfolio_value
        if leverage > MAX_LEVERAGE:
            n = (MAX_LEVERAGE * portfolio_value) / contract_value
        elif leverage < MIN_LEVERAGE:
            n = max(1, (MIN_LEVERAGE * portfolio_value) / contract_value)

        # Hard cap
        n = min(int(round(n)), max_contracts)
        n = max(1, n)
        df.iloc[i, df.columns.get_loc("contracts")] = n

    return df


def backtest_simple(df: pd.DataFrame, symbol: str, tick_value: float = None) -> dict:
    """
    Backtest with proper exit management:
    1. Stop loss: entry price - 1.5x noise_width (for longs), +1.5x for shorts
    2. Profit target: entry price + 2x noise_width (paper's optional exit)
    3. Trailing stop: 0.5% trailing (paper's option 4)
    4. Max hold: MAX_HOLD_BARS (force exit)
    5. Opposite signal: close and reverse

    Transaction costs: 1 tick slippage/side + commission.
    """
    if tick_value is None:
        tick_value = TICK_VALUES.get(symbol, 5.0)

    trades = []
    position = None  # {entry_idx, direction, contracts, entry_price, entry_noise_width, peak_price}

    SL_MULT = 1.5   # Stop at 1.5x noise width
    TP_MULT = 2.0   # Take profit at 2x noise width
    TRAIL_PCT = 0.005  # 0.5% trailing stop (per paper)

    for i in range(len(df)):
        row = df.iloc[i]
        if position is not None:
            bars_held = i - position["entry_idx"]
            direction = position["direction"]
            entry_price = position["entry_price"]
            noise_w = position["entry_noise_width"]
            peak = position["peak_price"]

            # Update peak/trough for trailing stop
            if direction == 1:
                peak = max(peak, row["high"])
                position["peak_price"] = peak
            else:
                peak = min(peak, row["low"])
                position["peak_price"] = peak

            exit_price = None
            exit_reason = None

            # 1. Stop loss
            if direction == 1:
                sl_price = entry_price - SL_MULT * noise_w
                if row["low"] <= sl_price:
                    exit_price = sl_price
                    exit_reason = "stop_loss"
            else:
                sl_price = entry_price + SL_MULT * noise_w
                if row["high"] >= sl_price:
                    exit_price = sl_price
                    exit_reason = "stop_loss"

            # 2. Take profit (2x noise width)
            if exit_reason is None:
                if direction == 1:
                    tp_price = entry_price + TP_MULT * noise_w
                    if row["high"] >= tp_price:
                        exit_price = tp_price
                        exit_reason = "take_profit"
                else:
                    tp_price = entry_price - TP_MULT * noise_w
                    if row["low"] <= tp_price:
                        exit_price = tp_price
                        exit_reason = "take_profit"

            # 3. Trailing stop (0.5% from peak) - only after min hold
            if exit_reason is None and bars_held >= MIN_HOLD_BARS:
                if direction == 1:
                    trail_price = peak * (1 - TRAIL_PCT)
                    if row["low"] <= trail_price and peak > entry_price:
                        exit_price = trail_price
                        exit_reason = "trailing_stop"
                else:
                    trail_price = peak * (1 + TRAIL_PCT)
                    if row["high"] >= trail_price and peak < entry_price:
                        exit_price = trail_price
                        exit_reason = "trailing_stop"

            # 4. Max hold
            if exit_reason is None and bars_held >= MAX_HOLD_BARS:
                exit_price = row["close"]
                exit_reason = "max_hold"

            # 5. Opposite signal
            if exit_reason is None and row["signal_raw"] != 0 and row["signal_raw"] != direction:
                exit_price = row["close"]
                exit_reason = "opposite_signal"

            if exit_price is not None:
                contracts = position["contracts"]
                # Slippage: 1 tick per side (adverse)
                if direction == 1:
                    eff_entry = entry_price - tick_value
                    eff_exit = exit_price - tick_value
                else:
                    eff_entry = entry_price + tick_value
                    eff_exit = exit_price + tick_value

                pnl_points = direction * (eff_exit - eff_entry)
                multiplier = 2.0 if symbol == "NQ" else 50.0
                pnl_dollar = pnl_points * multiplier * contracts
                commission = COMMISSION_RT * contracts
                net_pnl = pnl_dollar - commission

                trades.append({
                    "entry_idx": position["entry_idx"],
                    "exit_idx": i,
                    "entry_ts": df.iloc[position["entry_idx"]]["ts"],
                    "exit_ts": row["ts"],
                    "direction": direction,
                    "contracts": contracts,
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "bars_held": bars_held,
                    "exit_reason": exit_reason,
                    "pnl_points": round(pnl_points, 2),
                    "pnl_dollar": round(net_pnl, 2),
                    "session": position.get("session", "unknown"),
                    "noise_width": round(noise_w, 2),
                })
                position = None

        # Entry
        if position is None and row["signal_raw"] != 0:
            session = detect_session(row["hour_utc"], row["minute_utc"])
            if session == "off_session":
                continue
            noise_w = row.get("noise_width", 0)
            if pd.isna(noise_w) or noise_w <= 0:
                noise_w = 30.0  # fallback default
            position = {
                "entry_idx": i,
                "direction": int(row["signal_raw"]),
                "contracts": int(row.get("contracts", 1)),
                "entry_price": row["close"],
                "entry_noise_width": float(noise_w),
                "peak_price": row["close"],
                "session": session,
            }

    # Close open position at end
    if position is not None:
        last = df.iloc[-1]
        direction = position["direction"]
        contracts = position["contracts"]
        entry_price = position["entry_price"]
        exit_price = last["close"]
        pnl_points = direction * (exit_price - entry_price)
        multiplier = 2.0 if symbol == "NQ" else 50.0
        pnl_dollar = pnl_points * multiplier * contracts
        commission = COMMISSION_RT * contracts
        trades.append({
            "entry_idx": position["entry_idx"],
            "exit_idx": len(df) - 1,
            "entry_ts": df.iloc[position["entry_idx"]]["ts"],
            "exit_ts": last["ts"],
            "direction": direction,
            "contracts": contracts,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "bars_held": len(df) - 1 - position["entry_idx"],
            "exit_reason": "end_of_data",
            "pnl_points": round(pnl_points, 2),
            "pnl_dollar": round(pnl_dollar - commission, 2),
            "session": position.get("session", "unknown"),
            "noise_width": round(position["entry_noise_width"], 2),
        })

    return trades


def compute_metrics(trades: list, portfolio_value: float = 100000) -> dict:
    """Compute performance metrics from trade list."""
    if not trades:
        return {"total_trades": 0, "wr": 0, "total_pnl": 0, "sharpe": 0,
                "max_dd": 0, "avg_pnl": 0, "profit_factor": 0}

    tdf = pd.DataFrame(trades)
    winners = tdf[tdf["pnl_dollar"] > 0]
    losers = tdf[tdf["pnl_dollar"] <= 0]

    total_pnl = tdf["pnl_dollar"].sum()
    wr = len(winners) / len(tdf) * 100
    avg_win = winners["pnl_dollar"].mean() if len(winners) > 0 else 0
    avg_loss = losers["pnl_dollar"].mean() if len(losers) > 0 else 0
    gross_profit = winners["pnl_dollar"].sum() if len(winners) > 0 else 0
    gross_loss = abs(losers["pnl_dollar"].sum()) if len(losers) > 0 else 0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    # Equity curve for drawdown + sharpe
    equity = [portfolio_value]
    for t in trades:
        equity.append(equity[-1] + t["pnl_dollar"])
    equity = np.array(equity)

    # Max drawdown
    peak = np.maximum.accumulate(equity)
    dd = (equity - peak) / peak
    max_dd = dd.min() * 100

    # Sharpe (annualized, assume ~78 bars/day for 5m, scale appropriately)
    returns = np.diff(equity) / equity[:-1]
    if len(returns) > 1 and returns.std() > 0:
        sharpe = (returns.mean() / returns.std()) * np.sqrt(252 * 78)  # rough annualization for 5m
    else:
        sharpe = 0

    # R-multiple: PnL / ATR at entry (approximate with noise_width)
    # Session breakdown
    session_stats = {}
    for sess in ["asia", "london", "ny"]:
        sess_trades = tdf[tdf["session"] == sess]
        if len(sess_trades) > 0:
            session_stats[sess] = {
                "trades": len(sess_trades),
                "pnl": round(sess_trades["pnl_dollar"].sum(), 2),
                "wr": round(len(sess_trades[sess_trades["pnl_dollar"] > 0]) / len(sess_trades) * 100, 1),
            }

    # Long vs short
    longs = tdf[tdf["direction"] == 1]
    shorts = tdf[tdf["direction"] == -1]

    return {
        "total_trades": len(tdf),
        "long_trades": len(longs),
        "short_trades": len(shorts),
        "long_pnl": round(longs["pnl_dollar"].sum(), 2) if len(longs) > 0 else 0,
        "short_pnl": round(shorts["pnl_dollar"].sum(), 2) if len(shorts) > 0 else 0,
        "wr": round(wr, 1),
        "total_pnl": round(total_pnl, 2),
        "avg_pnl": round(tdf["pnl_dollar"].mean(), 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "profit_factor": round(profit_factor, 2),
        "sharpe_annualized": round(sharpe, 2),
        "max_dd_pct": round(max_dd, 2),
        "avg_bars_held": round(tdf["bars_held"].mean(), 1),
        "sessions": session_stats,
        "exit_reasons": tdf["exit_reason"].value_counts().to_dict(),
    }


def check_data_freshness(csv_path: str, max_age_hours: int = 48) -> dict:
    """Check if data is fresh enough for live signal generation."""
    df = pd.read_csv(csv_path, parse_dates=["ts"], nrows=1)
    # Read last few lines for latest timestamp
    import subprocess
    result = subprocess.run(["tail", "-1", csv_path], capture_output=True, text=True)
    last_line = result.stdout.strip()
    if not last_line or last_line.startswith("ts,"):
        return {"fresh": False, "reason": "Could not read last timestamp"}

    last_ts_str = last_line.split(",")[0]
    try:
        last_ts = pd.Timestamp(last_ts_str, tz="UTC")
    except:
        last_ts = pd.Timestamp(last_ts_str)
        if last_ts.tzinfo is None:
            last_ts = last_ts.tz_localize("UTC")

    now = pd.Timestamp.now(timezone.utc)
    age_hours = (now - last_ts).total_seconds() / 3600

    return {
        "fresh": age_hours < max_age_hours,
        "last_timestamp": str(last_ts),
        "age_hours": round(age_hours, 1),
        "max_age_hours": max_age_hours,
    }


def main():
    parser = argparse.ArgumentParser(description="Misango Vol-Targeted Noise Area Breakout")
    parser.add_argument("--csv", type=str, default=None, help="Path to CSV data file")
    parser.add_argument("--symbol", type=str, default="NQ", choices=["NQ", "ES"], help="Symbol to test")
    parser.add_argument("--tf", type=int, default=15, choices=[5, 15, 30, 60], help="Timeframe (minutes)")
    parser.add_argument("--lookback-bars", type=int, default=None, help="Lookback bars for noise area (auto if not set)")
    parser.add_argument("--portfolio", type=float, default=100000, help="Portfolio value for sizing")
    parser.add_argument("--no-trend-filter", action="store_true", help="Disable 50-MA trend filter")
    parser.add_argument("--no-volume-filter", action="store_true", help="Disable volume confirmation")
    parser.add_argument("--dry-run", action="store_true", help="Only compute noise area, no backtest")
    parser.add_argument("--json", action="store_true", help="Output JSON results")
    args = parser.parse_args()

    # Auto-select CSV if not provided
    if args.csv is None:
        candidates = [
            DATA_DIR / f"ALL-6MARKETS-{args.tf}m-60d.csv",
            DATA_DIR / f"ALL-6MARKETS-{args.tf}m-60d-normalized.csv",
            DATA_DIR / f"{args.symbol}-{args.tf}m-60d.csv",
            DATA_DIR / f"ALL-6MARKETS-{args.tf}m-5d.csv",
        ]
        for c in candidates:
            if c.exists():
                args.csv = str(c)
                break
        if args.csv is None:
            print(f"ERROR: No CSV found for {args.symbol} {args.tf}m. Provide --csv path.")
            sys.exit(1)

    print(f"=== Misango Vol-Targeted Noise Area Scalp ===")
    print(f"Symbol: {args.symbol}  TF: {args.tf}m  CSV: {args.csv}")
    print()

    # Data freshness check
    freshness = check_data_freshness(args.csv, max_age_hours=48)
    print(f"Data freshness: {'FRESH' if freshness['fresh'] else 'STALE'} "
          f"(last: {freshness.get('last_timestamp', '?')}, age: {freshness.get('age_hours', '?')}h)")
    if not freshness["fresh"]:
        print("WARNING: Data is stale (>48h old). Signals not suitable for live execution.")
    print()

    # Load data
    df = load_data(args.csv, args.symbol)
    print(f"Loaded {len(df)} bars of {args.symbol} "
          f"({df['ts'].min()} to {df['ts'].max()})")

    if len(df) < 100:
        print(f"ERROR: Only {len(df)} bars — need at least 100 for noise area calculation.")
        sys.exit(1)

    # Auto lookback: ~90 trading days worth of bars
    bars_per_day = {5: 78, 15: 26, 30: 13, 60: 7}
    if args.lookback_bars is None:
        args.lookback_bars = min(bars_per_day.get(args.tf, 26) * 90, len(df) // 4)
    print(f"Lookback: {args.lookback_bars} bars")
    print()

    # === PHASE 1: Compute indicators ===
    df = compute_noise_area(df, args.lookback_bars)
    df = compute_volume_threshold(df, vol_lookback=20)
    df = compute_trend_filter(df, ma_period=50)
    df = compute_ewma_vol(df, span=20)

    # Latest noise area values
    latest = df.iloc[-1]
    print(f"=== Current Noise Area ({args.symbol}) ===")
    print(f"  Close:  {latest['close']:.2f}")
    print(f"  UB:     {latest['ub']:.2f}  (+{latest['range_p75']:.2f})")
    print(f"  LB:     {latest['lb']:.2f}  (-{latest['range_p25']:.2f})")
    print(f"  Width:  {latest['noise_width']:.2f}")
    print(f"  Range P75 (90d): {latest['range_p75']:.2f}")
    print(f"  Range P25 (90d): {latest['range_p25']:.2f}")
    print(f"  EWMA Vol: {latest.get('ewma_vol', 0):.6f}")
    print(f"  Session: {detect_session(latest['hour_utc'], latest['minute_utc'])}")
    print()

    if args.dry_run:
        print("Dry run — skipping signal generation and backtest.")
        sys.exit(0)

    # === PHASE 2: Generate signals ===
    df = generate_signals(df,
                          use_trend_filter=not args.no_trend_filter,
                          use_volume_filter=not args.no_volume_filter)

    n_long = (df["signal_raw"] == 1).sum()
    n_short = (df["signal_raw"] == -1).sum()
    print(f"=== Signal Generation ===")
    print(f"  Long signals:  {n_long}")
    print(f"  Short signals: {n_short}")
    print(f"  Total:         {n_long + n_short}")
    print()

    if n_long + n_short == 0:
        print("No signals generated. Strategy produces no trades on this data.")
        if args.json:
            print(json.dumps({
                "error": "no_signals",
                "symbol": args.symbol,
                "tf": args.tf,
                **safety_metadata("no-signals-research-only"),
            }))
        sys.exit(0)

    # === PHASE 3: Position sizing ===
    df = position_sizing(df, args.portfolio, args.symbol)

    # === PHASE 4: Backtest ===
    trades = backtest_simple(df, args.symbol)
    metrics = compute_metrics(trades, args.portfolio)

    print(f"=== Backtest Results ({args.symbol} {args.tf}m) ===")
    print(f"  Total Trades:    {metrics['total_trades']}")
    print(f"  Win Rate:        {metrics['wr']}%")
    print(f"  Total PnL:       ${metrics['total_pnl']:.2f}")
    print(f"  Avg PnL/Trade:   ${metrics['avg_pnl']:.2f}")
    print(f"  Avg Win:         ${metrics['avg_win']:.2f}")
    print(f"  Avg Loss:        ${metrics['avg_loss']:.2f}")
    print(f"  Profit Factor:   {metrics['profit_factor']}")
    print(f"  Sharpe (ann.):   {metrics['sharpe_annualized']}")
    print(f"  Max Drawdown:    {metrics['max_dd_pct']}%")
    print(f"  Avg Bars Held:   {metrics['avg_bars_held']}")
    print()

    # Side asymmetry
    print(f"=== Side Asymmetry ===")
    print(f"  Long:  {metrics['long_trades']} trades, ${metrics['long_pnl']:.2f}")
    print(f"  Short: {metrics['short_trades']} trades, ${metrics['short_pnl']:.2f}")
    print()

    # Session breakdown
    if metrics["sessions"]:
        print(f"=== Session Breakdown ===")
        for sess, stats in metrics["sessions"].items():
            print(f"  {sess:>8}: {stats['trades']} trades, ${stats['pnl']:.2f}, WR {stats['wr']}%")
        print()

    # Exit reasons
    print(f"=== Exit Reasons ===")
    for reason, count in metrics["exit_reasons"].items():
        print(f"  {reason}: {count}")
    print()

    # === PHASE 5: Live signal check ===
    # Check latest bar for actionable signal
    last_signal = df[df["signal_raw"] != 0].iloc[-1] if (df["signal_raw"] != 0).any() else None
    if last_signal is not None:
        print(f"=== Latest Signal ===")
        print(f"  Time:      {last_signal['ts']}")
        print(f"  Direction: {'LONG' if last_signal['signal_raw'] == 1 else 'SHORT'}")
        print(f"  Price:     {last_signal['close']:.2f}")
        print(f"  Contracts: {int(last_signal['contracts'])}")
        print(f"  UB:        {last_signal['ub']:.2f}")
        print(f"  LB:        {last_signal['lb']:.2f}")
        print()

    # === Data freshness gate ===
    if freshness["fresh"]:
        verdict = "PASS"
    else:
        verdict = "FAIL (stale data)"
    print(f"=== DATA FRESHNESS GATE: {verdict} ===")
    print(f"  Data age: {freshness.get('age_hours', '?')}h (max: {freshness['max_age_hours']}h)")
    print()

    # JSON output
    if args.json:
        output = {
            "strategy": "vol_noise_scalp",
            "symbol": args.symbol,
            "timeframe": args.tf,
            "data": {
                "csv": args.csv,
                "bars": len(df),
                "date_range": f"{df['ts'].min()} to {df['ts'].max()}",
            },
            "freshness": freshness,
            "noise_area": {
                "close": float(latest["close"]),
                "ub": float(latest["ub"]),
                "lb": float(latest["lb"]),
                "width": float(latest["noise_width"]),
                "range_p75": float(latest["range_p75"]),
                "range_p25": float(latest["range_p25"]),
            },
            "signals": {"long": int(n_long), "short": int(n_short)},
            "metrics": metrics,
            "parameters": {
                "lookback_bars": args.lookback_bars,
                "confirmation_tau": CONFIRMATION_BARS,
                "target_vol_daily": TARGET_VOL_DAILY,
                "max_leverage": MAX_LEVERAGE,
                "max_contracts_mnq": MAX_CONTRACTS_MNQ,
                "min_hold_bars": MIN_HOLD_BARS,
                "max_hold_bars": MAX_HOLD_BARS,
                "trend_filter": not args.no_trend_filter,
                "volume_filter": not args.no_volume_filter,
            },
            **safety_metadata(
                "research-data-stale" if not freshness.get("fresh") else "research-only-backtest"
            ),
        }
        print("=== JSON OUTPUT ===")
        print(json.dumps(output, indent=2, default=str))

    # Save results to state file
    state_dir = STATE_DIR
    state_dir.mkdir(parents=True, exist_ok=True)
    state_file = state_dir / f"vol-noise-scalp-{args.symbol}-{args.tf}m.json"

    output = {
        "strategy": "vol_noise_scalp",
        "symbol": args.symbol,
        "timeframe": args.tf,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "freshness": freshness,
        "noise_area": {
            "close": float(latest["close"]) if not pd.isna(latest["close"]) else None,
            "ub": float(latest["ub"]) if not pd.isna(latest["ub"]) else None,
            "lb": float(latest["lb"]) if not pd.isna(latest["lb"]) else None,
            "width": float(latest["noise_width"]) if not pd.isna(latest["noise_width"]) else None,
        },
        "signals": {"long": int(n_long), "short": int(n_short), "total": int(n_long + n_short)},
        "metrics": metrics,
        "data_freshness_gate": verdict,
        **safety_metadata(
            "research-data-stale" if not freshness.get("fresh") else "research-only-backtest"
        ),
    }
    with open(state_file, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"State saved: {state_file}")


if __name__ == "__main__":
    main()
