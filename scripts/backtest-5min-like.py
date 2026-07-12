#!/usr/bin/env python3
"""
5-bar daily momentum backtest with ICT displacement-style parameters.
Mimics the proven 5-min bar pattern using daily 1-year data.

Pattern:
  Sensor: 5-bar displacement > multiplier × ATR (ICT displacement)
  Entry: momentum continuation in displacement direction
  Volume confirmation: current volume > 5-bar SMA volume
  Stop: opposite end of the signal bar
  Target: 2R (1:2 risk:reward)
  No overlapping positions

Walkforward:
  Train (40%): optimise displacement multiplier (1.0x-3.0x)
  Test  (30%): evaluate best multiplier
  OOS   (30%): final unseen performance

Data: /Users/brain/hedge/data/free/ALL-2MARKETS-NQ-ES-1d-1y.csv
      ES + NQ daily OHLCV, 251 bars each
"""

import warnings
warnings.filterwarnings('ignore', category=FutureWarning)

import pandas as pd
import numpy as np

# ── Config ──────────────────────────────────────────────────────────────
DATA_PATH = "/Users/brain/hedge/data/free/ALL-2MARKETS-NQ-ES-1d-1y.csv"
LOOKBACK = 5            # 5-bar displacement sensor (5 trading days ~ 1 week)
ATR_PERIOD = 14
VOL_SMA_PERIOD = 5
TRAIN_FRAC = 0.40       # first 40% of trading days for training
TEST_FRAC = 0.30        # next 30% for validation (OOS = remaining 30%)
RR_RATIO = 2.0          # 1:2 risk:reward (target = risk * 2)
MULTIPLIER_CANDIDATES = np.arange(1.0, 3.25, 0.25)


# ══════════════════════════════════════════════════════════════════════════
# 1. Load and prepare data
# ══════════════════════════════════════════════════════════════════════════
print("=" * 72)
print("5-BAR DAILY MOMENTUM BACKTEST — ICT DISPLACEMENT STYLE")
print("=" * 72)

df_raw = pd.read_csv(DATA_PATH, parse_dates=['ts'])
for col in ['open', 'high', 'low', 'close', 'volume']:
    df_raw[col] = pd.to_numeric(df_raw[col], errors='coerce')

df_raw = df_raw.sort_values(['ts', 'symbol']).reset_index(drop=True)

print(f"\nLoaded {len(df_raw)} rows, {df_raw['symbol'].nunique()} symbols ({df_raw['symbol'].unique()})")
print(f"Date range: {df_raw['ts'].min().date()} to {df_raw['ts'].max().date()}")

# ── Feature engineering per symbol (using a loop to avoid groupby apply issues) ──
frames = []
for sym in ['ES', 'NQ']:
    g = df_raw[df_raw['symbol'] == sym].sort_values('ts').copy()

    # 5-bar displacement (points and percent)
    g['displacement_5'] = g['close'] - g['close'].shift(LOOKBACK)
    g['displacement_pct'] = g['displacement_5'] / g['close'].shift(LOOKBACK) * 100.0
    g['disp_mag'] = g['displacement_5'].abs()

    # True Range for ATR
    g['prev_close'] = g['close'].shift(1)
    g['tr'] = np.maximum(
        g['high'] - g['low'],
        np.maximum(
            (g['high'] - g['prev_close']).abs(),
            (g['low'] - g['prev_close']).abs()
        )
    )
    g['atr'] = g['tr'].rolling(ATR_PERIOD).mean()

    # Volume SMA for confirmation
    g['vol_sma'] = g['volume'].rolling(VOL_SMA_PERIOD).mean()
    g['vol_confirmed'] = g['volume'] > g['vol_sma']

    # Forward return for evaluation
    g['forward_5_ret'] = (g['close'].shift(-LOOKBACK) / g['close'] - 1) * 100.0

    g['row_idx'] = g.index
    frames.append(g)

df = pd.concat(frames, ignore_index=True)
df = df.sort_values(['ts', 'symbol']).reset_index(drop=True)
df['row_idx_orig'] = df.index

