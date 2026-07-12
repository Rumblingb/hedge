#!/usr/bin/env python3
"""Write futures no-edge memory from current futures triage artifacts.

Research-only. This records rejected futures hypotheses so future agents do
not keep promoting full-sample Backtrader rows after purged OOS/cost gates
have already rejected the branch.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge/state"
OUT_DIR = ROOT / ".rumbling-hedge/research/futures-no-edge-ledger"
LATEST = OUT_DIR / "latest.json"
HISTORY = OUT_DIR / "history.jsonl"


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def aggregate(item: dict[str, Any]) -> dict[str, Any]:
    data = item.get("aggregate") if isinstance(item.get("aggregate"), dict) else {}
    return {
        "trades": data.get("trades", 0),
        "winRate": data.get("winRate", 0),
        "netR": data.get("netR", 0),
        "profitFactor": data.get("profitFactor", 0),
        "maxDrawdownR": data.get("maxDrawdownR", 0),
    }


def rejected(item: dict[str, Any]) -> bool:
    return str(item.get("status", "")).startswith("reject")


def matrix_rejection_entry(matrix: dict[str, Any]) -> dict[str, Any] | None:
    if matrix.get("command") != "walkforward-matrix" or matrix.get("status") != "reject":
        return None
    comparison = matrix.get("comparison") if isinstance(matrix.get("comparison"), dict) else {}
    configs = matrix.get("configs") if isinstance(matrix.get("configs"), list) else []
    robust_count = int(comparison.get("robustConfigCount") or 0)
    if robust_count > 0:
        return None
    config_summaries = []
    selected_profiles: set[str] = set()
    for config in configs:
        if not isinstance(config, dict):
            continue
        stitched = config.get("stitchedOos") if isinstance(config.get("stitchedOos"), dict) else {}
        windows = config.get("windows") if isinstance(config.get("windows"), list) else []
        for window in windows:
            if isinstance(window, dict) and isinstance(window.get("selectedProfileId"), str):
                selected_profiles.add(window["selectedProfileId"])
        config_summaries.append({
            "configId": config.get("configId"),
            "windowsEvaluated": config.get("windowsEvaluated", 0),
            "totalTrades": stitched.get("totalTrades", 0),
            "netTotalR": stitched.get("netTotalR", 0),
            "profitFactor": stitched.get("profitFactor", 0),
            "maxDrawdownR": stitched.get("maxDrawdownR", 0),
            "failureModes": config.get("failureModes") or [],
        })
    if not config_summaries:
        return None
    return {
        "id": "six-market-walkforward-matrix-current-profile-family",
        "track": "futures",
        "hypothesis": "The current six-market walk-forward profile family is robust enough to guide demo/live expansion.",
        "verdict": "no-edge",
        "status": "research-only",
        "evidence": {
            "artifact": str(STATE / "walkforward-matrix.latest.json"),
            "generatedAt": matrix.get("generatedAt"),
            "csvPath": matrix.get("csvPath"),
            "bestConfigId": comparison.get("bestConfigId"),
            "robustConfigCount": robust_count,
            "commonFailureModes": comparison.get("commonFailureModes") or [],
            "selectedProfileIds": sorted(selected_profiles),
            "configSummaries": config_summaries,
        },
        "reasons": [
            "The refreshed walk-forward matrix rejected every current config.",
            "Robust config count is zero.",
            "Stitched OOS and contract failure modes block demo/live interpretation.",
        ],
        "nextAction": (
            "Do not rerun this exact profile family as promotion evidence. Continue only with a new data source, "
            "a materially different feature family, or a pre-registered one-variable branch."
        ),
    }


def entry_hypothesis_entries(entry_research: dict[str, Any]) -> list[dict[str, Any]]:
    if entry_research.get("command") != "entry-hypothesis-research":
        return []
    datasets = entry_research.get("datasets") if isinstance(entry_research.get("datasets"), list) else []
    by_hypothesis: dict[str, list[dict[str, Any]]] = {}
    for dataset in datasets:
        if not isinstance(dataset, dict):
            continue
        dataset_id = dataset.get("id")
        symbol = dataset.get("symbol")
        hypotheses = dataset.get("hypotheses") if isinstance(dataset.get("hypotheses"), list) else []
        for row in hypotheses:
            if not isinstance(row, dict) or not isinstance(row.get("id"), str):
                continue
            by_hypothesis.setdefault(row["id"], []).append({
                "datasetId": dataset_id,
                "symbol": symbol,
                "bars15m": dataset.get("bars15m"),
                "bars1m": dataset.get("bars1m"),
                "first15m": dataset.get("first15m"),
                "last15m": dataset.get("last15m"),
                "coveragePct": row.get("coveragePct"),
                "evidenceGrade": row.get("evidenceGrade"),
                "oos": row.get("oos") if isinstance(row.get("oos"), dict) else {},
                "blockers": row.get("blockers") if isinstance(row.get("blockers"), list) else [],
            })

    entries: list[dict[str, Any]] = []
    for hypothesis_id, rows in sorted(by_hypothesis.items()):
        positive_rows = [
            row for row in rows
            if float((row.get("oos") or {}).get("netPoints") or 0) > 0
            and float((row.get("oos") or {}).get("profitFactor") or 0) >= 1.25
            and int((row.get("oos") or {}).get("tradeCount") or 0) >= 30
        ]
        robust_rows = [
            row for row in positive_rows
            if "not-cross-dataset-robust" not in row.get("blockers", [])
            and "coverage-too-thin" not in row.get("blockers", [])
            and "too-few-oos-trades" not in row.get("blockers", [])
        ]
        if robust_rows:
            continue
        if positive_rows:
            verdict = "needs-new-feature"
            reasons = [
                "At least one historical slice is positive, but the hypothesis is not cross-dataset robust.",
                "Current broker/current-data parity is not cleared by historical research.",
                "Do not promote a single-slice winner; rerun only as a pre-registered broker-grade one-variable test.",
            ]
            next_action = (
                "Keep as a watch-only research branch. Re-run on overlapping broker-grade Topstep/ProjectX "
                "1m/3m/15m data and require independent current NQ confirmation before demo-shadow discussion."
            )
        else:
            verdict = "no-edge"
            reasons = [
                "No evaluated historical/current slice produced enough positive OOS evidence after costs.",
                "The current form is rejected as a standalone futures entry/exit rule.",
            ]
            next_action = (
                "Do not rerun this exact branch as promotion evidence. Continue only if a materially different "
                "feature or data source is pre-registered."
            )
        entries.append({
            "id": f"entry-hypothesis-{hypothesis_id}",
            "track": "futures",
            "hypothesis": f"Entry hypothesis `{hypothesis_id}` improves NQ/ES futures execution timing robustly enough for demo-shadow review.",
            "verdict": verdict,
            "status": "research-only",
            "evidence": {
                "artifact": str(STATE / "entry-hypothesis-research.latest.json"),
                "generatedAt": entry_research.get("generatedAt"),
                "decision": entry_research.get("decision"),
                "datasets": rows,
                "positiveDatasetCount": len(positive_rows),
                "robustDatasetCount": len(robust_rows),
                "globalBlockers": entry_research.get("globalBlockers") or [],
            },
            "reasons": reasons,
            "nextAction": next_action,
        })
    return entries


def build_entries(
    triage: dict[str, Any],
    cot_research: dict[str, Any] | None = None,
    walkforward_matrix: dict[str, Any] | None = None,
    gex_backtest: dict[str, Any] | None = None,
    entry_hypothesis_research: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    vol = triage.get("volRegimeOos") if isinstance(triage.get("volRegimeOos"), dict) else {}
    inverse = triage.get("volRegimeInverseOos") if isinstance(triage.get("volRegimeInverseOos"), dict) else {}
    lower = triage.get("volRegimeLowerTimeframeOos") if isinstance(triage.get("volRegimeLowerTimeframeOos"), dict) else {}
    cost_gate = triage.get("costSlippageGate") if isinstance(triage.get("costSlippageGate"), dict) else {}

    if rejected(vol) and rejected(inverse):
        entries.append({
            "id": "wq-vol-regime-60m-current-form",
            "track": "futures",
            "hypothesis": "The current 60m WQ vol-regime rule has a durable NQ edge in normal or inverse direction.",
            "verdict": "no-edge",
            "status": "research-only",
            "evidence": {
                "normal": aggregate(vol),
                "normalBlockers": vol.get("blockers") or [],
                "inverse": aggregate(inverse),
                "inverseBlockers": inverse.get("blockers") or [],
            },
            "reasons": [
                "Normal 60m vol-regime failed purged OOS.",
                "Inverse 60m vol-regime failed the same purged OOS contract.",
                "Parameter-only reruns are not new evidence.",
            ],
            "nextAction": "Retire this exact 60m rule form until a new data source or materially different structural feature exists.",
        })

    for timeframe, item in sorted(lower.items()):
        if not isinstance(item, dict) or not rejected(item):
            continue
        agg = aggregate(item)
        verdict = "needs-new-feature" if float(agg.get("netR") or 0) > 0 else "no-edge"
        entries.append({
            "id": f"wq-vol-regime-{timeframe}-current-form",
            "track": "futures",
            "hypothesis": f"Lower-timeframe {timeframe} WQ vol-regime improves sample depth enough to pass OOS promotion.",
            "verdict": verdict,
            "status": "research-only",
            "evidence": {
                "aggregate": agg,
                "blockers": item.get("blockers") or [],
                "worstWindows": item.get("worstWindows") or [],
            },
            "reasons": [
                f"{timeframe} branch remains rejected by current OOS contract.",
                "Lower sample depth alone is not enough unless PF, positive-window ratio, and costs pass.",
            ],
            "nextAction": "Continue only with a materially different filter/feature; do not mine parameters on the same rejected rule.",
        })

    if cost_gate.get("readyForDemoExpansion") is False and int(cost_gate.get("volRegimeOosSurvivors") or 0) == 0:
        entries.append({
            "id": "backtrader-full-sample-survivors-with-zero-vol-oos-survivors",
            "track": "futures",
            "hypothesis": "Full-sample Backtrader cost/slippage survivors are enough to seed demo expansion.",
            "verdict": "no-edge",
            "status": "research-only",
            "evidence": {
                "backtraderSurvivors": cost_gate.get("backtraderSurvivors", 0),
                "volRegimeOosSurvivors": cost_gate.get("volRegimeOosSurvivors", 0),
                "readyForDemoExpansion": cost_gate.get("readyForDemoExpansion", False),
                "failureCounts": cost_gate.get("failureCounts") or {},
            },
            "reasons": [
                "Full-sample rows are hypothesis seeds only.",
                "Zero vol-regime OOS artifacts survive the current cost/window stress gate.",
            ],
            "nextAction": "Require purged OOS survivors before any Backtrader row can enter demo-shadow or expansion review.",
        })

    matrix_entry = matrix_rejection_entry(walkforward_matrix if isinstance(walkforward_matrix, dict) else {})
    if matrix_entry:
        entries.append(matrix_entry)

    cot_research = cot_research if isinstance(cot_research, dict) else {}
    cot_summary = cot_research.get("summary") if isinstance(cot_research.get("summary"), dict) else {}
    cot_inputs = cot_research.get("inputs") if isinstance(cot_research.get("inputs"), dict) else {}
    if cot_research.get("command") == "cot-regime-filter-research" and int(cot_summary.get("improvedPositiveRows") or 0) == 0:
        entries.append({
            "id": "cot-tff-regime-filter-current-backtrader-set",
            "track": "futures",
            "hypothesis": "Weekly CFTC/TFF positioning improves the current NQ Backtrader strategy set when added as the only regime gate.",
            "verdict": "no-edge",
            "status": "research-only",
            "evidence": {
                "artifact": str(STATE / "cot-regime-filter-research.latest.json"),
                "rows": cot_summary.get("rows", 0),
                "improvedPositiveRows": cot_summary.get("improvedPositiveRows", 0),
                "decision": cot_summary.get("decision", "missing"),
                "releaseLagDays": cot_inputs.get("releaseLagDays"),
                "oneVariable": cot_inputs.get("oneVariable"),
            },
            "reasons": [
                "The COT gate did not create any positive full-sample improvement rows with enough trades.",
                "Strict alignment mostly helped by blocking trades entirely in losing configurations, which is not a tradable edge.",
                "COT is weekly and lagged; it remains context unless a future OOS artifact proves otherwise.",
            ],
            "nextAction": "Keep COT as research context only; revisit only with a materially different strategy family or longer OOS sample.",
        })

    gex_backtest = gex_backtest if isinstance(gex_backtest, dict) else {}
    gex_metrics = gex_backtest.get("metrics") if isinstance(gex_backtest.get("metrics"), dict) else {}
    sign_atm = gex_metrics.get("signAtmGex") if isinstance(gex_metrics.get("signAtmGex"), dict) else {}
    buy_hold = gex_metrics.get("buyHold") if isinstance(gex_metrics.get("buyHold"), dict) else {}
    if gex_backtest.get("decision") == "research-only-gex-backtest-complete" and sign_atm and buy_hold:
        sign_sharpe = sign_atm.get("sharpe")
        buy_hold_sharpe = buy_hold.get("sharpe")
        sign_mean = float(sign_atm.get("meanDailyReturn") or 0)
        buy_hold_mean = float(buy_hold.get("meanDailyReturn") or 0)
        sign_loses_to_baseline = (
            sign_sharpe is not None
            and buy_hold_sharpe is not None
            and float(sign_sharpe) <= float(buy_hold_sharpe)
        ) or sign_mean <= buy_hold_mean
        if sign_loses_to_baseline:
            entries.append({
                "id": "gex-sign-atm-standalone-index-futures-proxy",
                "track": "futures",
                "hypothesis": "The sign of daily ATM SPY GEX alone predicts next-session index futures/proxy returns strongly enough to trade.",
                "verdict": "no-edge",
                "status": "research-only",
                "evidence": {
                    "artifact": str(STATE / "gex-backtest.latest.json"),
                    "decision": gex_backtest.get("decision"),
                    "dateRange": gex_metrics.get("dateRange"),
                    "rows": gex_metrics.get("rows"),
                    "signAtmGex": sign_atm,
                    "buyHold": buy_hold,
                    "rankGex": gex_metrics.get("rankGex"),
                    "nearGammaFlip": gex_metrics.get("nearGammaFlip"),
                    "farFromGammaFlip": gex_metrics.get("farFromGammaFlip"),
                },
                "reasons": [
                    "Standalone sign(ATM GEX) underperformed the buy-hold proxy on long-window Sharpe/return.",
                    "Daily GEX is slow regime context, not intraday execution timing for NQ/ES.",
                    "Any future use must prove incremental OOS lift as a one-variable overlay, not a standalone signal.",
                ],
                "nextAction": (
                    "Keep GEX as an options/regime context candidate only. Retest only as a pre-registered overlay "
                    "on an already positive futures rule with purged OOS, cost/slippage, and broker-grade replay."
                ),
            })

    entries.extend(entry_hypothesis_entries(entry_hypothesis_research if isinstance(entry_hypothesis_research, dict) else {}))

    return entries


def merge_entries(previous: list[dict[str, Any]], current: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for entry in previous:
        entry_id = entry.get("id")
        if isinstance(entry_id, str) and entry_id:
            merged[entry_id] = entry
    for entry in current:
        entry_id = entry.get("id")
        if not isinstance(entry_id, str) or not entry_id:
            continue
        prior = merged.get(entry_id)
        prior_is_no_edge = prior and prior.get("verdict") == "no-edge"
        current_clears_prior = entry.get("retestPassed") is True or bool(entry.get("supersededBy"))
        if prior_is_no_edge and entry.get("verdict") != "no-edge" and not current_clears_prior:
            retained = dict(prior)
            retained["lastSeenAt"] = entry.get("generatedAt") or datetime.now(timezone.utc).isoformat()
            retained["retainedReason"] = "Prior no-edge verdict retained until an explicit retestPassed or supersededBy clearance exists."
            merged[entry_id] = retained
            continue
        merged[entry_id] = entry
    return sorted(merged.values(), key=lambda item: str(item.get("id", "")))


def count_verdict(entries: list[dict[str, Any]], verdict: str) -> int:
    return sum(1 for entry in entries if entry.get("verdict") == verdict)


def main() -> int:
    triage = read_json(STATE / "futures-evidence-triage.latest.json")
    cot_research = read_json(STATE / "cot-regime-filter-research.latest.json")
    walkforward_matrix = read_json(STATE / "walkforward-matrix.latest.json")
    gex_backtest = read_json(STATE / "gex-backtest.latest.json")
    entry_hypothesis_research = read_json(STATE / "entry-hypothesis-research.latest.json")
    now = datetime.now(timezone.utc).isoformat()
    current_entries = build_entries(triage, cot_research, walkforward_matrix, gex_backtest, entry_hypothesis_research)
    previous_entries = read_json(LATEST).get("entries", [])
    if not isinstance(previous_entries, list):
        previous_entries = []
    entries = merge_entries(previous_entries, current_entries)
    no_edge_count = count_verdict(entries, "no-edge")
    needs_new_feature_count = count_verdict(entries, "needs-new-feature")
    learning_summary = [
        f"futures entries={len(entries)}, noEdge={no_edge_count}, needsNewFeature={needs_new_feature_count}",
        "Current vol-regime 60m normal/inverse forms are rejected by purged OOS.",
        "Full-sample Backtrader survivors are not promotion evidence without OOS survivors.",
    ]
    if any(entry.get("id") == "six-market-walkforward-matrix-current-profile-family" for entry in entries):
        learning_summary.append("The current six-market walk-forward matrix profile family is rejected; rerun only as a changed hypothesis, not promotion evidence.")
    if any(entry.get("id") == "cot-tff-regime-filter-current-backtrader-set" for entry in entries):
        learning_summary.append("COT/TFF regime gating of the current Backtrader set is negative memory; keep COT contextual until fresh OOS proves otherwise.")
    if any(entry.get("id") == "gex-sign-atm-standalone-index-futures-proxy" for entry in entries):
        learning_summary.append("Standalone sign-of-ATM-GEX is negative memory; use GEX only as a pre-registered overlay candidate.")
    if any(str(entry.get("id", "")).startswith("entry-hypothesis-") for entry in entries):
        learning_summary.append("Entry-hypothesis research is now in no-edge memory; single-slice winners remain watch-only until broker-grade/current and cross-dataset confirmation exists.")
    payload = {
        "command": "futures-no-edge-ledger",
        "generatedAt": now,
        "decision": "research-only-futures-no-edge-memory",
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "readyForExecution": False,
        "readyForDemoExpansion": False,
        "count": len(entries),
        "noEdgeCount": no_edge_count,
        "needsNewFeatureCount": needs_new_feature_count,
        "promotableCount": count_verdict(entries, "promotable"),
        "entries": entries,
        "learningSummary": learning_summary,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    LATEST.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    with HISTORY.open("a") as fh:
        fh.write(json.dumps(payload, sort_keys=True) + "\n")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
