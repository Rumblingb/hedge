# Bill Mac Mini Ops

This directory is the macOS-native operator surface for Bill.

## Purpose

The canonical Bill repo is now `~/hedge`.

This layer keeps Bill operable on the Mac mini through:
- shell wrappers that map to the real Bill CLI
- structured health output
- launchd templates for recurring checks
- one external environment template for paper/demo/live-safe operation

## Principles

- Bill stays first-class and separate from Agency OS.
- Risk and promotion remain in code, not prompts.
- The wrappers here must stay thin. They should call the real Bill CLI, not replace it.
- External credentials belong in `.env` or launchd environment variables, not in the wrappers.

## Commands

- `ops/mac-mini/bin/bill-doctor`
- `ops/mac-mini/bin/bill-health`
- `ops/mac-mini/bin/bill-cost-profile`
- `ops/mac-mini/bin/bill-prediction-collect [source] [limit] [outPath]`
- `ops/mac-mini/bin/bill-prediction-cycle-scheduled`
- `ops/mac-mini/bin/bill-prediction-iterations [count]`
- `ops/mac-mini/bin/bill-native-summary`
- `ops/mac-mini/bin/bill-prediction-scan [snapshot.json]`
- `ops/mac-mini/bin/bill-prediction-train [journalPath]`
- `ops/mac-mini/bin/bill-prediction-report [journalPath]`
- `ops/mac-mini/bin/bill-market-track-status`
- `ops/mac-mini/bin/bill-research-collect`
- `ops/mac-mini/bin/bill-researcher-run-scheduled`
- `ops/mac-mini/bin/bill-research-report`
- `ops/mac-mini/bin/bill-paper-loop [csvPath]`
- `ops/mac-mini/bin/bill-strategy-lab-scheduled`
- `ops/mac-mini/bin/bill-quant-autonomy [--dry-run|--force]`
- `ops/mac-mini/bin/bill-live-readiness [csvPath] [iterations]`
- `ops/mac-mini/bin/bill-kill-switch [on|off|status] [reason]`
- `npm run bill:nim-smoke`
- `npm run bill:fork-intake`
- `npm run bill:strategy-factory`
- `npm run bill:quant-autonomy`
- `npm run bill:autonomy-status`
- `npm run bill:dashboard`

## Files

- `env/bill.env.example` - environment template
- `COST_POLICY.md` - cheap-by-default Bill and quant box operating policy
- `bin/bill-install-env` - installs the secure env template to `~/Library/Application Support/AgentPay/bill/bill.env`
- `scripts/health.mjs` - structured JSON health command
- `scripts/cost-profile.mjs` - machine-readable Bill cost profile
- `scripts/prediction-cycle.mjs` - one locked collect -> scan -> report loop with iteration history
- `src/prediction/training.ts` - bounded learned scan-policy tuning based on the latest candidate journal, source catalog, and cycle history
- `src/prediction/scanPolicy.ts` - effective prediction scan thresholds, learned-policy loading, and classifier logic
- `scripts/prediction-iterations.mjs` - structured iteration history reader
- `src/research/collector.ts` - deterministic research ingest and curation catalog
- `src/research/tracks.ts` - explicit Bill market-track policy
- `src/research/tools.ts` - explicit Bill tool registry
- `src/research/sources.ts` - explicit Bill source catalog for autonomous collection and training inputs
- `src/research/macro.ts` - FRED macro/rates series collector when keyed access is configured
- `bin/bill-install-launchd` - installs and loads Bill launchd jobs
- `launchd/*.plist.template` - launchd templates for scheduled Bill jobs
- prediction scan sizing is controlled through `BILL_PREDICTION_BANKROLL`, `BILL_PREDICTION_MAX_RISK_PCT`, `BILL_PREDICTION_MAX_EXPOSURE_PCT`, and `BILL_PREDICTION_CONFIDENCE_HAIRCUT`
- Runtime prediction snapshots, candidate journals, and fill journals should live under `.rumbling-hedge/runtime/prediction/` so scheduled loops do not dirty tracked source/data files.

## Notes

