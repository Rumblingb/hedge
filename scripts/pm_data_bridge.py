#!/usr/bin/env python3
"""
Prediction Market Data Bridge
==============================
Connects the Bill/Hedge prediction market scanner output (PAIRED venue format)
to the execution engine (FLAT format).

Source:  hedge/journals/prediction-opportunities.jsonl  (PAIRED format)
Target:  .rumbling-hedge/runtime/prediction/flat-opportunities.json (JSON array)
         .rumbling-hedge/runtime/prediction/opportunities.jsonl     (JSONL for engine)
Summary: .rumbling-hedge/runtime/prediction/flat-summary.json       (top 10)

PAIRED format (scanner output):
  {"candidateId": "...", "eventTitleA": "...", "eventTitleB": "...",
   "grossEdgePct": 86.17, "netEdgePct": 81.67, "recommendedStake": 1,
   "displayedSizeA": 62461, "displayedSizeB": 1941,
   "sizing": {"entryPrice": 0.075, "referencePrice": 0.966, ...}, ...}

FLAT format (execution engine expects):
  {"eventTitle": "...", "price": 0.65, "edge": 0.12,
   "displayedSize": 1000, "externalId": "...", ...}

Mappings:
  eventTitle   = eventTitleA
  price        = (sizing.entryPrice + sizing.referencePrice) / 2
  edge         = netEdgePct / 100
  displayedSize = min(displayedSizeA, displayedSizeB)

Idempotent — safe to run repeatedly.
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent  # /Users/brain/hedge

# Source: scanner output
DEFAULT_SOURCE = REPO_ROOT / "journals" / "prediction-opportunities.jsonl"

# Targets (relative to repo root)
RUNTIME_DIR = REPO_ROOT / ".rumbling-hedge" / "runtime" / "prediction"
FLAT_JSON = RUNTIME_DIR / "flat-opportunities.json"
FLAT_JSONL = RUNTIME_DIR / "opportunities.jsonl"       # what the engine reads
SUMMARY_JSON = RUNTIME_DIR / "flat-summary.json"


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def load_paired_opportunities(path: Path) -> List[dict]:
    """Load PAIRED-format opportunities from a JSONL file."""
    if not path.exists():
        print(f"[bridge] Source not found: {path}", file=sys.stderr)
        return []

    opps = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                opps.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"[bridge] Skipping malformed line: {e}", file=sys.stderr)

    print(f"[bridge] Loaded {len(opps)} paired opportunities from {path}")
    return opps


def deduplicate_by_pair(opps: List[dict]) -> List[dict]:
    """Keep only the best opportunity per candidateId pair (highest netEdgePct)."""
    best: Dict[str, dict] = {}
    for opp in opps:
        cid = opp.get("candidateId", "")
        if not cid:
            continue
        net = opp.get("netEdgePct", -999)
        if cid not in best or net > best[cid].get("netEdgePct", -999):
            best[cid] = opp

    result = list(best.values())
    dropped = len(opps) - len(result)
    if dropped:
        print(f"[bridge] Deduplicated: kept {len(result)}, dropped {dropped} duplicates")
    return result


def map_to_flat(opp: dict) -> dict:
    """Map a single PAIRED-format opportunity to FLAT format."""
    sizing = opp.get("sizing", {})

    entry_price = sizing.get("entryPrice", 0.5)
    reference_price = sizing.get("referencePrice", 0.5)
    price = round((entry_price + reference_price) / 2, 6)

    return {
        "eventTitle": opp.get("eventTitleA", ""),
        "eventTitleB": opp.get("eventTitleB", ""),
        "price": price,
        "edge": round(opp.get("netEdgePct", 0.0) / 100.0, 6),
        "displayedSize": min(
            opp.get("displayedSizeA", 0),
            opp.get("displayedSizeB", 0),
        ),
        "externalId": opp.get("candidateId", ""),
        "venue": opp.get("venueA", ""),
        "venueB": opp.get("venueB", ""),
        "verdict": opp.get("verdict", ""),
        "marketType": opp.get("marketType", ""),
        "entryPrice": entry_price,
        "referencePrice": reference_price,
        "netEdgePct": opp.get("netEdgePct", 0.0),
        "grossEdgePct": opp.get("grossEdgePct", 0.0),
        "recommendedStake": sizing.get("recommendedStake", 0),
        "matchScore": opp.get("matchScore", 0.0),
        "expiryA": opp.get("expiryA", ""),
        "expiryB": opp.get("expiryB", ""),
        "ts": opp.get("ts", ""),
    }


def transform(opps: List[dict]) -> List[dict]:
    """Transform PAIRED opportunities → FLAT opportunities."""
    deduped = deduplicate_by_pair(opps)
    flat = [map_to_flat(o) for o in deduped]
    # Sort by edge descending
    flat.sort(key=lambda o: o["edge"], reverse=True)
    return flat


def build_summary(flat_opps: List[dict], top_n: int = 10) -> dict:
    """Build a summary with top N candidates and stats."""
    top = flat_opps[:top_n]

    edges = [o["edge"] for o in flat_opps]
    positive = [e for e in edges if e > 0]
    paper_trades = [o for o in flat_opps if o.get("verdict") == "paper-trade"]
    watches = [o for o in flat_opps if o.get("verdict") == "watch"]

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_file": str(DEFAULT_SOURCE),
        "total_opportunities": len(flat_opps),
        "positive_edge_count": len(positive),
        "max_edge": round(max(edges), 6) if edges else 0.0,
        "min_edge": round(min(edges), 6) if edges else 0.0,
        "avg_edge": round(sum(edges) / len(edges), 6) if edges else 0.0,
        "paper_trade_count": len(paper_trades),
        "watch_count": len(watches),
        "top_candidates": [
            {
                "rank": i + 1,
                "eventTitle": o["eventTitle"],
                "edge": o["edge"],
                "netEdgePct": o["netEdgePct"],
                "price": o["price"],
                "displayedSize": o["displayedSize"],
                "verdict": o["verdict"],
                "venue": o["venue"],
                "externalId": o["externalId"],
            }
            for i, o in enumerate(top)
        ],
    }


def write_outputs(flat_opps: List[dict], summary: dict):
    """Write all output files: flat JSON, JSONL, and summary."""
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

    # Flat JSON array
    with open(FLAT_JSON, "w") as f:
        json.dump(flat_opps, f, indent=2, default=str)
    print(f"[bridge] Wrote {len(flat_opps)} flat opportunities → {FLAT_JSON}")

    # JSONL for execution engine
    with open(FLAT_JSONL, "w") as f:
        for opp in flat_opps:
            f.write(json.dumps(opp, default=str) + "\n")
    print(f"[bridge] Wrote JSONL stream → {FLAT_JSONL}")

    # Summary
    with open(SUMMARY_JSON, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"[bridge] Wrote summary → {SUMMARY_JSON}")


def print_top(summary: dict, count: int = 10):
    """Print the top candidates to stdout."""
    print(f"\n{'='*70}")
    print(f"  Prediction Market Bridge — Top {count} Candidates by Edge")
    print(f"  Generated: {summary['generated_at']}")
    print(f"  Total: {summary['total_opportunities']} | "
          f"Positive edge: {summary['positive_edge_count']} | "
          f"Paper-trade: {summary['paper_trade_count']} | "
          f"Watch: {summary['watch_count']}")
    print(f"  Edge range: {summary['min_edge']:.4f} – {summary['max_edge']:.4f} "
          f"(avg {summary['avg_edge']:.4f})")
    print(f"{'='*70}")
    print(f"{'#':>3}  {'Edge':>8}  {'Net%':>7}  {'Price':>7}  {'Size':>10}  {'Verdict':>12}  Event")
    print(f"{'-'*3}  {'-'*8}  {'-'*7}  {'-'*7}  {'-'*10}  {'-'*12}  {'-'*40}")

    for c in summary["top_candidates"][:count]:
        title = c["eventTitle"][:70]
        print(f"{c['rank']:>3}  {c['edge']:>8.4f}  {c['netEdgePct']:>6.1f}%  "
              f"{c['price']:>7.4f}  {c['displayedSize']:>10.0f}  "
              f"{c['verdict']:>12}  {title}")

    print(f"{'='*70}\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(source_path: Optional[Path] = None, top_n: int = 10):
    """Run the bridge: load → transform → write → summarize."""
    source = source_path or DEFAULT_SOURCE

    # 1. Load
    paired = load_paired_opportunities(source)
    if not paired:
        print("[bridge] No opportunities found — writing empty outputs.", file=sys.stderr)
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        with open(FLAT_JSON, "w") as f:
            json.dump([], f)
        with open(FLAT_JSONL, "w") as f:
            pass  # empty file
        with open(SUMMARY_JSON, "w") as f:
            json.dump({
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "source_file": str(source),
                "total_opportunities": 0,
                "top_candidates": [],
            }, f, indent=2)
        print("[bridge] Wrote empty outputs.")
        return

    # 2. Transform
    flat = transform(paired)

    # 3. Summarize
    summary = build_summary(flat, top_n=top_n)

    # 4. Write
    write_outputs(flat, summary)

    # 5. Print
    print_top(summary, count=top_n)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Prediction Market Data Bridge — PAIRED → FLAT format"
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=None,
        help=f"Path to paired opportunities JSONL (default: {DEFAULT_SOURCE})",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=10,
        help="Number of top candidates in summary (default: 10)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress printed table output",
    )

    args = parser.parse_args()

    if args.quiet:
        # Redirect print_top output
        run(source_path=args.source, top_n=args.top)
    else:
        run(source_path=args.source, top_n=args.top)