# Print feature stats
print(f"Total rows after feature engineering: {len(df)}")
for sym in ['ES', 'NQ']:
    sd = df[df['symbol'] == sym]
    disp_atr = (sd['disp_mag'] / sd['atr']).dropna()
    print(f"\n{sym} ({len(sd)} bars):")
    print(f"  Displacement/ATR ratio:  mean={disp_atr.mean():.2f}x, "
          f"max={disp_atr.max():.2f}x, >1.5x: {(disp_atr>1.5).sum()} bars")
    print(f"  ATR: mean={sd['atr'].mean():.2f}, "
          f"ATR%={ (sd['atr']/sd['close']*100).mean():.3f}%")
    print(f"  Volume confirmed bars:  {sd['vol_confirmed'].sum()} / {len(sd)}")


# ══════════════════════════════════════════════════════════════════════════
# 2. Walkforward split (by trading day)
# ══════════════════════════════════════════════════════════════════════════
unique_dates = sorted(df['ts'].unique())
n_dates = len(unique_dates)

train_date_end = int(n_dates * TRAIN_FRAC)
test_date_end = train_date_end + int(n_dates * TEST_FRAC)

train_dates = set(unique_dates[:train_date_end])
test_dates = set(unique_dates[train_date_end:test_date_end])
oos_dates  = set(unique_dates[test_date_end:])

train_df = df[df['ts'].isin(train_dates)].copy()
test_df  = df[df['ts'].isin(test_dates)].copy()
oos_df   = df[df['ts'].isin(oos_dates)].copy()

print(f"\n── Walkforward Split ──")
print(f"Unique trading days: {n_dates}")
print(f"Train: {train_df['ts'].min().date()} → {train_df['ts'].max().date()} "
      f"({train_df['ts'].nunique()} days, {len(train_df)} rows)")
print(f"Test:  {test_df['ts'].min().date()} → {test_df['ts'].max().date()} "
      f"({test_df['ts'].nunique()} days, {len(test_df)} rows)")
print(f"OOS:   {oos_df['ts'].min().date()} → {oos_df['ts'].max().date()} "
      f"({oos_df['ts'].nunique()} days, {len(oos_df)} rows)")


