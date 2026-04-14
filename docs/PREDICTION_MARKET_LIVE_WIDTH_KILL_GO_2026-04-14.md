# Polymarket live width check and scanner decision

Date: 2026-04-14
Source: `hedge/data/prediction/polymarket-live-snapshot-2026-04-14.json`

## Validated snapshot facts
- Snapshot size: 598 markets across 10 events
- Live-liquidity markets: 526
- Zero-liquidity markets: 72
- The 10 highest-liquidity events were mostly extreme-width election or binary markets
- Top observed event liquidity by widest live book:
  - Military action against Iran ends by...? , 6.25M, 100% width
  - 2026 FIFA World Cup Winner, 4.08M, 99.7% width
  - Next Prime Minister of Hungary, 2.70M, 99.9% width
  - Democratic Presidential Nominee 2028, 2.41M, 98.9% width
  - Presidential Election Winner 2028, 1.85M, 98.9% width
- The live scan still has only one venue wired, so cross-venue `prediction-scan` has no valid pairs yet and remains structurally blocked.

## Decision
- **Kill** cross-venue scanner as the immediate cashflow path until a second live read-only venue adapter exists.
- **Go** on a Polymarket-only spread/width report path, because the live tape already shows meaningful width and liquidity concentration that can be ranked without pretending cross-venue edge exists.

## Next concrete move
- Add a Polymarket-only width-ranking report that surfaces the widest live books by liquidity-weighted spread.
- Keep the scanner paper-only and only re-open cross-venue matching after venue two is live.

## Risk note
- Width here is a quoting opportunity signal, not a fill guarantee.
- Zero-liquidity and near-1.00 priced books still need depth and execution checks before any promotion.
