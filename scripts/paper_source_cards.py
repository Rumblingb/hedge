#!/usr/bin/env python3
"""Build Obsidian source cards for Bill/Hermes paper PDFs.

Research-only. This turns downloaded papers into small, testable source cards
so Hermes can use them as hypothesis seeds without treating a PDF title or
abstract as execution evidence.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
HOME = Path.home()
STATE = ROOT / ".rumbling-hedge" / "state"
VAULT = HOME / "Documents" / "memorybrain"
CATALOG = VAULT / "Research-Catalog"
DEFAULT_OUTPUT = STATE / "paper-source-cards.latest.json"


def current_utc_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def default_markdown_path() -> Path:
    return CATALOG / f"Paper-Source-Cards-{current_utc_date()}.md"


DEFAULT_MARKDOWN = default_markdown_path()


@dataclass(frozen=True)
class PaperSeed:
    path: Path
    source_status: str
    next_action: str


DEFAULT_PAPERS = [
    PaperSeed(
        HOME / "Downloads" / "Lintner_Revisited_Quantitative_Analysis.pdf",
        "candidate",
        "Extract managed-futures/CTA allocation, trend, diversification, and volatility-targeting hypotheses.",
    ),
    PaperSeed(
        HOME / "Downloads" / "ssrn-3325720.pdf",
        "candidate",
        "Map global factor-premium evidence to futures feature families and p-hacking controls.",
    ),
    PaperSeed(
        HOME / "Downloads" / "ssrn-6702398.pdf",
        "candidate-with-caution",
        "Treat multimodal futures/tail-risk claims as feature-taxonomy inspiration until locally reproduced.",
    ),
    PaperSeed(
        HOME / "Downloads" / "Investing in Volatility.pdf",
        "candidate",
        "Convert volatility claims into one risk-overlay variable against no-edge vol-regime memory.",
    ),
    PaperSeed(
        HOME / "Downloads" / "Model Risk.pdf",
        "research-only",
        "Use for governance, stress testing, and model-risk controls, not direct entries.",
    ),
    PaperSeed(
        HOME / "Downloads" / "BB GCC Leader 1.0.pdf",
        "not-bill-alpha",
        "Personal/career document; exclude from Bill/Hermes alpha research.",
    ),
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def compact_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def redact_contact_text(text: str) -> str:
    text = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[redacted-email]", text)
    text = re.sub(r"\b(?:\+?\d[\d\s().-]{7,}\d)\b", "[redacted-phone]", text)
    return text


def extract_text(reader: Any, max_pages: int) -> str:
    chunks: list[str] = []
    for page in list(getattr(reader, "pages", []))[:max_pages]:
        try:
            chunks.append(page.extract_text() or "")
        except Exception:
            continue
    return compact_whitespace("\n".join(chunks))


def load_pdf(path: Path, max_pages: int, reader_factory: Callable[[str], Any] | None = None) -> dict[str, Any]:
    if not path.exists():
        return {
            "path": str(path),
            "exists": False,
            "pages": 0,
            "metadataTitle": None,
            "metadataAuthor": None,
            "textSample": "",
            "error": "missing",
        }

    try:
        if reader_factory is None:
            from pypdf import PdfReader

            reader_factory = PdfReader
        reader = reader_factory(str(path))
        metadata = getattr(reader, "metadata", None) or {}
        pages = len(getattr(reader, "pages", []))
        return {
            "path": str(path),
            "exists": True,
            "pages": pages,
            "metadataTitle": metadata.get("/Title"),
            "metadataAuthor": metadata.get("/Author"),
            "textSample": extract_text(reader, max_pages),
            "error": None,
        }
    except Exception as exc:
        return {
            "path": str(path),
            "exists": True,
            "pages": 0,
            "metadataTitle": None,
            "metadataAuthor": None,
            "textSample": "",
            "error": f"{type(exc).__name__}: {exc}",
        }


def infer_card(seed: PaperSeed, pdf: dict[str, Any]) -> dict[str, Any]:
    path = seed.path
    name = path.name
    title = str(pdf.get("metadataTitle") or name)
    hay = f"{name} {title} {pdf.get('metadataAuthor') or ''} {pdf.get('textSample') or ''}".lower()

    if "bb gcc leader" in hay or "baskaran balasubramanian" in hay:
        return {
            "decision": "not-bill-alpha",
            "lane": "exclude",
            "tradableVariable": "none",
            "oneVariableTest": "Do not test; personal/career document is outside Bill alpha.",
            "requiredData": [],
            "contraryChecks": ["Must not be embedded into alpha memory or strategy prompts."],
            "statusReason": "personal document, not financial-market research",
        }
    if "model risk" in hay:
        return {
            "decision": "research-only",
            "lane": "risk-governance",
            "tradableVariable": "none",
            "oneVariableTest": "Translate into model-risk checklist items, not trade rules.",
            "requiredData": ["current gate/audit artifacts", "stress-test outputs"],
            "contraryChecks": ["Governance notes cannot override OOS, broker parity, or data freshness gates."],
            "statusReason": "risk controls only",
        }
    if "multimodal" in hay or "tail risk" in hay or "transformer" in hay:
        return {
            "decision": "candidate-with-caution",
            "lane": "futures",
            "tradableVariable": "tail-risk-aware feature gate",
            "oneVariableTest": "Use one tail-risk feature as a filter on existing NQ session candidates; do not add ML model complexity in the same test.",
            "requiredData": ["timestamp-clean futures bars", "news/sentiment source if used", "purged OOS split"],
            "contraryChecks": [
                "Reject if source timestamps can leak future information.",
                "Reject if paper data or model cannot be reproduced locally.",
                "Reject if realistic execution costs remove the edge.",
            ],
            "statusReason": "ML/multimodal claims need strong leak and reproducibility checks",
        }
    if "volatility" in hay or "derman" in hay:
        return {
            "decision": "candidate",
            "lane": "futures",
            "tradableVariable": "volatility regime overlay",
            "oneVariableTest": "Add exactly one volatility-regime overlay to the current NQ session replay; keep entries/stops/targets fixed.",
            "requiredData": ["NQ OOS bars", "volatility proxy or options/volatility source", "cost/slippage gate"],
            "contraryChecks": [
                "Reject if improvement comes only from blocking most trades.",
                "Reject if it fails no-edge vol-regime memory or reduces OOS sample below contract.",
            ],
            "statusReason": "volatility may be useful as risk overlay, not standalone alpha",
        }
    if "global factor" in hay or "factor premium" in hay:
        return {
            "decision": "candidate",
            "lane": "futures",
            "tradableVariable": "cross-asset factor/regime feature",
            "oneVariableTest": "Test one global factor family as a regime overlay for NQ; do not tune entry parameters.",
            "requiredData": ["cross-asset futures/bond/commodity/currency history", "NQ OOS bars", "p-hacking controls"],
            "contraryChecks": [
                "Reject if effect is broad historical factor lore without current intraday relevance.",
                "Require out-of-sample evidence and multiple-testing discipline.",
            ],
            "statusReason": "factor evidence is useful but must survive local market/timeframe translation",
        }
    if "managed futures" in hay or "lintner" in hay or "cme group" in hay:
        return {
            "decision": "candidate",
            "lane": "futures",
            "tradableVariable": "managed-futures trend/risk allocation feature",
            "oneVariableTest": "Test one CTA-style trend/volatility allocation overlay on NQ session candidates.",
            "requiredData": ["multi-market futures history", "NQ OOS bars", "drawdown/risk metrics"],
            "contraryChecks": [
                "Do not confuse portfolio diversification evidence with intraday entry edge.",
                "Reject if prop-firm drawdown constraints worsen despite better average return.",
            ],
            "statusReason": "portfolio/risk overlay seed, not direct Topstep entry rule",
        }

    return {
        "decision": seed.source_status,
        "lane": "research",
        "tradableVariable": "unknown",
        "oneVariableTest": "Extract thesis and define one mechanical variable before coding.",
        "requiredData": [],
        "contraryChecks": ["Do not promote without local reproducible evidence."],
        "statusReason": "needs manual thesis extraction",
    }


def source_id(path: Path) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", path.stem.lower()).strip("-")
    return slug or "paper"


def build_report(
    seeds: list[PaperSeed] | None = None,
    max_pages: int = 3,
    reader_factory: Callable[[str], Any] | None = None,
) -> dict[str, Any]:
    seeds = seeds or DEFAULT_PAPERS
    cards: list[dict[str, Any]] = []
    for seed in seeds:
        pdf = load_pdf(seed.path, max_pages=max_pages, reader_factory=reader_factory)
        inferred = infer_card(seed, pdf)
        text_sample = redact_contact_text(pdf["textSample"])[:360]
        if inferred["decision"] == "not-bill-alpha":
            text_sample = "[redacted: excluded non-alpha document]"
        cards.append({
            "id": source_id(seed.path),
            "path": str(seed.path),
            "exists": pdf["exists"],
            "pages": pdf["pages"],
            "metadataTitle": pdf["metadataTitle"],
            "metadataAuthor": pdf["metadataAuthor"],
            "textSample": text_sample,
            "sourceStatus": seed.source_status,
            "nextAction": seed.next_action,
            **inferred,
        })

    decision_counts: dict[str, int] = {}
    lane_counts: dict[str, int] = {}
    missing = 0
    for card in cards:
        decision_counts[card["decision"]] = decision_counts.get(card["decision"], 0) + 1
        lane_counts[card["lane"]] = lane_counts.get(card["lane"], 0) + 1
        if not card["exists"]:
            missing += 1

    return {
        "command": "paper-source-cards",
        "generatedAt": now_iso(),
        "researchOnly": True,
        "readyForExecution": False,
        "readyForDemoExpansion": False,
        "readyForLive": False,
        "writesOrders": False,
        "touchesBroker": False,
        "summary": {
            "paperCount": len(cards),
            "missingCount": missing,
            "decisionCounts": decision_counts,
            "laneCounts": lane_counts,
        },
        "hardRules": [
            "Paper cards are hypothesis seeds only.",
            "No paper can approve Topstep demo, prediction paper, live routing, funding, or sizing.",
            "Every candidate requires a one-variable local test, purged OOS, cost/slippage, no-edge review, and source hygiene before promotion.",
        ],
        "cards": cards,
    }


def write_json(report: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")


def markdown_link(path: str) -> str:
    return f"[{Path(path).name}](<{path}>)"


def render_markdown(report: dict[str, Any]) -> str:
    generated_date = str(report.get("generatedAt") or current_utc_date())[:10]
    lines = [
        f"# Paper Source Cards - {generated_date}",
        "",
        "Parent hub: [[../Agent-Hermes/BILL-CONTROL-HUB]]",
        "",
        "Status: research-only. These papers are hypothesis seeds, not execution evidence.",
        "",
        f"Generated: `{report['generatedAt']}`",
        "",
        "## Summary",
        "",
        f"- Papers: `{report['summary']['paperCount']}`",
        f"- Missing: `{report['summary']['missingCount']}`",
        f"- Decisions: `{report['summary']['decisionCounts']}`",
        f"- Lanes: `{report['summary']['laneCounts']}`",
        "- Ready for execution/demo/live: `false`",
        "",
        "## Cards",
        "",
        "| Paper | Decision | Lane | Tradable Variable | One-Variable Test |",
        "|---|---|---|---|---|",
    ]
    for card in report["cards"]:
        lines.append(
            "| "
            + " | ".join([
                markdown_link(card["path"]),
                f"`{card['decision']}`",
                f"`{card['lane']}`",
                card["tradableVariable"],
                card["oneVariableTest"],
            ])
            + " |"
        )
    lines.extend(["", "## Contrary Checks", ""])
    for card in report["cards"]:
        lines.append(f"### {Path(card['path']).name}")
        lines.append("")
        lines.append(f"- Status reason: {card['statusReason']}")
        lines.append(f"- Required data: `{card['requiredData']}`")
        for check in card["contraryChecks"]:
            lines.append(f"- {check}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_markdown(report: dict[str, Any], markdown_path: Path) -> None:
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(render_markdown(report))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build research-only Bill paper source cards.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))
    parser.add_argument("--max-pages", type=int, default=3)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(max_pages=args.max_pages)
    write_json(report, Path(args.output))
    write_markdown(report, Path(args.markdown))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
