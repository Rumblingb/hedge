#!/usr/bin/env python3
"""Replay a fixed CLOB spread-compression feature.

Research-only. This changes one variable from the rejected CLOB drift baseline:
look for spread compression after a signed mid-price move, then test whether
the direction continues after half-spread cost. Thresholds are fixed up front;
the script does not mine parameters or approve paper/live routing.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
CLOB_DIR = ROOT / ".rumbling-hedge" / "prediction" / "clob"
DEFAULT_JSONL = CLOB_DIR / f"{datetime.now(timezone.utc).date().isoformat()}-market-channel.jsonl"
OUT = STATE / "prediction-clob-spread-compression-replay.latest.json"
VAULT = Path.home() / "Documents/memorybrain"
OUT_MD = VAULT / "Agent-Hermes" / "prediction-clob-spread-compression-replay-2026-05-30.md"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def to_float(value: Any) -> float | None:
    try:
        out = float(value)
        return out if math.isfinite(out) else None
    except Exception:
        return None


def parse_ts_ms(record: dict[str, Any]) -> int | None:
    local = record.get("localTs")
    if isinstance(local, str):
        try:
            return int(datetime.fromisoformat(local.replace("Z", "+00:00")).timestamp() * 1000)
        except Exception:
            pass
    exchange = to_float(record.get("exchangeTs") or record.get("timestamp"))
    return int(exchange) if exchange is not None else None


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        for line in path.read_text().splitlines():
            if not line.strip():
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


def add_quote(
    quotes: dict[str, list[dict[str, Any]]],
    *,
    asset: str,
    ts_ms: int,
    bid: Any,
    ask: Any,
    market: Any = None,
) -> None:
    best_bid = to_float(bid)
    best_ask = to_float(ask)
    if not asset or best_bid is None or best_ask is None:
        return
    if not (0 < best_bid < 1 and 0 < best_ask < 1 and best_ask >= best_bid):
        return
    quotes[asset].append({
        "assetId": asset,
        "market": market,
        "tsMs": ts_ms,
        "bid": best_bid,
        "ask": best_ask,
        "mid": (best_bid + best_ask) / 2,
        "spread": best_ask - best_bid,
    })


def extract_quotes(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    quotes: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        event = str(row.get("eventType") or row.get("event_type") or "")
        ts_ms = parse_ts_ms(row)
        if ts_ms is None:
            continue
        if event == "best_bid_ask":
            add_quote(
                quotes,
                asset=str(row.get("assetId") or row.get("asset_id") or ""),
                ts_ms=ts_ms,
                bid=row.get("bestBid") or row.get("best_bid"),
                ask=row.get("bestAsk") or row.get("best_ask"),
                market=row.get("market"),
            )
        elif event == "price_change":
            for change in row.get("priceChanges") or []:
                if not isinstance(change, dict):
                    continue
                add_quote(
                    quotes,
                    asset=str(change.get("asset_id") or change.get("assetId") or ""),
                    ts_ms=ts_ms,
                    bid=change.get("best_bid") or change.get("bestBid"),
                    ask=change.get("best_ask") or change.get("bestAsk"),
                    market=row.get("market"),
                )
    for asset_rows in quotes.values():
        asset_rows.sort(key=lambda item: item["tsMs"])
    return quotes


def future_quote(quotes: list[dict[str, Any]], start_index: int, horizon_ms: int) -> dict[str, Any] | None:
    target = quotes[start_index]["tsMs"] + horizon_ms
    for row in quotes[start_index + 1:]:
        if row["tsMs"] >= target:
            return row
    return None


def replay_window(
    quotes: dict[str, list[dict[str, Any]]],
    *,
    window_sec: int,
    lookback_sec: int,
    min_spread_compression: float,
    min_abs_mid_move: float,
    max_start_spread: float,
) -> dict[str, Any]:
    samples = []
    horizon_ms = window_sec * 1000
    lookback_ms = lookback_sec * 1000
    for asset_rows in quotes.values():
        left = 0
        for idx, row in enumerate(asset_rows):
            while left < idx and asset_rows[left]["tsMs"] < row["tsMs"] - lookback_ms:
                left += 1
            if left >= idx or row["spread"] > max_start_spread:
                continue
            prior = asset_rows[left]
            compression = prior["spread"] - row["spread"]
            mid_move = row["mid"] - prior["mid"]
            if compression < min_spread_compression:
                continue
            if abs(mid_move) < min_abs_mid_move:
                continue
            direction = 1 if mid_move > 0 else -1
            future = future_quote(asset_rows, idx, horizon_ms)
            if not future:
                continue
            gross = direction * (future["mid"] - row["mid"])
            net = gross - (row["spread"] / 2)
            samples.append({
                "assetId": row["assetId"],
                "market": row.get("market"),
                "windowSec": window_sec,
                "lookbackSec": lookback_sec,
                "spreadCompression": round(compression, 6),
                "priorSpread": round(prior["spread"], 6),
                "startSpread": round(row["spread"], 6),
                "signedMidMove": round(mid_move, 6),
                "direction": "long-yes" if direction > 0 else "short-yes",
                "grossForwardMove": gross,
                "netAfterHalfSpread": net,
                "hit": gross > 0,
            })
    hits = sum(1 for item in samples if item["hit"])
    mean_net = sum(item["netAfterHalfSpread"] for item in samples) / len(samples) if samples else None
    mean_gross = sum(item["grossForwardMove"] for item in samples) / len(samples) if samples else None
    median_spread = None
    if samples:
        spreads = sorted(item["startSpread"] for item in samples)
        median_spread = spreads[len(spreads) // 2]
    return {
        "windowSec": window_sec,
        "samples": len(samples),
        "hitRate": round(hits / len(samples), 6) if samples else None,
        "meanGrossMove": round(mean_gross, 6) if mean_gross is not None else None,
        "meanNetAfterHalfSpread": round(mean_net, 6) if mean_net is not None else None,
        "medianSpread": round(median_spread, 6) if median_spread is not None else None,
        "sampleRows": samples[:200],
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    rows = read_jsonl(Path(args.input))
    quotes = extract_quotes(rows)
    windows = [
        replay_window(
            quotes,
            window_sec=window,
            lookback_sec=args.lookback_sec,
            min_spread_compression=args.min_spread_compression,
            min_abs_mid_move=args.min_abs_mid_move,
            max_start_spread=args.max_start_spread,
        )
        for window in args.windows
    ]
    results = []
    for item in windows:
        blockers = []
        if item["samples"] < args.min_samples:
            blockers.append("too-few-samples")
        if item["hitRate"] is None or item["hitRate"] < args.min_hit_rate:
            blockers.append("hit-rate-below-contract")
        if item["meanNetAfterHalfSpread"] is None or item["meanNetAfterHalfSpread"] < args.min_net:
            blockers.append("net-after-half-spread-below-contract")
        results.append({key: value for key, value in item.items() if key != "sampleRows"} | {
            "verdict": "watch-research-only" if not blockers else "reject",
            "blockers": blockers,
        })
    watch = [item for item in results if item["verdict"] == "watch-research-only"]
    return {
        "command": "prediction-clob-spread-compression-replay",
        "generatedAt": now_iso(),
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "readyForPaper": False,
        "inputPath": str(Path(args.input).resolve()),
        "recordsRead": len(rows),
        "assetsWithQuotes": len(quotes),
        "quoteFeatureRows": sum(len(items) for items in quotes.values()),
        "fixedThresholds": {
            "lookbackSec": args.lookback_sec,
            "minSpreadCompression": args.min_spread_compression,
            "minAbsMidMove": args.min_abs_mid_move,
            "maxStartSpread": args.max_start_spread,
            "minSamples": args.min_samples,
            "minHitRate": args.min_hit_rate,
            "minNetAfterHalfSpread": args.min_net,
        },
        "results": results,
        "watchResearchCount": len(watch),
        "decision": "watch-research-only-not-paper" if watch else "research-only-no-spread-compression-edge",
        "nextAction": "Join to resolved labels and fee/fillability before paper review." if watch else "Do not rerun this exact spread-compression fixed form without a new label/source/feature.",
    }


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Prediction CLOB Spread Compression Replay - 2026-05-30",
        "",
        "Parent hub: [[BILL-CONTROL-HUB]]",
        "",
        "Research-only one-variable replay. This page does not approve paper or live trading.",
        "",
        "## Summary",
        "",
        f"- Decision: `{payload.get('decision')}`",
        f"- Records read: `{payload.get('recordsRead')}`",
        f"- Quote feature rows: `{payload.get('quoteFeatureRows')}`",
        f"- Watch research count: `{payload.get('watchResearchCount')}`",
        f"- Fixed thresholds: `{payload.get('fixedThresholds')}`",
        "",
        "## Windows",
        "",
    ]
    for item in payload.get("results") or []:
        lines.append(
            f"- `{item.get('windowSec')}s`: samples `{item.get('samples')}`, hit `{item.get('hitRate')}`, "
            f"net `{item.get('meanNetAfterHalfSpread')}`, verdict `{item.get('verdict')}`, blockers `{item.get('blockers')}`"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay fixed CLOB spread-compression feature.")
    parser.add_argument("--input", default=str(DEFAULT_JSONL))
    parser.add_argument("--output", default=str(OUT))
    parser.add_argument("--markdown-output", default=str(OUT_MD))
    parser.add_argument("--windows", type=lambda value: [int(item) for item in value.split(",")], default=[15, 60])
    parser.add_argument("--lookback-sec", type=int, default=60)
    parser.add_argument("--min-spread-compression", type=float, default=0.003)
    parser.add_argument("--min-abs-mid-move", type=float, default=0.001)
    parser.add_argument("--max-start-spread", type=float, default=0.05)
    parser.add_argument("--min-samples", type=int, default=30)
    parser.add_argument("--min-hit-rate", type=float, default=0.55)
    parser.add_argument("--min-net", type=float, default=0.0025)
    args = parser.parse_args()
    payload = build_report(args)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    md = Path(args.markdown_output)
    md.parent.mkdir(parents=True, exist_ok=True)
    md.write_text(render_markdown(payload))
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
