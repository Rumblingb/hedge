#!/usr/bin/env python3
"""Bootstrap Obsidian prediction label cards from local resolved-market history.

Research-only. This script does not approve paper/live trading; it only extracts
candidate resolved label rows from the local Polymarket archive so a human or a
later deterministic importer has concrete settlement rows to audit.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

STATE = ROOT / ".rumbling-hedge" / "state"
ANALYSIS = ROOT / ".rumbling-hedge" / "research" / "prediction-market-analysis"
DEFAULT_MANIFEST = ANALYSIS / "manifest.json"
OUT = STATE / "prediction-label-card-bootstrap.latest.json"
VAULT = Path.home() / "Documents" / "memorybrain"


EXCLUDED_HINTS = {
    "say",
    "speech",
    "rally",
    "debate",
    "town hall",
    "president of iran",
    "next president",
    "chess",
    "olympiad",
    "campaign",
    "hack",
}

TYPE_PATTERNS: list[tuple[str, tuple[str, ...]]] = [
    ("peace-deal", ("peace deal", "agreement", "ceasefire")),
    ("military-action", ("military action", "military response", "response against iran", "action against iran")),
    ("strike", ("strike", "strikes", "target")),
    ("nuclear", ("nuke", "nuclear")),
    ("oil-linked", ("oil", "gas", "gulf oil")),
    ("regime-leadership", ("supreme leader", "khamenei out")),
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def current_utc_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def default_markdown_path() -> Path:
    return VAULT / "Agent-Hermes" / f"prediction-label-card-bootstrap-{current_utc_date()}.md"


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


def infer_yes_outcome(row: dict[str, Any]) -> bool | None:
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


def classify_market_type(question: str) -> str | None:
    lowered = question.lower()
    if "iran" not in lowered and "iranian" not in lowered:
        return None
    if any(hint in lowered for hint in EXCLUDED_HINTS):
        return None
    for label, patterns in TYPE_PATTERNS:
        if any(pattern in lowered for pattern in patterns):
            return label
    return None


def settlement_url(slug: str | None, external_id: str | None) -> str:
    if slug:
        return f"https://polymarket.com/event/{slug}"
    if external_id:
        return f"https://polymarket.com/market/{external_id}"
    return "https://polymarket.com"


def isoish(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if "+00" in text and "T" not in text:
        return text.replace(" ", "T").replace("+00", "Z")
    return text.replace(" ", "T")


def candidate_from_row(row: dict[str, Any]) -> dict[str, Any] | None:
    question = str(row.get("question") or "").strip()
    market_type = classify_market_type(question)
    if not market_type:
        return None
    outcome = infer_yes_outcome(row)
    if outcome is None:
        return None
    external_id = str(row.get("id") or row.get("externalId") or "").strip()
    slug = str(row.get("slug") or "").strip()
    return {
        "venue": "polymarket",
        "externalId": external_id,
        "question": question,
        "closeTime": isoish(row.get("end_date") or row.get("closeTime")),
        "settlementSourceUrl": settlement_url(slug, external_id),
        "outcomeLabel": "Yes",
        "outcomeWon": bool(outcome),
        "marketType": market_type,
        "subjectKey": "iran",
        "notes": "auto-extracted from local closed Polymarket archive; validate settlement page before promotion",
        "volume": float(row.get("volume") or 0.0),
    }


def dedupe(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    rows: list[dict[str, Any]] = []
    for item in candidates:
        key = str(item.get("externalId") or item.get("question"))
        if key in seen:
            continue
        seen.add(key)
        rows.append(item)
    return rows


def rank_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    type_rank = {
        "peace-deal": 0,
        "military-action": 1,
        "strike": 2,
        "nuclear": 3,
        "oil-linked": 4,
        "regime-leadership": 5,
    }
    return sorted(
        dedupe(candidates),
        key=lambda item: (
            type_rank.get(str(item.get("marketType")), 99),
            -float(item.get("volume") or 0.0),
            str(item.get("closeTime") or ""),
        ),
    )


def load_polymarket_rows(manifest_path: Path, limit: int) -> list[dict[str, Any]]:
    manifest = read_json(manifest_path)
    tables = manifest.get("tables") if isinstance(manifest.get("tables"), dict) else {}
    files = (tables.get("polymarket_markets") or {}).get("sample") or []
    if not files:
        return []
    try:
        import duckdb  # type: ignore
    except Exception:
        return []
    con = duckdb.connect()
    rows = con.execute(
        """
        select
          cast(id as varchar) as id,
          question,
          slug,
          outcomes,
          outcome_prices,
          cast(end_date as varchar) as end_date,
          volume
        from read_parquet(?)
        where closed = true
          and (lower(question) like '%iran%' or lower(question) like '%iranian%')
        order by end_date desc
        limit ?
        """,
        [files, limit],
    ).fetchall()
    cols = ["id", "question", "slug", "outcomes", "outcome_prices", "end_date", "volume"]
    return [dict(zip(cols, row)) for row in rows]


def build_bootstrap(*, manifest_path: Path = DEFAULT_MANIFEST, source_rows: list[dict[str, Any]] | None = None, max_rows: int = 24) -> dict[str, Any]:
    rows = source_rows if source_rows is not None else load_polymarket_rows(manifest_path, limit=500)
    candidates = [item for row in rows if (item := candidate_from_row(row))]
    ranked = rank_candidates(candidates)[:max_rows]
    type_counts: dict[str, int] = {}
    for item in ranked:
        key = str(item.get("marketType") or "unknown")
        type_counts[key] = type_counts.get(key, 0) + 1
    blockers: list[str] = []
    if not ranked:
        blockers.append("no-local-iran-resolved-candidates")
    return {
        "command": "prediction-label-card-bootstrap",
        "generatedAt": now_iso(),
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "readyForPaper": False,
        "readyForExecution": False,
        "manifestPath": str(manifest_path),
        "sourceRowsScanned": len(rows),
        "candidateRows": len(candidates),
        "selectedRows": len(ranked),
        "typeCounts": type_counts,
        "rows": ranked,
        "blockers": blockers,
        "decision": "research-only-label-card-candidates-ready" if ranked else "research-only-label-card-bootstrap-blocked",
        "hardRules": [
            "Rows are candidate settlement evidence only; they do not approve paper/live/funding/routing.",
            "Use Polymarket closed-market pages as settlement references until a stricter official settlement source is attached.",
            "Do not count speech, election-candidate, sports, or broad non-Iran rows as Iran event-lag labels.",
        ],
    }


def table_lines(rows: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for row in rows:
        cells = [
            row.get("venue", ""),
            row.get("externalId", ""),
            str(row.get("question", "")).replace("|", "/"),
            row.get("closeTime", ""),
            row.get("settlementSourceUrl", ""),
            row.get("outcomeLabel", "Yes"),
            str(row.get("outcomeWon")).lower(),
            row.get("marketType", ""),
            row.get("subjectKey", "iran"),
            row.get("notes", ""),
        ]
        lines.append("| " + " | ".join(str(cell) for cell in cells) + " |")
    return lines


def render_markdown(payload: dict[str, Any]) -> str:
    generated_date = str(payload.get("generatedAt") or current_utc_date())[:10]
    lines = [
        f"# Prediction Label Card Bootstrap - {generated_date}",
        "",
        "Parent hub: [[BILL-CONTROL-HUB]]",
        "",
        "Research-only candidate rows mined from local closed Polymarket history.",
        "",
        "## Summary",
        "",
        f"- Decision: `{payload.get('decision')}`",
        f"- Source rows scanned: `{payload.get('sourceRowsScanned')}`",
        f"- Candidate rows: `{payload.get('candidateRows')}`",
        f"- Selected rows: `{payload.get('selectedRows')}`",
        f"- Type counts: `{payload.get('typeCounts')}`",
        f"- Blockers: `{payload.get('blockers')}`",
        "",
        "## Obsidian Rows",
        "",
        "| venue | externalId | question | closeTime | settlementSourceUrl | outcomeLabel | outcomeWon | marketType | subjectKey | notes |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    lines.extend(table_lines(payload.get("rows") or []))
    lines.extend(["", "## Hard Rules", ""])
    for rule in payload.get("hardRules") or []:
        lines.append(f"- {rule}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--max-rows", type=int, default=24)
    parser.add_argument("--json-out", default=str(OUT))
    parser.add_argument("--md-out", default=str(default_markdown_path()))
    args = parser.parse_args()

    payload = build_bootstrap(manifest_path=Path(args.manifest), max_rows=args.max_rows)
    json_out = Path(args.json_out)
    md_out = Path(args.md_out)
    json_out.parent.mkdir(parents=True, exist_ok=True)
    md_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    md_out.write_text(render_markdown(payload))
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
