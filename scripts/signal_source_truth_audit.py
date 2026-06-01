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
OUT = STATE / "signal-source-truth-audit.latest.json"


SOURCE_RULES = {
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


def promoted(payload: dict[str, Any]) -> bool:
    return (
        payload.get("promotedForExecution") is True
        or payload.get("promoted_for_execution") is True
        or payload.get("tradableSignal") is True
        or payload.get("tradable_signal") is True
        or payload.get("readyForExecution") is True
        or payload.get("ready_for_execution") is True
    )


def classify(filename: str) -> dict[str, Any]:
    path = STATE / filename
    payload = read_json(path)
    rule = SOURCE_RULES[filename]
    promoted_flag = promoted(payload)
    issue = None
    if rule["authority"].startswith("never") and promoted_flag:
        issue = "research-or-advisory-source-promoted"
    if filename == "alpha-lab.latest.json" and (STATE / "60m-signals-latest.json").exists():
        issue = issue or "coexists-with-60m-signal-source; keep research and advisory lanes separate"
    return {
        "file": filename,
        "path": str(path),
        "present": path.exists(),
        "role": rule["role"],
        "authority": rule["authority"],
        "reason": rule["reason"],
        "promotedLikeExecution": promoted_flag,
        "issue": issue,
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
            "60m signal bundles are advisory unless explicitly promoted and still gated.",
            "arbitration can block/reduce; it cannot approve trades.",
            "master signal still requires daily plan, broker/data gates, and firewalls.",
        ],
    }
    OUT.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
