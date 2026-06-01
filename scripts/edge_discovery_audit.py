#!/usr/bin/env python3
"""
Audit Bill/Hermes edge discovery, research evidence, cron posture, and data
freshness without touching broker execution.
"""

from __future__ import annotations

import csv
import json
import os
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


HOME = Path.home()
ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / ".rumbling-hedge" / "state"
RESEARCH_DIR = ROOT / ".rumbling-hedge" / "research"
OBSIDIAN = HOME / "Documents" / "memorybrain"
OBSIDIAN_HERMES = OBSIDIAN / "Agent-Hermes"
OBSIDIAN_RESEARCH = OBSIDIAN / "Research-Catalog"
HERMES_CRON = HOME / ".hermes" / "cron" / "jobs.json"
N8N_DB = HOME / ".n8n" / "database.sqlite"

OUTPUT_JSON = STATE_DIR / "edge-discovery-audit.latest.json"
OUTPUT_MD = OBSIDIAN_HERMES / "BILL-EDGE-DISCOVERY-AUDIT-2026-05-29.md"

CORE_DATASETS = [
    ROOT / "data/free/ALL-6MARKETS-1m-5d-normalized.csv",
    ROOT / "data/free/ALL-6MARKETS-15m-60d-normalized.csv",
    ROOT / "data/free/ALL-6MARKETS-30m-60d-normalized.csv",
    ROOT / "data/free/ALL-6MARKETS-60m-60d-normalized.csv",
    ROOT / "data/free/NQ-1m-5d.csv",
    ROOT / "data/free/ES-1m-5d.csv",
    ROOT / "data/free/NQ-15m-60d.csv",
    ROOT / "data/free/NQ-60m-60d.csv",
]

LEGACY_RESEARCH_DATASETS = [
    ROOT / "data/free/ALL-2MARKETS-NQ-ES-1m-21d-normalized.csv",
    ROOT / "data/free/ALL-2MARKETS-NQ-ES-1m-21d-normalized-5m.csv",
    ROOT / "data/free/ALL-2MARKETS-NQ-ES-1m-21d-normalized-15m.csv",
    ROOT / "data/free/ALL-2MARKETS-NQ-ES-1m-21d-normalized-30m.csv",
    ROOT / "data/free/ALL-2MARKETS-NQ-ES-1m-21d-normalized-60m.csv",
    ROOT / "data/research/ALL-6MARKETS-1m-30d-normalized.csv",
]


@dataclass
class Finding:
    severity: str
    area: str
    finding: str
    evidence: str
    action: str


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def resolved_subject_summary(payload: dict[str, Any], limit: int = 6) -> list[dict[str, Any]]:
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    return [
        {
            "externalId": item.get("externalId"),
            "status": item.get("status"),
            "resolvedMatchCount": item.get("resolvedMatchCount"),
            "subjectSpecificMatchCount": item.get("subjectSpecificMatchCount"),
        }
        for item in items[:limit]
        if isinstance(item, dict)
    ]


def disk_free(path: Path) -> dict[str, Any]:
    stat = os.statvfs(path)
    free = stat.f_bavail * stat.f_frsize
    total = stat.f_blocks * stat.f_frsize
    return {
        "path": str(path),
        "freeBytes": free,
        "totalBytes": total,
        "freeGiB": round(free / 1024 / 1024 / 1024, 3),
        "usedPct": round((1 - free / total) * 100, 2) if total else None,
    }


def parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def audit_csv(path: Path) -> dict[str, Any]:
    out: dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
        "rows": 0,
        "symbols": [],
        "latestTs": None,
        "latestAgeHours": None,
        "duplicateTimestampSymbolRows": 0,
        "timeReversals": 0,
        "nullOhlcvCells": 0,
        "zeroVolumeTail": False,
    }
    if not path.exists():
        return out

    out["mtime"] = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
    out["sizeBytes"] = path.stat().st_size
    seen: set[tuple[str, datetime]] = set()
    prev_by_symbol: dict[str, datetime] = {}
    latest: datetime | None = None
    symbols: set[str] = set()
    last_rows: list[dict[str, str]] = []

    try:
        with path.open(newline="") as fh:
            reader = csv.DictReader(fh)
            fields = reader.fieldnames or []
            time_col = next((c for c in fields if c.lower() in {"ts", "timestamp", "datetime", "time", "date"}), fields[0] if fields else None)
            symbol_col = next((c for c in fields if c.lower() in {"symbol", "ticker", "market"}), None)
            out["timeColumn"] = time_col
            out["symbolColumn"] = symbol_col
            for row in reader:
                out["rows"] += 1
                if len(last_rows) >= 12:
                    last_rows.pop(0)
                last_rows.append(row)
                symbol = row.get(symbol_col, "ALL") if symbol_col else "ALL"
                symbols.add(symbol)
                dt = parse_ts(row.get(time_col)) if time_col else None
                if dt:
                    latest = max(latest, dt) if latest else dt
                    key = (symbol, dt)
                    if key in seen:
                        out["duplicateTimestampSymbolRows"] += 1
                    seen.add(key)
                    prev = prev_by_symbol.get(symbol)
                    if prev and dt < prev:
                        out["timeReversals"] += 1
                    prev_by_symbol[symbol] = dt
                for col in ("open", "high", "low", "close", "volume", "Open", "High", "Low", "Close", "Volume"):
                    if col in row and row.get(col) in {"", "nan", "NaN", "None"}:
                        out["nullOhlcvCells"] += 1
    except Exception as exc:
        out["error"] = str(exc)
        return out

    out["symbols"] = sorted(s for s in symbols if s)
    if latest:
        out["latestTs"] = latest.isoformat()
        out["latestAgeHours"] = round((datetime.now(timezone.utc) - latest).total_seconds() / 3600, 2)
    out["zeroVolumeTail"] = bool(last_rows) and all(str(row.get("volume", row.get("Volume", ""))) in {"0", "0.0"} for row in last_rows[-3:])
    return out


def load_jobs() -> list[dict[str, Any]]:
    data = read_json(HERMES_CRON)
    jobs = data.get("jobs", data) if isinstance(data, dict) else data
    if isinstance(jobs, dict):
        jobs = list(jobs.values())
    return [job for job in jobs if isinstance(job, dict)]


def n8n_summary() -> dict[str, Any]:
    out = {"db": str(N8N_DB), "exists": N8N_DB.exists(), "active": 0, "inactive": 0, "billWorkflows": []}
    if not N8N_DB.exists():
        return out
    try:
        con = sqlite3.connect(str(N8N_DB))
        con.row_factory = sqlite3.Row
        rows = con.execute("select id, name, active from workflow_entity order by name").fetchall()
        con.close()
        out["active"] = sum(1 for row in rows if int(row["active"] or 0) == 1)
        out["inactive"] = sum(1 for row in rows if int(row["active"] or 0) == 0)
        out["billWorkflows"] = [dict(row) for row in rows if "bill" in str(row["name"]).lower() or "hermes" in str(row["name"]).lower()]
    except Exception as exc:
        out["error"] = str(exc)
    return out


def gate_mutator_audit() -> dict[str, Any]:
    scan_paths = [
        ROOT / "scripts",
        ROOT / "ops",
    ]
    suspicious: list[dict[str, str]] = []
    patterns = (
        "readyForPaper\"] = True",
        "readyForPaper'] = True",
        "recommendedStage\"] = \"paper\"",
        "recommendedStage'] = \"paper\"",
        "recommendedStage\"] = \"live\"",
        "recommendedStage'] = \"live\"",
        "currentStage\"] = \"paper\"",
        "currentStage'] = \"paper\"",
        "operator override",
        "gates flipped",
    )
    for root in scan_paths:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix not in {".py", ".sh", ".mjs", ".js", ".ts"}:
                continue
            if any(part in {".git", "node_modules"} for part in path.parts):
                continue
            try:
                text = path.read_text(errors="ignore")
            except Exception:
                continue
            lowered = text.lower()
            hits = [pattern for pattern in patterns if pattern.lower() in lowered]
            if hits and "quarantined" not in lowered:
                suspicious.append({
                    "path": str(path),
                    "patterns": ", ".join(hits[:5]),
                })
    return {
        "suspiciousCount": len(suspicious),
        "suspicious": suspicious,
        "policy": "No script may mutate prediction-review or promotion-state to widen readiness; gates must be produced by deterministic evidence commands.",
    }


