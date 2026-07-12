#!/usr/bin/env python3
"""Define requirements for macro/rates prediction-market research.

Research-only. The current macro/rates scan found public quotes, but also
showed parser mismatch: Fed decision brackets were being compared to unrelated
CPI threshold contracts. This artifact keeps that from being mistaken for edge.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
RESEARCH = ROOT / ".rumbling-hedge" / "research"
OUT = STATE / "prediction-macro-rates-requirements.latest.json"
VAULT = Path.home() / "Documents/memorybrain"

KALSHI_FILLABILITY = STATE / "kalshi-fillability-snapshot.latest.json"
NARROW_SCAN = STATE / "prediction-narrow-scan-runner.latest.json"
MACRO_SNAPSHOT = RESEARCH / "prediction-narrow-snapshots" / "macro-rates.json"
LABEL_MANIFEST = STATE / "prediction-label-source-manifest.latest.json"
PARSER_FIXTURE = STATE / "prediction-macro-rates-parser-fixture.latest.json"
RESOLVED_LABELS = STATE / "prediction-macro-rates-resolved-labels.latest.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def current_utc_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def default_markdown_path() -> Path:
    return VAULT / "Agent-Hermes" / f"prediction-macro-rates-requirements-{current_utc_date()}.md"


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text())
    except Exception:
        return {} if path.suffix == ".json" else []


def macro_report(narrow_scan: dict[str, Any]) -> dict[str, Any]:
    reports = narrow_scan.get("reports") if isinstance(narrow_scan.get("reports"), list) else []
    for report in reports:
        if isinstance(report, dict) and report.get("category") == "macro-rates":
            return report
    return {}


def top_executable_by_series(fillability: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    top = fillability.get("topExecutable") if isinstance(fillability.get("topExecutable"), list) else []
    for item in top:
        if not isinstance(item, dict):
            continue
        if not item.get("executable"):
            continue
        series = str(item.get("seriesTicker") or "").upper()
        if series:
            counts[series] = counts.get(series, 0) + 1
    return counts


def macro_snapshot_summary(snapshot: list[Any]) -> dict[str, Any]:
    rows = [row for row in snapshot if isinstance(row, dict)]
    settlement_text = "\n".join(str(row.get("settlementText") or "") for row in rows[:20])
    questions = [str(row.get("marketQuestion") or row.get("question") or "") for row in rows]
    fed_decision = [q for q in questions if "fed" in q.lower() and "interest" in q.lower()]
    bps_bracket = [q for q in questions if re.search(r"\b(?:25|50)\+?\s*bps\b", q.lower()) or "no change" in q.lower()]
    macro_like = [q for q in questions if is_macro_rates_question(q)]
    non_macro = [q for q in questions if not is_macro_rates_question(q)]
    return {
        "marketCount": len(rows),
        "fedDecisionQuestionCount": len(fed_decision),
        "bpsBracketQuestionCount": len(bps_bracket),
        "macroLikeQuestionCount": len(macro_like),
        "macroLikeShare": round(len(macro_like) / len(rows), 4) if rows else 0.0,
        "nonMacroSampleQuestions": non_macro[:8],
        "hasFomcCalendarSource": "fomccalendars" in settlement_text.lower(),
        "hasOpenMarketSource": "openmarket" in settlement_text.lower(),
        "sampleQuestions": questions[:8],
    }


def is_macro_rates_question(question: str) -> bool:
    text = question.lower()
    return bool(re.search(
        r"\b(fed|fomc|rates?|interest rates?|cpi|inflation|jobs report|unemployment|treasury|gdp|pce|basis points?|bps)\b",
        text,
    ))


def macro_label_summary(label_manifest: dict[str, Any], resolved_labels: dict[str, Any] | None = None) -> dict[str, Any]:
    resolved_labels = resolved_labels or {}
    items = label_manifest.get("coverage") if isinstance(label_manifest.get("coverage"), list) else []
    if not items:
        items = label_manifest.get("items") if isinstance(label_manifest.get("items"), list) else []
    macro_items = [
        item for item in items
        if isinstance(item, dict) and item.get("category") == "macro-rates"
    ]
    usable = [item for item in macro_items if item.get("status") == "usable-for-research-join"]
    official_count = int(resolved_labels.get("usableForResearchJoinCount") or 0)
    return {
        "manifestUsableForResearchJoinCount": label_manifest.get("usableForResearchJoinCount"),
        "macroItemCount": len(macro_items),
        "macroUsableForResearchJoinCount": len(usable),
        "officialComparableResolvedLabelCount": int(resolved_labels.get("officialComparableCount") or 0),
        "officialAgreementRate": resolved_labels.get("officialAgreementRate"),
        "officialUsableForResearchJoinCount": official_count,
        "resolvedLabelDecision": resolved_labels.get("decision"),
        "resolvedLabelBlockers": resolved_labels.get("blockers", []),
        "statusCounts": label_manifest.get("statusCounts", {}),
    }


def requirement(
    *,
    req_id: str,
    title: str,
    status: str,
    current: dict[str, Any],
    needed: dict[str, Any],
    proof_commands: list[str],
    blocks: list[str],
) -> dict[str, Any]:
    return {
        "id": req_id,
        "title": title,
        "status": status,
        "current": current,
        "needed": needed,
        "proofCommands": proof_commands,
        "blocks": blocks,
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
    }


def build_requirements(
    *,
    fillability: dict[str, Any],
    narrow_scan: dict[str, Any],
    macro_snapshot: list[Any],
    label_manifest: dict[str, Any],
    parser_fixture: dict[str, Any] | None = None,
    resolved_labels: dict[str, Any] | None = None,
) -> dict[str, Any]:
    report = macro_report(narrow_scan)
    diagnostics = report.get("diagnostics") if isinstance(report.get("diagnostics"), dict) else {}
    reject_reasons = diagnostics.get("rejectReasons") if isinstance(diagnostics.get("rejectReasons"), dict) else {}
    venue_pairs = int((diagnostics.get("crossVenuePairs") or 0) if isinstance(diagnostics.get("crossVenuePairs"), int) else 0)
    viable_pairs = int(report.get("viablePairs") or 0)
    series_counts = top_executable_by_series(fillability)
    snapshot_summary = macro_snapshot_summary(macro_snapshot)
    label_summary = macro_label_summary(label_manifest, resolved_labels)
    parser_fixture = parser_fixture or {}
    executable_quotes = int(fillability.get("executablePublicQuotes") or 0)
    bucket_counts = fillability.get("bucketCounts") if isinstance(fillability.get("bucketCounts"), dict) else {}
    tight_usable = int(bucket_counts.get("tight") or 0) + int(bucket_counts.get("usable") or 0)
    parser_mismatch_total = sum(
        int(reject_reasons.get(key) or 0)
        for key in ("market-type-mismatch", "outcome-mismatch", "temporal-mismatch")
    )

    requirements = [
        requirement(
            req_id="public-macro-quotes-fillable-enough-for-research",
            title="Public macro/rates quotes must be observable before parser work",
            status="pass" if executable_quotes > 0 and tight_usable > 0 and (series_counts.get("KXFED", 0) or series_counts.get("KXCPI", 0)) else "blocked",
            current={
                "executablePublicQuotes": executable_quotes,
                "bucketCounts": bucket_counts,
                "topExecutableSeriesCounts": series_counts,
            },
            needed={"minimumExecutablePublicQuotes": 1, "minimumTightOrUsableQuotes": 1, "series": ["KXFED", "KXCPI"]},
            proof_commands=["npm run --silent bill:kalshi-fillability-snapshot", "npm run --silent bill:prediction-macro-rates-requirements"],
            blocks=["macro/rates parser replay", "paper review"],
        ),
        requirement(
            req_id="polymarket-fed-decision-source-card",
            title="Polymarket Fed decision markets need explicit settlement/source cards",
            status=(
                "pass"
                if snapshot_summary["fedDecisionQuestionCount"] > 0
                and snapshot_summary["bpsBracketQuestionCount"] > 0
                and snapshot_summary["hasFomcCalendarSource"]
                and snapshot_summary["hasOpenMarketSource"]
                else "blocked"
            ),
            current=snapshot_summary,
            needed={"officialFomcCalendarUrl": True, "officialOpenMarketUrl": True, "bpsChangeOrNoChangeBrackets": True},
            proof_commands=["npm run --silent bill:prediction-category-drilldown", "npm run --silent bill:prediction-macro-rates-requirements"],
            blocks=["rate-decision parser fixture", "resolved-label card"],
        ),
        requirement(
            req_id="macro-snapshot-category-purity",
            title="Macro/rates snapshot must not be polluted by unrelated political or general markets",
            status="pass" if snapshot_summary["marketCount"] > 0 and float(snapshot_summary["macroLikeShare"]) >= 0.8 else "blocked",
            current={
                "marketCount": snapshot_summary["marketCount"],
                "macroLikeQuestionCount": snapshot_summary["macroLikeQuestionCount"],
                "macroLikeShare": snapshot_summary["macroLikeShare"],
                "nonMacroSampleQuestions": snapshot_summary["nonMacroSampleQuestions"],
            },
            needed={"minimumMacroLikeShare": 0.8, "categoryClassifierNeedsReview": True},
            proof_commands=["npm run --silent bill:prediction-category-drilldown", "npm run --silent bill:prediction-macro-rates-requirements"],
            blocks=["macro/rates scanner training data", "cross-venue pairing"],
        ),
        requirement(
            req_id="source-specific-parser-normalization",
            title="Parser must compare like with like: Fed upper-bound thresholds vs bps-change brackets",
            status=(
                "pass"
                if parser_fixture.get("decision") == "research-only-fed-kalshi-parser-fixture-ready"
                and int(parser_fixture.get("comparablePairCount") or 0) > 0
                else "blocked"
            ),
            current={
                "crossVenuePairs": venue_pairs,
                "viablePairs": viable_pairs,
                "rejectReasons": reject_reasons,
                "parserMismatchTotal": parser_mismatch_total,
                "topNearMisses": (diagnostics.get("topNearMisses") or [])[:5],
                "parserFixtureDecision": parser_fixture.get("decision"),
                "parserFixtureBlockers": parser_fixture.get("blockers", []),
                "parserFixtureComparablePairCount": parser_fixture.get("comparablePairCount"),
            },
            needed={
                "fedUpperBoundThresholdParser": True,
                "polymarketBpsChangeParser": True,
                "exactMeetingDateJoin": True,
                "explicitPriorUpperBoundSource": True,
                "doNotMatchFedDecisionToCpiPrints": True,
            },
            proof_commands=[
                "npm run --silent bill:prediction-narrow-scan",
                "npm run --silent bill:prediction-macro-rates-parser-fixture",
                "npm run --silent bill:prediction-macro-rates-requirements",
            ],
            blocks=["watchlist restoration", "edge estimate", "paper review"],
        ),
        requirement(
            req_id="macro-rates-resolved-label-history",
            title="Macro/rates needs subject-specific resolved labels before paper review",
            status=(
                "pass"
                if int(label_summary["macroUsableForResearchJoinCount"] or 0) >= 3
                or int(label_summary["officialUsableForResearchJoinCount"] or 0) >= 20
                else "blocked"
            ),
            current=label_summary,
            needed={
                "minimumMacroUsableResearchJoins": 3,
                "orMinimumOfficialComparableResolvedLabels": 20,
                "subjectSpecificRateDecisionHistory": True,
            },
            proof_commands=[
                "npm run --silent bill:prediction-label-source-manifest",
                "npm run --silent bill:prediction-resolved-outcome-join",
                "npm run --silent bill:prediction-macro-rates-resolved-labels",
            ],
            blocks=["paper candidate", "expectancy estimate"],
        ),
    ]
    blocked = [item for item in requirements if item["status"] != "pass"]
    return {
        "command": "prediction-macro-rates-requirements",
        "generatedAt": now_iso(),
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "readyForPaper": False,
        "readyForExecution": False,
        "requirements": requirements,
        "passCount": len(requirements) - len(blocked),
        "blockedCount": len(blocked),
        "decision": "research-only-macro-rates-requirements-not-cleared" if blocked else "research-only-macro-rates-requirements-cleared",
        "nextAction": (
            "Build a source-specific Fed/Kalshi parser fixture and resolved label cards; do not rerun broad macro scans as alpha."
            if blocked
            else "Run a source-specific macro/rates replay; still no paper/live route."
        ),
        "hardRules": [
            "No paper/live/funding route from macro/rates parser work.",
            "Do not compare Fed decision brackets to CPI threshold contracts.",
            "All Fed decision joins must use exact FOMC meeting dates and settlement source cards.",
            "Public quote fillability is necessary context, not alpha evidence.",
        ],
    }


def render_markdown(payload: dict[str, Any]) -> str:
    generated_date = str(payload.get("generatedAt") or current_utc_date())[:10]
    lines = [
        f"# Prediction Macro/Rates Requirements - {generated_date}",
        "",
        "Parent hub: [[BILL-CONTROL-HUB]]",
        "",
        "Research-only checklist for macro/rates prediction-market parser work. This page does not approve paper or live trading.",
        "",
        "## Summary",
        "",
        f"- Decision: `{payload.get('decision')}`",
        f"- Passed: `{payload.get('passCount')}`",
        f"- Blocked: `{payload.get('blockedCount')}`",
        "",
        "## Requirements",
        "",
    ]
    for item in payload.get("requirements") or []:
        lines.extend([
            f"### {item.get('id')}",
            "",
            f"- Title: {item.get('title')}",
            f"- Status: `{item.get('status')}`",
            f"- Current: `{item.get('current')}`",
            f"- Needed: `{item.get('needed')}`",
            f"- Blocks: `{item.get('blocks')}`",
            "- Proof commands:",
        ])
        for command in item.get("proofCommands") or []:
            lines.append(f"  - `{command}`")
        lines.append("")
    lines.extend(["## Hard Rules", ""])
    for rule in payload.get("hardRules") or []:
        lines.append(f"- {rule}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    snapshot = read_json(MACRO_SNAPSHOT)
    fillability = read_json(KALSHI_FILLABILITY)
    narrow_scan = read_json(NARROW_SCAN)
    label_manifest = read_json(LABEL_MANIFEST)
    parser_fixture = read_json(PARSER_FIXTURE)
    resolved_labels = read_json(RESOLVED_LABELS)
    payload = build_requirements(
        fillability=fillability if isinstance(fillability, dict) else {},
        narrow_scan=narrow_scan if isinstance(narrow_scan, dict) else {},
        macro_snapshot=snapshot if isinstance(snapshot, list) else [],
        label_manifest=label_manifest if isinstance(label_manifest, dict) else {},
        parser_fixture=parser_fixture if isinstance(parser_fixture, dict) else {},
        resolved_labels=resolved_labels if isinstance(resolved_labels, dict) else {},
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    markdown = default_markdown_path()
    markdown.parent.mkdir(parents=True, exist_ok=True)
    markdown.write_text(render_markdown(payload))
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
