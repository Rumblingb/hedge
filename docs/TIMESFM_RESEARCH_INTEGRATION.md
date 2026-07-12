# TimesFM Research Integration

Bill treats `google-research/timesfm` as an optional research-only forecasting engine.

## Placement

TimesFM belongs beside Kronos and Markov:

- `src/research/timesfm.ts` checks local readiness.
- `scripts/timesfm-forecast-local.py` runs bounded local forecasts once approved.
- Hermes reads `.rumbling-hedge/research/timesfm/readiness.json`.

It should not sit in prediction execution, futures demo execution, or promotion logic.

## Why It Is Useful

- Zero-shot probabilistic forecasts for futures/crypto/macro bars.
- Quantile bands for regime and anomaly evidence.
- Research comparison against Markov, Kronos, rolling mean, and walk-forward baselines.
- Possible context feature for Bill's opportunity board after OOS validation.

## Safety Model

- No package install by default.
- No model-weight download by default.
- Forecast script refuses to download unless `--allow-download` is passed.
- Output is research evidence only.
- No paper/live promotion can be based on TimesFM alone.

## Commands

Readiness:

```bash
npm run bill:timesfm-status --silent
```

Future forecast after approval and local setup:

```bash
python3 scripts/timesfm-forecast-local.py \
  --csv data/free/ALL-6MARKETS-1m-10d-normalized.csv \
  --out .rumbling-hedge/research/timesfm/forecast.json \
  --horizon 24 \
  --max-context 512 \
  --batch-size 4
```

Optional install after approval:

```bash
python3 -m pip install --user 'timesfm[torch]'
```

Optional model cache after approval:

```bash
huggingface-cli download google/timesfm-2.5-200m-pytorch
```

## Current Expected State

On this Mac, TimesFM is expected to report `missing` until:

- Python package `timesfm` is installed.
- Python package `torch` is installed.
- Hugging Face model weights are cached locally.
- `BILL_TIMESFM_ALLOW_DOWNLOAD` remains false unless the founder explicitly approves a download.

## Hermes Rule

Hermes may monitor and summarize TimesFM readiness. Hermes must not install packages, download weights, run forecasts, or use TimesFM output to widen Bill's execution authority without founder approval.
