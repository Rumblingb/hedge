#!/usr/bin/env python3
"""Build official-source resolved labels for historical macro/rates markets.

This is a research-only bridge between the local prediction-market archive and
official Fed target-range history. It checks whether closed Polymarket Fed/rate
markets agree with the Federal Reserve Open Market Operations table before any
macro/rates parser work is treated as usable evidence.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.fed_prior_upper_bound_source import (
    FED_OPENMARKET_URL,
    FedTargetRangeRow,
    fetch_html,
    parse_openmarket_rows,
)


STATE = ROOT / ".rumbling-hedge/state"
ANALYSIS = ROOT / ".rumbling-hedge/research/prediction-market-analysis"
DEFAULT_MANIFEST = ANALYSIS / "manifest.json"
OUT = STATE / "prediction-macro-rates-resolved-labels.latest.json"
VAULT = Path.home() / "Documents/memorybrain"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def current_utc_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def default_markdown_path() -> Path:
    return VAULT / "Agent-Hermes" / f"prediction-macro-rates-resolved-labels-{current_utc_date()}.md"


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


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


def polymarket_yes_won(row: dict[str, Any]) -> bool | None:
    outcomes = [str(item).strip().lower() for item in parse_json_array(row.get("outcomes"))]
    prices = parse_json_array(row.get("outcome_prices"))
    if not outcomes or not prices:
        return None
    try:
        numeric = [float(item) for item in prices]
    except Exception:
        return None
    if max(numeric, default=0.0) < 0.99:
        return None
    try:
        yes_idx = outcomes.index("yes")
    except ValueError:
        return None
    return numeric.index(max(numeric)) == yes_idx


def parse_close_date(row: dict[str, Any]) -> date | None:
    close_time = str(row.get("closeTime") or row.get("close_time") or "")
    match = re.match(r"(20\d{2})-(\d{2})-(\d{2})", close_time)
    if not match:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def parse_macro_rate_question(question: str) -> dict[str, Any] | None:
    text = question.lower()
    if "fed" not in text:
        return None
    threshold = re.search(r"\babove\s+(\d+(?:\.\d+)?)\s*%", text)
    if threshold and "rate" in text:
        return {"kind": "upper-bound-threshold", "thresholdUpperBound": float(threshold.group(1))}
    bps = re.search(r"\b(increase|decrease)\s+(?:interest\s+)?rates?\s+by\s+(\d+)\s*bps\b", text)
    if bps:
        direction = "increase" if bps.group(1) == "increase" else "decrease"
        return {"kind": "bps-change", "direction": direction, "changeBps": int(bps.group(2))}
    if "no change" in text and "rate" in text:
        return {"kind": "no-change"}
    return None


def nearest_official_row(target_rows: list[FedTargetRangeRow], close_day: date, max_days: int) -> FedTargetRangeRow | None:
    best: tuple[int, FedTargetRangeRow] | None = None
    for row in target_rows:
        row_day = date.fromisoformat(row.effectiveDate)
        distance = abs((row_day - close_day).days)
        if distance <= max_days and (best is None or distance < best[0]):
            best = (distance, row)
    return best[1] if best else None


def official_truth(parsed: dict[str, Any], target_row: FedTargetRangeRow) -> bool | None:
    kind = parsed.get("kind")
    if kind == "upper-bound-threshold":
        return target_row.upperBound > float(parsed["thresholdUpperBound"])
    if kind == "bps-change":
        change = int(parsed["changeBps"])
        if parsed.get("direction") == "increase":
            return int(target_row.increaseBps or 0) == change
        return int(target_row.decreaseBps or 0) == change
    if kind == "no-change":
        return int(target_row.increaseBps or 0) == 0 and int(target_row.decreaseBps or 0) == 0
    return None


def load_polymarket_fed_rows(manifest_path: Path, max_rows: int) -> tuple[list[dict[str, Any]], str | None]:
    manifest = read_json(manifest_path)
    tables = manifest.get("tables") if isinstance(manifest.get("tables"), dict) else {}
    files = (tables.get("polymarket_markets") or {}).get("sample") or []
    if not files:
        return [], "missing-polymarket-market-files"
    try:
        import duckdb  # type: ignore
    except Exception as exc:
        return [], f"duckdb-unavailable:{type(exc).__name__}"
    con = duckdb.connect()
    rows = con.execute(
        """
        select
          cast(id as varchar) as external_id,
          question,
          outcomes,
          outcome_prices,
          cast(end_date as varchar) as close_time
        from read_parquet(?)
        where closed = true
          and lower(question) like '%fed%'
          and (
            lower(question) like '%rate%'
            or lower(question) like '%bps%'
            or lower(question) like '%fomc%'
          )
        limit ?
        """,
        [files, max_rows],
    ).fetchall()
    cols = ["externalId", "question", "outcomes", "outcome_prices", "closeTime"]
    return [dict(zip(cols, row)) for row in rows], None


def build_resolved_labels(
    *,
    historical_rows: list[dict[str, Any]],
    fed_target_rows: list[FedTargetRangeRow],
    source_url: str,
    max_date_distance_days: int = 14,
) -> dict[str, Any]:
    parsed_rows: list[dict[str, Any]] = []
    mismatches: list[dict[str, Any]] = []
    kind_counts: dict[str, int] = {}
    comparable = 0
    agreements = 0

    for row in historical_rows:
        question = str(row.get("question") or "")
        parsed = parse_macro_rate_question(question)
        yes_won = polymarket_yes_won(row)
        close_day = parse_close_date(row)
        if parsed is None or yes_won is None or close_day is None:
            continue
        target = nearest_official_row(fed_target_rows, close_day, max_date_distance_days)
        if target is None:
            continue
        truth = official_truth(parsed, target)
        if truth is None:
            continue
        comparable += 1
        agreement = yes_won == truth
        agreements += int(agreement)
        kind = str(parsed.get("kind"))
        kind_counts[kind] = kind_counts.get(kind, 0) + 1
        item = {
            "venue": "polymarket",
            "externalId": row.get("externalId"),
            "question": question,
            "closeDate": close_day.isoformat(),
            "parsed": parsed,
            "marketYesWon": yes_won,
            "officialTruth": truth,
            "officialEffectiveDate": target.effectiveDate,
            "officialTargetRange": target.levelText,
            "agreement": agreement,
        }
        parsed_rows.append(item)
        if not agreement and len(mismatches) < 20:
            mismatches.append(item)

    agreement_rate = round(agreements / comparable, 6) if comparable else 0.0
    blockers: list[str] = []
    if not fed_target_rows:
        blockers.append("missing-official-fed-target-history")
    if not historical_rows:
        blockers.append("missing-local-polymarket-fed-history")
    if comparable < 20:
        blockers.append("too-few-officially-comparable-rate-markets")
    if comparable and agreement_rate < 0.95:
        blockers.append("official-label-agreement-below-contract")
    return {
        "command": "prediction-macro-rates-resolved-labels",
        "generatedAt": now_iso(),
        "source": {
            "officialFedTargetHistory": source_url,
            "localPredictionManifest": str(DEFAULT_MANIFEST),
        },
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "readyForPaper": False,
        "readyForExecution": False,
        "historicalRowsLoaded": len(historical_rows),
        "fedTargetRowsLoaded": len(fed_target_rows),
        "officialComparableCount": comparable,
        "officialAgreementCount": agreements,
        "officialAgreementRate": agreement_rate,
        "usableForResearchJoinCount": comparable if not blockers else 0,
        "kindCounts": kind_counts,
        "mismatchCount": comparable - agreements,
        "mismatchSamples": mismatches,
        "sampleLabels": parsed_rows[:50],
        "blockers": blockers,
        "decision": (
            "research-only-macro-rates-resolved-labels-blocked"
            if blockers
            else "research-only-macro-rates-resolved-labels-ready"
        ),
        "hardRules": [
            "Official Fed target history is the label source; market prices are not labels.",
            "Resolved labels are research context only until fillability, fees, and promotion gates pass.",
            "No paper/live/funding route from this artifact.",
        ],
    }


def render_markdown(payload: dict[str, Any]) -> str:
    generated_date = str(payload.get("generatedAt") or current_utc_date())[:10]
    lines = [
        f"# Prediction Macro/Rates Resolved Labels - {generated_date}",
        "",
        "Parent hub: [[BILL-CONTROL-HUB]]",
        "",
        "Research-only resolved-label audit for historical Fed/rate prediction markets.",
        "",
        "## Summary",
        "",
        f"- Decision: `{payload.get('decision')}`",
        f"- Historical rows loaded: `{payload.get('historicalRowsLoaded')}`",
        f"- Official comparable labels: `{payload.get('officialComparableCount')}`",
        f"- Official agreement rate: `{payload.get('officialAgreementRate')}`",
        f"- Usable for research join: `{payload.get('usableForResearchJoinCount')}`",
        f"- Kind counts: `{payload.get('kindCounts')}`",
        f"- Blockers: `{payload.get('blockers')}`",
        "",
        "## Hard Rules",
        "",
    ]
    for rule in payload.get("hardRules") or []:
        lines.append(f"- {rule}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build official-source macro/rates resolved-label audit.")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--fed-source-url", default=FED_OPENMARKET_URL)
    parser.add_argument("--fed-input-html", default="")
    parser.add_argument("--max-historical-rows", type=int, default=250_000)
    parser.add_argument("--max-date-distance-days", type=int, default=14)
    parser.add_argument("--output", default=str(OUT))
    parser.add_argument("--markdown", default=str(default_markdown_path()))
    args = parser.parse_args()

    if args.fed_input_html:
        fed_html = Path(args.fed_input_html).read_text()
    else:
        fed_html = fetch_html(args.fed_source_url)
    historical, error = load_polymarket_fed_rows(Path(args.manifest), args.max_historical_rows)
    payload = build_resolved_labels(
        historical_rows=historical,
        fed_target_rows=parse_openmarket_rows(fed_html),
        source_url=args.fed_source_url,
        max_date_distance_days=args.max_date_distance_days,
    )
    if error:
        payload["blockers"] = list(payload.get("blockers") or []) + [error]
        payload["decision"] = "research-only-macro-rates-resolved-labels-blocked"
        payload["usableForResearchJoinCount"] = 0

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    md = Path(args.markdown)
    md.parent.mkdir(parents=True, exist_ok=True)
    md.write_text(render_markdown(payload))
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
