# Architecture

## Goal

Rumbling Hedge is a lab for finding small, defensible futures edges in demo mode before any live API work exists.

## Core loop

1. Ingest minute bars for approved futures symbols
2. Run strategy plugins over rolling history
3. Pass every signal through hard guardrails
4. Simulate execution in the paper engine
5. Journal outcomes
6. Produce offline evolution proposals
7. Promote only reviewed changes

## Main modules

- `src/strategies`
  - winner-inspired proxy strategies
- `src/risk`
  - hard bounds, session rules, loss state, and signal gating
- `src/engine`
  - paper execution, summaries, and journal I/O
- `src/news`
  - provider seam for news alignment
- `src/evolution`
  - bounded proposal generation from recent trade history
- `src/adapters/topstep`
  - future live execution seam, intentionally disabled in this starter

## Execution model

The starter engine keeps only one position open at a time. That is deliberate. It reduces complexity and makes the first iteration easier to trust.

## Evolution model

The system may suggest:

- reducing daily trade count
- raising minimum RR
- shortening hold times
- raising news confidence thresholds
- disabling weak strategies

The system may not suggest:

- higher leverage
- more contracts
- looser daily loss limits
- later cutoff times
- wider self-authority
