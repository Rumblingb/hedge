#!/usr/bin/env python3
"""Local-only TimesFM CSV forecaster for Bill research.

By default this refuses to download model weights. Use --allow-download only
after founder approval. Outputs compact JSON for research review.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Any


DEFAULT_MODEL_ID = "google/timesfm-2.5-200m-pytorch"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run bounded local TimesFM forecasts from a CSV.")
    parser.add_argument("--csv", required=True, help="Input CSV with ts,symbol,close columns by default.")
    parser.add_argument("--out", required=True, help="Output JSON path.")
    parser.add_argument("--symbol-col", default="symbol")
    parser.add_argument("--time-col", default="ts")
    parser.add_argument("--value-col", default="close")
    parser.add_argument("--horizon", type=int, default=24)
    parser.add_argument("--max-context", type=int, default=512)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--model-id", default=DEFAULT_MODEL_ID)
    parser.add_argument("--allow-download", action="store_true", help="Allow Hugging Face weight download.")
    return parser.parse_args()


def hf_model_cache_dir(model_id: str) -> Path:
    hf_home = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface"))
    return hf_home / "hub" / f"models--{model_id.replace('/', '--')}"


def load_series(path: Path, symbol_col: str, time_col: str, value_col: str) -> dict[str, list[float]]:
    rows: dict[str, list[tuple[str, float]]] = defaultdict(list)
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            symbol = row.get(symbol_col) or "SERIES"
            raw = row.get(value_col)
            if raw is None or raw == "":
                continue
            try:
                value = float(raw)
            except ValueError:
                continue
            rows[symbol].append((row.get(time_col) or "", value))
    return {
        symbol: [value for _, value in sorted(values, key=lambda item: item[0])]
        for symbol, values in rows.items()
        if values
    }


def main() -> int:
    args = parse_args()
    cache_dir = hf_model_cache_dir(args.model_id)
    if not args.allow_download and not cache_dir.exists():
        payload = {
            "status": "blocked",
            "reason": "model weights are not cached locally and --allow-download was not provided",
            "modelId": args.model_id,
            "cacheDir": str(cache_dir),
        }
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(payload, indent=2) + "\n")
        print(json.dumps(payload, indent=2))
        return 2

    try:
        import numpy as np
        import torch
        import timesfm
    except ModuleNotFoundError as exc:
        payload = {
            "status": "blocked",
            "reason": f"missing Python package: {exc.name}",
            "installCommand": "python3 -m pip install --user 'timesfm[torch]'",
        }
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(payload, indent=2) + "\n")
        print(json.dumps(payload, indent=2))
        return 2

    series = load_series(Path(args.csv), args.symbol_col, args.time_col, args.value_col)
    if not series:
        raise SystemExit(f"no numeric {args.value_col} series found in {args.csv}")

    torch.set_float32_matmul_precision("high")
    model = timesfm.TimesFM_2p5_200M_torch.from_pretrained(
        args.model_id,
        local_files_only=not args.allow_download,
    )
    model.compile(
        timesfm.ForecastConfig(
            max_context=args.max_context,
            max_horizon=args.horizon,
            normalize_inputs=True,
            use_continuous_quantile_head=True,
            force_flip_invariance=True,
            infer_is_positive=True,
            fix_quantile_crossing=True,
            per_core_batch_size=args.batch_size,
        )
    )

    symbols = sorted(series)
    inputs = [np.asarray(series[symbol][-args.max_context :], dtype=np.float32) for symbol in symbols]
    point, quantiles = model.forecast(horizon=args.horizon, inputs=inputs)
    forecasts: list[dict[str, Any]] = []
    for index, symbol in enumerate(symbols):
        forecasts.append({
            "symbol": symbol,
            "contextRows": len(inputs[index]),
            "point": point[index].tolist(),
            "q10": quantiles[index, :, 1].tolist(),
            "q50": quantiles[index, :, 5].tolist(),
            "q90": quantiles[index, :, 9].tolist(),
        })

    payload = {
        "status": "ok",
        "modelId": args.model_id,
        "inputCsv": str(Path(args.csv).resolve()),
        "horizon": args.horizon,
        "maxContext": args.max_context,
        "batchSize": args.batch_size,
        "series": forecasts,
        "note": "Research-only forecast evidence. Do not route to execution without Bill promotion review."
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
