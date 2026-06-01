#!/usr/bin/env python3
"""Build a research-only label-source manifest for prediction markets.

The resolved-outcome join can compare a watch item to historical markets, but
it should not keep rerunning when the real blocker is thin subject-specific
labels. This manifest makes that blocker explicit and points the next research
loop toward new label coverage instead of wider matching thresholds.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.prediction_category_drilldown import category_for_text
from scripts.prediction_label_card_audit import CARD_ROOT, extract_label_rows, missing_fields
from scripts.prediction_resolved_outcome_join import (
    DEFAULT_MANIFEST,
    DEFAULT_WATCHLIST,
    infer_kalshi_outcome,
    infer_polymarket_outcome,
    load_historical_markets,
    overlap_score,
    subject_tokens,
    tokens,
)


STATE = ROOT / ".rumbling-hedge" / "state"
OUT = STATE / "prediction-label-source-manifest.latest.json"
VAULT = Path.home() / "Documents/memorybrain"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def current_utc_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def default_markdown_path() -> Path:
    return VAULT / "Agent-Hermes" / f"prediction-label-source-manifest-{current_utc_date()}.md"


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def text_of(row: dict[str, Any]) -> str:
    return str(row.get("question") or row.get("title") or row.get("marketQuestion") or "")


def resolved_for_label(row: dict[str, Any], desired_label: str) -> bool | None:
    if row.get("venue") == "polymarket":
        return infer_polymarket_outcome(row, desired_label)
    if row.get("venue") == "kalshi":
        return infer_kalshi_outcome(row, desired_label)
    return None


def load_label_card_rows(card_root: Path = CARD_ROOT) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not card_root.exists():
        return rows
    for card in sorted(card_root.glob("*.md")):
        section_present, raw_rows = extract_label_rows(card.read_text(errors="ignore"))
        if not section_present:
            continue
        category_hint = card.stem.split("-", 1)[0] if "-" in card.stem else "unknown"
        for row in raw_rows:
            if missing_fields(row):
                continue
            item = dict(row)
            item["category"] = category_hint
            item["source"] = "obsidian-label-card"
            item["cardPath"] = str(card)
            rows.append(item)
    return rows


def subject_key(text: str) -> str:
    parts = sorted(subject_tokens(text))
    return "+".join(parts[:4]) if parts else "generic"


def summarize_repeated_families(historical: list[dict[str, Any]], top_n: int) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str], dict[str, Any]] = {}
    for row in historical:
        question = text_of(row)
        category = category_for_text(question)
        key = subject_key(question)
        bucket = buckets.setdefault(
            (category, key),
            {
                "category": category,
                "subjectKey": key,
                "resolvedCount": 0,
                "venues": Counter(),
                "examples": [],
            },
        )
        bucket["resolvedCount"] += 1
        bucket["venues"][str(row.get("venue") or "missing")] += 1
        if len(bucket["examples"]) < 5:
            bucket["examples"].append({
                "venue": row.get("venue"),
                "externalId": row.get("externalId"),
                "question": question[:180],
                "closeTime": row.get("closeTime"),
            })

    rows: list[dict[str, Any]] = []
    for bucket in buckets.values():
        rows.append({
            "category": bucket["category"],
            "subjectKey": bucket["subjectKey"],
            "resolvedCount": bucket["resolvedCount"],
            "venues": dict(bucket["venues"].most_common()),
            "examples": bucket["examples"],
        })
    return sorted(rows, key=lambda item: (-int(item["resolvedCount"]), item["category"], item["subjectKey"]))[:top_n]


def coverage_for_watch_item(
    item: dict[str, Any],
    historical: list[dict[str, Any]],
    label_card_rows: list[dict[str, Any]] | None = None,
    *,
    min_score: float,
    min_matches: int,
    min_specific_matches: int,
    min_overlap_tokens: int,
    min_specific_overlap_tokens: int,
    top_matches: int,
) -> dict[str, Any]:
    question = text_of(item)
    desired_label = str(item.get("outcomeLabel") or "Yes")
    item_tokens = tokens(question)
    item_subject = subject_tokens(question)
    item_category = category_for_text(question)
    scored: list[tuple[float, dict[str, Any], bool | None]] = []
    subject_scored: list[tuple[float, dict[str, Any], bool | None]] = []
    venues: Counter[str] = Counter()
    subject_venues: Counter[str] = Counter()
    label_card_rows = label_card_rows or []

    for row in historical:
        row_question = text_of(row)
        row_tokens = tokens(row_question)
        if len(item_tokens & row_tokens) < min_overlap_tokens:
            continue
        score = overlap_score(item_tokens, row_tokens)
        if score < min_score:
            continue
        resolved = resolved_for_label(row, desired_label)
        if resolved is None:
            continue
        scored.append((score, row, resolved))
        venues[str(row.get("venue") or "missing")] += 1
        row_subject = subject_tokens(row_question)
        if item_subject and len(item_subject & row_subject) >= min_specific_overlap_tokens:
            subject_scored.append((score, row, resolved))
            subject_venues[str(row.get("venue") or "missing")] += 1

    scored.sort(key=lambda entry: entry[0], reverse=True)
    subject_scored.sort(key=lambda entry: entry[0], reverse=True)
    scored_ids = {str(row.get("externalId")) for _, row, _ in scored if row.get("externalId") is not None}
    subject_scored_ids = {str(row.get("externalId")) for _, row, _ in subject_scored if row.get("externalId") is not None}
    family_card_rows = [
        row
        for row in label_card_rows
        if str(row.get("category") or "").strip().lower() == item_category
        and str(row.get("externalId") or "") not in scored_ids
    ]
    matching_card_rows = [
        row
        for row in label_card_rows
        if str(row.get("subjectKey") or "").strip().lower() == subject_key(question).strip().lower()
        and str(row.get("externalId") or "") not in subject_scored_ids
    ]
    family_count = len(scored) + len(family_card_rows)
    subject_count = len(subject_scored) + len(matching_card_rows)
    if family_count < min_matches:
        status = "needs-family-label-source"
    elif subject_count < min_specific_matches:
        status = "needs-subject-label-source"
    else:
        status = "usable-for-research-join"
    blockers = ["research-only", "not-paper-ready"]
    if family_count < min_matches:
        blockers.append("too-few-family-resolved-labels")
    if subject_count < min_specific_matches:
        blockers.append("too-few-subject-resolved-labels")
    return {
        "venue": item.get("venue"),
        "externalId": item.get("externalId"),
        "question": question,
        "outcomeLabel": desired_label,
        "category": item_category,
        "subjectTokens": sorted(item_subject),
        "subjectKey": subject_key(question),
        "status": status,
        "familyResolvedCount": family_count,
        "subjectResolvedCount": subject_count,
        "rawArchiveFamilyResolvedCount": len(scored),
        "rawArchiveSubjectResolvedCount": len(subject_scored),
        "labelCardFamilyRows": len(family_card_rows),
        "labelCardSubjectRows": len(matching_card_rows),
        "venues": dict(venues.most_common()),
        "subjectVenues": dict(subject_venues.most_common()),
        "blockers": blockers,
        "recommendedNextSource": recommended_next_source(item_category, subject_count),
        "topMatches": [
            {
                "score": round(score, 6),
                "venue": row.get("venue"),
                "externalId": row.get("externalId"),
                "question": text_of(row)[:220],
                "closeTime": row.get("closeTime"),
                "desiredOutcomeWon": resolved,
            }
            for score, row, resolved in subject_scored[:top_matches]
        ],
        "labelCardMatches": [
            {
                "venue": row.get("venue"),
                "externalId": row.get("externalId"),
                "question": str(row.get("question") or "")[:220],
                "closeTime": row.get("closeTime"),
                "outcomeWon": str(row.get("outcomeWon") or "").lower(),
                "marketType": row.get("marketType"),
                "cardPath": row.get("cardPath"),
            }
            for row in matching_card_rows[:top_matches]
        ],
    }


def recommended_next_source(category: str, subject_count: int) -> str:
    if subject_count > 0:
        return "expand-subject-specific resolved history before rerunning the join"
    if category == "macro-rates":
        return "Kalshi series archive plus official release calendar labels"
    if category == "crypto":
        return "resolved crypto up/down corpus plus exchange OHLCV at settlement timestamps"
    if category == "geopolitics":
        return "Polymarket closed markets plus manual settlement/event-source cards"
    if category == "sports":
        return "tournament/team/player specific historical settlement cards"
    if category == "commodities":
        return "contract-specific settlement source and resolved line history"
    return "closed-market archive with subject-specific settlement labels"


def build_label_manifest(
    *,
    watchlist: dict[str, Any],
    historical: list[dict[str, Any]],
    manifest_path: Path,
    label_card_rows: list[dict[str, Any]] | None = None,
    min_score: float = 0.35,
    min_matches: int = 20,
    min_specific_matches: int = 5,
    min_overlap_tokens: int = 2,
    min_specific_overlap_tokens: int = 1,
    top_matches: int = 8,
    top_families: int = 25,
) -> dict[str, Any]:
    items = watchlist.get("items") if isinstance(watchlist.get("items"), list) else []
    label_card_rows = label_card_rows or []
    coverage = [
        coverage_for_watch_item(
            item,
            historical,
            label_card_rows,
            min_score=min_score,
            min_matches=min_matches,
            min_specific_matches=min_specific_matches,
            min_overlap_tokens=min_overlap_tokens,
            min_specific_overlap_tokens=min_specific_overlap_tokens,
            top_matches=top_matches,
        )
        for item in items
    ]
    status_counts = Counter(item["status"] for item in coverage)
    usable = int(status_counts.get("usable-for-research-join", 0))
    needs_new_source = len(coverage) - usable
    sources = {
        "watchlist": str(DEFAULT_WATCHLIST),
        "historicalManifest": str(manifest_path.resolve()),
        "labelCardRoot": str(CARD_ROOT),
    }
    return {
        "command": "prediction-label-source-manifest",
        "generatedAt": now_iso(),
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "readyForPaper": False,
        "readyForExecution": False,
        "manifestPath": str(manifest_path.resolve()),
        "sources": sources,
        "watchCount": len(items),
        "historicalRowsLoaded": len(historical),
        "labelCardRowsLoaded": len(label_card_rows),
        "statusCounts": dict(status_counts),
        "usableForResearchJoinCount": usable,
        "itemsNeedingNewLabelSource": needs_new_source,
        "decision": "research-only; build better resolved labels before paper/demo promotion",
        "coverage": coverage,
        "items": coverage,
        "repeatedFamilies": summarize_repeated_families(historical, top_families),
        "hardRules": [
            "Do not widen similarity thresholds to manufacture resolved history.",
            "Do not promote broad by-price priors without subject-specific labels.",
            "No item in this manifest approves paper, demo, live, funding, sizing, or broker routing.",
        ],
    }


def render_markdown(payload: dict[str, Any]) -> str:
    generated_date = str(payload.get("generatedAt") or current_utc_date())[:10]
    lines = [
        f"# Prediction Label Source Manifest - {generated_date}",
        "",
        "Parent hub: [[BILL-CONTROL-HUB]]",
        "",
        "Research-only manifest for resolved prediction-market labels. This page does not approve paper or live trading.",
        "",
        "## Summary",
        "",
        f"- Decision: `{payload.get('decision')}`",
        f"- Watch items: `{payload.get('watchCount')}`",
        f"- Historical rows loaded: `{payload.get('historicalRowsLoaded')}`",
        f"- Label card rows loaded: `{payload.get('labelCardRowsLoaded')}`",
        f"- Usable for research join: `{payload.get('usableForResearchJoinCount')}`",
        f"- Needs new label source: `{payload.get('itemsNeedingNewLabelSource')}`",
        f"- Status counts: `{payload.get('statusCounts')}`",
        "",
        "## Watch Coverage",
        "",
    ]
    for item in payload.get("coverage") or []:
        lines.extend([
            f"### {item.get('externalId')} - {item.get('category')}",
            "",
            f"- Question: {item.get('question')}",
            f"- Status: `{item.get('status')}`",
            f"- Subject key: `{item.get('subjectKey')}`",
            f"- Family resolved labels: `{item.get('familyResolvedCount')}`",
            f"- Subject resolved labels: `{item.get('subjectResolvedCount')}`",
            f"- Label-card rows used: family `{item.get('labelCardFamilyRows')}`, subject `{item.get('labelCardSubjectRows')}`",
            f"- Next source: {item.get('recommendedNextSource')}",
            f"- Blockers: `{item.get('blockers')}`",
            "",
        ])
    lines.extend(["## Hard Rules", ""])
    for rule in payload.get("hardRules") or []:
        lines.append(f"- {rule}")
    lines.append("")
    return "\n".join(lines)


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    watchlist = read_json(Path(args.watchlist))
    historical = load_historical_markets(Path(args.manifest), args.max_historical_rows)
    label_card_rows = load_label_card_rows(Path(args.label_card_root))
    return build_label_manifest(
        watchlist=watchlist,
        historical=historical,
        manifest_path=Path(args.manifest),
        label_card_rows=label_card_rows,
        min_score=args.min_score,
        min_matches=args.min_matches,
        min_specific_matches=args.min_specific_matches,
        min_overlap_tokens=args.min_overlap_tokens,
        min_specific_overlap_tokens=args.min_specific_overlap_tokens,
        top_matches=args.top_matches,
        top_families=args.top_families,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a research-only prediction label-source manifest.")
    parser.add_argument("--watchlist", default=str(DEFAULT_WATCHLIST))
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--label-card-root", default=str(CARD_ROOT))
    parser.add_argument("--output", default=str(OUT))
    parser.add_argument("--markdown-output", default=str(default_markdown_path()))
    parser.add_argument("--max-historical-rows", type=int, default=250_000)
    parser.add_argument("--min-score", type=float, default=0.35)
    parser.add_argument("--min-matches", type=int, default=20)
    parser.add_argument("--min-specific-matches", type=int, default=5)
    parser.add_argument("--min-overlap-tokens", type=int, default=2)
    parser.add_argument("--min-specific-overlap-tokens", type=int, default=1)
    parser.add_argument("--top-matches", type=int, default=8)
    parser.add_argument("--top-families", type=int, default=25)
    args = parser.parse_args()

    payload = build_report(args)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    markdown = Path(args.markdown_output)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    markdown.write_text(render_markdown(payload))
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
