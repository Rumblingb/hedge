#!/usr/bin/env python3
"""Write prediction-market no-edge memory from current triage artifacts.

Research-only. This records rejected prediction-market hypotheses so future
agents do not recreate paper candidates by loosening thresholds.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge/state"
OUT_DIR = ROOT / ".rumbling-hedge/research/prediction-no-edge-ledger"
LATEST = OUT_DIR / "latest.json"
HISTORY = OUT_DIR / "history.jsonl"


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def best_btc_fixed_rule(btc_oos: dict[str, Any]) -> dict[str, Any]:
    rules = btc_oos.get("rules") if isinstance(btc_oos.get("rules"), list) else []
    best: dict[str, Any] = {}
    best_score = -10**9
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        oos = rule.get("oos") if isinstance(rule.get("oos"), dict) else {}
        score = float(oos.get("avgPnlPerShare") or 0) * max(int(oos.get("trades") or 0), 1)
        if score > best_score:
            best = rule
            best_score = score
    return best


def build_entries(
    triage: dict[str, Any],
    narrow_scan: dict[str, Any] | None = None,
    btc_oos: dict[str, Any] | None = None,
    clob_depth_replay: dict[str, Any] | None = None,
    event_lag_replay: dict[str, Any] | None = None,
    clob_quote_intensity_replay: dict[str, Any] | None = None,
    clob_spread_compression_replay: dict[str, Any] | None = None,
    clob_latency_staleness_replay: dict[str, Any] | None = None,
    clob_trade_impact_replay: dict[str, Any] | None = None,
    macro_rates_cross_source_replay: dict[str, Any] | None = None,
    clob_trade_resolved_join: dict[str, Any] | None = None,
    clob_orderflow_resolution: dict[str, Any] | None = None,
    clob_edge_gate: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    narrow_scan = narrow_scan or {}
    btc_oos = btc_oos or {}
    clob_depth_replay = clob_depth_replay or {}
    clob_quote_intensity_replay = clob_quote_intensity_replay or {}
    clob_spread_compression_replay = clob_spread_compression_replay or {}
    clob_latency_staleness_replay = clob_latency_staleness_replay or {}
    clob_trade_impact_replay = clob_trade_impact_replay or {}
    macro_rates_cross_source_replay = macro_rates_cross_source_replay or {}
    event_lag_replay = event_lag_replay or {}
    clob_trade_resolved_join = clob_trade_resolved_join or {}
    clob_orderflow_resolution = clob_orderflow_resolution or {}
    clob_edge_gate = clob_edge_gate or {}
    clob = clob_edge_gate if clob_edge_gate.get("command") == "polymarket-clob-edge-gate" else (triage.get("clobEdgeGate") or {})
    blocker_counts = clob.get("blockerCounts") or {}
    resolved_join = triage.get("resolvedOutcomeJoin") or {}
    resolved_review = triage.get("resolvedOutcomeReview") or {}
    narrow_summary = narrow_scan.get("summary") if isinstance(narrow_scan.get("summary"), dict) else {}
    selected_categories = narrow_scan.get("selectedCategories") if isinstance(narrow_scan.get("selectedCategories"), list) else []
    if clob.get("status") == "REJECT_NO_EDGE":
        entries.append({
            "id": "polymarket-clob-drift-persistence-current-thresholds",
            "track": "prediction-markets",
            "hypothesis": "Short-window Polymarket CLOB quote/trade drift should predict near-term direction strongly enough to create watch/paper candidates.",
            "verdict": "no-edge",
            "status": "research-only",
            "evidence": {
                "rowsRead": clob.get("rowsRead", 0),
                "scoredGroups": clob.get("scoredGroups", 0),
                "watchResearchGroups": clob.get("watchResearchGroups", 0),
                "readyForPaper": clob.get("readyForPaper", False),
                "blockerCounts": blocker_counts,
            },
            "reasons": [
                "CLOB edge gate returned REJECT_NO_EDGE.",
                f"Net drift below threshold in {blocker_counts.get('net-drift-below-threshold', 0)} scored groups.",
                f"Directional hit rate too low in {blocker_counts.get('directional-hit-rate-too-low', 0)} scored groups.",
                f"Too few samples in {blocker_counts.get('too-few-samples', 0)} scored groups.",
            ],
            "nextAction": "Do not lower thresholds to create paper candidates. Retest only with longer capture, a different microstructure feature, or resolved-outcome joined labels.",
        })
    review = triage.get("review") or {}
    if (review.get("counts") or {}).get("paper-trade", 0) == 0:
        entries.append({
            "id": "broad-cross-venue-prediction-scan-current-normalization",
            "track": "prediction-markets",
            "hypothesis": "Broad Polymarket/Kalshi/Manifold scan should find same-horizon cross-venue watch or paper candidates.",
            "verdict": "needs-more-data",
            "status": "research-only",
            "evidence": {
                "venueCounts": review.get("venueCounts") or {},
                "counts": review.get("counts") or {},
                "blockers": review.get("blockers") or [],
                "resolvedOutcomeJoin": {
                    "statusCounts": resolved_join.get("statusCounts") or {},
                    "joinedResearchOnlyCount": resolved_join.get("joinedResearchOnlyCount", 0),
                    "minSpecificMatches": resolved_join.get("minSpecificMatches"),
                    "subjectSpecificCounts": resolved_join.get("subjectSpecificCounts") or [],
                    "readyForPaper": resolved_join.get("readyForPaper", False),
                },
            },
            "reasons": [
                "Venue coverage is healthy but zero watch candidates cleared review.",
                "Current scan needs narrower universe, better semantic matching, or market-family resolution history.",
                "Resolved-outcome joins must be subject-specific; broad family history alone is not paper evidence.",
            ],
            "nextAction": "Run narrow category scans and join watchlist to market-specific resolved outcomes before any paper promotion.",
        })
    if resolved_review.get("decision") == "do-not-promote-resolved-history-without-paper-review-and-fillability":
        item_decisions = [
            str(item.get("decision"))
            for item in (resolved_review.get("items") or [])
            if isinstance(item, dict)
        ]
        if item_decisions and all(decision in {
            "insufficient-market-family-history",
            "insufficient-subject-specific-history",
            "context-only-not-paper",
            "not-paper-ready",
        } for decision in item_decisions):
            entries.append({
                "id": "resolved-outcome-current-watchlist-context-only",
                "track": "prediction-markets",
                "hypothesis": "Current watchlist resolved-outcome joins should provide enough subject-specific evidence to promote prediction candidates.",
                "verdict": "needs-more-data",
                "status": "research-only",
                "currentFormRejected": True,
                "evidence": {
                    "decision": resolved_review.get("decision"),
                    "broadPriorRisk": resolved_review.get("broadPriorRisk"),
                    "joinedResearchOnlyCount": resolved_review.get("joinedResearchOnlyCount", 0),
                    "readyForPaper": resolved_review.get("readyForPaper", False),
                    "marketSpecificCoverage": resolved_review.get("marketSpecificCoverage") or {},
                    "itemDecisions": [
                        {
                            "externalId": item.get("externalId"),
                            "decision": item.get("decision"),
                            "resolvedMatchCount": item.get("resolvedMatchCount"),
                            "subjectSpecificMatchCount": item.get("subjectSpecificMatchCount"),
                            "subjectSpecificWinRate": item.get("subjectSpecificWinRate"),
                        }
                        for item in (resolved_review.get("items") or [])
                        if isinstance(item, dict)
                    ],
                },
                "reasons": [
                    "Resolved-outcome review stayed research-only and did not produce a paper-ready candidate.",
                    "Iran agreement/peace items have insufficient subject-specific history.",
                    "Argentina World Cup history is context-only without fillability, spread/fee, promotion, and market-specific paper evidence.",
                ],
                "nextAction": "Do not rerun the same resolved-outcome review as promotion evidence. Continue only with new resolved labels/source coverage, a new watchlist, or a genuinely new feature family.",
            })
    if narrow_summary and narrow_summary.get("watchCandidates", 0) == 0 and narrow_summary.get("paperCandidates", 0) == 0:
        entries.append({
            "id": "narrow-category-cross-venue-current-universe",
            "track": "prediction-markets",
            "hypothesis": "Narrow category scans should reveal same-horizon cross-venue watch or paper candidates without lowering thresholds.",
            "verdict": "needs-more-data",
            "status": "research-only",
            "evidence": {
                "categoryCount": narrow_summary.get("categoryCount", 0),
                "watchCandidates": narrow_summary.get("watchCandidates", 0),
                "paperCandidates": narrow_summary.get("paperCandidates", 0),
                "viablePairs": narrow_summary.get("viablePairs", 0),
                "repairableNearMisses": narrow_summary.get("repairableNearMisses", 0),
                "selectedCategories": selected_categories,
                "readyForPaper": narrow_scan.get("readyForPaper", False),
                "categoryRejectReasons": {
                    str(report.get("category")): ((report.get("diagnostics") or {}).get("rejectReasons") or {})
                    for report in narrow_scan.get("reports", [])
                    if isinstance(report, dict)
                },
            },
            "reasons": [
                "Current category-narrow scans produced zero watch and zero paper candidates.",
                "No viable cross-venue pair survived same-horizon, semantic, line, and market-type checks.",
                "Repairable near misses remain research seeds only until a single parser or settlement-horizon variable improves them.",
            ],
            "nextAction": "Retest only one category/parser variable at a time, starting with crypto settlement horizon or macro/rates line parsing; do not broaden thresholds.",
        })
        crypto_rejects = (
            narrow_scan.get("reports", [{}])[0].get("diagnostics", {}).get("rejectReasons", {})
            if len(selected_categories) == 1 and selected_categories[0] == "crypto" and isinstance(narrow_scan.get("reports"), list) and narrow_scan.get("reports")
            else {}
        )
        if selected_categories == ["crypto"] and crypto_rejects.get("temporal-mismatch", 0) > 0:
            entries.append({
                "id": "crypto-settlement-horizon-parser-current-form",
                "track": "prediction-markets",
                "hypothesis": "Crypto snapshot-day markets can be safely normalized against broader month-long BTC touch/ladder mirrors.",
                "verdict": "no-edge",
                "status": "research-only",
                "evidence": {
                    "selectedCategories": selected_categories,
                    "categoryCount": narrow_summary.get("categoryCount", 0),
                    "watchCandidates": narrow_summary.get("watchCandidates", 0),
                    "paperCandidates": narrow_summary.get("paperCandidates", 0),
                    "viablePairs": narrow_summary.get("viablePairs", 0),
                    "repairableNearMisses": narrow_summary.get("repairableNearMisses", 0),
                    "cryptoRejectReasons": crypto_rejects,
                    "safetyTest": "tests/predictionScanner.test.ts rejects snapshot-day contracts against broader month-long mirrors",
                },
                "reasons": [
                    "Crypto-only retest produced zero watch and zero paper candidates.",
                    "The top near misses are intentionally blocked by temporal mismatch between snapshot-day BTC markets and broader month-long BTC mirrors.",
                    "Relaxing this parser would weaken an existing safety test and likely manufacture false cross-venue edges.",
                ],
                "nextAction": "Do not relax crypto settlement horizon parsing from this evidence. Move the next one-variable prediction retest to macro/rates line parsing or another independently sourced feature.",
            })
        macro_rejects = (
            narrow_scan.get("reports", [{}])[0].get("diagnostics", {}).get("rejectReasons", {})
            if len(selected_categories) == 1 and selected_categories[0] == "macro-rates" and isinstance(narrow_scan.get("reports"), list) and narrow_scan.get("reports")
            else {}
        )
        if selected_categories == ["macro-rates"] and narrow_summary.get("repairableNearMisses", 0) == 0 and macro_rejects.get("market-type-mismatch", 0) > 0:
            entries.append({
                "id": "macro-rates-line-parser-current-form",
                "track": "prediction-markets",
                "hypothesis": "Macro/rates near misses can be repaired primarily by changing line parsing while keeping market-type, outcome, temporal, spread, and fee gates unchanged.",
                "verdict": "no-edge",
                "status": "research-only",
                "evidence": {
                    "selectedCategories": selected_categories,
                    "categoryCount": narrow_summary.get("categoryCount", 0),
                    "watchCandidates": narrow_summary.get("watchCandidates", 0),
                    "paperCandidates": narrow_summary.get("paperCandidates", 0),
                    "viablePairs": narrow_summary.get("viablePairs", 0),
                    "repairableNearMisses": narrow_summary.get("repairableNearMisses", 0),
                    "macroRatesRejectReasons": macro_rejects,
                },
                "reasons": [
                    "Macro/rates-only retest produced zero viable, watch, and paper candidates.",
                    "The top near misses are different economic events, especially Fed-decision markets versus CPI-print markets.",
                    "Line parsing is not the limiting variable when market type, outcome, temporal, and weak-relatedness gates reject the same pairs.",
                ],
                "nextAction": "Do not retest macro/rates line parsing from this evidence. Move to resolved-outcome joins, a new macro market source, or a different feature family.",
            })
    if macro_rates_cross_source_replay.get("decision") == "research-only-macro-rates-cross-source-replay-blocked":
        rows = macro_rates_cross_source_replay.get("rows") if isinstance(macro_rates_cross_source_replay.get("rows"), list) else []
        fee_blocked_rows = [
            row for row in rows
            if isinstance(row, dict)
            and "no-positive-net-edge-after-fee-stress" in (row.get("blockers") or [])
        ]
        blockers = macro_rates_cross_source_replay.get("blockers") if isinstance(macro_rates_cross_source_replay.get("blockers"), list) else []
        if rows and len(fee_blocked_rows) == len(rows):
            entries.append({
                "id": "macro-rates-cross-source-fee-stressed-current-form",
                "track": "prediction-markets",
                "hypothesis": "Macro/rates cross-source prices can become paper candidates from gross Polymarket/Kalshi mispricing after normal fee, spread, slippage, and sample-size stress.",
                "verdict": "no-edge",
                "status": "research-only",
                "currentFormRejected": True,
                "evidence": {
                    "decision": macro_rates_cross_source_replay.get("decision"),
                    "rowCount": macro_rates_cross_source_replay.get("rowCount", len(rows)),
                    "watchResearchCount": macro_rates_cross_source_replay.get("watchResearchCount", 0),
                    "blockers": blockers,
                    "feeBlockedRows": len(fee_blocked_rows),
                    "minSampleRows": macro_rates_cross_source_replay.get("minSampleRows"),
                    "maxYesNetEdgePct": max(
                        float(((row.get("feeStress") or {}).get("yesNetEdgePctVsAsk") or 0))
                        for row in fee_blocked_rows
                    ),
                    "maxNoNetEdgePct": max(
                        float(((row.get("feeStress") or {}).get("noNetEdgePctVsNoAsk") or 0))
                        for row in fee_blocked_rows
                    ),
                },
                "reasons": [
                    "Cross-source macro/rates replay is blocked and produced zero watch candidates.",
                    "Every comparable row failed positive net edge after fee/slippage stress.",
                    "The sample is too small for paper evidence, so the old gross-edge read must not be promoted or repeated as a candidate.",
                ],
                "nextAction": "Do not rerun the same macro/rates cross-source current form for paper. Continue only with a larger comparable/resolved sample, a new macro source/parser, or a feature that survives fee, spread, fillability, and sample-size stress.",
            })
    if btc_oos.get("command") == "prediction-btc-resolved-oos" and btc_oos.get("decision") == "research-only-no-fixed-rule-edge":
        best = best_btc_fixed_rule(btc_oos)
        best_oos = best.get("oos") if isinstance(best.get("oos"), dict) else {}
        entries.append({
            "id": "polymarket-btc-resolved-fixed-rules-current-form",
            "track": "prediction-markets",
            "hypothesis": "Fixed BTC resolved-corpus rules using spot distance, flow, momentum, or book-depth should produce enough OOS edge to become watch research candidates.",
            "verdict": "needs-more-data" if float(best_oos.get("avgPnlPerShare") or 0) > 0 else "no-edge",
            "status": "research-only",
            "currentFormRejected": True,
            "evidence": {
                "input": btc_oos.get("input"),
                "rows": btc_oos.get("rows", 0),
                "markets": btc_oos.get("markets", 0),
                "watchResearchCount": btc_oos.get("watchResearchCount", 0),
                "decision": btc_oos.get("decision"),
                "bestRule": {
                    "id": best.get("id"),
                    "side": best.get("side"),
                    "oneVariable": best.get("oneVariable"),
                    "oos": best_oos,
                    "decision": best.get("decision"),
                },
            },
            "reasons": [
                "BTC resolved OOS evaluator produced zero watch-research candidates under the fixed-rule contract.",
                "High-looking book-depth rules had too few OOS trades to pass sample-depth requirements.",
                "Rerunning the same fixed thresholds would be parameter mining unless a new feature or label source is added.",
            ],
            "nextAction": "Do not rerun the same BTC fixed rules. Continue only with a stronger market-family walk-forward, more resolved labels, fee/fillability review, or a genuinely different feature family.",
        })
    if clob_depth_replay.get("command") == "prediction-clob-depth-imbalance-replay" and clob_depth_replay.get("decision") == "research-only-no-depth-imbalance-edge":
        entries.append({
            "id": "polymarket-clob-depth-imbalance-current-form",
            "track": "prediction-markets",
            "hypothesis": "Fixed top-of-book depth imbalance should predict near-term Polymarket mid-price direction after a realistic spread prefilter.",
            "verdict": "no-edge",
            "status": "research-only",
            "currentFormRejected": True,
            "evidence": {
                "inputPath": clob_depth_replay.get("inputPath"),
                "recordsRead": clob_depth_replay.get("recordsRead", 0),
                "bookFeatureRows": clob_depth_replay.get("bookFeatureRows", 0),
                "watchResearchCount": clob_depth_replay.get("watchResearchCount", 0),
                "fixedThresholds": clob_depth_replay.get("fixedThresholds") or {},
                "results": clob_depth_replay.get("results") or [],
            },
            "reasons": [
                "Depth-imbalance replay produced zero watch-research windows under fixed thresholds.",
                "After the max-spread prefilter, current local book captures did not provide enough usable samples.",
                "Rerunning this exact fixed form would be parameter mining unless a new label source, longer fillable capture, or different microstructure feature is added.",
            ],
            "nextAction": "Do not rerun this exact depth-imbalance fixed form. Continue with longer fillable CLOB capture, quote-update intensity, spread compression, latency/staleness, or resolved-label joins.",
        })
    if (
        clob_quote_intensity_replay.get("command") == "prediction-clob-quote-intensity-replay"
        and clob_quote_intensity_replay.get("decision") == "research-only-no-quote-intensity-edge"
    ):
        entries.append({
            "id": "polymarket-clob-quote-intensity-current-form",
            "track": "prediction-markets",
            "hypothesis": "Fixed quote-update intensity plus signed recent quote drift should predict near-term Polymarket mid-price direction after a realistic spread prefilter.",
            "verdict": "no-edge",
            "status": "research-only",
            "currentFormRejected": True,
            "evidence": {
                "inputPath": clob_quote_intensity_replay.get("inputPath"),
                "recordsRead": clob_quote_intensity_replay.get("recordsRead", 0),
                "quoteFeatureRows": clob_quote_intensity_replay.get("quoteFeatureRows", 0),
                "watchResearchCount": clob_quote_intensity_replay.get("watchResearchCount", 0),
                "fixedThresholds": clob_quote_intensity_replay.get("fixedThresholds") or {},
                "results": clob_quote_intensity_replay.get("results") or [],
            },
            "reasons": [
                "Quote-intensity replay produced zero watch-research windows under fixed thresholds.",
                "Current local quote-update bursts did not create positive net forward drift after half-spread.",
                "Rerunning this exact fixed form would be parameter mining unless a new label source, longer fillable capture, or different microstructure feature is added.",
            ],
            "nextAction": "Do not rerun this exact quote-intensity fixed form. Continue with spread compression, latency/staleness, trade impact, longer fillable capture, or resolved-label joins.",
        })
    if (
        clob_spread_compression_replay.get("command") == "prediction-clob-spread-compression-replay"
        and clob_spread_compression_replay.get("decision") == "research-only-no-spread-compression-edge"
    ):
        entries.append({
            "id": "polymarket-clob-spread-compression-current-form",
            "track": "prediction-markets",
            "hypothesis": "Fixed spread compression after a signed mid-price move should predict near-term Polymarket mid-price continuation after half-spread cost.",
            "verdict": "no-edge",
            "status": "research-only",
            "currentFormRejected": True,
            "evidence": {
                "inputPath": clob_spread_compression_replay.get("inputPath"),
                "recordsRead": clob_spread_compression_replay.get("recordsRead", 0),
                "quoteFeatureRows": clob_spread_compression_replay.get("quoteFeatureRows", 0),
                "watchResearchCount": clob_spread_compression_replay.get("watchResearchCount", 0),
                "fixedThresholds": clob_spread_compression_replay.get("fixedThresholds") or {},
                "results": clob_spread_compression_replay.get("results") or [],
            },
            "reasons": [
                "Spread-compression replay produced zero watch-research windows under fixed thresholds.",
                "Current local quote compression did not create positive net forward drift after half-spread.",
                "Rerunning this exact fixed form would be parameter mining unless a new label source, longer fillable capture, or different microstructure feature is added.",
            ],
            "nextAction": "Do not rerun this exact spread-compression fixed form. Continue with latency/staleness, trade impact, longer fillable capture, or resolved-label joins.",
        })
    if (
        clob_latency_staleness_replay.get("command") == "prediction-clob-latency-staleness-replay"
        and clob_latency_staleness_replay.get("decision") == "research-only-no-latency-staleness-edge"
    ):
        entries.append({
            "id": "polymarket-clob-latency-staleness-current-form",
            "track": "prediction-markets",
            "hypothesis": "Fixed exchange-latency and quote-staleness filters should isolate cleaner near-term Polymarket continuation after half-spread cost.",
            "verdict": "no-edge",
            "status": "research-only",
            "currentFormRejected": True,
            "evidence": {
                "inputPath": clob_latency_staleness_replay.get("inputPath"),
                "recordsRead": clob_latency_staleness_replay.get("recordsRead", 0),
                "quoteFeatureRows": clob_latency_staleness_replay.get("quoteFeatureRows", 0),
                "watchResearchCount": clob_latency_staleness_replay.get("watchResearchCount", 0),
                "fixedThresholds": clob_latency_staleness_replay.get("fixedThresholds") or {},
                "results": clob_latency_staleness_replay.get("results") or [],
            },
            "reasons": [
                "Latency/staleness replay produced zero watch-research windows under fixed thresholds.",
                "Current local low-latency/fresh quote filter did not create positive net forward drift after half-spread.",
                "Rerunning this exact fixed form would be parameter mining unless a new label source, longer fillable capture, or different microstructure feature is added.",
            ],
            "nextAction": "Do not rerun this exact latency/staleness fixed form. Continue with trade impact, longer fillable capture, or resolved-label joins.",
        })
    if (
        clob_trade_impact_replay.get("command") == "prediction-clob-trade-impact-replay"
        and clob_trade_impact_replay.get("decision") == "research-only-no-trade-impact-edge"
    ):
        entries.append({
            "id": "polymarket-clob-trade-impact-current-form",
            "track": "prediction-markets",
            "hypothesis": "Fixed last-trade side/impact should predict near-term Polymarket mid-price continuation after half-spread cost.",
            "verdict": "no-edge",
            "status": "research-only",
            "currentFormRejected": True,
            "evidence": {
                "inputPath": clob_trade_impact_replay.get("inputPath"),
                "recordsRead": clob_trade_impact_replay.get("recordsRead", 0),
                "tradeFeatureRows": clob_trade_impact_replay.get("tradeFeatureRows", 0),
                "watchResearchCount": clob_trade_impact_replay.get("watchResearchCount", 0),
                "fixedThresholds": clob_trade_impact_replay.get("fixedThresholds") or {},
                "results": clob_trade_impact_replay.get("results") or [],
            },
            "reasons": [
                "Trade-impact replay produced zero watch-research windows under fixed thresholds.",
                "Current local last-trade events did not create positive net forward drift after half-spread.",
                "Rerunning this exact fixed form would be parameter mining unless a new label source, longer fillable capture, or different microstructure feature is added.",
            ],
            "nextAction": "Do not rerun this exact trade-impact fixed form. Continue with longer fillable capture, resolved-label joins, or a genuinely new feature family.",
        })

    if (
        clob_trade_resolved_join.get("command") == "prediction-clob-trade-resolved-label-join"
        and clob_trade_resolved_join.get("decision") == "research-only-no-labelled-trade-edge"
        and int(clob_trade_resolved_join.get("tradeMarketsStillOpenOrUnmapped", 0)) > 0
    ):
        entries.append({
            "id": "polymarket-clob-trade-resolved-label-join-current-capture",
            "track": "prediction-markets",
            "hypothesis": "Real captured last-trade prints joined to exact resolved market ids should carry post-spread edge.",
            "verdict": "no-edge",
            "status": "research-only",
            "currentFormRejected": True,
            "evidence": {
                "recordsRead": clob_trade_resolved_join.get("recordsRead", 0),
                "resolvedMarketIds": clob_trade_resolved_join.get("resolvedMarketIds", 0),
                "tradeMarketIdsSeen": clob_trade_resolved_join.get("tradeMarketIdsSeen", 0),
                "tradeMarketsStillOpenOrUnmapped": clob_trade_resolved_join.get("tradeMarketsStillOpenOrUnmapped", 0),
                "tradeFeatureRows": clob_trade_resolved_join.get("tradeFeatureRows", 0),
                "results": clob_trade_resolved_join.get("results") or [],
            },
            "reasons": [
                "Live capture markets are still OPEN, so exact-id join to resolved outcomes yields zero labelled samples.",
                "You cannot validate trade->resolution edge on markets that have not resolved; this is a capture-design gap, not a parameter problem.",
                "Rerunning the same live join would be parameter mining unless trades are captured AFTER resolution or a timestamped historical labelled-trade corpus is built.",
            ],
            "nextAction": "Capture trades on markets after they resolve, or build a historical labelled-trade corpus with timestamps, before retesting this join.",
        })
    if (
        clob_orderflow_resolution.get("command") == "prediction-clob-orderflow-resolution-replay"
        and clob_orderflow_resolution.get("decision") == "research-only-no-nonhindsight-signal"
    ):
        entries.append({
            "id": "polymarket-clob-orderflow-resolution-hindsight-baseline",
            "track": "prediction-markets",
            "hypothesis": "Whole-market order-flow direction should predict the resolved outcome with post-spread edge.",
            "verdict": "no-edge",
            "status": "research-only",
            "currentFormRejected": True,
            "evidence": {
                "marketsInIndex": clob_orderflow_resolution.get("marketsInIndex", 0),
                "tradesRead": clob_orderflow_resolution.get("tradesRead", 0),
                "tradesJoinedToResolved": clob_orderflow_resolution.get("tradesJoinedToResolved", 0),
                "marketsScored": clob_orderflow_resolution.get("marketsScored", 0),
                "wholeMarketFlow": clob_orderflow_resolution.get("wholeMarketFlow") or {},
            },
            "reasons": [
                "Historical trades parquet has NULL timestamps (block_number only), so a non-hindsight early/late split is impossible on this corpus.",
                "Whole-market flow -> resolution is a tautology (resolved-YES markets show net YES buying by construction), not a forward signal.",
                "Computed whole-market directional hit rate is below coin-flip, confirming no usable forward signal without time separation.",
            ],
            "nextAction": "Do not parameter-mine on historical flow. Build forward signal from live OPEN-market flow vs contemporaneous mid BEFORE resolution; that is the only non-hindsight path.",
        })
    if (
        event_lag_replay.get("command") == "prediction-event-lag-replay"
        and event_lag_replay.get("decision") == "research-only-event-lag-replay-blocked"
        and int(event_lag_replay.get("completeEventCount") or 0) > 0
        and int(event_lag_replay.get("repricedWindowCount") or 0) == 0
    ):
        entries.append({
            "id": "prediction-news-event-lag-current-form",
            "track": "prediction-markets",
            "hypothesis": "Mapped news events should create post-event prediction-market repricing large enough to survive half-spread costs under the current event-lag replay form.",
            "verdict": "no-edge",
            "status": "research-only",
            "currentFormRejected": True,
            "evidence": {
                "decision": event_lag_replay.get("decision"),
                "completeEventCount": event_lag_replay.get("completeEventCount", 0),
                "completeWindowCount": event_lag_replay.get("completeWindowCount", 0),
                "repricedWindowCount": event_lag_replay.get("repricedWindowCount", 0),
                "assetQuoteCount": event_lag_replay.get("assetQuoteCount", 0),
                "assetsWithQuotes": event_lag_replay.get("assetsWithQuotes", 0),
                "missingReasonCounts": event_lag_replay.get("missingReasonCounts") or {},
                "byHorizon": event_lag_replay.get("byHorizon") or {},
                "readyForPaper": event_lag_replay.get("readyForPaper", False),
            },
            "reasons": [
                "Event-lag replay produced complete no-lookahead event windows but zero repriced windows after half-spread.",
                "The current form has evidence of live/fillable CLOB capture, so the blocker is not merely missing recorder plumbing.",
                "Rerunning the same news-to-market lag form would be parameter mining unless the event definition, horizon, feature family, or label source changes.",
            ],
            "nextAction": "Do not rerun the same event-lag replay form as paper evidence. Continue only with a different microstructure feature, longer forward capture through fresh events, resolved labels, or a separately specified one-variable horizon/event-definition retest.",
        })
    return entries


def merge_entries(previous: list[dict[str, Any]], current: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge durable no-edge memory.

    A rejected hypothesis should not disappear just because the latest triage
    artifact stopped mentioning it. It can be replaced only by an explicit
    current entry carrying retestPassed=true or supersededBy.
    """
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

    return finalize_entries(sorted(merged.values(), key=lambda item: str(item.get("id", ""))))


