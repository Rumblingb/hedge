#!/usr/bin/env python3
"""Verify execution-adjacent files are quarantined or read-only.

This is a source/runtime safety verifier. It proves that the legacy/manual
execution-adjacent files currently visible in the dirty tree do not route
orders, move funds, or silently bypass the Bill/Hermes control plane.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
OUT = STATE / "execution-quarantine-verifier.latest.json"
OUT_MD = STATE / "execution-quarantine-verifier.latest.md"


@dataclass(frozen=True)
class Check:
    id: str
    path: str
    passed: bool
    evidence: str
    writesOrders: bool = False
    touchesBroker: bool = False
    movesFunds: bool = False
    note: str = ""


def rel_path(path: Path) -> str:
    return str(path.relative_to(ROOT))


def read_text(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8", errors="ignore")


def contains_all(text: str, needles: list[str]) -> tuple[bool, list[str]]:
    missing = [needle for needle in needles if needle not in text]
    return not missing, missing


def forbidden_present(text: str, patterns: list[str]) -> list[str]:
    hits: list[str] = []
    for pattern in patterns:
        if re.search(pattern, text, re.IGNORECASE | re.MULTILINE):
            hits.append(pattern)
    return hits


def source_check(
    *,
    check_id: str,
    relative: str,
    required: list[str],
    forbidden: list[str] | None = None,
    note: str = "",
    touches_broker: bool = False,
) -> Check:
    text = read_text(relative)
    required_ok, missing = contains_all(text, required)
    forbidden_hits = forbidden_present(text, forbidden or [])
    passed = required_ok and not forbidden_hits
    evidence = "required markers present"
    if missing:
        evidence = f"missing markers: {missing}"
    if forbidden_hits:
        evidence = f"{evidence}; forbidden patterns: {forbidden_hits}"
    return Check(
        id=check_id,
        path=relative,
        passed=passed,
        evidence=evidence,
        touchesBroker=touches_broker,
        note=note,
    )


def run_quarantined_shell() -> Check:
    relative = "ops/mac-mini/bin/bill-pm-auto-execute-loop.sh"
    proc = subprocess.run(
        ["bash", relative],
        cwd=ROOT,
        env={**os.environ, "BILL_ENABLE_AGENTIC_FUND_EXECUTION": "false"},
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
        check=False,
    )
    combined = f"{proc.stdout}\n{proc.stderr}"
    passed = proc.returncode == 42 and "quarantined" in combined.lower() and "will not run" in combined.lower()
    return Check(
        id="legacy-pm-auto-loop-quarantined",
        path=relative,
        passed=passed,
        evidence=f"returncode={proc.returncode}; output={combined.strip()[:240]}",
        note="Executed only the local quarantined stub; no secrets, broker, wallet, or order path.",
    )


def run_pm_arb_placeholder() -> Check:
    relative = "scripts/pm_arb_scanner.py"
    with tempfile.TemporaryDirectory(prefix="bill-pm-arb-quarantine-") as raw:
        temp_home = Path(raw)
        proc = subprocess.run(
            ["python3", relative],
            cwd=ROOT,
            env={**os.environ, "HOME": str(temp_home)},
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
            check=False,
        )
        state = temp_home / ".rumbling-hedge" / "state" / "pm-arb-scanner.latest.json"
        payload = json.loads(state.read_text()) if state.exists() else {}
    passed = (
        proc.returncode == 2
        and payload.get("status") == "quarantined"
        and payload.get("researchOnly") is True
        and payload.get("promotedForExecution") is False
        and payload.get("max_edge_pct") == 0.0
    )
    return Check(
        id="pm-arb-scanner-placeholder-quarantined",
        path=relative,
        passed=passed,
        evidence=(
            f"returncode={proc.returncode}; status={payload.get('status')}; "
            f"researchOnly={payload.get('researchOnly')}; promotedForExecution={payload.get('promotedForExecution')}"
        ),
        note="Ran with an isolated HOME so it could not modify live state.",
    )


def check_agentic_fund_shadow_gate() -> Check:
    return source_check(
        check_id="agentic-fund-shadow-unless-explicitly-enabled",
        relative="scripts/agentic_fund.sh",
        required=[
            "EXECUTION_ENABLED=\"${BILL_ENABLE_AGENTIC_FUND_EXECUTION:-false}\"",
            "TRADING_TIMEZONE=\"${BILL_TRADING_TIMEZONE:-Europe/London}\"",
            "execution_gate_status()",
            "SHADOW_ONLY",
            "BILL_ENABLE_AGENTIC_FUND_EXECUTION is not true; bridge skipped",
            "BILL_ENABLE_FUTURES_DEMO_EXECUTION is not true",
            "RH_TOPSTEP_READ_ONLY is not false",
            "RH_LIVE_EXECUTION_ENABLED is true",
            "daily plan explicitly says no new Bill/Hermes orders approved",
            "daily plan lacks BILL_ROUTE_APPROVAL: APPROVED",
            "daily plan lacks BROKER_RECONCILIATION: GREEN",
            "execution gate blocked; bridge skipped",
            "python3 scripts/master_bridge.py",
        ],
        note="This script may generate research signals, but the bridge branch is behind default-false env plus daily-plan/broker-readiness gates.",
    )


def check_start_gengar_gate() -> Check:
    return source_check(
        check_id="gengar-launcher-dry-run-by-default",
        relative="ops/start-gengar-live.sh",
        required=[
            "BILL_GENGAR_LIVE_EXECUTION_ENABLED:-false",
            "watcher will run in DRY_RUN mode",
            "POLYMARKET_PRIVATE_KEY:?",
            "npx tsx src/prediction/gengarExecutionWatcher.ts",
        ],
        note="Private key is required only inside the explicit live-enabled branch.",
    )


def check_launchd_realtime_locked() -> Check:
    return source_check(
        check_id="realtime-launchd-template-keeps-execution-env-locked",
        relative="ops/mac-mini/launchd/com.agentpay.bill.realtime-bridge.plist.template",
        required=[
            "<key>BILL_ENABLE_FUTURES_DEMO_EXECUTION</key>",
            "<string>false</string>",
            "<key>RH_TOPSTEP_READ_ONLY</key>",
            "<string>true</string>",
            "<key>RH_LIVE_EXECUTION_ENABLED</key>",
        ],
        note="Template only launches realtime quote refresh with execution env explicitly locked.",
    )


def check_strategy_runner_reboot_fail_closed() -> Check:
    template = read_text("ops/mac-mini/launchd/com.agentpay.bill.strategy-engine-runner.plist.template")
    wrapper = read_text("ops/mac-mini/bin/bill-strategy-engine-runner")
    required_template, missing_template = contains_all(template, [
        "<key>BILL_ENABLE_FUTURES_DEMO_EXECUTION</key>",
        "<string>false</string>",
        "<key>RH_TOPSTEP_READ_ONLY</key>",
        "<string>true</string>",
        "<key>RH_LIVE_EXECUTION_ENABLED</key>",
        "<key>RunAtLoad</key>",
        "<key>KeepAlive</key>",
    ])
    required_wrapper, missing_wrapper = contains_all(wrapper, [
        "load_bill_env",
        "export BILL_ENABLE_FUTURES_DEMO_EXECUTION=false",
        "export RH_TOPSTEP_READ_ONLY=true",
        "export RH_LIVE_EXECUTION_ENABLED=false",
        "exec \"$(bill_tsx)\" src/engine/strategyEngineRunner.ts",
    ])
    env_load_pos = wrapper.find("load_bill_env")
    futures_lock_pos = wrapper.find("export BILL_ENABLE_FUTURES_DEMO_EXECUTION=false")
    readonly_lock_pos = wrapper.find("export RH_TOPSTEP_READ_ONLY=true")
    live_lock_pos = wrapper.find("export RH_LIVE_EXECUTION_ENABLED=false")
    exec_pos = wrapper.find('exec "$(bill_tsx)" src/engine/strategyEngineRunner.ts')
    ordering_ok = (
        env_load_pos != -1
        and futures_lock_pos != -1
        and readonly_lock_pos != -1
        and live_lock_pos != -1
        and exec_pos != -1
        and env_load_pos < futures_lock_pos < readonly_lock_pos < live_lock_pos < exec_pos
    )
    return Check(
        id="strategy-runner-reboot-fail-closed",
        path="ops/mac-mini/bin/bill-strategy-engine-runner",
        passed=required_template and required_wrapper and ordering_ok,
        evidence=(
            f"missingTemplate={missing_template}; missingWrapper={missing_wrapper}; "
            f"locksAfterEnvBeforeExec={ordering_ok}"
        ),
        note=(
            "RunAtLoad/KeepAlive can restart after power loss; both launchd and wrapper "
            "must force demo/live execution locked after bill.env is loaded."
        ),
    )


def check_command_center_reboot_fail_closed() -> Check:
    template = read_text("ops/mac-mini/launchd/com.agentpay.bill.command-center.plist.template")
    wrapper = read_text("ops/mac-mini/bin/bill-command-center")
    installer = read_text("ops/mac-mini/bin/bill-install-launchd")
    required_template, missing_template = contains_all(template, [
        "<key>BILL_ENABLE_FUTURES_DEMO_EXECUTION</key>",
        "<string>false</string>",
        "<key>RH_TOPSTEP_READ_ONLY</key>",
        "<string>true</string>",
        "<key>RH_LIVE_EXECUTION_ENABLED</key>",
        "<key>RunAtLoad</key>",
        "<key>KeepAlive</key>",
        "command-center-stdout.log",
        "command-center-stderr.log",
    ])
    required_wrapper, missing_wrapper = contains_all(wrapper, [
        "load_bill_env",
        "export BILL_ENABLE_FUTURES_DEMO_EXECUTION=false",
        "export RH_TOPSTEP_READ_ONLY=true",
        "export RH_LIVE_EXECUTION_ENABLED=false",
        "exec python3 command_center_server.py",
    ])
    installer_ok = "com.agentpay.bill.command-center" in installer
    env_load_pos = wrapper.find("load_bill_env")
    futures_lock_pos = wrapper.find("export BILL_ENABLE_FUTURES_DEMO_EXECUTION=false")
    readonly_lock_pos = wrapper.find("export RH_TOPSTEP_READ_ONLY=true")
    live_lock_pos = wrapper.find("export RH_LIVE_EXECUTION_ENABLED=false")
    exec_pos = wrapper.find("exec python3 command_center_server.py")
    ordering_ok = (
        env_load_pos != -1
        and futures_lock_pos != -1
        and readonly_lock_pos != -1
        and live_lock_pos != -1
        and exec_pos != -1
        and env_load_pos < futures_lock_pos < readonly_lock_pos < live_lock_pos < exec_pos
    )
    return Check(
        id="command-center-reboot-fail-closed",
        path="ops/mac-mini/bin/bill-command-center",
        passed=required_template and required_wrapper and installer_ok and ordering_ok,
        evidence=(
            f"missingTemplate={missing_template}; missingWrapper={missing_wrapper}; "
            f"installerIncludesCommandCenter={installer_ok}; locksAfterEnvBeforeExec={ordering_ok}"
        ),
        note=(
            "Command Center is observability only, but restart/power-loss recovery must still "
            "force execution locks before serving live state to agents or the founder UI."
        ),
    )


def check_position_sizing_is_output_only() -> Check:
    return source_check(
        check_id="position-sizing-output-only",
        relative="scripts/position_sizing_engine.py",
        required=[
            "OUTPUT_NAME = \"position-sizing-engine.latest.json\"",
            "recommended_contracts",
            "_write_output",
            "MAX_CONTRACTS_MNQ",
        ],
        forbidden=[
            r"api\.topstepx\.com",
            r"\.submit\(",
            r"/api/Order/(place|submit|modify|cancel)",
            r"POLYMARKET_PRIVATE_KEY",
        ],
        note="Sizing writes a recommendation artifact only; it must not become a route.",
    )


def check_cron_position_sizing_wrapper() -> Check:
    return source_check(
        check_id="cron-position-sizing-wrapper-output-only",
        relative="scripts/cron_position_sizing.sh",
        required=[
            "scripts/position_sizing_engine.py",
            "BILL_POSITION_SIZING_BALANCE",
        ],
        forbidden=[
            r"master_bridge\.py",
            r"topstep_demo_bridge\.py",
            r"fund-and-trade",
            r"deposit",
        ],
    )


def check_pre_trade_is_advisory() -> Check:
    return source_check(
        check_id="pre-trade-check-advisory-output-only",
        relative="scripts/pre_trade_check.py",
        required=[
            "DECISION_PATH = STATE_DIR / \"pre_trade_decision.json\"",
            "BILL_PRE_TRADE_MAX_CONTRACTS",
            "BILL_FUTURES_DEMO_MAX_CONTRACTS",
            "with open(DECISION_PATH, \"w\")",
        ],
        forbidden=[
            r"api\.topstepx\.com",
            r"topstep_demo_bridge\.py",
            r"master_bridge\.py",
            r"\.submit\(",
            r"/api/Order/(place|submit|modify|cancel)",
        ],
        note="The string TRADE here is a decision artifact, not an order route.",
    )


def check_realtime_bridge_data_only() -> Check:
    return source_check(
        check_id="realtime-data-bridge-data-only",
        relative="scripts/realtime_data_bridge.py",
        required=[
            "Writes quote state for futures research and execution gates.",
            "execution_grade",
            "write_state",
            "quote_block_reason",
        ],
        forbidden=[
            r"api\.topstepx\.com/api/Order",
            r"topstep_demo_bridge\.py",
            r"master_bridge\.py",
            r"\.submit\(",
            r"POLYMARKET_PRIVATE_KEY",
        ],
        note="This may connect to quote/data vendors; it should never place orders.",
    )


def check_trade_journal_read_only_broker() -> Check:
    return source_check(
        check_id="trade-journal-read-only-broker-observer",
        relative="scripts/trade_journal.py",
        required=[
            "/api/Auth/loginKey",
            "/api/Order/search",
            "/api/Position/searchOpen",
            "--dry-run",
            "JOURNAL_PATH",
        ],
        forbidden=[
            r"/api/Order/(place|submit|modify|cancel)",
            r"/api/Position/close",
            r"submitOrder",
            r"placeOrder",
            r"cancelOrder",
        ],
        touches_broker=True,
        note="This is broker read-only telemetry. It remains outside routing approval and should be dry-run first after edits.",
    )


def check_demo_execution_blockers_before_submit() -> Check:
    text = read_text("src/live/demoExecution.ts")
    required = [
        "BILL_ENABLE_FUTURES_DEMO_EXECUTION is not true.",
        "RH_LIVE_EXECUTION_ENABLED is not true.",
        "RH_TOPSTEP_READ_ONLY is still true.",
        "daily plan lacks BILL_ROUTE_APPROVAL: APPROVED",
        "daily plan lacks BROKER_RECONCILIATION: GREEN",
        "Topstep monitor warnings require reconciliation",
        "live-readiness gate does not allow demo expansion",
        "synthetic demo fallback signal is shadow-only and cannot be routed",
        "adapter.submit(signal)",
    ]
    required_ok, missing = contains_all(text, required)
    blocker_pos = text.find("if (routingBlockers.length > 0)")
    submit_pos = text.find("adapter.submit(signal)")
    ordering_ok = blocker_pos != -1 and submit_pos != -1 and blocker_pos < submit_pos
    classification_pos = text.find("executionClassificationBlocker")
    classification_ok = classification_pos != -1 and classification_pos < submit_pos
    passed = required_ok and ordering_ok and classification_ok
    evidence = f"missing={missing}; blockersBeforeSubmit={ordering_ok}; classificationBeforeSubmit={classification_ok}"
    return Check(
        id="futures-demo-execution-blockers-before-submit",
        path="src/live/demoExecution.ts",
        passed=passed,
        evidence=evidence,
        note="This file contains a submit path, but the verifier checks the lock order and keeps execution disabled.",
    )


def check_projectx_adapter_demo_only_guards() -> Check:
    text = read_text("src/adapters/projectx/projectxAdapter.ts")
    required = [
        "assertDemoOnlyAccountLock(this.config);",
        "ProjectX live adapter is in read-only mode. Keep RH_TOPSTEP_READ_ONLY=true until the demo shadow loop is approved.",
        "assertDemoOnlyAccountIsSimulated(this.config, account);",
        "await this.cancelOrdersByTagPrefix(token, account.id, contract.id, `bt`);",
        "path: \"/api/Order/place\",",
        "action: \"market entry order with protective brackets\"",
        "stopLossBracket:",
        "type: ORDER_TYPE.stop",
        "takeProfitBracket:",
        "type: ORDER_TYPE.limit",
        "path: \"/api/Position/closeContract\",",
    ]
    required_ok, missing = contains_all(text, required)

    submit_start = text.find("public async submit")
    readonly_pos = text.find("if (this.config.readOnly)", submit_start)
    simulated_pos = text.find("assertDemoOnlyAccountIsSimulated(this.config, account);", submit_start)
    cleanup_pos = text.find("await this.cancelOrdersByTagPrefix(token, account.id, contract.id, `bt`);", submit_start)
    place_pos = text.find('path: "/api/Order/place"', submit_start)
    submit_ordering_ok = (
        submit_start != -1
        and readonly_pos != -1
        and simulated_pos != -1
        and cleanup_pos != -1
        and place_pos != -1
        and readonly_pos < simulated_pos < cleanup_pos < place_pos
    )

    flatten_start = text.find("public async flattenAll")
    flatten_readonly_pos = text.find("if (this.config.readOnly)", flatten_start)
    close_pos = text.find('path: "/api/Position/closeContract"', flatten_start)
    flatten_ordering_ok = (
        flatten_start != -1
        and flatten_readonly_pos != -1
        and close_pos != -1
        and flatten_readonly_pos < close_pos
    )

    passed = required_ok and submit_ordering_ok and flatten_ordering_ok
    return Check(
        id="projectx-adapter-demo-only-guards-before-broker-write",
        path="src/adapters/projectx/projectxAdapter.ts",
        passed=passed,
        evidence=(
            f"missing={missing}; submitGuardsBeforePlace={submit_ordering_ok}; "
            f"flattenReadOnlyBeforeClose={flatten_ordering_ok}"
        ),
        note="This file has broker-write methods, so it stays quarantined; the check proves demo-only/read-only/account guards and OCO construction remain visible before writes.",
    )


def check_topstep_compliance_policy_only() -> Check:
    return source_check(
        check_id="topstep-compliance-policy-only",
        relative="src/risk/topstepCompliance.ts",
        required=[
            "TopstepComplianceTracker",
            "TOPSTEP_50K",
            "recordTrade",
            "endOfDay",
            "canTrade",
            "maxAdditionalProfitToday",
        ],
        forbidden=[
            r"api\.topstepx\.com",
            r"/api/Order/(place|submit|modify|cancel)",
            r"/api/Position/close",
            r"fetch\(",
            r"\.submit\(",
            r"POLYMARKET_PRIVATE_KEY",
        ],
        note="Topstep compliance is policy/math only. It must not call broker, submit orders, or change route state.",
    )


def check_gengar_watcher_live_gate() -> Check:
    watcher_text = read_text("src/prediction/gengarExecutionWatcher.ts")
    live_gate_text = read_text("src/prediction/execution/liveGate.ts")
    required_watcher = [
        "evaluateGengarLiveExecutionGate",
        "BILL_GENGAR_LIVE_EXECUTION_ENABLED must be exactly 'true'.",
        "dryRun: !liveMode",
        "Live intent refused",
        "websocket trade-side signal lacks on-chain/quote-reaction confirmation",
    ]
    required_live_gate = [
        "BILL_PREDICTION_EXECUTION_MODE must be exactly 'live'.",
        "BILL_PREDICTION_LIVE_EXECUTION_ENABLED must be exactly 'true'.",
    ]
    required_watcher_ok, missing_watcher = contains_all(watcher_text, required_watcher)
    required_live_gate_ok, missing_live_gate = contains_all(live_gate_text, required_live_gate)
    gate_pos = watcher_text.find("if (liveGate.liveIntent && !liveGate.ok)")
    executor_pos = watcher_text.find("new PolymarketExecutor")
    ordering_ok = gate_pos != -1 and executor_pos != -1 and gate_pos < executor_pos
    missing = missing_watcher + [f"liveGate:{item}" for item in missing_live_gate]
    passed = required_watcher_ok and required_live_gate_ok and ordering_ok
    return Check(
        id="gengar-watcher-live-gate-before-executor",
        path="src/prediction/gengarExecutionWatcher.ts",
        passed=passed,
        evidence=f"missing={missing}; gateBeforeExecutor={ordering_ok}",
        note="Prediction live execution requires explicit live env plus liveGate; default mode is dry-run.",
    )


def check_fund_os_audit_read_only() -> Check:
    return source_check(
        check_id="fund-os-completion-audit-read-only",
        relative="scripts/bill_fund_os_completion_audit.py",
        required=[
            "This is not a trading gate.",
            "Check",
            "read_json",
        ],
        forbidden=[
            r"api\.topstepx\.com/api/Order",
            r"POLYMARKET_PRIVATE_KEY",
            r"subprocess\.run\(",
            r"urllib\.request",
            r"\.submit\(",
        ],
        note="Completion audit should inspect artifacts only.",
    )


CHECKS: list[Callable[[], Check]] = [
    run_quarantined_shell,
    run_pm_arb_placeholder,
    check_agentic_fund_shadow_gate,
    check_start_gengar_gate,
    check_launchd_realtime_locked,
    check_strategy_runner_reboot_fail_closed,
    check_command_center_reboot_fail_closed,
    check_position_sizing_is_output_only,
    check_cron_position_sizing_wrapper,
    check_pre_trade_is_advisory,
    check_realtime_bridge_data_only,
    check_trade_journal_read_only_broker,
    check_demo_execution_blockers_before_submit,
    check_projectx_adapter_demo_only_guards,
    check_topstep_compliance_policy_only,
    check_gengar_watcher_live_gate,
    check_fund_os_audit_read_only,
]


def build_report() -> dict[str, object]:
    checks = [fn() for fn in CHECKS]
    failed = [check for check in checks if not check.passed]
    return {
        "command": "verify-execution-quarantine",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "movesFunds": False,
        "readyForExecution": False,
        "readyForDemoExpansion": False,
        "readyForLive": False,
        "status": "PASS" if not failed else "BLOCKED",
        "allChecksPassed": not failed,
        "failedCheckIds": [check.id for check in failed],
        "checkedPaths": [check.path for check in checks],
        "readOnlyBrokerObserverPaths": [check.path for check in checks if check.touchesBroker],
        "checks": [asdict(check) for check in checks],
        "hardRules": [
            "This verifier does not approve any order route.",
            "Files with submit paths remain blocked unless daily plan, broker reconciliation, source hygiene, realtime data, and promotion gates pass.",
            "Broker observer scripts may read fills/positions only; they are not execution paths.",
        ],
    }


def render_markdown(report: dict[str, object]) -> str:
    lines = [
        "# Execution Quarantine Verifier",
        "",
        f"Generated: `{report['generatedAt']}`",
        f"Status: `{report['status']}`",
        f"Ready for execution: `{report['readyForExecution']}`",
        "",
        "## Checks",
        "",
        "| Check | Path | Result | Evidence |",
        "|---|---|---:|---|",
    ]
    for item in report["checks"]:  # type: ignore[index]
        result = "PASS" if item["passed"] else "FAIL"
        evidence = str(item["evidence"]).replace("|", "/")
        lines.append(f"| `{item['id']}` | `{item['path']}` | `{result}` | {evidence} |")
    lines.extend(["", "## Hard Rules", ""])
    for rule in report["hardRules"]:  # type: ignore[index]
        lines.append(f"- {rule}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    report = build_report()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    OUT_MD.write_text(render_markdown(report))
    print(json.dumps({
        "status": report["status"],
        "allChecksPassed": report["allChecksPassed"],
        "failedCheckIds": report["failedCheckIds"],
        "json": str(OUT),
        "markdown": str(OUT_MD),
    }, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
