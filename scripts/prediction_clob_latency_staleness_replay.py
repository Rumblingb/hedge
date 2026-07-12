#!/usr/bin/env python3
"""Replay a fixed CLOB latency/staleness feature.

Research-only. This changes one variable from the rejected CLOB drift baseline:
use quote latency/staleness as a fixed filter before testing signed mid-price
continuation. Thresholds are fixed up front; the script does not mine
parameters or approve paper/live routing.
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
OUT = STATE / "prediction-clob-latency-staleness-replay.latest.json"
VAULT = Path.home() / "Documents/memorybrain"
OUT_MD = VAULT / "Agent-Hermes" / "prediction-clob-latency-staleness-replay-2026-05-30.md"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def to_float(value: Any) -> float | None:
    try:
        out = float(value)
        return out if math.isfinite(out) else None
    except Exception:
        return None


def iso_ms(value: Any) -> int | None:
    if not isinstance(value, str):
        return None
    try:
        return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)
    except Exception:
        return None


def exchange_ms(record: dict[str, Any]) -> int | None:
    value = to_float(record.get("exchangeTs") or record.get("timestamp"))
    return int(value) if value is not None else None


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
    local_ms: int | None,
    exchange_ts_ms: int | None,
    bid: Any,
    ask: Any,
    market: Any = None,
) -> None:
    best_bid = to_float(bid)
    best_ask = to_float(ask)
    if not asset or local_ms is None or best_bid is None or best_ask is None:
        return
    if not (0 < best_bid < 1 and 0 < best_ask < 1 and best_ask >= best_bid):
        return
    latency_ms = None
    if exchange_ts_ms is not None:
        latency_ms = max(0, local_ms - exchange_ts_ms)
    quotes[asset].append({
        "assetId": asset,
        "market": market,
        "localMs": local_ms,
        "exchangeMs": exchange_ts_ms,
        "latencyMs": latency_ms,
        "bid": best_bid,
        "ask": best_ask,
        "mid": (best_bid + best_ask) / 2,
        "spread": best_ask - best_bid,
    })


def extract_quotes(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    quotes: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        event = str(row.get("eventType") or row.get("event_type") or "")
        local_ms = iso_ms(row.get("localTs"))
        exch_ms = exchange_ms(row)
        if event == "best_bid_ask":
            add_quote(
                quotes,
                asset=str(row.get("assetId") or row.get("asset_id") or ""),
                local_ms=local_ms,
                exchange_ts_ms=exch_ms,
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
                    local_ms=local_ms,
                    exchange_ts_ms=exch_ms,
                    bid=change.get("best_bid") or change.get("bestBid"),
                    ask=change.get("best_ask") or change.get("bestAsk"),
                    market=row.get("market"),
                )
    for asset_rows in quotes.values():
        asset_rows.sort(key=lambda item: item["localMs"])
    return quotes


def future_quote(quotes: list[dict[str, Any]], start_index: int, horizon_ms: int) -> dict[str, Any] | None:
    target = quotes[start_index]["localMs"] + horizon_ms
    for row in quotes[start_index + 1:]:
        if row["localMs"] >= target:
            return row
    return None


def replay_window(
    quotes: dict[str, list[dict[str, Any]]],
    *,
    window_sec: int,
    lookback_sec: int,
    max_latency_ms: int,
    max_staleness_ms: int,
    min_abs_prior_move: float,
    max_start_spread: float,
) -> dict[str, Any]:
    samples = []
    horizon_ms = window_sec * 1000
    lookback_ms = lookback_sec * 1000
    for asset_rows in quotes.values():
        left = 0
        for idx, row in enumerate(asset_rows):
            while left < idx and asset_rows[left]["localMs"] < row["localMs"] - lookback_ms:
                left += 1
            if left >= idx or row["spread"] > max_start_spread:
                continue
            latency_ms = row.get("latencyMs")
            if latency_ms is None or latency_ms > max_latency_ms:
                continue
            staleness_ms = row["localMs"] - asset_rows[idx - 1]["localMs"] if idx > 0 else None
            if staleness_ms is None or staleness_ms > max_staleness_ms:
                continue
            prior = asset_rows[left]
            prior_move = row["mid"] - prior["mid"]
            if abs(prior_move) < min_abs_prior_move:
                continue
            direction = 1 if prior_move > 0 else -1
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
                "latencyMs": latency_ms,
                "stalenessMs": staleness_ms,
                "priorMove": round(prior_move, 6),
                "direction": "long-yes" if direction > 0 else "short-yes",
                "grossForwardMove": gross,
                "netAfterHalfSpread": net,
                "hit": gross > 0,
                "startSpread": row["spread"],
            })
    hits = sum(1 for item in samples if item["hit"])
    mean_net = sum(item["netAfterHalfSpread"] for item in samples) / len(samples) if samples else None
    mean_gross = sum(item["grossForwardMove"] for item in samples) / len(samples) if samples else None
    median_latency = None
    median_staleness = None
    if samples:
        latencies = sorted(item["latencyMs"] for item in samples)
        staleness = sorted(item["stalenessMs"] for item in samples)
        median_latency = latencies[len(latencies) // 2]
        median_staleness = staleness[len(staleness) // 2]
    return {
        "windowSec": window_sec,
        "samples": len(samples),
        "hitRate": round(hits / len(samples), 6) if samples else None,
        "meanGrossMove": round(mean_gross, 6) if mean_gross is not None else None,
        "meanNetAfterHalfSpread": round(mean_net, 6) if mean_net is not None else None,
        "medianLatencyMs": median_latency,
        "medianStalenessMs": median_staleness,
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
            max_latency_ms=args.max_latency_ms,
            max_staleness_ms=args.max_staleness_ms,
            min_abs_prior_move=args.min_abs_prior_move,
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
        "command": "prediction-clob-latency-staleness-replay",
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
            "maxLatencyMs": args.max_latency_ms,
            "maxStalenessMs": args.max_staleness_ms,
            "minAbsPriorMove": args.min_abs_prior_move,
            "maxStartSpread": args.max_start_spread,
            "minSamples": args.min_samples,
            "minHitRate": args.min_hit_rate,
            "minNetAfterHalfSpread": args.min_net,
        },
        "results": results,
        "watchResearchCount": len(watch),
        "decision": "watch-research-only-not-paper" if watch else "research-only-no-latency-staleness-edge",
        "nextAction": "Join to resolved labels and fee/fillability before paper review." if watch else "Do not rerun this exact latency/staleness fixed form without a new label/source/feature.",
    }


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Prediction CLOB Latency Staleness Replay - 2026-05-30",
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
            f"net `{item.get('meanNetAfterHalfSpread')}`, medianLatencyMs `{item.get('medianLatencyMs')}`, "
            f"medianStalenessMs `{item.get('medianStalenessMs')}`, verdict `{item.get('verdict')}`, blockers `{item.get('blockers')}`"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay fixed CLOB latency/staleness feature.")
    parser.add_argument("--input", default=str(DEFAULT_JSONL))
    parser.add_argument("--output", default=str(OUT))
    parser.add_argument("--markdown-output", default=str(OUT_MD))
    parser.add_argument("--windows", type=lambda value: [int(item) for item in value.split(",")], default=[15, 60])
    parser.add_argument("--lookback-sec", type=int, default=60)
    parser.add_argument("--max-latency-ms", type=int, default=10_000)
    parser.add_argument("--max-staleness-ms", type=int, default=30_000)
    parser.add_argument("--min-abs-prior-move", type=float, default=0.001)
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
