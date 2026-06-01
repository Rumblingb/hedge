#!/usr/bin/env python3
"""Offline OOS evaluator for resolved Polymarket BTC up/down features.

Research-only. This consumes a resolved historical parquet corpus and tests a
small fixed set of one-feature-family rules. It does not route, fund, paper,
or place prediction-market orders.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import polars as pl


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = Path("/Volumes/Seagate Expansion Drive/hedge-data/features/polymarket_btc_updown/btc_5m_resolved_all_features.parquet")
STATE = ROOT / ".rumbling-hedge/state"
HERMES = Path.home() / "Documents/memorybrain/Agent-Hermes"
DEFAULT_OUTPUT = STATE / "prediction-btc-resolved-oos.latest.json"
DEFAULT_MARKDOWN = HERMES / "prediction-btc-resolved-oos-2026-05-30.md"


@dataclass(frozen=True)
class Rule:
    rule_id: str
    side: str
    one_variable: str
    description: str
    condition: pl.Expr


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def fixed_rules(max_spread: float = 0.08) -> list[Rule]:
    valid_up = pl.col("up_price").is_between(0.15, 0.85) & (pl.col("avg_spread") <= max_spread)
    valid_down = pl.col("down_price").is_between(0.15, 0.85) & (pl.col("avg_spread") <= max_spread)
    return [
        Rule(
            "spot-distance-up",
            "up",
            "spot distance to strike",
            "Buy UP when BTC spot is already above strike by a fixed margin.",
            valid_up & (pl.col("spot_distance_to_strike_pct") >= 0.0015),
        ),
        Rule(
            "spot-distance-down",
            "down",
            "spot distance to strike",
            "Buy DOWN when BTC spot is already below strike by a fixed margin.",
            valid_down & (pl.col("spot_distance_to_strike_pct") <= -0.0015),
        ),
        Rule(
            "trade-flow-up",
            "up",
            "trade flow imbalance",
            "Buy UP when recent trade flow is strongly buy-skewed.",
            valid_up & (pl.col("trade_flow_imbalance") >= 0.35),
        ),
        Rule(
            "trade-flow-down",
            "down",
            "trade flow imbalance",
            "Buy DOWN when recent trade flow is strongly sell-skewed.",
            valid_down & (pl.col("trade_flow_imbalance") <= -0.35),
        ),
        Rule(
            "spot-momentum-up",
            "up",
            "spot momentum",
            "Buy UP when 3-bar and 12-bar BTC spot momentum are both positive.",
            valid_up & (pl.col("spot_mom_3bar") > 0) & (pl.col("spot_mom_12bar") > 0),
        ),
        Rule(
            "spot-momentum-down",
            "down",
            "spot momentum",
            "Buy DOWN when 3-bar and 12-bar BTC spot momentum are both negative.",
            valid_down & (pl.col("spot_mom_3bar") < 0) & (pl.col("spot_mom_12bar") < 0),
        ),
        Rule(
            "book-depth-up",
            "up",
            "order-book depth imbalance",
            "Buy UP when UP book depth imbalance is positive.",
            valid_up & (pl.col("up_depth_imbalance") >= 0.25),
        ),
        Rule(
            "book-depth-down",
            "down",
            "order-book depth imbalance",
            "Buy DOWN when DOWN book depth imbalance is positive.",
            valid_down & (pl.col("down_depth_imbalance") >= 0.25),
        ),
    ]


def read_input(path: Path) -> pl.DataFrame:
    if not path.exists():
        raise FileNotFoundError(str(path))
    columns = [
        "market_id",
        "ts",
        "end_ts",
        "question",
        "resolution",
        "target_up_win",
        "target_down_win",
        "up_price",
        "down_price",
        "avg_spread",
        "spot_distance_to_strike_pct",
        "trade_flow_imbalance",
        "spot_mom_3bar",
        "spot_mom_12bar",
        "spot_vol_12bar",
        "spot_vol_48bar",
        "up_depth_imbalance",
        "down_depth_imbalance",
        "ob_rows",
        "trade_count",
    ]
    return pl.scan_parquet(path).select([column for column in columns if column in pl.scan_parquet(path).collect_schema().names()]).collect()


def signals_for_rule(df: pl.DataFrame, rule: Rule) -> pl.DataFrame:
    price_col = "up_price" if rule.side == "up" else "down_price"
    target_col = "target_up_win" if rule.side == "up" else "target_down_win"
    return (
        df.filter(rule.condition)
        .with_columns([
            pl.lit(rule.rule_id).alias("rule"),
            pl.lit(rule.side).alias("side"),
            (pl.col(price_col).cast(pl.Float64) + (pl.col("avg_spread").cast(pl.Float64) / 2)).clip(0.01, 0.99).alias("entry_price"),
            pl.col(target_col).cast(pl.Float64).alias("outcome"),
        ])
        .with_columns([
            (pl.col("outcome") - pl.col("entry_price")).alias("pnl_per_share"),
            (pl.col("outcome") == 1.0).alias("hit"),
        ])
        .sort(["market_id", "ts"])
        .group_by("market_id", maintain_order=True)
        .first()
        .select([
            "rule",
            "side",
            "market_id",
            "ts",
            "end_ts",
            "entry_price",
            "outcome",
            "pnl_per_share",
            "hit",
            "avg_spread",
        ])
    )


def split_by_market_time(signals: pl.DataFrame, train_fraction: float = 0.6) -> pl.DataFrame:
    if signals.is_empty():
        return signals.with_columns(pl.lit("none").alias("split"))
    markets = (
        signals.group_by("market_id")
        .agg(pl.col("end_ts").max().alias("market_end_ts"))
        .sort("market_end_ts")
        .with_row_index("market_index")
    )
    cutoff = int(markets.height * train_fraction)
    markets = markets.with_columns(
        pl.when(pl.col("market_index") < cutoff).then(pl.lit("train")).otherwise(pl.lit("oos")).alias("split")
    )
    return signals.join(markets.select(["market_id", "split", "market_index"]), on="market_id", how="left")


def stats(frame: pl.DataFrame) -> dict[str, Any]:
    if frame.is_empty():
        return {
            "trades": 0,
            "hitRate": 0.0,
            "netPnlPerShare": 0.0,
            "avgPnlPerShare": 0.0,
            "avgEntryPrice": 0.0,
            "avgSpread": 0.0,
        }
    row = frame.select([
        pl.len().alias("trades"),
        pl.col("hit").cast(pl.Float64).mean().alias("hitRate"),
        pl.col("pnl_per_share").sum().alias("netPnlPerShare"),
        pl.col("pnl_per_share").mean().alias("avgPnlPerShare"),
        pl.col("entry_price").mean().alias("avgEntryPrice"),
        pl.col("avg_spread").mean().alias("avgSpread"),
    ]).to_dicts()[0]
    return {
        "trades": int(row["trades"] or 0),
        "hitRate": round(float(row["hitRate"] or 0), 6),
        "netPnlPerShare": round(float(row["netPnlPerShare"] or 0), 6),
        "avgPnlPerShare": round(float(row["avgPnlPerShare"] or 0), 6),
        "avgEntryPrice": round(float(row["avgEntryPrice"] or 0), 6),
        "avgSpread": round(float(row["avgSpread"] or 0), 6),
    }


def rule_summary(rule: Rule, signals: pl.DataFrame) -> dict[str, Any]:
    split = split_by_market_time(signals)
    train = split.filter(pl.col("split") == "train")
    oos = split.filter(pl.col("split") == "oos")
    train_stats = stats(train)
    oos_stats = stats(oos)
    passes = (
        oos_stats["trades"] >= 40
        and oos_stats["avgPnlPerShare"] > 0.015
        and oos_stats["hitRate"] >= max(0.52, oos_stats["avgEntryPrice"] + 0.03)
        and oos_stats["avgSpread"] <= 0.08
    )
    return {
        "id": rule.rule_id,
        "side": rule.side,
        "oneVariable": rule.one_variable,
        "description": rule.description,
        "train": train_stats,
        "oos": oos_stats,
        "passesResearchContract": passes,
        "decision": "watch-research-only" if passes else "reject-current-fixed-rule",
        "promotionBlockers": [] if passes else [
            "fixed rule did not pass OOS trade count, net edge, hit-rate, and spread contract"
        ],
    }


def build_report(path: Path = DEFAULT_INPUT, max_spread: float = 0.08) -> dict[str, Any]:
    df = read_input(path)
    rules = fixed_rules(max_spread=max_spread)
    summaries: list[dict[str, Any]] = []
    for rule in rules:
        summaries.append(rule_summary(rule, signals_for_rule(df, rule)))
    watch = [item for item in summaries if item["passesResearchContract"]]
    return {
        "command": "prediction-btc-resolved-oos",
        "generatedAt": now_iso(),
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "readyForPaper": False,
        "readyForExecution": False,
        "input": str(path),
        "rows": df.height,
        "markets": df.select(pl.col("market_id").n_unique()).item(),
        "maxSpread": max_spread,
        "rules": summaries,
        "watchResearchCount": len(watch),
        "decision": "research-only-watch-candidates-present" if watch else "research-only-no-fixed-rule-edge",
        "nextAction": (
            "If any watch candidates exist, run stricter market-family walk-forward, fee model, and fillability review before paper."
            if watch else
            "Write fixed-rule BTC resolved corpus result to no-edge memory or test a genuinely different feature family."
        ),
        "hardRules": [
            "This is offline resolved-label research only.",
            "Do not paper/live trade from this artifact.",
            "Rows are repeated market observations; evaluation uses only the earliest qualifying signal per market per rule.",
            "No threshold may be loosened without creating a new no-edge-aware hypothesis.",
        ],
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Prediction BTC Resolved OOS - 2026-05-30",
        "",
        "Parent hub: [[BILL-CONTROL-HUB]]",
        "",
        f"Decision: `{report.get('decision')}`",
        f"Rows: `{report.get('rows')}`",
        f"Markets: `{report.get('markets')}`",
        f"Watch research count: `{report.get('watchResearchCount')}`",
        "",
        "Research-only. This page does not approve paper or live orders.",
        "",
        "## Fixed Rules",
        "",
        "| Rule | Side | Train avg pnl | OOS trades | OOS hit | OOS avg pnl | Decision |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for item in report.get("rules") or []:
        lines.append(
            f"| `{item['id']}` | `{item['side']}` | `{item['train']['avgPnlPerShare']}` | "
            f"`{item['oos']['trades']}` | `{item['oos']['hitRate']}` | `{item['oos']['avgPnlPerShare']}` | `{item['decision']}` |"
        )
    lines.extend(["", "## Hard Rules", ""])
    for rule in report.get("hardRules") or []:
        lines.append(f"- {rule}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run offline BTC resolved OOS prediction-market research.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))
    parser.add_argument("--max-spread", type=float, default=0.08)
    args = parser.parse_args()

    report = build_report(Path(args.input), max_spread=args.max_spread)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    markdown = Path(args.markdown)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    markdown.write_text(render_markdown(report))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
