#!/usr/bin/env python3
"""Fable 5 Metaprompt — Comprehensive Foundation + Execution Priorities
Run this first each session to load context. Then execute the highest-priority action.

CORE PHILOSOPHY: Every small edge compounds. Even PF 1.2 edges contribute to
arbitration consensus. Don't ignore ES, GC, CL just because NQ is stronger.

P0: KEEP DEMO RUNNING — NQ ORB 3m verified, promoted, bridge fires every 15min
P1: BUILD GC SIGNAL GENERATORS — GC PJI (100% WF, PF 1.586) + GC vol_regime (80% WF, PF 3.07)
P2: BUILD ES ORB 15M SIGNAL — PF 1.385, 538 trades, contributes to arbitration
P3: INTEGRATE NQ QUANT V4 ENGINE as arbitration signal (PF 3.53, 0/11 neg yrs)
P4: GOLD vol_regime on personal account (overnight holds, not Topstep)

ALL INSTRUMENTS STATUS:
  NQ: 4 edges (ORB 3m lead, VWAP 15m, ORB 5m, ORB 45m) — demo running
  GC: 3 edges (PJI 100% WF, vol 80% WF, vol 60% WF) — READY FOR SIGNAL GENERATORS
  ES: 1 edge (ORB 15m, 538 trades, PF 1.385) — READY FOR SIGNAL GENERATOR
  CL: dead for VWAP/ORB
  ZN: dead for ORB
  6E: dead for VWAP

SYSTEM CONTEXT:
  Mode: demo (BILL_ENABLE_FUTURES_DEMO_EXECUTION=true)
  Bridge: enabled, fires */15 during RTH
  Signals: 21 total (orb, nq-quant, es-orb, 4 GC, 2 session, 12 legacy)
  Accounts: 22983191 (DEMO 100K), 23268236 (TEST 50K A), 23536817 (TEST 50K B), 23665193 (LIVE)
  Session safety: resolved (xbar plugin disabled, launchd unloaded, redundant crons paused)
  Data: TradingView WS keeps realtime-quote fresh (<60s). No TopstepX connection needed.

UNUSED ASSETS:
  1. external/nq-quant/experiments/unified_engine_1m.py — V4 engine, PF 3.53, 10.3yr backtest
  2. external/nq-quant/experiments/ — 80+ experiment scripts (FVG, displacement, ML, XGBoost)
  3. external/prediction-market-analysis/ — full polymarket analysis toolkit
  4. data/free/GC-* — 22+ years of gold data (daily back to 1975, hourly, minute)
  5. .rumbling-hedge/research/founder-notes/strategy-directives.latest.json — 9 strategies

NEXT ACTIONS FOR FABLE:
  1. Create signal generators for GC PJI + GC vol_regime (read AI Scientist run results, write signal files)
  2. Create ES ORB 15m signal generator (538 trades, PF 1.385 — real volume)
  3. Wire NQ Quant V4 engine to produce live signals
  4. Build opening stop-hunt reversal strategy
  5. Build post-news settlement continuation strategy
"""

import json, sys
from pathlib import Path

ROOT = Path.home() / "hedge"
STATE = ROOT / ".rumbling-hedge" / "state"

def status():
    s = {
        "mode": "demo",
        "bridge": "enabled",
        "signals": 21,
        "promoted": ["nq-orb-3m-vt16"],
        "gc_edges": ["pji-100pct-wf", "vol-80pct-wf", "vol-60pct-wf"],
        "es_edges": ["orb-15m-538trades"],
        "philosophy": "every small edge compounds through arbitration",
    }
    print(json.dumps(s, indent=2))

if __name__ == "__main__":
    status()
