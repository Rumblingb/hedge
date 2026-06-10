#!/usr/bin/env python3
"""Fable 5 Metaprompt — Comprehensive Foundation + Execution Priorities
Run this first each session to load context. Then execute the highest-priority action.

P0: KEEP DEMO RUNNING — NQ ORB 3m verified, promoted, bridge fires every 15min
P1: INTEGRATE NQ QUANT V4 ENGINE as arbitration signal #14 (PF 3.53, 0/11 neg yrs)
P2: BUILD opening stop-hunt reversal strategy
P3: BUILD post-news settlement continuation strategy
P4: GOLD vol_regime on personal account (overnight holds, not Topstep)

SYSTEM CONTEXT:
  Mode: demo (BILL_ENABLE_FUTURES_DEMO_EXECUTION=true)
  Bridge: enabled, fires */15 during RTH
  Accounts: 22983191 (DEMO 100K), 23268236 (TEST 50K A), 23536817 (TEST 50K B), 23665193 (LIVE)
  Session safety: resolved (xbar plugin disabled, launchd unloaded, redundant crons paused)
  Data: TradingView WS keeps realtime-quote fresh (<60s). No TopstepX connection needed.
  All safety gates: PASS

UNUSED ASSETS (integrate for P1-P4):
  1. external/nq-quant/experiments/unified_engine_1m.py — V4 engine, PF 3.53, 10.3yr backtest
  2. external/nq-quant/experiments/ — 80+ experiment scripts (FVG, displacement, ML, XGBoost)
  3. external/prediction-market-analysis/ — full polymarket analysis toolkit
  4. data/free/GC-* — 22+ years of gold data (daily back to 1975, hourly, minute)
  5. .rumbling-hedge/research/founder-notes/strategy-directives.latest.json — 9 strategies

STRATEGY DIRECTIVES (from Apple Notes, priority order):
  1. opening-stop-hunt — 5min ORB stop hunt, RTH only, max 30min hold
  2. post-news-settlement — news spike → volume dry-up → continuation
  3. tail-score-risk-gate — VIX + COT + capitulation context gate
  4. fomc-reaction-fade — initial headline spike → revert
  5. opex-gamma-pin — options expiry, needs options chain data

LENOVO HERMES:
  Host: 192.168.1.100 (unreachable during this session)
  Runs: separate Hermes instance, SSH's to Mac for compute
  When back: check ~/ops/mac-mini/ for scripts, launchd for services
"""

import json, sys
from pathlib import Path

ROOT = Path.home() / "hedge"
STATE = ROOT / ".rumbling-hedge" / "state"

def status():
    """Print current system state for Fable's context window."""
    s = {
        "mode": "demo",
        "bridge": "enabled",
        "accounts": 4,
        "promoted_edges": ["nq-orb-3m-vt16"],
        "unused_engines": ["nq-quant-v4 (PF 3.53)", "prediction-market-analysis"],
        "next_actions": ["integrate-nq-quant-signal", "opening-stop-hunt", "gold-personal-account"],
    }
    print(json.dumps(s, indent=2))

if __name__ == "__main__":
    status()
