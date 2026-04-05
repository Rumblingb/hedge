# Rumbling Hedge

Rumbling Hedge is a separate trading lab for guarded research, backtesting, and paper execution.

It is built around one principle: the agent can suggest tighter changes, but it does not get to loosen its own risk rails or silently rewrite live behavior mid-session.

## What is in v0.1

- Topstep-style hard guardrails encoded in code, not prompts
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
npm run sim
npm run research
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

The demo research engine now tracks both gross and net performance. Net R includes configurable friction for fees, slippage, and a small stress haircut, so a strategy has to survive costs rather than just print clean gross backtests.
Research summaries also include per-symbol contribution breakdowns so you can see where the edge is actually coming from.
They also roll up into market-family summaries (`index`, `fx`, `energy`, `metal`, `bond`, `ag`, `crypto`) and a simple suggested focus list that prefers the strongest positive contributors.
Walk-forward research also returns a normalized family budget recommendation so you can see which market families should stay active in the next research pass.

When `npm run research` uses synthetic data, it now builds bars from the union of all research profile universes instead of only the base config universe. That makes the profile comparison more representative of the full liquid-futures research mix.

Useful environment overrides:

- `RH_FEE_R_PER_CONTRACT`
- `RH_SLIPPAGE_R_PER_SIDE`
- `RH_STRESS_MULTIPLIER`
- `RH_STRESS_BUFFER_R`

Before backtesting a vendor export, inspect it first:

```bash
npm run inspect-csv -- ./path/to/minute-bars.csv
```

Current research profiles include:

- `topstep-index-open`
- `index-core-breadth`
- `liquid-core-mix`
- `trend-only`
- `balanced-wctc`
- `strict-news`

## Operating posture

- Demo first
- Local device only for any future live execution
- Flat by the Topstep cutoff
- No automatic promotion of strategy changes
- Evolution is reviewable, bounded, and reversible

## Docs

- [Architecture](./docs/ARCHITECTURE.md)
- [Agentic Stack 2026](./docs/AGENTIC_STACK_2026.md)
- [Context Drift Checklist](./docs/CONTEXT_DRIFT_CHECKLIST.md)
- [Founder Inputs](./docs/FOUNDER_INPUTS.md)
- [Morning Checkpoint 2026-04-05](./docs/MORNING_CHECKPOINT_2026-04-05.md)
- [Real Data Playbook](./docs/REAL_DATA_PLAYBOOK.md)
- [Risk Guardrails](./docs/RISK_GUARDRAILS.md)
- [Research Memo 2026](./docs/RESEARCH_MEMO_2026.md)
- [Sources](./docs/SOURCES.md)
