#!/usr/bin/env python3
"""
Daily-bar ret_30:30 momentum backtest with walkforward validation.
Data: ES + NQ daily OHLCV, ~502 rows (251 days × 2 symbols).
"""
import warnings
warnings.filterwarnings('ignore', category=FutureWarning)

import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
from datetime import datetime, timedelta

# ── Config ──────────────────────────────────────────────────────────
DATA_PATH = "/Users/brain/hedge/data/free/ALL-2MARKETS-NQ-ES-1d-1y.csv"
TRAIN_ROWS = 300    # first 300 bars (~150 trading days × 2 symbols)
TEST_ROWS  = 100    # next 100 bars (~50 days × 2)
# The remainder (~102 rows) is OOS holdout
RET_PERIOD = 30      # days for ret_30 and forward_30
ATR_PERIOD = 14
TARGET_FRAC = 0.50   # target = 50% of projected momentum return
MAX_TRADES_PER_SYMBOL_PER_WEEK = 1
STOP_ATR_MULT = 1.0  # trailing stop at 1x ATR

# ── Load & parse ────────────────────────────────────────────────────
df = pd.read_csv(DATA_PATH, parse_dates=['ts'])
for col in ['open','high','low','close','volume']:
    df[col] = pd.to_numeric(df[col], errors='coerce')

df = df.sort_values(['ts', 'symbol']).reset_index(drop=True)
df['row_idx'] = df.index  # keep original row order for split

print(f"Loaded {len(df)} rows, {df['symbol'].nunique()} symbols")
print(f"Date range: {df['ts'].min().date()} to {df['ts'].max().date()}")
print(f"Training rows: 0–{TRAIN_ROWS-1}")
print(f"Test rows: {TRAIN_ROWS}–{TRAIN_ROWS+TEST_ROWS-1}")
print(f"OOS holdout rows: {TRAIN_ROWS+TEST_ROWS}–{len(df)-1}")
print(f"In-sample split date boundary: {df.iloc[TRAIN_ROWS-1]['ts'].date()}")
print(f"Test/OOS split date boundary: {df.iloc[TRAIN_ROWS+TEST_ROWS-1]['ts'].date()}")
print()

# ── Feature engineering per symbol ──────────────────────────────────
def add_features(group):
    """Add ret_30, forward_30_ret, ATR to a single-symbol DataFrame."""
    g = group.copy().sort_values('ts')
    g['ret_30'] = g['close'].pct_change(RET_PERIOD) * 100.0
    g['forward_30_ret'] = (g['close'].shift(-RET_PERIOD) / g['close'] - 1) * 100.0
    # ATR
    g['prev_close'] = g['close'].shift(1)
    g['tr'] = np.maximum(
        g['high'] - g['low'],
        np.maximum(
            (g['high'] - g['prev_close']).abs(),
            (g['low'] - g['prev_close']).abs()
        )
    )
    g['atr'] = g['tr'].rolling(ATR_PERIOD).mean()
    return g

df = df.groupby('symbol', group_keys=False).apply(add_features).reset_index(drop=True)
df = df.sort_values('row_idx').reset_index(drop=True)

# Take one trading week boundary: borrow from ts for weekday
df['week'] = df['ts'].dt.isocalendar().week.combine(df['ts'].dt.year, lambda w, y: f"{y}-W{w:02d}")
df['dow'] = df['ts'].dt.dayofweek

print("Feature ranges after engineering:")
print(f"  ret_30:    {df['ret_30'].min():.2f}% to {df['ret_30'].max():.2f}%")
print(f"  forward_30: {df['forward_30_ret'].min():.2f}% to {df['forward_30_ret'].max():.2f}%")
print(f"  atr:       {df['atr'].min():.2f} to {df['atr'].max():.2f}")
print()

# ── Split ────────────────────────────────────────────────────────────
train = df.iloc[:TRAIN_ROWS].copy()
test  = df.iloc[TRAIN_ROWS:TRAIN_ROWS+TEST_ROWS].copy()
oos   = df.iloc[TRAIN_ROWS+TEST_ROWS:].copy()

# ── Train momentum model (pooled across symbols) ────────────────────
train_valid = train.dropna(subset=['ret_30', 'forward_30_ret'])
X_train = train_valid[['ret_30']].values
y_train = train_valid['forward_30_ret'].values

model = LinearRegression()
model.fit(X_train, y_train)
r2 = model.score(X_train, y_train)
print(f"Trained pooled linear model: forward_30 = {model.coef_[0]:.4f} × ret_30 + {model.intercept_:.4f}")
print(f"  R² (in-sample, {len(train_valid)} obs): {r2:.4f}")
print()

