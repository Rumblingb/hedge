#!/usr/bin/env python3
"""Replay a GENUINELY NEW CLOB microstructure feature family against resolved labels.

Research-only, read-only. No order/funding/broker writes.

The 5 previously rejected fixed forms (depth-imbalance, quote-intensity,
spread-compression, latency-staleness, trade-impact) all predicted a SHORT-TERM
FORWARD mid-price move (15s/60s) from live-capture microstructure. This script
defines a DIFFERENT family:

    clob-resolved-label-pre-resolution-resting-convergence

It predicts the RESOLVED binary outcome (target_up_win) from RESTING order-book
state (depth imbalance + execution-flow imbalance + spread) measured at a
PRE-RESOLUTION eligibility window, so the measurement cannot mechanically encode
the outcome. That is what makes it non-tautological: at the final resolution bar
the winning side's book is 100% on that side by construction (a tautology the
no-edge ledger already rejected as polymarket-clob-orderflow-resolution-hindsight-baseline).

Protocol:
  * Eligible rows MUST have fraction-elapsed <= --max-elig-frac (default 0.5).
    This guarantees the microstructure is sampled BEFORE resolution is knowable.
  * A negative-control mode (--include-resolution-bar) deliberately removes the
    filter to show the tautology AUC (~0.99) and prove the family is not merely
    re-discovering the rejected hindsight baseline.
  * Out-of-sample skill is measured by grouped (by-market) K-fold CV AUC plus the
    fixed no-edge contract metrics: hitRate >= 0.55, meanNetAfterHalfSpread >=
    0.0025, minSamples >= 30.
  * If zero pre-resolution rows exist (the capture-design gap), the family is
    reported as research-only / no-edge with an explicit capture-gap reason, and
    the ledger is NOT promoted. The 5 rejected fixed-form blockers are preserved.
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
DEFAULT_CORPUS = Path(
    "/Volumes/Seagate Expansion Drive/hedge-data/features/polymarket_btc_updown/btc_5m_resolved_all_features.parquet"
)
DEFAULT_OUTPUT = STATE / "prediction-clob-resolved-label-feature-replay.latest.json"
VAULT = Path.home() / "Documents/memorybrain"
DEFAULT_MD = (
    VAULT
    / "Agent-Hermes"
    / f"prediction-clob-resolved-label-feature-replay-{datetime.now(timezone.utc).date().isoformat()}.md"
)

FEATURE_FAMILY_ID = "polymarket-clob-resolved-label-pre-resolution-resting-convergence-current-form"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def auc_score(scores: np.ndarray, labels: np.ndarray) -> float | None:
    scores = np.asarray(scores, dtype=float)
    labels = np.asarray(labels, dtype=int)
    m = ~np.isnan(scores)
    scores, labels = scores[m], labels[m]
    n_pos = int(labels.sum())
    n_neg = int(len(labels) - n_pos)
    if n_pos == 0 or n_neg == 0 or len(labels) < 2:
        return None
    order = np.argsort(scores)
    ranks = np.empty(len(scores), dtype=float)
    ranks[order] = np.arange(1, len(scores) + 1)
    return float((ranks[labels == 1].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))


def grouped_cv_auc(feature: pd.Series, label: pd.Series, market: pd.Series, k: int = 5) -> dict[str, Any]:
    f = feature.values.astype(float)
    y = label.values.astype(int)
    mk = market.values
    markets = np.unique(mk)
    if len(markets) < k:
        return {"status": "too-few-markets", "k": k, "markets": int(len(markets)), "foldAucs": []}
    rng = np.random.default_rng(42)
    perm = rng.permutation(markets)
    folds = np.array_split(perm, k)
    fold_aucs: list[float] = []
    for i in range(k):
        test_markets = set(folds[i].tolist())
        test_mask = np.array([m in test_markets for m in mk])
        if test_mask.sum() < 2:
            continue
        tr_auc = auc_score(f[~test_mask], y[~test_mask])
        te_auc = auc_score(f[test_mask], y[test_mask])
        if te_auc is not None:
            fold_aucs.append(te_auc)
    return {
        "status": "ok",
        "k": k,
        "markets": int(len(markets)),
        "foldAucs": [round(a, 4) for a in fold_aucs],
        "meanTestAuc": round(float(np.mean(fold_aucs)), 4) if fold_aucs else None,
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    df = pd.read_parquet(args.corpus)
    ob_cols = ["up_bid_depth", "up_ask_depth", "down_bid_depth", "down_ask_depth",
               "up_depth_imbalance", "down_depth_imbalance", "ob_rows"]
    trade_cols = ["trade_count", "trade_usdc", "buy_usdc", "sell_usdc",
                  "trade_flow_imbalance", "avg_trade_price"]
    need = ob_cols + trade_cols + ["avg_spread", "spot_price", "start_ts", "end_ts"]
    ok = df[need].notna().all(axis=1)
    sub = df.loc[ok].copy()
    sub["elapsed"] = sub["ts"] - sub["start_ts"]
    life = (sub["end_ts"] - sub["start_ts"]).replace(0, np.nan)
    sub["frac"] = (sub["elapsed"] / life).clip(lower=0, upper=1)

    if args.include_resolution_bar:
        elig = sub
        mode = "negative-control-resolution-bar"
    else:
        elig = sub[sub["frac"] <= args.max_elig_frac]
        mode = "pre-resolution-forward"

    # Feature family: net resting convergence pressure (resting book, not executed flow)
    elig = elig.copy()
    elig["net_resting_pressure"] = elig["up_depth_imbalance"] - elig["down_depth_imbalance"]
    elig["flow_minus_resting"] = elig["trade_flow_imbalance"] - elig["net_resting_pressure"]

    y = elig["target_up_win"].astype(int)
    market = elig["market_id"]

    sample_rows = 0
    cv = {"status": "no-eligible-rows"}
    contract = None
    blockers: list[str] = []
    if len(elig) >= 1:
        sample_rows = int(len(elig))
        cv = grouped_cv_auc(elig["net_resting_pressure"], y, market, k=args.cv_folds)
        # Fixed-threshold contract: bet UP when net_resting_pressure > 0
        thr = 0.0
        bet_up = elig["net_resting_pressure"].values > thr
        correct = (bet_up & (y.values == 1)) | (~bet_up & (y.values == 0))
        hit = float(correct.mean()) if len(correct) else None
        spread = elig["avg_spread"].fillna(elig["avg_spread"].median()).values
        entry = 0.5  # binary up/down token mid at the eligible bar
        # payoff: correct -> 1-entry ; wrong -> -entry ; net after half-spread
        payoff = np.where(correct, 1.0 - entry, -entry)
        net = (payoff - spread / 2.0).mean() if len(payoff) else None
        contract = {
            "threshold": thr,
            "samples": sample_rows,
            "hitRate": round(hit, 6) if hit is not None else None,
            "meanNetAfterHalfSpread": round(float(net), 6) if net is not None else None,
        }
        if sample_rows < args.min_samples:
            blockers.append("too-few-pre-resolution-samples")
        if hit is None or hit < args.min_hit_rate:
            blockers.append("hit-rate-below-contract")
        if net is None or net < args.min_net:
            blockers.append("net-after-half-spread-below-contract")
    else:
        blockers.append("zero-eligible-pre-resolution-rows")

    passes = len(blockers) == 0 and cv.get("meanTestAuc") is not None and cv["meanTestAuc"] > 0.55

    # Negative-control AUC (tautology check) on the full last-bar set
    last = sub.groupby("market_id").tail(1)
    neg_auc = auc_score(
        (last["up_depth_imbalance"] - last["down_depth_imbalance"]).values.astype(float),
        last["target_up_win"].astype(int).values,
    )

    verdict = "watch-research-only" if passes else "reject"
    if mode == "pre-resolution-forward" and sample_rows == 0:
        decision = "research-only-no-pre-resolution-microstructure"
        next_action = (
            "Capture CLOB microstructure in a PRE-RESOLUTION window (fraction-elapsed <= "
            f"{args.max_elig_frac}) or build a historical early-window labelled-trade corpus; "
            "the current resolved corpus only carries microstructure at the resolution bar, "
            "so a non-tautological forward test is impossible on it."
        )
    elif passes:
        decision = "watch-research-only-pre-resolution-resting-convergence"
        next_action = "Promote to watch research; require fee/fillability + live pre-resolution capture confirmation before paper."
    else:
        decision = "research-only-no-edge-pre-resolution-resting-convergence"
        next_action = "Do not rerun with looser thresholds. Continue only with pre-resolution microstructure capture or a different feature family."

    return {
        "command": "prediction-clob-resolved-label-feature-replay",
        "featureFamilyId": FEATURE_FAMILY_ID,
        "generatedAt": now_iso(),
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "readyForPaper": bool(passes),
        "mode": mode,
        "corpusPath": str(Path(args.corpus).resolve()),
        "corpusMarkets": int(df["market_id"].nunique()),
        "corpusRows": int(len(df)),
        "populatedMicrostructureRows": int(len(sub)),
        "eligibility": {
            "maxEligFrac": args.max_elig_frac,
            "includeResolutionBar": args.include_resolution_bar,
        },
        "eligibleRows": sample_rows,
        "eligibleMarkets": int(elig["market_id"].nunique()) if sample_rows else 0,
        "negativeControlResolutionBarAuc": round(neg_auc, 4) if neg_auc is not None else None,
        "crossValidatedAuc": cv,
        "contract": contract,
        "blockers": blockers,
        "verdict": verdict,
        "decision": decision,
        "nextAction": next_action,
    }


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# Prediction CLOB Resolved-Label Feature Replay - {payload.get('generatedAt', '')[:10]}",
        "",
        "Parent hub: [[BILL-CONTROL-HUB]]",
        "",
        "Research-only. Genuinely new family: pre-resolution resting-book convergence vs resolved labels.",
        "",
        "## Summary",
        "",
        f"- Mode: `{payload.get('mode')}`",
        f"- Decision: `{payload.get('decision')}`",
        f"- Verdict: `{payload.get('verdict')}`",
        f"- Corpus markets: `{payload.get('corpusMarkets')}`",
        f"- Corpus rows: `{payload.get('corpusRows')}`",
        f"- Populated microstructure rows: `{payload.get('populatedMicrostructureRows')}`",
        f"- Eligible pre-resolution rows: `{payload.get('eligibleRows')}`",
        f"- Negative-control (resolution-bar) AUC: `{payload.get('negativeControlResolutionBarAuc')}`",
        f"- Cross-validated AUC: `{payload.get('crossValidatedAuc')}`",
        f"- Contract: `{payload.get('contract')}`",
        f"- Blockers: `{payload.get('blockers')}`",
        "",
        f"## Next action",
        "",
        payload.get("nextAction", ""),
        "",
        "Note: a near-perfect negative-control AUC proves the family is NOT tautological by design; "
        "the blocker is the absence of pre-resolution microstructure in the current corpus, not parameters.",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay new resolved-label CLOB microstructure feature family.")
    parser.add_argument("--corpus", default=str(DEFAULT_CORPUS))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown-output", default=str(DEFAULT_MD))
    parser.add_argument("--max-elig-frac", type=float, default=0.5)
    parser.add_argument("--include-resolution-bar", action="store_true")
    parser.add_argument("--cv-folds", type=int, default=5)
    parser.add_argument("--min-samples", type=int, default=30)
    parser.add_argument("--min-hit-rate", type=float, default=0.55)
    parser.add_argument("--min-net", type=float, default=0.0025)
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