def build_audit() -> dict[str, Any]:
    findings: list[Finding] = []

    disk = disk_free(Path("/"))
    if disk["freeGiB"] < 5:
        findings.append(Finding(
            "P0",
            "storage",
            "Mac SSD free space is too low for reliable research or live-state writes.",
            f"freeGiB={disk['freeGiB']} usedPct={disk['usedPct']}",
            "Pause heavy research/optimization jobs and move large archives/results to the Seagate drive before resuming sweeps.",
        ))

    data_audits = [audit_csv(path) for path in CORE_DATASETS]
    legacy_data_audits = [audit_csv(path) | {"legacyResearchOnly": True} for path in LEGACY_RESEARCH_DATASETS]
    for item in data_audits:
        if not item["exists"]:
            findings.append(Finding("P1", "data", "Core dataset is missing.", item["path"], "Rebuild or remove it from execution/backtest configs."))
            continue
        age = item.get("latestAgeHours")
        if isinstance(age, (int, float)) and age > 36:
            findings.append(Finding(
                "P1",
                "data",
                "Dataset is stale for live/demo decision support.",
                f"{item['path']} latest={item.get('latestTs')} ageHours={age}",
                "Refresh the feed before any strategy can use this timeframe for execution decisions.",
            ))
        if item.get("duplicateTimestampSymbolRows") or item.get("timeReversals"):
            findings.append(Finding(
                "P1",
                "data",
                "Dataset has ordering or duplicate-key defects.",
                f"{item['path']} duplicates={item.get('duplicateTimestampSymbolRows')} reversals={item.get('timeReversals')}",
                "Quarantine the dataset for research-only until normalized from raw source again.",
            ))
        if item.get("zeroVolumeTail"):
            findings.append(Finding(
                "P2",
                "data",
                "Dataset tail has zero volume bars, so volume and DOM-proxy features can be misleading.",
                f"{item['path']} latest={item.get('latestTs')}",
                "Do not let volume-confirmation, DOM proxy, or whale-flow filters size/confirm trades from this file.",
            ))
    stale_legacy = [
        item for item in legacy_data_audits
        if isinstance(item.get("latestAgeHours"), (int, float)) and item["latestAgeHours"] > 36
    ]
    if stale_legacy:
        findings.append(Finding(
            "P2",
            "data-archive",
            "Legacy 1m research datasets are stale and must stay out of execution configs.",
            "; ".join(f"{Path(item['path']).name} ageHours={item.get('latestAgeHours')}" for item in stale_legacy[:6]),
            "Use fresh 1m-5d/15m/30m/60m lanes for current research; keep 21d/30d files as archive-only until rebuilt from a reliable paid source.",
        ))

    collector = Path("scripts/research_collector.py").read_text(errors="ignore")
    if "metadata_only" not in collector or "paper_abstract_only" not in collector:
        findings.append(Finding(
            "P1",
            "research",
            "Raw research collector does not label weak evidence.",
            "scripts/research_collector.py missing metadata/abstract-only evidence fields",
            "Patch collector outputs with tradable_signal=false and promoted_for_execution=false.",
        ))

    strategy_feed = read_json(RESEARCH_DIR / "researcher/strategy-feed.latest.json")
    directives = strategy_feed.get("directives", [])
    if directives:
        weak_evidence_terms = ("example trade", "video", "profit in backtest", "win rate", "quote:")
        weak = [
            d for d in directives
            if any(term in " ".join(map(str, d.get("evidence", []))).lower() for term in weak_evidence_terms)
        ]
        if weak:
            findings.append(Finding(
                "P1",
                "research",
                "Strategy directives include marketing/video/backtest claims as evidence.",
                f"{len(weak)}/{len(directives)} directives contain weak evidence terms",
                "Treat these as hypothesis seeds only; require transcript/full-text extraction, local implementation, walk-forward, and OOS before promotion.",
            ))

    live_gate = read_json(STATE_DIR / "live-readiness-gate.latest.json")
    if live_gate.get("blockers"):
        findings.append(Finding(
            "P0",
            "execution-gate",
            "Live-readiness gate is blocked.",
            "; ".join(map(str, live_gate.get("blockers", []))),
            "Do not enable demo/live routing until blockers are cleared and today's Obsidian plan approves the specific order lane.",
        ))

    futures_cost_gate = read_json(STATE_DIR / "futures-cost-slippage-gate.latest.json")
    futures_cost_writes_orders = futures_cost_gate.get("writesOrders")
    futures_cost_bt_survivors = (futures_cost_gate.get("backtrader") or {}).get("survivorCount")
    futures_cost_oos_survivors = (futures_cost_gate.get("volRegimeOos") or {}).get("survivorCount")
    if not futures_cost_gate:
        findings.append(Finding(
            "P0",
            "futures-evidence",
            "Futures cost/slippage gate is missing.",
            str(STATE_DIR / "futures-cost-slippage-gate.latest.json"),
            "Run npm run bill:futures-cost-slippage-gate before treating any futures strategy as demo-shadow eligible.",
        ))
    elif futures_cost_writes_orders is not False or not futures_cost_oos_survivors:
        findings.append(Finding(
            "P0",
            "futures-evidence",
            "Futures cost/slippage gate is not deployable.",
            f"writesOrders={futures_cost_writes_orders} backtraderSurvivors={futures_cost_bt_survivors} volOosSurvivors={futures_cost_oos_survivors}",
            "Treat full-sample Backtrader survivors as hypotheses only; require cost-stressed purged OOS survivors before demo-shadow.",
        ))

    prediction_review = read_json(STATE_DIR / "prediction-review.latest.json")
    prediction_promotion = read_json(STATE_DIR / "promotion-state.json")
    clob_edge = read_json(STATE_DIR / "polymarket-clob-edge-gate.latest.json")
    resolved_join = read_json(STATE_DIR / "prediction-resolved-outcome-join.latest.json")
    resolved_subject_counts = resolved_subject_summary(resolved_join)
    prediction_ready = (
        prediction_review.get("readyForPaper") is True
        and prediction_promotion.get("recommendedStage") in {"paper", "live"}
        and clob_edge.get("readyForPaper") is True
        and clob_edge.get("writesOrders") is False
        and resolved_join.get("readyForPaper") is True
        and resolved_join.get("writesOrders") is False
    )
    if not prediction_ready:
        findings.append(Finding(
            "P1",
            "prediction-evidence",
            "Prediction-market evidence is still research-only.",
            json.dumps({
                "reviewReady": prediction_review.get("readyForPaper"),
                "promotion": prediction_promotion.get("recommendedStage"),
                "clobReady": clob_edge.get("readyForPaper"),
                "resolvedReady": resolved_join.get("readyForPaper"),
                "resolvedStatusCounts": resolved_join.get("statusCounts"),
                "resolvedSubjectSpecific": resolved_subject_counts,
            })[:700],
            "Keep prediction markets in research mode; require paper-ready review, promotion, CLOB edge, and resolved-outcome join before paper/live.",
        ))

    monitor = read_json(STATE_DIR / "topstep-100k-monitor.latest.json")
    if str(monitor.get("status", "")).upper() == "BLOCKED" or monitor.get("hardBlockers"):
        findings.append(Finding(
            "P0",
            "topstep",
            "Topstep monitor is blocked or has hard blockers.",
            json.dumps({"status": monitor.get("status"), "hardBlockers": monitor.get("hardBlockers")})[:700],
            "Keep master bridge paused; reconcile broker state before new demo orders.",
        ))

    jobs = load_jobs()
    active_heavy = []
    broad_implementers = []
    for job in jobs:
        if job.get("enabled") is not True:
            continue
        name = str(job.get("name", ""))
        prompt = str(job.get("prompt", ""))
        hay = f"{name}\n{prompt}".lower()
        if any(term in hay for term in ("full_strategy_pipeline", "parameter-sweep", "optimization sweeps", "self-evolving alpha")):
            active_heavy.append(name)
        if "implement it immediately" in hay:
            broad_implementers.append(name)
    if active_heavy:
        findings.append(Finding(
            "P1",
            "hermes-cron",
            "Heavy or broad research jobs are active while storage/live-readiness are degraded.",
            ", ".join(active_heavy),
            "Pause or constrain them until disk and evidence gates are green.",
        ))
    if broad_implementers:
        findings.append(Finding(
            "P1",
            "hermes-cron",
            "A research job can self-implement changes after browsing.",
            ", ".join(broad_implementers),
            "Change it to write candidate cards only unless Obsidian daily plan explicitly approves implementation.",
        ))

    n8n = n8n_summary()
    gate_mutators = gate_mutator_audit()
    if gate_mutators["suspiciousCount"]:
        findings.append(Finding(
            "P0",
            "governance",
            "Potential gate-mutator scripts can widen prediction/live readiness.",
            json.dumps(gate_mutators["suspicious"][:5])[:700],
            "Quarantine or delete scripts that directly flip readyForPaper/currentStage/recommendedStage outside the deterministic review path.",
        ))

    if not n8n.get("billWorkflows"):
        findings.append(Finding(
            "P2",
            "n8n",
            "n8n has no active Bill/Hermes execution workflow beyond the control plane.",
            json.dumps(n8n)[:700],
            "Keep n8n as monitoring/control-plane only unless a deterministic webhook path is explicitly designed.",
        ))

    status = "BLOCKED" if any(f.severity == "P0" for f in findings) else "NEEDS_FIXES" if findings else "OK"
    return {
        "command": "edge-discovery-audit",
        "generatedAt": now_iso(),
        "status": status,
        "researchOnly": True,
        "executionIsolation": {
            "writesOrders": False,
            "touchesBroker": False,
            "allowedOutputs": [str(OUTPUT_JSON), str(OUTPUT_MD)],
        },
        "disk": disk,
        "datasets": data_audits,
        "legacyResearchDatasets": legacy_data_audits,
        "hermesCron": {
            "path": str(HERMES_CRON),
            "enabledCount": sum(1 for job in jobs if job.get("enabled") is True),
            "pausedCount": sum(1 for job in jobs if job.get("enabled") is False),
            "heavyActive": active_heavy,
            "broadImplementers": broad_implementers,
        },
        "n8n": n8n,
        "gateMutators": gate_mutators,
        "strategyFeed": {
            "path": str(RESEARCH_DIR / "researcher/strategy-feed.latest.json"),
            "generatedAt": strategy_feed.get("generatedAt"),
            "directiveCount": len(directives),
        },
        "futuresEvidence": {
            "costSlippageGate": {
                "path": str(STATE_DIR / "futures-cost-slippage-gate.latest.json"),
                "present": bool(futures_cost_gate),
                "writesOrders": futures_cost_writes_orders,
                "backtraderSurvivors": futures_cost_bt_survivors,
                "volOosSurvivors": futures_cost_oos_survivors,
                "failureCounts": futures_cost_gate.get("failureCounts", {}),
            },
        },
        "predictionEvidence": {
            "reviewReadyForPaper": prediction_review.get("readyForPaper"),
            "promotionCurrentStage": prediction_promotion.get("currentStage"),
            "promotionRecommendedStage": prediction_promotion.get("recommendedStage"),
            "clobReadyForPaper": clob_edge.get("readyForPaper"),
            "clobWatchResearchGroups": clob_edge.get("watchResearchGroups"),
            "resolvedJoinReadyForPaper": resolved_join.get("readyForPaper"),
            "resolvedJoinStatusCounts": resolved_join.get("statusCounts", {}),
            "resolvedJoinHistoricalRows": resolved_join.get("historicalRowsLoaded"),
            "resolvedJoinMinSpecificMatches": resolved_join.get("minSpecificMatches"),
            "resolvedJoinSubjectSpecific": resolved_subject_counts,
        },
        "findings": [asdict(f) for f in findings],
    }