- `npm install` must be run once in the repo before the wrappers work.
- The wrappers resolve the repo root from their own location or from `BILL_REPO_ROOT`.
- Secrets should live in `~/Library/Application Support/AgentPay/bill/bill.env`, not in the repo or launchd plists.
- NVIDIA NIM uses the OpenAI-compatible cloud lane here; set `NVIDIA_NIM_API_KEY` in the secure env file and use `npm run bill:nim-smoke` to verify connectivity.
- Native Bill jobs should carry the recurring workload; scheduled LLM loops should stay infrequent and bounded.
- `bill-paper-loop` stays disabled until `BILL_ENABLE_PAPER_LOOP=true` is set in the secure env file.
- When enabled without arguments, `bill-paper-loop` defaults to `data/free/ALL-6MARKETS-1m-10d-normalized.csv` so launchd can run the futures demo/shadow loop without extra flags.
- `bill-paper-loop` now calls `demo-overnight`, which appends per-account strategy samples into `.rumbling-hedge/logs/futures-demo-samples.jsonl` and refreshes `.rumbling-hedge/state/futures-demo.latest.json`.
- `bill-prediction-cycle-scheduled` is the scheduler of truth for prediction-market automation. It runs collect -> scan -> report -> train under one lock every 5 minutes.
- `bill-prediction-cycle-scheduled` kills hung child stages after `BILL_PREDICTION_CYCLE_CHILD_TIMEOUT_MS` and only runs copy-demo every `BILL_PREDICTION_COPY_DEMO_EVERY_NTH_RUN` cycles by default.
- `bill-research-collect-scheduled` refreshes a discard-aware research catalog of public market data, venue snapshots, Bill-local artifacts, and paper metadata.
- `bill-researcher-run-scheduled` is the bounded 24/7 research lane. It runs on a staggered 70-minute cadence, respects target cadence, daily crawl budget, and corpus byte limits, then deletes transient transcript artifacts after strategy extraction.
- `bill-strategy-lab-scheduled` keeps the strategy-maker loop alive without widening authority. It runs on a staggered 155-minute cadence, uses light continuous windows, and schedules heavier OOS/readiness passes in batches.
- `bill-strategy-lab-scheduled` only runs the heavier strategy-factory pass on full cycles so `BILL_MAX_HEAVY_JOBS=1` remains viable on the 16GB Mac Mini.
- `bill-quant-autonomy` is the machine-first quant runner. It holds the shared heavy-compute slot, executes stale fork/research/strategy tasks locally, refreshes the board, and writes `.rumbling-hedge/state/quant-autonomy.latest.json`.
- `bill:fork-intake` reads the GitHub fork manifest and writes compact cards under `.rumbling-hedge/research/forks/`; it should replace local clones for reference-repo ingestion.
- `bill:dashboard` refreshes `.rumbling-hedge/state/autonomy-status.latest.json` before writing the OpenJarvis board, making the board the single founder-facing Bill/Hedge surface.
- `bill-health` now expects the researcher scheduler, strategy lab, and OpenJarvis board artifacts to exist when those loops are enabled. Expensive compile/deep diagnostics only run when `BILL_HEALTH_DEEP=true`.
- `bill:market-track-status` now reports both the active tool registry and the broader source catalog so operators can see what Bill can collect today versus what is merely cataloged for later wiring.
- `bill-doctor` and `bill-health` now surface demo-account lane assignment, strategy diversification state, and whether the broader collection loops are actually enabled.
- Bill should keep `prediction` and `futures-core` as the equal-first execution tracks. Other domain tracks can remain collection/training tracks without spawning new execution permissions.
- `bill-prediction-collect-scheduled`, `bill-prediction-scan-scheduled`, and `bill-prediction-report-scheduled` still exist as thin stage wrappers, but launchd should drive the cycle job rather than the stages independently.
- `bill-prediction-report-scheduled` writes a native summary artifact into Bill lane memory.
- Prediction training is bounded: it can tighten or rebalance scan thresholds, but it does not grant itself new live permissions or widen the active execution wedge.
- First live activation remains approval-gated even after these service wrappers exist.
