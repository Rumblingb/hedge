# Retired Goal/Live Readiness Snapshot

This folder preserves systems that were removed from the active
`codex/goal-live-market-readiness` tree during the live-readiness restructure.

Retired here means:

- kept for audit, recovery, and selective cherry-picking;
- not imported by the active TypeScript or Rust build;
- not considered current deployment evidence;
- not allowed to override current live/demo gates.

Contents:

- `bill-core/` - prior Rust backtesting, sweep, and prop-firm research engine.
- `src/engine/alphaLab.ts` - prior TypeScript alpha lab engine.

If any module is revived, copy it back through a normal implementation change,
add tests, and rerun the current gates instead of promoting from this archive.
