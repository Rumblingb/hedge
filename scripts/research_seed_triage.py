#!/usr/bin/env python3
"""Triage Bill/Hermes YT, paper, and web strategy seeds.

Research-only. This keeps founder/Hermes "gold" labels from becoming
execution evidence until a seed has local implementation, OOS, cost/slippage,
and promotion artifacts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge/state"
RESEARCH = ROOT / ".rumbling-hedge/research"
VAULT = Path.home() / "Documents" / "memorybrain"
HERMES = VAULT / "Agent-Hermes"
DEFAULT_HYPOTHESES = RESEARCH / "researcher/strategy-hypotheses.latest.json"
DEFAULT_STRATEGY_FEED = RESEARCH / "researcher/strategy-feed.latest.json"
DEFAULT_STRATEGY_ZOO = STATE / "strategy-zoo-audit.latest.json"
DEFAULT_FUTURES_NO_EDGE = RESEARCH / "futures-no-edge-ledger/latest.json"
DEFAULT_PREDICTION_NO_EDGE = RESEARCH / "prediction-no-edge-ledger/latest.json"
DEFAULT_BACKTRADER_RESEARCH = STATE / "backtrader-research.latest.json"
DEFAULT_YOUTUBE_QUEUE = VAULT / "Research-Catalog" / "youtube-queue.md"
DEFAULT_RESEARCHER_LATEST_RUN = RESEARCH / "researcher/latest-run.json"
DEFAULT_YOUTUBE_SOURCE_CARDS = VAULT / "Research-Catalog" / "Youtube-Transcript-Source-Cards-2026-05-30.md"
DEFAULT_OUTPUT = STATE / "research-seed-triage.latest.json"
DEFAULT_YOUTUBE_TARGETS_OUTPUT = STATE / "research-seed-youtube-targets.latest.json"


def current_utc_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


DEFAULT_MARKDOWN = HERMES / f"research-seed-triage-{current_utc_date()}.md"


def read_json(path: Path, default: Any | None = None) -> Any:
    try:
        return json.loads(path.read_text())
    except Exception:
        return {} if default is None else default


def stable_queue_id(url: str, title: str) -> str:
    digest = hashlib.sha1(f"{url}|{title}".encode("utf-8")).hexdigest()[:12]
    return f"youtube-queue-{digest}"


def parse_youtube_queue(path: Path) -> list[dict[str, Any]]:
    """Convert the Obsidian YouTube queue into research-only seed stubs."""
    if not path.exists():
        return []
    seeds: list[dict[str, Any]] = []
    channel = "unknown"
    pattern = re.compile(r"- \[(?P<title>[^\]]+)\]\((?P<url>https?://[^)]+)\)")
    for raw in path.read_text(errors="ignore").splitlines():
        line = raw.strip()
        if line.startswith("## "):
            channel = line.removeprefix("## ").strip()
            continue
        match = pattern.search(line)
        if not match:
            continue
        title = match.group("title").strip()
        url = match.group("url").strip()
        seeds.append({
            "id": stable_queue_id(url, title),
            "title": title,
            "market": "research-inbox",
            "sourceOrigin": "youtube-queue",
            "sourceChannels": [channel],
            "sourceVideoTitles": [title],
            "sourceUrls": [url],
            "evidence": [
                "Queued video only; transcript/rules/local replay not extracted yet."
            ],
        })
    return seeds


def queued_youtube_targets(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict) or item.get("sourceOrigin") != "youtube-queue":
            continue
        urls = item.get("sourceUrls") if isinstance(item.get("sourceUrls"), list) else []
        if not urls:
            continue
        targets.append({
            "id": str(item.get("id") or stable_queue_id(str(urls[0]), str(item.get("title") or ""))),
            "kind": "youtube-transcript",
            "videos": [str(urls[0])],
            "limit": 1,
            "priority": 1,
            "cadence": "manual",
            "rationale": (
                "Queued Bill/Hermes research seed. Extract transcript into explicit entry, stop, "
                "target, risk, contrary, and one-variable test rules before any local replay."
            ),
            "tags": [
                "bill",
                "research-seed",
                "youtube-queue",
                "futures-core",
                "prediction-market-watch",
            ],
        })
    return targets


def queued_youtube_latest_run_summary(payload: dict[str, Any]) -> dict[str, Any]:
    if not payload:
        return {"present": False}
    target_results = payload.get("targetResults") if isinstance(payload.get("targetResults"), list) else []
    queued_results = [
        item for item in target_results
        if isinstance(item, dict) and str(item.get("targetId") or "").startswith("youtube-queue-")
    ]
    if not queued_results:
        return {"present": False}
    failed = [item for item in queued_results if item.get("error")]
    return {
        "present": True,
        "runId": payload.get("runId"),
        "status": payload.get("status"),
        "targetsAttempted": len(queued_results),
        "targetsSucceeded": len(queued_results) - len(failed),
        "strategyHypothesesCount": payload.get("strategyHypothesesCount", 0),
        "chunksCollected": payload.get("chunksCollected", 0),
        "transcriptArtifactsDeleted": payload.get("transcriptArtifactsDeleted", 0),
        "blockers": payload.get("blockers") if isinstance(payload.get("blockers"), list) else [],
        "failedTargetIds": [str(item.get("targetId")) for item in failed],
        "targetResults": [
            {
                "targetId": item.get("targetId"),
                "videosProcessed": item.get("videosProcessed"),
                "collected": item.get("collected"),
                "kept": item.get("kept"),
                "error": item.get("error"),
            }
            for item in queued_results
        ],
    }


def parse_youtube_source_cards(path: Path) -> dict[str, Any]:
    """Summarize the durable Obsidian source-card note for queued YT runs."""
    if not path.exists():
        return {"present": False, "path": str(path)}
    text = path.read_text(errors="ignore")
    run_match = re.search(r"Researcher run:\s*`([^`]+)`", text)
    result_match = re.search(
        r"Result:\s*`(?P<succeeded>\d+)/(?P<attempted>\d+)`\s*queued YouTube targets succeeded,\s*"
        r"`(?P<kept>\d+)`\s*raw transcript chunks kept,\s*"
        r"`(?P<promoted>\d+)`\s*strategy hypotheses promoted",
        text,
    )
    cards: list[dict[str, str]] = []
    in_table = False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("| Source | Decision | Lane |"):
            in_table = True
            continue
        if in_table and (not line.startswith("|") or line.startswith("## ")):
            break
        if not in_table or set(line.replace("|", "").strip()) <= {"-", " "}:
            continue
        parts = [part.strip() for part in line.strip("|").split("|")]
        if len(parts) < 5:
            continue
        link = re.search(r"\[([^\]]+)\]\(([^)]+)\)", parts[0])
        cards.append({
            "title": link.group(1) if link else parts[0],
            "url": link.group(2) if link else "",
            "decision": parts[1].strip("`"),
            "lane": parts[2].strip("`"),
            "tradableVariable": parts[3],
            "oneVariableTest": parts[4],
        })

    result: dict[str, Any] = {
        "present": True,
        "path": str(path),
        "researcherRun": run_match.group(1) if run_match else None,
        "cards": cards,
        "executionRelevant": False,
        "operatorRead": (
            "Durable source cards exist for queued YouTube transcripts. They are hypothesis "
            "evidence only; latest-run.json may be overwritten by newer researcher runs."
        ),
    }
    if result_match:
        result.update({
            "targetsSucceeded": int(result_match.group("succeeded")),
            "targetsAttempted": int(result_match.group("attempted")),
            "rawTranscriptChunksKept": int(result_match.group("kept")),
            "strategyHypothesesPromoted": int(result_match.group("promoted")),
        })
    return result


def text_blob(item: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in [
        "title",
        "market",
        "setupSummary",
        "sourceTargetIds",
        "sourceVideoTitles",
        "sourceChannels",
        "sourceUrls",
    ]:
        value = item.get(key)
        if isinstance(value, list):
            parts.extend(str(part) for part in value)
        elif value is not None:
            parts.append(str(value))
    for key in ["biasRules", "entryRules", "stopRules", "targetRules", "riskRules", "evidence"]:
        value = item.get(key)
        if isinstance(value, list):
            parts.extend(str(part) for part in value)
    return " ".join(parts).lower()


def source_kinds(item: dict[str, Any]) -> list[str]:
    blob = text_blob(item)
    kinds: set[str] = set()
    if item.get("sourceVideoIds") or "youtube" in blob or "youtu.be" in blob:
        kinds.add("youtube")
    if any(token in blob for token in ["arxiv", "doi.org", "nber", "wiley", "springer", "openalex", "paper"]):
        kinds.add("paper")
    if any(token in blob for token in ["backtest", "win rate", "profit", "drawdown", "sharpe"]):
        kinds.add("external-backtest-claim")
    return sorted(kinds or {"unknown"})


def infer_strategy_id(item: dict[str, Any]) -> str | None:
    blob = text_blob(item)
    if "liquidity reversion" in blob:
        return "liquidity-reversion"
    if "volume profile" in blob or "auction market" in blob:
        return "auction-profile-unmapped"
    if any(token in blob for token in ["ict", "fvg", "fair value gap", "order block", "smart money", "liquidity sweep"]):
        return "ict-displacement"
    if "opening range" in blob or "orb" in blob or "opening auction" in blob:
        return "opening-range-reversal"
    if "donchian" in blob:
        return "donchian-breakout"
    if "trend" in blob and "momentum" in blob:
        return "wq-trend-mom"
    if "daily range" in blob or "range breakout" in blob:
        return "daily-range-breakout"
    if "bollinger" in blob or "rsi" in blob or "mean reversion" in blob:
        return "mean-reversion-unmapped"
    if "prediction" in blob or "polymarket" in blob or "kalshi" in blob:
        return "prediction-market-unmapped"
    return None


def list_len(item: dict[str, Any], key: str) -> int:
    value = item.get(key)
    return len(value) if isinstance(value, list) else 0


def machine_testable(item: dict[str, Any]) -> bool:
    return (
        list_len(item, "entryRules") > 0
        and list_len(item, "stopRules") > 0
        and list_len(item, "targetRules") > 0
        and (list_len(item, "symbols") > 0 or list_len(item, "timeframes") > 0)
    )


def blocked_strategy_ids(strategy_feed: dict[str, Any]) -> set[str]:
    blocked: set[str] = set()
    for item in strategy_feed.get("blockedDirectives") or []:
        if isinstance(item, dict) and isinstance(item.get("strategyId"), str):
            blocked.add(item["strategyId"])
    return blocked


def no_edge_ids(*ledgers: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for ledger in ledgers:
        for item in ledger.get("entries") or []:
            if not isinstance(item, dict):
                continue
            verdict = str(item.get("verdict") or "")
            if verdict in {"no-edge", "needs-new-feature"} and isinstance(item.get("id"), str):
                ids.add(item["id"])
    return ids


def strategy_zoo_index(zoo: dict[str, Any]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for item in zoo.get("items") or []:
        if isinstance(item, dict) and isinstance(item.get("strategyId"), str):
            index[item["strategyId"]] = item
    return index


def backtrader_local_rejections(backtrader: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return strategy families whose current local Backtrader rows are all negative."""
    families = ["wq-trend-mom", "wq-vol-regime", "orb-breakout"]
    rows = backtrader.get("results") if isinstance(backtrader.get("results"), list) else []
    grouped: dict[str, list[dict[str, Any]]] = {family: [] for family in families}
    for row in rows:
        if not isinstance(row, dict):
            continue
        strategy = str(row.get("strategy") or "")
        for family in families:
            if strategy.startswith(family):
                grouped[family].append(row)

    rejected: dict[str, dict[str, Any]] = {}
    for family, items in grouped.items():
        scored = [
            item for item in items
            if isinstance(item.get("totalR"), (int, float))
        ]
        if not scored:
            continue
        best = max(scored, key=lambda item: float(item.get("totalR", 0)))
        if float(best.get("totalR", 0)) <= 0:
            rejected[family] = {
                "rows": len(scored),
                "bestStrategy": best.get("strategy"),
                "bestTotalR": best.get("totalR"),
                "bestAvgR": best.get("avgR"),
            }
    return rejected


