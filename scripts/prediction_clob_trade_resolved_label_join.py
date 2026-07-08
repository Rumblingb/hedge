#!/usr/bin/env python3
"""Join captured CLOB last-trade prints to resolved-outcome labels (exact-id).

Research-only, read-only. This is the branch the fixed-form replays and the
no-edge ledger repeatedly point at: test whether REAL executed trades, joined
to subject-specific resolved outcomes, carry post-spread edge.

The capture's `market` field is the Polymarket market id, so we join on the
EXACT historical closed-market id (not fuzzy subject tokens -- the promotion
gate warns against token matching). A trade observation counts only when its
market id is present in the resolved-outcome index.

On live captures this yields 0 labelled samples because the recorded markets
are still OPEN (audit gap: you cannot validate trade->resolution edge on
markets that have not resolved). The script reports that gap honestly rather
than fabricating labels.
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
DEFAULT_MANIFEST = ROOT / ".rumbling-hedge" / "research" / "prediction-market-analysis" / "manifest.json"
VAULT = Path.home() / "Documents/memorybrain"
OUT = STATE / "prediction-clob-trade-resolved-label-join.latest.json"
OUT_MD = VAULT / "Agent-Hermes" / f"prediction-clob-trade-resolved-label-join-{datetime.now(timezone.utc).date().isoformat()}.md"


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


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def build_resolved_index(manifest_path: Path, max_rows: int) -> dict[str, bool]:
    """market id -> resolved YES (True) / NO (False)."""
    manifest = read_json(manifest_path)
    tables = manifest.get("tables") if isinstance(manifest.get("tables"), dict) else {}
    files = (tables.get("polymarket_markets") or {}).get("sample") or []
    idx: dict[str, bool] = {}
    if not files:
        return idx
    try:
        import duckdb
    except Exception:
        return idx
    con = duckdb.connect()
    rows = con.execute(
        "select id, outcomes, outcome_prices from read_parquet(?) where closed = true limit ?",
        [files, max_rows],
    ).fetchall()
    for mid, outcomes, prices in rows:
        try:
            out_list = [str(x).strip().lower() for x in json.loads(outcomes) if isinstance(x, str)]
            price_list = [float(x) for x in json.loads(prices)]
        except Exception:
            continue
        if len(out_list) != 2 or len(price_list) != 2:
            continue
        if max(price_list) < 0.99:
            continue
        winner = int(price_list.index(max(price_list)))
        try:
            yes_idx = out_list.index("yes")
        except ValueError:
            continue
        idx[str(mid)] = winner == yes_idx
    return idx


def extract_quotes_and_trades(rows):
    quotes: dict[str, list[dict[str, Any]]] = defaultdict(list)
    trades: list[dict[str, Any]] = []
    for row in rows:
        event = str(row.get("eventType") or row.get("event_type") or "")
        ts_ms = iso_ms(row.get("localTs"))
        if event == "best_bid_ask":
            best_bid = to_float(row.get("bestBid") or row.get("best_bid"))
            best_ask = to_float(row.get("bestAsk") or row.get("best_ask"))
            asset = str(row.get("assetId") or row.get("asset_id") or "")
            if asset and ts_ms is not None and best_bid and best_ask and 0 < best_bid < 1 and 0 < best_ask < 1 and best_ask >= best_bid:
                quotes[asset].append({"tsMs": ts_ms, "mid": (best_bid + best_ask) / 2, "spread": best_ask - best_bid})
        elif event == "price_change":
            for change in row.get("priceChanges") or []:
                if not isinstance(change, dict):
                    continue
                best_bid = to_float(change.get("best_bid") or change.get("bestBid"))
                best_ask = to_float(change.get("best_ask") or change.get("bestAsk"))
                asset = str(change.get("asset_id") or change.get("assetId") or "")
                ts = iso_ms(row.get("localTs"))
                if asset and ts is not None and best_bid and best_ask and 0 < best_bid < 1 and 0 < best_ask < 1 and best_ask >= best_bid:
                    quotes[asset].append({"tsMs": ts, "mid": (best_bid + best_ask) / 2, "spread": best_ask - best_bid})
        elif event == "last_trade_price":
            asset = str(row.get("assetId") or row.get("asset_id") or "")
            price = to_float(row.get("price"))
            size = to_float(row.get("size"))
            side = str(row.get("side") or "").upper()
            mid = str(row.get("market") or "")
            if not asset or ts_ms is None or price is None or size is None or size <= 0 or side not in {"BUY", "SELL"} or not (0 < price < 1):
                continue
            trades.append({"marketId": mid, "assetId": asset, "tsMs": ts_ms, "price": price, "size": size, "side": side})
    for asset_rows in quotes.values():
        asset_rows.sort(key=lambda item: item["tsMs"])
    trades.sort(key=lambda item: item["tsMs"])
    return quotes, trades


def prior_quote(quotes, ts_ms, max_age_ms):
    best = None
    for idx, quote in enumerate(quotes):
        if quote["tsMs"] > ts_ms:
            break
        best = (idx, quote)
    if best is None:
        return None
    idx, quote = best
    if ts_ms - quote["tsMs"] > max_age_ms:
        return None
    return idx, quote


def future_quote(quotes, start_index, start_ts_ms, horizon_ms):
    target = start_ts_ms + horizon_ms
    for quote in quotes[start_index + 1:]:
        if quote["tsMs"] >= target:
            return quote
    return None


def replay_window(quotes, trades, resolved, *, window_sec, min_trade_size, max_quote_age_ms, max_start_spread):
    samples = []
    horizon_ms = window_sec * 1000
    recent_market_ids = set()
    for trade in trades:
        recent_market_ids.add(trade["marketId"])
        if trade["size"] < min_trade_size:
            continue
        asset_quotes = quotes.get(trade["assetId"], [])
        matched = prior_quote(asset_quotes, trade["tsMs"], max_quote_age_ms)
        if not matched:
            continue
        quote_idx, quote = matched
        if quote["spread"] > max_start_spread:
            continue
        label = resolved.get(trade["marketId"])
        if label is None:
            continue  # market not in resolved set (open / unmapped)
        future = future_quote(asset_quotes, quote_idx, trade["tsMs"], horizon_ms)
        if not future:
            continue
        direction = 1 if trade["side"] == "BUY" else -1
        gross = direction * (future["mid"] - trade["price"])
        net = gross - (quote["spread"] / 2)
        samples.append({
            "marketId": trade["marketId"][:16],
            "windowSec": window_sec,
            "side": trade["side"],
            "tradePrice": round(trade["price"], 6),
            "resolvedYes": label,
            "grossForwardMove": gross,
            "netAfterHalfSpread": net,
            "hit": (gross > 0) == label,
        })
    hits = sum(1 for item in samples if item["hit"])
    mean_net = sum(item["netAfterHalfSpread"] for item in samples) / len(samples) if samples else None
    mean_gross = sum(item["grossForwardMove"] for item in samples) / len(samples) if samples else None
    return {
        "windowSec": window_sec,
        "samples": len(samples),
        "hitRate": round(hits / len(samples), 6) if samples else None,
        "meanGrossMove": round(mean_gross, 6) if mean_gross is not None else None,
        "meanNetAfterHalfSpread": round(mean_net, 6) if mean_net is not None else None,
        "sampleRows": samples[:200],
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    rows = read_jsonl(Path(args.input))
    resolved = build_resolved_index(Path(args.manifest), args.max_rows)
    quotes, trades = extract_quotes_and_trades(rows)
    market_ids_seen = {t["marketId"] for t in trades}
    joined_open = sum(1 for mid in market_ids_seen if mid not in resolved)
    windows = [
        replay_window(
            quotes, trades, resolved, window_sec=window,
            min_trade_size=args.min_trade_size, max_quote_age_ms=args.max_quote_age_ms,
            max_start_spread=args.max_start_spread,
        )
        for window in args.windows
    ]
    results = []
    for item in windows:
        blockers = []
        if item["samples"] < args.min_samples:
            blockers.append("too-few-labelled-trade-samples")
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
        "command": "prediction-clob-trade-resolved-label-join",
        "generatedAt": now_iso(),
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "readyForPaper": False,
        "inputPath": str(Path(args.input).resolve()),
        "manifestPath": str(Path(args.manifest).resolve()),
        "recordsRead": len(rows),
        "resolvedMarketIds": len(resolved),
        "tradeMarketIdsSeen": len(market_ids_seen),
        "tradeMarketsStillOpenOrUnmapped": joined_open,
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
        "decision": "watch-research-only-not-paper" if watch else "research-only-no-labelled-trade-edge",
        "nextAction": "Capture trades on markets AFTER they resolve (or build a historical labelled-trade corpus with timestamps) to populate the join.",
    }


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Prediction CLOB Trade x Resolved-Label Join - " + str(payload.get("generatedAt", ""))[:10],
        "",
        "Parent hub: [[BILL-CONTROL-HUB]]",
        "",
        "Research-only. Real captured trades joined to exact resolved market ids.",
        "",
        "## Summary",
        "",
        f"- Decision: `{payload.get('decision')}`",
        f"- Records read: `{payload.get('recordsRead')}`",
        f"- Resolved market ids in index: `{payload.get('resolvedMarketIds')}`",
        f"- Trade market ids seen: `{payload.get('tradeMarketIdsSeen')}`",
        f"- Trade markets still OPEN / unmapped: `{payload.get('tradeMarketsStillOpenOrUnmapped')}`",
        f"- Watch research count: `{payload.get('watchResearchCount')}`",
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
    lines.append("Note: 0 labelled samples on live captures is the EXPECTED audit gap -- recorded markets are open and cannot carry a resolved label yet.")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Join captured CLOB trades to resolved-outcome labels.")
    parser.add_argument("--input", default=str(DEFAULT_JSONL))
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--output", default=str(OUT))
    parser.add_argument("--markdown-output", default=str(OUT_MD))
    parser.add_argument("--windows", type=lambda value: [int(x) for x in value.split(",")], default=[15, 60])
    parser.add_argument("--min-trade-size", type=float, default=10.0)
    parser.add_argument("--max-quote-age-ms", type=int, default=30_000)
    parser.add_argument("--max-start-spread", type=float, default=0.05)
    parser.add_argument("--min-samples", type=int, default=30)
    parser.add_argument("--min-hit-rate", type=float, default=0.55)
    parser.add_argument("--min-net", type=float, default=0.0025)
    parser.add_argument("--max-rows", type=int, default=250_000)
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
