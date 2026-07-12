#!/usr/bin/env python3
"""Run research-only prediction scans over category-narrow snapshots.

This consumes the manifest written by prediction_category_drilldown.py and
invokes the existing deterministic prediction scanner once per category. Each
category writes to a research journal, not the main runtime opportunities file.
It never executes, writes fills, approves paper/live, or changes route flags.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
DEFAULT_MANIFEST = ROOT / ".rumbling-hedge" / "research" / "prediction-narrow-snapshots" / "manifest.latest.json"
DEFAULT_OUT_DIR = ROOT / ".rumbling-hedge" / "research" / "prediction-narrow-scans"
DEFAULT_OUTPUT = STATE / "prediction-narrow-scan-runner.latest.json"


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def safe_category(value: Any) -> str:
    text = str(value or "").strip().lower()
    return "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in text).strip("-") or "unknown"


def category_filter(args: argparse.Namespace) -> set[str]:
    values = getattr(args, "category", None) or []
    return {safe_category(value) for value in values if safe_category(value)}


def build_scan_command(snapshot_path: Path) -> list[str]:
    return ["npx", "tsx", "src/cli.ts", "prediction-scan", str(snapshot_path)]


def run_scan(item: dict[str, Any], out_dir: Path, timeout_seconds: int) -> dict[str, Any]:
    category = safe_category(item.get("category"))
    snapshot_path = Path(str(item.get("path") or ""))
    snapshot_market_count = item.get("marketCount", "missing")
    journal_path = out_dir / f"{category}.opportunities.jsonl"
    report_path = out_dir / f"{category}.report.json"
    if not snapshot_path.exists():
        return {
            "category": category,
            "snapshotPath": str(snapshot_path),
            "snapshotMarketCount": snapshot_market_count,
            "status": "missing-snapshot",
            "researchOnly": True,
            "writesOrders": False,
            "journalPath": str(journal_path),
            "reportPath": str(report_path),
            "counts": {},
            "diagnostics": {},
            "top10": [],
        }

    env = os.environ.copy()
    env["BILL_PREDICTION_JOURNAL_PATH"] = str(journal_path)
    env.setdefault("BILL_PREDICTION_EXECUTION_MODE", "paper")
    env.setdefault("BILL_PREDICTION_LIVE_EXECUTION_ENABLED", "false")

    completed = subprocess.run(
        build_scan_command(snapshot_path),
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
        check=False,
    )
    if completed.returncode != 0:
        report = {
            "category": category,
            "snapshotPath": str(snapshot_path),
            "snapshotMarketCount": snapshot_market_count,
            "status": "scan-failed",
            "researchOnly": True,
            "writesOrders": False,
            "journalPath": str(journal_path),
            "reportPath": str(report_path),
            "error": completed.stderr.strip()[-2000:],
            "counts": {},
            "diagnostics": {},
            "top10": [],
        }
    else:
        payload = json.loads(completed.stdout)
        report = {
            "category": category,
            "snapshotPath": str(snapshot_path),
            "snapshotMarketCount": snapshot_market_count,
            "status": "ok",
            "researchOnly": True,
            "writesOrders": False,
            "journalPath": str(journal_path),
            "reportPath": str(report_path),
            "counts": payload.get("counts") or {},
            "reasons": payload.get("reasons") or {},
            "venuePairs": payload.get("venuePairs") or {},
            "diagnostics": payload.get("diagnostics") or {},
            "top10": payload.get("top10") or [],
        }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def summarize_reports(reports: list[dict[str, Any]]) -> dict[str, Any]:
    paper = sum(int((report.get("counts") or {}).get("paper-trade") or 0) for report in reports)
    watch = sum(int((report.get("counts") or {}).get("watch") or 0) for report in reports)
    viable_pairs = sum(int((report.get("diagnostics") or {}).get("viablePairs") or 0) for report in reports)
    repairable_near_misses = sum(len((report.get("diagnostics") or {}).get("repairableNearMisses") or []) for report in reports)
    return {
        "categoryCount": len(reports),
        "paperCandidates": paper,
        "watchCandidates": watch,
        "viablePairs": viable_pairs,
        "repairableNearMisses": repairable_near_misses,
        "readyForPaper": False,
        "promotionRule": "Research-only. Paper remains blocked until prediction review and promotion gates agree.",
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    manifest = read_json(Path(args.manifest), [])
    if not isinstance(manifest, list):
        manifest = []
    selected_category_filter = category_filter(args)
    selected = [
        item for item in manifest
        if isinstance(item, dict)
        and item.get("researchOnly") is True
        and item.get("writesOrders") is False
        and (not selected_category_filter or safe_category(item.get("category")) in selected_category_filter)
    ][: int(args.limit)]
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    reports = [run_scan(item, out_dir, int(args.timeout_seconds)) for item in selected]
    summary = summarize_reports(reports)
    return {
        "command": "prediction-narrow-scan-runner",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "researchOnly": True,
        "writesOrders": False,
        "readyForPaper": False,
        "manifestPath": str(Path(args.manifest).resolve()),
        "outDir": str(out_dir.resolve()),
        "selectedCategories": sorted(selected_category_filter),
        "summary": summary,
        "reports": reports,
        "hardRules": [
            "This runner scans only category-narrow research snapshots.",
            "When --category is set, only that named category is scanned so one-variable retests stay isolated.",
            "It writes category research journals, not the main runtime opportunities journal.",
            "It cannot approve paper/live execution or change route flags.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run research-only prediction scans over category-narrow snapshots.")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--limit", type=int, default=6)
    parser.add_argument("--timeout-seconds", type=int, default=90)
    parser.add_argument("--category", action="append", default=[], help="Limit the run to one category. May be repeated.")
    args = parser.parse_args()
    report = build_report(args)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
