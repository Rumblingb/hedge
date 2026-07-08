#!/usr/bin/env python3
"""Research-only sketch: 5-minute price displacement on Polymarket CLOB capture JSONL.

Detects short-horizon mid-price moves after quote updates. Does not route orders.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
DEFAULT_CAPTURE = Path(
    "/Volumes/Seagate Expansion Drive/hedge-data/prediction-clob-capture/2026-07-06-market-channel.jsonl"
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def mid_from_book(book: dict[str, Any]) -> float | None:
    bids = book.get("bids") or []
    asks = book.get("asks") or []
    if not bids or not asks:
        return None
    try:
        best_bid = float(bids[0].get("price") if isinstance(bids[0], dict) else bids[0][0])
        best_ask = float(asks[0].get("price") if isinstance(asks[0], dict) else asks[0][0])
    except (TypeError, ValueError, IndexError):
        return None
    if best_bid <= 0 or best_ask <= 0:
        return None
    return (best_bid + best_ask) / 2.0


def load_events(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def displacement_events(
    rows: list[dict[str, Any]],
    *,
    window_sec: int = 300,
    min_move: float = 0.015,
) -> list[dict[str, Any]]:
    by_asset: dict[str, list[tuple[float, float]]] = {}
    for row in rows:
        asset = str(row.get("asset_id") or row.get("token_id") or row.get("market") or "unknown")
        ts_raw = row.get("ts") or row.get("timestamp") or row.get("received_at")
        book = row.get("book") or row.get("orderbook") or row
        if ts_raw is None:
            continue
        try:
            if isinstance(ts_raw, (int, float)):
                ts = float(ts_raw) / (1000.0 if ts_raw > 1e12 else 1.0)
            else:
                ts = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00")).timestamp()
        except (TypeError, ValueError):
            continue
        mid = mid_from_book(book if isinstance(book, dict) else {})
        if mid is None:
            continue
        by_asset.setdefault(asset, []).append((ts, mid))

    hits: list[dict[str, Any]] = []
    for asset, series in by_asset.items():
        series.sort(key=lambda item: item[0])
        for idx, (ts, mid) in enumerate(series):
            anchor = mid
            for j in range(idx + 1, len(series)):
                ts_j, mid_j = series[j]
                if ts_j - ts > window_sec:
                    break
                move = mid_j - anchor
                if abs(move) >= min_move:
                    hits.append({
                        "assetId": asset,
                        "startTs": ts,
                        "endTs": ts_j,
                        "windowSec": int(ts_j - ts),
                        "startMid": round(anchor, 4),
                        "endMid": round(mid_j, 4),
                        "displacement": round(move, 4),
                        "direction": "up" if move > 0 else "down",
                    })
                    break
    return hits


def build_report(path: Path, *, window_sec: int, min_move: float) -> dict[str, Any]:
    rows = load_events(path)
    hits = displacement_events(rows, window_sec=window_sec, min_move=min_move)
    return {
        "command": "prediction-five-min-displacement-scanner",
        "generatedAt": now_iso(),
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "capturePath": str(path),
        "messageCount": len(rows),
        "displacementHits": len(hits),
        "windowSec": window_sec,
        "minMove": min_move,
        "topHits": sorted(hits, key=lambda item: abs(item["displacement"]), reverse=True)[:20],
        "readyForPaper": False,
        "operatorRead": "Sketch only — validate against event timestamps and fillability before paper promotion.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture", default=str(DEFAULT_CAPTURE))
    parser.add_argument("--window-sec", type=int, default=300)
    parser.add_argument("--min-move", type=float, default=0.015)
    args = parser.parse_args()
    payload = build_report(Path(args.capture), window_sec=args.window_sec, min_move=args.min_move)
    out = STATE / "prediction-five-min-displacement-scanner.latest.json"
    out.write_text(json.dumps(payload, indent=2))
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
