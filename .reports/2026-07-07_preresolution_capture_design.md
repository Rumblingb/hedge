# pre-resolution CLOB capture — design & proof (task t_d6a63517)

## Root cause (PROVEN)
The historical source `BrockMisner/polymarket-btc-updown` orderbook is
**resolution-window-only**. Across 616 resolved BTC markets, of 232,725 corpus rows only
**1,193 carry microstructure**, and 100% sit at fraction-elapsed >= 0.83 (median 0.997;
min first-populated frac per market = 0.829). **Zero rows at frac <= 0.5.**
=> Rebuilding the corpus from the same source reproduces the identical gap. Historical path
is a dead end; a *live capture* of pre-resolution order flow is required.

## Deliverables (new code)
- `scripts/polymarket_clob_preresolution_capture.mjs`
  - Captures BOTH outcome tokens per market, emits `pre_resolution_book` snapshots when
    frac <= 0.5 (configurable `--max-elig-frac`, default 0.5).
  - Reuses recorder's `selectAssetsWithDiagnostics` for market selection.
  - Offline `--replay-jsonl` mode (no network) reconstructs book state from recorded events.
  - Live WS mode for deployment (read-only, no keys, no orders).
- `scripts/prediction_clob_preresolution_corpus_builder.py`
  - Joins capture jsonl + resolved labels + market times into the replay's EXACT parquet schema
    (40 cols incl. `up_bid_depth, down_ask_depth, up_depth_imbalance, down_depth_imbalance,
    avg_spread, start_ts, end_ts, target_up_win`).
  - `--synthetic` mode (offline proof), `--capture` mode (live/recorded).
- `tests/test_preresolution_clob_pipeline.py` (4 tests, invokes REAL replay harness as subprocess)

## Proof (offline, deterministic)
40-market synthetic pre-resolution corpus -> REAL `prediction_clob_resolved_label_feature_replay.py`:
- mode: pre-resolution-forward
- eligibleRows: 200 (>= 30 gate cleared)
- populatedMicrostructureRows: 200 (microstructure now present at frac <= 0.5)
- crossValidatedAuc.meanTestAuc: 0.728
- negativeControlResolutionBarAuc: 0.7093 (tautology gate intact)
- verdict: watch-research-only (paper NOT approved — correct: synthetic = no real edge)

2-market live-style fixture also verified end-to-end (capture 4 labelled snapshots ->
corpus 4 rows -> replay 4 eligible rows, populated microstructure).

## Test results
`pytest tests/test_prediction_clob_*.py tests/test_preresolution_clob_pipeline.py` -> 9 passed
(5 existing + 4 new).

## Environment blockers THIS session (cannot fix in sandbox)
- Seagate external drive (`/Volumes/Seagate Expansion Drive`) unmounted; macOS
  DiskManagement framework unavailable in sandbox -> cannot remount.
- No network: DNS fails for huggingface.co / kaggle.com / ws-subscriptions-clob.polymarket.com.
- `~/Documents/memorybrain` (Obsidian vault) is TCC-blocked for writes -> this report written to
  `/Users/brain/hedge/.reports/` instead; run kanban comment carries the same text.

## Next actions (require live env)
1. Live capture: `node scripts/polymarket_clob_preresolution_capture.mjs --snapshot <live-snapshot>
   --duration-sec 86400 --out-dir <path> --max-elig-frac 0.5`  (needs WS network + mounted drive).
2. Persist capture jsonl; build corpus with resolved labels (resolver supplies target_up_win).
3. Re-run replay harness on the REAL captured corpus; only then is paper-eligibility meaningful.
