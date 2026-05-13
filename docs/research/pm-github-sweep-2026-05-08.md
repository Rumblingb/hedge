# Prediction Market GitHub Sweep - 2026-05-08

Purpose: quarantine and rank open-source prediction-market tooling for Bill/Hermes. Do not run third-party trading code live from these repos. Port specific mechanisms into Bill behind Bill's risk, paper, execution, and kill-switch gates.

## Intake Result

Cloned or confirmed locally under `research-repos/`:

- `evan-kolberg/prediction-market-backtesting`
- `TauricResearch/TradingAgents`
- `mvanhorn/last30days-skill`
- `firecrawl/firecrawl`
- `pydantic/pydantic-ai`
- `n8n-io/n8n`
- `aarora4/Awesome-Prediction-Market-Tools`
- `pmxt-dev/pmxt`
- `guzus/dr-manhattan`
- `suislanchez/polymarket-kalshi-weather-bot`
- `ImMike/polymarket-arbitrage`
- `Quentin-Piot/prediction-market-backtester`
- `PaulieB14/polymarket-orderbook-substreams`
- `suitedaces/polyterminal`
- `jogobeny/polymarket-orderbook-reconstruction`
- `AKCodez/prediction-market-alpha-playbook`
- `braedonsaunders/homerun`
- `0xalberto/polymarket-arbitrage-bot`
- `studentzove/polymarket-arbitrage-bot` — retired OpenClaw memory named it as a PM arbitrage reference; treat as hypothesis/intake only until source is revalidated.
- `CarlosIbCu/polymarket-kalshi-btc-arbitrage-bot` — retired OpenClaw memory named it as a BTC PM/Kalshi arbitrage reference; treat as hypothesis/intake only until source is revalidated.

Exact links that did not resolve on GitHub:

- `FiatFiorino/polymarket-assistant-tool`
- `tavily-ai/tavily-mcp-server`
- `txbabaxyz/collectmarkets2`
- `txbabaxyz/mlmodelpoly`

Forked to `Rumblingb` for preservation and deeper intake:

- `Rumblingb/prediction-market-backtesting`
- `Rumblingb/prediction-market-backtester`
- `Rumblingb/pmxt` already existed
- `Rumblingb/dr-manhattan`
- `Rumblingb/polymarket-orderbook-substreams`
- `Rumblingb/polyterminal`
- `Rumblingb/polymarket-orderbook-reconstruction`
- `Rumblingb/prediction-market-alpha-playbook`
- `Rumblingb/polymarket-arbitrage`
- `Rumblingb/polymarket-kalshi-weather-bot`

## Security Read

No obvious committed private keys were found in the first-pass grep. Several repos use `.env.example` placeholders for private keys/API keys, which is expected.

Risk categories:

- Live order paths: `pmxt`, `dr-manhattan`, `homerun`, `polymarket-arbitrage`, `polymarket-kalshi-weather-bot`, and most bot repos can place orders if credentials are supplied.
- Process/control risk: `homerun`, `n8n`, and `firecrawl` have broad service/process surfaces. Treat them as architecture references, not embedded dependencies.
- SEO-spam risk: many GitHub search results have repeated keyword-stuffed descriptions and little evidence of real implementation. Avoid importing those.
- Settlement/semantic risk: all Kalshi/Polymarket arbitrage repos require strict market equivalence checks. Similar titles are not enough.

Policy: no third-party repo should receive Bill credentials or wallet keys. All useful ideas must be ported into Bill modules and tested in paper/shadow mode first.

Retired OpenClaw appendix: two additional repo names were recovered from `/Users/brain/.openclaw.retired-2026-05-12/workspace-bill/PREDICTION_BOT_OPPORTUNITY_MAP.md`. They are not proof of edge; they are search seeds for future fork-intake/distillation.

## Best Repos To Use

1. `prediction-market-backtesting`
   - Useful because it already models prediction-market strategies as pure logic separated from venue I/O.
   - Port ideas: microprice imbalance, final-period momentum, panic fade, VWAP reversion, late-favorite limit-hold.

2. `prediction-market-backtester`
   - Useful because it emphasizes reproducible backtests, explicit execution assumptions, run artifacts, latency, fees, and bid/ask fills.
   - Port ideas: run metadata, trade/equity artifacts, explicit slippage/latency assumptions.

3. `pmxt`
   - Useful as a CCXT-like interface reference for Polymarket, Kalshi, Limitless, and other venues.
   - Port ideas: normalized exchange adapter contracts. Do not import wholesale until Bill's auth and rate-limit boundaries are explicit.

4. `polymarket-orderbook-substreams`
   - Highest value data infra candidate. It covers CLOB v1 and v2, including the 2026-04-28 CLOB v2 migration, v2 side fields, fee semantics, and exchange-version tagging.
   - Port ideas: authoritative on-chain fill/order history for fillability and adverse-selection studies.

5. `polyterminal`
   - Directly relevant to BTC/ETH/SOL/XRP 15m binary markets.
   - Port ideas: 500ms orderbook snapshot collector, Binance spot stream pairing, market/window schema, automatic resolution.

6. `polymarket-orderbook-reconstruction`
   - Useful for replaying PMXT-scraped orderbook data.
   - Port ideas: historical book reconstruction before trusting edge claims.

7. `polymarket-arbitrage` by ImMike
   - Useful for cross-platform scanner structure and market-matching concepts.
   - Port ideas: text-similarity matching only as a candidate generator, never as final equivalence proof.

8. `polymarket-kalshi-weather-bot`
   - Useful because weather markets are structurally forecastable and can diversify away from pure BTC microstructure.
   - Port ideas: ensemble weather probability model, calibration/Brier tracking, conservative Kelly sizing.

9. `prediction-market-alpha-playbook`
   - Useful as a checklist of edge classes and antipatterns.
   - Port ideas: Wilson lower-bound promotion, journal-PnL skepticism, side/token alignment checks, cohort search before killing strategies.

10. `homerun`
    - Interesting but large and AGPL. Use as architecture inspiration only unless license implications are acceptable.
    - Port ideas: shadow/live bridge, L2 replay, strategy hot reload, wallet discovery isolation.

## Immediate Bill Implementation Priorities

1. Fillability layer for Gengar/UP-DOWN signals.
   - Log token IDs, best bid/ask, spread, top-book size, simulated `$1`/`$5` fills, and post-fee EV for every candidate.
   - This closes the current gap where direction looks good but buyability is unproven.

2. Orderbook snapshot store.
   - Start with the `polyterminal` model: market window, token IDs, spot start/end, and periodic book snapshots.
   - Add later: Substreams/on-chain fill ingestion from `polymarket-orderbook-substreams`.

3. Conservative PM backtest artifact format.
   - Borrow from `prediction-market-backtester`: `results.json`, `equity.csv`, `trades.csv`, git commit, config hash, fee/slippage/latency assumptions.

4. Cross-venue equivalence gate.
   - Before PM/Kalshi arb can be trusted, require same underlying, same reference price/source, same start/end window, same settlement rule, and same timezone/cutoff.

5. Weather edge track.
   - BTC UP/DOWN is latency-sensitive and capacity-limited. Weather/Kalshi/PM markets may offer slower, more model-driven edge with cleaner OOS validation.

## Do Not Use Directly

- Broad SEO bot repos from GitHub search unless later proven real by source inspection.
- Any repo that defaults to live trading, requires keys on startup, or has unclear dry-run behavior.
- Any cross-venue arb bot that matches markets by title alone.
- Any wallet/copy-trading system that cannot reconcile against official activity/on-chain fills.
