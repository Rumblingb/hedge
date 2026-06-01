# Topstep Closed-Loop Framework Plan - 2026-05-26

## Mission
Run the Topstep 100K demo for one full month as a prop-firm payout lab, not a signal firehose. The objective is a repeatable path toward consistent payouts: controlled MNQ risk, verified OCO brackets, daily broker reconciliation, walk-forward/OOS proof, and a research loop that promotes only strategies with live-demo evidence.

## Current Truth
- TopstepX direct demo bridge exists and OCO bracket payload is verified: SL bracket `type=4` Stop, TP bracket `type=1` Limit, signed ticks by side.
- Current route is `topstep_demo` only. Live production is not cleared.
- Guardrail monitor currently shows no hard blockers, but warns about a stale local position file that must not be treated as broker truth.
- Latest master signal: no entry conditions met across the active strategy/timeframe set.
- Live-readiness gate is blocked by uncommitted source changes, non-deployable walk-forward, thin rolling OOS, and failed stressed readiness.
- Strategy-zoo audit has 8 registered strategies in the current supported domain; execution remains disabled by design until gates pass.

## Immediate Code Findings Fixed
- `scripts/master_bridge.py` called `topstep_demo_bridge.py` before writing the current signal file. The bridge could read an old/null signal. Fixed by writing a pending signal first, then updating state after Topstep submission.
- Master bridge looked for the old phrase `ORDER SUBMITTED` and could mark a successful OCO submission as failed. Fixed by reading `topstep-demo-submission.latest.json` and matching `last_signal`.
- Master bridge advertised research sizing of 3-5 MNQ even though Topstep demo policy is max 1 MNQ. Fixed state/output to cap Topstep demo route at 1 MNQ while preserving research size separately.
- Topstep bridge duplicate detection never wrote `last_signal`. Fixed.
- Topstep bridge dry-run label still said TP type Market. Fixed to Limit.
- Fill checker reused `ts` for both check time and order timestamps. Fixed so logs use the actual check timestamp.
- Guardrail monitor expected `sl/tp`, while master signals use `stop/target`. Fixed to accept both shapes.

## Strategy Stack Decision

### Execution Lane: NY Session, MNQ Only
As of the phase-3 audit, no strategy is cleared for fresh Topstep demo expansion. The execution lane is locked until broker flatness, account ID reconciliation, and the research contract pass.

Current research priority order:
1. `wq-vol-regime` 60m — strongest cross-engine candidate, but still needs rolling OOS and broker-style replay confirmation before routing.
2. `orb-breakout` 30m/15m — keep in reconciliation only because Rust/time-exit and Backtrader/OCO results disagree.
3. `wq-trend-mom` 30m/60m — shadow only until OOS repairs the negative Backtrader evidence.

Do not route 1m/5m strategies despite high total R until drawdown and slippage replay prove they survive prop-firm rules. Their win rates and trade frequency make them too dangerous for a 1-trade/day payout campaign.

### Research Lane
Keep these shadow-only until independent filters and OOS pass:
- ICT displacement / opening stop hunt / liquidity reversion / session momentum
- DOM micro edges
- Kalman NQ/ES pairs
- Prediction-market-to-futures lead signals
- New external alpha features from Polymarket BTC, NQ Kaggle, S&P options regime, vol-regime datasets

## Backtest Framework
Use three engines, each with a distinct role:

1. Rust `bill-core`
   - Fast exhaustive sweeps and canonical strategy matrix.
   - Required outputs: trade list, R multiples, MAE/MFE, daily P&L, drawdown, consecutive losses, rule breaches.
   - Fix remaining latent bugs before trusting more sweeps: mixed-symbol point-value risk, gapper early-index underflow risk, and any strategy using fixed bar exits without bracket replay.

2. TypeScript Bill engine
   - Governance layer: promotion gates, strategy zoo, live readiness, no-edge ledger, macro/risk policies.
   - Required output: promotion decision with blockers, not just performance stats.

3. Backtrader Python harness
   - Independent replication layer, not the primary engine.
   - Use Backtrader `Cerebro`, analyzers, commission/slippage, OCO/bracket order simulation, and automated runner patterns to verify that Rust results are not an artifact.
   - Every promoted setup must have at least one Backtrader reproduction on the same CSV/parquet input.

Backtrader reference:
- https://github.com/mementum/backtrader
- https://www.backtrader.com/docu/automated-bt-run/automated-bt-run/