def decision_for(
    strategy_id: str | None,
    testable: bool,
    zoo_item: dict[str, Any] | None,
    blocked_ids: set[str],
    rejected_ids: set[str],
    local_rejections: dict[str, dict[str, Any]] | None = None,
) -> tuple[str, list[str], str]:
    blockers: list[str] = []
    local_rejections = local_rejections or {}
    if strategy_id is None:
        return (
            "research-only-narrative-seed",
            ["no local strategy family inferred"],
            "Create a machine-testable hypothesis card before coding.",
        )
    if strategy_id.endswith("-unmapped"):
        return (
            "research-only-unmapped-seed",
            ["no local executable strategy family exists"],
            "Create a small local replay implementation before spending OOS budget.",
        )
    if strategy_id in blocked_ids:
        blockers.append("blocked by current strategy-feed no-edge memory")
    if strategy_id in rejected_ids:
        blockers.append("blocked by no-edge ledger")
    if strategy_id in local_rejections:
        evidence = local_rejections[strategy_id]
        blockers.append(
            "local Backtrader replay rejected current form "
            f"(rows={evidence.get('rows')}, bestTotalR={evidence.get('bestTotalR')})"
        )
    if zoo_item and zoo_item.get("classification") == "QUARANTINED":
        blockers.append("strategy zoo classification is QUARANTINED")
    if blockers:
        return (
            "quarantine-no-edge",
            blockers,
            "Do not retest unless a genuinely new feature/filter supersedes the rejected mechanics.",
        )
    if not zoo_item:
        return (
            "research-only-unregistered",
            ["strategy family not present in strategy zoo"],
            "Register a local deterministic implementation before OOS work.",
        )
    if zoo_item.get("phase") == "candidate-retest" and testable:
        return (
            "candidate-retest-research-only",
            ["requires fresh local OOS, cost/slippage, and live-readiness gates"],
            "Run one-variable local replay; reject on negative worst fold or cost stress.",
        )
    if not testable:
        return (
            "research-only-needs-rules",
            ["seed is not fully machine-testable"],
            "Extract explicit entry, stop, target, symbol, timeframe, and invalidation rules.",
        )
    return (
        "research-only-hypothesis",
        ["not approved by promotion/live-readiness gates"],
        "Keep as a hypothesis until local evidence exists.",
    )


