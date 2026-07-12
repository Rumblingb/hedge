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

- Challenge mode can use one NQ contract when the setup quality is high and the daily lock is active.
- Funded mode drops to MNQ payout-defense sizing unless real payout history justifies more.
- Daily net target range: $350-$650.
- Hard daily loss stop: $350.
- Avoid best-day concentration. A one-day pass creates payout and consistency fragility.
- Funded preference: XFA Consistency only if the largest payout-window day stays at or below 40% of net profit; otherwise use XFA Standard and collect five $150+ days.

NQ-only challenge template:

- Instrument: NQ during challenge; MNQ during funded payout-defense.
- Target: 80 ticks / 20 points.
- Initial stop: 24-28 ticks / 6-7 points.
- Runner trail: 20 ticks / 5 points after first objective pressure confirms.
- Max trades: 3 per day.
- Challenge daily profit lock: around $1,200, below the $1,500 50K best-day recommendation.
- Challenge daily loss lock: around $450, far inside the $1,000 daily loss limit.
- Funded daily profit lock: around $300.
- Funded daily loss lock: around $180.

Automation foundation:

- Bracket order must exist before entry.
- State machine must enforce max-three-trades, daily lock, two-loss stop, news lockout, and platform risk lock.
- Bot must recompute combine best-day concentration and funded payout-window consistency before every entry.
- No funded account can inherit challenge sizing by default.

Promotion gate:

- At least one payout-builder with positive expectancy, >=20 trades, resilience >=0.45, and non-flat bias.
- No daily loss breach, platform lock, or synthetic fallback signal in the last 10 sampled sessions.
- Replayable journal for every entry, skip, exit, and stop-after-target decision.

## Hard No-Go Conditions

- No live Polymarket orders from third-party repo code.
- No Bill credentials or wallet keys in cloned research repos.
- No Topstep routed orders unless the demo account lock and read-only policy are explicitly reviewed.
- No increased sizing after a demo pass; first funded payout proof comes before scaling.
