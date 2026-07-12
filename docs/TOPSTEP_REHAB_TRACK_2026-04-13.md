# Topstep Rehab Track 2026-04-13

## Mission

Treat the current NQ/index result as a failed first read, not a green light.

Use Hedge as the source of truth for a demo-first rehabilitation loop that is allowed to learn, prune, and stand down without pretending the path is already profitable.

## Practical workstreams

### 1) Research
- Extend real minute-bar coverage before changing strategy complexity.
- Run both `NQ` and `NQ+ES` views so single-symbol optimism does not hide index-family weakness.
- Keep the comparison set narrow: `ict-killzone-core` vs `trend-only`.

### 2) Strategy
- Keep the current rehab hypothesis simple: morning index continuation only, with ICT displacement as a candidate filter, not a license to widen risk.
- Do not add new strategies until the current lane is stable across windows.
- Do not loosen guardrails to manufacture trade count.

### 3) Validation
- Promotion is blocked unless data quality is green, trade count is sufficient, and walk-forward stability is positive.
- The current blocker is stability, not missing risk controls.
- Use rolling OOS and daily plan output as the truth source, not discretionary confidence.

### 4) Ops
- Keep `demo-only` and `read-only`.
- Treat `research-only` output as a valid operating state.
- Preserve journals, rejected signals, regime notes, and blocker reasons every session.

## What is failing right now

### Current verified read inside Hedge

`data/free/NQ-1m-5d.csv`
- data quality: pass
- winner: `ict-killzone-core`
- train net R: `-10.88`
- test net R: `3.59`
- test trades: `7`
- score stability: `0`
- promotion result: **fail** (`testTradeCount`, `scoreStability`)

`data/free/ALL-2MARKETS-NQ-ES-1m-5d-normalized.csv`
- data quality: pass
- winner: `trend-only`
- train net R: `-12.49`
- test net R: `2.21`
- test trades: `8`
- score stability: `0`
- promotion result: **fail** (`scoreStability`)

Historical rolling OOS read on the NQ/ES rehab slice:
- challenge aggregate survivability: `35.33`, deployable windows: `0`
- funded aggregate survivability: `52.67`, deployable windows: `0`

### Failure diagnosis

The NQ/index lane is failing because:
1. training windows are materially negative before the small positive test windows appear,
2. walk-forward stability is zero, so the profile ranking is not repeatable,
3. the lane depends on one market family, so there is no cross-family cushion,
4. risk tightening can reduce damage, but it does not create a deployable edge,
5. the current five-day slice is enough to reject promotion, but not enough to prove recovery.

This is a rehabilitation state, not a production state.

## Best next safe iteration inside Hedge

### Rehab step now

Do **not** widen hours, contracts, or strategy count.

Instead:
1. keep the lane in `research-only` / shadow mode,
2. extend the real minute-bar sample for `NQ` and `ES`,
3. rerun the paired rehab checks below on the larger sample,
4. only allow paper shadow review if stability improves and the selected execution plan produces an actual candidate.

### Paired rehab checks

Run both views every cycle:

```bash
npm run inspect-csv -- <new-nq-or-nq-es-file>
npm run data-quality -- <new-nq-or-nq-es-file>
npm run research -- data/free/NQ-1m-5d.csv
npm run research -- data/free/ALL-2MARKETS-NQ-ES-1m-5d-normalized.csv
npm run demo-tomorrow -- data/free/NQ-1m-5d.csv
npm run demo-tomorrow -- data/free/ALL-2MARKETS-NQ-ES-1m-5d-normalized.csv
```

### Rehab pass condition

The rehab lane is still blocked unless all of the following are true on the updated dataset:
- `promotionGate.ready` is true for the selected lane,
- score stability is above threshold,
- test performance remains positive after costs,
- the daily plan emits a real candidate instead of `research-only`,
- the account remains demo-only and reviewed.

## Explicit non-goals

- No live capital shortcuts.
- No claim that the current NQ lane is profitable.
- No risk loosening to force Topstep progress.
- No external execution or account changes without approval.
