# Bill/Hedge Live-Readiness Battlecard — 2026-05-13

## Verdict

Bill/Hedge is **not live-ready** for futures or unrestricted prediction-market execution.

The system is allowed to keep researching, paper trading, and micro-sandboxing only where gates explicitly permit it. No strategy is currently GOLD/SILVER executable after canonical evidence review.

## What Actually Worked

- Researcher lane is producing strategy feed artifacts again.
- HDD futures data is connected through runtime fallbacks.
- Prediction-market dataset is connected and status is ready.
- Gengar direction audit is statistically interesting, but still not a deployable fillability edge.
- OpenJarvis/live-readiness board now surfaces blockers instead of hiding them.

## What Failed Or Remains Thin

| Lane | Result | Reason |
| --- | --- | --- |
| short-term-reversal | Not deployable | 90d direct backtest produced 0 accepted trades; mostly hold-time/RR/session rejects. |
| ret-30-momentum | Not deployable | 90d direct backtest: 12 trades, net -14.57R, PF 0.05, risk of ruin 1. |
| intraday-momentum | Not deployable | 90d direct backtest produced 0 accepted trades; signal/gate mismatch. |
| ES/NQ meta strategy | Not deployable | 30d research-only script: 88 trades, -$21 before real costs, PF 0.78 ES / 0.98 NQ, max DD -$305. |
| rolling OOS selected profiles | Not deployable | 30d: 0/2 deployable; 90d: 0/4 deployable. Primary blockers: deflated expectancy and test trade count. |
| prediction-market copy/edge | Research/micro only | 4 paper candidates, but promotion still says research due committee reject/no-watch; Gengar has duplicate-window risk and no fillability proof. |

## Hard Safety Changes Applied

- Downgraded `short-term-reversal` and `ret-30-momentum` to BRONZE until canonical gates pass.
- Demo execution refuses non-GOLD/SILVER strategy classes.
- Synthetic demo fallback signals are always shadow-only.
- Demo exploration routing now requires `live-readiness-gate.readyForDemoExpansion === true`.
- ProjectX adapter fails closed and attempts flattening if protective stop placement fails after entry.
- NQ daily lock reserves trade count before submit and fails closed if state cannot be persisted.
- Cold archive no longer truncates JSONL by date grep and no longer deletes copied state unless explicitly enabled.

## Quant Rule Going Forward

A strategy can only move toward live if all are true:

1. Frozen rule spec and dataset manifest.
2. Rolling OOS has enough trades per fold and positive deflated expectancy.
3. Walk-forward and stressed live-readiness agree.
4. Paper/demo fill telemetry matches simulated slippage and fees.
5. No no-edge/non-promotable ledger conflict.
6. Board and Obsidian brain log show the exact evidence and current head.

## Next Sharp Question

Which lane should receive the next 24h of compute: prediction-market fillability/adverse-selection proof, or futures strategy repair around `ret-30-momentum`/`short-term-reversal` with a frozen spec?
