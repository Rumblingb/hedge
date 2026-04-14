# Rumbling Hedge

Rumbling Hedge is a guarded trading system for financial markets: prediction markets, futures, options, and crypto.

It is built around one principle: the agent can suggest tighter changes, but it does not get to loosen its own risk rails or silently rewrite live behavior mid-session.

## Canonical repo and Mac mini ops

This repo is now the canonical Bill codebase on the Mac mini.

Use the macOS-native operator layer in [`ops/mac-mini`](./ops/mac-mini):
- `npm run bill:doctor`
- `npm run bill:health`
- `npm run bill:cost-profile`
- `npm run bill:prediction-collect -- [source] [limit] [outPath]`
- `npm run bill:prediction-iterations -- [count]`
- `npm run bill:native-summary`
- `npm run bill:prediction-scan -- [snapshot.json]`
- `npm run bill:prediction-train -- [journalPath]`
- `npm run bill:prediction-report -- [journalPath]`
- `npm run bill:market-track-status`
- `npm run bill:research-collect`
- `npm run bill:research-report`
- `npm run bill:paper-loop -- [csvPath]`
- `npm run bill:live-readiness -- [csvPath] [iterations]`
- `npm run bill:kill-switch -- status`

Bill's autonomous source surface is emitted into `.rumbling-hedge/research/source-catalog.json`. It captures which free/free-tier finance and prediction APIs are already wired, which ones are cataloged for later integration, what config they need, and which tracks they improve.

The operating posture is stepwise:
- `prediction` and `futures-core` are the equal-first execution tracks.
- `options-us`, `crypto-liquid`, and `macro-rates` stay inside the domain as collection/training tracks until their own paper/demo promotion paths are ready.
- The system is not research-only. Prediction paper execution and futures demo/shadow execution stay part of the product, even while live permissions remain closed.

Bill's prediction loop now retrains a bounded learned scan policy on every scheduled cycle. The learned policy lives in `.rumbling-hedge/state/prediction-learned-policy.json`, the latest training state in `.rumbling-hedge/state/prediction-learning.latest.json`, and the per-cycle training inputs in `.rumbling-hedge/research/prediction-training-set.json`.

## What is in v0.1

- Topstep-approved hard guardrails encoded in code, not prompts
- Paper/backtest engine with one-position-at-a-time execution
- Strategy plugin seam for winner-inspired proxies
- News gate interface with a mock provider for simulation
- Offline evolution proposals that only tighten or disable behavior
- Journal + summary reporting

## What is intentionally not in v0.1

- Live Topstep order routing
- VPS deployment
- Mid-session self-modifying execution
- Unbounded LLM autonomy

## Quick start

```bash
npm install
npm run doctor
npm run context-drift
npm run inspect-csv -- ./path/to/minute-bars.csv
npm run fetch-free -- NQ 1m 5d
npm run fetch-free-universe -- 1m 5d
npm run data-quality -- data/free/ALL-6MARKETS-1m-5d.csv
npm run normalize-universe -- data/free/ALL-6MARKETS-1m-5d.csv
npm run oos-rolling -- data/free/ALL-6MARKETS-1m-5d.csv
npm run day-plan -- data/free/ALL-6MARKETS-1m-5d-normalized.csv
npm run dashboard -- data/free/ALL-6MARKETS-1m-5d-normalized.csv
npm run kill-switch -- status
npm run live-readiness -- data/free/ALL-6MARKETS-1m-5d-normalized.csv 3
npm run demo-tomorrow -- data/free/ALL-6MARKETS-1m-5d-normalized.csv 3
npm run sim
npm run research
npm run jarvis
npm run jarvis-loop
npm run jarvis-brief
npm run evolve
```

To run a CSV backtest:

```bash
npm run backtest -- ./path/to/minute-bars.csv
```

Real minute-bar CSVs are easiest when they use a header row. The loader accepts either a headered file or the legacy 7-column order, and it normalizes futures contract codes like `NQM26` or `ESM26` to root symbols (`NQ`, `ES`).

Expected columns:

```text
ts,symbol,open,high,low,close,volume
2026-04-01T13:30:00.000Z,NQ,18250,18253,18248,18252,1320
```

For the exact ingest shape, symbol handling, and demo-first workflow, see [Real Data Playbook](./docs/REAL_DATA_PLAYBOOK.md).

## Free data sources (implemented)

Use the new ingestion commands to fetch and write normalized CSVs directly into `data/free`.

Single symbol:

```bash
npm run fetch-free -- NQ 1m 5d
```

Universe batch (`NQ`, `ES`, `CL`, `GC`, `6E`, `ZN`) + combined CSV:

```bash
npm run fetch-free-universe -- 1m 5d
```

Provider options:

- `auto` (default): uses Yahoo first; for daily bars (`1d`) it can fall back to Stooq.
- `yahoo`: best free no-key source for short-window intraday futures bars.
- `stooq`: free no-key fallback for daily bars (`1d`) only.
- `polygon`: Polygon.io aggregates API (requires `RH_POLYGON_API_KEY`).

