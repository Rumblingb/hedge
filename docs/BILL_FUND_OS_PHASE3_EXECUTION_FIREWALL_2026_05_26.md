# Bill Fund OS Phase 3 — Execution Firewall

Date: 2026-05-26

## Decision

Bill/Hermes is in research-and-shadow mode until the execution firewall passes. The current stack has promising candidates, but the latest research contract says `reject-current-stack`; that result is authoritative.

The fund architecture is now:

1. Research agents discover ideas, papers, YouTube notes, external data, and single-variable hypotheses.
2. Backtrader/Rust/TypeScript test the idea with costs, OOS splits, walk-forward, and prop-firm constraints.
3. Only deterministic execution code can route a trade.
4. LLMs may summarize, queue, and audit. They do not trade.

## Safety Changes Applied

- Disabled the loaded launchd execution services:
  - `com.agentpay.bill.strategy-engine-runner`
  - `com.agentpay.bill.gengar-execution`
- Left monitor-only jobs running.
- Patched `src/live/signalRouter.ts` so it is default-deny unless all explicit execution env flags are set.
- Patched `src/prediction/gengarExecutionWatcher.ts` so Polymarket execution is dry-run unless live prediction mode is explicitly enabled.
- Patched `ops/start-gengar-live.sh` to remove the hard-coded private key and require a secure env key before live mode.
- Patched `/Users/brain/.hermes/scripts/topstep_demo_bridge.py` so it honors read-only/demo env gates before broker auth and blocks stale Topstep position state.
- Paused agent-backed prediction-market cron jobs that could wake agents into execution-adjacent work.

## Current Evidence

Futures:

- `strategy-research-contracts.latest.json`: `reject-current-stack`.
- `walkforward-matrix.latest.json`: no robust config count.
- `live-readiness.latest.json`: not deployable.
- `backtrader-research.latest.json`: best current row is `wq-vol-regime-60m`, 1 MNQ, 16-point stop, 32-point target, +32.4406R research result. This is a candidate, not a deployment approval.
- ORB has a useful contradiction: older Rust/time-exit evidence looked better than Backtrader/OCO evidence. Treat as research-only until reconciled.

Prediction markets:

- Gengar BTC oracle-lag bucket calibration is the strongest candidate.
- Polymarket/Kalshi exact-contract arb currently has no executable candidates.
- Raw websocket trade-side inference is quarantined unless confirmed by quote reaction or on-chain fill evidence.
- Live prediction execution is disabled; paper/shadow only.

## Keep

- `wq-vol-regime-60m` as the primary futures candidate.
- Backtrader as independent bracket/OCO reproduction.
- Rust as fast sweep engine.
- TypeScript gates as promotion authority.
- Obsidian/Hermes as memory and narrative, not broker truth.
- Prediction-market research as a separate lane, especially BTC oracle-lag calibration.

## Quarantine

- Any strategy promoted only by notes, screenshots, Discord excitement, or one in-sample sweep.
- ORB route expansion until OCO-style replay explains the cross-engine mismatch.
- DOM-from-OHLCV claims as order-flow evidence. They may be context features, not tape truth.
- Whale/COT/flow jobs that output neutral fallback data while sounding confident.
- Agent-backed execution watchers.
- Mixed Topstep account IDs until broker reconciliation is complete.

## Next Tests

1. Futures: run a target-only comparison for `wq-vol-regime-60m` with fixed 1 MNQ and 16-point stop; targets 24 vs 32 points; require rolling OOS.
2. Futures: reconcile ORB by running identical entries with time exit vs OCO bracket exit.
3. Futures: split volatility, volume, and NY-session buckets without retuning every variable together.
4. Prediction markets: calibrate Polymarket BTC up/down by exact expiry bucket and `spot_mom_3bar`; separate train/test by date.
5. Prediction markets: rebuild fillability checks before any paper candidate is considered real.

## Reopen Conditions

Topstep demo can reopen only when all are true:

- Broker confirms flat or current position is reconciled.
- Account label and numeric account ID are consistent across bridge, risk state, and broker response.
- `RH_TOPSTEP_READ_ONLY=false` only after the audit checklist passes.
- `BILL_ENABLE_FUTURES_DEMO_EXECUTION=true` only for the deterministic bridge, not agent-backed routers.
- Latest candidate passes the strategy research contract, live-readiness gate, and broker-style dry-run.
- Max size remains 1 MNQ until 20 broker-confirmed demo trades are clean.

## Agent Handoff Rule

When a weaker agent touches this system, it must start with:

1. `docs/research/README.md`
2. `docs/BILL_FUND_OS_PHASE3_EXECUTION_FIREWALL_2026_05_26.md`
3. `.rumbling-hedge/state/strategy-research-contracts.latest.json`
4. `.rumbling-hedge/state/topstep-100k-monitor.latest.json`
5. `.rumbling-hedge/state/bill-prediction-data-audit.latest.json` if present

If any of those say blocked, the agent may research or backtest only.
