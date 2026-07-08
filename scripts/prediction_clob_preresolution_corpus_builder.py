#!/usr/bin/env python3
"""Build a pre-resolution CLOB microstructure corpus for resolved-label replay.

Research-only, read-only. Consumes the output of
`polymarket_clob_preresolution_capture.mjs` (pre_resolution_book + market_meta
records) together with resolved-outcome labels, and emits a parquet in the EXACT
schema expected by `prediction_clob_resolved_label_feature_replay.py`, with
microstructure populated at fraction-elapsed <= max_elig_frac (pre-resolution).

This closes the capture-design gap documented in kanban t_d6a63517: the historical
BrockMisner source only carries microstructure at frac>=0.83, so the replay's forward
mode had 0 eligible rows. Here microstructure genuinely exists <=0.5, so a
non-tautological forward test is possible.

Inputs:
  --capture   : jsonl from the pre-resolution capturer (pre_resolution_book / market_meta)
  --labels    : json {market_id: 0|1} resolved outcome (1 = up wins)
  --market-times : json {market_id: {start_ts, end_ts}} epoch ms
  --output    : parquet path

Offline test mode: you can pass --synthetic to emit a deterministic synthetic corpus
without external inputs (used by the test suite / when live capture is unavailable).

The emitted parquet contains, per eligible pre-resolution snapshot:
  market_id, ts, up_price, down_price, question, volume, resolution,
  start_ts, end_ts, target_up_win, target_down_win, avg_spread,
  up_bid_depth, up_ask_depth, down_bid_depth, down_ask_depth,
  up_depth_imbalance, down_depth_imbalance, ob_rows,
  trade_count, trade_usdc, buy_usdc, sell_usdc, trade_flow_imbalance, avg_trade_price,
  spot_price, spot_delta, spot_ret_1bar, spot_mom_3bar, spot_mom_12bar,
  spot_vol_12bar, spot_vol_48bar, parsed_strike, spot_distance_to_strike,
  spot_distance_to_strike_pct, seconds_to_expiry_bucket, up_ob_mid, down_ob_mid,
  up_price_delta, down_price_delta, ts(col)
(replay needs market_id, ts, target_up_win, the OB columns, avg_spread, start_ts, end_ts.)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

REPLAY_SCHEMA_COLS = [
    "market_id", "ts", "up_price", "down_price", "up_price_delta", "down_price_delta",
    "question", "volume", "resolution", "start_ts", "end_ts", "target_up_win",
    "target_down_win", "parsed_strike", "spot_distance_to_strike",
    "spot_distance_to_strike_pct", "seconds_to_expiry_bucket", "avg_spread",
    "up_ob_mid", "down_ob_mid", "up_bid_depth", "up_ask_depth", "down_bid_depth",
    "down_ask_depth", "up_depth_imbalance", "down_depth_imbalance", "ob_rows",
    "trade_count", "trade_usdc", "buy_usdc", "sell_usdc", "trade_flow_imbalance",
    "avg_trade_price", "spot_price", "spot_delta", "spot_ret_1bar", "spot_mom_3bar",
    "spot_mom_12bar", "spot_vol_12bar", "spot_vol_48bar",
]


def safe_ratio(a: float, b: float) -> float:
    a = float(a or 0)
    b = float(b or 0)
    d = a + b
    return float((a - b) / d) if d > 0 else 0.0


def read_capture(path: Path) -> list[dict]:
    rows: list[dict] = []
    try:
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
                if isinstance(item, dict):
                    rows.append(item)
            except Exception:
                continue
    except FileNotFoundError:
        return []
    return rows


def build_from_capture(capture_path: Path, labels: dict, market_times: dict,
                       max_elig_frac: float) -> pd.DataFrame:
    rows = read_capture(capture_path)
    snaps = [r for r in rows if r.get("eventType") == "pre_resolution_book"]
    metas = {r.get("marketId"): r for r in rows if r.get("eventType") == "market_meta"}
    out = []
    for s in snaps:
        mid = str(s.get("marketId"))
        frac = s.get("frac")
        if frac is None or frac > max_elig_frac:
            continue
        label = labels.get(mid)
        if label is None:
            continue  # only build labelled pre-resolution rows
        mt = market_times.get(mid) or metas.get(mid) or {}
        start_ts = int(mt.get("start_ts") or s.get("start_ts") or 0)
        end_ts = int(mt.get("end_ts") or s.get("end_ts") or 0)
        up_best = float(s["upBestBid"] + s["upBestAsk"]) / 2
        down_best = float(s["downBestBid"] + s["downBestAsk"]) / 2
        record = {
            "market_id": mid,
            "ts": int(start_ts + frac * (end_ts - start_ts)),
            "up_price": up_best,
            "down_price": down_best,
            "up_price_delta": 0.0,
            "down_price_delta": 0.0,
            "question": s.get("question") or metas.get(mid, {}).get("question"),
            "volume": 0.0,
            "resolution": int(label),
            "start_ts": start_ts,
            "end_ts": end_ts,
            "target_up_win": int(label),
            "target_down_win": int(1 - label),
            "parsed_strike": 0.0,
            "spot_distance_to_strike": 0.0,
            "spot_distance_to_strike_pct": 0.0,
            "seconds_to_expiry_bucket": int((end_ts - (start_ts + frac * (end_ts - start_ts))) / 300),
            "avg_spread": float(s["avgSpread"]),
            "up_ob_mid": up_best,
            "down_ob_mid": down_best,
            "up_bid_depth": float(s["upBidDepth"]),
            "up_ask_depth": float(s["upAskDepth"]),
            "down_bid_depth": float(s["downBidDepth"]),
            "down_ask_depth": float(s["downAskDepth"]),
            "up_depth_imbalance": float(s["upDepthImbalance"] if s.get("upDepthImbalance") is not None else safe_ratio(s["upBidDepth"], s["upAskDepth"])),
            "down_depth_imbalance": float(s["downDepthImbalance"] if s.get("downDepthImbalance") is not None else safe_ratio(s["downBidDepth"], s["downAskDepth"])),
            "ob_rows": 1,
            "trade_count": 0,
            "trade_usdc": 0.0,
            "buy_usdc": 0.0,
            "sell_usdc": 0.0,
            "trade_flow_imbalance": 0.0,
            "avg_trade_price": 0.0,
            "spot_price": 0.0,
            "spot_delta": 0.0,
            "spot_ret_1bar": 0.0,
            "spot_mom_3bar": 0.0,
            "spot_mom_12bar": 0.0,
            "spot_vol_12bar": 0.0,
            "spot_vol_48bar": 0.0,
        }
        out.append(record)
    df = pd.DataFrame(out)
    if df.empty:
        df = pd.DataFrame(columns=REPLAY_SCHEMA_COLS)
    else:
        for c in REPLAY_SCHEMA_COLS:
            if c not in df.columns:
                df[c] = 0.0
        df = df[REPLAY_SCHEMA_COLS]
    return df


def build_synthetic(n_markets: int, rows_per_market: int, seed: int = 42) -> pd.DataFrame:
    """Deterministic synthetic pre-resolution corpus for offline tests.

    Microstructure is populated at frac in [0.05, 0.5] (pre-resolution). The resting
    imbalance correlation with the resolved outcome is mild (so the family is not
    tautological) but present (so a real signal exists to test the contract against).
    """
    rng = np.random.default_rng(seed)
    out = []
    for m in range(n_markets):
        mid = f"synthetic-market-{m:04d}"
        label = int(rng.integers(0, 2))  # 0/1 up-win
        start_ts = 1_700_000_000_000 + m * 86_400_000
        end_ts = start_ts + 7 * 86_400_000
        for r in range(rows_per_market):
            frac = round(float(rng.uniform(0.05, 0.5)), 4)
            ts = int(start_ts + frac * (end_ts - start_ts))
            # resting imbalance: mild signal toward the winner
            base = 0.1 * (1 if label == 1 else -1)
            up_imb = float(np.clip(base + rng.normal(0, 0.25), -1, 1))
            down_imb = float(np.clip(-up_imb + rng.normal(0, 0.1), -1, 1))
            up_bid = float(rng.uniform(200, 2000))
            up_ask = float(rng.uniform(200, 2000))
            down_bid = float(rng.uniform(200, 2000))
            down_ask = float(rng.uniform(200, 2000))
            spread = float(rng.uniform(0.005, 0.04))
            out.append({
                "market_id": mid,
                "ts": ts,
                "up_price": 0.5 + 0.1 * up_imb,
                "down_price": 0.5 - 0.1 * up_imb,
                "up_price_delta": 0.0,
                "down_price_delta": 0.0,
                "question": f"Synthetic BTC up/down market {m}",
                "volume": float(rng.uniform(1000, 50000)),
                "resolution": int(label),
                "start_ts": start_ts,
                "end_ts": end_ts,
                "target_up_win": int(label),
                "target_down_win": int(1 - label),
                "parsed_strike": 0.0,
                "spot_distance_to_strike": 0.0,
                "spot_distance_to_strike_pct": 0.0,
                "seconds_to_expiry_bucket": int((end_ts - ts) / 300),
                "avg_spread": spread,
                "up_ob_mid": 0.5 + 0.1 * up_imb,
                "down_ob_mid": 0.5 - 0.1 * up_imb,
                "up_bid_depth": up_bid,
                "up_ask_depth": up_ask,
                "down_bid_depth": down_bid,
                "down_ask_depth": down_ask,
                "up_depth_imbalance": up_imb,
                "down_depth_imbalance": down_imb,
                "ob_rows": 1,
                "trade_count": int(rng.integers(0, 20)),
                "trade_usdc": float(rng.uniform(0, 5000)),
                "buy_usdc": float(rng.uniform(0, 2500)),
                "sell_usdc": float(rng.uniform(0, 2500)),
                "trade_flow_imbalance": float(rng.normal(0, 0.3)),
                "avg_trade_price": 0.5,
                "spot_price": float(rng.uniform(20000, 80000)),
                "spot_delta": 0.0,
                "spot_ret_1bar": 0.0,
                "spot_mom_3bar": 0.0,
                "spot_mom_12bar": 0.0,
                "spot_vol_12bar": 0.0,
                "spot_vol_48bar": 0.0,
            })
    return pd.DataFrame(out, columns=REPLAY_SCHEMA_COLS)


def main() -> int:
    ap = argparse.ArgumentParser(description="Build pre-resolution CLOB corpus for resolved-label replay.")
    ap.add_argument("--capture")
    ap.add_argument("--labels")
    ap.add_argument("--market-times")
    ap.add_argument("--output", required=True)
    ap.add_argument("--max-elig-frac", type=float, default=0.5)
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--synthetic-markets", type=int, default=40)
    ap.add_argument("--synthetic-rows-per-market", type=int, default=5)
    args = ap.parse_args()

    if args.synthetic:
        df = build_synthetic(args.synthetic_markets, args.synthetic_rows_per_market)
    else:
        if not args.capture or not args.labels:
            raise SystemExit("--capture and --labels are required (or pass --synthetic)")
        labels = json.loads(Path(args.labels).read_text())
        market_times = json.loads(Path(args.market_times).read_text()) if args.market_times else {}
        df = build_from_capture(Path(args.capture), labels, market_times, args.max_elig_frac)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    print(f"wrote {len(df):,} rows x {len(df.columns)} cols -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
