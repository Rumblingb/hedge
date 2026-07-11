# Prediction Bot Stack Spec

Date: 2026-04-13
Owner: Bill
Status: paper-only, buildable now

## Purpose
Define the smallest guarded stack for Bill's prediction-market lane.

This is not a live-arb thesis. It is a paper-only scanner and journal for exact-overlap market opportunities.

## Evidence basis
- `awesome-OpenClaw-Money-Maker` is a useful lead list, not a strategy thesis.
- `pmxt` is the best current infra base.
- `py-clob-client` / `clob-client` are the Polymarket read-only access layer.
- `poly_data` is useful for market/trade retrieval patterns.
- Cross-venue arb remains blocked by exact-match scarcity, fee drag, and fill realism.

## Scope
### In scope
- Polymarket catalog + order-book snapshots
- Kalshi catalog + quote snapshots
- normalized event/market/outcome schema
- exact-overlap and near-exact contract matching
- fee-aware paper ranking
- opportunity journaling

### Out of scope
- live capital
- withdrawal paths
- broad cross-venue arbitrage claims
- copy-trading bots
- MEV/flash-loan templates

## Core modules
### 1) Market adapters
Read-only adapters that fetch and normalize:
- venue
- external id
- event title
- market question
- outcome label
- side
- expiry
- settlement text
- quoted prices
- displayed size

### 2) Canonical matcher
Match only contracts that share:
- same underlying event
- same expiry window
- compatible settlement wording
- same outcome mapping

Near-exact matches must be flagged, not auto-accepted.

### 3) Fee and friction model
Per candidate, compute:
- gross spread
- fee-adjusted spread
- conservative slippage haircut
- executable-size estimate

Unknown fee assumptions should fail closed.

### 4) Paper journal
Persist each candidate with:
- timestamp
- candidate id
- venue pair
- quotes
- depth
- fees
- match score
- net edge
- verdict
- notes

## Verdicts
- `reject`: mismatch, weak size, negative net edge, or unclear settlement
- `watch`: high-confidence match with no usable edge yet
- `paper-trade`: exact match, positive net edge, and plausible size after friction

## Promotion gate
Do not promote beyond paper-only until all are true:
- exact contract equivalence confirmed
- positive net edge after fees and conservative slippage
- displayed size supports the quote
- settlement rules are compatible
- repeated opportunities appear across multiple checks

## Minimal build order
1. catalog fetchers
2. normalization layer
3. exact matcher
4. fee model
5. journal writer
6. top-10 CLI report

## Acceptance criteria for v0
A first run is useful if it can output a stable table of the top 10 candidates with:
- venue A price
- venue B price
- net edge
- match confidence
- size note
- verdict

If the output is mostly `reject`, that still counts as a valid result.