def write_markdown(audit: dict[str, Any]) -> None:
    lines = [
        "# Bill Edge Discovery Audit - 2026-05-29",
        "",
        f"Generated: {audit['generatedAt']}",
        f"Status: {audit['status']}",
        "",
        "## Operating Decision",
        "",
        "No new Topstep demo/live orders are approved from this audit. Research and backtests may continue only in shadow/research mode until storage, data freshness, broker reconciliation, and OOS gates are green.",
        "",
        "## Findings",
        "",
    ]
    for finding in audit["findings"]:
        lines.extend([
            f"### {finding['severity']} - {finding['area']}",
            "",
            f"- Finding: {finding['finding']}",
            f"- Evidence: {finding['evidence']}",
            f"- Required action: {finding['action']}",
            "",
        ])
    if not audit["findings"]:
        lines.append("No blockers found.")
        lines.append("")

    lines.extend([
        "## Data Freshness",
        "",
        "| Dataset | Latest | Age h | Rows | Notes |",
        "|---|---:|---:|---:|---|",
    ])
    for item in audit["datasets"]:
        notes = []
        if item.get("duplicateTimestampSymbolRows"):
            notes.append(f"dups={item['duplicateTimestampSymbolRows']}")
        if item.get("timeReversals"):
            notes.append(f"reversals={item['timeReversals']}")
        if item.get("zeroVolumeTail"):
            notes.append("zero-volume-tail")
        lines.append(f"| `{item['path']}` | {item.get('latestTs')} | {item.get('latestAgeHours')} | {item.get('rows')} | {', '.join(notes) or 'ok'} |")

    legacy_items = audit.get("legacyResearchDatasets", [])
    if legacy_items:
        lines.extend([
            "",
            "## Legacy Research Datasets",
            "",
            "These files are archive/research-only until rebuilt from a reliable source. They must not drive live/demo decisions.",
            "",
            "| Dataset | Latest | Age h | Rows | Notes |",
            "|---|---:|---:|---:|---|",
        ])
        for item in legacy_items:
            notes = ["legacy-research-only"]
            if item.get("zeroVolumeTail"):
                notes.append("zero-volume-tail")
            lines.append(f"| `{item['path']}` | {item.get('latestTs')} | {item.get('latestAgeHours')} | {item.get('rows')} | {', '.join(notes)} |")

    lines.extend([
        "",
        "## Futures Evidence Gates",
        "",
        f"- Cost/slippage gate present: {audit.get('futuresEvidence', {}).get('costSlippageGate', {}).get('present')}",
        f"- Backtrader cost-stress survivors: {audit.get('futuresEvidence', {}).get('costSlippageGate', {}).get('backtraderSurvivors')}",
        f"- Purged OOS cost-stress survivors: {audit.get('futuresEvidence', {}).get('costSlippageGate', {}).get('volOosSurvivors')}",
        f"- Failure counts: {audit.get('futuresEvidence', {}).get('costSlippageGate', {}).get('failureCounts')}",
        "",
        "## Prediction Evidence Gates",
        "",
        f"- Review ready for paper: {audit.get('predictionEvidence', {}).get('reviewReadyForPaper')}",
        f"- Promotion stage: {audit.get('predictionEvidence', {}).get('promotionCurrentStage')} / {audit.get('predictionEvidence', {}).get('promotionRecommendedStage')}",
        f"- CLOB ready for paper: {audit.get('predictionEvidence', {}).get('clobReadyForPaper')}",
        f"- Resolved-outcome join ready for paper: {audit.get('predictionEvidence', {}).get('resolvedJoinReadyForPaper')}",
        f"- Resolved-outcome status counts: {audit.get('predictionEvidence', {}).get('resolvedJoinStatusCounts')}",
        f"- Resolved historical rows: {audit.get('predictionEvidence', {}).get('resolvedJoinHistoricalRows')}",
        "",
        "## Hermes/n8n Posture",
        "",
        f"- Hermes cron enabled: {audit['hermesCron']['enabledCount']}",
        f"- Hermes cron paused: {audit['hermesCron']['pausedCount']}",
        f"- Heavy active jobs: {', '.join(audit['hermesCron']['heavyActive']) or 'none'}",
        f"- Broad self-implementing jobs: {', '.join(audit['hermesCron']['broadImplementers']) or 'none'}",
        f"- n8n active workflows: {audit['n8n'].get('active')}",
        f"- n8n Bill/Hermes workflows: {audit['n8n'].get('billWorkflows')}",
        f"- Gate mutator suspicious scripts: {audit.get('gateMutators', {}).get('suspiciousCount')}",
        "",
        "## Next Research Rule",
        "",
        "YT/paper/social items are hypothesis seeds until they have source text or transcript, explicit rules, local implementation, in-sample and out-of-sample results, costs/slippage, and a shadow-demo promotion record.",
        "",
    ])
    OUTPUT_MD.write_text("\n".join(lines))


def main() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    OBSIDIAN_HERMES.mkdir(parents=True, exist_ok=True)
    audit = build_audit()
    OUTPUT_JSON.write_text(json.dumps(audit, indent=2))
    write_markdown(audit)
    print(json.dumps({
        "status": audit["status"],
        "findings": len(audit["findings"]),
        "json": str(OUTPUT_JSON),
        "markdown": str(OUTPUT_MD),
    }, indent=2))


if __name__ == "__main__":
    main()
