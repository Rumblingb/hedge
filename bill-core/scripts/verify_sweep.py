#!/usr/bin/env python3
"""Quick verification: compare Python reimplementation vs Rust binary output."""
import sys
sys.path.insert(0, '/Users/brain/hedge/bill-core/scripts')
from param_sweep import load_bars, sweep_orb_breakout, sweep_wq_trend_mom, sweep_wq_vol_regime, report

# Test orb-breakout with default params on 15m
bars = load_bars('/Users/brain/hedge/data/free/ALL-2MARKETS-NQ-ES-1m-21d-normalized-15m.csv', 'NQ')
print(f"Loaded {len(bars)} bars (15m, NQ)")

# Default orb-breakout: rw=12, vt=1.3, eo=8
trades_orb = sweep_orb_breakout(bars, {'range_window': 12, 'vol_threshold': 1.3, 'exit_offset': 8})
report(trades_orb, "orb-breakout default (rw=12,vt=1.3,eo=8)")
print(f"  Rust says: 485 trades, total R 385.21")
print(f"  Python says: {len(trades_orb)} trades, total R {sum(t.r_multiple for t in trades_orb):.2f}")
print()

# Default wq-trend-mom: ss=20, sl=50, vt=1.3, eo=8
trades_trend = sweep_wq_trend_mom(bars, {'sma_short': 20, 'sma_long': 50, 'vol_threshold': 1.3, 'exit_offset': 8})
report(trades_trend, "wq-trend-mom default (ss=20,sl=50,vt=1.3,eo=8)")
print(f"  Rust says: 295 trades, total R 130.46")
print(f"  Python says: {len(trades_trend)} trades, total R {sum(t.r_multiple for t in trades_trend):.2f}")
print()

# Default wq-vol-regime: sl=10, ll=30, st=1.5, lt=0.7, eo=5
trades_vol = sweep_wq_vol_regime(bars, {'short_lookback': 10, 'long_lookback': 30, 'short_threshold': 1.5, 'long_threshold': 0.7, 'exit_offset': 5})
report(trades_vol, "wq-vol-regime default (sl=10,ll=30,st=1.5,lt=0.7,eo=5)")
print(f"  Rust says: 484 trades, total R 47.11")
print(f"  Python says: {len(trades_vol)} trades, total R {sum(t.r_multiple for t in trades_vol):.2f}")
