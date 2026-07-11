# Prediction Market Demo Slice

Date: 2026-04-13
Owner: Bill
Status: proposed, paper-only

## Goal
Turn the useful parts of `awesome-OpenClaw-Money-Maker` into a demoable lane for Bill without live-capital shortcuts.

## Selected source components
### USE now
- `pmxt` for multi-venue market normalization and event/market/outcome abstraction
- `Prediction Market Analysis` for data/indexing and analysis structure
- `py-clob-client` / `clob-client` for direct Polymarket read-only order-book access
- `poly_data` for event/trade retrieval patterns

### LEARN from
- `poly-maker` for quoting, inventory, and order-replacement logic
- short-duration Polymarket bots for alert UX and trigger ideas

### QUARANTINE
- cross-venue arb bots as direct strategy bases
- copy trading bots
- AI-heavy bot claims without edge validation
- MEV/flash-loan templates for this first demo

## Best first demo
A paper-only exact-overlap scanner for Polymarket and Kalshi.

## Demo flow
1. Fetch venue market catalogs
2. Normalize event, market, outcome, expiry, and settlement text
3. Match only high-confidence equivalent contracts
4. Pull quotes / order-book snapshots
5. Compute gross spread, net spread after fees, and executable size checks
6. Classify each candidate as `reject`, `watch`, or `paper-trade`
7. Write an opportunity journal for replay and review

## Minimal demo UI/output
- top 10 overlap candidates
- venue A yes/no prices
- venue B yes/no prices
- net edge after fees
- confidence score on event equivalence
- liquidity note
- final recommendation

## Why this demo wins
- directly matches Bill's current lane
- useful even if it proves no live arb exists
- creates reusable infra for later single-venue structure and market-making work
- safe to demo without funding accounts

## Blockers
- exact contract equivalence across venues
- fill realism and depth at quoted prices
- differing settlement rules and wording

## Promotion gate
Do not consider live deployment until the scanner shows repeated paper opportunities with:
- exact contract matches
- positive net edge after fees
- sufficient displayed size and realistic execution assumptions
- documented settlement compatibility