# ── Backtest engine ─────────────────────────────────────────────────
def backtest(partition_df, partition_name, model):
    """
    Walk through each bar chronologically.
    On each bar where we have ret_30 and atr, compute a prediction.
    If we're not in a trade for that symbol, check the signal.
    If signal, enter with:
      - direction: sign(predicted_return)
      - position_size: fixed 1 contract/unit
      - target_price: entry_price * (1 + TARGET_FRAC * predicted_return / 100 * direction)
      - stop_price: trailing stop at entry - direction * STOP_ATR_MULT * atr
    Max 1 trade per symbol per calendar week.
    """
    trades = []
    
    in_trade = {}   # symbol -> {entry_price, direction, target, stop, entry_ts, entry_row, high_since_entry, low_since_entry}
    weekly_trade_count = {}  # (symbol, week) -> count
    
    for idx, row in partition_df.iterrows():
        sym = row['symbol']
        ts = row['ts']
        week_key = (sym, row['week'])
        
        if week_key not in weekly_trade_count:
            weekly_trade_count[week_key] = 0
        
        # Skip bars without features
        if pd.isna(row['ret_30']) or pd.isna(row['atr']):
            continue
        
        direction = np.sign(model.predict([[row['ret_30']]])[0])
        pred_ret = model.predict([[row['ret_30']]])[0]
        
        # Skip tiny predictions (noise filter)
        if abs(pred_ret) < 0.1:
            direction = 0
        
        # Manage existing positions
        if sym in in_trade:
            pos = in_trade[sym]
            # Update trailing stop
            if direction > 0:  # long
                pos['high_since_entry'] = max(pos['high_since_entry'], row['high'])
                pos['stop'] = pos['high_since_entry'] - STOP_ATR_MULT * row['atr']
            else:  # short
                pos['low_since_entry'] = min(pos['low_since_entry'], row['low'])
                pos['stop'] = pos['low_since_entry'] + STOP_ATR_MULT * row['atr']
            
            # Check exit conditions
            exit_reason = None
            
            # Check stop
            if direction > 0 and row['low'] <= pos['stop']:
                exit_reason = 'stop'
            elif direction <= 0 and row['high'] >= pos['stop']:
                exit_reason = 'stop'
            
            # Check target
            if direction > 0 and row['high'] >= pos['target']:
                exit_reason = 'target'
            elif direction <= 0 and row['low'] <= pos['target']:
                exit_reason = 'target'
            
            # Time-based exit: hold max 30 bars
            bars_held = idx - pos['entry_row']
            if bars_held >= RET_PERIOD:
                exit_reason = 'timeout'
            
            if exit_reason:
                exit_price = None
                if exit_reason == 'target':
                    exit_price = pos['target']
                elif exit_reason == 'stop':
                    exit_price = pos['stop']
                else:  # timeout
                    exit_price = row['close']
                
                pnl = (exit_price - pos['entry_price']) * direction
                ret_pct = pnl / pos['entry_price'] * 100
                
                trades.append({
                    'symbol': sym,
                    'entry_date': pos['entry_ts'].date(),
                    'exit_date': ts.date(),
                    'direction': 'LONG' if pos['direction'] > 0 else 'SHORT',
                    'entry_price': pos['entry_price'],
                    'exit_price': exit_price,
                    'pnl_pct': ret_pct,
                    'pnl_points': pnl,
                    'exit_reason': exit_reason,
                    'partition': partition_name,
                    'bars_held': bars_held,
                    'predicted_return': pos.get('pred_ret', 0),
                })
                del in_trade[sym]
        
        # Entry logic
        if sym not in in_trade and direction != 0:
            if weekly_trade_count.get(week_key, 0) >= MAX_TRADES_PER_SYMBOL_PER_WEEK:
                continue
            
            entry_price = row['close']
            pos_direction = 1 if direction > 0 else -1
            target_price = entry_price * (1 + TARGET_FRAC * pred_ret / 100 * pos_direction)
            stop_price = entry_price - pos_direction * STOP_ATR_MULT * row['atr']
            
            # Ensure stop is on the right side
            if pos_direction > 0:
                stop_price = min(stop_price, entry_price * 0.95)  # cap at 5% below entry
                stop_price = entry_price - STOP_ATR_MULT * row['atr']
                target_price = max(target_price, entry_price * 1.001)
            else:
                stop_price = max(stop_price, entry_price * 1.05)  # cap at 5% above entry  
                stop_price = entry_price + STOP_ATR_MULT * row['atr']
                target_price = min(target_price, entry_price * 0.999)
            
            in_trade[sym] = {
                'direction': pos_direction,
                'entry_price': entry_price,
                'target': target_price,
                'stop': stop_price,
                'entry_ts': ts,
                'entry_row': idx,
                'high_since_entry': row['high'],
                'low_since_entry': row['low'],
                'pred_ret': pred_ret,
            }
            weekly_trade_count[week_key] = weekly_trade_count.get(week_key, 0) + 1
    
    # Close any open trades at end of partition
    for sym, pos in list(in_trade.items()):
        trades.append({
            'symbol': sym,
            'entry_date': pos['entry_ts'].date(),
            'exit_date': partition_df.iloc[-1]['ts'].date(),
            'direction': 'LONG' if pos['direction'] > 0 else 'SHORT',
            'entry_price': pos['entry_price'],
            'exit_price': partition_df.iloc[-1]['close'],
            'pnl_pct': (partition_df.iloc[-1]['close'] - pos['entry_price']) / pos['entry_price'] * 100 * pos['direction'],
            'pnl_points': (partition_df.iloc[-1]['close'] - pos['entry_price']) * pos['direction'],
            'exit_reason': 'end_of_partition',
            'partition': partition_name,
            'bars_held': len(partition_df) - pos['entry_row'],
            'predicted_return': pos.get('pred_ret', 0),
        })
    
    return pd.DataFrame(trades) if trades else pd.DataFrame()


