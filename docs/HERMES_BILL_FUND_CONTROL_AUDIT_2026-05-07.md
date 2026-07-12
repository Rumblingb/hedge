# Hermes/Bill Fund Control Audit — 2026-05-07

This audit distills the local Bill/Hedge, Hermes, OpenClaw, OpenJarvis, launchd, and memorybrain state inspected on 2026-05-07. It is an execution-readiness document, not a claim of profitability.

## Locked Vision

- Hermes is the fund controller: memory, queue, supervision, worker rotation, cost discipline, and founder-facing decision state.
- Bill/Hedge owns market research, strategy testing, paper/demo execution, risk controls, and prediction-market/futures evidence.
- OpenClaw is a bounded implementation/fixer worker that Hermes can assign patches to; it must not become an unbounded trading actor.
- OpenJarvis is the founder dashboard and input surface. Founder voice/input is advisory unless an explicit approval gate is satisfied.
- V1 remains paper/demo-only. Prediction live execution stays disabled. Futures Topstep routing may use demo accounts only under hard caps.

## Current Runtime Truth

- Autonomy status is degraded but honest: source tree dirty, prediction has zero paper candidates, research feed has no machine-testable directives after no-edge filtering, and strategy-lab OOS is thin.
- Strategy-lab is fresh again and blocked for the right reasons: 1 rolling OOS window evaluated, 0 deployable windows, live-readiness not deployable.
- Quant-autonomy, health, and OpenJarvis board artifacts are fresh.
- Researcher is running and keeps distilled hypothesis cards; raw YouTube transcript/temp files are not being retained in `.rumbling-hedge`.
- HDD is not currently mounted. `/Volumes` only shows `Macintosh HD`; cold archive now skips cleanly instead of throwing permission errors.
- Current Topstep env is demo-only, max-one-order constrained, and fallback exploration is disabled. Demo routing still remains blocked by OOS evidence.

## Critical Fixes Applied

- Removed forced demo sampling of quarantined legacy strategies from `src/live/demoSampling.ts`.
- Prevented synthetic `*-demo-fallback` signals from ever routing to ProjectX in `src/live/demoExecution.ts`.
- Updated strategy-feed generation to filter no-edge ledger strategies outside tests, so failed strategies become negative memory rather than recurring instructions.
- Made rolling OOS honor bounded profile IDs from the CLI and avoid default re-tuning unless `BILL_ROLLING_OOS_TUNE=true`.
- Restored ProjectX protective brackets in order requests.
- Fixed Manifold seed alignment for Bitcoin “hit $level” price-ladder markets.
- Made cold archive use the repo-local state path and skip cleanly when cold storage is missing or not writable.
- Set Vitest file execution to serial to match the 16GB Mac Mini compute envelope.
- Runtime env tightened: `BILL_FUTURES_DEMO_EXPLORATION_ENABLED=false`, max demo trades/day/loss/consecutive losses reset to 1.

## Remaining Blockers

1. No proven deployable edge.
   - No futures strategy is promotable.
   - Prediction scanner has no economically viable paper candidates.
   - Research feed now has zero directives because the current transcript/fork cards mostly point at quarantined no-edge families.

2. OOS evidence is too thin.
   - Current OOS dataset supports only 1 requested 20d/5d/1d rolling window.
   - Need more clean minute-bar history or smaller explicitly labeled smoke windows; do not call 1 window live-ready.

3. Research quality is still weak.
   - ICT/FVG transcript cards are mostly qualitative and marketing-like.
   - Good behavior is now fail-closed: cards can seed hypotheses, but no-edge strategies are filtered unless rules/data materially change.

4. Positioning context is incomplete.
   - COT exists and should remain weekly/contextual.
   - Dealer gamma is degraded across providers; gamma-conditioned strategies must not promote without usable options greeks.

5. Source custody is still unresolved.
   - The worktree has many modified/untracked source, docs, data, and runtime files.
   - Before broad architecture changes, split source/config/tests/docs from runtime/data and commit/push intentionally.

6. Native execution is not yet present.
   - The repo is TypeScript plus Python sidecars. There is no C++/Rust deterministic execution core today.
   - Native code should come after evidence and control boundaries are stable; the current bottleneck is proof, not microsecond latency.

## Hermes Control Phases

### Phase 1 — Stabilize Truth

- Keep all live-money gates closed.
- Keep Topstep demo routing capped and demo-only.
- Keep prediction execution paper-only.
- Refresh board, health, strategy-lab, quant-autonomy, researcher, and prediction artifacts on schedule.
- Treat no-edge ledger as hard negative memory.

### Phase 2 — Research Better, Not More

- Require each research card to produce machine-testable rules: entry, stop, target, invalidation, session, symbol, data needs, and expected failure mode.
- Route ICT/FVG cards into research-only unless they introduce a materially different rule than the failed no-edge families.
- Prioritize structural edges: event spike fade with economic calendar, opening stop-hunt with strict auction rules, COT/regime-conditioned capitulation, prediction/futures divergence, and cross-venue prediction exact-overlap.

### Phase 3 — Evidence Factory

- Add more OOS history before claiming rolling validation.
- Run profile slices by family; do not test every idea in every heavy loop.
- Promote only if walk-forward, rolling OOS, slippage/fee stress, sample size, paper/demo fills, and drawdown rules all pass.
- Record failed profiles in the no-edge ledger with the exact reason and what new evidence would justify retest.

### Phase 4 — Execution Room

- During market windows, Hermes may switch OpenJarvis into execution mode only when gates are green.
- Execution view should show: active gates, Topstep demo accounts, prediction candidates, open/filled/cancelled orders, PnL, daily loss, trailing drawdown, no-edge quarantines, data freshness, and current blockers.
- Founder voice remains suggestions/approvals, not direct order execution.

### Phase 5 — Native Core

- Build a small C++ or Rust `bill-core` only for deterministic strategy/risk/order calculations once the TS evidence pipeline identifies deployable rules.
- Keep orchestration, research, dashboards, and memory in TypeScript/Python where iteration speed matters.
- Native core must be pure, replayable, tested against historical fixtures, and never depend on LLM output at runtime.

## Next Best Iteration

1. Clean source custody: separate runtime/data dirt from source changes and commit the safety/control fixes.
2. Add enough historical futures data for at least 4 true rolling OOS windows.
3. Implement research-card quality scoring so vague transcript cards enter the graveyard instead of strategy-feed.
4. Wire COT/HMM/Kronos/TimesFM into explicit strategy gates where they improve testable hypotheses, not as loose narrative context.
5. Build the execution-room board after the above gates are stable.