# ══════════════════════════════════════════════════════════════════════════
# 3. Backtest engine
# ══════════════════════════════════════════════════════════════════════════
def run_backtest(data, multiplier, verbose=False):
    """
    Displacement-momentum strategy:
      LONG:  displacement_5 > multiplier * atr  AND  vol_confirmed
      SHORT: displacement_5 < -multiplier * atr  AND  vol_confirmed
    Entry at close of signal bar.
    Stop at opposite end of signal bar.
    Target at 1:2 risk:reward.
    No overlapping positions per symbol.
    """
    trades = []
    position = {}  # {sym: {'type','entry_price','stop','target','risk','entry_date',...}}

    for sym in ['ES', 'NQ']:
        sd = data[data['symbol'] == sym].sort_values('ts').reset_index(drop=True)
        pos = None

        for i in range(len(sd)):
            row = sd.iloc[i]
            date_str = row['ts'].strftime('%Y-%m-%d')
            close = float(row['close'])
            o = float(row['open'])
            high = float(row['high'])
            low = float(row['low'])

            # Skip rows with NaN features (not enough history)
            if pd.isna(row['displacement_5']) or pd.isna(row['atr']) or row['atr'] == 0:
                continue
            if pd.isna(row['vol_confirmed']) or not bool(row['vol_confirmed']):
                continue

            displacement = float(row['displacement_5'])
            atr = float(row['atr'])
            vol_conf = bool(row['vol_confirmed'])

            # ── Check exit for existing position ──
            if pos is not None:
                exit_price = None
                exit_reason = None

                if pos['type'] == 'long':
                    if low <= pos['stop']:
                        exit_price = pos['stop']
                        exit_reason = 'stop'
                    elif high >= pos['target']:
                        exit_price = pos['target']
                        exit_reason = 'target'
                else:  # short
                    if high >= pos['stop']:
                        exit_price = pos['stop']
                        exit_reason = 'stop'
                    elif low <= pos['target']:
                        exit_price = pos['target']
                        exit_reason = 'target'

                if exit_price is not None:
                    if pos['type'] == 'long':
                        ret_pct = (exit_price - pos['entry_price']) / pos['entry_price'] * 100.0
                    else:
                        ret_pct = (pos['entry_price'] - exit_price) / pos['entry_price'] * 100.0

                    r_multiple = ret_pct / (pos['risk'] / pos['entry_price'] * 100.0)

                    trades.append({
                        'symbol': sym,
                        'entry_date': pos['entry_date'],
                        'exit_date': date_str,
                        'type': pos['type'],
                        'entry_price': round(pos['entry_price'], 2),
                        'exit_price': round(exit_price, 2),
                        'ret_pct': round(ret_pct, 2),
                        'r_multiple': round(r_multiple, 2),
                        'exit_reason': exit_reason,
                        'displacement': round(pos.get('displacement', 0), 2),
                        'atr_entry': round(pos.get('atr_entry', 0), 2),
                        'risk': round(pos['risk'], 2),
                    })
                    pos = None

            # ── Check entry (if no position open) ──
            if pos is not None:
                continue

            entry_type = None
            entry_price = close  # enter at close of signal bar

            if displacement > multiplier * atr:
                entry_type = 'long'
            elif displacement < -multiplier * atr:
                entry_type = 'short'

            if entry_type is not None:
                if entry_type == 'long':
                    stop = low
                    risk = entry_price - stop
                    if risk <= 0:
                        continue
                    target = entry_price + RR_RATIO * risk
                else:  # short
                    stop = high
                    risk = stop - entry_price
                    if risk <= 0:
                        continue
                    target = entry_price - RR_RATIO * risk

                pos = {
                    'type': entry_type,
                    'entry_price': entry_price,
                    'stop': stop,
                    'target': target,
                    'risk': risk,
                    'entry_date': date_str,
                    'displacement': displacement,
                    'atr_entry': atr,
                }

                if verbose:
                    disp_ratio = abs(displacement) / atr
                    print(f"  {date_str} {sym} {entry_type.upper():5s} "
                          f"entry={entry_price:.2f} stop={stop:.2f} target={target:.2f} "
                          f"R={risk:.2f} disp/ATR={disp_ratio:.2f}x")

        # Close any remaining open position at last bar's close
        if pos is not None:
            last_row = sd.iloc[-1]
            exit_price = float(last_row['close'])
            if pos['type'] == 'long':
                ret_pct = (exit_price - pos['entry_price']) / pos['entry_price'] * 100.0
            else:
                ret_pct = (pos['entry_price'] - exit_price) / pos['entry_price'] * 100.0

            trades.append({
                'symbol': sym,
                'entry_date': pos['entry_date'],
                'exit_date': str(last_row['ts'].date()),
                'type': pos['type'],
                'entry_price': round(pos['entry_price'], 2),
                'exit_price': round(exit_price, 2),
                'ret_pct': round(ret_pct, 2),
                'r_multiple': round(ret_pct / (pos['risk'] / pos['entry_price'] * 100.0), 2),
                'exit_reason': 'open',
                'displacement': round(pos['displacement'], 2),
                'atr_entry': round(pos['atr_entry'], 2),
                'risk': round(pos['risk'], 2),
            })

    return trades


def calc_metrics(trades):
    """Calculate performance metrics from trade list."""
    if len(trades) == 0:
        return {'n_trades': 0, 'win_rate': 0, 'avg_ret': 0, 'total_return': 0,
                'sharpe': 0, 'max_dd': 0, 'avg_r': 0, 'profit_factor': 0,
                'avg_hold_days': 0, 'long_pct': 0, 'target_hit_pct': 0}

    df_t = pd.DataFrame(trades)
    wins = df_t[df_t['ret_pct'] > 0.001]
    losses = df_t[df_t['ret_pct'] <= 0.001]

    total_ret = df_t['ret_pct'].sum()
    avg_r = df_t['r_multiple'].mean()

    # Sharpe-like: mean(R) / std(R) * sqrt(252 / ~days-per-trade)
    rets = df_t['ret_pct'].values
    sharpe = 0.0
    if len(rets) > 1 and rets.std() > 0:
        sharpe = rets.mean() / rets.std() * np.sqrt(252 / 2)  # ~2 days avg hold approximation

    # Max drawdown from cumulative returns
    cum_ret = df_t['ret_pct'].cumsum()
    running_max = cum_ret.cummax()
    dd = cum_ret - running_max
    max_dd = dd.min()

    # Profit factor
    gross_profit = wins['ret_pct'].sum() if len(wins) > 0 else 0
    gross_loss = abs(losses['ret_pct'].sum()) if len(losses) > 0 else 0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 999.0

    # Avg hold (calendar days)
    entry_dates = pd.to_datetime(df_t['entry_date'])
    exit_dates = pd.to_datetime(df_t['exit_date'])
    avg_hold = (exit_dates - entry_dates).dt.days.mean()

    return {
        'n_trades': len(df_t),
        'win_rate': len(wins) / len(df_t) * 100,
        'avg_ret': df_t['ret_pct'].mean(),
        'total_return': total_ret,
        'sharpe': sharpe,
        'max_dd': max_dd,
        'avg_r': avg_r,
        'profit_factor': profit_factor,
        'avg_hold_days': avg_hold,
        'long_pct': (df_t['type'] == 'long').mean() * 100,
        'target_hit_pct': (df_t['exit_reason'] == 'target').mean() * 100,
    }


