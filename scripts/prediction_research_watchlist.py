#!/usr/bin/env python3
"""Build a safe research watchlist from prediction-market gates.

The output is a handoff artifact for research agents: which markets deserve
more read-only CLOB capture or market-specific resolution work next. It is not
a paper/live signal and contains no execution route.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
DEFAULT_INPUT = STATE / "prediction-calibration-gate.latest.json"
DEFAULT_OUTPUT = STATE / "prediction-research-watchlist.latest.json"


def read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


def build_watch_item(candidate: dict[str, Any], book_by_asset: dict[str, dict[str, Any]]) -> dict[str, Any]:
    blockers = list(candidate.get("blockers") or [])
    token_id = candidate.get("clobTokenId")
    venue = candidate.get("venue")
    latest_book = book_by_asset.get(str(token_id)) if token_id else None
    latest_spread = latest_book.get("spread") if latest_book else None
    if isinstance(latest_spread, (int, float)) and latest_spread > 0.02:
        blockers.append("latest-clob-spread-too-wide")
    item = {
        "venue": venue,
        "externalId": candidate.get("externalId"),
        "clobTokenId": token_id,
        "question": candidate.get("question"),
        "outcomeLabel": candidate.get("outcomeLabel"),
        "expiry": candidate.get("expiry"),
        "bestBid": candidate.get("bestBid"),
        "bestAsk": candidate.get("bestAsk"),
        "spread": candidate.get("spread"),
        "displayedSize": candidate.get("displayedSize"),
        "calibratedWinRate": candidate.get("calibratedWinRate"),
        "netEdgeAfterBufferAndSpread": candidate.get("netEdgeAfterBufferAndSpread"),
        "researchStatus": "watch-research-only",
        "paperStatus": "blocked",
        "blockers": blockers,
        "nextEvidenceNeeded": [
            "market-specific resolved-outcome history",
            "read-only CLOB quote/trade persistence",
            "spread and fillability under realistic size",
            "settlement wording review",
        ],
    }
    if venue == "polymarket" and token_id:
        item["clobCaptureEligible"] = True
        item["suggestedRecorderFlag"] = f"--token-id {token_id}"
    else:
        item["clobCaptureEligible"] = False
    if latest_book:
        item["latestClobBook"] = {
            "bestBid": latest_book.get("bestBid"),
            "bestAsk": latest_book.get("bestAsk"),
            "spread": latest_book.get("spread"),
            "bidSize": latest_book.get("bidSize"),
            "askSize": latest_book.get("askSize"),
            "lastBookLocalTs": latest_book.get("lastBookLocalTs"),
            "lastBbaLocalTs": latest_book.get("lastBbaLocalTs"),
        }
    return item


def build_report(args) -> dict[str, Any]:
    source = read_json(Path(args.input))
    recorder = read_json(STATE / "polymarket-clob-recorder.latest.json")
    book_by_asset = {
        str(row.get("assetId")): row
        for row in recorder.get("latestBookState") or []
        if row.get("assetId")
    }
    candidates = [
        build_watch_item(candidate, book_by_asset)
        for candidate in source.get("topCandidates") or []
        if candidate.get("verdict") == "watch-research"
    ][: args.max_items]
    token_ids = [
        str(item["clobTokenId"])
        for item in candidates
        if item.get("clobCaptureEligible") and item.get("clobTokenId")
    ]
    recorder_command = None
    if token_ids:
        token_args = " ".join(f"--token-id {shell_quote(token_id)}" for token_id in token_ids)
        recorder_command = (
            "npm run --silent bill:polymarket-clob-recorder -- "
            f"--duration-sec {int(args.duration_sec)} --max-assets {len(token_ids)} {token_args}"
        )

    return {
        "command": "prediction-research-watchlist",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "researchOnly": True,
        "writesOrders": False,
        "readyForPaper": False,
        "sourcePath": str(Path(args.input).resolve()),
        "sourceStatus": source.get("status", "missing"),
        "latestRecorderPath": str((STATE / "polymarket-clob-recorder.latest.json").resolve()),
        "latestRecorderStatus": recorder.get("status", "missing"),
        "watchCount": len(candidates),
        "polymarketClobTokenIds": token_ids,
        "suggestedReadOnlyRecorderCommand": recorder_command,
        "items": candidates,
        "decision": "Watchlist is for read-only research only; do not paper/live trade from this artifact.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build read-only prediction research watchlist.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--max-items", type=int, default=10)
    parser.add_argument("--duration-sec", type=int, default=180)
    args = parser.parse_args()

    payload = build_report(args)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps({
        "wrote": str(out),
        "watchCount": payload["watchCount"],
        "tokenIds": payload["polymarketClobTokenIds"],
        "researchOnly": payload["researchOnly"],
        "writesOrders": payload["writesOrders"],
        "readyForPaper": payload["readyForPaper"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
