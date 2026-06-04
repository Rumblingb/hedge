#!/usr/bin/env python3
"""
backtest_clv_momentum.py — CLV Momentum Burst Scalper (5m NQ)

Tests Signal 1 from intraday-scalp-discovery.md:
  CLV > 0.7 (long) or CLV < -0.7 (short) + volume > 1.3x rolling mean
  + bar range > median range + session filter (10:00-12:00, 14:00-16:00 ET)

Usage:
  python3 scripts/backtest_clv_momentum.py [--symbol NQ] [--days 30]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import yfinance as yf


# ── Constants ───────────────────────────────────────────────────────────────
CLV_THRESHOLD = 0.7          # |CLV| above this = extreme
VOLUME_MULT = 1.3            # volume > VOLUME_MULT × rolling mean
RANGE_MULT = 1.0             # bar range > RANGE_MULT × median range
ROLLING_WINDOW = 20          # bars for rolling stats
VOLUME_WINDOW = 20           # rolling volume mean
TP_R_MULT = 1.5              # TP as multiple of entry bar range
SL_R_MULT = 1.0              # SL as multiple of entry bar range
TIME_STOP_BARS = 2           # exit after N bars if TP/SL not hit

# Session filter: hour buckets in ET
ACTIVE_SESSIONS = [(10, 12), (14, 16)]  # 10:00-12:00, 14:00-16:00 ET

SYMBOL_MAP = {
    "NQ": {"yf_ticker": "QQQ", "point_value": 5, "min_volume": 5000},
    "ES": {"yf_ticker": "SPY", "point_value": 50, "min_volume": 15000},
}


# ── Data ─────────────────────────────────────────────────────────────────────
def fetch_5m_bars(ticker: str, days: int = 30) -> pd.DataFrame:
    """Download 5-min OHLCV from Yahoo."""
    period = f"{max(7, days + 5)}d"
    df = yf.download(
        ticker, interval="5m", period=period,
        progress=False, auto_adjust=True,
    )
    if df.empty:
        raise RuntimeError(f"No 5m data returned for {ticker}")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    required = {"Open", "High", "Low", "Close", "Volume"}
    missing = required - set(df.columns)
    if missing:
        raise RuntimeError(f"Missing columns: {missing}")
    return df


# ── Signal ───────────────────────────────────────────────────────────────────
def compute_clv(df: pd.DataFrame) -> pd.Series:
    """Close Location Value per bar."""
    rng = df["High"] - df["Low"]
    rng = rng.replace(0, np.nan)
    return ((df["Close"] - df["Low"]) - (df["High"] - df["Close"])) / rng


def compute_rolling_stats(df: pd.DataFrame) -> pd.DataFrame:
    """Add derived columns: CLV, rolling vol mean, median range, etc."""
    out = df.copy()
    out["clv"] = compute_clv(out)
    out["bar_range"] = out["High"] - out["Low"]
    out["vol_mean"] = out["Volume"].rolling(VOLUME_WINDOW, min_periods=10).mean()
    out["range_median"] = out["bar_range"].rolling(VOLUME_WINDOW, min_periods=10).median()
    out["hour_et"] = out.index.hour  # approximate — yfinance times are in exchange TZ
    return out


def is_active_session(hour: int) -> bool:
    for start, end in ACTIVE_SESSIONS:
        if start <= hour < end:
            return True
    return False


def generate_signals(df: pd.DataFrame) -> pd.Series:
    """Return 1 (long), -1 (short), 0 (none) per bar."""
    signals = pd.Series(0, index=df.index, dtype=int)

    for i in range(ROLLING_WINDOW, len(df)):
        row = df.iloc[i]
        clv = row["clv"]
        vol = row["Volume"]
        vol_mean = row["vol_mean"]
        bar_range = row["bar_range"]
        range_med = row["range_median"]
        hour = row["hour_et"]

        if pd.isna(clv) or pd.isna(vol_mean) or pd.isna(range_med):
            continue
        if not is_active_session(hour):
            continue
        if vol < vol_mean * VOLUME_MULT:
            continue
        if bar_range < range_med * RANGE_MULT:
            continue

        if clv > CLV_THRESHOLD:
            signals.iloc[i] = 1
        elif clv < -CLV_THRESHOLD:
            signals.iloc[i] = -1

    return signals


# ── Backtest ─────────────────────────────────────────────────────────────────
def run_backtest(
    df: pd.DataFrame,
    signals: pd.Series,
    point_value: float = 5.0,
    contracts: int = 1,
) -> dict:
    """Walk forward and simulate trades."""
    trades = []
    equity_curve = [0.0]

    for i in range(ROLLING_WINDOW, len(df)):
        sig = signals.iloc[i]
        if sig == 0:
            continue

        entry_price = df["Close"].iloc[i]
        bar_range = df["bar_range"].iloc[i]
        entry_idx = i
        direction = sig  # 1 = long, -1 = short

        tp_price = entry_price + direction * bar_range * TP_R_MULT
        sl_price = entry_price - direction * bar_range * SL_R_MULT
        exit_idx = min(i + TIME_STOP_BARS, len(df) - 1)

        # Simulate bar-by-bar exit
        realized_r = 0.0
        exit_price = entry_price
        exit_bar = entry_idx

        for j in range(i + 1, exit_idx + 1):
            bar_high = df["High"].iloc[j]
            bar_low = df["Low"].iloc[j]

            if direction == 1:  # long
                if bar_high >= tp_price:
                    exit_price = tp_price
                    exit_bar = j
                    realized_r = (tp_price - entry_price) / bar_range * TP_R_MULT
                    break
                elif bar_low <= sl_price:
                    exit_price = sl_price
                    exit_bar = j
                    realized_r = -(entry_price - sl_price) / bar_range * SL_R_MULT
                    break
            else:  # short
                if bar_low <= tp_price:
                    exit_price = tp_price
                    exit_bar = j
                    realized_r = (entry_price - tp_price) / bar_range * TP_R_MULT
                    break
                elif bar_high >= sl_price:
                    exit_price = sl_price
                    exit_bar = j
                    realized_r = -(sl_price - entry_price) / bar_range * SL_R_MULT
                    break
        else:
            # Time stop
            exit_price = df["Close"].iloc[exit_idx]
            exit_bar = exit_idx
            if direction == 1:
                realized_r = (exit_price - entry_price) / bar_range
            else:
                realized_r = (entry_price - exit_price) / bar_range

        trade = {
            "entry_bar": entry_idx,
            "exit_bar": exit_bar,
            "direction": "LONG" if direction == 1 else "SHORT",
            "entry": round(entry_price, 2),
            "exit": round(exit_price, 2),
            "realized_r": round(realized_r, 4),
            "pnl_dollars": round(realized_r * bar_range * point_value * contracts, 2),
        }
        trades.append(trade)
        equity_curve.append(equity_curve[-1] + trade["pnl_dollars"])

    # Stats
    n_trades = len(trades)
    if n_trades == 0:
        return {"trades": [], "win_rate": 0, "profit_factor": 0,
                "total_r": 0, "avg_r": 0, "sharpe": 0,
                "max_drawdown_pct": 0, "equity_curve": equity_curve}

    winners = [t for t in trades if t["realized_r"] > 0]
    losers = [t for t in trades if t["realized_r"] <= 0]
    win_rate = len(winners) / n_trades

    total_r = sum(t["realized_r"] for t in trades)
    avg_r = total_r / n_trades
    gross_profit = sum(t["pnl_dollars"] for t in winners)
    gross_loss = abs(sum(t["pnl_dollars"] for t in losers))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    returns = pd.Series(equity_curve).diff().dropna()
    sharpe = (returns.mean() / returns.std() * np.sqrt(252 * 78)) if returns.std() > 0 else 0  # 78 five-min bars/day

    peak = np.maximum.accumulate(equity_curve)
    drawdown = np.array(equity_curve) - peak
    max_dd = abs(min(drawdown)) if peak[-1] > 0 else 0
    max_dd_pct = (max_dd / peak[np.argmin(drawdown)]) * 100 if peak[np.argmin(drawdown)] > 0 else 0

    return {
        "n_trades": n_trades,
        "n_winners": len(winners),
        "n_losers": len(losers),
        "win_rate": round(win_rate, 4),
        "profit_factor": round(profit_factor, 2),
        "total_r": round(total_r, 2),
        "avg_r": round(avg_r, 4),
        "sharpe": round(sharpe, 2),
        "max_drawdown_pct": round(max_dd_pct, 2),
        "total_pnl": round(equity_curve[-1], 2),
        "trades": trades,
        "equity_curve": equity_curve,
    }


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="CLV Momentum Burst Backtest")
    parser.add_argument("--symbol", default="NQ", choices=["NQ", "ES"])
    parser.add_argument("--days", type=int, default=30, help="Days of 5m data to fetch")
    parser.add_argument("--state-dir", default=str(Path.home() / ".rumbling-hedge" / "state"))
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    cfg = SYMBOL_MAP[args.symbol]

    try:
        df = fetch_5m_bars(cfg["yf_ticker"], args.days)
    except Exception as e:
        print(json.dumps({"error": str(e), "status": "DATA_FETCH_FAILED"}))
        sys.exit(1)

    df = compute_rolling_stats(df)
    signals = generate_signals(df)
    result = run_backtest(df, signals, point_value=cfg["point_value"])

    # Add metadata
    result["symbol"] = args.symbol
    result["bars_processed"] = len(df)
    result["signal_count"] = int((signals != 0).sum())
    result["thresholds"] = {
        "clv_threshold": CLV_THRESHOLD,
        "volume_mult": VOLUME_MULT,
        "range_mult": RANGE_MULT,
        "tp_r_mult": TP_R_MULT,
        "sl_r_mult": SL_R_MULT,
        "time_stop_bars": TIME_STOP_BARS,
        "active_sessions": ACTIVE_SESSIONS,
    }
    result["timestamp"] = datetime.now(timezone.utc).isoformat()

    # Write state
    state_dir = Path(args.state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    out_path = state_dir / "backtest-clv-momentum.latest.json"
    out_path.write_text(json.dumps(result, indent=2, default=str) + "\n")

    # Print summary
    print(f"symbol={args.symbol}  trades={result['n_trades']}  "
          f"WR={result['win_rate']:.1%}  PF={result['profit_factor']}  "
          f"totalR={result['total_r']}  avgR={result['avg_r']}  "
          f"Sharpe={result['sharpe']}  maxDD={result['max_drawdown_pct']:.1f}%")
    print(f"Full results → {out_path}")


if __name__ == "__main__":
    main()
