#!/usr/bin/env python3
"""Verify prediction-market funding helpers fail closed without moving funds."""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RETIRE_ROOT = ROOT / ".retired"


@dataclass(frozen=True)
class FundingHelper:
    active: str
    retired: str | None = None
    active_required: bool = False


HELPERS = [
    FundingHelper("scripts/deposit-clob.ts", ".retired/deposit-clob.ts"),
    FundingHelper("scripts/deposit-simple.ts", ".retired/deposit-simple.ts"),
    FundingHelper("scripts/fund-and-trade.ts", ".retired/fund-and-trade.ts"),
    FundingHelper("scripts/wire-up.ts", active_required=True),
    FundingHelper("scripts/swap-and-fund.ts", active_required=True),
]
APPROVAL_ENV = "HERMES_ALLOW_POLYMARKET_FUNDING"
APPROVAL_VALUE = "I_UNDERSTAND_THIS_MOVES_FUNDS"
PREDICTION_GATE_TESTS = [
    "tests/predictionExecutionAuthorization.test.ts",
    "tests/predictionExecution.test.ts",
    "tests/gengarExecutionWatcher.test.ts",
    "tests/pmBot.test.ts",
]
PREDICTION_GATE_SOURCE_MARKERS = {
    "src/prediction/execution/authorization.ts": [
        "prediction review has blockers",
        "prediction review is not ready for paper execution",
        "promotion state has blockers",
        "promotion state still requires approvals",
    ],
    "src/prediction/execution/liveGate.ts": [
        "BILL_PREDICTION_LIVE_EXECUTION_ENABLED must be exactly 'true'.",
        "BILL_PREDICTION_EXECUTION_MODE must be exactly 'live'.",
        "BILL_PREDICTION_LIVE_ACKNOWLEDGED must be exactly 'true'",
        "RH_MODE=paper is incompatible with live prediction execution",
    ],
}


def helper_env() -> dict[str, str]:
    env = os.environ.copy()
    for key in [
        "BILL_POLYMARKET_FUNDING_ENABLED",
        "BILL_SWAP_AND_FUND_ENABLED",
        APPROVAL_ENV,
        "POLYMARKET_PRIVATE_KEY",
        "POLYMARKET_RELAYER_API_KEY",
    ]:
        env.pop(key, None)
    return env


def assert_source_quarantined(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    required = [
        APPROVAL_ENV,
        APPROVAL_VALUE,
        "process.exit(2)",
        "BLOCKED",
    ]
    for needle in required:
        if needle not in text:
            raise AssertionError(f"{path} is missing funding firewall marker {needle!r}")
    if re.search(r"RELAYER_KEY\s*=\s*['\"][0-9a-f]{8}-", text):
        raise AssertionError(f"{path} appears to contain a hardcoded relayer API key")


def run_helper(path: str) -> dict[str, object]:
    result = subprocess.run(
        ["npx", "tsx", path],
        cwd=ROOT,
        env=helper_env(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=20,
        check=False,
    )
    combined = f"{result.stdout}\n{result.stderr}"
    if "BLOCKED" not in combined:
        raise AssertionError(f"{path} did not print BLOCKED; rc={result.returncode}; output={combined[:500]}")
    if result.returncode != 2:
        raise AssertionError(f"{path} should exit 2 when funding env is absent; got {result.returncode}")
    forbidden = [
        "Approve tx",
        "Deposit tx",
        "Submitting WALLET batch",
        "Swap confirmed",
        "Transfer confirmed",
        "Signature:",
    ]
    if any(needle in combined for needle in forbidden):
        raise AssertionError(f"{path} reached a transaction path while disabled; output={combined[:800]}")
    return {
        "script": path,
        "returncode": result.returncode,
        "blocked": True,
    }


def verify_helper(helper: FundingHelper) -> dict[str, object]:
    active_path = ROOT / helper.active
    retired_path = ROOT / helper.retired if helper.retired else None

    if active_path.exists():
        assert_source_quarantined(active_path)
        result = run_helper(helper.active)
        result["state"] = "active-fail-closed"
        return result

    if helper.active_required:
        raise AssertionError(f"{helper.active} is required in active source but is missing")

    if retired_path and retired_path.exists():
        assert_source_quarantined(retired_path)
        return {
            "script": helper.active,
            "retiredPath": helper.retired,
            "state": "retired-quarantined",
            "blocked": True,
            "notRunnableFromActiveSource": True,
        }

    return {
        "script": helper.active,
        "retiredPath": helper.retired,
        "state": "retired-absent-from-active-source",
        "blocked": True,
        "notRunnableFromActiveSource": True,
    }


def assert_prediction_gate_source_markers() -> list[dict[str, object]]:
    checked: list[dict[str, object]] = []
    for rel, markers in PREDICTION_GATE_SOURCE_MARKERS.items():
        path = ROOT / rel
        text = path.read_text(encoding="utf-8")
        missing = [marker for marker in markers if marker not in text]
        if missing:
            raise AssertionError(f"{rel} missing fail-closed marker(s): {missing}")
        checked.append({
            "script": rel,
            "state": "prediction-execution-gate-source-reviewed",
            "blocked": True,
            "markerCount": len(markers),
        })
    return checked


def run_prediction_gate_tests() -> dict[str, object]:
    env = helper_env()
    env.update({
        "BILL_PREDICTION_EXECUTION_MODE": "paper",
        "BILL_PREDICTION_LIVE_EXECUTION_ENABLED": "false",
        "RH_LIVE_EXECUTION_ENABLED": "false",
    })
    result = subprocess.run(
        ["npm", "run", "--silent", "test", "--", *PREDICTION_GATE_TESTS],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=60,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(
            "prediction execution gate tests failed; "
            f"rc={result.returncode}; stdout={result.stdout[-1000:]}; stderr={result.stderr[-1000:]}"
        )
    return {
        "state": "prediction-execution-gate-tests-pass",
        "tests": PREDICTION_GATE_TESTS,
        "returncode": result.returncode,
    }


def main() -> None:
    checked: list[dict[str, object]] = []
    for helper in HELPERS:
        checked.append(verify_helper(helper))
    checked.extend(assert_prediction_gate_source_markers())
    checked.append(run_prediction_gate_tests())
    print(json.dumps({
        "ok": True,
        "checked": checked,
        "approvalEnv": APPROVAL_ENV,
        "writesOrders": False,
        "movesFunds": False,
    }, indent=2))


if __name__ == "__main__":
    main()
