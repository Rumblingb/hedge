#!/usr/bin/env python3
"""Local-only TimesFM v1.0 CSV forecaster for Bill research.

Uses google/timesfm-1.0-200m-pytorch (torch_model.ckpt).
Requires model weights to be pre-downloaded (set HF_HOME).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Any

DEFAULT_MODEL_ID = "google/timesfm-1.0-200m-pytorch"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run bounded local TimesFM v1.0 forecasts from a CSV.")
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


def find_ckpt_path(model_id: str) -> Path | None:
    """Find the torch_model.ckpt for v1.0 PyTorch model."""
    hf_home = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface"))
    model_dir_name = f"models--{model_id.replace('/', '--')}"
    # Try both with and without hub/ prefix (different HF cache layouts)
    for hub_dir in [hf_home / model_dir_name, hf_home / "hub" / model_dir_name]:
        if hub_dir.exists():
            snapshots = list(hub_dir.glob("snapshots/*/torch_model.ckpt"))
            if snapshots:
                return snapshots[0]
    return None


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
    ckpt_path = find_ckpt_path(args.model_id)

    if ckpt_path is None and not args.allow_download:
        payload = {
            "status": "blocked",
            "reason": (
                f"model weights not found for {args.model_id} and --allow-download not provided. "
                "Download the v1.0 model: from huggingface_hub import hf_hub_download; "
                "hf_hub_download('google/timesfm-1.0-200m-pytorch', 'torch_model.ckpt', "
                "cache_dir=HF_HOME)"
            ),
            "modelId": args.model_id,
        }
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(payload, indent=2) + "\n")
        print(json.dumps(payload, indent=2))
        return 2

    try:
        import numpy as np
        import timesfm
    except ModuleNotFoundError as exc:
        payload = {
            "status": "blocked",
            "reason": f"missing Python package: {exc.name}",
            "installCommand": "python3 -m pip install --user 'timesfm>=1.3.0,<1.4.0'",
        }
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(payload, indent=2) + "\n")
        print(json.dumps(payload, indent=2))
        return 2

    series = load_series(Path(args.csv), args.symbol_col, args.time_col, args.value_col)
    if not series:
        raise SystemExit(f"no numeric {args.value_col} series found in {args.csv}")

    # v1.0 API: TimesFmHparams + TimesFmCheckpoint → TimesFm constructor
    hparams = timesfm.TimesFmHparams(
        context_len=args.max_context,
        horizon_len=args.horizon,
        backend="cpu",
        per_core_batch_size=args.batch_size,
    )
    ckpt = timesfm.TimesFmCheckpoint(
        version="torch",
        path=str(ckpt_path),
        type="pt",
    )
    model = timesfm.TimesFm(hparams=hparams, checkpoint=ckpt)

    symbols = sorted(series)
    inputs = np.stack([
        np.asarray(series[symbol][-args.max_context:], dtype=np.float32)
        for symbol in symbols
    ])
    freq = np.zeros(len(symbols), dtype=np.int32)
    point, quantiles = model.forecast(inputs, freq)
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