print("─" * 60)
print("BACKTESTING")

# In-sample (train period)
train_trades = backtest(train, 'TRAIN', model)
print(f"\nTRAIN period trades: {len(train_trades)}")

# Test period
test_trades = backtest(test, 'TEST', model)
print(f"TEST period trades: {len(test_trades)}")

# OOS holdout
oos_trades = backtest(oos, 'OOS', model)
print(f"OOS holdout trades: {len(oos_trades)}")

all_trades = pd.concat([train_trades, test_trades, oos_trades], ignore_index=True)

# ── Metrics ─────────────────────────────────────────────────────────
def compute_metrics(trades_df, label):
    if trades_df.empty or len(trades_df) == 0:
        print(f"\n{'='*60}")
        print(f"{label} — NO TRADES")
        print(f"{'='*60}")
        return
    
    total_pnl = trades_df['pnl_points'].sum()
    wins = trades_df[trades_df['pnl_points'] > 0]
    losses = trades_df[trades_df['pnl_points'] <= 0]
    win_rate = len(wins) / len(trades_df) * 100 if len(trades_df) > 0 else 0
    gross_profit = wins['pnl_points'].sum() if len(wins) > 0 else 0
    gross_loss = abs(losses['pnl_points'].sum()) if len(losses) > 0 else 1e-10
    profit_factor = gross_profit / gross_loss if gross_loss != 0 else float('inf')
    
    # Max drawdown on cumulative PnL
    cum_pnl = trades_df['pnl_points'].cumsum().values
    peak = np.maximum.accumulate(cum_pnl)
    dd = cum_pnl - peak
    max_dd = abs(dd.min())
    
    # Sharpe-like (assuming 0 risk-free)
    returns = trades_df['pnl_pct'].values
    sharpe = np.mean(returns) / np.std(returns) * np.sqrt(252 / np.mean(trades_df['bars_held'])) if np.std(returns) > 0 and len(returns) > 1 else 0
    # Actually let's compute a daily-equivalent Sharpe from per-trade returns
    # For simplicity, annualized Sharpe = mean(pnl_pct) / std(pnl_pct) * sqrt(252 / avg_holding_days)
    avg_hold = trades_df['bars_held'].mean()
    sharpe = (np.mean(returns) / np.std(returns) * np.sqrt(252 / avg_hold)) if np.std(returns) > 0 and len(returns) > 1 and avg_hold > 0 else 0
    
    print(f"\n{'='*60}")
    print(f"{label} — RESULTS")
    print(f"{'='*60}")
    print(f"  Total trades:          {len(trades_df)}")
    print(f"  Total P&L (points):    {total_pnl:+.2f}")
    print(f"  Win rate:              {win_rate:.1f}%")
    print(f"  Profit factor:         {profit_factor:.2f}")
    print(f"  Max drawdown (pts):    {max_dd:.2f}")
    print(f"  Sharpe (annualized):   {sharpe:.2f}")
    print(f"  Avg hold (bars):       {avg_hold:.1f}")
    print(f"  Avg win:               {trades_df[trades_df['pnl_points']>0]['pnl_points'].mean():+.2f}" if len(wins)>0 else "  Avg win:               N/A")
    print(f"  Avg loss:              {trades_df[trades_df['pnl_points']<=0]['pnl_points'].mean():+.2f}" if len(losses)>0 else "  Avg loss:              N/A")
    print(f"  Best trade:            {trades_df['pnl_points'].max():+.2f}")
    print(f"  Worst trade:           {trades_df['pnl_points'].min():+.2f}")
    print(f"  Predicted ret range:   {trades_df['predicted_return'].min():+.2f}% to {trades_df['predicted_return'].max():+.2f}%")
    
    # Direction breakdown
    longs = trades_df[trades_df['direction'] == 'LONG']
    shorts = trades_df[trades_df['direction'] == 'SHORT']
    if len(longs) > 0:
        print(f"\n  Longs:  {len(longs)} trades, P&L: {longs['pnl_points'].sum():+.2f}, WR: {len(longs[longs['pnl_points']>0])/len(longs)*100:.1f}%")
    if len(shorts) > 0:
        print(f"  Shorts: {len(shorts)} trades, P&L: {shorts['pnl_points'].sum():+.2f}, WR: {len(shorts[shorts['pnl_points']>0])/len(shorts)*100:.1f}%")
    
    # Exit reason breakdown
    for reason in trades_df['exit_reason'].unique():
        subset = trades_df[trades_df['exit_reason'] == reason]
        print(f"  Exit '{reason}': {len(subset)} trades, P&L: {subset['pnl_points'].sum():+.2f}")
    
    # Symbol breakdown
    for sym in trades_df['symbol'].unique():
        subset = trades_df[trades_df['symbol'] == sym]
        print(f"  Symbol {sym}: {len(subset)} trades, P&L: {subset['pnl_points'].sum():+.2f}, WR: {len(subset[subset['pnl_points']>0])/len(subset)*100:.1f}%")