def print_metrics(phase, m, trades, multiplier):
    print(f"\n── {phase} Results (multiplier={multiplier:.2f}x) ──")
    if m['n_trades'] == 0:
        print("  No trades generated.")
        return
    print(f"  Trades:             {m['n_trades']}")
    print(f"  Win rate:           {m['win_rate']:.1f}%")
    print(f"  Avg return/trade:   {m['avg_ret']:.2f}%")
    print(f"  Total return:       {m['total_return']:.2f}%")
    print(f"  Avg R-multiple:     {m['avg_r']:.2f}")
    print(f"  Profit factor:      {m['profit_factor']:.2f}")
    print(f"  Sharpe (annual):    {m['sharpe']:.2f}")
    print(f"  Max drawdown:       {m['max_dd']:.2f}%")
    print(f"  Avg hold:           {m['avg_hold_days']:.1f} days")
    print(f"  Long trades:        {m['long_pct']:.0f}%")
    print(f"  Target hit:         {m['target_hit_pct']:.0f}%")
    df_t = pd.DataFrame(trades)
    for sym in df_t['symbol'].unique():
        st = df_t[df_t['symbol'] == sym]
        wins = (st['ret_pct'] > 0.001).sum()
        total = len(st)
        wr = wins / total * 100 if total > 0 else 0
        print(f"  {sym}: {total} trades, {wr:.0f}% WR, "
              f"{st['ret_pct'].sum():+.2f}% total, "
              f"avg R={st['r_multiple'].mean():.2f}")


# ══════════════════════════════════════════════════════════════════════════
# PHASE 1: TRAINING — Optimise displacement multiplier
# ══════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 72)
print("PHASE 1: TRAINING — Optimising displacement multiplier")
print("=" * 72)

results = []
for mult in MULTIPLIER_CANDIDATES:
    trades = run_backtest(train_df, mult)
    m = calc_metrics(trades)
    results.append({'multiplier': mult, 'n_trades': m['n_trades'],
                    'total_return': m['total_return'], 'sharpe': m['sharpe'],
                    'win_rate': m['win_rate'], 'avg_r': m['avg_r'],
                    'profit_factor': m['profit_factor'], 'max_dd': m['max_dd']})
    print(f"  {mult:.2f}x → {m['n_trades']:3d} trades, "
          f"ret={m['total_return']:+7.2f}%, Sharpe={m['sharpe']:.3f}, "
          f"WR={m['win_rate']:.0f}%, PF={m['profit_factor']:.2f}, "
          f"avgR={m['avg_r']:.2f}")

results_df = pd.DataFrame(results)
# Pick best by Sharpe (min 5 trades)
valid = results_df[results_df['n_trades'] >= 5]
if len(valid) == 0:
    best_idx = results_df['total_return'].idxmax()
else:
    best_idx = valid['sharpe'].idxmax()

best_mult = float(results_df.loc[best_idx, 'multiplier'])
print(f"\n>>> Best multiplier (train): {best_mult:.2f}x "
      f"(Sharpe={results_df.loc[best_idx, 'sharpe']:.3f}, "
      f"n_trades={int(results_df.loc[best_idx, 'n_trades'])})")


# ══════════════════════════════════════════════════════════════════════════
# PHASE 2: TEST — Evaluate best multiplier on validation set
# ══════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 72)
print(f"PHASE 2: TEST — Multiplier={best_mult:.2f}x on validation data")
print("=" * 72)