## Promotion Gates
A strategy can enter the Topstep demo lane only if all are true:
- Data max age within route window; no stale 5m/15m/30m inputs.
- Purged/walk-forward OOS positive in every evaluated window.
- Worst fold net R positive after fees/slippage.
- Deflated expectancy positive after multiple-testing penalty.
- Max consecutive loss streak survivable under Topstep daily drawdown.
- Bracket replay proves SL/TP distances are valid for MNQ tick size.
- Topstep demo bridge dry-run shows signed ticks and `type=4/type=1`.
- No overlap with no-edge ledger/quarantine blockers.

A strategy can scale beyond 1 MNQ only after:
- 20 broker-confirmed demo trades.
- No orphaned order, no duplicate route, no stale-data route.
- Positive net P&L after realistic fills.
- No daily drawdown breach.
- Best day under 40% of total profit for the 100K payout path.
- At least 5 trading days with stable execution.

## One-Month Demo Protocol
Week 1: execution-firewall validation
- Do not route a new demo trade until Topstep broker flatness and account ID reconciliation are confirmed.
- Run `wq-vol-regime` 60m, ORB, and `wq-trend-mom` in shadow/backtest only.
- One MNQ max once the gate reopens.
- One trade max per day once the gate reopens.
- Fixed bracket, no trail until stats prove trail improves expectancy.
- Confirm every fill and both OCO legs.

Week 2: controlled A/B
- Compare ORB 60m against `wq-vol-regime` 60m in shadow.
- Live-demo route still one strategy per day.
- Backtrader replication for the current champion.

Week 3: regime gating
- Add macro/vol regime overlay as a size/no-trade gate only.
- Test whether vol-regime overlay reduces losing streaks.
- No additional size unless week 1-2 broker results are clean.

Week 4: payout simulation
- Continue 1 MNQ unless all scale gates pass.
- Optimize for smooth daily progress, not max R.
- Stop for the day after one realized loss or first material platform anomaly.

## n8n/Hermes/Obsidian Loop
Current n8n is underbuilt: only a premarket workflow exists. Required workflows:

1. Topstep execution monitor
   - Trigger every 5-15 minutes during NY session.
   - Read broker open positions, orders, fills.
   - Alert if position exists without matching OCO legs.

2. Daily EOD reconciliation
   - Compare Topstep fills, operating log, risk state, and master signal state.
   - Write a compact Obsidian daily row: strategy, entry, exit, R, P&L, mistake, next action.

3. Strategy evidence board
   - Pull latest Rust sweep, Backtrader replication, TS gates, and demo fills.
   - Promote/demote strategies into `enabled`, `shadow`, `quarantine`.

4. Research intake
   - Weekly web/YT/paper scan creates hypotheses only.
   - No route changes unless the hypothesis receives a reproducible test artifact.

Hermes should be the narrator and escalator, not the source of broker truth. Broker API, state JSON, and operating log must be the source of truth.

## Prediction Markets / Gengar
Keep Gengar separate from Topstep execution, but let it contribute context:
- Prediction market BTC features can train Gengar directly.
- Prediction-market-to-futures signals may become a futures gate only after latency and calibration tests.
- Raw Polymarket websocket side is not truth; require quote-reaction or on-chain calibration.
- Micro-live sandbox stays capped; do not treat it as futures/live readiness.

## Required Build Next
P0:
- Add a single `topstep_closed_loop_status.py` that reads master signal, Topstep submission, fill check, monitor, operating log, and prints one status JSON.
- Add broker-order reconciliation: entry order must have exactly one SL and one TP bracket/tag pair.
- Add a Topstep-specific trade ledger JSONL, not only Markdown.
- Add Backtrader reproduction harness for ORB 60m/30m/15m with commission, slippage, bracket exits, analyzers.
- Fix/disable any cron still saying LucidFlex execution while founder intent is Topstep demo-only.

P1:
- Build `strategy_evidence_matrix.json`: Rust stats + TS gates + Backtrader stats + demo fills.
- Extend Rust backtests to emit trade-level CSV/JSONL and prop-firm metrics for 100K MNQ.
- Add data freshness repair for lower-timeframe NQ.
- Add n8n execution monitor + EOD reconciliation workflows.

P2:
- Integrate external alpha datasets as gates, not direct entries.
- Add MLflow/W&B-style experiment registry only after core ledgers are reliable.
- Move from file polling to an event bus later; not needed before the month-long demo is stable.

## Go / No-Go
Go for next demo trade:
- Topstep monitor hard blockers empty.
- Master signal fresh and includes side, entry, stop, target.
- Data feed fresh for that timeframe.
- Bridge writes `submitted=true` and matching `last_signal`.
- Fill checker confirms position/fill and OCO tags.

No-go:
- Any stale data route.
- Any missing OCO confirmation.
- Any duplicate signal.
- Any daily loss or one realized loss under current rules.
- Any mismatch between Topstep account label and numeric ID.
- Any live-readiness gate claim that ignores the current blockers.
