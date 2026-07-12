#!/usr/bin/env python3
"""Run v3 backtest on the new 21-day data instead of 5-day."""
import sys
sys.path.insert(0, "/Users/brain/hedge/scripts")

# Read the backtest-v3.py and patch the DATA path
with open("/Users/brain/hedge/scripts/backtest-v3.py") as f:
    code = f.read()

code = code.replace(
    'DATA = "/Users/brain/hedge/data/free/ALL-2MARKETS-NQ-ES-1m-5d-normalized.csv"',
    'DATA = "/Users/brain/hedge/data/free/ALL-2MARKETS-NQ-ES-1m-21d-normalized.csv"'
)
exec(code)