test_trades = run_backtest(test_df, best_mult, verbose=True)
test_m = calc_metrics(test_trades)
print_metrics("TEST", test_m, test_trades, best_mult)


# ══════════════════════════════════════════════════════════════════════════
# PHASE 3: OOS — Final unseen performance
# ══════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 72)
print(f"PHASE 3: OOS — Multiplier={best_mult:.2f}x on unseen data")
print("=" * 72)

oos_trades = run_backtest(oos_df, best_mult, verbose=False)
oos_m = calc_metrics(oos_trades)
print_metrics("OOS", oos_m, oos_trades, best_mult)


# ══════════════════════════════════════════════════════════════════════════
# PHASE 4: FULL — Run on entire dataset
# ══════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 72)
print(f"PHASE 4: FULL DATASET — Multiplier={best_mult:.2f}x")
print("=" * 72)

full_trades = run_backtest(df, best_mult, verbose=False)
full_m = calc_metrics(full_trades)
print_metrics("FULL", full_m, full_trades, best_mult)


# ══════════════════════════════════════════════════════════════════════════
# Trade Listing
# ══════════════════════════════════════════════════════════════════════════
if len(full_trades) > 0:
    print(f"\n── All Trades (full dataset, {best_mult:.2f}x) ──")
    df_trades = pd.DataFrame(full_trades).sort_values(['entry_date', 'symbol'])
    for _, t in df_trades.iterrows():
        print(f"  {t['symbol']:4s} {str(t['entry_date']):12s}→{str(t['exit_date']):12s} "
              f"{t['type']:5s} entry={t['entry_price']:<10.2f} exit={t['exit_price']:<10.2f} "
              f"ret={t['ret_pct']:+7.2f}% R={t['r_multiple']:+5.2f} "
              f"{t['exit_reason']:6s} disp={t['displacement']:<8.2f}")


# ══════════════════════════════════════════════════════════════════════════
# FINAL SUMMARY
# ══════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 72)
print("FINAL SUMMARY")
print("=" * 72)
print(f"Strategy:    {LOOKBACK}-bar daily momentum, ICT displacement")
print(f"Data:        ES + NQ, {n_dates} trading days "
      f"({df['ts'].min().date()} → {df['ts'].max().date()})")
print(f"Multiplier:  {best_mult:.2f}x ATR (optimised on {train_df['ts'].nunique()} train days)")
print(f"Risk:Reward: 1:{RR_RATIO:.0f} (target = 2R, stop = opposite of signal bar)")
print(f"Volume conf: Current > {VOL_SMA_PERIOD}-bar SMA")
print(f"Walkforward: Train {TRAIN_FRAC*100:.0f}% / Test {TEST_FRAC*100:.0f}% / "
      f"OOS {(1-TRAIN_FRAC-TEST_FRAC)*100:.0f}%")
print()

phases_data = [
    ("TRAIN", results_df.loc[best_idx]),
    ("TEST",  test_m),
    ("OOS",   oos_m),
    ("FULL",  full_m),
]

print(f"  {'Phase':8s} {'Trades':8s} {'WinRate':9s} {'TotRet':10s} {'AvgR':8s} "
      f"{'Sharpe':8s} {'PF':8s} {'MaxDD':8s}")
print(f"  {'-'*8} {'-'*8} {'-'*9} {'-'*10} {'-'*8} {'-'*8} {'-'*8} {'-'*8}")
for phase, m in phases_data:
    if isinstance(m, pd.Series):
        print(f"  {phase:8s} {int(m['n_trades']):<8d} {m['win_rate']:<8.1f}% "
              f"{m['total_return']:<+9.2f}% {m['avg_r']:<8.2f} {m['sharpe']:<8.3f} "
              f"{m['profit_factor']:<8.2f} {m['max_dd']:<7.2f}%")
    else:
        print(f"  {phase:8s} {m['n_trades']:<8d} {m['win_rate']:<8.1f}% "
              f"{m['total_return']:<+9.2f}% {m['avg_r']:<8.2f} {m['sharpe']:<8.3f} "
              f"{m['profit_factor']:<8.2f} {m['max_dd']:<7.2f}%")

print()
print("Saved: /Users/brain/hedge/scripts/backtest-5min-like.py")
print("Done.")
