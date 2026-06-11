# Alpha Research — Sessions × RR × Options (2026-06-11, Fable session)

Continuation of the Fable 5 research line (options, ES, GC, NQ — session timing + RR).
Artifacts: `ai-scientist-templates/financial_strategy/run_f5_*`,
`.rumbling-hedge/state/research-session-orb.latest.json`,
`.rumbling-hedge/state/options/vrp-put-spreads.latest.json`.

## 1. NQ ORB 3m — bracket geometry VALIDATED (first time)

The blessed edge `nq-orb-3m-vt16` (PF 3.245) was verified with **time exits only**;
live execution uses 1.0 ATR stop + RR target brackets that research never tested.
Full harness (vt 1.6, tf-agreement, NY sessions), NQ 1m 3yr, 5-fold WF:

| take_profit_rr | train PF (n=320) | OOS PF (n=138) | OOS WR |
|---|---|---|---|
| 1.5 | 2.60 | 2.51 | 69.6% |
| 2.0 (live) | 2.92 | 2.92 | 68.1% |
| 2.5 | 3.45 | 2.87 | 65.2% |
| 3.0 | 3.83 | 3.19 | 65.2% |

**Conclusion:** live 1.0 ATR / 2RR geometry holds the edge (OOS PF 2.92). RR is a
plateau, not a cliff — 2.0–3.0 all fine; slight preference for 2.5–3.0 if anything.
No change required to live brackets.

## 2. London / Asia ORB on NQ — NO EDGE (kill recommendation)

Blessed evidence is ny_morning/ny_afternoon only (London explicitly skipped in the
verifying run). Live, however, `BILL_LONDON_TRADING_ENABLED=true` /
`BILL_ASIA_TRADING_ENABLED=true` and the 2026-06-11 plan approved both routes.
Both campaign losses to date were London-session fills.

Faithful backtest of the live London ORB spec (15-min range from 07:00 UTC,
entries to 12:00 UTC; Asia anchored 23:00 UTC), NQ 1m 3yr, cost 1.5 pts:

| session | exit | all PF (n) | OOS PF (n) |
|---|---|---|---|
| london | time exit 18 bars | 0.76 (766) | 0.72 (230) |
| london | 1.0 ATR / 2RR (live) | 0.48 (766) | 0.54 (230) |
| asia | time exit 18 bars | 0.62 (765) | 0.75 (230) |
| asia | 1.0 ATR / 2RR (live) | 0.30 (765) | 0.46 (230) |
| ny (raw, no filters) | time exit | 0.96 (735) | 1.01 (221) |

NY raw ≈ breakeven confirms the prior finding that the volume filter + timeframe
agreement is what creates the NY edge; London/Asia are negative even before the
live bracket geometry makes them worse.

**Recommendation (operator decision, not applied):** revoke
`BILL_LONDON_ROUTE_APPROVAL` / `BILL_ASIA_ROUTE_APPROVAL` in the daily plan and set
`BILL_LONDON_TRADING_ENABLED=false`, `BILL_ASIA_TRADING_ENABLED=false` until a
London-specific edge passes the blessed-edge bar. Expected effect: removes the
strategy class responsible for 2/2 campaign losses.

## 3. ES ORB 15m — brackets DESTROY the edge (Lane B risk)

Registered ES ORB 15m evidence (PF 1.385, 538 trades) is time-exit based. Same
harness with live-style brackets (ES 1m 20yr):

| take_profit_rr | train PF (n=872) | OOS PF (n=374) |
|---|---|---|
| 1.5 | 0.09 | 0.62 |
| 2.0 | 0.10 | 0.69 |
| 2.5 | 0.09 | 0.73 |

**Conclusion:** ES ORB 15m is only viable with its researched time exit (4-bar /
60 min hold). Lane B (MES forward test, approved today) must use time exits, not
ATR/RR brackets. If `es_orb_lane_bridge.py` submits OCO brackets, Lane B is
trading an unverified-negative configuration. Verify before next Lane B fill.

## 4. Options lane — first real backtest: SPX put credit spread VRP

Data caveat found: `combined_options_data.csv` is Excel-truncated at 2^20 rows —
actual coverage 2010-01..2013-08 (not 2010-2023 as labeled), day-first dates.
Weekly entry, short ~30Δ/long ~15Δ (and 20Δ/10Δ) puts, conservative fills
(short@bid, long@ask), hold to expiry. Train <2012-07, OOS after:

| DTE | deltas | all PF (n) | OOS PF (n) | WR |
|---|---|---|---|---|
| 30 | 30/15 | 1.78 (131) | 2.81 (54) | 87% |
| 30 | 20/10 | 1.97 (130) | 7.28 (53) | 92% |
| 45 | 30/15 | 1.84 (104) | 2.05 (30) | 87% |
| 45 | 20/10 | 2.04 (104) | 2.43 (30) | 93% |
| 14 | any | ~1.0 | — | — |

**Conclusion:** classic VRP harvest shows up cleanly at 30-45 DTE; 14 DTE is noise
after spreads. NOT promotable: sample is a 2010-2013 bull window with no crisis
regime (worst single loss -51 vs avg +2 — tail risk is the whole question).
Next steps: (a) acquire post-2013 chains incl. 2020 crash + 2022 bear,
(b) VIX-regime conditioning is in the artifact (terciles), use it once crisis data
exists, (c) options need a non-Topstep account (Tastytrade/IBKR/Tradier).

## 5. GC

No new GC runs this session (GC vol_regime stays not-topstep-tradeable; PJI
signal generator already live). GC session work is the next research slot.
