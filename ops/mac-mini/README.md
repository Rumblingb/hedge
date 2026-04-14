# Bill Mac Mini Ops

This directory is the macOS-native operator surface for Bill.

## Purpose

The canonical Bill repo is now `/Users/baskar_viji/hedge`.

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
- `ops/mac-mini/bin/bill-prediction-report [journalPath]`
- `ops/mac-mini/bin/bill-paper-loop [csvPath] [iterations]`
- `ops/mac-mini/bin/bill-live-readiness [csvPath] [iterations]`
- `ops/mac-mini/bin/bill-kill-switch [on|off|status] [reason]`

## Files

- `env/bill.env.example` - environment template
- `COST_POLICY.md` - cheap-by-default Bill and quant box operating policy
- `bin/bill-install-env` - installs the secure env template to `~/Library/Application Support/AgentPay/bill/bill.env`
- `scripts/health.mjs` - structured JSON health command
- `scripts/cost-profile.mjs` - machine-readable Bill cost profile
- `scripts/prediction-cycle.mjs` - one locked collect -> scan -> report loop with iteration history
- `scripts/prediction-iterations.mjs` - structured iteration history reader
- `bin/bill-install-launchd` - installs and loads Bill launchd jobs
- `launchd/*.plist.template` - launchd templates for scheduled Bill jobs
- prediction scan sizing is controlled through `BILL_PREDICTION_BANKROLL`, `BILL_PREDICTION_MAX_RISK_PCT`, `BILL_PREDICTION_MAX_EXPOSURE_PCT`, and `BILL_PREDICTION_CONFIDENCE_HAIRCUT`

## Notes

- `npm install` must be run once in the repo before the wrappers work.
- The wrappers intentionally assume the repo root is `/Users/baskar_viji/hedge`.
- Secrets should live in `~/Library/Application Support/AgentPay/bill/bill.env`, not in the repo or launchd plists.
- Native Bill jobs should carry the recurring workload; scheduled LLM loops should stay infrequent and bounded.
- `bill-paper-loop` stays disabled until `BILL_ENABLE_PAPER_LOOP=true` is set in the secure env file.
- `bill-prediction-cycle-scheduled` is the scheduler of truth for prediction-market automation. It runs collect -> scan -> report under one lock every 5 minutes.
- `bill-prediction-collect-scheduled`, `bill-prediction-scan-scheduled`, and `bill-prediction-report-scheduled` still exist as thin stage wrappers, but launchd should drive the cycle job rather than the stages independently.
- `bill-prediction-report-scheduled` writes a native summary artifact into Bill lane memory.
- First live activation remains approval-gated even after these service wrappers exist.
