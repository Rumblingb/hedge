#!/usr/bin/env python3
"""Replay mapped news events against CLOB quote movement without lookahead.

Research-only. This measures whether strict event/market mappings have
observable post-event repricing in captured CLOB data. It does not infer a
trade direction and cannot approve paper, demo, live, funding, or sizing.
"""

from __future__ import annotations

import argparse
import glob
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
CLOB_DIR = ROOT / ".rumbling-hedge" / "prediction" / "clob"
MAPPING_PLAN = STATE / "prediction-event-market-mapping-plan.latest.json"
OUT = STATE / "prediction-event-lag-replay.latest.json"
VAULT = Path.home() / "Documents/memorybrain"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def current_utc_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def default_markdown_path() -> Path:
    return VAULT / "Agent-Hermes" / f"prediction-event-lag-replay-{current_utc_date()}.md"


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except Exception:
                continue
            if isinstance(item, dict):
                rows.append(item)
    except FileNotFoundError:
        return []
    return rows


def to_float(value: Any) -> float | None:
    try:
        out = float(value)
        return out if math.isfinite(out) else None
    except Exception:
        return None


def parse_time_ms(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        numeric = float(value)
        if not math.isfinite(numeric):
            return None
        return int(numeric if numeric > 10_000_000_000 else numeric * 1000)
    text = str(value).strip()
    if not text:
        return None
    numeric = to_float(text)
    if numeric is not None:
        return int(numeric if numeric > 10_000_000_000 else numeric * 1000)
    try:
        return int(datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp() * 1000)
    except Exception:
        return None


def parse_record_ts_ms(record: dict[str, Any]) -> int | None:
    for key in ("localTs", "timestamp", "ts", "exchangeTs"):
        ts_ms = parse_time_ms(record.get(key))
        if ts_ms is not None:
            return ts_ms
    return None


def level_price_size(level: Any) -> tuple[float, float] | None:
    if not isinstance(level, dict):
        return None
    price = to_float(level.get("price"))
    size = to_float(level.get("size"))
    if price is None or size is None or not (0 <= price <= 1) or size <= 0:
        return None
    return price, size


def best_level(levels: Any, *, reverse: bool) -> tuple[float, float] | None:
    if not isinstance(levels, list):
        return None
    parsed = [item for item in (level_price_size(level) for level in levels) if item]
    if not parsed:
        return None
    parsed.sort(key=lambda item: item[0], reverse=reverse)
    return parsed[0]


def quote_from_record(record: dict[str, Any]) -> list[dict[str, Any]]:
    event = str(record.get("eventType") or record.get("event_type") or "")
    ts_ms = parse_record_ts_ms(record)
    if ts_ms is None:
        return []
    quotes: list[dict[str, Any]] = []
    if event == "book":
        asset = str(record.get("assetId") or record.get("asset_id") or "")
        bid = best_level(record.get("bids"), reverse=True)
        ask = best_level(record.get("asks"), reverse=False)
        if asset and bid and ask and ask[0] >= bid[0]:
            quotes.append({
                "assetId": asset,
                "tsMs": ts_ms,
                "mid": (bid[0] + ask[0]) / 2,
                "spread": ask[0] - bid[0],
                "eventType": event,
            })
        return quotes
    if event == "best_bid_ask":
        asset = str(record.get("assetId") or record.get("asset_id") or "")
        bid = to_float(record.get("bestBid") or record.get("best_bid"))
        ask = to_float(record.get("bestAsk") or record.get("best_ask"))
        if asset and bid is not None and ask is not None and ask >= bid:
            quotes.append({"assetId": asset, "tsMs": ts_ms, "mid": (bid + ask) / 2, "spread": ask - bid, "eventType": event})
        return quotes
    if event == "price_change":
        for change in record.get("priceChanges") or []:
            if not isinstance(change, dict):
                continue
            asset = str(change.get("asset_id") or change.get("assetId") or "")
            bid = to_float(change.get("best_bid") or change.get("bestBid"))
            ask = to_float(change.get("best_ask") or change.get("bestAsk"))
            if asset and bid is not None and ask is not None and ask >= bid:
                quotes.append({"assetId": asset, "tsMs": ts_ms, "mid": (bid + ask) / 2, "spread": ask - bid, "eventType": event})
    return quotes


def load_quotes(paths: list[Path]) -> dict[str, list[dict[str, Any]]]:
    quotes: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for path in paths:
        for record in read_jsonl(path):
            for quote in quote_from_record(record):
                quotes[quote["assetId"]].append(quote)
    for asset_quotes in quotes.values():
        asset_quotes.sort(key=lambda item: item["tsMs"])
    return quotes


def quote_before(quotes: list[dict[str, Any]], event_ts_ms: int, max_age_ms: int) -> dict[str, Any] | None:
    best = None
    for quote in quotes:
        if quote["tsMs"] > event_ts_ms:
            break
        if event_ts_ms - quote["tsMs"] <= max_age_ms:
            best = quote
    return best


def quote_at_or_after(quotes: list[dict[str, Any]], target_ts_ms: int, max_ts_ms: int) -> dict[str, Any] | None:
    for quote in quotes:
        if quote["tsMs"] < target_ts_ms:
            continue
        if quote["tsMs"] <= max_ts_ms:
            return quote
        return None
    return None


def repricing_check(abs_move: float, half_spread: float, min_abs_move: float, *, eps: float = 1e-9) -> dict[str, Any]:
    clears_min_abs_move = abs_move + eps >= min_abs_move
    clears_half_spread = abs_move > half_spread + eps
    return {
        "clearsMinAbsMove": clears_min_abs_move,
        "clearsHalfSpread": clears_half_spread,
        "repriced": clears_min_abs_move and clears_half_spread,
        "epsilon": eps,
    }


def candidate_rows(mapping_plan: dict[str, Any]) -> list[dict[str, Any]]:
    rows = mapping_plan.get("candidates") if isinstance(mapping_plan.get("candidates"), list) else []
    return [row for row in rows if isinstance(row, dict)]


def replay_candidate(
    candidate: dict[str, Any],
    quotes_by_asset: dict[str, list[dict[str, Any]]],
    *,
    pre_minutes: int,
    horizons_minutes: list[int],
    min_abs_move: float,
) -> tuple[list[dict[str, Any]], list[str]]:
    asset = str(candidate.get("clobTokenId") or "")
    event_ts_ms = parse_time_ms(candidate.get("articleDatetime") or candidate.get("published"))
    if not asset:
        return [], ["missing-clob-token"]
    if event_ts_ms is None:
        return [], ["invalid-event-timestamp"]
    asset_quotes = quotes_by_asset.get(asset, [])
    if not asset_quotes:
        return [], ["no-quotes-for-clob-token"]
    pre = quote_before(asset_quotes, event_ts_ms, pre_minutes * 60 * 1000)
    if not pre:
        return [], ["no-pre-event-quote-within-window"]
    rows: list[dict[str, Any]] = []
    missing_reasons: list[str] = []
    for horizon in horizons_minutes:
        target = event_ts_ms + horizon * 60 * 1000
        post = quote_at_or_after(asset_quotes, target, target + 60 * 1000)
        if not post:
            missing_reasons.append(f"no-post-event-quote-{horizon}m")
            continue
        move = post["mid"] - pre["mid"]
        abs_move = abs(move)
        half_spread = pre["spread"] / 2
        check = repricing_check(abs_move, half_spread, min_abs_move)
        rows.append({
            "externalId": candidate.get("externalId"),
            "clobTokenId": asset,
            "headline": candidate.get("headline"),
            "question": candidate.get("question"),
            "source": candidate.get("source"),
            "eventTsMs": event_ts_ms,
            "preQuoteTsMs": pre["tsMs"],
            "postQuoteTsMs": post["tsMs"],
            "preAgeSec": round((event_ts_ms - pre["tsMs"]) / 1000, 3),
            "postDelaySec": round((post["tsMs"] - event_ts_ms) / 1000, 3),
            "horizonMinutes": horizon,
            "preMid": round(pre["mid"], 6),
            "postMid": round(post["mid"], 6),
            "midMove": round(move, 6),
            "absMidMove": round(abs_move, 6),
            "preSpread": round(pre["spread"], 6),
            "halfSpread": round(half_spread, 6),
            "minAbsMove": round(min_abs_move, 6),
            "absMoveAfterHalfSpread": round(abs_move - half_spread, 6),
            "clearsMinAbsMove": check["clearsMinAbsMove"],
            "clearsHalfSpread": check["clearsHalfSpread"],
            "repricingEpsilon": check["epsilon"],
            "repriced": check["repriced"],
            "researchOnly": True,
            "writesOrders": False,
            "touchesBroker": False,
        })
    return rows, missing_reasons


def build_replay(
    *,
    mapping_plan: dict[str, Any],
    clob_paths: list[Path],
    pre_minutes: int = 30,
    horizons_minutes: list[int] | None = None,
    min_events: int = 3,
    min_abs_move: float = 0.01,
) -> dict[str, Any]:
    horizons_minutes = horizons_minutes or [15, 30, 60, 120]
    candidates = candidate_rows(mapping_plan)
    quotes_by_asset = load_quotes(clob_paths)
    windows: list[dict[str, Any]] = []
    missing = Counter()
    for candidate in candidates:
        rows, reasons = replay_candidate(
            candidate,
            quotes_by_asset,
            pre_minutes=pre_minutes,
            horizons_minutes=horizons_minutes,
            min_abs_move=min_abs_move,
        )
        windows.extend(rows)
        missing.update(reasons)
    complete_events = {str(item.get("externalId")) for item in windows if item.get("externalId")}
    repriced = [item for item in windows if item.get("repriced")]
    by_horizon: dict[str, dict[str, Any]] = {}
    for horizon in horizons_minutes:
        rows = [item for item in windows if item.get("horizonMinutes") == horizon]
        by_horizon[str(horizon)] = {
            "windows": len(rows),
            "repricedCount": sum(1 for item in rows if item.get("repriced")),
            "medianAbsMove": median([float(item["absMidMove"]) for item in rows]),
            "medianAbsMoveAfterHalfSpread": median([float(item["absMoveAfterHalfSpread"]) for item in rows]),
        }
    blockers: list[str] = []
    if len(complete_events) < min_events:
        blockers.append("too-few-complete-event-windows")
    if not repriced:
        blockers.append("no-post-event-repricing-after-half-spread")
    return {
        "command": "prediction-event-lag-replay",
        "generatedAt": now_iso(),
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "readyForPaper": False,
        "readyForExecution": False,
        "mappingDecision": mapping_plan.get("decision"),
        "candidateCount": len(candidates),
        "clobPaths": [str(path) for path in clob_paths],
        "assetQuoteCount": sum(len(rows) for rows in quotes_by_asset.values()),
        "assetsWithQuotes": len(quotes_by_asset),
        "preMinutes": pre_minutes,
        "horizonsMinutes": horizons_minutes,
        "minimumCompleteEvents": min_events,
        "minimumAbsMove": min_abs_move,
        "completeEventCount": len(complete_events),
        "completeWindowCount": len(windows),
        "repricedWindowCount": len(repriced),
        "byHorizon": by_horizon,
        "missingReasonCounts": dict(missing),
        "sampleWindows": windows[:100],
        "blockers": blockers,
        "decision": "research-only-event-lag-replay-watch" if not blockers else "research-only-event-lag-replay-blocked",
        "nextAction": (
            "Review mapped events manually, add more event-window CLOB capture, then run resolved-label expectancy."
            if not blockers
            else "Collect more pre/post event CLOB windows before any event-lag expectancy estimate."
        ),
        "hardRules": [
            "No lookahead: pre quote must be before the event timestamp; post quote must be after it.",
            "This measures repricing only, not trade direction.",
            "No paper, funding, demo, live, sizing, or broker route is approved by this artifact.",
        ],
    }


def median(values: list[float]) -> float | None:
    if not values:
        return None
    values = sorted(values)
    mid = len(values) // 2
    if len(values) % 2:
        return round(values[mid], 6)
    return round((values[mid - 1] + values[mid]) / 2, 6)


def render_markdown(payload: dict[str, Any]) -> str:
    generated_date = str(payload.get("generatedAt") or current_utc_date())[:10]
    lines = [
        f"# Prediction Event Lag Replay - {generated_date}",
        "",
        "Parent hub: [[BILL-CONTROL-HUB]]",
        "",
        "Research-only no-lookahead replay of mapped news events against CLOB repricing.",
        "",
        "## Summary",
        "",
        f"- Decision: `{payload.get('decision')}`",
        f"- Complete events: `{payload.get('completeEventCount')}`",
        f"- Complete windows: `{payload.get('completeWindowCount')}`",
        f"- Repriced windows: `{payload.get('repricedWindowCount')}`",
        f"- Blockers: `{payload.get('blockers')}`",
        "",
        "## Horizons",
        "",
    ]
    for horizon, stats in (payload.get("byHorizon") or {}).items():
        lines.append(f"- `{horizon}m`: `{stats}`")
    lines.extend(["", "## Hard Rules", ""])
    for rule in payload.get("hardRules") or []:
        lines.append(f"- {rule}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay prediction event lag without lookahead.")
    parser.add_argument("--mapping-plan", default=str(MAPPING_PLAN))
    parser.add_argument("--clob-glob", default=str(CLOB_DIR / "*-market-channel.jsonl"))
    parser.add_argument("--pre-minutes", type=int, default=30)
    parser.add_argument("--horizons-minutes", default="15,30,60,120")
    parser.add_argument("--min-events", type=int, default=3)
    parser.add_argument("--min-abs-move", type=float, default=0.01)
    parser.add_argument("--output", default=str(OUT))
    parser.add_argument("--markdown-output", default=str(default_markdown_path()))
    args = parser.parse_args()

    horizons = [int(part.strip()) for part in args.horizons_minutes.split(",") if part.strip()]
    payload = build_replay(
        mapping_plan=read_json(Path(args.mapping_plan)),
        clob_paths=[Path(path) for path in sorted(glob.glob(args.clob_glob))],
        pre_minutes=args.pre_minutes,
        horizons_minutes=horizons,
        min_events=args.min_events,
        min_abs_move=args.min_abs_move,
    )
    out = Path(args.output)
    md = Path(args.markdown_output)
    out.parent.mkdir(parents=True, exist_ok=True)
    md.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    md.write_text(render_markdown(payload))
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