# Print results
compute_metrics(train_trades, 'IN-SAMPLE (TRAIN)')
compute_metrics(test_trades, 'TEST (WALKFORWARD)')
compute_metrics(oos_trades, 'OOS HOLDOUT')
compute_metrics(all_trades, 'ALL TRADES (COMBINED)')

print()
print("─" * 60)
print("SUMMARY TABLE")
print("─" * 60)
print(f"{'Period':<20} {'Trades':>7} {'P&L':>10} {'WinRate':>8} {'PF':>7} {'MaxDD':>8} {'Sharpe':>8}")
print(f"{'─'*20} {'─'*7} {'─'*10} {'─'*8} {'─'*7} {'─'*8} {'─'*8}")

def summary_row(trades_df, label):
    if trades_df.empty or len(trades_df) == 0:
        print(f"{label:<20} {'0':>7} {'—':>10} {'—':>8} {'—':>7} {'—':>8} {'—':>8}")
        return
    total_pnl = trades_df['pnl_points'].sum()
    wins = trades_df[trades_df['pnl_points'] > 0]
    losses = trades_df[trades_df['pnl_points'] <= 0]
    win_rate = len(wins) / len(trades_df) * 100
    gp = wins['pnl_points'].sum() if len(wins) > 0 else 0
    gl = abs(losses['pnl_points'].sum()) if len(losses) > 0 else 1e-10
    pf = gp / gl if gl != 0 else float('inf')
    cum = trades_df['pnl_points'].cumsum().values
    peak = np.maximum.accumulate(cum)
    mdd = abs((cum - peak).min())
    rets = trades_df['pnl_pct'].values
    avg_hold = trades_df['bars_held'].mean()
    sharpe = (np.mean(rets) / np.std(rets) * np.sqrt(252 / avg_hold)) if np.std(rets) > 0 and avg_hold > 0 else 0
    print(f"{label:<20} {len(trades_df):>7} {total_pnl:>+9.1f} {win_rate:>7.1f}% {pf:>6.2f} {mdd:>7.1f} {sharpe:>7.2f}")

summary_row(train_trades, 'TRAIN (in-sample)')
summary_row(test_trades, 'TEST (walkforward)')
summary_row(oos_trades, 'OOS holdout')
print(f"{'─'*20} {'─'*7} {'─'*10} {'─'*8} {'─'*7} {'─'*8} {'─'*8}")
summary_row(all_trades, 'ALL COMBINED')

print()
print("Top 5 best trades:")
if len(all_trades) > 0:
    for _, t in all_trades.nlargest(5, 'pnl_points').iterrows():
        print(f"  {t['symbol']:4s} {t['direction']:5s} {str(t['entry_date']):>10s} → {str(t['exit_date']):>10s} "
              f"P&L={t['pnl_points']:+7.1f} ({t['exit_reason']})")

print()
print("Bottom 5 worst trades:")
if len(all_trades) > 0:
    for _, t in all_trades.nsmallest(5, 'pnl_points').iterrows():
        print(f"  {t['symbol']:4s} {t['direction']:5s} {str(t['entry_date']):>10s} → {str(t['exit_date']):>10s} "
              f"P&L={t['pnl_points']:+7.1f} ({t['exit_reason']})")
