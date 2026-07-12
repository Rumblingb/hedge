#!/usr/bin/env python3
"""Order-flow direction vs resolved outcome. HINDSIGHT BASELINE + tautology proof.

Research-only, read-only. The historical trades parquet has NULL timestamps
(block_number only), so a non-hindsight early/late split is impossible on this
corpus. Instead this script computes the WHOLE-market net flow -> resolution
directional accuracy, which is the tautological upper bound (a market that
resolves YES will by construction show net YES buying by end of trading).

The point is to PROVE the need for time-separation and to establish that the
only non-hindsight signal must come from OPEN-market live flow capture -- which
is the real next step, not a parameter change on this data.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
VAULT = Path.home() / "Documents/memorybrain"
OUT = STATE / "prediction-clob-orderflow-resolution-replay.latest.json"
OUT_MD = VAULT / "Agent-Hermes" / f"prediction-clob-orderflow-resolution-replay-{datetime.now(timezone.utc).date().isoformat()}.md"
USDC = "0"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def build_market_index(con: duckdb.DuckDBPyConnection, markets_files: list[str]) -> dict[str, dict[str, Any]]:
    idx: dict[str, dict[str, Any]] = {}
    rows = con.execute(
        "select id, question, outcomes, outcome_prices, clob_token_ids from read_parquet(?) where closed = true",
        [markets_files],
    ).fetchall()
    for mid, question, outcomes, prices, tokens in rows:
        try:
            out_list = [str(x).strip().lower() for x in json.loads(outcomes) if isinstance(x, str)]
            price_list = [float(x) for x in json.loads(prices)]
            token_list = json.loads(tokens)
        except Exception:
            continue
        if len(out_list) != 2 or len(price_list) != 2 or len(token_list) != 2:
            continue
        if max(price_list) < 0.99:
            continue
        winner = int(price_list.index(max(price_list)))
        try:
            yes_idx = out_list.index("yes")
        except ValueError:
            continue
        resolved = "YES" if winner == yes_idx else "NO"
        yes_token = str(token_list[yes_idx])
        no_token = str(token_list[1 - yes_idx])
        for tk, side in ((yes_token, "YES"), (no_token, "NO")):
            idx[tk] = {"marketId": str(mid), "question": str(question), "resolved": resolved, "mySide": side}
    return idx


def load_trades(con: duckdb.DuckDBPyConnection, trades_files: list[str]) -> list[dict[str, Any]]:
    rows = con.execute(
        "select maker_asset_id, taker_asset_id, maker_amount, taker_amount from read_parquet(?)",
        [trades_files],
    ).fetchall()
    out = []
    for ma, ta, mamt, tamt in rows:
        if ta and str(ta) != USDC:
            out.append({"token": str(ta), "side": "BUY", "amount": float(tamt or 0)})
        elif ma and str(ma) != USDC:
            out.append({"token": str(ma), "side": "SELL", "amount": float(mamt or 0)})
    return out


def aggregate(by_token: dict[str, list[dict[str, Any]]], market_index: dict[str, dict[str, Any]], min_trades: int):
    scored = []
    for token, tk_trades in by_token.items():
        info = market_index.get(token)
        if info is None or len(tk_trades) < min_trades:
            continue
        net = sum(t["amount"] if t["side"] == "BUY" else -t["amount"] for t in tk_trades)
        signal = "YES" if net > 0 else ("NO" if net < 0 else None)
        scored.append({
            "marketId": info["marketId"],
            "question": info["question"][:80],
            "resolved": info["resolved"],
            "netYesBuy": round(net, 2),
            "signal": signal,
            "hit": (signal == info["resolved"]) if signal else None,
            "nTrades": len(tk_trades),
        })
    return scored


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    manifest = read_json(Path(args.manifest))
    tables = manifest.get("tables") if isinstance(manifest.get("tables"), dict) else {}
    markets_files = (tables.get("polymarket_markets") or {}).get("sample") or []
    trades_files = (tables.get("polymarket_trades") or {}).get("sample") or []
    con = duckdb.connect()
    market_index = build_market_index(con, markets_files)
    trades = load_trades(con, trades_files)
    by_token: dict[str, list[dict[str, Any]]] = defaultdict(list)
    joined = 0
    for t in trades:
        if t["token"] in market_index:
            joined += 1
            by_token[t["token"]].append(t)
    scored = aggregate(by_token, market_index, args.min_trades)
    hits = [s["hit"] for s in scored if s["hit"] is not None]
    acc = sum(1 for h in hits if h) / len(hits) if hits else None
    blockers = []
    if len(scored) < args.min_markets:
        blockers.append("too-few-joined-markets")
    if acc is None or acc < args.min_hit_rate:
        blockers.append("flow-hit-rate-below-contract")
    return {
        "command": "prediction-clob-orderflow-resolution-replay",
        "generatedAt": now_iso(),
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "readyForPaper": False,
        "manifestPath": str(Path(args.manifest).resolve()),
        "marketsInIndex": len(market_index),
        "tradesRead": len(trades),
        "tradesJoinedToResolved": joined,
        "marketsScored": len(scored),
        "wholeMarketFlow": {
            "markets": len(hits),
            "directionalHitRate": round(acc, 6) if acc is not None else None,
            "edgeOverFlip": round(acc - 0.5, 6) if acc is not None else None,
            "note": "tautological upper bound: whole-market flow includes post-conviction period; non-hindsight split impossible (timestamps NULL in trades parquet).",
        },
        "fixedThresholds": {"minMarkets": args.min_markets, "minHitRate": args.min_hit_rate, "minTradesPerMarket": args.min_trades},
        "sampleMarkets": scored[:50],
        "decision": "research-only-no-nonhindsight-signal",
        "nextAction": "Capture OPEN-market live flow (you have it); build a forward paper signal from live flow vs contemporaneous mid BEFORE resolution. Historical corpus cannot supply time-separated labels.",
    }


def render_markdown(payload: dict[str, Any]) -> str:
    w = payload.get("wholeMarketFlow", {})
    lines = [
        "# Prediction CLOB Order-Flow x Resolution Replay - " + str(payload.get("generatedAt", ""))[:10],
        "",
        "Parent hub: [[BILL-CONTROL-HUB]]",
        "",
        "Research-only. Whole-market order flow vs resolved outcome (hindsight baseline).",
        "",
        "## Summary",
        "",
        f"- Decision: `{payload.get('decision')}`",
        f"- Markets in index: `{payload.get('marketsInIndex')}`",
        f"- Trades read: `{payload.get('tradesRead')}`",
        f"- Trades joined: `{payload.get('tradesJoinedToResolved')}`",
        f"- Markets scored: `{payload.get('marketsScored')}`",
        "",
        "## Whole-market flow -> resolution (TAUTOLOGICAL)",
        f"- Markets: `{w.get('markets')}`",
        f"- Directional hit rate: `{w.get('directionalHitRate')}`",
        f"- Edge over coin-flip: `{w.get('edgeOverFlip')}`",
        f"- Note: {w.get('note')}",
        "",
        "Conclusion: non-hindsight flow->resolution edge cannot be computed from the current corpus. "
        "The only forward signal requires live open-market flow capture vs contemporaneous mid, before resolution.",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Order-flow vs resolved outcome (hindsight baseline).")
    parser.add_argument("--manifest", default=str(ROOT / ".rumbling-hedge" / "research" / "prediction-market-analysis" / "manifest.json"))
    parser.add_argument("--output", default=str(OUT))
    parser.add_argument("--markdown-output", default=str(OUT_MD))
    parser.add_argument("--min-markets", type=int, default=30)
    parser.add_argument("--min-hit-rate", type=float, default=0.55)
    parser.add_argument("--min-trades", type=int, default=5)
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
