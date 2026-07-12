#!/usr/bin/env python3
"""Research-only GEX backtest for index futures context.

This script studies whether SPY option-chain gamma exposure has next-session
predictive value for an equity-index proxy. It is deliberately research-only:
it never touches brokers, never writes orders, and never emits a tradable
signal. Use the output as a hypothesis seed for options/regime overlays.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
DEFAULT_OPTIONS_DIR = Path(os.environ.get(
    "BILL_GEX_OPTIONS_DIR",
    str(Path.home() / ".cache/kagglehub/datasets/dudesurfin/spy-options-eod-volatility-surface-2010-2023/versions/2"),
))
DEFAULT_RETURNS_CSV = ROOT / "data/free/30yr-cross-asset-market-data.csv"
DEFAULT_JSON = STATE / "gex-backtest.latest.json"
DEFAULT_CSV = ROOT / "data/research/gex-backtest-results.csv"


REQUIRED_OPTION_COLUMNS = {
    "[QUOTE_DATE]",
    "[UNDERLYING_LAST]",
    "[STRIKE]",
    "[C_SIZE]",
    "[P_SIZE]",
    "[C_VOLUME]",
    "[P_VOLUME]",
    "[C_GAMMA]",
    "[P_GAMMA]",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_size(value: Any) -> float:
    """Parse CBOE-style "bid x ask" size fields into a liquidity proxy."""
    if pd.isna(value):
        return 0.0
    try:
        bid_raw, ask_raw = str(value).lower().split("x", 1)
        return max(float(bid_raw.strip()), float(ask_raw.strip()))
    except Exception:
        return 0.0


def safe_rank_bins(series: pd.Series, bins: int) -> pd.Series:
    """Return stable integer rank bins even when sample size is small."""
    if len(series) == 0:
        return pd.Series(dtype="float64")
    rank = series.rank(method="first")
    bin_count = max(1, min(bins, len(rank)))
    labels = list(range(bin_count))
    binned = pd.qcut(rank, bin_count, labels=labels, duplicates="drop")
    values = pd.Series(binned, index=series.index).astype(float)
    if bin_count == 1:
        return values.fillna(0.0)
    midpoint = (bin_count - 1) / 2
    return values - midpoint


def compute_daily_gex(option_chain: pd.DataFrame) -> pd.DataFrame:
    missing = sorted(REQUIRED_OPTION_COLUMNS - set(option_chain.columns))
    if missing:
        raise ValueError(f"option chain missing required columns: {missing}")

    df = option_chain.copy()
    df["[QUOTE_DATE]"] = pd.to_datetime(df["[QUOTE_DATE]"]).dt.date.astype(str)
    df["c_size_num"] = df["[C_SIZE]"].apply(parse_size)
    df["p_size_num"] = df["[P_SIZE]"].apply(parse_size)
    df["c_eff_vol"] = np.where(df["[C_VOLUME]"] > 0, df["[C_VOLUME]"], df["c_size_num"])
    df["p_eff_vol"] = np.where(df["[P_VOLUME]"] > 0, df["[P_VOLUME]"], df["p_size_num"])
    df["call_gex"] = df["c_eff_vol"] * df["[C_GAMMA]"] * df["[UNDERLYING_LAST]"]
    df["put_gex"] = -df["p_eff_vol"] * df["[P_GAMMA]"] * df["[UNDERLYING_LAST]"]
    df["net_gex"] = df["call_gex"] + df["put_gex"]

    spot = df["[UNDERLYING_LAST]"]
    df["atm_mask"] = (df["[STRIKE]"] > spot * 0.85) & (df["[STRIKE]"] < spot * 1.15)
    df["atm_call_gex"] = df["atm_mask"] * df["call_gex"]
    df["atm_put_gex"] = df["atm_mask"] * df["put_gex"]
    df["atm_net_gex"] = df["atm_call_gex"] + df["atm_put_gex"]

    daily = df.groupby("[QUOTE_DATE]").agg({
        "net_gex": "sum",
        "atm_net_gex": "sum",
        "call_gex": "sum",
        "put_gex": "sum",
        "[UNDERLYING_LAST]": "last",
        "[C_VOLUME]": "sum",
        "[P_VOLUME]": "sum",
        "[C_GAMMA]": "mean",
        "[P_GAMMA]": "mean",
    }).reset_index()

    daily = daily.merge(compute_gamma_flip_levels(df), on="[QUOTE_DATE]", how="left")
    daily["gex_pct"] = daily["net_gex"] / daily["[UNDERLYING_LAST]"] / 100
    daily["atm_gex_pct"] = daily["atm_net_gex"] / daily["[UNDERLYING_LAST]"] / 100
    for col in ["gex_pct", "atm_gex_pct"]:
        lo, hi = daily[col].quantile([0.01, 0.99])
        daily[f"{col}_w"] = daily[col].clip(lo, hi)
    daily["gex_rank"] = safe_rank_bins(daily["gex_pct_w"], 10)
    daily["atm_gex_rank"] = safe_rank_bins(daily["atm_gex_pct_w"], 10)
    return daily


def compute_gamma_flip_levels(df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for quote_date, group in df.groupby("[QUOTE_DATE]"):
        spot = float(group["[UNDERLYING_LAST]"].iloc[0])
        near = group[(group["[STRIKE]"] > spot * 0.8) & (group["[STRIKE]"] < spot * 1.2)].copy()
        if near.empty:
            near = group.copy()
        near = near.sort_values("[STRIKE]")
        near["weighted_gamma"] = (
            near["c_size_num"] * near["[C_GAMMA]"] +
            near["p_size_num"] * near["[P_GAMMA]"]
        )
        near["cum_gamma"] = near["weighted_gamma"].cumsum()
        total_gamma = float(near["weighted_gamma"].sum())
        if total_gamma == 0:
            flip = float(near["[STRIKE]"].iloc[len(near) // 2])
        else:
            half = total_gamma / 2
            crossed = near[near["cum_gamma"] >= half]
            flip = float((crossed if not crossed.empty else near)["[STRIKE]"].iloc[0])
        rows.append({"[QUOTE_DATE]": quote_date, "gamma_flip": flip})
    return pd.DataFrame(rows)


def load_options_gex(options_dir: Path, start_year: int, end_year: int) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    daily_frames: list[pd.DataFrame] = []
    files: list[dict[str, Any]] = []
    for year in range(start_year, end_year + 1):
        path = options_dir / f"spy_eod_{year}.parquet"
        if not path.exists():
            files.append({"year": year, "path": str(path), "status": "missing"})
            continue
        chain = pd.read_parquet(path)
        daily = compute_daily_gex(chain)
        daily_frames.append(daily)
        files.append({"year": year, "path": str(path), "status": "loaded", "rows": int(len(chain)), "days": int(len(daily))})
    if not daily_frames:
        raise FileNotFoundError(f"no spy_eod_YYYY.parquet files found in {options_dir}")
    return pd.concat(daily_frames, ignore_index=True), files


def load_return_proxy(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"return proxy CSV not found: {path}")
    df = pd.read_csv(path)
    if {"Date", "S&P500"}.issubset(df.columns):
        out = df[["Date", "S&P500"]].copy()
        out.columns = ["date", "proxy_close"]
    elif {"date", "close"}.issubset(df.columns):
        out = df[["date", "close"]].copy()
        out.columns = ["date", "proxy_close"]
    else:
        raise ValueError("return proxy CSV must contain Date/S&P500 or date/close columns")
    out["date"] = pd.to_datetime(out["date"])
    out["proxy_return"] = out["proxy_close"].pct_change().shift(-1)
    return out


def metric_stats(series: pd.Series) -> dict[str, Any]:
    clean = series.dropna()
    std = float(clean.std()) if len(clean) else 0.0
    mean = float(clean.mean()) if len(clean) else 0.0
    return {
        "meanDailyReturn": mean,
        "sharpe": mean / std * float(np.sqrt(252)) if std > 0 else None,
        "count": int(len(clean)),
    }


def run_backtest(gex: pd.DataFrame, returns: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    merged = gex.copy()
    merged["date"] = pd.to_datetime(merged["[QUOTE_DATE]"])
    merged = merged.merge(returns, on="date", how="inner")
    if merged.empty:
        raise ValueError("GEX data has no overlapping dates with return proxy")

    merged["gex_quintile"] = pd.qcut(
        merged["atm_gex_pct_w"].rank(method="first"),
        min(5, len(merged)),
        labels=False,
        duplicates="drop",
    )
    merged["negative_atm_gex"] = merged["atm_gex_pct_w"] < 0
    merged["signal_sign_atm_gex"] = np.where(merged["atm_gex_pct_w"] > 0, 1, -1)
    merged["signal_rank_gex"] = np.sign(merged["gex_rank"])
    merged["signal_extreme_deciles"] = np.where(merged["gex_rank"] >= 2, 1, np.where(merged["gex_rank"] <= -2, -1, 0))
    merged["ret_sign_atm_gex"] = merged["signal_sign_atm_gex"] * merged["proxy_return"]
    merged["ret_rank_gex"] = merged["signal_rank_gex"] * merged["proxy_return"]
    merged["ret_extreme_deciles"] = merged["signal_extreme_deciles"] * merged["proxy_return"]
    merged["spot_vs_flip"] = (merged["[UNDERLYING_LAST]"] - merged["gamma_flip"]).abs() / merged["[UNDERLYING_LAST]"]
    merged["near_flip"] = merged["spot_vs_flip"] < 0.02

    metrics = {
        "rows": int(len(merged)),
        "dateRange": {
            "start": merged["date"].min().date().isoformat(),
            "end": merged["date"].max().date().isoformat(),
        },
        "buyHold": metric_stats(merged["proxy_return"]),
        "signAtmGex": metric_stats(merged["ret_sign_atm_gex"]),
        "rankGex": metric_stats(merged["ret_rank_gex"]),
        "extremeDeciles": metric_stats(merged.loc[merged["signal_extreme_deciles"] != 0, "ret_extreme_deciles"]),
        "negativeAtmGex": metric_stats(merged.loc[merged["negative_atm_gex"], "proxy_return"]),
        "positiveAtmGex": metric_stats(merged.loc[~merged["negative_atm_gex"], "proxy_return"]),
        "nearGammaFlip": metric_stats(merged.loc[merged["near_flip"], "proxy_return"]),
        "farFromGammaFlip": metric_stats(merged.loc[~merged["near_flip"], "proxy_return"]),
    }
    return merged, metrics


def blocked_payload(reason: str, **extra: Any) -> dict[str, Any]:
    return {
        "command": "gex-backtest",
        "generatedAt": now_iso(),
        "decision": "research-only-gex-backtest-blocked",
        "reason": reason,
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "movesFunds": False,
        "readyForExecution": False,
        "readyForDemoExpansion": False,
        "readyForLive": False,
        **extra,
    }


def build_payload(metrics: dict[str, Any], *, files: list[dict[str, Any]], output_csv: Path) -> dict[str, Any]:
    return {
        "command": "gex-backtest",
        "generatedAt": now_iso(),
        "decision": "research-only-gex-backtest-complete",
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "movesFunds": False,
        "readyForExecution": False,
        "readyForDemoExpansion": False,
        "readyForLive": False,
        "operatorRead": (
            "GEX backtest is a slow options/regime research seed only. It is not a futures "
            "route, not broker evidence, and not approval for sizing or live/demo trading."
        ),
        "promotionBlockers": [
            "requires no-lookahead futures replay with current broker-grade data",
            "requires purged walk-forward and cost/slippage stress",
            "requires daily Bill route approval and broker reconciliation before any demo discussion",
        ],
        "metrics": metrics,
        "loadedOptionFiles": files,
        "csvOutput": str(output_csv),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run research-only GEX backtest.")
    parser.add_argument("--options-dir", default=str(DEFAULT_OPTIONS_DIR))
    parser.add_argument("--returns-csv", default=str(DEFAULT_RETURNS_CSV))
    parser.add_argument("--start-year", type=int, default=2010)
    parser.add_argument("--end-year", type=int, default=2023)
    parser.add_argument("--output-json", default=str(DEFAULT_JSON))
    parser.add_argument("--output-csv", default=str(DEFAULT_CSV))
    parser.add_argument("--compact", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_json = Path(args.output_json)
    output_csv = Path(args.output_csv)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_csv.parent.mkdir(parents=True, exist_ok=True)

    try:
        gex, files = load_options_gex(Path(args.options_dir), args.start_year, args.end_year)
        returns = load_return_proxy(Path(args.returns_csv))
        merged, metrics = run_backtest(gex, returns)
        save_cols = [
            "date",
            "atm_gex_pct_w",
            "atm_gex_rank",
            "gex_rank",
            "net_gex",
            "atm_net_gex",
            "gamma_flip",
            "[UNDERLYING_LAST]",
            "proxy_close",
            "proxy_return",
            "gex_quintile",
            "signal_sign_atm_gex",
            "ret_sign_atm_gex",
            "spot_vs_flip",
            "near_flip",
        ]
        merged[[col for col in save_cols if col in merged.columns]].to_csv(output_csv, index=False)
        payload = build_payload(metrics, files=files, output_csv=output_csv)
    except Exception as exc:
        payload = blocked_payload(
            str(exc),
            optionsDir=str(Path(args.options_dir)),
            returnsCsv=str(Path(args.returns_csv)),
        )

    output_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    if args.compact:
        print(json.dumps({
            "decision": payload["decision"],
            "readyForExecution": payload["readyForExecution"],
            "reason": payload.get("reason"),
            "metrics": payload.get("metrics"),
        }, sort_keys=True))
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