Examples:

```bash
npm run fetch-free -- ES 1d 1y ./data/free/ES-1d-1y.csv stooq
npm run fetch-free -- CL 1m 5d ./data/free/CL-1m-5d.csv yahoo
```

Production note:

- Free feeds are suitable for research iteration, but not final execution-grade truth.
- Keep your existing promotion gates strict and prefer longer OOS windows before deployment decisions.

Data-quality gate note:

- `research`, `jarvis`, `jarvis-loop`, and `oos-rolling` now enforce a dataset completeness gate for CSV input.
- To bypass temporarily for exploration only: `RH_ALLOW_INCOMPLETE_DATA=1`.

Rolling OOS iteration:

```bash
npm run oos-rolling -- data/free/ALL-6MARKETS-1m-5d.csv 4 2 1
```

Arguments: `csvPath [windows] [minTrainDays] [testDays]`.

Universe normalization (next-iteration data fix):

```bash
npm run normalize-universe -- data/free/ALL-6MARKETS-1m-5d.csv
npm run data-quality -- data/free/ALL-6MARKETS-1m-5d-normalized.csv
npm run oos-rolling -- data/free/ALL-6MARKETS-1m-5d-normalized.csv 4 2 1
npm run oos-rolling -- data/free/ALL-6MARKETS-1m-5d-normalized.csv 4 2 1 1
```

`normalize-universe` keeps only timestamps present across all symbols (inner join), which removes late/partial symbol tails and makes cross-symbol OOS evaluation more consistent.
The last `oos-rolling` argument is `embargoDays`, which creates a purged gap between train and test windows to reduce leakage/lookahead bias.

The demo research engine now tracks both gross and net performance. Net R includes configurable friction for fees, slippage, and a small stress haircut, so a strategy has to survive costs rather than just print clean gross backtests.
Research summaries also include per-symbol contribution breakdowns so you can see where the edge is actually coming from.
They also roll up into market-family summaries (`index`, `fx`, `energy`, `metal`, `bond`, `ag`, `crypto`) and a simple suggested focus list that prefers the strongest positive contributors.
Walk-forward research also returns a normalized family budget recommendation so you can see which market families should stay active in the next research pass.
`day-plan` turns the research output into an operator-facing answer for a specific session: which profile is selected, which strategies are enabled, which symbols are preferred, how the latest session is classified by regime, which strategy-symbol candidates rank highest on expected value, and whether the system should trade or stand down.
`dashboard` packages that into a live-ops snapshot with account safety flags, kill-switch state, journal summary, and recent trades so you can monitor the agent from one terminal pane.
`kill-switch` gives you a local force-stop file outside strategy logic. Use `npm run kill-switch -- on "reason"` to freeze the system and `npm run kill-switch -- off` after review.
Profile scoring is activity-aware, so profiles with very small out-of-sample sample size are penalized instead of floating to the top by default.
Research output now separates the top-ranked `winner` from a `deployableWinner` (first profile that actually passes promotion checks).
`npm run jarvis -- <csvPath>` returns an agentic-fund operations report with survivability score, current status, failed checks, and `learningActions` that suggest fixable next adjustments.
`npm run jarvis-loop -- <csvPath>` runs one autonomous improvement iteration: baseline diagnostics, safe application of `learningActions` env patches, and a tuned rerun with delta metrics.
`npm run jarvis-brief -- <csvPath> --note "..."` packages Jarvis into a K/main-friendly handoff: concise headline, recommended action, a prioritized K action queue, escalation triggers, a Rajiv-ready update draft, and stable machine context for a conversational layer.
Backtest and sim outputs now include rejected-signal telemetry (`rejectedReasonCounts` and `rejectedSignalRecords`) so failed entries can be analyzed systematically.
Jarvis and live-readiness outputs now include `agentStatus` and `evolutionPlan` so the engine explicitly tells you whether it is in stabilization or guarded-expansion mode.
`npm run risk-model -- <csvPath>` compares current execution, perfect/zero-friction execution, and stressed execution, then ranks RR buckets so you can see which slightly risky but good-RR trades survive best.

When `npm run research` uses synthetic data, it now builds bars from the union of all research profile universes instead of only the base config universe. That makes the profile comparison more representative of the full liquid-futures research mix.

Useful environment overrides:

