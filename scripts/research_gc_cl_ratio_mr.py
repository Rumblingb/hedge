#!/usr/bin/env python3
"""
research_gc_cl_ratio_mr.py

RESEARCH ONLY. No broker access, no order routing, no live state mutation.

Validates a GC/CL ratio mean-reversion pairs strategy on 15m bars using a
purged walk-forward protocol. Outputs an honest OOS-after-costs verdict to
.rumbling-hedge/state/pairs-gc-cl-research.latest.json

Strategy
--------
- ratio = log(GC_close / CL_close)
- z = (ratio - rolling_mean(ratio, lookback)) / rolling_std(ratio, lookback)
- Entry:
    z > +entry_z  -> ratio is too high -> bet it falls -> SHORT GC / LONG CL
    z < -entry_z  -> ratio is too low  -> bet it rises -> LONG GC / SHORT CL
- Exit:
    |z| <= exit_z (mean reversion achieved), OR
    |z| >= stop_z (blown through, cut loss), OR
    end of data (forced flat)
  stop_z = entry_z + STOP_BUFFER (fixed buffer, not grid-searched)

Position sizing (state simplification, per the task spec)
-----------------------------------------------------------
1 GC contract vs 1 CL contract spread. Dollar P&L:
    GC: $10 per 0.10 tick  -> $100 / 1.00 price point
    CL: $10 per 0.01 tick  -> $1000 / 1.00 price point

Costs (round trip, per leg):
    commission: $2.50 / side / contract -> $5.00 round trip per leg
    slippage:   1 tick per leg per side -> 2 ticks round trip per leg
        GC: 2 * $10 = $20 round trip slippage
        CL: 2 * $10 = $20 round trip slippage
    Total fixed cost per spread trade (2 legs):
        commission: 2 * $5.00 = $10.00
        slippage:   2 * $20   = $40.00
        TOTAL: $50.00 per round-trip spread trade

Validation
----------
Purged walk-forward over the aligned 15m series:
  - Split history into rolling windows.
  - For each window: TRAIN on the first ~40% (growing/rolling), embargo
    1 trading day (96 bars @ 15m), TEST on the next window.
  - Grid search on TRAIN: lookback in {50,100,200}, entry_z in
    {1.5,2.0,2.5}, exit_z in {0.0,0.5}. Pick best by net P&L.
  - Apply the TRAIN-selected params, frozen, to TEST (OOS).
  - Roll forward and repeat.
  - Aggregate all OOS folds. Also report a naive "best in-sample"
    (best params chosen and evaluated on the SAME full-sample data,
    no OOS) for an overfitting contrast.

If aligned history < 40 trading days, the script flags this explicitly
and the verdict is capped accordingly.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path("/Users/brain/hedge")
DATA_DIR = ROOT / "data" / "free"
OUT_PATH = ROOT / ".rumbling-hedge" / "state" / "pairs-gc-cl-research.latest.json"

# --- contract economics -----------------------------------------------------
GC_TICK = 0.10
GC_TICK_VALUE = 10.0  # $ per tick
GC_PT_VALUE = GC_TICK_VALUE / GC_TICK  # $100 / 1.00 price point

CL_TICK = 0.01
CL_TICK_VALUE = 10.0  # $ per tick
CL_PT_VALUE = CL_TICK_VALUE / CL_TICK  # $1000 / 1.00 price point

COMMISSION_PER_SIDE_PER_CONTRACT = 2.50
SLIPPAGE_TICKS_PER_LEG_PER_SIDE = 1

# Round-trip fixed cost for a 1x1 GC/CL spread trade (2 legs, entry+exit)
ROUNDTRIP_COMMISSION = 2 * 2 * COMMISSION_PER_SIDE_PER_CONTRACT  # 2 legs * 2 sides * $2.50 = $10
ROUNDTRIP_SLIPPAGE = (
    2 * SLIPPAGE_TICKS_PER_LEG_PER_SIDE * GC_TICK_VALUE  # GC leg: entry+exit ticks
    + 2 * SLIPPAGE_TICKS_PER_LEG_PER_SIDE * CL_TICK_VALUE  # CL leg: entry+exit ticks
)
ROUNDTRIP_COST = ROUNDTRIP_COMMISSION + ROUNDTRIP_SLIPPAGE  # $50

# --- grid ---------------------------------------------------------------
LOOKBACK_GRID = [50, 100, 200]
ENTRY_Z_GRID = [1.5, 2.0, 2.5]
EXIT_Z_GRID = [0.0, 0.5]
STOP_BUFFER = 1.5  # stop_z = entry_z + STOP_BUFFER (fixed, not grid-searched)

BARS_PER_DAY_15M = 96  # 24h * 4 (these instruments trade ~23h/day, approx)
EMBARGO_BARS = BARS_PER_DAY_15M  # 1 trading day embargo between train and test

MIN_TRADING_DAYS = 40


def load_aligned(timeframe_suffix: str) -> pd.DataFrame:
    gc_path = DATA_DIR / f"GC-{timeframe_suffix}.csv"
    cl_path = DATA_DIR / f"CL-{timeframe_suffix}.csv"
    gc = pd.read_csv(gc_path)
    cl = pd.read_csv(cl_path)
    for df in (gc, cl):
        df["ts"] = pd.to_datetime(df["ts"], utc=True, errors="coerce")
    gc = gc[["ts", "close"]].rename(columns={"close": "gc_close"})
    cl = cl[["ts", "close"]].rename(columns={"close": "cl_close"})
    merged = pd.merge(gc, cl, on="ts", how="inner").sort_values("ts").reset_index(drop=True)
    merged = merged.dropna(subset=["gc_close", "cl_close"])
    merged = merged[(merged["gc_close"] > 0) & (merged["cl_close"] > 0)]
    return merged.reset_index(drop=True)


def compute_zscore(df: pd.DataFrame, lookback: int) -> pd.Series:
    ratio = np.log(df["gc_close"] / df["cl_close"])
    mean = ratio.rolling(lookback, min_periods=lookback).mean()
    std = ratio.rolling(lookback, min_periods=lookback).std()
    z = (ratio - mean) / std.replace(0, np.nan)
    return z


def simulate(df: pd.DataFrame, lookback: int, entry_z: float, exit_z: float) -> list[dict]:
    """Simulate the ratio mean-reversion strategy on df (must contain gc_close, cl_close, ts).

    Returns list of trade dicts with net P&L in dollars after costs.
    """
    stop_z = entry_z + STOP_BUFFER
    z = compute_zscore(df, lookback)
    n = len(df)

    trades: list[dict] = []
    in_position = False
    direction = 0  # +1: long GC / short CL ; -1: short GC / long CL
    entry_idx = None
    entry_gc = entry_cl = None

    for i in range(n):
        zi = z.iloc[i]
        if np.isnan(zi):
            continue

        if not in_position:
            if zi > entry_z:
                direction = -1  # ratio too high -> short GC / long CL
            elif zi < -entry_z:
                direction = +1  # ratio too low -> long GC / short CL
            else:
                continue
            in_position = True
            entry_idx = i
            entry_gc = df["gc_close"].iloc[i]
            entry_cl = df["cl_close"].iloc[i]
            continue

        # in position: check exit conditions
        exit_reason = None
        if abs(zi) <= exit_z:
            exit_reason = "z_revert"
        elif abs(zi) >= stop_z:
            exit_reason = "stop"
        elif i == n - 1:
            exit_reason = "eod_force_flat"

        if exit_reason is not None:
            exit_gc = df["gc_close"].iloc[i]
            exit_cl = df["cl_close"].iloc[i]

            # GC leg: direction (+1 long GC, -1 short GC)
            gc_pnl = direction * (exit_gc - entry_gc) * GC_PT_VALUE
            # CL leg is opposite direction of GC leg
            cl_pnl = (-direction) * (exit_cl - entry_cl) * CL_PT_VALUE

            gross_pnl = gc_pnl + cl_pnl
            net_pnl = gross_pnl - ROUNDTRIP_COST

            trades.append({
                "entry_ts": str(df["ts"].iloc[entry_idx]),
                "exit_ts": str(df["ts"].iloc[i]),
                "direction": "long_gc_short_cl" if direction > 0 else "short_gc_long_cl",
                "entry_z": float(z.iloc[entry_idx]),
                "exit_z": float(zi),
                "exit_reason": exit_reason,
                "hold_bars": i - entry_idx,
                "gross_pnl": float(gross_pnl),
                "net_pnl": float(net_pnl),
                "cost": float(ROUNDTRIP_COST),
            })

            in_position = False
            direction = 0
            entry_idx = None
            entry_gc = entry_cl = None

    return trades


def trade_metrics(trades: list[dict]) -> dict:
    if not trades:
        return {
            "trades": 0,
            "win_rate_pct": None,
            "profit_factor": None,
            "net_pnl": 0.0,
            "gross_pnl": 0.0,
            "max_drawdown": 0.0,
            "avg_hold_bars": None,
            "avg_net_pnl_per_trade": None,
        }
    nets = [t["net_pnl"] for t in trades]
    grosses = [t["gross_pnl"] for t in trades]
    wins = [p for p in nets if p > 0]
    losses = [p for p in nets if p <= 0]
    gross_profit = sum(wins)
    gross_loss = -sum(losses)
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (float("inf") if gross_profit > 0 else None)

    # equity curve / max drawdown
    equity = np.cumsum(nets)
    running_max = np.maximum.accumulate(equity)
    drawdown = equity - running_max
    max_dd = float(drawdown.min()) if len(drawdown) else 0.0

    return {
        "trades": len(trades),
        "win_rate_pct": round(100.0 * len(wins) / len(trades), 2),
        "profit_factor": round(profit_factor, 4) if profit_factor not in (None, float("inf")) else profit_factor,
        "net_pnl": round(float(sum(nets)), 2),
        "gross_pnl": round(float(sum(grosses)), 2),
        "max_drawdown": round(max_dd, 2),
        "avg_hold_bars": round(float(np.mean([t["hold_bars"] for t in trades])), 2),
        "avg_net_pnl_per_trade": round(float(np.mean(nets)), 2),
    }


def grid_search(df_train: pd.DataFrame) -> tuple[tuple[int, float, float], dict]:
    best_params = None
    best_net = -float("inf")
    best_metrics = None
    for lookback in LOOKBACK_GRID:
        for entry_z in ENTRY_Z_GRID:
            for exit_z in EXIT_Z_GRID:
                trades = simulate(df_train, lookback, entry_z, exit_z)
                m = trade_metrics(trades)
                if m["net_pnl"] > best_net:
                    best_net = m["net_pnl"]
                    best_params = (lookback, entry_z, exit_z)
                    best_metrics = m
    return best_params, best_metrics


def build_walk_forward_folds(n_bars: int) -> list[dict]:
    """Build purged walk-forward fold boundaries.

    TRAIN window followed by an EMBARGO gap, then a TEST window. Folds
    roll forward without overlap in test windows.
    """
    n_folds_target = 4
    usable = n_bars
    test_size = usable // (n_folds_target + 2)  # leave room for train growth
    test_size = max(test_size, BARS_PER_DAY_15M * 3)  # at least ~3 days per test fold

    folds = []
    train_start = 0
    train_size = max(int(usable * 0.4), 250)

    pos = train_size
    while True:
        train_end = pos  # exclusive
        test_start = train_end + EMBARGO_BARS
        test_end = test_start + test_size
        if test_end > usable:
            test_end = usable
        if test_start >= usable or (test_end - test_start) < BARS_PER_DAY_15M:
            break
        folds.append({
            "train_start": train_start,
            "train_end": train_end,
            "test_start": test_start,
            "test_end": test_end,
        })
        pos = test_end
        if pos >= usable:
            break

    return folds


def main() -> None:
    df = load_aligned("15m-60d")
    df60 = load_aligned("60m-60d")

    n_bars = len(df)
    span_days = (df["ts"].iloc[-1] - df["ts"].iloc[0]).days if n_bars > 1 else 0
    approx_trading_days = n_bars / BARS_PER_DAY_15M

    folds_meta = build_walk_forward_folds(n_bars)

    fold_results = []
    all_oos_trades: list[dict] = []

    for i, f in enumerate(folds_meta):
        train_df = df.iloc[f["train_start"]:f["train_end"]].reset_index(drop=True)
        test_df = df.iloc[f["test_start"]:f["test_end"]].reset_index(drop=True)

        if len(train_df) < max(LOOKBACK_GRID) + 10 or len(test_df) < BARS_PER_DAY_15M:
            continue

        best_params, train_metrics = grid_search(train_df)
        lookback, entry_z, exit_z = best_params

        # need lookback warmup bars before test_start to compute z at the
        # start of the test window without leakage past the embargo cut.
        warmup_start = max(0, f["test_start"] - lookback)
        test_with_warmup = df.iloc[warmup_start:f["test_end"]].reset_index(drop=True)
        oos_trades_full = simulate(test_with_warmup, lookback, entry_z, exit_z)

        # only count trades whose entry occurred at/after the actual test_start
        test_start_ts = df["ts"].iloc[f["test_start"]]
        oos_trades = [t for t in oos_trades_full if pd.Timestamp(t["entry_ts"]) >= test_start_ts]

        oos_metrics = trade_metrics(oos_trades)
        all_oos_trades.extend(oos_trades)

        fold_results.append({
            "fold": i + 1,
            "train_range": [str(train_df["ts"].iloc[0]), str(train_df["ts"].iloc[-1])],
            "test_range": [str(test_df["ts"].iloc[0]), str(test_df["ts"].iloc[-1])],
            "selected_params": {"lookback": lookback, "entry_z": entry_z, "exit_z": exit_z, "stop_z": entry_z + STOP_BUFFER},
            "train_in_sample": train_metrics,
            "test_oos": oos_metrics,
        })

    aggregate_oos = trade_metrics(all_oos_trades)

    # Naive in-sample best: grid search on FULL data, evaluate on FULL data (no OOS split)
    naive_best_params, naive_metrics = grid_search(df)

    verdict = "no-edge"
    notes = []
    if approx_trading_days < MIN_TRADING_DAYS:
        notes.append(
            f"Aligned 15m history is only ~{approx_trading_days:.1f} trading days "
            f"(< {MIN_TRADING_DAYS} day minimum). Any verdict here is provisional / "
            f"low-confidence regardless of metric values."
        )
        verdict = "no-edge"
    else:
        oos_pf = aggregate_oos["profit_factor"]
        oos_net = aggregate_oos["net_pnl"]
        oos_trades_n = aggregate_oos["trades"]
        if oos_trades_n == 0:
            verdict = "no-edge"
            notes.append("Zero OOS trades generated across folds; cannot evaluate edge.")
        elif oos_pf is not None and oos_pf > 1.2 and oos_net > 0 and oos_trades_n >= 20:
            verdict = "weak-candidate-needs-more-data"
            if oos_pf > 1.5 and oos_trades_n >= 40:
                verdict = "candidate-for-shadow-lane"
        else:
            verdict = "no-edge"

    generated_at = datetime.now(timezone.utc).isoformat()

    result = {
        "generatedAt": generated_at,
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "promoted_for_execution": False,
        "evidence_level": "research-backtest-only",
        "method": {
            "description": (
                "Z-score of log(GC/CL) on 15m bars, mean-reversion entries, "
                "exit on z-revert or stop, purged walk-forward grid search "
                "(train -> pick params -> 1-day embargo -> test next window -> roll)."
            ),
            "lookback_grid": LOOKBACK_GRID,
            "entry_z_grid": ENTRY_Z_GRID,
            "exit_z_grid": EXIT_Z_GRID,
            "stop_buffer_added_to_entry_z": STOP_BUFFER,
            "embargo_bars": EMBARGO_BARS,
            "embargo_description": "1 trading day (96x 15m bars) gap between end of train window and start of test window",
            "costs": {
                "commission_per_side_per_contract_usd": COMMISSION_PER_SIDE_PER_CONTRACT,
                "slippage_ticks_per_leg_per_side": SLIPPAGE_TICKS_PER_LEG_PER_SIDE,
                "gc_tick_value_usd": GC_TICK_VALUE,
                "cl_tick_value_usd": CL_TICK_VALUE,
                "roundtrip_cost_per_spread_trade_usd": ROUNDTRIP_COST,
            },
            "position_sizing": "1x GC contract vs 1x CL contract spread (state simplification)",
        },
        "datasets": {
            "gc_15m": "data/free/GC-15m-60d.csv",
            "cl_15m": "data/free/CL-15m-60d.csv",
            "gc_60m": "data/free/GC-60m-60d.csv",
            "cl_60m": "data/free/CL-60m-60d.csv",
            "aligned_bars_15m": n_bars,
            "span_calendar_days": span_days,
            "approx_trading_days_15m": round(approx_trading_days, 2),
            "first_ts": str(df["ts"].iloc[0]),
            "last_ts": str(df["ts"].iloc[-1]),
            "min_required_trading_days": MIN_TRADING_DAYS,
            "sufficient_history": approx_trading_days >= MIN_TRADING_DAYS,
            "60m_aligned_bars": len(df60),
        },
        "folds": fold_results,
        "aggregate": {
            "oos": aggregate_oos,
            "naive_in_sample_best": {
                "selected_params": {
                    "lookback": naive_best_params[0],
                    "entry_z": naive_best_params[1],
                    "exit_z": naive_best_params[2],
                    "stop_z": naive_best_params[1] + STOP_BUFFER,
                },
                "metrics": naive_metrics,
            },
            "overfitting_contrast_note": (
                "Compare aggregate.oos vs aggregate.naive_in_sample_best. "
                "naive_in_sample_best fits the SAME data it is evaluated on "
                "(no train/test split) and is expected to look materially "
                "better than true OOS. A large gap between the two indicates "
                "overfitting / curve-fit risk in the naive approach."
            ),
        },
        "verdict": verdict,
        "notes": notes,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(result, indent=2, default=str))

    # --- console report ---
    print(f"Aligned 15m bars: {n_bars} (~{approx_trading_days:.1f} trading days, "
          f"{df['ts'].iloc[0]} -> {df['ts'].iloc[-1]})")
    print(f"Roundtrip cost per spread trade: ${ROUNDTRIP_COST:.2f} "
          f"(commission ${ROUNDTRIP_COMMISSION:.2f} + slippage ${ROUNDTRIP_SLIPPAGE:.2f})")
    print()
    print("Per-fold results:")
    header = f"{'fold':<5}{'lookback':<9}{'entry_z':<8}{'exit_z':<8}{'oos_trades':<11}{'oos_wr%':<9}{'oos_pf':<8}{'oos_net':<12}{'oos_maxdd':<12}{'avg_hold':<9}"
    print(header)
    for f in fold_results:
        m = f["test_oos"]
        p = f["selected_params"]
        print(f"{f['fold']:<5}{p['lookback']:<9}{p['entry_z']:<8}{p['exit_z']:<8}"
              f"{m['trades']:<11}{(m['win_rate_pct'] if m['win_rate_pct'] is not None else 'n/a'):<9}"
              f"{(m['profit_factor'] if m['profit_factor'] is not None else 'n/a'):<8}"
              f"{m['net_pnl']:<12}{m['max_drawdown']:<12}"
              f"{(m['avg_hold_bars'] if m['avg_hold_bars'] is not None else 'n/a'):<9}")
    print()
    print("Aggregate OOS:", json.dumps(aggregate_oos, indent=2))
    print()
    print("Naive in-sample best (overfitting contrast):")
    print("  params:", result["aggregate"]["naive_in_sample_best"]["selected_params"])
    print("  metrics:", json.dumps(naive_metrics, indent=2))
    print()
    print("VERDICT:", verdict)
    for n in notes:
        print("  NOTE:", n)
    print()
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
