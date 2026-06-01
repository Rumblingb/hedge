#!/usr/bin/env python3
"""Verify prediction-market funding helpers fail closed without moving funds."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HELPERS = [
    "scripts/deposit-clob.ts",
    "scripts/deposit-simple.ts",
    "scripts/fund-and-trade.ts",
    "scripts/wire-up.ts",
    "scripts/swap-and-fund.ts",
]
APPROVAL_ENV = "HERMES_ALLOW_POLYMARKET_FUNDING"
APPROVAL_VALUE = "I_UNDERSTAND_THIS_MOVES_FUNDS"


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


def main() -> None:
    checked: list[dict[str, object]] = []
    for relative in HELPERS:
        path = ROOT / relative
        assert_source_quarantined(path)
        checked.append(run_helper(relative))
    print(json.dumps({
        "ok": True,
        "checked": checked,
        "approvalEnv": APPROVAL_ENV,
        "writesOrders": False,
        "movesFunds": False,
    }, indent=2))


if __name__ == "__main__":
    main()