- `RH_ACCOUNT_PHASE` (`challenge` or `funded`)
- `RH_FEE_R_PER_CONTRACT`
- `RH_SLIPPAGE_R_PER_SIDE`
- `RH_STRESS_MULTIPLIER`
- `RH_STRESS_BUFFER_R`
- `RH_TRAILING_MAX_DRAWDOWN_R`
- `RH_NEWS_BLACKOUT_MINUTES_BEFORE`
- `RH_NEWS_BLACKOUT_MINUTES_AFTER`
- `RH_EXECUTION_LATENCY_MS`
- `RH_EXECUTION_LATENCY_JITTER_MS`
- `RH_EXECUTION_SLIPPAGE_TICKS_PER_SIDE`
- `RH_EXECUTION_DATA_QUALITY_PENALTY_R`
- `RH_EXECUTION_SLIPPAGE_MODEL` (`ticks` or `dollars`)
- `RH_EXECUTION_RISK_PER_CONTRACT_USD`
- `RH_STOP_MGMT_ENABLED`
- `RH_BREAK_EVEN_TRIGGER_R`
- `RH_BREAK_EVEN_OFFSET_R`
- `RH_RUNNER_ENABLED`
- `RH_RUNNER_TRIGGER_R`
- `RH_RUNNER_TRAILING_DISTANCE_R`
- `RH_LIVE_EXECUTION_ENABLED`
- `RH_TOPSTEP_BASE_URL`
- `RH_TOPSTEP_USERNAME`
- `RH_TOPSTEP_ACCOUNT_ID`
- `RH_TOPSTEP_ALLOWED_ACCOUNT_ID`
- `RH_TOPSTEP_ALLOWED_ACCOUNT_LABEL`
- `RH_TOPSTEP_API_KEY`
- `RH_TOPSTEP_DEMO_ONLY`
- `RH_TOPSTEP_READ_ONLY`
- `RH_POLYGON_API_KEY`
- `RH_POLYGON_BASE_URL`
- `ALPHA_VANTAGE_API_KEY`
- `FINNHUB_API_KEY`
- `IEX_CLOUD_API_KEY`
- `OPENFIGI_API_KEY`
- `SEC_EDGAR_USER_AGENT`
- `DATABENTO_API_KEY`
- `ALPACA_API_KEY`
- `ALPACA_SECRET_KEY`
- `FRED_API_KEY`

`challenge` and `funded` use different default risk posture. The funded phase is intentionally tighter (contracts, daily trades, daily loss, consecutive losses, and minimum RR) to prioritize payout survivability.

Topstep / ProjectX safety posture:

- live integration defaults to `demo-only`
- live integration defaults to `read-only`
- if demo-only mode is enabled, the configured account must match `RH_TOPSTEP_ALLOWED_ACCOUNT_ID` or be a member of `RH_TOPSTEP_ALLOWED_ACCOUNT_IDS`
- `RH_ENABLED_STRATEGIES` can enable multiple guarded strategy lanes for demo testing; the default env templates now show the full four-strategy set
- if you have four Topstep demo accounts, put all four ids in `RH_TOPSTEP_ALLOWED_ACCOUNT_IDS` and parallel labels in `RH_TOPSTEP_ALLOWED_ACCOUNT_LABELS` so Bill can assign one primary strategy lane per account
- `bill:paper-loop` defaults to `data/free/ALL-6MARKETS-1m-5d-normalized.csv` when no CSV path is provided, so scheduled demo/shadow futures runs do not depend on an extra launchd argument
- do not remove the account lock when a real personal or funded account is also linked elsewhere in Topstep

Live deployment readiness:

```bash
npm run live-readiness -- data/free/ALL-6MARKETS-1m-5d-normalized.csv 3
npm run demo-tomorrow -- data/free/ALL-6MARKETS-1m-5d-normalized.csv 3
```

This command estimates real-world degradation from latency, slippage model, and data-quality penalties, then runs bounded self-evolving iterations (`jarvis-loop` logic) to recover deployability under stressed assumptions.

Before backtesting a vendor export, inspect it first:

```bash
npm run inspect-csv -- ./path/to/minute-bars.csv
```

Current research profiles include:

- `topstep-index-open`
- `index-core-breadth`
- `ict-killzone-core`
- `liquid-core-mix`
- `trend-only`
- `balanced-wctc`
- `strict-news`

## Operating posture

- Demo first
- Local device only for any future live execution, with broker support limited to Topstep-approved paths until a reviewed payout track record exists
- Flat by the Topstep cutoff
- No automatic promotion of strategy changes
- Evolution is reviewable, bounded, and reversible

## Docs

- [Architecture](./docs/ARCHITECTURE.md)
- [Agentic Stack 2026](./docs/AGENTIC_STACK_2026.md)
- [Context Drift Checklist](./docs/CONTEXT_DRIFT_CHECKLIST.md)
- [Founder Inputs](./docs/FOUNDER_INPUTS.md)
- [ICT Strategy Selection](./docs/ICT_STRATEGY_SELECTION.md)
- [Morning Checkpoint 2026-04-05](./docs/MORNING_CHECKPOINT_2026-04-05.md)
- [Bill Source Catalog](./docs/BILL_SOURCE_CATALOG.md)
- [Real Data Playbook](./docs/REAL_DATA_PLAYBOOK.md)
- [Topstep Demo Operating Path](./docs/TOPSTEP_DEMO_OPERATING_PATH.md)
- [Risk Guardrails](./docs/RISK_GUARDRAILS.md)
- [Research Memo 2026](./docs/RESEARCH_MEMO_2026.md)
- [Sources](./docs/SOURCES.md)