def finalize_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Update durable guidance after related current-form tests settle."""
    by_id = {str(entry.get("id")): entry for entry in entries if entry.get("id")}
    current_narrow_rejected = (
        by_id.get("crypto-settlement-horizon-parser-current-form", {}).get("verdict") == "no-edge"
        and by_id.get("macro-rates-line-parser-current-form", {}).get("verdict") == "no-edge"
    )
    if not current_narrow_rejected:
        return entries

    for entry_id in (
        "broad-cross-venue-prediction-scan-current-normalization",
        "narrow-category-cross-venue-current-universe",
    ):
        entry = by_id.get(entry_id)
        if not entry:
            continue
        entry["currentFormRejected"] = True
        entry["rejectedBy"] = [
            "crypto-settlement-horizon-parser-current-form",
            "macro-rates-line-parser-current-form",
        ]
        entry["nextAction"] = (
            "Do not rerun the current broad/narrow cross-venue universe. Continue only with resolved-outcome joins, "
            "longer targeted CLOB capture, a new market source, or a genuinely new feature family."
        )
    return entries


def count_verdict(entries: list[dict[str, Any]], verdict: str) -> int:
    return sum(1 for entry in entries if entry.get("verdict") == verdict)


def main() -> int:
    triage = read_json(STATE / "prediction-evidence-triage.latest.json")
    narrow_scan = read_json(STATE / "prediction-narrow-scan-runner.latest.json")
    btc_oos = read_json(STATE / "prediction-btc-resolved-oos.latest.json")
    clob_depth_replay = read_json(STATE / "prediction-clob-depth-imbalance-replay.latest.json")
    clob_quote_intensity_replay = read_json(STATE / "prediction-clob-quote-intensity-replay.latest.json")
    clob_spread_compression_replay = read_json(STATE / "prediction-clob-spread-compression-replay.latest.json")
    clob_latency_staleness_replay = read_json(STATE / "prediction-clob-latency-staleness-replay.latest.json")
    clob_trade_impact_replay = read_json(STATE / "prediction-clob-trade-impact-replay.latest.json")
    event_lag_replay = read_json(STATE / "prediction-event-lag-replay.latest.json")
    macro_rates_cross_source_replay = read_json(STATE / "prediction-macro-rates-cross-source-replay.latest.json")
    clob_trade_resolved_join = read_json(STATE / "prediction-clob-trade-resolved-label-join.latest.json")
    clob_orderflow_resolution = read_json(STATE / "prediction-clob-orderflow-resolution-replay.latest.json")
    clob_edge_gate = read_json(STATE / "polymarket-clob-edge-gate.latest.json")
    now = datetime.now(timezone.utc).isoformat()
    current_entries = build_entries(
        triage,
        narrow_scan,
        btc_oos,
        clob_depth_replay,
        event_lag_replay,
        clob_quote_intensity_replay,
        clob_spread_compression_replay,
        clob_latency_staleness_replay,
        clob_trade_impact_replay,
        macro_rates_cross_source_replay,
        clob_trade_resolved_join,
        clob_orderflow_resolution,
        clob_edge_gate,
    )
    previous_entries = read_json(LATEST).get("entries", [])
    if not isinstance(previous_entries, list):
        previous_entries = []
    entries = merge_entries(previous_entries, current_entries)
    no_edge_count = count_verdict(entries, "no-edge")
    promotable_count = count_verdict(entries, "promotable")
    payload = {
        "command": "prediction-no-edge-ledger",
        "generatedAt": now,
        "researchOnly": True,
        "writesOrders": False,
        "count": len(entries),
        "noEdgeCount": no_edge_count,
        "needsMoreDataCount": count_verdict(entries, "needs-more-data"),
        "promotableCount": promotable_count,
        "entries": entries,
        "learningSummary": [
            f"prediction entries={len(entries)}, noEdge={no_edge_count}, promotable={promotable_count}",
            "Current CLOB drift/persistence hypothesis is rejected under existing thresholds.",
            "Broad by-price priors and broad cross-venue scans are research seeds, not paper evidence.",
        ],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    LATEST.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    with HISTORY.open("a") as fh:
        fh.write(json.dumps(payload, sort_keys=True) + "\n")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
