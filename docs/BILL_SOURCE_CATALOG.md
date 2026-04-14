# Bill Source Catalog

Bill now emits a machine-readable source catalog at `.rumbling-hedge/research/source-catalog.json`.

This file exists so Bill can reason about three separate questions without relying on prompt memory:

- what data sources are already wired into the native runtime
- which additional free or free-tier APIs are available but still need integration work
- which config variables gate collection and training on each track

## Categories

- `prediction-market`: Polymarket, Kalshi, Manifold, plus cataloged PMXT and venue SDKs
- `market-data`: Yahoo, Stooq, Polygon, Alpha Vantage, Finnhub, IEX, Databento, Alpaca, yfinance
- `macro`: FRED
- `symbology`: OpenFIGI
- `filings`: SEC EDGAR
- `universe`: FinanceDatabase
- `discovery`: the Public APIs finance index

## How Bill should use it

1. Prefer sources with `mode=active` and `automationReady=true`.
2. Treat `mode=missing-config` as operator setup debt, not as a reason to widen execution scope.
3. Treat `mode=catalog-only` as research backlog. These sources can inform future wiring, but they should not block current prediction-market loops.
4. Use `collectionCommand` when present instead of inventing a new path.

## Generated artifacts

- `.rumbling-hedge/research/source-catalog.json`
- `.rumbling-hedge/research/tool-registry.json`
- `.rumbling-hedge/research/track-policy.json`
- `.rumbling-hedge/research/catalog.json`

## Config keys

- `RH_POLYGON_API_KEY`
- `ALPHA_VANTAGE_API_KEY`
- `FINNHUB_API_KEY`
- `IEX_CLOUD_API_KEY`
- `OPENFIGI_API_KEY`
- `SEC_EDGAR_USER_AGENT`
- `DATABENTO_API_KEY`
- `ALPACA_API_KEY`
- `ALPACA_SECRET_KEY`
- `FRED_API_KEY`

The source catalog is designed to keep Bill self-learning while preserving the current operating posture: one active prediction cashflow wedge, broader market data as context and training input, and no silent expansion into new execution venues.
