# CTO Operating Model

## Role

Rumbling Hedge is run as a controlled research program, not as a loose trading bot.

The operating principle is:

- one stable mainline
- parallel worktree lanes for separate concerns
- hard verification before promotion
- no live autonomy without explicit human approval

## Decision Rights

The founder owns product intent and risk appetite.

The CTO brain owns:

- research prioritization
- experiment design
- lane selection
- code integration order
- merge/rollback decisions for non-live changes

The system itself may propose tighter rules, but it may not widen exposure, relax guardrails, or self-promote into live execution.

## Control Layers

1. Product intent
   - Which futures universe we care about
   - Which demo outcome matters
   - What counts as "good enough"
2. Research
   - Strategy ideas, market mix, regime splits, cost assumptions
3. Implementation
   - Code changes in isolated worktrees
4. Verification
   - Typecheck, tests, walk-forward, sim, and stress checks
5. Promotion
   - Only after evidence clears the gate

## Non-Negotiables

- Demo-first
- Local-device only for any future live path
- No worktree may bypass the hard risk rails
- No profile may increase contracts, loosen drawdown, or extend trading hours without explicit review
- Every candidate must show net performance after costs, not just gross backtest PnL

## Verification Gates

Minimum gate for a code change:

- `npm run typecheck`
- `npm test`
- `npm run research`
- `npm run sim`

Minimum gate for a strategy candidate:

- walk-forward performance
- consistent behavior across train and test splits
- acceptable drawdown
- no dependency on a single market regime
- explainable failure modes

Minimum gate for a live-capable path:

- founder approval
- local-device compliance
- explicit kill switch
- full audit logging
- no unresolved policy ambiguity

## Operating Cadence

- Daily: review fresh research, sim output, and failure logs
- Per change: build in a worktree, verify locally, then merge to trunk
- Weekly: prune weak strategies and simplify the stack
- Monthly: re-rank the market mix and research profiles

## Minimal Founder Inputs

I need only a few things to keep this moving:

- the target account path: demo only, or demo plus later live candidate
- the allowed market universe
- the maximum risk budget you will tolerate in demo
- the minimum evidence threshold before we promote a strategy
- any hard no-go windows or instruments
- whether you want the lab biased toward index momentum, cross-asset trend, or balanced multi-market research

If those inputs do not change, I will keep iterating inside the existing guardrails and report back only when something is materially better or materially worse.