def classify_seed(
    item: dict[str, Any],
    zoo_index: dict[str, dict[str, Any]],
    blocked_ids: set[str],
    rejected_ids: set[str],
    local_rejections: dict[str, dict[str, Any]] | None = None,
    stable_id: str | None = None,
) -> dict[str, Any]:
    strategy_id = infer_strategy_id(item)
    testable = machine_testable(item)
    zoo_item = zoo_index.get(strategy_id or "")
    decision, blockers, next_action = decision_for(
        strategy_id,
        testable,
        zoo_item,
        blocked_ids,
        rejected_ids,
        local_rejections,
    )
    return {
        "id": stable_id or item.get("id") or "missing",
        "sourceId": item.get("id") or "missing",
        "title": item.get("title") or "Untitled",
        "market": item.get("market") or "unknown",
        "inferredStrategyId": strategy_id,
        "sourceKinds": source_kinds(item),
        "machineTestable": testable,
        "localClassification": zoo_item.get("classification") if zoo_item else None,
        "localPhase": zoo_item.get("phase") if zoo_item else None,
        "localExecutable": bool(zoo_item.get("executable")) if zoo_item else False,
        "decision": decision,
        "blockers": blockers,
        "nextAction": next_action,
        "sourceUrls": item.get("sourceUrls") if isinstance(item.get("sourceUrls"), list) else [],
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    hypotheses = read_json(Path(args.hypotheses), {"hypotheses": []})
    items = hypotheses.get("hypotheses") if isinstance(hypotheses.get("hypotheses"), list) else []
    youtube_queue_path = getattr(args, "youtube_queue", None)
    queue_items = parse_youtube_queue(Path(youtube_queue_path)) if youtube_queue_path else []
    items = list(items) + queue_items
    youtube_targets = queued_youtube_targets(queue_items)
    zoo = read_json(Path(args.strategy_zoo))
    feed = read_json(Path(args.strategy_feed))
    futures_no_edge = read_json(Path(args.futures_no_edge))
    prediction_no_edge = read_json(Path(args.prediction_no_edge))
    backtrader = read_json(Path(getattr(args, "backtrader_research", DEFAULT_BACKTRADER_RESEARCH)))
    researcher_latest = read_json(Path(getattr(args, "researcher_latest_run", DEFAULT_RESEARCHER_LATEST_RUN)))
    youtube_source_cards = parse_youtube_source_cards(
        Path(getattr(args, "youtube_source_cards", DEFAULT_YOUTUBE_SOURCE_CARDS))
    )

    zoo_idx = strategy_zoo_index(zoo)
    blocked_ids = blocked_strategy_ids(feed)
    rejected_ids = no_edge_ids(futures_no_edge, prediction_no_edge)
    local_rejections = backtrader_local_rejections(backtrader)
    seen_ids: dict[str, int] = {}
    triaged: list[dict[str, Any]] = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            continue
        raw_id = str(item.get("id") or f"missing-{index}")
        seen_ids[raw_id] = seen_ids.get(raw_id, 0) + 1
        stable_id = raw_id if seen_ids[raw_id] == 1 else f"{raw_id}#{seen_ids[raw_id]}"
        triaged.append(classify_seed(item, zoo_idx, blocked_ids, rejected_ids, local_rejections, stable_id))

    def count(predicate) -> int:
        return sum(1 for item in triaged if predicate(item))

    next_build_queue = [
        item for item in triaged
        if item["decision"] == "candidate-retest-research-only"
    ][:5]
    summary = {
        "totalSeeds": len(triaged),
        "queuedYouTubeSeeds": len(queue_items),
        "youtubeSeeds": count(lambda item: "youtube" in item["sourceKinds"]),
        "paperSeeds": count(lambda item: "paper" in item["sourceKinds"]),
        "externalBacktestClaims": count(lambda item: "external-backtest-claim" in item["sourceKinds"]),
        "machineTestableSeeds": count(lambda item: item["machineTestable"]),
        "candidateRetestSeeds": len(next_build_queue),
        "quarantinedNoEdgeSeeds": count(lambda item: item["decision"] == "quarantine-no-edge"),
        "unmappedSeeds": count(lambda item: item["decision"] == "research-only-unmapped-seed"),
        "duplicateSourceIds": sum(count - 1 for count in seen_ids.values() if count > 1),
        "localBacktraderRejectedFamilies": len(local_rejections),
        "executableSeeds": 0,
    }
    payload = {
        "command": "research-seed-triage",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "researchOnly": True,
        "writesOrders": False,
        "readyForExecution": False,
        "decision": "research-only; no seed is executable without local OOS/promotion evidence",
        "totalSeeds": summary["totalSeeds"],
        "queuedYT": summary["queuedYouTubeSeeds"],
        "candidateRetest": summary["candidateRetestSeeds"],
        "quarantinedNoEdge": summary["quarantinedNoEdgeSeeds"],
        "executable": summary["executableSeeds"],
        "summary": summary,
        "localBacktraderRejections": local_rejections,
        "nextBuildQueue": next_build_queue,
        "queuedYouTubeResearcherTargets": youtube_targets,
        "queuedYouTubeLatestRun": queued_youtube_latest_run_summary(researcher_latest),
        "queuedYouTubeSourceCards": youtube_source_cards,
        "items": triaged,
        "hardRules": [
            "YT/paper/web 'gold' is a source label, not edge evidence.",
            "External backtest claims cannot promote a strategy without local replay.",
            "No seed can route demo/live from this artifact.",
            "Durable transcript/source cards can preserve prior queued runs, but they remain hypothesis-only.",
            "Quarantined/no-edge families require a new independent feature before retest.",
        ],
    }
    return payload


def render_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    generated_date = str(report.get("generatedAt") or current_utc_date())[:10]
    lines = [
        f"# Research Seed Triage - {generated_date}",
        "",
        "Parent hub: [[BILL-CONTROL-HUB]]",
        "",
        "Research-only. This note separates YT/paper/web strategy seeds from execution evidence.",
        "",
        "## Summary",
        "",
        f"- Total seeds: `{summary.get('totalSeeds', 0)}`",
        f"- Queued YouTube seeds: `{summary.get('queuedYouTubeSeeds', 0)}`",
        f"- Machine-testable seeds: `{summary.get('machineTestableSeeds', 0)}`",
        f"- Candidate retest seeds: `{summary.get('candidateRetestSeeds', 0)}`",
        f"- Quarantined/no-edge seeds: `{summary.get('quarantinedNoEdgeSeeds', 0)}`",
        f"- External backtest claims: `{summary.get('externalBacktestClaims', 0)}`",
        f"- Executable seeds: `0`",
        "",
        "## Next Build Queue",
        "",
    ]
    queue = report.get("nextBuildQueue") if isinstance(report.get("nextBuildQueue"), list) else []
    if not queue:
        lines.append("- None. No seed has local evidence good enough for retest priority.")
    for item in queue:
        lines.append(f"- `{item.get('inferredStrategyId')}` - {item.get('title')} - {item.get('nextAction')}")
    queued = [
        item for item in report.get("items", [])
        if isinstance(item, dict) and str(item.get("sourceId", "")).startswith("youtube-queue-")
    ][:10]
    lines.extend(["", "## Queued YouTube Seeds", ""])
    if not queued:
        lines.append("- None found in the current YouTube queue.")
    for item in queued:
        urls = item.get("sourceUrls") if isinstance(item.get("sourceUrls"), list) else []
        lines.append(
            f"- `{item.get('decision')}` - {item.get('title')} - {urls[0] if urls else 'missing-url'}"
        )
    targets = report.get("queuedYouTubeResearcherTargets") if isinstance(report.get("queuedYouTubeResearcherTargets"), list) else []
    lines.extend(["", "## Queued YouTube Researcher Targets", ""])
    if not targets:
        lines.append("- None. Run seed triage after the YouTube queue updates.")
    for target in targets[:10]:
        lines.append(
            f"- `{target.get('id')}` videos `{target.get('videos')}` cadence `{target.get('cadence')}`"
        )
    latest = report.get("queuedYouTubeLatestRun") if isinstance(report.get("queuedYouTubeLatestRun"), dict) else {}
    lines.extend(["", "## Queued YouTube Latest Researcher Run", ""])
    if not latest.get("present"):
        lines.append("- No queued-video researcher run found yet.")
    else:
        lines.extend([
            f"- Run: `{latest.get('runId')}`",
            f"- Status: `{latest.get('status')}`",
            f"- Targets: `{latest.get('targetsSucceeded')}/{latest.get('targetsAttempted')}`",
            f"- Strategy hypotheses: `{latest.get('strategyHypothesesCount')}`",
            f"- Transcript artifacts deleted: `{latest.get('transcriptArtifactsDeleted')}`",
            f"- Failed target ids: `{latest.get('failedTargetIds')}`",
        ])
        blockers = latest.get("blockers") if isinstance(latest.get("blockers"), list) else []
        for blocker in blockers[:3]:
            lines.append(f"  - blocker: `{blocker}`")
    source_cards = report.get("queuedYouTubeSourceCards") if isinstance(report.get("queuedYouTubeSourceCards"), dict) else {}
    lines.extend(["", "## Queued YouTube Source Cards", ""])
    if not source_cards.get("present"):
        lines.append("- No durable queued-video source-card note found yet.")
    else:
        lines.extend([
            f"- Note: [{Path(str(source_cards.get('path') or '')).name}](<{source_cards.get('path')}>)",
            f"- Researcher run: `{source_cards.get('researcherRun')}`",
            f"- Queued targets: `{source_cards.get('targetsSucceeded', 'unknown')}/{source_cards.get('targetsAttempted', 'unknown')}`",
            f"- Raw chunks kept: `{source_cards.get('rawTranscriptChunksKept', 'unknown')}`",
            f"- Strategy hypotheses promoted: `{source_cards.get('strategyHypothesesPromoted', 'unknown')}`",
            f"- Execution relevant: `{source_cards.get('executionRelevant')}`",
        ])
        for card in source_cards.get("cards", [])[:6]:
            if isinstance(card, dict):
                lines.append(
                    f"- `{card.get('decision')}` / `{card.get('lane')}` - "
                    f"{card.get('title')} - {card.get('oneVariableTest')}"
                )
    lines.extend(["", "## Hard Rules", ""])
    for rule in report.get("hardRules") or []:
        lines.append(f"- {rule}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hypotheses", default=str(DEFAULT_HYPOTHESES))
    parser.add_argument("--strategy-feed", default=str(DEFAULT_STRATEGY_FEED))
    parser.add_argument("--strategy-zoo", default=str(DEFAULT_STRATEGY_ZOO))
    parser.add_argument("--futures-no-edge", default=str(DEFAULT_FUTURES_NO_EDGE))
    parser.add_argument("--prediction-no-edge", default=str(DEFAULT_PREDICTION_NO_EDGE))
    parser.add_argument("--backtrader-research", default=str(DEFAULT_BACKTRADER_RESEARCH))
    parser.add_argument("--youtube-queue", default=str(DEFAULT_YOUTUBE_QUEUE))
    parser.add_argument("--researcher-latest-run", default=str(DEFAULT_RESEARCHER_LATEST_RUN))
    parser.add_argument("--youtube-source-cards", default=str(DEFAULT_YOUTUBE_SOURCE_CARDS))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--youtube-targets-output", default=str(DEFAULT_YOUTUBE_TARGETS_OUTPUT))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))
    args = parser.parse_args()

    report = build_report(args)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    youtube_targets_output = Path(args.youtube_targets_output)
    youtube_targets_output.parent.mkdir(parents=True, exist_ok=True)
    youtube_targets_output.write_text(json.dumps({
        "generatedAt": report["generatedAt"],
        "researchOnly": True,
        "writesOrders": False,
        "readyForExecution": False,
        "targets": report.get("queuedYouTubeResearcherTargets", []),
    }, indent=2, sort_keys=True) + "\n")
    markdown = Path(args.markdown)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    markdown.write_text(render_markdown(report))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
