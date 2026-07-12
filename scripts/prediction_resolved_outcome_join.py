#!/usr/bin/env python3
"""Join prediction watchlist items to historical resolved market families.

This is a research-only gate. It uses local historical prediction-market
parquet slices to ask whether a live/watch candidate has comparable resolved
markets. It does not write orders, fills, approvals, or promotion state.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
ANALYSIS = ROOT / ".rumbling-hedge" / "research" / "prediction-market-analysis"
DEFAULT_WATCHLIST = STATE / "prediction-research-watchlist.latest.json"
DEFAULT_MANIFEST = ANALYSIS / "manifest.json"
DEFAULT_OUTPUT = STATE / "prediction-resolved-outcome-join.latest.json"

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "before",
    "by",
    "for",
    "from",
    "in",
    "is",
    "new",
    "of",
    "on",
    "or",
    "the",
    "to",
    "us",
    "will",
    "with",
    "announce",
    "announces",
    "announced",
    "yes",
    "no",
    "jan",
    "january",
    "feb",
    "february",
    "mar",
    "march",
    "apr",
    "april",
    "may",
    "jun",
    "june",
    "jul",
    "july",
    "aug",
    "august",
    "sep",
    "sept",
    "september",
    "oct",
    "october",
    "nov",
    "november",
    "dec",
    "december",
}

GENERIC_FAMILY_TERMS = {
    "above",
    "agreement",
    "below",
    "ceasefire",
    "deal",
    "extension",
    "fifa",
    "final",
    "finals",
    "market",
    "match",
    "over",
    "peace",
    "permanent",
    "price",
    "rate",
    "rates",
    "score",
    "settle",
    "under",
    "win",
    "wins",
    "world",
    "cup",
}


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def tokens(text: str | None) -> set[str]:
    if not text:
        return set()
    return {
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if len(token) >= 3 and not token.isdigit() and token not in STOPWORDS
    }


def overlap_score(needle: set[str], haystack: set[str]) -> float:
    if not needle or not haystack:
        return 0.0
    overlap = len(needle & haystack)
    if overlap == 0:
        return 0.0
    return overlap / math.sqrt(len(needle) * len(haystack))


def subject_tokens(text: str | None) -> set[str]:
    return tokens(text) - GENERIC_FAMILY_TERMS


def parse_json_array(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if not isinstance(value, str):
        return []
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    except Exception:
        return []


def infer_polymarket_outcome(row: dict[str, Any], desired_label: str) -> bool | None:
    outcomes = [str(item).strip().lower() for item in parse_json_array(row.get("outcomes"))]
    prices = parse_json_array(row.get("outcome_prices"))
    label = (desired_label or "Yes").strip().lower()
    if not outcomes or not prices:
        return None
    try:
        numeric = [float(item) for item in prices]
    except Exception:
        return None
    if max(numeric, default=0.0) < 0.99:
        return None
    try:
        winner_idx = numeric.index(max(numeric))
        desired_idx = outcomes.index(label)
    except ValueError:
        return None
    return winner_idx == desired_idx


def infer_kalshi_outcome(row: dict[str, Any], desired_label: str) -> bool | None:
    result = str(row.get("result") or "").strip().lower()
    label = (desired_label or "Yes").strip().lower()
    if result not in {"yes", "no"}:
        return None
    return result == label


def load_historical_markets(manifest_path: Path, max_rows: int) -> list[dict[str, Any]]:
    manifest = read_json(manifest_path)
    tables = manifest.get("tables") if isinstance(manifest.get("tables"), dict) else {}
    records: list[dict[str, Any]] = []
    try:
        import duckdb  # type: ignore
    except Exception:
        return records

    con = duckdb.connect()
    poly_files = (tables.get("polymarket_markets") or {}).get("sample") or []
    if poly_files:
        rows = con.execute(
            """
            select
              'polymarket' as venue,
              cast(id as varchar) as external_id,
              question,
              outcomes,
              outcome_prices,
              cast(end_date as varchar) as close_time
            from read_parquet(?)
            where closed = true
            limit ?
            """,
            [poly_files, max_rows],
        ).fetchall()
        cols = ["venue", "externalId", "question", "outcomes", "outcome_prices", "closeTime"]
        records.extend(dict(zip(cols, row)) for row in rows)

    kalshi_files = (tables.get("kalshi_markets") or {}).get("sample") or []
    if kalshi_files:
        rows = con.execute(
            """
            select
              'kalshi' as venue,
              cast(ticker as varchar) as external_id,
              title as question,
              result,
              cast(close_time as varchar) as close_time
            from read_parquet(?)
            where status in ('determined', 'finalized', 'settled')
              and result in ('yes', 'no')
            limit ?
            """,
            [kalshi_files, max_rows],
        ).fetchall()
        cols = ["venue", "externalId", "question", "result", "closeTime"]
        records.extend(dict(zip(cols, row)) for row in rows)

    return records


def resolve_for_item(
    item: dict[str, Any],
    historical: list[dict[str, Any]],
    min_score: float,
    min_matches: int,
    min_overlap_tokens: int,
    min_specific_matches: int,
    min_specific_overlap_tokens: int,
    top_n: int,
) -> dict[str, Any]:
    question = str(item.get("question") or "")
    desired_label = str(item.get("outcomeLabel") or "Yes")
    item_tokens = tokens(question)
    item_subject_tokens = subject_tokens(question)
    scored: list[tuple[float, dict[str, Any], bool | None]] = []
    subject_scored: list[tuple[float, dict[str, Any], bool | None]] = []
    for row in historical:
        row_question = str(row.get("question") or "")
        row_tokens = tokens(row_question)
        if len(item_tokens & row_tokens) < min_overlap_tokens:
            continue
        score = overlap_score(item_tokens, row_tokens)
        if score < min_score:
            continue
        resolved = (
            infer_polymarket_outcome(row, desired_label)
            if row.get("venue") == "polymarket"
            else infer_kalshi_outcome(row, desired_label)
        )
        if resolved is None:
            continue
        scored.append((score, row, resolved))
        row_subject_tokens = subject_tokens(row_question)
        if item_subject_tokens and len(item_subject_tokens & row_subject_tokens) >= min_specific_overlap_tokens:
            subject_scored.append((score, row, resolved))
    scored.sort(key=lambda entry: entry[0], reverse=True)
    subject_scored.sort(key=lambda entry: entry[0], reverse=True)
    matches = scored[:top_n]
    wins = sum(1 for _, _, resolved in scored if resolved)
    losses = sum(1 for _, _, resolved in scored if not resolved)
    total = wins + losses
    subject_wins = sum(1 for _, _, resolved in subject_scored if resolved)
    subject_losses = sum(1 for _, _, resolved in subject_scored if not resolved)
    subject_total = subject_wins + subject_losses
    if total < min_matches:
        status = "insufficient-history"
    elif subject_total < min_specific_matches:
        status = "insufficient-subject-specific-history"
    else:
        status = "joined-research-only"
    blockers = [
        "research-only",
        "not-paper-ready",
    ]
    if total < min_matches:
        blockers.append("too-few-market-family-resolved-outcomes")
    elif subject_total < min_specific_matches:
        blockers.append("too-few-subject-specific-resolved-outcomes")
    return {
        "venue": item.get("venue"),
        "externalId": item.get("externalId"),
        "question": question,
        "outcomeLabel": desired_label,
        "status": status,
        "resolvedMatchCount": total,
        "resolvedWinRate": round(wins / total, 6) if total else None,
        "wins": wins,
        "losses": losses,
        "tokenCount": len(item_tokens),
        "subjectTokenCount": len(item_subject_tokens),
        "subjectTokens": sorted(item_subject_tokens),
        "subjectSpecificMatchCount": subject_total,
        "subjectSpecificWinRate": round(subject_wins / subject_total, 6) if subject_total else None,
        "subjectSpecificWins": subject_wins,
        "subjectSpecificLosses": subject_losses,
        "blockers": blockers,
        "topMatches": [
            {
                "score": round(score, 6),
                "venue": row.get("venue"),
                "externalId": row.get("externalId"),
                "question": row.get("question"),
                "closeTime": row.get("closeTime"),
                "desiredOutcomeWon": resolved,
            }
            for score, row, resolved in matches
        ],
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    watchlist = read_json(Path(args.watchlist))
    items = watchlist.get("items") if isinstance(watchlist.get("items"), list) else []
    historical = load_historical_markets(Path(args.manifest), args.max_historical_rows)
    joins = [
        resolve_for_item(
            item,
            historical,
            args.min_score,
            args.min_matches,
            args.min_overlap_tokens,
            args.min_specific_matches,
            args.min_specific_overlap_tokens,
            args.top_matches,
        )
        for item in items
    ]
    status_counts = Counter(item["status"] for item in joins)
    joined = sum(1 for item in joins if item["status"] == "joined-research-only")
    return {
        "command": "prediction-resolved-outcome-join",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "researchOnly": True,
        "writesOrders": False,
        "readyForPaper": False,
        "watchlistPath": str(Path(args.watchlist).resolve()),
        "manifestPath": str(Path(args.manifest).resolve()),
        "historicalRowsLoaded": len(historical),
        "watchCount": len(items),
        "joinedResearchOnlyCount": joined,
        "statusCounts": dict(status_counts),
        "minScore": args.min_score,
        "minMatches": args.min_matches,
        "minOverlapTokens": args.min_overlap_tokens,
        "minSpecificMatches": args.min_specific_matches,
        "minSpecificOverlapTokens": args.min_specific_overlap_tokens,
        "decision": "research-only; resolved outcomes are context until spread, fillability, fees, and promotion review agree",
        "items": joins,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Join prediction watchlist to historical resolved outcome families.")
    parser.add_argument("--watchlist", default=str(DEFAULT_WATCHLIST))
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--max-historical-rows", type=int, default=250_000)
    parser.add_argument("--min-score", type=float, default=0.35)
    parser.add_argument("--min-matches", type=int, default=20)
    parser.add_argument("--min-overlap-tokens", type=int, default=2)
    parser.add_argument("--min-specific-matches", type=int, default=5)
    parser.add_argument("--min-specific-overlap-tokens", type=int, default=1)
    parser.add_argument("--top-matches", type=int, default=8)
    args = parser.parse_args()
    payload = build_report(args)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
