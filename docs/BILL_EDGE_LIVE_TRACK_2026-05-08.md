# Bill Edge Live Track 2026-05-08

## Goal

Move Bill toward a live, compounding hedge loop without bypassing payout and execution gates.

Priority lanes:

- Prop firms: clear Topstep-style challenges, graduate to funded, extract first payouts, then scale only from proof.
- Prediction markets: convert discovered Polymarket edges into live-data paper watches, then only allow tiny live sizing after fillability, rules, and wallet funding gates are satisfied.

## Tomorrow Target

Tomorrow should be live-data and demo-active, not unrestricted live capital.

- Run `npm run bill:prediction-edge-intake` before market review.
- Run `npm run bill:prediction-copy-demo` with `BILL_PREDICTION_COPY_LEADER_SOURCE_PATH=/Users/brain/polymarket_top_wallets.json`.
- Run `npm run bill:prop-firm-payout-plan` and trade only payout-builder candidates in demo/read-only Topstep mode.
- Keep Polymarket execution disabled until wallet funding, market-rule review, fill simulation, and risk caps are all green.

## Polymarket Track

Current intake source:

- `/Users/brain/polymarket_edges_all_categories.json`
- `/Users/brain/polymarket_top_wallets.json`

Bill now classifies discovered edges as:

- `paper-watch`: high/medium confidence with usable slugs and no immediate thin-liquidity block.
- `research-watch`: interesting but missing execution-ready evidence.
- `avoid`: liquidity trap, wide spread, or insufficient executable liquidity.

First paper-watch candidates from the current file:

- Starmer Out calendar series.
- Base token launch time spread.
- US declares war on Iran tail-risk contract.
- US recession by end 2026.
- MSTR BTC sell time series.
- BTC $150k calendar spread.
- OpenAI IPO time series.

Every paper-watch still needs:

- Active market check against Gamma.
- Top-book bid/ask/depth and simulated $1/$5 fill.
- Settlement-rule reread and falsifying-event checklist.
- Adverse-selection log before any live approval.

## Prop-Firm Track

Bill should optimize for payout eligibility, not gross PnL.

Topstep 50K operating plan:

- One contract per 50K account until the evidence is durable.
- Daily net target range: $350-$650.
- Hard daily loss stop: $350.
- Avoid best-day concentration. A one-day pass creates payout and consistency fragility.
- Funded preference: XFA Consistency only if the largest payout-window day stays at or below 40% of net profit; otherwise use XFA Standard and collect five $150+ days.

Promotion gate:

- At least one payout-builder with positive expectancy, >=20 trades, resilience >=0.45, and non-flat bias.
- No daily loss breach, platform lock, or synthetic fallback signal in the last 10 sampled sessions.
- Replayable journal for every entry, skip, exit, and stop-after-target decision.

## Hard No-Go Conditions

- No live Polymarket orders from third-party repo code.
- No Bill credentials or wallet keys in cloned research repos.
- No Topstep routed orders unless the demo account lock and read-only policy are explicitly reviewed.
- No increased sizing after a demo pass; first funded payout proof comes before scaling.
