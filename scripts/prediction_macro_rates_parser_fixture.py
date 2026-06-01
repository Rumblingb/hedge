#!/usr/bin/env python3
"""Build a research-only Fed/Kalshi macro-rates parser fixture.

The broad prediction scanner correctly rejects current macro/rates pairs, but
the next useful step is source-specific parsing: Polymarket Fed decision
brackets express a change in the target upper bound, while Kalshi KXFED
contracts express whether the post-meeting upper bound is above a threshold.

This fixture extracts both sides and refuses to mark the parser comparable
unless a prior upper-bound value is supplied from an explicit source. It writes
no orders and does not change the TypeScript scanner.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge/state"
RESEARCH = ROOT / ".rumbling-hedge/research"
MACRO_SNAPSHOT = RESEARCH / "prediction-narrow-snapshots/macro-rates.json"
KALSHI_FILLABILITY = STATE / "kalshi-fillability-snapshot.latest.json"
FED_PRIOR_SOURCE = STATE / "fed-prior-upper-bound-source.latest.json"
OUT = STATE / "prediction-macro-rates-parser-fixture.latest.json"
VAULT = Path.home() / "Documents/memorybrain"

MONTHS: dict[str, int] = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def current_utc_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def default_markdown_path() -> Path:
    return VAULT / "Agent-Hermes" / f"prediction-macro-rates-parser-fixture-{current_utc_date()}.md"


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def parse_prior(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
        return parsed if 0 <= parsed <= 10 else None
    except Exception:
        return None


def prior_from_source_artifact(path: Path) -> tuple[float | None, str | None]:
    payload = read_json(path, {})
    if not isinstance(payload, dict):
        return None, None
    if payload.get("decision") != "research-only-fed-prior-upper-bound-source-ready":
        return None, None
    if not payload.get("dataUsable"):
        return None, None
    prior = parse_prior(str(payload.get("priorUpperBound") or ""))
    source = payload.get("source") if isinstance(payload.get("source"), dict) else {}
    source_url = str(source.get("url") or "")
    if prior is None or not source_url:
        return None, None
    effective = payload.get("effectiveDate")
    return prior, f"{source_url}#effectiveDate={effective}"


def resolve_prior(
    *,
    explicit_prior: str | None,
    explicit_source: str | None,
    source_artifact: Path,
) -> tuple[float | None, str | None]:
    prior = parse_prior(explicit_prior)
    source = explicit_source
    if prior is not None and source and source != "manual-unset":
        return prior, source
    artifact_prior, artifact_source = prior_from_source_artifact(source_artifact)
    if artifact_prior is not None and artifact_source:
        return artifact_prior, artifact_source
    return prior, source


def parse_date_from_text(text: str) -> str | None:
    lowered = text.lower()
    match = re.search(
        r"\b(january|jan|february|feb|march|mar|april|apr|may|june|jun|july|jul|august|aug|september|sept|sep|october|oct|november|nov|december|dec)\s+(\d{1,2}),?\s+(20\d{2})\b",
        lowered,
    )
    if match:
        month = MONTHS[match.group(1)]
        day = int(match.group(2))
        year = int(match.group(3))
        return f"{year:04d}-{month:02d}-{day:02d}"

    month_year = re.search(
        r"\b(january|jan|february|feb|march|mar|april|apr|may|june|jun|july|jul|august|aug|september|sept|sep|october|oct|november|nov|december|dec)\s+(20\d{2})\b",
        lowered,
    )
    if month_year:
        month = MONTHS[month_year.group(1)]
        year = int(month_year.group(2))
        return f"{year:04d}-{month:02d}-xx"
    return None


def expiry_date(row: dict[str, Any]) -> str | None:
    expiry = str(row.get("expiry") or "")
    return expiry[:10] if re.match(r"20\d{2}-\d{2}-\d{2}", expiry) else None


def parse_polymarket_fed_decision(row: dict[str, Any]) -> dict[str, Any] | None:
    if str(row.get("venue") or "").lower() != "polymarket":
        return None
    question = str(row.get("marketQuestion") or "")
    settlement = str(row.get("settlementText") or "")
    question_text = question.lower()
    text = f"{question} {settlement}".lower()
    if "fed" not in text:
        return None
    if "no change" not in question_text and "bps" not in question_text:
        return None

    delta_bps: int | None = None
    bucket = "unknown"
    if "no change" in question_text:
        delta_bps = 0
        bucket = "no-change"
    else:
        bps = re.search(r"\b(25|50)\+?\s*bps\b", question_text)
        if not bps:
            return None
        amount = int(bps.group(1))
        if "decrease" in question_text or "cut" in question_text or "lower" in question_text:
            delta_bps = -amount
            bucket = f"cut-{amount}{'-plus' if '50+' in question_text else ''}"
        elif "increase" in question_text or "hike" in question_text or "raise" in question_text:
            delta_bps = amount
            bucket = f"hike-{amount}{'-plus' if '50+' in question_text else ''}"

    if delta_bps is None:
        return None
    return {
        "venue": row.get("venue"),
        "externalId": row.get("externalId"),
        "question": question,
        "meetingDate": expiry_date(row) or parse_date_from_text(question) or parse_date_from_text(settlement),
        "deltaBps": delta_bps,
        "bucket": bucket,
        "price": row.get("price"),
        "clobTokenId": row.get("clobTokenId"),
    }


def parse_kalshi_kxfed(row: dict[str, Any]) -> dict[str, Any] | None:
    title = str(row.get("title") or row.get("marketQuestion") or row.get("eventTitle") or "")
    ticker = str(row.get("ticker") or row.get("externalId") or "")
    series = str(row.get("seriesTicker") or "")
    text = f"{ticker} {title}".lower()
    if "kxfed" not in text and series.upper() != "KXFED":
        return None
    threshold = re.search(r"\babove\s+(\d+(?:\.\d+)?)%\s+following\b", text)
    if not threshold:
        threshold = re.search(r"-t(\d+(?:\.\d+)?)\b", text)
    if not threshold:
        return None
    return {
        "venue": "kalshi",
        "ticker": ticker or row.get("externalId"),
        "question": title,
        "meetingDate": parse_date_from_text(title),
        "thresholdUpperBound": float(threshold.group(1)),
        "yesBid": row.get("yesBid") if "yesBid" in row else row.get("bestBid"),
        "yesAsk": row.get("yesAsk") if "yesAsk" in row else row.get("bestAsk"),
        "lastPrice": row.get("lastPrice") if "lastPrice" in row else row.get("price"),
        "bucket": row.get("bucket"),
    }


def implied_upper_bound(prior_upper_bound: float | None, pm: dict[str, Any]) -> dict[str, Any]:
    delta = int(pm.get("deltaBps") or 0)
    if prior_upper_bound is None:
        return {"status": "missing-prior-upper-bound"}
    if "plus" in str(pm.get("bucket") or ""):
        if delta < 0:
            return {"status": "range", "operator": "<=", "value": round(prior_upper_bound + (delta / 100), 4)}
        return {"status": "range", "operator": ">=", "value": round(prior_upper_bound + (delta / 100), 4)}
    return {"status": "exact", "value": round(prior_upper_bound + (delta / 100), 4)}


def threshold_truth(implied: dict[str, Any], threshold: float) -> bool | None:
    status = implied.get("status")
    if status == "exact":
        return float(implied["value"]) > threshold
    if status == "range":
        # A range cannot be reduced to one truth value unless the whole range is
        # on one side of the threshold. Ambiguous cases stay untradeable.
        value = float(implied["value"])
        if implied.get("operator") == ">=" and value > threshold:
            return True
        if implied.get("operator") == "<=" and value <= threshold:
            return False
    return None


def build_fixture(
    *,
    macro_snapshot: list[Any],
    kalshi_fillability: dict[str, Any],
    prior_upper_bound: float | None,
    prior_source: str | None,
) -> dict[str, Any]:
    rows = [row for row in macro_snapshot if isinstance(row, dict)]
    top_executable = kalshi_fillability.get("topExecutable") if isinstance(kalshi_fillability.get("topExecutable"), list) else []
    pm_decisions = [parsed for row in rows if (parsed := parse_polymarket_fed_decision(row))]
    kxfed_rows = [parsed for row in [*rows, *top_executable] if isinstance(row, dict) and (parsed := parse_kalshi_kxfed(row))]
    same_meeting_pairs: list[dict[str, Any]] = []
    for pm in pm_decisions:
        for kx in kxfed_rows:
            if pm.get("meetingDate") != kx.get("meetingDate"):
                continue
            implied = implied_upper_bound(prior_upper_bound, pm)
            same_meeting_pairs.append({
                "polymarketExternalId": pm.get("externalId"),
                "polymarketBucket": pm.get("bucket"),
                "polymarketDeltaBps": pm.get("deltaBps"),
                "kalshiTicker": kx.get("ticker"),
                "meetingDate": pm.get("meetingDate"),
                "thresholdUpperBound": kx.get("thresholdUpperBound"),
                "impliedUpperBound": implied,
                "kalshiYesIfPolymarketBucketWins": threshold_truth(implied, float(kx.get("thresholdUpperBound"))),
            })

    prior_ok = prior_upper_bound is not None and bool(prior_source and prior_source != "manual-unset")
    comparable = [pair for pair in same_meeting_pairs if pair.get("kalshiYesIfPolymarketBucketWins") is not None]
    blockers: list[str] = []
    if not pm_decisions:
        blockers.append("no-polymarket-fed-decision-brackets")
    if not kxfed_rows:
        blockers.append("no-kalshi-kxfed-threshold-contracts")
    if not same_meeting_pairs:
        blockers.append("no-exact-meeting-date-fed-kxfed-overlap")
    if not prior_ok:
        blockers.append("missing-explicit-prior-upper-bound-source")
    if prior_ok and not comparable:
        blockers.append("no-unambiguous-threshold-truth-table")

    return {
        "command": "prediction-macro-rates-parser-fixture",
        "generatedAt": now_iso(),
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "readyForPaper": False,
        "readyForExecution": False,
        "priorUpperBound": prior_upper_bound,
        "priorUpperBoundSource": prior_source or "manual-unset",
        "polymarketFedDecisionCount": len(pm_decisions),
        "kalshiKxfedThresholdCount": len(kxfed_rows),
        "sameMeetingPairCount": len(same_meeting_pairs),
        "comparablePairCount": len(comparable),
        "polymarketFedDecisions": pm_decisions,
        "kalshiKxfedThresholds": kxfed_rows,
        "sameMeetingPairs": same_meeting_pairs[:100],
        "blockers": blockers,
        "decision": "research-only-fed-kalshi-parser-fixture-blocked" if blockers else "research-only-fed-kalshi-parser-fixture-ready",
        "nextAction": (
            "Add an explicit official prior upper-bound source before comparing Polymarket Fed brackets to KXFED thresholds."
            if "missing-explicit-prior-upper-bound-source" in blockers
            else "Use the truth table as a parser fixture only; still require resolved labels and fillability before paper review."
        ),
        "hardRules": [
            "No paper/live/funding route from this fixture.",
            "A KXFED threshold is not the same contract as a Polymarket bps-change bracket.",
            "The prior upper bound must come from an explicit official/source artifact, not price inference.",
            "Plus buckets remain ambiguous unless the threshold truth is one-sided for the whole bucket.",
        ],
    }


def render_markdown(payload: dict[str, Any]) -> str:
    generated_date = str(payload.get("generatedAt") or current_utc_date())[:10]
    lines = [
        f"# Prediction Macro/Rates Parser Fixture - {generated_date}",
        "",
        "Parent hub: [[BILL-CONTROL-HUB]]",
        "",
        "Research-only Fed/Kalshi parser fixture. This page does not approve paper or live trading.",
        "",
        "## Summary",
        "",
        f"- Decision: `{payload.get('decision')}`",
        f"- Polymarket Fed brackets: `{payload.get('polymarketFedDecisionCount')}`",
        f"- Kalshi KXFED thresholds: `{payload.get('kalshiKxfedThresholdCount')}`",
        f"- Same-meeting pairs: `{payload.get('sameMeetingPairCount')}`",
        f"- Comparable pairs: `{payload.get('comparablePairCount')}`",
        f"- Prior upper bound: `{payload.get('priorUpperBound')}` from `{payload.get('priorUpperBoundSource')}`",
        f"- Blockers: `{payload.get('blockers')}`",
        "",
        "## Next Action",
        "",
        payload.get("nextAction", ""),
        "",
        "## Hard Rules",
        "",
    ]
    for rule in payload.get("hardRules") or []:
        lines.append(f"- {rule}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a research-only Fed/Kalshi parser fixture.")
    parser.add_argument("--macro-snapshot", default=str(MACRO_SNAPSHOT))
    parser.add_argument("--kalshi-fillability", default=str(KALSHI_FILLABILITY))
    parser.add_argument("--output", default=str(OUT))
    parser.add_argument("--markdown", default=str(default_markdown_path()))
    parser.add_argument("--prior-upper-bound", default=os.environ.get("BILL_FED_PRIOR_UPPER_BOUND"))
    parser.add_argument("--prior-source", default=os.environ.get("BILL_FED_PRIOR_UPPER_BOUND_SOURCE", "manual-unset"))
    parser.add_argument("--fed-prior-source", default=str(FED_PRIOR_SOURCE))
    args = parser.parse_args()
    snapshot = read_json(Path(args.macro_snapshot), [])
    prior_upper_bound, prior_source = resolve_prior(
        explicit_prior=args.prior_upper_bound,
        explicit_source=args.prior_source,
        source_artifact=Path(args.fed_prior_source),
    )
    payload = build_fixture(
        macro_snapshot=snapshot if isinstance(snapshot, list) else [],
        kalshi_fillability=read_json(Path(args.kalshi_fillability), {}),
        prior_upper_bound=prior_upper_bound,
        prior_source=prior_source,
    )
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
