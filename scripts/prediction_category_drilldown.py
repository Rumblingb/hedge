#!/usr/bin/env python3
"""Research-only prediction-market category drilldown.

This turns the broad scanner's "zero viable pairs" result into a smaller queue
of categories worth retesting. It never writes orders or paper fills.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
RUNTIME = ROOT / ".rumbling-hedge" / "runtime" / "prediction"
DEFAULT_SNAPSHOT = RUNTIME / "combined-live-snapshot.json"
DEFAULT_CYCLE = STATE / "prediction-cycle.latest.json"
DEFAULT_OUT = STATE / "prediction-category-drilldown.latest.json"
DEFAULT_KALSHI_FILLABILITY = STATE / "kalshi-fillability-snapshot.latest.json"
DEFAULT_MD = Path.home() / "Documents/memorybrain/Agent-Hermes/prediction-category-drilldown-2026-05-29.md"
DEFAULT_NARROW_DIR = ROOT / ".rumbling-hedge" / "research" / "prediction-narrow-snapshots"


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def text_of(item: dict[str, Any]) -> str:
    return " ".join(
        str(item.get(key) or "")
        for key in ["eventTitle", "marketQuestion", "settlementText", "outcomeLabel"]
    ).lower()


def category_for_text(text: str) -> str:
    text = text.lower()
    if re.search(r"\b(bitcoin|btc|ethereum|eth|crypto)\b", text):
        return "crypto"
    if re.search(r"\b(cpi|fed|fomc|rates?|interest rates?|inflation|jobs?|unemployment|gdp|recession|pce|treasury|basis points?|bps)\b", text):
        return "macro-rates"
    if re.search(r"\b(world cup|fifa|french open|wimbledon|grand slam|champions league|ucl|nba|nfl|soccer|football|tennis|ufc|mlb|nhl|f1|formula 1|cricket|rugby|boxing|golf|serie a|premier league|la liga|bundesliga|esports|iem|major 2026)\b", text):
        return "sports"
    if any(token in text for token in ["iran", "ukraine", "russia", "china", "ceasefire", "war", "peace", "hormuz", "blockade", "diplomatic"]):
        return "geopolitics"
    if any(token in text for token in ["election", "president", "senate", "congress", "mayor", "governor"]):
        return "politics"
    if any(token in text for token in ["stock", "market cap", "nasdaq", "s&p", "spx", "nvidia", "tesla", "apple", "amazon", "aramco"]):
        return "equities"
    if re.search(r"\b(wti|crude oil|oil|gas price|natural gas|gold|silver|copper|corn|wheat)\b", text):
        return "commodities"
    if re.search(r"\b[a-z][a-z .'-]{2,}\s+vs\.?\s+[a-z][a-z .'-]{2,}\b", text):
        return "sports"
    return "other"


def category_for_market(item: dict[str, Any]) -> str:
    return category_for_text(text_of(item))


def safe_float(value: Any) -> float | None:
    try:
        out = float(value)
        return out if math.isfinite(out) else None
    except Exception:
        return None


def median(values: list[float]) -> float | None:
    return round(statistics.median(values), 6) if values else None


def summarize_snapshot(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_category[category_for_market(row)].append(row)

    categories: dict[str, Any] = {}
    for category, items in sorted(by_category.items()):
        venue_counts = Counter(str(item.get("venue", "missing")) for item in items)
        spreads = [value for item in items if (value := safe_float(item.get("spreadPct"))) is not None]
        displayed_sizes = [value for item in items if (value := safe_float(item.get("displayedSize"))) is not None]
        clob_tokens = sum(1 for item in items if item.get("clobTokenId"))
        categories[category] = {
            "markets": len(items),
            "venueCounts": dict(venue_counts.most_common()),
            "venues": sorted(venue_counts.keys()),
            "crossVenueEligible": len(venue_counts) >= 2,
            "medianSpreadPct": median(spreads),
            "medianDisplayedSize": median(displayed_sizes),
            "clobTokenCount": clob_tokens,
            "sampleQuestions": [str(item.get("marketQuestion") or item.get("eventTitle") or "")[:160] for item in items[:5]],
        }
    return categories


def summarize_near_misses(cycle: dict[str, Any]) -> dict[str, Any]:
    diagnostics = ((cycle.get("scan") or {}).get("diagnostics") or {})
    near_misses = diagnostics.get("topNearMisses") if isinstance(diagnostics.get("topNearMisses"), list) else []
    out: dict[str, Any] = {}
    for item in near_misses:
        category = category_for_text(" ".join([
            str(item.get("eventTitleA") or ""),
            str(item.get("eventTitleB") or ""),
            str(item.get("outcomeA") or ""),
            str(item.get("outcomeB") or ""),
        ]).lower())
        bucket = out.setdefault(category, {
            "nearMissCount": 0,
            "reasonCounts": Counter(),
            "venuePairs": Counter(),
            "bestMatchScore": 0.0,
            "examples": [],
        })
        bucket["nearMissCount"] += 1
        bucket["bestMatchScore"] = max(bucket["bestMatchScore"], safe_float(item.get("matchScore")) or 0.0)
        bucket["venuePairs"][f"{item.get('venueA', 'missing')}->{item.get('venueB', 'missing')}"] += 1
        for reason in item.get("reasons") or []:
            bucket["reasonCounts"][str(reason)] += 1
        if len(bucket["examples"]) < 3:
            bucket["examples"].append({
                "candidateId": item.get("candidateId"),
                "eventTitleA": item.get("eventTitleA"),
                "eventTitleB": item.get("eventTitleB"),
                "matchScore": item.get("matchScore"),
                "reasons": item.get("reasons") or [],
            })

    normalized: dict[str, Any] = {}
    for category, bucket in sorted(out.items()):
        normalized[category] = {
            "nearMissCount": bucket["nearMissCount"],
            "reasonCounts": dict(bucket["reasonCounts"].most_common()),
            "venuePairs": dict(bucket["venuePairs"].most_common()),
            "bestMatchScore": round(bucket["bestMatchScore"], 4),
            "examples": bucket["examples"],
        }
    return normalized


def category_for_kalshi_series(series_ticker: str) -> str:
    series = series_ticker.upper()
    if series in {"KXFED", "KXCPI"}:
        return "macro-rates"
    if series in {"KXBTC", "KXETH"}:
        return "crypto"
    if series in {"KXSPY", "KXNASDAQ100"}:
        return "equities"
    if series in {"KXPRES", "KXHOUSE", "KXSENATE"}:
        return "politics"
    return "other"


def summarize_kalshi_fillability(snapshot: dict[str, Any]) -> dict[str, Any]:
    top = snapshot.get("topExecutable") if isinstance(snapshot.get("topExecutable"), list) else []
    by_category: dict[str, dict[str, Any]] = {}
    for row in top:
        if not isinstance(row, dict) or not row.get("executable"):
            continue
        series = str(row.get("seriesTicker") or row.get("series_ticker") or "")
        category = category_for_kalshi_series(series)
        bucket = by_category.setdefault(category, {
            "executablePublicQuotes": 0,
            "seriesTickers": Counter(),
            "tightCount": 0,
            "usableCount": 0,
            "sampleTickers": [],
        })
        bucket["executablePublicQuotes"] += 1
        if series:
            bucket["seriesTickers"][series] += 1
        if row.get("bucket") == "tight":
            bucket["tightCount"] += 1
        if row.get("bucket") == "usable":
            bucket["usableCount"] += 1
        if len(bucket["sampleTickers"]) < 5:
            bucket["sampleTickers"].append(row.get("ticker"))

    categories: dict[str, Any] = {}
    for category, bucket in sorted(by_category.items()):
        categories[category] = {
            "executablePublicQuotes": bucket["executablePublicQuotes"],
            "seriesTickers": dict(bucket["seriesTickers"].most_common()),
            "tightCount": bucket["tightCount"],
            "usableCount": bucket["usableCount"],
            "sampleTickers": bucket["sampleTickers"],
        }
    return {
        "present": bool(snapshot),
        "generatedAt": snapshot.get("generatedAt"),
        "marketsInspected": snapshot.get("marketsInspected"),
        "executablePublicQuotes": snapshot.get("executablePublicQuotes", 0),
        "bucketCounts": snapshot.get("bucketCounts", {}),
        "categories": categories,
        "researchOnly": snapshot.get("researchOnly", True),
        "writesOrders": snapshot.get("writesOrders", False),
        "readyForPaper": snapshot.get("readyForPaper", False),
    }


def build_next_tests(categories: dict[str, Any], near_misses: dict[str, Any], fillability: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    fillability = fillability or {}
    fillable_categories = fillability.get("categories") if isinstance(fillability.get("categories"), dict) else {}
    domain_priority_bonus = {
        "macro-rates": 70,
        "commodities": 80,
        "crypto": 35,
        "geopolitics": 25,
        "other": -90,
    }
    candidates: list[dict[str, Any]] = []
    for category, summary in categories.items():
        if not summary.get("crossVenueEligible"):
            continue
        reasons = (near_misses.get(category) or {}).get("reasonCounts", {})
        fillable = fillable_categories.get(category) if isinstance(fillable_categories.get(category), dict) else {}
        fillability_bonus = min(120, int(fillable.get("executablePublicQuotes", 0)) * 8)
        if category == "crypto":
            one_variable = "settlement horizon"
            command_hint = "Run a crypto-only scan and separate snapshot-above daily markets from month-end touch/generic markets."
        elif category == "sports":
            one_variable = "market family"
            command_hint = "Run sports outrights only, then require same tournament, same winner entity, and market-specific resolved history."
        elif category == "macro-rates":
            one_variable = "line parser"
            command_hint = "Run CPI/Fed/rates only and normalize numeric lines before comparing venues."
        elif category == "commodities":
            one_variable = "reference market and line parser"
            command_hint = "Run commodities/energy only, then normalize touch-vs-close, contract month, and settlement source before comparing venues."
        else:
            one_variable = "market universe"
            command_hint = f"Run {category}-only scan and inspect whether blockers are semantic, line, or temporal."
        candidates.append({
            "id": f"{category}-narrow-scan",
            "category": category,
            "priorityScore": int(summary.get("markets", 0)) + 20 * len(summary.get("venues", [])) + 5 * len(reasons) + domain_priority_bonus.get(category, 0) + fillability_bonus,
            "oneVariable": one_variable,
            "marketCount": summary.get("markets", 0),
            "venues": summary.get("venues", []),
            "dominantBlockers": list(reasons)[:4],
            "kalshiFillability": fillable,
            "fillabilityGuided": bool(fillable),
            "commandHint": command_hint,
            "promotionRule": "Research-only. Continue only if watch candidates have same settlement horizon, clear wording, acceptable spread, and market-specific resolved outcomes.",
        })
    return sorted(candidates, key=lambda item: item["priorityScore"], reverse=True)[:6]


def write_narrow_snapshots(rows: list[dict[str, Any]], next_tests: list[dict[str, Any]], out_dir: Path) -> list[dict[str, Any]]:
    """Write category-filtered research snapshots for the next scanner loop.

    These files are inputs for research only. They are intentionally just subsets
    of the combined snapshot and do not contain orders, fills, or approvals.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, Any]] = []
    rows_by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        rows_by_category[category_for_market(row)].append(row)

    for test in next_tests:
        category = str(test.get("category") or "")
        if not category:
            continue
        category_rows = rows_by_category.get(category, [])
        snapshot_path = out_dir / f"{category}.json"
        snapshot_path.write_text(json.dumps(category_rows, indent=2, sort_keys=True) + "\n")
        manifest.append({
            "category": category,
            "path": str(snapshot_path),
            "marketCount": len(category_rows),
            "nextTestId": test.get("id"),
            "kalshiFillability": test.get("kalshiFillability", {}),
            "fillabilityGuided": bool(test.get("fillabilityGuided")),
            "researchOnly": True,
            "writesOrders": False,
            "promotionRule": test.get("promotionRule"),
        })

    (out_dir / "manifest.latest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Prediction Category Drilldown - 2026-05-29",
        "",
        "Parent hub: [[BILL-CONTROL-HUB]]",
        "",
        "This is research-only. It writes no orders and cannot approve paper/live execution.",
        "",
        "## Decision",
        "",
        f"- Ready for paper: `{report['readyForPaper']}`",
        f"- Writes orders: `{report['writesOrders']}`",
        f"- Snapshot markets: `{report['snapshotMarketCount']}`",
        f"- Cross-venue pairs: `{report['scanDiagnostics'].get('crossVenuePairs', 'missing')}`",
        f"- Viable pairs: `{report['scanDiagnostics'].get('viablePairs', 'missing')}`",
        "",
        "## Category Coverage",
        "",
        "| Category | Markets | Venues | Median Spread | CLOB Tokens |",
        "|---|---:|---|---:|---:|",
    ]
    for category, summary in report["categories"].items():
        lines.append(
            f"| {category} | {summary['markets']} | {', '.join(summary['venues'])} | {summary['medianSpreadPct']} | {summary['clobTokenCount']} |"
        )
    lines.extend(["", "## Next Narrow Tests", ""])
    for item in report["nextTests"]:
        fillability_note = ""
        if item.get("fillabilityGuided"):
            fillability_note = f" Kalshi executable quotes: `{(item.get('kalshiFillability') or {}).get('executablePublicQuotes', 0)}`."
        lines.append(f"- `{item['id']}`: {item['commandHint']}{fillability_note} Promotion rule: {item['promotionRule']}")
    if report.get("narrowSnapshots"):
        lines.extend(["", "## Narrow Snapshot Inputs", ""])
        for item in report["narrowSnapshots"]:
            lines.append(f"- `{item['category']}`: `{item['path']}` ({item['marketCount']} markets, researchOnly `{item['researchOnly']}`)")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    snapshot = read_json(Path(args.snapshot), [])
    if not isinstance(snapshot, list):
        snapshot = []
    cycle = read_json(Path(args.cycle), {})
    fillability = summarize_kalshi_fillability(read_json(Path(args.kalshi_fillability), {}))
    categories = summarize_snapshot([row for row in snapshot if isinstance(row, dict)])
    near_misses = summarize_near_misses(cycle if isinstance(cycle, dict) else {})
    diagnostics = (((cycle or {}).get("scan") or {}).get("diagnostics") or {}) if isinstance(cycle, dict) else {}
    return {
        "command": "prediction-category-drilldown",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "researchOnly": True,
        "writesOrders": False,
        "readyForPaper": False,
        "snapshotPath": str(Path(args.snapshot).resolve()),
        "cyclePath": str(Path(args.cycle).resolve()),
        "snapshotMarketCount": len(snapshot),
        "scanDiagnostics": {
            "totalMarkets": diagnostics.get("totalMarkets"),
            "crossVenuePairs": diagnostics.get("crossVenuePairs"),
            "viablePairs": diagnostics.get("viablePairs"),
            "rejectReasons": diagnostics.get("rejectReasons", {}),
            "venuePairs": diagnostics.get("venuePairs", {}),
        },
        "categories": categories,
        "nearMisses": near_misses,
        "kalshiFillability": fillability,
        "nextTests": build_next_tests(categories, near_misses, fillability),
        "narrowSnapshots": [],
        "hardRules": [
            "This drilldown is research-only and writes no orders.",
            "Do not lower scan thresholds to manufacture watch or paper candidates.",
            "Prediction paper promotion still requires review.readyForPaper and promotion recommendedStage=paper.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Research-only prediction-market category drilldown.")
    parser.add_argument("--snapshot", default=str(DEFAULT_SNAPSHOT))
    parser.add_argument("--cycle", default=str(DEFAULT_CYCLE))
    parser.add_argument("--kalshi-fillability", default=str(DEFAULT_KALSHI_FILLABILITY))
    parser.add_argument("--output", default=str(DEFAULT_OUT))
    parser.add_argument("--markdown", default=str(DEFAULT_MD))
    parser.add_argument("--narrow-dir", default=str(DEFAULT_NARROW_DIR))
    args = parser.parse_args()
    report = build_report(args)
    snapshot = read_json(Path(args.snapshot), [])
    if not isinstance(snapshot, list):
        snapshot = []
    report["narrowSnapshots"] = write_narrow_snapshots(
        [row for row in snapshot if isinstance(row, dict)],
        report["nextTests"],
        Path(args.narrow_dir),
    )
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    write_markdown(Path(args.markdown), report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
