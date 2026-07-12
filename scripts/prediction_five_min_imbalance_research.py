#!/usr/bin/env python3
"""Research-only: post-shock 5-minute fade expectancy on Polymarket CLOB captures.

Hypothesis: after a short-horizon mid displacement (price imbalance / overreaction),
mid mean-reverts within a fixed hold (default 5 minutes). One variable: shock
threshold. Fillability filters locked (max half-spread, min samples).

Never writes orders / never touches broker.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
DEFAULT_CAPTURE_DIR = Path(
    "/Volumes/Seagate Expansion Drive/hedge-data/prediction-clob-capture"
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_ts(row: dict[str, Any]) -> float | None:
    raw = row.get("localTs") or row.get("ts") or row.get("timestamp") or row.get("received_at")
    if raw is None:
        return None
    try:
        if isinstance(raw, (int, float)):
            return float(raw) / (1000.0 if raw > 1e12 else 1.0)
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


def mid_from_row(row: dict[str, Any]) -> tuple[float | None, float | None]:
    """Return (mid, half_spread). Prefer bestBid/bestAsk; else book top."""
    bb = row.get("bestBid")
    ba = row.get("bestAsk")
    if bb is not None and ba is not None:
        try:
            bid = float(bb)
            ask = float(ba)
            if bid > 0 and ask > 0 and ask >= bid:
                return (bid + ask) / 2.0, (ask - bid) / 2.0
        except (TypeError, ValueError):
            pass
    bids = row.get("bids") or []
    asks = row.get("asks") or []
    if not bids or not asks:
        return None, None

    def top_px(levels: list[Any], side: str) -> float | None:
        try:
            lvl = levels[0]
            if isinstance(lvl, dict):
                return float(lvl.get("price"))
            if isinstance(lvl, (list, tuple)):
                return float(lvl[0])
            return float(lvl)
        except (TypeError, ValueError, IndexError):
            return None

    bid = top_px(bids, "bid")
    ask = top_px(asks, "ask")
    if bid is None or ask is None or bid <= 0 or ask <= 0 or ask < bid:
        return None, None
    return (bid + ask) / 2.0, (ask - bid) / 2.0


def asset_key(row: dict[str, Any]) -> str | None:
    aid = row.get("assetId") or row.get("asset_id") or row.get("token_id")
    if aid:
        return str(aid)
    # price_change often lacks assetId — skip (cannot form mid series cleanly)
    return None


def load_mid_series(paths: list[Path]) -> dict[str, list[tuple[float, float, float]]]:
    """asset -> sorted list of (ts, mid, half_spread)."""
    by: dict[str, list[tuple[float, float, float]]] = defaultdict(list)
    for path in paths:
        if not path.exists():
            continue
        with path.open() as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(row, dict):
                    continue
                et = row.get("eventType") or row.get("event_type")
                if et not in (None, "book", "best_bid_ask", "price_change", "last_trade_price"):
                    # still try if mid present
                    pass
                key = asset_key(row)
                if not key:
                    continue
                ts = parse_ts(row)
                if ts is None:
                    continue
                mid, hs = mid_from_row(row)
                if mid is None or hs is None:
                    continue
                by[key].append((ts, mid, hs))
    for key in by:
        by[key].sort(key=lambda x: x[0])
    return by


def forward_mid(
    series: list[tuple[float, float, float]],
    idx: int,
    hold_sec: float,
    *,
    max_overshoot_sec: float | None = None,
) -> tuple[float, float, float] | None:
    """First quote at or after ts[idx]+hold_sec, but not later than hold+overshoot.

    Without an overshoot cap, sparse CLOB captures turn a '5m hold' into hours/days
    and invent false expectancy.
    """
    t0 = series[idx][0]
    target = t0 + hold_sec
    deadline = t0 + hold_sec + (max_overshoot_sec if max_overshoot_sec is not None else hold_sec * 0.5)
    for j in range(idx + 1, len(series)):
        ts_j = series[j][0]
        if ts_j > deadline:
            return None
        if ts_j >= target:
            return series[j]
    return None


def evaluate(
    series_by_asset: dict[str, list[tuple[float, float, float]]],
    *,
    shock_lookback_sec: float,
    shock_threshold: float,
    hold_sec: float,
    max_half_spread: float,
    min_gap_sec: float,
) -> dict[str, Any]:
    trades: list[dict[str, Any]] = []
    for asset, series in series_by_asset.items():
        if len(series) < 5:
            continue
        last_entry_ts = -1e18
        for i in range(1, len(series)):
            ts, mid, hs = series[i]
            if hs > max_half_spread:
                continue
            # find mid ~lookback ago
            anchor_mid = None
            for k in range(i - 1, -1, -1):
                if series[i][0] - series[k][0] >= shock_lookback_sec:
                    anchor_mid = series[k][1]
                    break
                if series[i][0] - series[k][0] > shock_lookback_sec * 2:
                    break
            if anchor_mid is None:
                # use earliest in window
                window = [s for s in series[:i] if ts - s[0] <= shock_lookback_sec]
                if not window:
                    continue
                anchor_mid = window[0][1]
            shock = mid - anchor_mid
            if abs(shock) < shock_threshold:
                continue
            if ts - last_entry_ts < min_gap_sec:
                continue
            fwd = forward_mid(series, i, hold_sec, max_overshoot_sec=hold_sec * 0.5)
            if fwd is None:
                continue
            f_ts, f_mid, f_hs = fwd
            actual_hold = f_ts - ts
            if actual_hold < hold_sec * 0.8 or actual_hold > hold_sec * 1.5:
                continue
            # Fade: short the shock direction
            side = -1 if shock > 0 else 1
            gross = side * (f_mid - mid)
            # Round-trip half-spread haircut at entry + exit
            cost = hs + f_hs
            net = gross - cost
            trades.append(
                {
                    "assetId": asset[-12:],
                    "entryTs": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(),
                    "exitTs": datetime.fromtimestamp(f_ts, tz=timezone.utc).isoformat(),
                    "shock": round(shock, 4),
                    "entryMid": round(mid, 4),
                    "exitMid": round(f_mid, 4),
                    "holdSec": round(actual_hold, 1),
                    "entryHalfSpread": round(hs, 4),
                    "exitHalfSpread": round(f_hs, 4),
                    "gross": round(gross, 4),
                    "cost": round(cost, 4),
                    "net": round(net, 4),
                    "fadeWorked": gross > 0,
                }
            )
            last_entry_ts = ts

    n = len(trades)
    if n == 0:
        return {
            "shockThreshold": shock_threshold,
            "trades": 0,
            "status": "no-trades",
        }
    nets = [t["net"] for t in trades]
    grosses = [t["gross"] for t in trades]
    wins = [x for x in nets if x > 0]
    losses = [x for x in nets if x <= 0]
    gw = sum(wins) if wins else 0.0
    gl = abs(sum(losses)) if losses else 0.0
    pf = (gw / gl) if gl > 0 else None
    # chronological OOS last 30%
    cut = int(n * 0.7)
    oos = nets[cut:]
    oos_wins = [x for x in oos if x > 0]
    return {
        "shockThreshold": shock_threshold,
        "trades": n,
        "hitRateGross": round(sum(1 for t in trades if t["fadeWorked"]) / n, 4),
        "hitRateNet": round(len(wins) / n, 4),
        "avgGross": round(sum(grosses) / n, 5),
        "avgNet": round(sum(nets) / n, 5),
        "totalNet": round(sum(nets), 5),
        "pf": None if pf is None else round(pf, 4),
        "oosTrades": len(oos),
        "oosAvgNet": round(sum(oos) / len(oos), 5) if oos else None,
        "oosHitRateNet": round(len(oos_wins) / len(oos), 4) if oos else None,
        "medianHoldSec": sorted(t["holdSec"] for t in trades)[n // 2],
        "status": "ok",
        "sampleTrades": trades[:8],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--capture-dir", type=Path, default=DEFAULT_CAPTURE_DIR)
    ap.add_argument(
        "--files",
        default="",
        help="Comma-separated filenames under capture-dir (default: recent days)",
    )
    ap.add_argument("--shock-lookback-sec", type=float, default=60.0)
    ap.add_argument("--hold-sec", type=float, default=300.0)
    ap.add_argument("--thresholds", default="0.01,0.015,0.02,0.03,0.05")
    ap.add_argument("--max-half-spread", type=float, default=0.02)
    ap.add_argument("--min-gap-sec", type=float, default=120.0)
    ap.add_argument(
        "--out",
        type=Path,
        default=STATE / "prediction-five-min-imbalance-research.latest.json",
    )
    args = ap.parse_args()

    if args.files.strip():
        paths = [args.capture_dir / f.strip() for f in args.files.split(",") if f.strip()]
    else:
        # Prefer recent captures that exist
        candidates = [
            "2026-07-09-market-channel.jsonl",
            "2026-07-08-market-channel.jsonl",
            "2026-07-06-market-channel.jsonl",
            "2026-06-30-market-channel.jsonl",
            "2026-06-24-market-channel.jsonl",
            "2026-06-23-market-channel.jsonl",
        ]
        paths = [args.capture_dir / c for c in candidates if (args.capture_dir / c).exists()]

    series = load_mid_series(paths)
    thresholds = [float(x) for x in args.thresholds.split(",") if x.strip()]
    results = [
        evaluate(
            series,
            shock_lookback_sec=args.shock_lookback_sec,
            shock_threshold=th,
            hold_sec=args.hold_sec,
            max_half_spread=args.max_half_spread,
            min_gap_sec=args.min_gap_sec,
        )
        for th in thresholds
    ]
    ok = [r for r in results if r.get("trades", 0) > 0]
    best = max(ok, key=lambda r: (r.get("oosAvgNet") or -1e9, r.get("avgNet") or -1e9), default=None)

    # Literature / local gate context
    payload = {
        "generatedAt": now_iso(),
        "command": "prediction-five-min-imbalance-research",
        "hypothesis": (
            "After a short-horizon mid displacement on Polymarket CLOB, fading the shock "
            f"and holding {args.hold_sec:.0f}s mean-reverts enough to clear round-trip spread."
        ),
        "oneVariable": "shockThreshold (mid move in lookback window)",
        "lockedFilters": {
            "shockLookbackSec": args.shock_lookback_sec,
            "holdSec": args.hold_sec,
            "maxHalfSpread": args.max_half_spread,
            "minGapSec": args.min_gap_sec,
        },
        "capturePaths": [str(p) for p in paths],
        "assetsWithMids": len(series),
        "midQuotes": sum(len(v) for v in series.values()),
        "results": results,
        "bestThreshold": best,
        "decision": "research-only-five-min-imbalance-probe",
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "readyForPaper": False,
        "readyForExecution": False,
        "localContext": {
            "seed": "pm-5min-displacement-fade",
            "eventLagReplay": (
                "Existing event-lag replay: 15m median abs move ~0 after half-spread; "
                "120m raw moves exist but fail half-spread clearance — liquidity kills edge."
            ),
        },
        "literatureNotes": [
            "QuantPedia Polymarket mean-reversion: alpha collapses under realistic spread/fees",
            "arXiv 2605.00864 NBA CLOB arb: median episode ~3.6s; shallow books cap size",
            "Crash-bot style >15%/4h reversion is multi-hour, not 5-minute hold",
            "News-lag blogs claim 5–30m stale AMM windows — Polymarket CLOB is hybrid; bots compress seconds",
        ],
        "operatorRead": (
            "Use bestThreshold only if oosAvgNet>0 AND pf>=1.25 AND trades>=30; "
            "else reject for paper. Never promote on gross hit-rate alone."
        ),
        "promotionGate": "prediction paper-promotion gate + fillability + labeled event windows",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps({
        "out": str(args.out),
        "assetsWithMids": payload["assetsWithMids"],
        "midQuotes": payload["midQuotes"],
        "results": results,
        "bestThreshold": best,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
