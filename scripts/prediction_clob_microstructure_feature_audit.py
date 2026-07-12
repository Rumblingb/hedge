#!/usr/bin/env python3
"""Audit CLOB microstructure feature readiness for prediction markets.

This is not an edge gate. It tells the research loop which new feature family
is actually testable from local CLOB captures and the cataloged microstructure
repo, while keeping the rejected drift/persistence threshold memory intact.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
CLOB_DIR = ROOT / ".rumbling-hedge" / "prediction" / "clob"
DEFAULT_JSONL = CLOB_DIR / f"{datetime.now(timezone.utc).date().isoformat()}-market-channel.jsonl"
DEFAULT_PERSISTENCE = STATE / "polymarket-clob-persistence.latest.json"
DEFAULT_EDGE_GATE = STATE / "polymarket-clob-edge-gate.latest.json"
DEFAULT_NO_EDGE_LEDGER = ROOT / ".rumbling-hedge" / "research" / "prediction-no-edge-ledger" / "latest.json"
DEFAULT_REPO = Path("/Volumes/Seagate Expansion Drive/hedge-data/external-alpha-2026-05-25/github/polymarket-microstructure")
OUT = STATE / "prediction-clob-microstructure-feature-audit.latest.json"
VAULT = Path.home() / "Documents/memorybrain"
OUT_MD = VAULT / "Agent-Hermes" / "prediction-clob-microstructure-feature-audit-2026-05-30.md"


FEATURE_NO_EDGE_IDS = {
    "clob-depth-imbalance-persistence": "polymarket-clob-depth-imbalance-current-form",
    "clob-quote-update-intensity": "polymarket-clob-quote-intensity-current-form",
    "clob-spread-compression-before-move": "polymarket-clob-spread-compression-current-form",
    "clob-latency-staleness": "polymarket-clob-latency-staleness-current-form",
    "clob-trade-impact": "polymarket-clob-trade-impact-current-form",
    "clob-resolved-label-resting-convergence": "polymarket-clob-resolved-label-pre-resolution-resting-convergence-current-form",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def to_float(value: Any) -> float | None:
    try:
        out = float(value)
        return out if math.isfinite(out) else None
    except Exception:
        return None


def read_jsonl(path: Path, max_rows: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        with path.open() as handle:
            for line in handle:
                if len(rows) >= max_rows:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                    if isinstance(item, dict):
                        rows.append(item)
                except Exception:
                    rows.append({"eventType": "parse_error"})
    except FileNotFoundError:
        return []
    return rows


def level_count(record: dict[str, Any], side: str) -> int:
    levels = record.get(side)
    return len(levels) if isinstance(levels, list) else 0


def summarize_capture(rows: list[dict[str, Any]]) -> dict[str, Any]:
    event_counts = Counter(str(row.get("eventType") or row.get("event_type") or "missing") for row in rows)
    assets = Counter(str(row.get("assetId") or row.get("asset_id") or "missing") for row in rows)
    book_rows = [row for row in rows if str(row.get("eventType") or row.get("event_type")) == "book"]
    bba_rows = [row for row in rows if str(row.get("eventType") or row.get("event_type")) == "best_bid_ask"]
    price_change_rows = [row for row in rows if str(row.get("eventType") or row.get("event_type")) == "price_change"]
    trade_rows = [row for row in rows if str(row.get("eventType") or row.get("event_type")) == "last_trade_price"]
    spreads = []
    for row in bba_rows:
        bid = to_float(row.get("bestBid") or row.get("best_bid"))
        ask = to_float(row.get("bestAsk") or row.get("best_ask"))
        if bid is not None and ask is not None and ask >= bid:
            spreads.append(ask - bid)
    avg_book_levels = None
    if book_rows:
        avg_book_levels = round(
            sum(level_count(row, "bids") + level_count(row, "asks") for row in book_rows) / len(book_rows),
            4,
        )
    return {
        "recordsRead": len(rows),
        "eventCounts": dict(event_counts.most_common()),
        "assetsObserved": len([asset for asset in assets if asset != "missing"]),
        "topAssets": dict(assets.most_common(10)),
        "bookEvents": len(book_rows),
        "bestBidAskEvents": len(bba_rows),
        "priceChangeEvents": len(price_change_rows),
        "lastTradeEvents": len(trade_rows),
        "avgBookLevels": avg_book_levels,
        "medianObservedSpread": round(sorted(spreads)[len(spreads) // 2], 6) if spreads else None,
    }


def repo_feature_inventory(repo: Path) -> list[dict[str, Any]]:
    feature_dirs = [
        repo / "polydata" / "measures",
        repo / "data" / "panel_quote",
        repo / "artifacts",
    ]
    out: list[dict[str, Any]] = []
    for folder in feature_dirs:
        if not folder.exists():
            continue
        for path in sorted(folder.iterdir()):
            if path.is_file() and path.suffix in {".py", ".parquet", ".csv", ".txt"}:
                out.append({
                    "name": path.stem,
                    "path": str(path),
                    "kind": path.suffix.lstrip("."),
                    "sizeBytes": path.stat().st_size,
                })
    return out


def rejected_feature_forms(no_edge_ledger: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    entries = no_edge_ledger.get("entries") if isinstance(no_edge_ledger.get("entries"), list) else []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        entry_id = str(entry.get("id") or "")
        if not entry_id:
            continue
        if entry.get("verdict") == "no-edge" and entry.get("currentFormRejected") is True:
            out[entry_id] = entry
    return out


def feature_candidates(
    capture: dict[str, Any],
    repo_features: list[dict[str, Any]],
    edge_gate: dict[str, Any],
    no_edge_ledger: dict[str, Any],
) -> list[dict[str, Any]]:
    names = {str(item.get("name")) for item in repo_features}
    rejected_thresholds = edge_gate.get("thresholds") if isinstance(edge_gate.get("thresholds"), dict) else {}
    rejected_forms = rejected_feature_forms(no_edge_ledger)
    candidates = [
        {
            "id": "clob-depth-imbalance-persistence",
            "oneVariable": "book depth imbalance",
            "readyForOfflineResearch": capture.get("bookEvents", 0) >= 20 and capture.get("avgBookLevels") is not None,
            "sourceEvidence": ["book events with bid/ask levels", "external depth measure"] if "depth" in names else ["book events with bid/ask levels"],
            "promotionGate": "Must beat rejected drift baseline after spread/fee stress and resolved-label join.",
        },
        {
            "id": "clob-quote-update-intensity",
            "oneVariable": "quote update intensity",
            "readyForOfflineResearch": capture.get("priceChangeEvents", 0) + capture.get("bestBidAskEvents", 0) >= 200,
            "sourceEvidence": ["price_change/best_bid_ask events", "external intensity measure"] if "intensity" in names else ["price_change/best_bid_ask events"],
            "promotionGate": "Measure update burst before repricing without lowering drift thresholds.",
        },
        {
            "id": "clob-spread-compression-before-move",
            "oneVariable": "spread compression",
            "readyForOfflineResearch": capture.get("bestBidAskEvents", 0) + capture.get("priceChangeEvents", 0) >= 200,
            "sourceEvidence": ["best_bid_ask/price_change spread series", "external spread measure"] if "spread" in names else ["best_bid_ask/price_change spread series"],
            "promotionGate": "Must show forward repricing edge net of half-spread and fees.",
        },
        {
            "id": "clob-latency-staleness",
            "oneVariable": "quote staleness/latency",
            "readyForOfflineResearch": capture.get("recordsRead", 0) >= 500,
            "sourceEvidence": ["localTs/exchangeTs fields", "external latency measure"] if "latency" in names else ["localTs/exchangeTs fields"],
            "promotionGate": "Can filter markets only if it improves OOS fillability/edge without becoming a stale-price trap.",
        },
        {
            "id": "clob-trade-impact",
            "oneVariable": "last trade impact",
            "readyForOfflineResearch": capture.get("lastTradeEvents", 0) >= 50,
            "sourceEvidence": ["last_trade_price events", "external impact/trades measures"] if {"impact", "trades"} & names else ["last_trade_price events"],
            "promotionGate": "Requires enough real trade events; do not infer trade impact from quote-only data.",
        },
        {
            "id": "clob-resolved-label-resting-convergence",
            "oneVariable": "pre-resolution resting-book convergence vs resolved outcome",
            "readyForOfflineResearch": True,  # tested offline against resolved BTC corpus, not live capture
            "sourceEvidence": ["resolved BTC corpus resting depth + flow imbalance", "avg_spread"],
            "promotionGate": "Pre-resolution (frac<=0.5) resting microstruct must predict the resolved binary outcome under grouped-CV AUC + fixed no-edge contract; the resolution-bar tautology is a negative control, not evidence.",
        },
    ]
    for item in candidates:
        no_edge_id = FEATURE_NO_EDGE_IDS.get(str(item["id"]))
        rejected_entry = rejected_forms.get(no_edge_id or "")
        raw_ready = bool(item["readyForOfflineResearch"])
        item["researchOnly"] = True
        item["writesOrders"] = False
        item["touchesBroker"] = False
        item["rawDataReady"] = raw_ready
        item["noEdgeLedgerId"] = no_edge_id
        # The 5 historical fixed forms are blocked as rejected. The new resolved-label family is a
        # DIFFERENT family: it is flagged currentFixedFormRejected ONLY if a ledger entry with the
        # SAME ledger id was already rejected under this exact family id (it is not, yet).
        item["currentFixedFormRejected"] = (
            bool(rejected_entry) and str(item["id"]) != "clob-resolved-label-resting-convergence"
        )
        item["readyForOfflineResearch"] = raw_ready and not (
            rejected_entry and str(item["id"]) != "clob-resolved-label-resting-convergence"
        )
        item["blockedBy"] = ["polymarket-clob-drift-persistence-current-thresholds"]
        if rejected_entry:
            item["blockedBy"].append(no_edge_id)
            item["rejectedReason"] = rejected_entry.get("nextAction")
        item["rejectedBaselineThresholds"] = rejected_thresholds
    return candidates


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    rows = read_jsonl(Path(args.input), args.max_rows)
    capture = summarize_capture(rows)
    persistence = read_json(Path(args.persistence))
    edge_gate = read_json(Path(args.edge_gate))
    no_edge_ledger = read_json(Path(args.no_edge_ledger))
    repo = Path(args.repo)
    repo_features = repo_feature_inventory(repo)
    candidates = feature_candidates(capture, repo_features, edge_gate, no_edge_ledger)
    ready = [item for item in candidates if item["readyForOfflineResearch"]]
    raw_ready = [item for item in candidates if item["rawDataReady"]]
    rejected = [item for item in candidates if item["currentFixedFormRejected"]]
    if ready:
        decision = "research-only-new-feature-audit"
        next_action = "Run one unrejected ready feature family at a time against resolved labels; keep old drift thresholds as rejected baseline."
    elif rejected and raw_ready:
        decision = "research-only-current-fixed-features-exhausted"
        next_action = "Do not rerun rejected fixed forms. Continue only with longer fillable CLOB capture, resolved-outcome label joins, or a genuinely new feature family from the repo."
    else:
        decision = "collect-more-clob-data-before-feature-test"
        next_action = "Run the read-only CLOB recorder longer before testing new microstructure features."
    return {
        "command": "prediction-clob-microstructure-feature-audit",
        "generatedAt": now_iso(),
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "readyForPaper": False,
        "inputPath": str(Path(args.input).resolve()),
        "repoPath": str(repo),
        "capture": capture,
        "persistenceSummary": {
            "present": bool(persistence),
            "quoteObservations": persistence.get("quoteObservations"),
            "assetsEligible": persistence.get("assetsEligible"),
            "decision": persistence.get("decision"),
        },
        "rejectedBaseline": {
            "present": bool(edge_gate),
            "status": edge_gate.get("status"),
            "watchResearchGroups": edge_gate.get("watchResearchGroups"),
            "blockerCounts": edge_gate.get("blockerCounts", {}),
        },
        "repoFeatureCount": len(repo_features),
        "repoFeatureSamples": repo_features[:30],
        "featureCandidates": candidates,
        "rawDataReadyFeatureCount": len(raw_ready),
        "readyFeatureCount": len(ready),
        "rejectedFixedFeatureCount": len(rejected),
        "noEdgeLedger": {
            "present": bool(no_edge_ledger),
            "count": no_edge_ledger.get("count"),
            "noEdgeCount": no_edge_ledger.get("noEdgeCount"),
            "promotableCount": no_edge_ledger.get("promotableCount"),
        },
        "decision": decision,
        "nextAction": next_action,
    }


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Prediction CLOB Microstructure Feature Audit - 2026-05-30",
        "",
        "Parent hub: [[BILL-CONTROL-HUB]]",
        "",
        "Research-only audit for new CLOB feature families. This does not approve paper or live trading.",
        "",
        "## Summary",
        "",
        f"- Decision: `{payload.get('decision')}`",
        f"- Ready feature count: `{payload.get('readyFeatureCount')}`",
        f"- Raw-data-ready feature count: `{payload.get('rawDataReadyFeatureCount')}`",
        f"- Rejected fixed feature count: `{payload.get('rejectedFixedFeatureCount')}`",
        f"- Rejected baseline: `{payload.get('rejectedBaseline', {}).get('status')}`",
        f"- Capture records: `{payload.get('capture', {}).get('recordsRead')}`",
        f"- Event counts: `{payload.get('capture', {}).get('eventCounts')}`",
        f"- Repo feature count: `{payload.get('repoFeatureCount')}`",
        "",
        "## Feature Candidates",
        "",
    ]
    for item in payload.get("featureCandidates") or []:
        lines.extend([
            f"### {item.get('id')}",
            "",
            f"- One variable: `{item.get('oneVariable')}`",
            f"- Raw data ready: `{item.get('rawDataReady')}`",
            f"- Ready for unrejected offline research: `{item.get('readyForOfflineResearch')}`",
            f"- Current fixed form rejected: `{item.get('currentFixedFormRejected')}`",
            f"- Source evidence: `{item.get('sourceEvidence')}`",
            f"- Promotion gate: {item.get('promotionGate')}",
            "",
        ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit prediction-market CLOB microstructure feature readiness.")
    parser.add_argument("--input", default=str(DEFAULT_JSONL))
    parser.add_argument("--persistence", default=str(DEFAULT_PERSISTENCE))
    parser.add_argument("--edge-gate", default=str(DEFAULT_EDGE_GATE))
    parser.add_argument("--no-edge-ledger", default=str(DEFAULT_NO_EDGE_LEDGER))
    parser.add_argument("--repo", default=str(DEFAULT_REPO))
    parser.add_argument("--output", default=str(OUT))
    parser.add_argument("--markdown-output", default=str(OUT_MD))
    parser.add_argument("--max-rows", type=int, default=250_000)
    args = parser.parse_args()
    payload = build_report(args)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    md = Path(args.markdown_output)
    md.parent.mkdir(parents=True, exist_ok=True)
    md.write_text(render_markdown(payload))
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
