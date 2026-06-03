#!/usr/bin/env python3
"""Classify Bill signal artifacts by authority.

The goal is to prevent research candidates, advisory shadow signals, and
execution gates from being blended into one vote. This script is intentionally
read-only over state files and writes a diagnostic artifact only.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path("/Users/brain/hedge")
STATE = ROOT / ".rumbling-hedge/state"
LEGACY_STATE = Path.home() / ".rumbling-hedge/state"
OUT = STATE / "signal-source-truth-audit.latest.json"
MAX_ADVISORY_SOURCE_AGE_SECONDS = 2 * 3600


SOURCE_RULES = {
    "pead-signal.latest.json": {
        "role": "fundamental-research-overlay",
        "authority": "never-route-unless-promoted",
        "reason": "PEAD is a slow post-earnings drift hypothesis and cannot approve/cancel intraday Topstep trades without explicit promotion.",
    },
    "sr-proximity-signal.latest.json": {
        "role": "technical-research-overlay",
        "authority": "never-route-unless-promoted",
        "reason": "Support/resistance proximity is advisory context unless promoted with execution-grade evidence.",
    },
    "insider-signal.latest.json": {
        "role": "fundamental-research-overlay",
        "authority": "never-route-unless-promoted",
        "reason": "Insider flow is slow fundamental context and cannot approve/cancel intraday Topstep trades without explicit promotion.",
    },
    "alpha-lab.latest.json": {
        "role": "research-candidates",
        "authority": "never-route",
        "reason": "Alpha-lab emits candidate features/backtests, not executable signals.",
    },
    "60m-signals-latest.json": {
        "role": "advisory-shadow-signal",
        "authority": "never-route-unless-promoted",
        "reason": "60m signal bundle is research/advisory unless promotedForExecution and tradableSignal are explicitly true.",
    },
    "60m-signal.latest.json": {
        "role": "legacy-summary-signal",
        "authority": "never-route",
        "reason": "Legacy one-line signal summary lacks evidence and promotion metadata.",
    },
    "arbitration.latest.json": {
        "role": "pre-trade-consensus-gate",
        "authority": "block-or-reduce-only",
        "reason": "Arbitration may block or reduce risk, but cannot approve execution by itself.",
    },
    "master-signal.latest.json": {
        "role": "execution-candidate",
        "authority": "requires-daily-plan-and-firewalls",
        "reason": "Master signal is only usable after route approval, data freshness, broker parity, and firewalls pass.",
    },
}


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text())
    except Exception as exc:
        return {"_read_error": str(exc)}
    return payload if isinstance(payload, dict) else {"_payload_type": type(payload).__name__}


def parse_timestamp(payload: dict[str, Any]) -> datetime | None:
    raw = (
        payload.get("timestamp")
        or payload.get("ts")
        or payload.get("generatedAt")
        or payload.get("generated_at")
    )
    if not raw:
        return None
    text = str(raw)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def age_seconds(dt: datetime | None, now: datetime) -> int | None:
    if dt is None:
        return None
    return max(0, int((now - dt.astimezone(timezone.utc)).total_seconds()))


def source_summary(path: Path, now: datetime) -> dict[str, Any]:
    payload = read_json(path)
    present = path.exists()
    mtime_dt = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc) if present else None
    payload_dt = parse_timestamp(payload)
    return {
        "path": str(path),
        "present": present,
        "timestamp": payload_dt.isoformat() if payload_dt else None,
        "mtime": mtime_dt.isoformat() if mtime_dt else None,
        "payloadAgeSeconds": age_seconds(payload_dt, now),
        "fileAgeSeconds": age_seconds(mtime_dt, now),
        "keys": sorted(payload.keys())[:24],
        "payload": payload,
    }


def promoted(payload: dict[str, Any]) -> bool:
    return (
        payload.get("promotedForExecution") is True
        or payload.get("promoted_for_execution") is True
        or payload.get("tradableSignal") is True
        or payload.get("tradable_signal") is True
        or payload.get("readyForExecution") is True
        or payload.get("ready_for_execution") is True
    )


def classify(filename: str, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    path = STATE / filename
    canonical = source_summary(path, now)
    legacy = source_summary(LEGACY_STATE / filename, now)
    payload = canonical["payload"] if canonical["present"] else legacy["payload"]
    rule = SOURCE_RULES[filename]
    promoted_flag = promoted(payload)
    issue = None
    source_issues: list[str] = []
    warnings: list[str] = []
    if rule["authority"] == "never-route" and promoted_flag:
        issue = "research-or-advisory-source-promoted"
    if rule["authority"] == "never-route-unless-promoted" and promoted_flag and not (
        payload.get("promoted_for_execution") is True
        and payload.get("tradable_signal") is True
    ):
        issue = "partial-or-ambiguous-execution-promotion"
    if filename == "alpha-lab.latest.json" and (STATE / "60m-signals-latest.json").exists():
        issue = issue or "coexists-with-60m-signal-source; keep research and advisory lanes separate"
    if legacy["present"] and not canonical["present"]:
        source_issues.append("legacy-only-source-visible-to-fallback-readers")
    if canonical["present"] and legacy["present"] and (
        canonical["timestamp"] != legacy["timestamp"] or canonical["keys"] != legacy["keys"]
    ):
        source_issues.append("canonical-legacy-state-divergence")
    for label, summary in (("canonical", canonical), ("legacy", legacy)):
        source_age = summary["payloadAgeSeconds"]
        if source_age is None:
            source_age = summary["fileAgeSeconds"]
        if summary["present"] and isinstance(source_age, int) and source_age > MAX_ADVISORY_SOURCE_AGE_SECONDS:
            warnings.append(f"{label}-source-stale")
    return {
        "file": filename,
        "path": str(path),
        "present": canonical["present"] or legacy["present"],
        "canonicalPresent": canonical["present"],
        "legacyPresent": legacy["present"],
        "role": rule["role"],
        "authority": rule["authority"],
        "reason": rule["reason"],
        "promotedLikeExecution": promoted_flag,
        "issue": issue or (source_issues[0] if source_issues else None),
        "sourceIssues": source_issues,
        "warnings": warnings,
        "canonical": {key: value for key, value in canonical.items() if key != "payload"},
        "legacy": {key: value for key, value in legacy.items() if key != "payload"},
        "keys": sorted(payload.keys())[:24],
    }


def main() -> None:
    rows = [classify(filename) for filename in SOURCE_RULES]
    issues = [row for row in rows if row["issue"]]
    result = {
        "command": "signal-source-truth-audit",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "decision": "source-truth-visible-execution-locked",
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "movesFunds": False,
        "readyForExecution": False,
        "readyForDemoExpansion": False,
        "issueCount": len(issues),
        "issues": issues,
        "sources": rows,
        "hardRules": [
            "alpha-lab is research candidate evidence only.",
            "PEAD, insider, and S/R overlays are context only unless promoted_for_execution=true and tradable_signal=true.",
            "60m signal bundles are advisory unless explicitly promoted and still gated.",
            "arbitration can block/reduce; it cannot approve trades.",
            "master signal still requires daily plan, broker/data gates, and firewalls.",
        ],
    }
    OUT.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
