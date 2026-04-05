# Morning Checkpoint 2026-04-05

## What Changed This Cycle

- Added a cheap/free 2026 agentic stack memo in [Agentic Stack 2026](./AGENTIC_STACK_2026.md).
- Expanded quant research profiles to compare an index core against a broader liquid-futures mix.
- Added per-symbol contribution reporting.
- Added per-market-family contribution reporting.
- Added `suggestedFocus` so research output now points toward the strongest positive market families.
- Added a context-drift safeguard with both a checklist and a runnable command.
- Added `npm run inspect-csv` so vendor minute-bar exports can be checked before backtesting.
- Added a normalized train/test-aware family budget recommendation to walk-forward research output.

## Current Stable Commands

- `npm run context-drift`
- `npm run verify`
- `npm run inspect-csv -- ./path/to/minute-bars.csv`
- `npm run research`
- `npm run sim`

## Current Research Read

On the current synthetic harness:

- winner: `liquid-core-mix`
- strongest market families: `bond`, `energy`, then `metal`
- weak family in the current sample: `index`
- active research budget set: `bond`, `energy`, `metal`

On the current synthetic sim:

- strongest families: `energy`, `index`, then `metal`
- weak family in the current sample: `fx`

This is useful for research prioritization, but it is not real-market proof.

## What I Believe Right Now

- The current credible thesis is still liquid futures, demo first, cost-aware, and rules based.
- Agentic tooling is useful for research acceleration and operator discipline, not as the live risk owner.
- The next real step should be driven by real minute-bar data, not by adding more strategy folklore.

## Next Best Move

1. Run `npm run inspect-csv -- <file>` on real minute-bar CSVs for `NQ`, `ES`, `CL`, `GC`, `6E`, and `ZN`.
2. Run the current research stack on those real files.
3. Re-rank the market mix on real data and prune any family that fails net of costs.

## Re-entry Rule

Before making the next substantial change:

1. Run `npm run context-drift`
2. Run `npm run verify`
3. Inspect any real CSV with `npm run inspect-csv -- <file>`
4. Read the winner, family contribution, and family budget output from `npm run research`
5. Only then decide whether to widen, tighten, or simplify
