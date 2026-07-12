#!/usr/bin/env python3
"""Build capture-anchored replay targets from already-captured CLOB quotes.

Research-only. The news->market mapping pipeline is currently blocked: today's
RSS events are too recent to have been forward-captured, and the historical
market stream shares ZERO assetIds with the live capture, so captured quotes
cannot be joined to question text. Pointing the replay grid at those unmapped
tokens yields no-quotes-for-clob-token for every scenario.

This generator instead derives replay candidates directly from the capture: for
each asset that has quotes on BOTH sides of an intra-capture anchor (>= preMinutes
before and >= postMinutes after), it selects the first such quote as the event
anchor. Because the anchor is a real captured quote timestamp and every measured
post quote lies strictly after it, the replay is strictly no-lookahead.

These are MICROSTRUCTURE-LAG BASELINES, not news-event lag. They carry
question: null and mappingStatus: capture-anchored-microstructure-baseline
so downstream consumers never mistake them for news-driven repricing. They make
the lag grid mechanically runnable and quantify how much intraday CLOB drift
occurs over 30m/60m/120m windows, which is the honest floor the current data
supports.

No labels, no keys, no orders, no broker state are touched.
"""

from __future__ import annotations

import argparse
import glob
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
CLOB_DIR = ROOT / ".rumbling-hedge" / "prediction" / "clob"
DEFAULT_EXTERNAL_CLOB_DIR = Path(
    "/Volumes/Seagate Expansion Drive/hedge-data/prediction-clob-capture"
)
OUT = STATE / "prediction-event-capture-anchored-targets.latest.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_time_ms(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        numeric = float(value)
        if not numeric or numeric <= 0:
            return None
        return int(numeric if numeric > 10_000_000_000 else numeric * 1000)
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp() * 1000)
    except Exception:
        return None


def clob_paths() -> list:
    patterns = [str(CLOB_DIR / "*-market-channel.jsonl")]
    if DEFAULT_EXTERNAL_CLOB_DIR.is_dir():
        patterns.append(str(DEFAULT_EXTERNAL_CLOB_DIR / "*-market-channel.jsonl"))
    paths = {}
    for pattern in patterns:
        for path in glob.glob(pattern):
            paths[str(Path(path).expanduser())] = Path(path).expanduser()
    return sorted(paths.values(), key=lambda p: str(p))


def load_quotes(paths: list) -> dict:
    ts_by_asset = defaultdict(list)
    for path in paths:
        try:
            text = path.read_text()
        except FileNotFoundError:
            continue
        for line in text.splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if rec.get("eventType") == "new_market":
                continue
            aid = rec.get("assetId") or rec.get("asset_id")
            ts = parse_time_ms(rec.get("localTs") or rec.get("timestamp") or rec.get("ts"))
            if aid and ts:
                ts_by_asset[str(aid)].append(ts)
    for asset in ts_by_asset:
        ts_by_asset[asset] = sorted(set(t for t in ts_by_asset[asset] if t))
    return ts_by_asset


def build_targets(ts_by_asset: dict, *, pre_minutes: int, post_minutes: int, min_quotes: int = 5) -> list:
    pre_ms = pre_minutes * 60 * 1000
    post_ms = post_minutes * 60 * 1000
    candidates = []
    for asset, quotes in ts_by_asset.items():
        if len(quotes) < min_quotes:
            continue
        anchor = None
        for ts in quotes:
            has_pre = any(ts - pre_ms <= x <= ts for x in quotes)
            has_post = any(x >= ts + post_ms for x in quotes)
            if has_pre and has_post:
                anchor = ts
                break
        if anchor is None:
            continue
        candidates.append(
            {
                "clobTokenId": asset,
                "externalId": None,
                "headline": None,
                "question": None,
                "source": None,
                "articleDatetime": datetime.fromtimestamp(anchor / 1000, tz=timezone.utc).isoformat(),
                "mappingStatus": "capture-anchored-microstructure-baseline",
                "dataSource": "clob-capture",
                "questionAvailable": False,
                "preMinutes": pre_minutes,
                "postMinutes": post_minutes,
                "anchorQuoteCount": len(quotes),
                "quoteSpanMs": quotes[-1] - quotes[0],
                "specificityFlags": ["not-news-anchored", "microstructure-lag-baseline"],
                "exclusionReasons": [],
            }
        )
    candidates.sort(key=lambda item: item["clobTokenId"])
    return candidates


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pre-minutes", type=int, default=30)
    parser.add_argument("--post-minutes", type=int, default=120)
    parser.add_argument("--min-quotes", type=int, default=5)
    args = parser.parse_args()

    quotes = load_quotes(clob_paths())
    candidates = build_targets(
        quotes,
        pre_minutes=args.pre_minutes,
        post_minutes=args.post_minutes,
        min_quotes=args.min_quotes,
    )
    total_assets = len(quotes)
    payload = {
        "command": "prediction-event-capture-anchored-replay-targets",
        "generatedAt": now_iso(),
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "preMinutes": args.pre_minutes,
        "postMinutes": args.post_minutes,
        "minQuotes": args.min_quotes,
        "totalCapturedAssets": total_assets,
        "candidateCount": len(candidates),
        "candidates": candidates,
        "note": (
            "Microstructure-lag baseline targets derived from captured CLOB quotes. "
            "Anchors are real intra-capture quote timestamps with pre/post coverage; "
            "no news labels are available for the captured assets. These are NOT "
            "news-event lag measurements."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(
        {k: v for k, v in payload.items() if k != "candidates"},
        indent=2,
        sort_keys=True,
    ))
    print("candidateCount=%d totalCapturedAssets=%d" % (len(candidates), total_assets))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
