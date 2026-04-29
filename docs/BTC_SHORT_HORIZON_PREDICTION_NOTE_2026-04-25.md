# BTC Short-Horizon Prediction Note

## Current read

As of April 25, 2026, the short-duration BTC direction market is live on Polymarket and quoted around 51% for `Up` on the current 5-minute window. Polymarket's own market rules state that `Up` wins if the ending BTC price is greater than or equal to the starting price for the window, with settlement based on the Chainlink BTC/USD stream.

## Structural edge that did exist

There is a real structural bias toward `Up` because the market resolves `Up` on `>=`, not only on `>`.

That means the fair unconditional probability for `Up` is:

- `P(close > open)` plus
- `P(close = open)`

and not just `P(close > open)`.

## What recent BTC data says

Using recent Yahoo BTC-USD 5-minute bars as a spot proxy:

- last 5 days: `close >= open` in 51.40% of bars
- last 1 month: `close >= open` in 50.43% of bars

This suggests the old blind `buy Up` thesis is not a clean free lunch anymore. A live market price around 51% is broadly in line with recent unconditional BTC 5-minute direction frequency.

## Important caution

This comparison is only a proxy because:

1. Polymarket resolves on Chainlink BTC/USD, not Yahoo spot.
2. Short-horizon execution edge depends on queue position, spread, and latency.
3. Fees and slippage can erase a small unconditional probability advantage.

## Bill implication

Bill should not treat BTC 5-minute `Up` as a standalone exploitable edge by default.

The only credible edge paths here are:

1. Better microstructure than the crowd.
2. Faster reaction to order-book or reference-price shifts.
3. Selective participation when price-to-beat, live spot drift, and quote quality diverge enough to survive costs.

## Recommended posture

- Keep this lane in research mode.
- Track live quote bias versus recent realized `close >= open` frequency.
- Only escalate if a repeatable edge survives fees, slippage, and reference-source mismatch.
