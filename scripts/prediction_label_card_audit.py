#!/usr/bin/env python3
"""Audit Obsidian prediction-market resolved-label cards.

Research-only. This lets Obsidian act as the human label-entry surface while a
deterministic script checks whether settlement rows are complete enough to use
as research evidence later.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
VAULT = Path.home() / "Documents" / "memorybrain"
HERMES = VAULT / "Agent-Hermes"
CARD_ROOT = VAULT / "Research-Catalog" / "prediction-label-cards"
EVENT_GAP_PLAN = STATE / "prediction-event-label-gap-plan.latest.json"
OUT = STATE / "prediction-label-card-audit.latest.json"

REQUIRED_FIELDS = [
    "venue",
    "externalId",
    "question",
    "closeTime",
    "settlementSourceUrl",
    "outcomeLabel",
    "outcomeWon",
    "marketType",
    "subjectKey",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def current_utc_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def default_markdown_path() -> Path:
    return HERMES / f"prediction-label-card-audit-{current_utc_date()}.md"


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def normalize_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def split_table_row(line: str) -> list[str]:
    stripped = line.strip().strip("|")
    return [cell.strip().strip("`") for cell in stripped.split("|")]


def is_separator(line: str) -> bool:
    cells = split_table_row(line)
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell.strip()) for cell in cells)


def extract_status(text: str) -> str:
    match = re.search(r"^Status:\s*`?([^`\n]+)`?", text, flags=re.MULTILINE)
    return match.group(1).strip() if match else "missing"


def extract_label_rows(text: str) -> tuple[bool, list[dict[str, str]]]:
    lines = text.splitlines()
    wanted = {normalize_header(field): field for field in REQUIRED_FIELDS}
    for idx, line in enumerate(lines):
        if not line.lstrip().startswith("|"):
            continue
        headers = split_table_row(line)
        normalized = [normalize_header(header) for header in headers]
        if not all(field in normalized for field in wanted):
            continue
        if idx + 1 >= len(lines) or not is_separator(lines[idx + 1]):
            continue
        field_by_index = {
            col_idx: wanted[header]
            for col_idx, header in enumerate(normalized)
            if header in wanted
        }
        rows: list[dict[str, str]] = []
        for raw in lines[idx + 2 :]:
            if not raw.lstrip().startswith("|"):
                break
            cells = split_table_row(raw)
            row = {
                field: cells[col_idx].strip() if col_idx < len(cells) else ""
                for col_idx, field in field_by_index.items()
            }
            rows.append(row)
        return True, rows
    return False, []


def missing_fields(row: dict[str, str]) -> list[str]:
    missing = []
    for field in REQUIRED_FIELDS:
        value = str(row.get(field) or "").strip()
        if not value:
            missing.append(field)
    outcome = str(row.get("outcomeWon") or "").strip().lower()
    if outcome and outcome not in {"true", "false"}:
        missing.append("outcomeWon:boolean")
    if str(row.get("outcomeLabel") or "").strip().lower() in {"yes/no", "true/false"}:
        missing.append("outcomeLabel:concrete")
    return missing


def audit_card(path: Path) -> dict[str, Any]:
    text = path.read_text(errors="ignore")
    section_present, rows = extract_label_rows(text)
    audited_rows = []
    valid_count = 0
    incomplete_count = 0
    for idx, row in enumerate(rows, start=1):
        missing = missing_fields(row)
        is_template = bool(
            not row.get("venue")
            and not row.get("externalId")
            and str(row.get("subjectKey") or "").strip()
        )
        valid = not missing and not is_template
        if valid:
            valid_count += 1
        else:
            incomplete_count += 1
        audited_rows.append({
            "rowNumber": idx,
            "valid": valid,
            "templateLike": is_template,
            "missingFields": missing,
            "venue": row.get("venue"),
            "externalId": row.get("externalId"),
            "question": row.get("question"),
            "marketType": row.get("marketType"),
            "subjectKey": row.get("subjectKey"),
        })
    return {
        "path": str(path),
        "name": path.name,
        "status": extract_status(text),
        "sectionPresent": section_present,
        "rowCount": len(rows),
        "validResolvedLabelRows": valid_count,
        "incompleteRows": incomplete_count,
        "rows": audited_rows,
        "blockers": card_blockers(section_present, valid_count, incomplete_count),
    }


def card_blockers(section_present: bool, valid_count: int, incomplete_count: int) -> list[str]:
    blockers: list[str] = []
    if not section_present:
        blockers.append("required-label-table-missing")
    if valid_count == 0:
        blockers.append("no-valid-resolved-label-rows")
    if incomplete_count:
        blockers.append("incomplete-or-template-label-rows-present")
    return blockers


def expected_card_paths(event_gap_plan: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    for item in event_gap_plan.get("gapItems") or []:
        if not isinstance(item, dict):
            continue
        plan = item.get("collectionPlan") if isinstance(item.get("collectionPlan"), dict) else {}
        card = plan.get("manualSettlementCard")
        if isinstance(card, str) and card and card not in paths:
            paths.append(card)
    return paths


def build_audit(*, card_root: Path = CARD_ROOT, event_gap_plan: dict[str, Any] | None = None) -> dict[str, Any]:
    event_gap_plan = event_gap_plan or {}
    cards = [audit_card(path) for path in sorted(card_root.glob("*.md"))] if card_root.exists() else []
    expected = expected_card_paths(event_gap_plan)
    existing = {str(Path(card["path"]).resolve()) for card in cards}
    missing_expected = [
        path
        for path in expected
        if str(Path(path).resolve()) not in existing
    ]
    valid_total = sum(int(card.get("validResolvedLabelRows") or 0) for card in cards)
    incomplete_total = sum(int(card.get("incompleteRows") or 0) for card in cards)
    status_counts = Counter(str(card.get("status") or "missing") for card in cards)
    blockers: list[str] = []
    if missing_expected:
        blockers.append("expected-settlement-card-missing")
    if valid_total == 0:
        blockers.append("no-valid-label-card-rows")
    if incomplete_total:
        blockers.append("incomplete-label-card-rows")
    return {
        "command": "prediction-label-card-audit",
        "generatedAt": now_iso(),
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "readyForPaper": False,
        "readyForExecution": False,
        "cardRoot": str(card_root),
        "expectedSettlementCards": expected,
        "missingExpectedCards": missing_expected,
        "cardCount": len(cards),
        "statusCounts": dict(status_counts),
        "validResolvedLabelRows": valid_total,
        "incompleteRows": incomplete_total,
        "cards": cards,
        "blockers": blockers,
        "decision": "research-only-label-cards-not-ready" if blockers else "research-only-label-cards-ready-for-join-intake",
        "nextAction": (
            "Fill required settlement-card rows with concrete resolved markets before rerunning event-lag resolved-label checks."
            if blockers
            else "Convert validated label-card rows into the resolved-label manifest; still no paper/live approval."
        ),
        "hardRules": [
            "A label card row is not usable without settlementSourceUrl and concrete outcomeWon.",
            "Template rows do not count as evidence.",
            "Do not use label cards to approve paper, funding, demo, live, sizing, or broker routing.",
        ],
    }


def render_markdown(payload: dict[str, Any]) -> str:
    generated_date = str(payload.get("generatedAt") or current_utc_date())[:10]
    lines = [
        f"# Prediction Label Card Audit - {generated_date}",
        "",
        "Parent hub: [[BILL-CONTROL-HUB]]",
        "",
        "Research-only audit of Obsidian settlement cards for prediction-market resolved labels.",
        "",
        "## Summary",
        "",
        f"- Decision: `{payload.get('decision')}`",
        f"- Cards: `{payload.get('cardCount')}`",
        f"- Valid resolved label rows: `{payload.get('validResolvedLabelRows')}`",
        f"- Incomplete rows: `{payload.get('incompleteRows')}`",
        f"- Blockers: `{payload.get('blockers')}`",
        "",
        "## Cards",
        "",
    ]
    for card in payload.get("cards") or []:
        lines.extend([
            f"### {card.get('name')}",
            "",
            f"- Path: `{card.get('path')}`",
            f"- Status: `{card.get('status')}`",
            f"- Label table present: `{card.get('sectionPresent')}`",
            f"- Valid rows: `{card.get('validResolvedLabelRows')}`",
            f"- Incomplete rows: `{card.get('incompleteRows')}`",
            f"- Blockers: `{card.get('blockers')}`",
            "",
        ])
    lines.extend(["## Hard Rules", ""])
    for rule in payload.get("hardRules") or []:
        lines.append(f"- {rule}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    payload = build_audit(event_gap_plan=read_json(EVENT_GAP_PLAN))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    markdown = default_markdown_path()
    markdown.parent.mkdir(parents=True, exist_ok=True)
    markdown.write_text(render_markdown(payload))
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
