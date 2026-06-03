#!/usr/bin/env python3
"""Fail clearance if execution-capable Bill processes are running unsafe."""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]

TARGET_MARKERS = [
    "strategyEngineRunner",
    "master_bridge.py",
    "topstep_demo_bridge.py",
    "60m_exec_bridge.py",
    "agentpay-labs-bridge",
    "gengarExecution",
    "start-gengar-live.sh",
    "bill-pm-auto-execute-loop.sh",
    "prediction-execute",
    "pm-bot --live",
]

UNSAFE_MARKERS = [
    "BILL_ENABLE_FUTURES_DEMO_EXECUTION=true",
    "RH_TOPSTEP_READ_ONLY=false",
    "RH_LIVE_EXECUTION_ENABLED=true",
    "BILL_POLYMARKET_FUNDING_ENABLED=true",
    "BILL_SWAP_AND_FUND_ENABLED=true",
    "HERMES_ALLOW_POLYMARKET_FUNDING=I_UNDERSTAND_THIS_MOVES_FUNDS",
    " --live",
]

SAFE_MARKERS = [
    "BILL_ENABLE_FUTURES_DEMO_EXECUTION=false",
    "RH_TOPSTEP_READ_ONLY=true",
    "RH_LIVE_EXECUTION_ENABLED=false",
]

SENSITIVE_ASSIGNMENT = re.compile(
    r"(?P<key>[A-Za-z_][A-Za-z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|PASS|AUTH|CREDENTIAL)[A-Za-z0-9_]*)=(?P<value>\S+)",
    re.IGNORECASE,
)
SENSITIVE_VALUE = re.compile(
    r"\b(?:sk-[A-Za-z0-9_-]{12,}|sk-ant-[A-Za-z0-9_-]{12,}|nvapi-[A-Za-z0-9_-]{12,}|pk_[A-Za-z0-9_-]{12,})\b"
)


@dataclass(frozen=True)
class ProcessRow:
    pid: int
    command: str


def candidate_reason(command: str) -> str | None:
    for marker in TARGET_MARKERS:
        if marker in command:
            return marker
    return None


def unsafe_reasons(command: str) -> list[str]:
    return [marker for marker in UNSAFE_MARKERS if marker in command]


def safe_evidence(command: str) -> list[str]:
    return [marker for marker in SAFE_MARKERS if marker in command]


def redact_command(command: str) -> str:
    """Redact unrelated secrets while preserving safety env markers."""
    safe_values = {
        "BILL_ENABLE_FUTURES_DEMO_EXECUTION=false",
        "BILL_ENABLE_FUTURES_DEMO_EXECUTION=true",
        "RH_TOPSTEP_READ_ONLY=false",
        "RH_TOPSTEP_READ_ONLY=true",
        "RH_LIVE_EXECUTION_ENABLED=false",
        "RH_LIVE_EXECUTION_ENABLED=true",
        "BILL_POLYMARKET_FUNDING_ENABLED=true",
        "BILL_SWAP_AND_FUND_ENABLED=true",
    }

    def replace_assignment(match: re.Match[str]) -> str:
        token = match.group(0)
        if token in safe_values:
            return token
        return f"{match.group('key')}=<redacted>"

    redacted = SENSITIVE_ASSIGNMENT.sub(replace_assignment, command)
    return SENSITIVE_VALUE.sub("<redacted-secret>", redacted)


def classify(rows: Iterable[ProcessRow]) -> dict[str, object]:
    candidates: list[dict[str, object]] = []
    unsafe: list[dict[str, object]] = []
    for row in rows:
        reason = candidate_reason(row.command)
        if not reason:
            continue
        if "verify_no_execution_enabled_processes.py" in row.command:
            continue
        item = {
            "pid": row.pid,
            "matched": reason,
            "unsafeReasons": unsafe_reasons(row.command),
            "safeEvidence": safe_evidence(row.command),
            "commandTail": redact_command(row.command)[-700:],
        }
        candidates.append(item)
        if item["unsafeReasons"]:
            unsafe.append(item)
    return {
        "ok": not unsafe,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "movesFunds": False,
        "candidateCount": len(candidates),
        "unsafeCount": len(unsafe),
        "candidates": candidates,
        "unsafe": unsafe,
    }


def process_pids() -> list[int]:
    proc = subprocess.run(
        ["ps", "-axo", "pid=,command="],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    pids: list[int] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        pid_text, _, command = line.partition(" ")
        try:
            pid = int(pid_text)
        except ValueError:
            continue
        if candidate_reason(command):
            pids.append(pid)
    return pids


def process_rows() -> list[ProcessRow]:
    rows: list[ProcessRow] = []
    for pid in process_pids():
        if pid == os.getpid():
            continue
        proc = subprocess.run(
            ["ps", "eww", "-p", str(pid), "-o", "command="],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        command = proc.stdout.strip()
        if command:
            rows.append(ProcessRow(pid=pid, command=command))
    return rows


def main() -> int:
    report = classify(process_rows())
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
