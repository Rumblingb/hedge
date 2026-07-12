# Prediction Market Analysis Import

Bill treats `jon-becker/prediction-market-analysis` as an isolated historical research corpus. Do not run upstream `make setup` from the Hedge repo.

## What It Adds

- Kalshi win-rate-by-price calibration.
- Kalshi maker/taker excess return buckets.
- Polymarket win-rate-by-price calibration when resolved token mappings are available.
- Compact JSON artifacts for Hermes and Bill research review.

## Safety Model

- No automatic download.
- No network calls in the importer.
- No writes outside the configured output directory.
- Bounded parquet reads with `--max-files-per-table`.
- Dataset remains research-only and must not promote paper/live execution.

## Commands

Check readiness:

```bash
npm run bill:prediction-market-analysis-status
```

Dry-run importer once the extracted data exists:

```bash
python3 scripts/prediction-market-analysis-import.py \
  --data-root .rumbling-hedge/external/prediction-market-analysis/data \
  --out-dir .rumbling-hedge/research/prediction-market-analysis \
  --dry-run
```

Run a bounded import:

```bash
python3 scripts/prediction-market-analysis-import.py \
  --data-root .rumbling-hedge/external/prediction-market-analysis/data \
  --out-dir .rumbling-hedge/research/prediction-market-analysis \
  --max-files-per-table 25
```

Install the optional parquet reader:

```bash
python3 -m pip install --user duckdb
```

## Hermes Feed

Hermes should read:

- `/Users/baskar_viji/.hermes/workspace/bill/PREDICTION_MARKET_ANALYSIS.md`
- `.rumbling-hedge/research/prediction-market-analysis/readiness.json`
- `.rumbling-hedge/research/prediction-market-analysis/summary.json`

Hermes may summarize readiness and import blockers. Hermes must not download the archive, install packages, or widen execution authority without founder approval.
