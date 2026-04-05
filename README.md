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
npm run sim
npm run research
npm run evolve
```

To run a CSV backtest:

```bash
npm run backtest -- ./path/to/minute-bars.csv
```

CSV columns expected:

```text
ts,symbol,open,high,low,close,volume
2026-04-01T13:30:00.000Z,NQ,18250,18253,18248,18252,1320
```

## Operating posture

- Demo first
- Local device only for any future live execution
- Flat by the Topstep cutoff
- No automatic promotion of strategy changes
- Evolution is reviewable, bounded, and reversible

## Docs

- [Architecture](./docs/ARCHITECTURE.md)
- [Risk Guardrails](./docs/RISK_GUARDRAILS.md)
- [Research Memo 2026](./docs/RESEARCH_MEMO_2026.md)
- [Sources](./docs/SOURCES.md)
