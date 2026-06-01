#!/usr/bin/env python3
"""Research-only calibration gate for current prediction-market snapshots.

This uses compact historical by-price artifacts to screen current Polymarket
and Kalshi rows for rough calibration dislocations. It is intentionally not a
paper/live signal: broad by-price priors are too coarse for execution, but they
can help choose which markets deserve deeper CLOB/resolution research.
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SNAPSHOT = ROOT / ".rumbling-hedge/runtime/prediction/latest-combined-snapshot.json"
DEFAULT_ANALYSIS_DIR = ROOT / ".rumbling-hedge/research/prediction-market-analysis"
DEFAULT_OUTPUT = ROOT / ".rumbling-hedge/state/prediction-calibration-gate.latest.json"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text())


def rows_from_snapshot(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        rows = data.get("markets") or data.get("rows") or []
        return [row for row in rows if isinstance(row, dict)]
    return []


def to_float(value: Any) -> float | None:
    if isinstance(value, (int, float)) and math.isfinite(value):
        return float(value)
    if isinstance(value, str):
        try:
            parsed = float(value)
            return parsed if math.isfinite(parsed) else None
        except ValueError:
            return None
    return None


def price_bucket(price: float) -> int:
    return max(1, min(99, int(round(price * 100))))


def load_calibration_rows(path: Path, min_trades: int) -> dict[int, dict[str, Any]]:
    payload = read_json(path)
    out: dict[int, dict[str, Any]] = {}
    for row in payload.get("rows") or []:
        price = int(row.get("price", -1))
        trades = int(row.get("total_trades", 0) or 0)
        win_rate = to_float(row.get("win_rate"))
        if 1 <= price <= 99 and trades >= min_trades and win_rate is not None and 0 <= win_rate <= 1:
            out[price] = {
                "price": price,
                "totalTrades": trades,
                "winRate": win_rate,
                "winRatePct": row.get("win_rate_pct"),
            }
    return out


def build_candidate(row: dict[str, Any], calibration: dict[int, dict[str, Any]], args) -> dict[str, Any] | None:
    venue = str(row.get("venue") or "").lower()
    if venue not in {"polymarket", "kalshi"}:
        return None
    ask = to_float(row.get("bestAsk"))
    bid = to_float(row.get("bestBid"))
    displayed = to_float(row.get("displayedSize")) or to_float(row.get("topBookDepth")) or 0.0
    if ask is None or bid is None or not (0 < bid <= ask < 1):
        return None
    spread = ask - bid
    bucket = price_bucket(ask)
    prior = calibration.get(bucket)
    if not prior:
        return None
    calibrated = float(prior["winRate"])
    raw_edge = calibrated - ask
    net_edge = raw_edge - float(args.fee_buffer) - spread
    blockers = []
    if displayed < args.min_displayed_size:
        blockers.append("displayed-size-below-threshold")
    if spread > args.max_spread:
        blockers.append("spread-too-wide")
    if net_edge < args.min_net_edge:
        blockers.append("net-edge-below-threshold")
    if prior["totalTrades"] < args.min_calibration_trades:
        blockers.append("calibration-sample-too-thin")
    blockers.append("broad-by-price-prior-only")
    blockers.append("not-joined-to-market-specific-resolution-history")

    return {
        "venue": venue,
        "externalId": row.get("externalId"),
        "clobTokenId": row.get("clobTokenId"),
        "question": row.get("marketQuestion") or row.get("eventTitle"),
        "outcomeLabel": row.get("outcomeLabel"),
        "expiry": row.get("expiry"),
        "bucket": bucket,
        "bestBid": round(bid, 6),
        "bestAsk": round(ask, 6),
        "spread": round(spread, 6),
        "displayedSize": round(displayed, 4),
        "calibratedWinRate": round(calibrated, 6),
        "calibrationTrades": prior["totalTrades"],
        "rawEdge": round(raw_edge, 6),
        "netEdgeAfterBufferAndSpread": round(net_edge, 6),
        "verdict": "watch-research" if len(blockers) == 2 else "reject",
        "blockers": blockers,
    }


def run(args) -> dict[str, Any]:
    snapshot_rows = rows_from_snapshot(read_json(Path(args.snapshot)))
    analysis_dir = Path(args.analysis_dir)
    calibrations = {
        "polymarket": load_calibration_rows(analysis_dir / "polymarket-win-rate-by-price.json", args.min_calibration_trades),
        "kalshi": load_calibration_rows(analysis_dir / "kalshi-win-rate-by-price.json", args.min_calibration_trades),
    }

    candidates = []
    for row in snapshot_rows:
        venue = str(row.get("venue") or "").lower()
        candidate = build_candidate(row, calibrations.get(venue, {}), args)
        if candidate:
            candidates.append(candidate)
    candidates.sort(key=lambda item: (
        item["verdict"] == "watch-research",
        item["netEdgeAfterBufferAndSpread"],
        item["displayedSize"],
    ), reverse=True)
    watch = [item for item in candidates if item["verdict"] == "watch-research"]
    blocker_counts: dict[str, int] = {}
    for candidate in candidates:
        for blocker in candidate["blockers"]:
            blocker_counts[blocker] = blocker_counts.get(blocker, 0) + 1

    status = "WATCH_RESEARCH_ONLY" if watch else "REJECT_NO_CALIBRATED_EDGE"
    return {
        "command": "prediction-market-calibration-gate",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "researchOnly": True,
        "writesOrders": False,
        "readyForPaper": False,
        "snapshotPath": str(Path(args.snapshot).resolve()),
        "analysisDir": str(analysis_dir.resolve()),
        "thresholds": {
            "minCalibrationTrades": args.min_calibration_trades,
            "minDisplayedSize": args.min_displayed_size,
            "maxSpread": args.max_spread,
            "feeBuffer": args.fee_buffer,
            "minNetEdge": args.min_net_edge,
        },
        "status": status,
        "rowsScanned": len(snapshot_rows),
        "candidatesScored": len(candidates),
        "watchResearchCandidates": len(watch),
        "blockerCounts": blocker_counts,
        "topCandidates": candidates[: int(args.top_n)],
        "decision": (
            "Study watch candidates offline only; broad calibration priors are not execution evidence."
            if watch else
            "No current market cleared the broad by-price calibration research gate."
        ),
        "nextAction": "Join candidates to market-specific resolved outcome history, CLOB persistence, spread, and fillability before any paper promotion.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Research-only prediction-market calibration gate.")
    parser.add_argument("--snapshot", default=str(DEFAULT_SNAPSHOT))
    parser.add_argument("--analysis-dir", default=str(DEFAULT_ANALYSIS_DIR))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--min-calibration-trades", type=int, default=100)
    parser.add_argument("--min-displayed-size", type=float, default=100.0)
    parser.add_argument("--max-spread", type=float, default=0.02)
    parser.add_argument("--fee-buffer", type=float, default=0.01)
    parser.add_argument("--min-net-edge", type=float, default=0.03)
    parser.add_argument("--top-n", type=int, default=25)
    args = parser.parse_args()

    payload = run(args)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps({
        "wrote": str(out),
        "status": payload["status"],
        "rowsScanned": payload["rowsScanned"],
        "candidatesScored": payload["candidatesScored"],
        "watchResearchCandidates": payload["watchResearchCandidates"],
        "readyForPaper": payload["readyForPaper"],
        "researchOnly": payload["researchOnly"],
        "writesOrders": payload["writesOrders"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
