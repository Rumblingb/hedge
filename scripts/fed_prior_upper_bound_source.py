#!/usr/bin/env python3
"""Fetch the official Fed target-range upper bound for macro-rate research.

The prediction macro/rates parser needs a prior upper-bound value before it can
compare Polymarket bps-change buckets with Kalshi KXFED threshold contracts.
This script obtains that value from the Federal Reserve Open Market Operations
table and writes a research-only artifact. It never touches broker or order
state.
"""

from __future__ import annotations

import argparse
import json
import re
import urllib.request
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge/state"
OUT = STATE / "fed-prior-upper-bound-source.latest.json"
VAULT = Path.home() / "Documents/memorybrain"
OUT_MD = VAULT / "Agent-Hermes" / "fed-prior-upper-bound-source-2026-05-30.md"
FED_OPENMARKET_URL = "https://www.federalreserve.gov/monetarypolicy/openmarket.htm"

MONTHS: dict[str, int] = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


@dataclass(frozen=True)
class FedTargetRangeRow:
    effectiveDate: str
    increaseBps: int | None
    decreaseBps: int | None
    lowerBound: float
    upperBound: float
    levelText: str
    sourceYear: int


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_int(value: str) -> int | None:
    cleaned = re.sub(r"[^\d-]", "", value)
    if not cleaned:
        return None
    try:
        return int(cleaned)
    except ValueError:
        return None


def parse_level_range(value: str) -> tuple[float, float] | None:
    cleaned = (
        value.replace("\u2011", "-")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\xa0", " ")
        .strip()
    )
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:-|to)\s*(\d+(?:\.\d+)?)", cleaned)
    if not match:
        return None
    lower = float(match.group(1))
    upper = float(match.group(2))
    if not (0 <= lower <= upper <= 10):
        return None
    return lower, upper


def parse_effective_date(year: int, text: str) -> str | None:
    match = re.search(r"\b(" + "|".join(MONTHS) + r")\s+(\d{1,2})\b", text.lower())
    if not match:
        return None
    month = MONTHS[match.group(1)]
    day = int(match.group(2))
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


class FedOpenMarketParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.current_year: int | None = None
        self._h4_depth = 0
        self._h4_text: list[str] = []
        self._cell_depth = 0
        self._cell_text: list[str] = []
        self._row: list[str] | None = None
        self.rows: list[FedTargetRangeRow] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "h4":
            self._h4_depth += 1
            self._h4_text = []
        elif tag == "tr":
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell_depth += 1
            self._cell_text = []

    def handle_data(self, data: str) -> None:
        if self._h4_depth:
            self._h4_text.append(data)
        if self._cell_depth:
            self._cell_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "h4" and self._h4_depth:
            self._h4_depth -= 1
            text = normalize_space(" ".join(self._h4_text))
            if re.fullmatch(r"20\d{2}", text):
                self.current_year = int(text)
        elif tag in {"td", "th"} and self._cell_depth and self._row is not None:
            self._cell_depth -= 1
            self._row.append(normalize_space(" ".join(self._cell_text)))
        elif tag == "tr" and self._row is not None:
            self._finish_row(self._row)
            self._row = None

    def _finish_row(self, cells: list[str]) -> None:
        if self.current_year is None or len(cells) < 4:
            return
        if cells[0].lower() == "date" or cells[3].lower() == "level (%)":
            return
        effective = parse_effective_date(self.current_year, cells[0])
        level = parse_level_range(cells[3])
        if not effective or level is None:
            return
        lower, upper = level
        self.rows.append(
            FedTargetRangeRow(
                effectiveDate=effective,
                increaseBps=parse_int(cells[1]),
                decreaseBps=parse_int(cells[2]),
                lowerBound=lower,
                upperBound=upper,
                levelText=cells[3],
                sourceYear=self.current_year,
            )
        )


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def parse_openmarket_rows(html: str) -> list[FedTargetRangeRow]:
    parser = FedOpenMarketParser()
    parser.feed(html)
    return sorted(parser.rows, key=lambda row: row.effectiveDate, reverse=True)


def fetch_html(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "accept": "text/html,application/xhtml+xml",
            "user-agent": "bill-hermes-fed-prior-upper-bound/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read().decode("utf-8", errors="replace")


def build_payload(*, rows: list[FedTargetRangeRow], source_url: str, retrieved_at: str | None = None) -> dict[str, Any]:
    retrieved_at = retrieved_at or now_iso()
    latest = rows[0] if rows else None
    blockers: list[str] = []
    if latest is None:
        blockers.append("official-fed-target-range-row-not-found")
    return {
        "command": "fed-prior-upper-bound-source",
        "generatedAt": retrieved_at,
        "source": {
            "name": "Federal Reserve Board - Open Market Operations",
            "url": source_url,
            "retrievedAt": retrieved_at,
        },
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "readyForPaper": False,
        "readyForExecution": False,
        "dataUsable": latest is not None,
        "effectiveDate": latest.effectiveDate if latest else None,
        "priorUpperBound": latest.upperBound if latest else None,
        "priorLowerBound": latest.lowerBound if latest else None,
        "levelText": latest.levelText if latest else None,
        "increaseBps": latest.increaseBps if latest else None,
        "decreaseBps": latest.decreaseBps if latest else None,
        "rowCount": len(rows),
        "latestRows": [asdict(row) for row in rows[:10]],
        "blockers": blockers,
        "decision": (
            "research-only-fed-prior-upper-bound-source-blocked"
            if blockers
            else "research-only-fed-prior-upper-bound-source-ready"
        ),
        "hardRules": [
            "Official source only; never infer the prior upper bound from market prices.",
            "This artifact is parser context, not a trading signal.",
            "No paper/live/funding route from this artifact.",
        ],
    }


def render_markdown(payload: dict[str, Any]) -> str:
    source = payload.get("source") if isinstance(payload.get("source"), dict) else {}
    lines = [
        "# Fed Prior Upper Bound Source - 2026-05-30",
        "",
        "Parent hub: [[BILL-CONTROL-HUB]]",
        "",
        "Research-only official Fed source artifact for prediction macro/rates parsing.",
        "",
        "## Summary",
        "",
        f"- Decision: `{payload.get('decision')}`",
        f"- Data usable: `{payload.get('dataUsable')}`",
        f"- Effective date: `{payload.get('effectiveDate')}`",
        f"- Target range: `{payload.get('levelText')}`",
        f"- Prior upper bound: `{payload.get('priorUpperBound')}`",
        f"- Source: `{source.get('url')}`",
        f"- Retrieved: `{source.get('retrievedAt')}`",
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
    parser = argparse.ArgumentParser(description="Build official Fed prior-upper-bound research artifact.")
    parser.add_argument("--source-url", default=FED_OPENMARKET_URL)
    parser.add_argument("--input-html", default="")
    parser.add_argument("--output", default=str(OUT))
    parser.add_argument("--markdown", default=str(OUT_MD))
    args = parser.parse_args()

    if args.input_html:
        html = Path(args.input_html).read_text()
    else:
        html = fetch_html(args.source_url)

    payload = build_payload(rows=parse_openmarket_rows(html), source_url=args.source_url)
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
