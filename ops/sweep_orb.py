#!/usr/bin/env python3
"""
orb-breakout parameter optimization sweeper.
Tests different range windows, volume thresholds, and exit offsets.
"""
from hermes_tools import terminal
import re
import json

# Base CSV paths
CSVS = {
    "15m": "../data/free/ALL-2MARKETS-NQ-ES-1m-21d-normalized-15m.csv",
    "30m": "../data/free/ALL-2MARKETS-NQ-ES-1m-21d-normalized-30m.csv",
    "5m": "../data/free/ALL-2MARKETS-NQ-ES-1m-21d-normalized-5m.csv",
}

# Parameters to sweep
ORB_WINDOWS = [8, 10, 12, 14, 16, 20]
VOL_THRESHOLDS = [1.2, 1.3, 1.5, 2.0, 2.5]
EXIT_OFFSETS = [3, 5, 8]

results = []

for tf_name, csv_path in CSVS.items():
    for window in ORB_WINDOWS:
        for vol_thresh in VOL_THRESHOLDS:
            for exit_n in EXIT_OFFSETS:
                label = f"orb_w{window}_v{vol_thresh}_e{exit_n}"
                print(f"\n=== {tf_name} / {label} ===")
                
                # Currently the binary compiles with hardcoded params.
                # For real param sweep, we need to modify the source and recompile.
                # For now, use the precompiled binary with different strategies.
                # The binary has orb-breakout hardcoded with window=12, vol=1.3, exit=5
                
                # Since we can't easily param-sweep without modifying source,
                # let's parse the baseline results we already have
                
                cmd = f"cd /Users/brain/hedge/bill-core && cargo run --bin full_strategy_pipeline -- '{csv_path}' 2>&1 | grep 'orb-breakout'"
                out = terminal(cmd, timeout=180)
                
                break  # one iteration for now — will build full sweep after modifying source
            break
        break
    break

print("\nBaseline orb-breakout results captured. Source modification needed for param sweep.")
