#!/usr/bin/env python3
"""Replay source-specific macro/rates cross-source pricing.

Research-only. This uses the cleared Fed/Kalshi parser fixture to transform
Polymarket Fed decision bucket prices into implied probabilities for matching
Kalshi KXFED threshold contracts. It produces watch/reject context only.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge/state"
PARSER_FIXTURE = STATE / "prediction-macro-rates-parser-fixture.latest.json"
REQUIREMENTS = STATE / "prediction-macro-rates-requirements.latest.json"
OUT = STATE / "prediction-macro-rates-cross-source-replay.latest.json"
VAULT = Path.home() / "Documents/memorybrain"
OUT_MD = VAULT / "Agent-Hermes" / "prediction-macro-rates-cross-source-replay-2026-05-30.md"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def to_float(value: Any) -> float | None:
    if isinstance(value, (int, float)) and value == value:
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def fee_from_rate_pct(price: float | None, rate: float) -> float:
    if price is None:
        return 0.0
    p = min(max(float(price), 0.01), 0.99)
    return rate * p * (1 - p) * 100


def pm_price_by_id(parser_fixture: dict[str, Any]) -> dict[str, float]:
    rows = parser_fixture.get("polymarketFedDecisions") if isinstance(parser_fixture.get("polymarketFedDecisions"), list) else []
    out: dict[str, float] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        external_id = str(row.get("externalId") or "")
        price = to_float(row.get("price"))
        if external_id and price is not None and 0 <= price <= 1:
            out[external_id] = price
    return out


def kxfed_by_ticker(parser_fixture: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = parser_fixture.get("kalshiKxfedThresholds") if isinstance(parser_fixture.get("kalshiKxfedThresholds"), list) else []
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        if isinstance(row, dict) and row.get("ticker"):
            out[str(row["ticker"])] = row
    return out


def build_replay(
    *,
    parser_fixture: dict[str, Any],
    requirements: dict[str, Any],
    min_edge_pct: float = 3.0,
    max_spread_pct: float = 5.0,
    min_sample_rows: int = 20,
    slippage_pct: float = 0.5,
    polymarket_macro_fee_rate: float = 0.05,
    kalshi_taker_fee_multiplier: float = 0.07,
) -> dict[str, Any]:
    blockers: list[str] = []
    if parser_fixture.get("decision") != "research-only-fed-kalshi-parser-fixture-ready":
        blockers.append("parser-fixture-not-ready")
    if requirements.get("decision") != "research-only-macro-rates-requirements-cleared":
        blockers.append("macro-rates-requirements-not-cleared")

    prices = pm_price_by_id(parser_fixture)
    kalshi = kxfed_by_ticker(parser_fixture)
    pairs = parser_fixture.get("sameMeetingPairs") if isinstance(parser_fixture.get("sameMeetingPairs"), list) else []
    grouped: dict[str, list[dict[str, Any]]] = {}
    for pair in pairs:
        if not isinstance(pair, dict):
            continue
        if pair.get("kalshiYesIfPolymarketBucketWins") is None:
            continue
        ticker = str(pair.get("kalshiTicker") or "")
        if ticker:
            grouped.setdefault(ticker, []).append(pair)

    rows: list[dict[str, Any]] = []
    watch: list[dict[str, Any]] = []
    for ticker, ticker_pairs in sorted(grouped.items()):
        yes_sum = 0.0
        total = 0.0
        contributing_buckets: list[dict[str, Any]] = []
        for pair in ticker_pairs:
            pm_id = str(pair.get("polymarketExternalId") or "")
            price = prices.get(pm_id)
            if price is None:
                continue
            total += price
            truth = bool(pair.get("kalshiYesIfPolymarketBucketWins"))
            if truth:
                yes_sum += price
            contributing_buckets.append({
                "polymarketExternalId": pm_id,
                "bucket": pair.get("polymarketBucket"),
                "price": price,
                "kalshiYesIfBucketWins": truth,
            })
        if total <= 0:
            continue
        kx = kalshi.get(ticker, {})
        bid = to_float(kx.get("yesBid"))
        ask = to_float(kx.get("yesAsk"))
        mid = round((bid + ask) / 2, 6) if bid is not None and ask is not None else None
        spread_pct = round((ask - bid) * 100, 4) if bid is not None and ask is not None else None
        implied_yes = round(yes_sum / total, 6)
        implied_no = round(1 - implied_yes, 6)
        yes_edge_pct = round((implied_yes - ask) * 100, 4) if ask is not None else None
        no_edge_pct = round((implied_no - (1 - bid)) * 100, 4) if bid is not None else None
        yes_fee_drag_pct = round(
            fee_from_rate_pct(implied_yes, polymarket_macro_fee_rate)
            + fee_from_rate_pct(ask, kalshi_taker_fee_multiplier)
            + slippage_pct,
            4,
        )
        no_ask = (1 - bid) if bid is not None else None
        no_fee_drag_pct = round(
            fee_from_rate_pct(implied_no, polymarket_macro_fee_rate)
            + fee_from_rate_pct(no_ask, kalshi_taker_fee_multiplier)
            + slippage_pct,
            4,
        )
        yes_net_edge_pct = round(yes_edge_pct - yes_fee_drag_pct, 4) if yes_edge_pct is not None else None
        no_net_edge_pct = round(no_edge_pct - no_fee_drag_pct, 4) if no_edge_pct is not None else None
        edge_survives_fee_stress = bool(
            (yes_net_edge_pct is not None and yes_net_edge_pct >= min_edge_pct)
            or (no_net_edge_pct is not None and no_net_edge_pct >= min_edge_pct)
        )
        row_blockers = ["research-only", "not-paper-ready"]
        if edge_survives_fee_stress:
            row_blockers.append("sample-size-too-small")
        else:
            row_blockers.append("no-positive-net-edge-after-fee-stress")
        row = {
            "ticker": ticker,
            "question": kx.get("question"),
            "meetingDate": ticker_pairs[0].get("meetingDate"),
            "thresholdUpperBound": kx.get("thresholdUpperBound"),
            "kalshiYesBid": bid,
            "kalshiYesAsk": ask,
            "kalshiYesMid": mid,
            "kalshiSpreadPct": spread_pct,
            "polymarketBucketPriceTotal": round(total, 6),
            "polymarketImpliedYesProbability": implied_yes,
            "polymarketImpliedNoProbability": implied_no,
            "yesEdgePctVsAsk": yes_edge_pct,
            "noEdgePctVsNoAsk": no_edge_pct,
            "feeStress": {
                "slippagePct": slippage_pct,
                "polymarketMacroFeeRate": polymarket_macro_fee_rate,
                "kalshiTakerFeeMultiplier": kalshi_taker_fee_multiplier,
                "yesFeeDragPct": yes_fee_drag_pct,
                "noFeeDragPct": no_fee_drag_pct,
                "yesNetEdgePctVsAsk": yes_net_edge_pct,
                "noNetEdgePctVsNoAsk": no_net_edge_pct,
                "edgeSurvivesFeeStress": edge_survives_fee_stress,
            },
            "contributingBuckets": contributing_buckets,
            "watchResearchOnly": False,
            "paperStatus": "blocked",
            "blockers": row_blockers,
        }
        if (
            not blockers
            and spread_pct is not None
            and spread_pct <= max_spread_pct
            and len(grouped) >= min_sample_rows
            and edge_survives_fee_stress
        ):
            row["watchResearchOnly"] = True
            watch.append(row)
        rows.append(row)

    if not rows:
        blockers.append("no-source-specific-cross-source-rows")
    elif len(rows) < min_sample_rows:
        blockers.append("too-few-source-specific-sample-rows")
    return {
        "command": "prediction-macro-rates-cross-source-replay",
        "generatedAt": now_iso(),
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "readyForPaper": False,
        "readyForExecution": False,
        "minEdgePct": min_edge_pct,
        "maxSpreadPct": max_spread_pct,
        "minSampleRows": min_sample_rows,
        "feeStressDefaults": {
            "slippagePct": slippage_pct,
            "polymarketMacroFeeRate": polymarket_macro_fee_rate,
            "kalshiTakerFeeMultiplier": kalshi_taker_fee_multiplier,
        },
        "rows": rows,
        "rowCount": len(rows),
        "watchResearchCount": len(watch),
        "watchResearch": watch[:20],
        "blockers": blockers,
        "decision": (
            "research-only-macro-rates-cross-source-replay-blocked"
            if blockers
            else "research-only-macro-rates-cross-source-replay-complete"
        ),
        "hardRules": [
            "This is cross-source research context only, not an order directive.",
            "No paper/live/funding route without repeated OOS samples, fee stress, and promotion review.",
            "Do not use broad CPI or unrelated macro lines as substitutes for Fed decision thresholds.",
        ],
    }


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Prediction Macro/Rates Cross-Source Replay - 2026-05-30",
        "",
        "Parent hub: [[BILL-CONTROL-HUB]]",
        "",
        "Research-only Polymarket-to-Kalshi Fed/rates cross-source replay.",
        "",
        "## Summary",
        "",
        f"- Decision: `{payload.get('decision')}`",
        f"- Rows: `{payload.get('rowCount')}`",
        f"- Watch research rows: `{payload.get('watchResearchCount')}`",
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
    parser = argparse.ArgumentParser(description="Replay macro/rates cross-source pricing research.")
    parser.add_argument("--parser-fixture", default=str(PARSER_FIXTURE))
    parser.add_argument("--requirements", default=str(REQUIREMENTS))
    parser.add_argument("--min-edge-pct", type=float, default=3.0)
    parser.add_argument("--max-spread-pct", type=float, default=5.0)
    parser.add_argument("--min-sample-rows", type=int, default=20)
    parser.add_argument("--slippage-pct", type=float, default=0.5)
    parser.add_argument("--polymarket-macro-fee-rate", type=float, default=0.05)
    parser.add_argument("--kalshi-taker-fee-multiplier", type=float, default=0.07)
    parser.add_argument("--output", default=str(OUT))
    parser.add_argument("--markdown", default=str(OUT_MD))
    args = parser.parse_args()
    payload = build_replay(
        parser_fixture=read_json(Path(args.parser_fixture)),
        requirements=read_json(Path(args.requirements)),
        min_edge_pct=args.min_edge_pct,
        max_spread_pct=args.max_spread_pct,
        min_sample_rows=args.min_sample_rows,
        slippage_pct=args.slippage_pct,
        polymarket_macro_fee_rate=args.polymarket_macro_fee_rate,
        kalshi_taker_fee_multiplier=args.kalshi_taker_fee_multiplier,
    )
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
