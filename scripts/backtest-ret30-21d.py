#!/usr/bin/env python3
import sys

with open("/Users/brain/hedge/scripts/backtest-ret30.py") as f:
    code = f.read()

code = code.replace(
    'DATA = "/Users/brain/hedge/data/free/ALL-2MARKETS-NQ-ES-1m-5d-normalized.csv"',
    'DATA = "/Users/brain/hedge/data/free/ALL-2MARKETS-NQ-ES-1m-21d-normalized.csv"'
)
exec(code)
