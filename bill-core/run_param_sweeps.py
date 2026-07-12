#!/usr/bin/env python3
"""Run parameter sweeps for top strategies using param_sweep binary."""

import subprocess
import json
import sys
import os
from datetime import datetime
from itertools import product

BINARY = "./target/release/param_sweep"
DATA_DIR = "../data/free"

SWEEPS = {
    # 1. ORB-BREAKOUT on 15m and 30m
    "orb-breakout-15m": {
        "csv": f"{DATA_DIR}/ALL-2MARKETS-NQ-ES-1m-21d-normalized-15m.csv",
        "strategy": "orb-breakout",
        "params_base": {},
        "sweep_params": {
            "--range-window": [8, 10, 12, 14, 16, 20],
            "--vol-threshold": [1.3, 1.5, 2.0],
            "--exit-offset": [3, 5, 8],
        },
    },
    "orb-breakout-30m": {
        "csv": f"{DATA_DIR}/ALL-2MARKETS-NQ-ES-1m-21d-normalized-30m.csv",
        "strategy": "orb-breakout",
        "params_base": {},
        "sweep_params": {
            "--range-window": [8, 10, 12, 14, 16, 20],
            "--vol-threshold": [1.3, 1.5, 2.0],
            "--exit-offset": [3, 5, 8],
        },
    },
    # 2. WQ-TREND-MOM on 30m
    "wq-trend-mom-30m": {
        "csv": f"{DATA_DIR}/ALL-2MARKETS-NQ-ES-1m-21d-normalized-30m.csv",
        "strategy": "wq-trend-mom",
        "params_base": {},
        "sweep_params": {
            "--sma-short": [10, 15, 20, 30],
            "--sma-long": [30, 40, 50, 60],
            "--vol-threshold": [1.3, 1.5],
            "--exit-offset": [3, 5, 8],
        },
    },
    # 3. WQ-VOL-REGIME on 60m
    "wq-vol-regime-60m": {
        "csv": f"{DATA_DIR}/ALL-2MARKETS-NQ-ES-1m-21d-normalized-60m.csv",
        "strategy": "wq-vol-regime",
        "params_base": {},
        "sweep_params": {
            "--short-lookback": [5, 10, 15, 20],
            "--long-lookback": [20, 30, 40, 50],
            "--short-threshold": [1.3, 1.4, 1.5, 1.6, 1.7, 2.0],
            "--long-threshold": [0.5, 0.6, 0.7, 0.8, 0.9],
            "--exit-offset": [3, 5, 8],
        },
    },
}

def run_single(params: dict) -> dict:
    cmd = [BINARY, "--csv", params["csv"], "--strategy", params["strategy"], "--symbol", "NQ"]
    for k, v in params.items():
        if k in ("csv", "strategy"):
            continue
        cmd.extend([f"--{k.replace('_', '-')}", str(v)])
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        return {"error": result.stderr.strip()}
    try:
        return json.loads(result.stdout.strip())
    except json.JSONDecodeError:
        return {"error": result.stdout.strip()[:200]}

def run_sweep(name: str, config: dict) -> list[dict]:
    results = []
    keys = list(config["sweep_params"].keys())
    values = list(config["sweep_params"].values())
    total = 1
    for v in values:
        total *= len(v)
    print(f"\n{'='*60}")
    print(f"Sweep: {name} — {total} configs")
    print(f"{'='*60}")

    for combo in product(*values):
        params = {
            "csv": config["csv"],
            "strategy": config["strategy"],
        }
        param_label_parts = []
        for k, v in zip(keys, combo):
            param_key = k.lstrip("-").replace("-", "_")
            params[param_key] = v
            param_label_parts.append(f"{k.lstrip('-')}={v}")

        label = ",".join(param_label_parts)
        result = run_single(params)
        if "error" in result:
            print(f"  ERROR {label}: {result['error']}")
            continue
        results.append(result)
        print(f"  {label}: {result.get('trades',0)}t {result.get('wr',0):.1f}% R={result.get('total_r',0):.2f} avg={result.get('avg_r',0):.2f}")

    return results

def print_top(results: list[dict], top_n: int = 10):
    sorted_results = sorted(results, key=lambda r: r.get("total_r", 0), reverse=True)
    print(f"\n{'='*60}")
    print(f"TOP {top_n} RESULTS")
    print(f"{'='*60}")
    for r in sorted_results[:top_n]:
        # Filter to only show the strategy-specific params
        skip_keys = {"csv", "symbol", "strategy", "trades", "wins", "losses", "wr", "total_r", "avg_r"}
        param_parts = [f"{k}={v}" for k, v in r.items() if k not in skip_keys]
        print(f"  {' '.join(param_parts):<50s} | {r['trades']:>4d}t WR={r['wr']:>5.1f}% R={r['total_r']:>8.2f} avg={r['avg_r']:>6.2f}")

def main():
    all_results = {}

    for name, config in SWEEPS.items():
        results = run_sweep(name, config)
        all_results[name] = results
        print_top(results, 10)

    # Summary table
    print(f"\n{'='*60}")
    print("SUMMARY: BEST CONFIG PER SWEEP")
    print(f"{'='*60}")
    for name, results in all_results.items():
        if not results:
            continue
        best = max(results, key=lambda r: r.get("total_r", 0))
        skip_keys = {"csv", "symbol", "strategy", "trades", "wins", "losses", "wr", "total_r", "avg_r"}
        param_parts = [f"{k}={v}" for k, v in best.items() if k not in skip_keys]
        print(f"  {name:<25s} | {' '.join(param_parts):<45s} | {best['trades']:>4d}t WR={best['wr']:>5.1f}% R={best['total_r']:>8.2f}")

if __name__ == "__main__":
    main()
