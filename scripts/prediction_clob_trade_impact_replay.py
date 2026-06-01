#!/usr/bin/env python3
"""Replay a fixed CLOB last-trade impact feature.

Research-only. This changes one variable from the rejected CLOB drift baseline:
use real last-trade events as the signal, then test whether the trade side
predicts future mid-price movement after half-spread cost. Thresholds are fixed
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
OUT = STATE / "prediction-clob-trade-impact-replay.latest.json"
VAULT = Path.home() / "Documents/memorybrain"
OUT_MD = VAULT / "Agent-Hermes" / "prediction-clob-trade-impact-replay-2026-05-30.md"


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
    ts_ms: int | None,
    bid: Any,
    ask: Any,
    market: Any = None,
) -> None:
    best_bid = to_float(bid)
    best_ask = to_float(ask)
    if not asset or ts_ms is None or best_bid is None or best_ask is None:
        return
    if not (0 < best_bid < 1 and 0 < best_ask < 1 and best_ask >= best_bid):
        return
    quotes[asset].append({
        "assetId": asset,
        "market": market,
        "tsMs": ts_ms,
        "mid": (best_bid + best_ask) / 2,
        "spread": best_ask - best_bid,
    })


def add_trade(trades: list[dict[str, Any]], row: dict[str, Any]) -> None:
    asset = str(row.get("assetId") or row.get("asset_id") or "")
    ts_ms = iso_ms(row.get("localTs"))
    price = to_float(row.get("price"))
    size = to_float(row.get("size"))
    side = str(row.get("side") or "").upper()
    if not asset or ts_ms is None or price is None or size is None or size <= 0:
        return
    if side not in {"BUY", "SELL"}:
        return
    if not (0 < price < 1):
        return
    trades.append({
        "assetId": asset,
        "market": row.get("market"),
        "tsMs": ts_ms,
        "price": price,
        "size": size,
        "side": side,
    })


def extract_quotes_and_trades(rows: list[dict[str, Any]]) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    quotes: dict[str, list[dict[str, Any]]] = defaultdict(list)
    trades: list[dict[str, Any]] = []
    for row in rows:
        event = str(row.get("eventType") or row.get("event_type") or "")
        ts_ms = iso_ms(row.get("localTs"))
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
        elif event == "last_trade_price":
            add_trade(trades, row)
    for asset_rows in quotes.values():
        asset_rows.sort(key=lambda item: item["tsMs"])
    trades.sort(key=lambda item: item["tsMs"])
    return quotes, trades


def prior_quote(quotes: list[dict[str, Any]], ts_ms: int, max_age_ms: int) -> tuple[int, dict[str, Any]] | None:
    best_idx = None
    best = None
    for idx, quote in enumerate(quotes):
        if quote["tsMs"] > ts_ms:
            break
        best_idx = idx
        best = quote
    if best_idx is None or best is None:
        return None
    if ts_ms - best["tsMs"] > max_age_ms:
        return None
    return best_idx, best


def future_quote(quotes: list[dict[str, Any]], start_index: int, start_ts_ms: int, horizon_ms: int) -> dict[str, Any] | None:
    target = start_ts_ms + horizon_ms
    for quote in quotes[start_index + 1:]:
        if quote["tsMs"] >= target:
            return quote
    return None


def replay_window(
    quotes: dict[str, list[dict[str, Any]]],
    trades: list[dict[str, Any]],
    *,
    window_sec: int,
    min_trade_size: float,
    max_quote_age_ms: int,
    max_start_spread: float,
) -> dict[str, Any]:
    samples = []
    horizon_ms = window_sec * 1000
    for trade in trades:
        if trade["size"] < min_trade_size:
            continue
        asset_quotes = quotes.get(trade["assetId"], [])
        matched = prior_quote(asset_quotes, trade["tsMs"], max_quote_age_ms)
        if not matched:
            continue
        quote_idx, quote = matched
        if quote["spread"] > max_start_spread:
            continue
        future = future_quote(asset_quotes, quote_idx, trade["tsMs"], horizon_ms)
        if not future:
            continue
        direction = 1 if trade["side"] == "BUY" else -1
        gross = direction * (future["mid"] - trade["price"])
        net = gross - (quote["spread"] / 2)
        samples.append({
            "assetId": trade["assetId"],
            "market": trade.get("market"),
            "windowSec": window_sec,
            "side": trade["side"],
            "tradePrice": round(trade["price"], 6),
            "tradeSize": round(trade["size"], 6),
            "startMid": round(quote["mid"], 6),
            "startSpread": round(quote["spread"], 6),
            "quoteAgeMs": trade["tsMs"] - quote["tsMs"],
            "grossForwardMove": gross,
            "netAfterHalfSpread": net,
            "hit": gross > 0,
        })
    hits = sum(1 for item in samples if item["hit"])
    mean_net = sum(item["netAfterHalfSpread"] for item in samples) / len(samples) if samples else None
    mean_gross = sum(item["grossForwardMove"] for item in samples) / len(samples) if samples else None
    median_quote_age = None
    if samples:
        ages = sorted(item["quoteAgeMs"] for item in samples)
        median_quote_age = ages[len(ages) // 2]
    return {
        "windowSec": window_sec,
        "samples": len(samples),
        "hitRate": round(hits / len(samples), 6) if samples else None,
        "meanGrossMove": round(mean_gross, 6) if mean_gross is not None else None,
        "meanNetAfterHalfSpread": round(mean_net, 6) if mean_net is not None else None,
        "medianQuoteAgeMs": median_quote_age,
        "sampleRows": samples[:200],
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    rows = read_jsonl(Path(args.input))
    quotes, trades = extract_quotes_and_trades(rows)
    windows = [
        replay_window(
            quotes,
            trades,
            window_sec=window,
            min_trade_size=args.min_trade_size,
            max_quote_age_ms=args.max_quote_age_ms,
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
        "command": "prediction-clob-trade-impact-replay",
        "generatedAt": now_iso(),
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "readyForPaper": False,
        "inputPath": str(Path(args.input).resolve()),
        "recordsRead": len(rows),
        "assetsWithQuotes": len(quotes),
        "quoteFeatureRows": sum(len(items) for items in quotes.values()),
        "tradeFeatureRows": len(trades),
        "fixedThresholds": {
            "minTradeSize": args.min_trade_size,
            "maxQuoteAgeMs": args.max_quote_age_ms,
            "maxStartSpread": args.max_start_spread,
            "minSamples": args.min_samples,
            "minHitRate": args.min_hit_rate,
            "minNetAfterHalfSpread": args.min_net,
        },
        "results": results,
        "watchResearchCount": len(watch),
        "decision": "watch-research-only-not-paper" if watch else "research-only-no-trade-impact-edge",
        "nextAction": "Join to resolved labels and fee/fillability before paper review." if watch else "Do not rerun this exact trade-impact fixed form without a new label/source/feature.",
    }


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Prediction CLOB Trade Impact Replay - 2026-05-30",
        "",
        "Parent hub: [[BILL-CONTROL-HUB]]",
        "",
        "Research-only one-variable replay. This page does not approve paper or live trading.",
        "",
        "## Summary",
        "",
        f"- Decision: `{payload.get('decision')}`",
        f"- Records read: `{payload.get('recordsRead')}`",
        f"- Trade feature rows: `{payload.get('tradeFeatureRows')}`",
        f"- Watch research count: `{payload.get('watchResearchCount')}`",
        f"- Fixed thresholds: `{payload.get('fixedThresholds')}`",
        "",
        "## Windows",
        "",
    ]
    for item in payload.get("results") or []:
        lines.append(
            f"- `{item.get('windowSec')}s`: samples `{item.get('samples')}`, hit `{item.get('hitRate')}`, "
            f"net `{item.get('meanNetAfterHalfSpread')}`, medianQuoteAgeMs `{item.get('medianQuoteAgeMs')}`, "
            f"verdict `{item.get('verdict')}`, blockers `{item.get('blockers')}`"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay fixed CLOB last-trade impact feature.")
    parser.add_argument("--input", default=str(DEFAULT_JSONL))
    parser.add_argument("--output", default=str(OUT))
    parser.add_argument("--markdown-output", default=str(OUT_MD))
    parser.add_argument("--windows", type=lambda value: [int(item) for item in value.split(",")], default=[15, 60])
    parser.add_argument("--min-trade-size", type=float, default=10.0)
    parser.add_argument("--max-quote-age-ms", type=int, default=30_000)
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
