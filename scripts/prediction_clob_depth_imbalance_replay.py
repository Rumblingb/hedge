#!/usr/bin/env python3
"""Replay a fixed CLOB depth-imbalance feature against forward mid moves.

Research-only. This changes one variable from the rejected CLOB drift baseline:
use book depth imbalance instead of raw quote persistence. Thresholds are fixed
up front; the script does not mine parameters or approve paper/live routing.
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
OUT = STATE / "prediction-clob-depth-imbalance-replay.latest.json"
VAULT = Path.home() / "Documents/memorybrain"
OUT_MD = VAULT / "Agent-Hermes" / "prediction-clob-depth-imbalance-replay-2026-05-30.md"


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


def top_level(levels: Any, reverse: bool) -> tuple[float, float] | None:
    if not isinstance(levels, list):
        return None
    parsed = []
    for level in levels:
        if not isinstance(level, dict):
            continue
        price = to_float(level.get("price"))
        size = to_float(level.get("size"))
        if price is None or size is None or not (0 < price < 1) or size <= 0:
            continue
        parsed.append((price, size))
    if not parsed:
        return None
    parsed.sort(key=lambda item: item[0], reverse=reverse)
    return parsed[0]


def extract_quotes_and_books(rows: list[dict[str, Any]]) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    quotes: dict[str, list[dict[str, Any]]] = defaultdict(list)
    books: list[dict[str, Any]] = []
    for row in rows:
        event = str(row.get("eventType") or row.get("event_type") or "")
        ts_ms = parse_ts_ms(row)
        if ts_ms is None:
            continue
        if event == "book":
            asset = str(row.get("assetId") or row.get("asset_id") or "")
            bid = top_level(row.get("bids"), reverse=True)
            ask = top_level(row.get("asks"), reverse=False)
            if not asset or not bid or not ask or ask[0] < bid[0]:
                continue
            mid = (bid[0] + ask[0]) / 2
            spread = ask[0] - bid[0]
            imbalance = (bid[1] - ask[1]) / (bid[1] + ask[1])
            quote = {
                "assetId": asset,
                "market": row.get("market"),
                "tsMs": ts_ms,
                "mid": mid,
                "spread": spread,
                "bidSize": bid[1],
                "askSize": ask[1],
                "imbalance": imbalance,
            }
            quotes[asset].append(quote)
            books.append(quote)
            continue
        if event == "best_bid_ask":
            asset = str(row.get("assetId") or row.get("asset_id") or "")
            bid = to_float(row.get("bestBid") or row.get("best_bid"))
            ask = to_float(row.get("bestAsk") or row.get("best_ask"))
            if asset and bid is not None and ask is not None and ask >= bid:
                quotes[asset].append({"assetId": asset, "market": row.get("market"), "tsMs": ts_ms, "mid": (bid + ask) / 2, "spread": ask - bid})
            continue
        if event == "price_change":
            for change in row.get("priceChanges") or []:
                if not isinstance(change, dict):
                    continue
                asset = str(change.get("asset_id") or change.get("assetId") or "")
                bid = to_float(change.get("best_bid") or change.get("bestBid"))
                ask = to_float(change.get("best_ask") or change.get("bestAsk"))
                if asset and bid is not None and ask is not None and ask >= bid:
                    quotes[asset].append({"assetId": asset, "market": row.get("market"), "tsMs": ts_ms, "mid": (bid + ask) / 2, "spread": ask - bid})
    for asset_rows in quotes.values():
        asset_rows.sort(key=lambda item: item["tsMs"])
    books.sort(key=lambda item: item["tsMs"])
    return quotes, books


def future_quote(quotes: list[dict[str, Any]], ts_ms: int, horizon_ms: int) -> dict[str, Any] | None:
    target = ts_ms + horizon_ms
    for quote in quotes:
        if quote["tsMs"] >= target:
            return quote
    return None


def replay_window(
    quotes: dict[str, list[dict[str, Any]]],
    books: list[dict[str, Any]],
    *,
    window_sec: int,
    imbalance_threshold: float,
    max_start_spread: float,
) -> dict[str, Any]:
    samples = []
    horizon_ms = window_sec * 1000
    for book in books:
        if book["spread"] > max_start_spread:
            continue
        imbalance = book["imbalance"]
        if abs(imbalance) < imbalance_threshold:
            continue
        direction = 1 if imbalance > 0 else -1
        future = future_quote(quotes.get(book["assetId"], []), book["tsMs"], horizon_ms)
        if not future:
            continue
        gross = direction * (future["mid"] - book["mid"])
        net = gross - (book["spread"] / 2)
        samples.append({
            "assetId": book["assetId"],
            "market": book.get("market"),
            "windowSec": window_sec,
            "imbalance": round(imbalance, 6),
            "direction": "long-yes" if direction > 0 else "short-yes",
            "grossForwardMove": gross,
            "netAfterHalfSpread": net,
            "hit": gross > 0,
            "startSpread": book["spread"],
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
    quotes, books = extract_quotes_and_books(rows)
    windows = [
        replay_window(
            quotes,
            books,
            window_sec=window,
            imbalance_threshold=args.imbalance_threshold,
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
        "command": "prediction-clob-depth-imbalance-replay",
        "generatedAt": now_iso(),
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "readyForPaper": False,
        "inputPath": str(Path(args.input).resolve()),
        "recordsRead": len(rows),
        "assetsWithQuotes": len(quotes),
        "bookFeatureRows": len(books),
        "fixedThresholds": {
            "imbalanceThreshold": args.imbalance_threshold,
            "maxStartSpread": args.max_start_spread,
            "minSamples": args.min_samples,
            "minHitRate": args.min_hit_rate,
            "minNetAfterHalfSpread": args.min_net,
        },
        "results": results,
        "watchResearchCount": len(watch),
        "decision": "watch-research-only-not-paper" if watch else "research-only-no-depth-imbalance-edge",
        "nextAction": "Join to resolved labels and fee/fillability before paper review." if watch else "Do not rerun this exact depth-imbalance fixed form without a new label/source/feature.",
    }


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Prediction CLOB Depth Imbalance Replay - 2026-05-30",
        "",
        "Parent hub: [[BILL-CONTROL-HUB]]",
        "",
        "Research-only one-variable replay. This page does not approve paper or live trading.",
        "",
        "## Summary",
        "",
        f"- Decision: `{payload.get('decision')}`",
        f"- Records read: `{payload.get('recordsRead')}`",
        f"- Book feature rows: `{payload.get('bookFeatureRows')}`",
        f"- Watch research count: `{payload.get('watchResearchCount')}`",
        f"- Fixed thresholds: `{payload.get('fixedThresholds')}`",
        "",
        "## Windows",
        "",
    ]
    for item in payload.get("results") or []:
        lines.extend([
            f"- `{item.get('windowSec')}s`: samples `{item.get('samples')}`, hit `{item.get('hitRate')}`, net `{item.get('meanNetAfterHalfSpread')}`, verdict `{item.get('verdict')}`, blockers `{item.get('blockers')}`",
        ])
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay fixed CLOB depth imbalance feature.")
    parser.add_argument("--input", default=str(DEFAULT_JSONL))
    parser.add_argument("--output", default=str(OUT))
    parser.add_argument("--markdown-output", default=str(OUT_MD))
    parser.add_argument("--windows", type=lambda value: [int(part) for part in value.split(",") if part], default=[15, 60])
    parser.add_argument("--imbalance-threshold", type=float, default=0.2)
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
