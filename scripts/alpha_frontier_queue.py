#!/usr/bin/env python3
"""Build the next Bill/Hermes alpha frontier queue.

This is research-only. It intentionally starts where the evidence triage
stops: current futures and prediction-market forms are rejected, so the next
useful work must add a genuinely new feature family, source, or label set.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml
except Exception:  # pragma: no cover - exercised only when PyYAML is absent
    yaml = None


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge/state"
RESEARCH = ROOT / ".rumbling-hedge/research"
VAULT = Path.home() / "Documents/memorybrain"
HERMES = VAULT / "Agent-Hermes"
CATALOG = ROOT / "config/external_alpha_catalog.yaml"
OUT = STATE / "alpha-frontier-queue.latest.json"
DEFAULT_CLOB_MAX_OUTPUT_MB = 128
DEFAULT_CLOB_MIN_FREE_GB = 20
LABEL_SOURCE_MANIFEST = STATE / "prediction-label-source-manifest.latest.json"
CLOB_MICROSTRUCTURE_AUDIT = STATE / "prediction-clob-microstructure-feature-audit.latest.json"
NQ_SESSION_STRUCTURE_AUDIT = STATE / "futures-nq-session-structure-audit.latest.json"
NQ_HISTORICAL_COVERAGE_AUDIT = STATE / "futures-nq-historical-coverage-audit.latest.json"
NQ_HISTORICAL_SESSION_REPLAY = STATE / "futures-nq-historical-session-replay.latest.json"
NQ_HISTORICAL_SESSION_WALKFORWARD = STATE / "futures-nq-historical-session-walkforward.latest.json"
NQ_HISTORICAL_SESSION_COST_STRESS = STATE / "futures-nq-historical-session-cost-stress.latest.json"
NQ_CURRENT_DATA_PARITY = STATE / "futures-nq-current-data-parity.latest.json"
FUTURES_DATA_REQUIREMENTS = STATE / "futures-data-requirements.latest.json"
FUTURES_BROKER_PARITY_PLAN = STATE / "futures-broker-parity-plan.latest.json"
PREDICTION_EVENT_LAG_REQUIREMENTS = STATE / "prediction-event-lag-requirements.latest.json"
PREDICTION_EVENT_MARKET_MAPPING_PLAN = STATE / "prediction-event-market-mapping-plan.latest.json"
PREDICTION_EVENT_TIMESTAMP_DATASET = STATE / "prediction-event-timestamp-dataset.latest.json"
PREDICTION_EVENT_LAG_REPLAY = STATE / "prediction-event-lag-replay.latest.json"
PREDICTION_EVENT_LAG_SENSITIVITY = STATE / "prediction-event-lag-sensitivity.latest.json"
PREDICTION_EVENT_LAG_WATCH_REVIEW = STATE / "prediction-event-lag-watch-review.latest.json"
PREDICTION_EVENT_CLOB_CAPTURE_TARGETS = STATE / "prediction-event-clob-capture-targets.latest.json"
PREDICTION_EVENT_CAPTURE_CYCLE = STATE / "prediction-event-capture-cycle.latest.json"
PREDICTION_EVENT_LABEL_GAP_PLAN = STATE / "prediction-event-label-gap-plan.latest.json"
PREDICTION_MACRO_RATES_REQUIREMENTS = STATE / "prediction-macro-rates-requirements.latest.json"
PREDICTION_MACRO_RATES_CROSS_SOURCE_REPLAY = STATE / "prediction-macro-rates-cross-source-replay.latest.json"
PAPER_SOURCE_CARDS = STATE / "paper-source-cards.latest.json"
YOUTUBE_SOURCE_CARDS_MD = VAULT / "Research-Catalog/Youtube-Transcript-Source-Cards-2026-05-30.md"
YOUTUBE_CORPUS_CHUNKS = RESEARCH / "corpus/chunks.jsonl"
FABERVAALE_REPLAY = STATE / "futures-nq-fabervaale-orb-replay.latest.json"
FABERVAALE_SIZING_OVERLAY = STATE / "futures-nq-sizing-overlay.latest.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def current_utc_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def default_markdown_path() -> Path:
    return HERMES / f"bill-alpha-frontier-queue-{current_utc_date()}.md"


def hermes_markdown_path(stem: str) -> str:
    return str(HERMES / f"{stem}-{current_utc_date()}.md")


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def read_catalog(path: Path = CATALOG) -> dict[str, Any]:
    if not path.exists():
        return {}
    text = path.read_text()
    if yaml:
        try:
            data = yaml.safe_load(text)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    return parse_simple_catalog(text)


def parse_simple_catalog(text: str) -> dict[str, Any]:
    """Parse the small external alpha catalog when PyYAML is unavailable.

    The file is intentionally simple: top-level ``datasets`` and
    ``source_repos`` maps with nested ``path`` fields. We only need enough
    structure to keep data provenance visible and fail closed.
    """
    out: dict[str, Any] = {"datasets": {}, "source_repos": {}}
    section = ""
    current = ""
    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not raw.startswith(" ") and stripped.endswith(":"):
            section = stripped[:-1]
            current = ""
            continue
        if section not in {"datasets", "source_repos"}:
            continue
        if raw.startswith("  ") and not raw.startswith("    ") and stripped.endswith(":"):
            current = stripped[:-1]
            out[section].setdefault(current, {})
            continue
        if current and raw.startswith("    ") and ":" in stripped:
            key, value = stripped.split(":", 1)
            value = value.strip()
            if value.startswith("[") and value.endswith("]"):
                value = [item.strip() for item in value[1:-1].split(",") if item.strip()]
            out[section][current][key.strip()] = value
    return out


def entry_ids(ledger: dict[str, Any]) -> set[str]:
    entries = ledger.get("entries") if isinstance(ledger.get("entries"), list) else []
    return {str(entry.get("id")) for entry in entries if isinstance(entry, dict) and entry.get("id")}


def rejected_memory(ledger: dict[str, Any]) -> list[dict[str, Any]]:
    entries = ledger.get("entries") if isinstance(ledger.get("entries"), list) else []
    out: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        verdict = str(entry.get("verdict") or "")
        if verdict in {"no-edge", "needs-new-feature", "needs-more-data"}:
            out.append({
                "id": entry.get("id"),
                "verdict": verdict,
                "nextAction": entry.get("nextAction"),
                "currentFormRejected": bool(entry.get("currentFormRejected")),
            })
    return out


def catalog_dataset(catalog: dict[str, Any], key: str) -> dict[str, Any]:
    datasets = catalog.get("datasets") if isinstance(catalog.get("datasets"), dict) else {}
    item = datasets.get(key)
    return item if isinstance(item, dict) else {}


def catalog_repo(catalog: dict[str, Any], key: str) -> dict[str, Any]:
    repos = catalog.get("source_repos") if isinstance(catalog.get("source_repos"), dict) else {}
    item = repos.get(key)
    return item if isinstance(item, dict) else {}


def audit_dataset(external_alpha_audit: dict[str, Any], dataset_id: str) -> dict[str, Any]:
    datasets = external_alpha_audit.get("datasets") if isinstance(external_alpha_audit.get("datasets"), list) else []
    for item in datasets:
        if isinstance(item, dict) and item.get("id") == dataset_id:
            return item
    return {}


def local_nq_60d_min(external_alpha_audit: dict[str, Any]) -> str:
    ranges = external_alpha_audit.get("localFuturesRanges") if isinstance(external_alpha_audit.get("localFuturesRanges"), dict) else {}
    item = ranges.get("all_15m_60d_nq") if isinstance(ranges.get("all_15m_60d_nq"), dict) else {}
    return str(item.get("min") or "")


def audit_max(dataset_audit: dict[str, Any]) -> str:
    time_range = dataset_audit.get("timeRange") if isinstance(dataset_audit.get("timeRange"), dict) else {}
    return str(time_range.get("max") or "")


def feature_path(item: dict[str, Any]) -> str:
    return str(item.get("path") or "missing")


def file_exists(path_text: str) -> bool:
    return bool(path_text and path_text != "missing" and Path(path_text).exists())


def data_available(data_paths: list[str]) -> bool:
    return bool(data_paths) and all(file_exists(path) for path in data_paths)


def candidate_paper_cards(paper_source_cards: dict[str, Any]) -> list[dict[str, Any]]:
    cards = paper_source_cards.get("cards") if isinstance(paper_source_cards.get("cards"), list) else []
    out: list[dict[str, Any]] = []
    for card in cards:
        if not isinstance(card, dict):
            continue
        if card.get("lane") != "futures":
            continue
        if card.get("decision") not in {"candidate", "candidate-with-caution"}:
            continue
        if not card.get("path"):
            continue
        out.append(card)
    return out


def base_item(
    *,
    item_id: str,
    lane: str,
    priority: int,
    one_variable: str,
    hypothesis: str,
    evidence: list[str],
    commands: list[str],
    promotion_gate: str,
    blocked_by: list[str],
    data_paths: list[str],
) -> dict[str, Any]:
    runnable_prefixes = ("npm ", ".venv/", "tsx ", "node ", "BILL_", "jq ")
    runnable_commands = [command for command in commands if command.startswith(runnable_prefixes)]
    research_steps = [command for command in commands if command not in runnable_commands]
    if not runnable_commands:
        runnable_commands = ["npm run --silent bill:alpha-frontier-queue"]
    return {
        "id": item_id,
        "lane": lane,
        "priority": priority,
        "oneVariable": one_variable,
        "hypothesis": hypothesis,
        "evidence": evidence,
        "commands": runnable_commands,
        "researchSteps": research_steps,
        "promotionGate": promotion_gate,
        "blockedBy": blocked_by,
        "dataPaths": data_paths,
        "dataAvailable": data_available(data_paths),
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "operatorApprovalRequiredBeforeExecution": True,
    }


def futures_frontier(catalog: dict[str, Any], futures_no_edge: dict[str, Any]) -> list[dict[str, Any]]:
    rejected = entry_ids(futures_no_edge)
    nq_1m = catalog_dataset(catalog, "nq_futures_1m")
    nq_5m = catalog_dataset(catalog, "nq_futures_5m")
    nq_15m = catalog_dataset(catalog, "nq_futures_15m")
    options = catalog_dataset(catalog, "sp500_options_daily_regime")
    breadth = catalog_dataset(catalog, "equities_5m_breadth_2026_03")
    vol_repo = catalog_repo(catalog, "vol_regime_prediction")
    blocked = sorted(rejected)
    items = [
        base_item(
            item_id="futures-paid-nq-1m-session-structure-oos",
            lane="futures",
            priority=20,
            one_variable="data source",
            hypothesis="The failed WQ/ORB current forms may be a data-quality/sample issue; use the best validated Seagate NQ cadence for historical OOS before inventing new parameters.",
            evidence=[
                "current 15m/30m/60m vol-regime forms are rejected in futures no-edge memory",
                "external catalog exposes Seagate NQ parquet features",
            ],
            commands=[
                "npm run --silent bill:external-alpha-data-audit",
                "npm run --silent bill:futures-nq-historical-coverage-audit",
                "npm run --silent bill:futures-nq-historical-session-replay",
                "npm run --silent bill:futures-nq-historical-session-walkforward",
                (
                    "npm run --silent bill:futures-nq-historical-session-walkforward -- "
                    "--replay .rumbling-hedge/state/futures-nq-fabervaale-orb-local-5m-replay.latest.json "
                    "--output .rumbling-hedge/state/futures-nq-fabervaale-orb-local-5m-walkforward.latest.json "
                    f"--markdown {hermes_markdown_path('futures-nq-fabervaale-orb-local-5m-walkforward')}"
                ),
                "npm run --silent bill:futures-nq-historical-session-cost-stress",
                "npm run --silent bill:futures-nq-current-data-parity",
                "npm run --silent bill:futures-nq-session-structure-audit",
                "npm run --silent bill:futures-data-requirements",
                "npm run --silent bill:futures-broker-parity-plan",
                "npm run --silent bill:futures-nq-research-cycle -- --run-local-research",
                "npm run --silent bill:alpha-frontier-queue",
                "Use the coverage audit's best historical cadence; keep any no-overlap current CSV parity result as a blocker for demo/current-data claims.",
            ],
            promotion_gate="Only continue if paid-source replay passes data parity, purged OOS, cost/slippage, walk-forward, and rolling OOS gates.",
            blocked_by=blocked,
            data_paths=[feature_path(nq_1m), feature_path(nq_5m), feature_path(nq_15m)],
        ),
        base_item(
            item_id="futures-options-regime-risk-overlay",
            lane="futures",
            priority=21,
            one_variable="dealer-gamma regime overlay",
            hypothesis="Dealer-gamma regime conditions the nq-orb-3m-vt16 edge: breakouts should follow through on short-gamma/far-from-flip days and fail on long-gamma pinning days. Conditioning filter, not an entry signal. See .rumbling-hedge/research/specs/gamma-orb-conditioning.md.",
            evidence=[
                "COT/TFF current gate is no-edge; a different non-price regime source is required",
                "standalone GEX timing already dead (gex-sign-atm-standalone-index-futures-proxy, Sharpe 0.30); conditional angle untested",
                "gex history (data/research/gex-backtest-results.csv) overlaps NQ bars ~1yr (2023) -> in-sample screen now + forward demo-tagged arm",
            ],
            commands=[
                "In-sample screen: join 2023 ORB-3m per-trade P&L (emit from blessed template; do NOT reimplement ORB) to gex CSV signal_sign_atm_gex/gex_quintile/spot_vs_flip/near_flip; permutation-test the avgR gap (>=1000 shuffles).",
                "Forward arm: snapshot dealerGamma.ts regime daily, tag each live ORB-3m demo trade with that day's regime, recheck after ~40 trades.",
                "Reject if improvement is only from blocking all trades, reducing sample below the OOS contract, or duplicating the existing vol-regime-gate.",
            ],
            promotion_gate="Overlay must add OOS Sharpe BEYOND vol-regime-gate after costs, survive purged walk-forward + shuffle, without reducing sample below the promotion contract.",
            blocked_by=["cot-tff-regime-filter-current-backtrader-set"] if "cot-tff-regime-filter-current-backtrader-set" in rejected else [],
            data_paths=[feature_path(options)],
        ),
        base_item(
            item_id="futures-equity-breadth-nq-overlay",
            lane="futures",
            priority=22,
            one_variable="equity breadth overlay",
            hypothesis="NQ intraday entries may improve when conditioned on mega-cap/breadth participation rather than NQ price alone.",
            evidence=[
                "price-only and volume-regime forms failed OOS",
                "external catalog has a prototype 5m equities breadth dataset for March 2026",
            ],
            commands=[
                "Run a smoke test on equities_5m_breadth_2026_03 as a filter only; do not tune entry parameters in the same test.",
                "If smoke is positive, backfill only the needed months and rerun purged OOS.",
            ],
            promotion_gate="Prototype month can only justify backfill, not demo-shadow; full promotion needs multi-month OOS and cost/slippage.",
            blocked_by=blocked,
            data_paths=[feature_path(breadth)],
        ),
        base_item(
            item_id="futures-true-orderflow-replace-dom-proxy",
            lane="futures",
            priority=23,
            one_variable="true tape/order-book feature",
            hypothesis="OHLCV DOM proxy is not reliable; Databento live/historical MBO or MBP features should replace CLV proxy before any order-flow gate is trusted.",
            evidence=[
                "DOM proxy is shadow context and must not be treated as true order-book evidence",
                "TopstepX/ProjectX SignalR is the primary realtime quote path; Databento remains optional for depth/order-flow research",
            ],
            commands=[
                "During open Globex, rerun bill:topstep-realtime-proof and bill:topstep-realtime-bridge with execution flags still off.",
                "npm run --silent bill:databento-orderflow-feature-smoke -- --timeout-sec 20",
                "Compare read-only Databento MBP/MBO features against DOM proxy before any strategy integration.",
            ],
            promotion_gate="No order-flow feature can confirm trades until broker realtime proof is canonical, optional depth evidence is validated, and OOS replay beats no-DOM baseline.",
            blocked_by=["dom-proxy is OHLCV proxy only", "depth-orderflow-evidence-not-cleared"],
            data_paths=[],
        ),
        base_item(
            item_id="futures-vol-regime-feature-taxonomy-rebuild",
            lane="futures",
            priority=24,
            one_variable="volatility feature definition",
            hypothesis="The vol-regime idea can only be revisited via a new feature taxonomy, not parameter mining on the rejected WQ rule.",
            evidence=[
                "wq-vol-regime 60m normal/inverse is no-edge",
                "15m current form needs a new feature despite positive netR because PF/window contract failed",
                "external vol-regime repo is cataloged for feature taxonomy only",
            ],
            commands=[
                "Extract feature definitions from the cataloged vol_regime_prediction repo; freeze parameters before OOS.",
                "Run a single-feature ablation against current rejected vol-regime baseline.",
            ],
            promotion_gate="Must supersede current form with explicit retestPassed/supersededBy evidence before no-edge memory can be cleared.",
            blocked_by=["wq-vol-regime-60m-current-form", "wq-vol-regime-15m-current-form", "wq-vol-regime-30m-current-form"],
            data_paths=[feature_path(vol_repo)],
        ),
    ]
    return items


def paper_seed_frontier(paper_source_cards: dict[str, Any]) -> list[dict[str, Any]]:
    cards = candidate_paper_cards(paper_source_cards)
    if not cards:
        return []
    data_paths = [str(card.get("path")) for card in cards if card.get("path")]
    item = base_item(
        item_id="futures-paper-source-one-variable-tests",
        lane="futures",
        priority=25,
        one_variable="paper-derived feature seed",
        hypothesis="Collected futures papers can seed new risk, trend, and regime features, but each paper idea must become exactly one frozen variable before OOS replay.",
        evidence=[
            "paper-source-cards classified futures papers as hypothesis candidates",
            "paper cards are source memory, not strategy evidence or execution approval",
        ],
        commands=[
            "npm run --silent bill:paper-source-cards",
            "npm run --silent bill:alpha-frontier-queue",
            "Pick exactly one paper card, freeze one tradable variable, and run it against the current no-edge baseline without changing entries or exits.",
            "Reject if the effect only appears in full sample, worsens drawdown, shrinks OOS below contract, or fails costs.",
        ],
        promotion_gate="Paper-derived ideas require one-variable local replay, purged OOS, cost/slippage, no-edge review, and broker/data gates before any demo-shadow discussion.",
        blocked_by=[
            "paper-source-is-hypothesis-only",
            "requires-one-variable-oos-before-promotion",
        ],
        data_paths=data_paths,
    )
    item["dataQuality"] = {
        "paperSourceCards": ".rumbling-hedge/state/paper-source-cards.latest.json",
        "candidateCount": len(cards),
        "cautionCount": sum(1 for card in cards if card.get("decision") == "candidate-with-caution"),
        "candidateIds": [card.get("id") for card in cards],
        "candidateVariables": [card.get("tradableVariable") for card in cards],
        "sourceStatusCounts": (paper_source_cards.get("summary") or {}).get("decisionCounts", {}),
    }
    return [item]


def youtube_seed_frontier(source_cards_path: str | Path | None) -> list[dict[str, Any]]:
    if not source_cards_path:
        return []
    path = Path(source_cards_path)
    if not path.exists():
        return []
    try:
        text = path.read_text(errors="replace")
    except Exception:
        return []

    items: list[dict[str, Any]] = []
    source_path = str(path)
    corpus_path = str(YOUTUBE_CORPUS_CHUNKS)
    if "FaberVaale opening range improvement" in text and "`candidate`" in text:
        item = base_item(
            item_id="futures-youtube-fabervaale-orb-vol-target-oos",
            lane="futures",
            priority=26,
            one_variable="volatility-targeted sizing",
            hypothesis="The FaberVaale opening-range breakout should be tested as one frozen NQ NY-session rule set, changing only fixed sizing versus capped volatility-targeted sizing.",
            evidence=[
                "YouTube transcript source card classifies FaberVaale as a futures candidate",
                "source card explicitly warns not to add the delta filter in the first retest",
                "source card requires purged OOS, regime splits, costs, and broker/data gates before Topstep discussion",
            ],
            commands=[
                "npm run --silent bill:futures-nq-historical-coverage-audit",
                (
                    "npm run --silent bill:futures-nq-historical-session-replay -- "
                    "--strategy fabervaale-orb "
                    "--input '/Volumes/Seagate Expansion Drive/hedge-data/features/nq_futures/nq_5_minute.parquet' "
                    "--cadence-minutes 5 "
                    "--output .rumbling-hedge/state/futures-nq-fabervaale-orb-replay.latest.json "
                    f"--markdown {hermes_markdown_path('futures-nq-fabervaale-orb-replay')}"
                ),
                (
                    "npm run --silent bill:futures-nq-historical-session-replay -- "
                    "--strategy fabervaale-orb "
                    "--input /Users/brain/hedge/data/free/NQ-5m-60d.csv "
                    "--cadence-minutes 5 "
                    "--output .rumbling-hedge/state/futures-nq-fabervaale-orb-local-5m-replay.latest.json "
                    f"--markdown {hermes_markdown_path('futures-nq-fabervaale-orb-local-5m-replay')}"
                ),
                "npm run --silent bill:futures-nq-historical-session-walkforward",
                (
                    "npm run --silent bill:futures-nq-historical-session-walkforward -- "
                    "--replay .rumbling-hedge/state/futures-nq-fabervaale-orb-local-5m-replay.latest.json "
                    "--output .rumbling-hedge/state/futures-nq-fabervaale-orb-local-5m-walkforward.latest.json "
                    f"--markdown {hermes_markdown_path('futures-nq-fabervaale-orb-local-5m-walkforward')}"
                ),
                "npm run --silent bill:futures-nq-historical-session-cost-stress",
                (
                    "npm run --silent bill:futures-nq-historical-session-cost-stress -- "
                    "--replay .rumbling-hedge/state/futures-nq-fabervaale-orb-local-5m-replay.latest.json "
                    "--output .rumbling-hedge/state/futures-nq-fabervaale-orb-local-5m-cost-stress.latest.json "
                    f"--markdown {hermes_markdown_path('futures-nq-fabervaale-orb-local-5m-cost-stress')}"
                ),
                "npm run --silent bill:futures-nq-sizing-overlay",
                "npm run --silent bill:futures-nq-research-cycle -- --run-local-research",
                "npm run --silent bill:alpha-frontier-queue",
            ],
            promotion_gate="FaberVaale video rules can only become demo-shadow candidates after one-variable OOS, cost/slippage, drawdown/Topstep fit, data freshness, broker parity, and daily route approval all pass.",
            blocked_by=[
                "youtube-source-is-hypothesis-only",
                "requires-one-variable-oos-before-promotion",
                "current-session-depth-not-cleared",
                "daily-route-approval-not-allow",
            ],
            data_paths=[source_path, corpus_path],
        )
        item["dataQuality"] = {
            "sourceCard": source_path,
            "corpus": corpus_path,
            "sourceDecision": "candidate",
            "sourceMarket": "futures",
            "strategyFamily": "ny-opening-range-breakout",
            "researchArtifact": str(FABERVAALE_REPLAY),
            "sizingOverlay": str(FABERVAALE_SIZING_OVERLAY),
            "sizingOverlayDecision": read_json(FABERVAALE_SIZING_OVERLAY).get("decision", "missing"),
            "sizingBestProfileId": read_json(FABERVAALE_SIZING_OVERLAY).get("bestProfileId", "missing"),
            "firstVariableAllowed": "position-sizing-only",
            "forbiddenFirstRetestVariables": ["delta-filter", "short-leg", "entry-parameter-tuning"],
        }
        items.append(item)

    if "PEAD post-earnings announcement drift" in text and "`candidate-with-caution`" in text:
        item = base_item(
            item_id="futures-youtube-pead-earnings-regime-overlay",
            lane="futures",
            priority=27,
            one_variable="top-component earnings regime flag",
            hypothesis="PEAD should first be tested as a timestamp-clean NQ top-component earnings breadth/regime overlay, not as an intraday Topstep entry strategy.",
            evidence=[
                "YouTube transcript source card classifies PEAD as candidate-with-caution",
                "source card says the 60-trading-day hold conflicts with prop-firm intraday objectives",
                "older Obsidian arsenal notes were marked stale until no-lookahead event evidence exists",
            ],
            commands=[
                "npm run --silent bill:researcher-report",
                "npm run --silent bill:alpha-frontier-queue",
            ],
            promotion_gate="PEAD requires an earnings event manifest with timestamp/BMO/AMC/source-quality fields, no-lookahead reaction-day replay, cost/stress review, and separate route approval before it can influence any sizing or execution path.",
            blocked_by=[
                "youtube-source-is-hypothesis-only",
                "earnings-event-manifest-missing",
                "requires-no-lookahead-reaction-day-audit",
                "not-a-topstep-intraday-oco-strategy",
                "daily-route-approval-not-allow",
            ],
            data_paths=[source_path, corpus_path],
        )
        item["dataQuality"] = {
            "sourceCard": source_path,
            "corpus": corpus_path,
            "sourceDecision": "candidate-with-caution",
            "sourceMarket": "futures-overlay/equities-research",
            "strategyFamily": "post-earnings-announcement-drift",
            "firstVariableAllowed": "top-component-earnings-regime-flag-only",
            "requiresEventManifest": True,
        }
        items.append(item)

    return items


def prediction_frontier(catalog: dict[str, Any], prediction_no_edge: dict[str, Any]) -> list[dict[str, Any]]:
    rejected = entry_ids(prediction_no_edge)
    btc = catalog_dataset(catalog, "polymarket_btc_updown_5m_resolved_all")
    poly_repo = catalog_repo(catalog, "polymarket_microstructure")
    blocked = sorted(rejected)
    items: list[dict[str, Any]] = []
    if "polymarket-btc-resolved-fixed-rules-current-form" not in rejected:
        items.append(base_item(
            item_id="prediction-btc-updown-resolved-feature-oos",
            lane="prediction-markets",
            priority=30,
            one_variable="resolved labeled corpus",
            hypothesis="Resolved BTC up/down 5m data may support an offline edge test because labels, spreads, depth, flow imbalance, and expiry buckets already exist.",
            evidence=[
                "current broad/narrow cross-venue universe is rejected",
                "external catalog has Polymarket BTC up/down resolved feature parquet with gold features",
            ],
            commands=[
                "npm run --silent bill:prediction-btc-resolved-oos",
                "Build an offline walk-forward evaluator for polymarket_btc_updown_5m_resolved_all; no paper/live route.",
                "Stress by spread/depth/time-to-expiry buckets before any watchlist promotion.",
            ],
            promotion_gate="Only paper-candidate if walk-forward hit rate, net after fees/spread, fillability, and no-edge clearance all pass.",
            blocked_by=blocked,
            data_paths=[feature_path(btc)],
        ))
    items.extend([
        base_item(
            item_id="prediction-new-resolved-label-source",
            lane="prediction-markets",
            priority=31,
            one_variable="resolved outcome label source",
            hypothesis="The current watchlist is context-only because subject-specific history is thin; the next step is better labels/source coverage, not wider matching thresholds.",
            evidence=[
                "resolved-outcome-current-watchlist-context-only is active",
                "prediction-resolved-outcome-join loaded broad history but did not produce paper-ready items",
            ],
            commands=[
                "Create a label-source manifest for repeated markets by family before scanning new live markets.",
                "Rerun resolved-outcome join only after adding new labels/source coverage or a new watchlist.",
            ],
            promotion_gate="No candidate can reach paper without subject-specific resolved history plus spread/fee/fillability review.",
            blocked_by=["resolved-outcome-current-watchlist-context-only"],
            data_paths=[],
        ),
        base_item(
            item_id="prediction-clob-microstructure-new-features",
            lane="prediction-markets",
            priority=32,
            one_variable="microstructure feature family",
            hypothesis="Current CLOB drift/persistence thresholds are no-edge; retest only with different microstructure features such as imbalance persistence, impact, latency, or queue-depth changes.",
            evidence=[
                "polymarket-clob-drift-persistence-current-thresholds is no-edge",
                "external catalog references a Polymarket microstructure repo for measure implementations",
            ],
            commands=[
                "Extract read-only spread/depth/effective/impact/latency measures from the cataloged microstructure repo.",
                "Replay one unrejected CLOB feature family against recorded samples; do not lower current drift thresholds.",
            ],
            promotion_gate="New feature must beat current CLOB no-edge baseline on directional hit rate and net drift after spread/fees.",
            blocked_by=[
                item_id
                for item_id in [
                    "polymarket-clob-drift-persistence-current-thresholds",
                    "polymarket-clob-depth-imbalance-current-form",
                    "polymarket-clob-quote-intensity-current-form",
                    "polymarket-clob-spread-compression-current-form",
                    "polymarket-clob-latency-staleness-current-form",
                    "polymarket-clob-trade-impact-current-form",
                ]
                if item_id in rejected
            ],
            data_paths=[feature_path(poly_repo)],
        ),
        base_item(
            item_id="prediction-macro-rates-new-source-parser",
            lane="prediction-markets",
            priority=33,
            one_variable="new macro market source",
            hypothesis="Kalshi fillability exists in macro/rates, but current macro-rates line parser is no-edge; use a new source/parser target rather than rerunning the same parser.",
            evidence=[
                "macro-rates-line-parser-current-form is no-edge",
                "Kalshi fillability snapshot found tight/usable public quotes concentrated in KXFED/KXCPI",
                "fee-stressed cross-source replay must replace gross-edge reads before any paper review",
            ],
            commands=[
                "Add a source-specific macro/rates label/parser fixture before running another narrow scan.",
                "Keep market-type, temporal, spread, fee, and threshold rules unchanged.",
            ],
            promotion_gate="Parser changes can only restore watch candidates; paper still requires resolved labels, fillability, CLOB/orderbook, and fee stress.",
            blocked_by=[
                item_id
                for item_id in [
                    "macro-rates-line-parser-current-form",
                    "macro-rates-cross-source-fee-stressed-current-form",
                ]
                if item_id in rejected
            ],
            data_paths=[],
        ),
        base_item(
            item_id="prediction-news-first-event-lag-study",
            lane="prediction-markets",
            priority=34,
            one_variable="news-to-market lag feature",
            hypothesis="For news-driven prediction markets, price is lagging; test whether timestamped news/event shocks lead prediction-market repricing before touching execution.",
            evidence=[
                "current price/matching-only prediction scans found no paper candidates",
                "user thesis prioritizes news and flow-of-money over price-only signals",
            ],
            commands=[
                "Build a read-only event timestamp dataset and align it to resolved markets and CLOB samples.",
                "Measure post-news repricing latency by market family before designing any scanner.",
            ],
            promotion_gate="Requires timestamp provenance, no lookahead, resolved labels, fillability, spread/fee stress, and no-edge clearance.",
            blocked_by=blocked,
            data_paths=[],
        ),
    ])
    return items


def build_frontier(
    *,
    catalog: dict[str, Any],
    futures_no_edge: dict[str, Any],
    prediction_no_edge: dict[str, Any],
    handoff: dict[str, Any],
    external_alpha_audit: dict[str, Any] | None = None,
    prediction_label_manifest: dict[str, Any] | None = None,
    clob_microstructure_audit: dict[str, Any] | None = None,
    nq_session_structure_audit: dict[str, Any] | None = None,
    nq_historical_coverage_audit: dict[str, Any] | None = None,
    nq_historical_session_replay: dict[str, Any] | None = None,
    nq_historical_session_walkforward: dict[str, Any] | None = None,
    nq_historical_session_cost_stress: dict[str, Any] | None = None,
    nq_current_data_parity: dict[str, Any] | None = None,
    futures_data_requirements: dict[str, Any] | None = None,
    futures_broker_parity_plan: dict[str, Any] | None = None,
    prediction_event_lag_requirements: dict[str, Any] | None = None,
    prediction_event_market_mapping_plan: dict[str, Any] | None = None,
    prediction_event_timestamp_dataset: dict[str, Any] | None = None,
    prediction_event_lag_replay: dict[str, Any] | None = None,
    prediction_event_lag_sensitivity: dict[str, Any] | None = None,
    prediction_event_lag_watch_review: dict[str, Any] | None = None,
    prediction_event_clob_capture_targets: dict[str, Any] | None = None,
    prediction_event_capture_cycle: dict[str, Any] | None = None,
    prediction_event_label_gap_plan: dict[str, Any] | None = None,
    prediction_macro_rates_requirements: dict[str, Any] | None = None,
    prediction_macro_rates_cross_source_replay: dict[str, Any] | None = None,
    paper_source_cards: dict[str, Any] | None = None,
    youtube_source_cards_path: str | Path | None = None,
) -> dict[str, Any]:
    paper_source_cards = paper_source_cards or {}
    items = (
        futures_frontier(catalog, futures_no_edge)
        + paper_seed_frontier(paper_source_cards)
        + youtube_seed_frontier(youtube_source_cards_path)
        + prediction_frontier(catalog, prediction_no_edge)
    )
    external_alpha_audit = external_alpha_audit or {}
    prediction_label_manifest = prediction_label_manifest or {}
    clob_microstructure_audit = clob_microstructure_audit or {}
    nq_session_structure_audit = nq_session_structure_audit or {}
    nq_historical_coverage_audit = nq_historical_coverage_audit or {}
    nq_historical_session_replay = nq_historical_session_replay or {}
    nq_historical_session_walkforward = nq_historical_session_walkforward or {}
    nq_historical_session_cost_stress = nq_historical_session_cost_stress or {}
    nq_current_data_parity = nq_current_data_parity or {}
    futures_data_requirements = futures_data_requirements or {}
    futures_broker_parity_plan = futures_broker_parity_plan or {}
    prediction_event_lag_requirements = prediction_event_lag_requirements or {}
    prediction_event_market_mapping_plan = prediction_event_market_mapping_plan or {}
    prediction_event_timestamp_dataset = prediction_event_timestamp_dataset or {}
    prediction_event_lag_replay = prediction_event_lag_replay or {}
    prediction_event_lag_sensitivity = prediction_event_lag_sensitivity or {}
    prediction_event_lag_watch_review = prediction_event_lag_watch_review or {}
    prediction_event_clob_capture_targets = prediction_event_clob_capture_targets or {}
    prediction_event_capture_cycle = prediction_event_capture_cycle or {}
    prediction_event_label_gap_plan = prediction_event_label_gap_plan or {}
    prediction_macro_rates_requirements = prediction_macro_rates_requirements or {}
    prediction_macro_rates_cross_source_replay = prediction_macro_rates_cross_source_replay or {}
    nq_parity = external_alpha_audit.get("nqLocalParity") if isinstance(external_alpha_audit.get("nqLocalParity"), dict) else {}
    nq_source_parity = external_alpha_audit.get("nqSourceParity") if isinstance(external_alpha_audit.get("nqSourceParity"), dict) else {}
    nq_historical_usability = (
        external_alpha_audit.get("nqHistoricalResearchUsability")
        if isinstance(external_alpha_audit.get("nqHistoricalResearchUsability"), dict)
        else {}
    )
    nq_60d_min = local_nq_60d_min(external_alpha_audit)
    for item in items:
        if item.get("id") == "futures-paid-nq-1m-session-structure-oos":
            item["dataQuality"] = {
                "externalAlphaAudit": ".rumbling-hedge/state/external-alpha-data-audit.latest.json",
                "nqSessionStructureAudit": ".rumbling-hedge/state/futures-nq-session-structure-audit.latest.json",
                "nqHistoricalCoverageAudit": ".rumbling-hedge/state/futures-nq-historical-coverage-audit.latest.json",
                "nqHistoricalSessionReplay": ".rumbling-hedge/state/futures-nq-historical-session-replay.latest.json",
                "nqHistoricalSessionWalkforward": ".rumbling-hedge/state/futures-nq-historical-session-walkforward.latest.json",
                "nqHistoricalSessionCostStress": ".rumbling-hedge/state/futures-nq-historical-session-cost-stress.latest.json",
                "nqCurrentDataParity": ".rumbling-hedge/state/futures-nq-current-data-parity.latest.json",
                "futuresDataRequirements": ".rumbling-hedge/state/futures-data-requirements.latest.json",
                "futuresBrokerParityPlan": ".rumbling-hedge/state/futures-broker-parity-plan.latest.json",
                "nqLocalParityOk": bool(nq_parity.get("ok")),
                "nqLocalParityReason": nq_parity.get("reason") or nq_parity.get("error"),
                "nqSourceParityOk": bool(nq_source_parity.get("ok")),
                "nqHistoricalUsableForResearch": bool(nq_historical_usability.get("usableForHistoricalResearch")),
                "nqUsableForExecutionParity": bool(nq_historical_usability.get("usableForExecutionParity")),
                "nqHistoricalUsabilityRead": nq_historical_usability.get("read"),
                "currentLocalParityDecision": nq_current_data_parity.get("decision"),
                "cleanCurrentLocalPairCount": nq_current_data_parity.get("cleanLocalResearchPairCount"),
                "bestCurrentLocalResearchPair": (
                    (nq_current_data_parity.get("bestCurrentLocalResearchPair") or {}).get("pairId")
                    if isinstance(nq_current_data_parity.get("bestCurrentLocalResearchPair"), dict)
                    else None
                ),
                "brokerParityChecked": bool(nq_current_data_parity.get("brokerParityChecked")),
                "sessionCount": nq_session_structure_audit.get("sessionCount"),
                "sessionDecision": nq_session_structure_audit.get("decision"),
                "historicalCoverageDecision": nq_historical_coverage_audit.get("decision"),
                "historicalCoverageBlockers": (
                    nq_historical_coverage_audit.get("blockers")
                    if isinstance(nq_historical_coverage_audit.get("blockers"), list)
                    else []
                ),
                "usableHistoricalOosCount": nq_historical_coverage_audit.get("usableHistoricalOosCount"),
                "preferredPromotionDepthCount": nq_historical_coverage_audit.get("preferredPromotionDepthCount"),
                "currentLocalCsvParityCheckedCount": nq_historical_coverage_audit.get("currentLocalCsvParityCheckedCount"),
                "currentLocalCsvParityClearedCount": nq_historical_coverage_audit.get("currentLocalCsvParityClearedCount"),
                "bestHistoricalOosCandidate": (
                    (nq_historical_coverage_audit.get("bestHistoricalOosCandidate") or {}).get("datasetId")
                    if isinstance(nq_historical_coverage_audit.get("bestHistoricalOosCandidate"), dict)
                    else None
                ),
                "bestHistoricalOosSessionCount": (
                    (nq_historical_coverage_audit.get("bestHistoricalOosCandidate") or {}).get("sessionCount")
                    if isinstance(nq_historical_coverage_audit.get("bestHistoricalOosCandidate"), dict)
                    else None
                ),
                "historicalSessionReplayDecision": nq_historical_session_replay.get("decision"),
                "historicalSessionReplayTradeCount": nq_historical_session_replay.get("tradeCount"),
                "historicalSessionReplayOos": nq_historical_session_replay.get("oosStats"),
                "historicalSessionWalkforwardDecision": nq_historical_session_walkforward.get("decision"),
                "historicalSessionWalkforwardFoldCount": nq_historical_session_walkforward.get("foldCount"),
                "historicalSessionWalkforwardPositiveFoldShare": nq_historical_session_walkforward.get("positiveFoldShare"),
                "historicalSessionWalkforwardWorstFoldNetR": nq_historical_session_walkforward.get("worstFoldNetR"),
                "historicalSessionCostStressDecision": nq_historical_session_cost_stress.get("decision"),
                "historicalSessionCostStressSurvivingCases": nq_historical_session_cost_stress.get("survivingCaseCount"),
                "historicalSessionCostStressCaseCount": nq_historical_session_cost_stress.get("caseCount"),
                "dataRequirementBlockedCount": futures_data_requirements.get("blockedCount"),
                "brokerParityPlanDecision": futures_broker_parity_plan.get("decision"),
                "brokerParityMissingProofs": futures_broker_parity_plan.get("missingProofs"),
                "overlapRows": nq_parity.get("overlapRows"),
            }
            if nq_parity and not nq_parity.get("ok"):
                reason = nq_parity.get("reason") or nq_parity.get("error")
                blocker = (
                    "external-alpha NQ current parity not cleared; historical research only"
                    if reason == "date-range-mismatch-or-no-overlap"
                    else "external-alpha NQ parity not cleared"
                )
                item["blockedBy"] = list(item.get("blockedBy") or []) + [blocker]
            if nq_historical_coverage_audit.get("currentLocalCsvParityCheckedCount") and not nq_historical_coverage_audit.get("currentLocalCsvParityClearedCount"):
                item["blockedBy"] = list(item.get("blockedBy") or []) + [
                    "historical NQ source does not overlap current local CSV bars; not current parity evidence"
                ]
        if item.get("id") == "futures-options-regime-risk-overlay":
            options_audit = audit_dataset(external_alpha_audit, "sp500_options_daily_regime")
            item["dataQuality"] = {
                "externalAlphaAudit": ".rumbling-hedge/state/external-alpha-data-audit.latest.json",
                "datasetMax": audit_max(options_audit),
                "localNq60dMin": nq_60d_min,
            }
            if nq_60d_min and audit_max(options_audit) and audit_max(options_audit) < nq_60d_min[:10]:
                item["blockedBy"] = list(item.get("blockedBy") or []) + ["options regime range does not overlap current NQ OOS data"]
        if item.get("id") == "futures-equity-breadth-nq-overlay":
            breadth_audit = audit_dataset(external_alpha_audit, "equities_5m_breadth_2026_03")
            item["dataQuality"] = {
                "externalAlphaAudit": ".rumbling-hedge/state/external-alpha-data-audit.latest.json",
                "datasetMax": audit_max(breadth_audit),
                "localNq60dMin": nq_60d_min,
            }
            if nq_60d_min and audit_max(breadth_audit) and audit_max(breadth_audit) < nq_60d_min[:10]:
                item["blockedBy"] = list(item.get("blockedBy") or []) + ["equity breadth range does not overlap current NQ OOS data"]
        if item.get("id") == "prediction-new-resolved-label-source":
            item["commands"] = [
                "npm run --silent bill:prediction-label-card-bootstrap",
                "npm run --silent bill:prediction-label-card-audit",
                "npm run --silent bill:prediction-label-source-manifest",
                "npm run --silent bill:prediction-resolved-outcome-join",
            ]
            item["dataPaths"] = [str(LABEL_SOURCE_MANIFEST)]
            item["dataAvailable"] = LABEL_SOURCE_MANIFEST.exists()
            item["dataQuality"] = {
                "labelSourceManifest": ".rumbling-hedge/state/prediction-label-source-manifest.latest.json",
                "present": bool(prediction_label_manifest),
                "watchCount": prediction_label_manifest.get("watchCount"),
                "historicalRowsLoaded": prediction_label_manifest.get("historicalRowsLoaded"),
                "labelCardRowsLoaded": prediction_label_manifest.get("labelCardRowsLoaded"),
                "usableForResearchJoinCount": prediction_label_manifest.get("usableForResearchJoinCount"),
                "itemsNeedingNewLabelSource": prediction_label_manifest.get("itemsNeedingNewLabelSource"),
                "statusCounts": prediction_label_manifest.get("statusCounts", {}),
            }
            if prediction_label_manifest and not prediction_label_manifest.get("usableForResearchJoinCount"):
                item["blockedBy"] = list(item.get("blockedBy") or []) + ["label-source manifest found zero research-join-usable watch items"]
        if item.get("id") == "prediction-clob-microstructure-new-features":
            commands = [
                "npm run --silent bill:prediction-clob-microstructure-audit",
                "npm run --silent bill:polymarket-clob-persistence",
                "npm run --silent bill:polymarket-clob-edge-gate",
            ]
            if "polymarket-clob-depth-imbalance-current-form" not in entry_ids(prediction_no_edge):
                commands.insert(1, "npm run --silent bill:prediction-clob-depth-imbalance")
            if "polymarket-clob-quote-intensity-current-form" not in entry_ids(prediction_no_edge):
                insert_at = 2 if "npm run --silent bill:prediction-clob-depth-imbalance" in commands else 1
                commands.insert(insert_at, "npm run --silent bill:prediction-clob-quote-intensity")
            if "polymarket-clob-spread-compression-current-form" not in entry_ids(prediction_no_edge):
                insert_at = 1
                if "npm run --silent bill:prediction-clob-depth-imbalance" in commands:
                    insert_at += 1
                if "npm run --silent bill:prediction-clob-quote-intensity" in commands:
                    insert_at += 1
                commands.insert(insert_at, "npm run --silent bill:prediction-clob-spread-compression")
            if "polymarket-clob-latency-staleness-current-form" not in entry_ids(prediction_no_edge):
                insert_at = 1
                for command in [
                    "npm run --silent bill:prediction-clob-depth-imbalance",
                    "npm run --silent bill:prediction-clob-quote-intensity",
                    "npm run --silent bill:prediction-clob-spread-compression",
                ]:
                    if command in commands:
                        insert_at += 1
                commands.insert(insert_at, "npm run --silent bill:prediction-clob-latency-staleness")
            if "polymarket-clob-trade-impact-current-form" not in entry_ids(prediction_no_edge):
                insert_at = 1
                for command in [
                    "npm run --silent bill:prediction-clob-depth-imbalance",
                    "npm run --silent bill:prediction-clob-quote-intensity",
                    "npm run --silent bill:prediction-clob-spread-compression",
                    "npm run --silent bill:prediction-clob-latency-staleness",
                ]:
                    if command in commands:
                        insert_at += 1
                commands.insert(insert_at, "npm run --silent bill:prediction-clob-trade-impact")
            if (
                clob_microstructure_audit.get("decision") == "research-only-current-fixed-features-exhausted"
                and int(clob_microstructure_audit.get("readyFeatureCount") or 0) == 0
            ):
                commands = [
                    "npm run --silent bill:prediction-clob-microstructure-audit",
                    "npm run --silent bill:prediction-label-source-manifest",
                    "npm run --silent bill:prediction-resolved-outcome-join",
                    "npm run --silent bill:polymarket-clob-recorder -- --duration-sec 900 --max-assets 20 --max-output-mb 128 --min-free-gb 20 --terms 'fed,rate,cpi,inflation,iran,ceasefire,war,trump,tariff,bitcoin,btc,ethereum,eth,nvidia,tesla'",
                    "npm run --silent bill:polymarket-clob-persistence",
                    "npm run --silent bill:polymarket-clob-edge-gate",
                    "npm run --silent bill:alpha-frontier-queue",
                ]
                item["researchSteps"] = [
                    "Do not replay any rejected fixed CLOB feature form from current no-edge memory.",
                    "Add longer fillable public CLOB capture and resolved labels before testing a genuinely new repo-derived feature family.",
                ]
            item["commands"] = commands
            item["dataPaths"] = list(item.get("dataPaths") or []) + [str(CLOB_MICROSTRUCTURE_AUDIT)]
            item["dataAvailable"] = bool(item.get("dataAvailable")) and CLOB_MICROSTRUCTURE_AUDIT.exists()
            item["dataQuality"] = {
                "microstructureAudit": ".rumbling-hedge/state/prediction-clob-microstructure-feature-audit.latest.json",
                "present": bool(clob_microstructure_audit),
                "readyFeatureCount": clob_microstructure_audit.get("readyFeatureCount"),
                "rawDataReadyFeatureCount": clob_microstructure_audit.get("rawDataReadyFeatureCount"),
                "rejectedFixedFeatureCount": clob_microstructure_audit.get("rejectedFixedFeatureCount"),
                "decision": clob_microstructure_audit.get("decision"),
                "rejectedBaselineStatus": ((clob_microstructure_audit.get("rejectedBaseline") or {}).get("status") if isinstance(clob_microstructure_audit.get("rejectedBaseline"), dict) else None),
                "captureRecords": ((clob_microstructure_audit.get("capture") or {}).get("recordsRead") if isinstance(clob_microstructure_audit.get("capture"), dict) else None),
            }
        if item.get("id") == "prediction-macro-rates-new-source-parser":
            item["commands"] = [
                "npm run --silent bill:kalshi-fillability-snapshot",
                "npm run --silent bill:fed-prior-upper-bound-source",
                "npm run --silent bill:prediction-macro-rates-parser-fixture",
                "npm run --silent bill:prediction-macro-rates-resolved-labels",
                "npm run --silent bill:prediction-macro-rates-requirements",
                "npm run --silent bill:prediction-macro-rates-cross-source-replay",
                "npm run --silent bill:alpha-frontier-queue",
            ]
            item["dataPaths"] = [str(PREDICTION_MACRO_RATES_REQUIREMENTS)]
            item["dataAvailable"] = PREDICTION_MACRO_RATES_REQUIREMENTS.exists()
            item["dataQuality"] = {
                "macroRatesRequirements": ".rumbling-hedge/state/prediction-macro-rates-requirements.latest.json",
                "macroRatesCrossSourceReplay": ".rumbling-hedge/state/prediction-macro-rates-cross-source-replay.latest.json",
                "present": bool(prediction_macro_rates_requirements),
                "blockedCount": prediction_macro_rates_requirements.get("blockedCount"),
                "passCount": prediction_macro_rates_requirements.get("passCount"),
                "decision": prediction_macro_rates_requirements.get("decision"),
                "crossSourceDecision": prediction_macro_rates_cross_source_replay.get("decision"),
                "crossSourceRows": prediction_macro_rates_cross_source_replay.get("rowCount"),
                "crossSourceWatchResearchCount": prediction_macro_rates_cross_source_replay.get("watchResearchCount"),
                "crossSourceBlockers": prediction_macro_rates_cross_source_replay.get("blockers"),
            }
            if prediction_macro_rates_requirements and prediction_macro_rates_requirements.get("blockedCount"):
                item["blockedBy"] = list(item.get("blockedBy") or []) + ["macro-rates requirements not cleared"]
            elif prediction_macro_rates_requirements:
                item["blockedBy"] = [
                    blocker
                    for blocker in list(item.get("blockedBy") or [])
                    if blocker != "macro-rates-line-parser-current-form"
                ]
                item["rejectedBaseline"] = "macro-rates-line-parser-current-form"
            rejected_prediction_ids = entry_ids(prediction_no_edge)
            item["rejectedBaselines"] = [
                baseline
                for baseline in [
                    "macro-rates-line-parser-current-form",
                    "macro-rates-cross-source-fee-stressed-current-form",
                ]
                if baseline in rejected_prediction_ids
            ]
        if item.get("id") == "prediction-news-first-event-lag-study":
            item["commands"] = [
                "npm run --silent bill:finnhub-news",
                "npm run --silent bill:prediction-event-news-rss",
                "npm run --silent bill:prediction-event-market-mapping-plan",
                "npm run --silent bill:prediction-event-timestamp-dataset",
                "npm run --silent bill:prediction-event-lag-requirements",
                "npm run --silent bill:prediction-event-lag-replay",
                "npm run --silent bill:prediction-event-lag-sensitivity",
                "npm run --silent bill:prediction-event-lag-watch-review",
                "npm run --silent bill:prediction-event-clob-capture-targets",
                (
                    "npm run --silent bill:prediction-event-capture-cycle -- --run-recorder "
                    f"--duration-sec 900 --max-assets 15 --max-output-mb {DEFAULT_CLOB_MAX_OUTPUT_MB} "
                    f"--min-free-gb {DEFAULT_CLOB_MIN_FREE_GB}"
                ),
                "npm run --silent bill:prediction-label-card-bootstrap",
                "npm run --silent bill:prediction-label-card-audit",
                "npm run --silent bill:prediction-label-source-manifest",
                "npm run --silent bill:prediction-event-label-gap-plan",
                "npm run --silent bill:alpha-frontier-queue",
            ]
            item["dataPaths"] = [
                str(PREDICTION_EVENT_MARKET_MAPPING_PLAN),
                str(PREDICTION_EVENT_TIMESTAMP_DATASET),
                str(PREDICTION_EVENT_LAG_REQUIREMENTS),
                str(PREDICTION_EVENT_LAG_REPLAY),
                str(PREDICTION_EVENT_LAG_SENSITIVITY),
                str(PREDICTION_EVENT_LAG_WATCH_REVIEW),
                str(PREDICTION_EVENT_CLOB_CAPTURE_TARGETS),
                str(PREDICTION_EVENT_CAPTURE_CYCLE),
                str(PREDICTION_EVENT_LABEL_GAP_PLAN),
            ]
            item["dataAvailable"] = (
                PREDICTION_EVENT_MARKET_MAPPING_PLAN.exists()
                and PREDICTION_EVENT_TIMESTAMP_DATASET.exists()
                and PREDICTION_EVENT_LAG_REQUIREMENTS.exists()
                and PREDICTION_EVENT_LAG_REPLAY.exists()
                and PREDICTION_EVENT_LAG_SENSITIVITY.exists()
                and PREDICTION_EVENT_LAG_WATCH_REVIEW.exists()
                and PREDICTION_EVENT_CLOB_CAPTURE_TARGETS.exists()
                and PREDICTION_EVENT_CAPTURE_CYCLE.exists()
                and PREDICTION_EVENT_LABEL_GAP_PLAN.exists()
            )
            item["dataQuality"] = {
                "eventMarketMappingPlan": ".rumbling-hedge/state/prediction-event-market-mapping-plan.latest.json",
                "eventTimestampDataset": ".rumbling-hedge/state/prediction-event-timestamp-dataset.latest.json",
                "eventLagRequirements": ".rumbling-hedge/state/prediction-event-lag-requirements.latest.json",
                "eventLagReplay": ".rumbling-hedge/state/prediction-event-lag-replay.latest.json",
                "eventLagSensitivity": ".rumbling-hedge/state/prediction-event-lag-sensitivity.latest.json",
                "eventLagWatchReview": ".rumbling-hedge/state/prediction-event-lag-watch-review.latest.json",
                "eventClobCaptureTargets": ".rumbling-hedge/state/prediction-event-clob-capture-targets.latest.json",
                "eventCaptureCycle": ".rumbling-hedge/state/prediction-event-capture-cycle.latest.json",
                "eventLabelGapPlan": ".rumbling-hedge/state/prediction-event-label-gap-plan.latest.json",
                "present": bool(prediction_event_lag_requirements),
                "mappingPlanPresent": bool(prediction_event_market_mapping_plan),
                "mappingCandidateCount": prediction_event_market_mapping_plan.get("candidateCount"),
                "mappingDecision": prediction_event_market_mapping_plan.get("decision"),
                "timestampDatasetPresent": bool(prediction_event_timestamp_dataset),
                "timestampDatasetDecision": prediction_event_timestamp_dataset.get("decision"),
                "timestampCoverageStatusCounts": prediction_event_timestamp_dataset.get("coverageStatusCounts"),
                "timestampForwardCaptureRequired": prediction_event_timestamp_dataset.get("forwardCaptureRequired"),
                "lagReplayPresent": bool(prediction_event_lag_replay),
                "lagReplayDecision": prediction_event_lag_replay.get("decision"),
                "lagReplayCompleteEventCount": prediction_event_lag_replay.get("completeEventCount"),
                "lagReplayRepricedWindowCount": prediction_event_lag_replay.get("repricedWindowCount"),
                "lagSensitivityPresent": bool(prediction_event_lag_sensitivity),
                "lagSensitivityDecision": prediction_event_lag_sensitivity.get("decision"),
                "lagSensitivityBestRepricedWindowCount": prediction_event_lag_sensitivity.get("bestRepricedWindowCount"),
                "lagSensitivityWatchScenarioCount": prediction_event_lag_sensitivity.get("watchScenarioCount"),
                "lagWatchReviewPresent": bool(prediction_event_lag_watch_review),
                "lagWatchReviewDecision": prediction_event_lag_watch_review.get("decision"),
                "lagWatchReviewRepricedWindowCount": prediction_event_lag_watch_review.get("repricedWatchWindowCount"),
                "captureTargetsPresent": bool(prediction_event_clob_capture_targets),
                "captureTargetCount": prediction_event_clob_capture_targets.get("targetCount"),
                "captureTargetDecision": prediction_event_clob_capture_targets.get("decision"),
                "captureCyclePresent": bool(prediction_event_capture_cycle),
                "captureCycleDecision": prediction_event_capture_cycle.get("decision"),
                "captureCycleMode": prediction_event_capture_cycle.get("mode"),
                "blockedCount": prediction_event_lag_requirements.get("blockedCount"),
                "passCount": prediction_event_lag_requirements.get("passCount"),
                "decision": prediction_event_lag_requirements.get("decision"),
                "gapPlanPresent": bool(prediction_event_label_gap_plan),
                "gapCount": prediction_event_label_gap_plan.get("gapCount"),
                "eventMappedGapCount": prediction_event_label_gap_plan.get("eventMappedGapCount"),
                "gapDecision": prediction_event_label_gap_plan.get("decision"),
            }
    items.sort(key=lambda item: int(item.get("priority", 999)))
    return {
        "command": "alpha-frontier-queue",
        "generatedAt": now_iso(),
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "readyForExecution": False,
        "readyForDemoExpansion": False,
        "readyForLive": False,
        "decision": "new-feature-research-only; execution remains locked",
        "gateSnapshot": {
            "handoffDecision": handoff.get("decision", "missing"),
            "readyForExecution": handoff.get("readyForExecution", False),
            "readyForDemoExpansion": handoff.get("readyForDemoExpansion", False),
            "readyForLive": handoff.get("readyForLive", False),
        },
        "negativeMemory": {
            "futures": rejected_memory(futures_no_edge),
            "predictionMarkets": rejected_memory(prediction_no_edge),
        },
        "frontier": items,
        "hardRules": [
            "Do not rerun current-form rejected strategies as if they are new alpha.",
            "Change one variable at a time: new data source, new feature family, or new label source.",
            "No item in this queue approves paper, demo, live, funding, sizing, or broker routing.",
            "Promotion requires explicit evidence gates, not an attractive full-sample or video/paper claim.",
        ],
    }


def render_markdown(payload: dict[str, Any]) -> str:
    generated_date = str(payload.get("generatedAt") or current_utc_date())[:10]
    lines = [
        f"# Bill Alpha Frontier Queue - {generated_date}",
        "",
        "Parent hub: [[BILL-CONTROL-HUB]]",
        "",
        "Research-only queue for genuinely new feature families. This page does not approve orders.",
        "",
        "## Gate Snapshot",
        "",
        f"- Decision: `{payload.get('decision')}`",
        f"- Handoff: `{payload.get('gateSnapshot', {}).get('handoffDecision')}`",
        f"- Ready for execution: `{payload.get('readyForExecution')}`",
        f"- Ready for demo expansion: `{payload.get('readyForDemoExpansion')}`",
        "",
        "## Frontier Items",
        "",
    ]
    for item in payload.get("frontier") or []:
        lines.extend([
            f"### {item.get('priority')}. {item.get('id')}",
            "",
            f"- Lane: `{item.get('lane')}`",
            f"- One variable: `{item.get('oneVariable')}`",
            f"- Hypothesis: {item.get('hypothesis')}",
            f"- Promotion gate: {item.get('promotionGate')}",
            f"- Data available: `{item.get('dataAvailable')}`",
            f"- Blocked by: `{item.get('blockedBy')}`",
            "- Data paths:",
        ])
        for path in item.get("dataPaths") or []:
            lines.append(f"  - `{path}`")
        lines.append("- Commands:")
        for command in item.get("commands") or []:
            lines.append(f"  - `{command}`")
        if item.get("researchSteps"):
            lines.append("- Research steps:")
            for step in item.get("researchSteps") or []:
                lines.append(f"  - {step}")
        lines.append("")
    lines.extend(["## Hard Rules", ""])
    for rule in payload.get("hardRules") or []:
        lines.append(f"- {rule}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    catalog = read_catalog()
    futures_no_edge = read_json(RESEARCH / "futures-no-edge-ledger/latest.json")
    prediction_no_edge = read_json(RESEARCH / "prediction-no-edge-ledger/latest.json")
    handoff = read_json(STATE / "bill-clearance-handoff.latest.json")
    external_alpha_audit = read_json(STATE / "external-alpha-data-audit.latest.json")
    prediction_label_manifest = read_json(LABEL_SOURCE_MANIFEST)
    clob_microstructure_audit = read_json(CLOB_MICROSTRUCTURE_AUDIT)
    nq_session_structure_audit = read_json(NQ_SESSION_STRUCTURE_AUDIT)
    nq_historical_coverage_audit = read_json(NQ_HISTORICAL_COVERAGE_AUDIT)
    nq_historical_session_replay = read_json(NQ_HISTORICAL_SESSION_REPLAY)
    nq_historical_session_walkforward = read_json(NQ_HISTORICAL_SESSION_WALKFORWARD)
    nq_historical_session_cost_stress = read_json(NQ_HISTORICAL_SESSION_COST_STRESS)
    nq_current_data_parity = read_json(NQ_CURRENT_DATA_PARITY)
    futures_data_requirements = read_json(FUTURES_DATA_REQUIREMENTS)
    futures_broker_parity_plan = read_json(FUTURES_BROKER_PARITY_PLAN)
    prediction_event_lag_requirements = read_json(PREDICTION_EVENT_LAG_REQUIREMENTS)
    prediction_event_market_mapping_plan = read_json(PREDICTION_EVENT_MARKET_MAPPING_PLAN)
    prediction_event_timestamp_dataset = read_json(PREDICTION_EVENT_TIMESTAMP_DATASET)
    prediction_event_lag_replay = read_json(PREDICTION_EVENT_LAG_REPLAY)
    prediction_event_lag_sensitivity = read_json(PREDICTION_EVENT_LAG_SENSITIVITY)
    prediction_event_lag_watch_review = read_json(PREDICTION_EVENT_LAG_WATCH_REVIEW)
    prediction_event_clob_capture_targets = read_json(PREDICTION_EVENT_CLOB_CAPTURE_TARGETS)
    prediction_event_capture_cycle = read_json(PREDICTION_EVENT_CAPTURE_CYCLE)
    prediction_event_label_gap_plan = read_json(PREDICTION_EVENT_LABEL_GAP_PLAN)
    prediction_macro_rates_requirements = read_json(PREDICTION_MACRO_RATES_REQUIREMENTS)
    prediction_macro_rates_cross_source_replay = read_json(PREDICTION_MACRO_RATES_CROSS_SOURCE_REPLAY)
    paper_source_cards = read_json(PAPER_SOURCE_CARDS)
    payload = build_frontier(
        catalog=catalog,
        futures_no_edge=futures_no_edge,
        prediction_no_edge=prediction_no_edge,
        handoff=handoff,
        external_alpha_audit=external_alpha_audit,
        prediction_label_manifest=prediction_label_manifest,
        clob_microstructure_audit=clob_microstructure_audit,
        nq_session_structure_audit=nq_session_structure_audit,
        nq_historical_coverage_audit=nq_historical_coverage_audit,
        nq_historical_session_replay=nq_historical_session_replay,
        nq_historical_session_walkforward=nq_historical_session_walkforward,
        nq_historical_session_cost_stress=nq_historical_session_cost_stress,
        nq_current_data_parity=nq_current_data_parity,
        futures_data_requirements=futures_data_requirements,
        futures_broker_parity_plan=futures_broker_parity_plan,
        prediction_event_lag_requirements=prediction_event_lag_requirements,
        prediction_event_market_mapping_plan=prediction_event_market_mapping_plan,
        prediction_event_timestamp_dataset=prediction_event_timestamp_dataset,
        prediction_event_lag_replay=prediction_event_lag_replay,
        prediction_event_lag_sensitivity=prediction_event_lag_sensitivity,
        prediction_event_lag_watch_review=prediction_event_lag_watch_review,
        prediction_event_clob_capture_targets=prediction_event_clob_capture_targets,
        prediction_event_capture_cycle=prediction_event_capture_cycle,
        prediction_event_label_gap_plan=prediction_event_label_gap_plan,
        prediction_macro_rates_requirements=prediction_macro_rates_requirements,
        prediction_macro_rates_cross_source_replay=prediction_macro_rates_cross_source_replay,
        paper_source_cards=paper_source_cards,
        youtube_source_cards_path=YOUTUBE_SOURCE_CARDS_MD,
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    HERMES.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    default_markdown_path().write_text(render_markdown(payload))
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
