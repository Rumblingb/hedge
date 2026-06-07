import json
import shlex
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "package.json"
N8N_ACTIVATION_HELPER = ROOT / "ops" / "activate-bill-workflows.sh"


OUTPUT_EXTENSIONS = {".csv", ".json", ".jsonl", ".log", ".md", ".parquet", ".txt"}
SOURCE_EXTENSIONS = {".js", ".mjs", ".py", ".sh", ".ts"}


def bill_scripts() -> dict[str, str]:
    return {
        name: command
        for name, command in json.loads(PACKAGE.read_text()).get("scripts", {}).items()
        if name.startswith("bill:")
    }


def script_tokens(command: str) -> list[str]:
    cleaned = (
        command.replace("&&", " ")
        .replace("||", " ")
        .replace(";", " ")
        .replace("(", " ")
        .replace(")", " ")
    )
    return shlex.split(cleaned)


def target_tokens(command: str) -> list[str]:
    targets: list[str] = []
    skip_next = False
    for token in script_tokens(command):
        if skip_next:
            skip_next = False
            continue
        if token in {"--output", "--markdown", "--csv", "--input", "--replay"}:
            skip_next = True
            continue
        if token.startswith("-"):
            continue
        suffix = Path(token).suffix
        if suffix in OUTPUT_EXTENSIONS:
            continue
        if suffix in SOURCE_EXTENSIONS:
            targets.append(token)
            continue
        if token.startswith("ops/mac-mini/bin/") or token.startswith("ops/mac-mini/scripts/"):
            targets.append(token)
            continue
        if token == "native/bill-core-cpp":
            targets.append(token)
    return targets


class BillPackageScriptsTest(unittest.TestCase):
    def test_bill_script_targets_exist(self):
        missing = []
        for name, command in bill_scripts().items():
            for target in target_tokens(command):
                if target in {"src/cli.ts"}:
                    continue
                if not (ROOT / target).exists():
                    missing.append((name, target))

        self.assertEqual(missing, [])

    def test_clearance_evidence_fast_script_skips_slow_tests_and_prints_progress(self):
        scripts = bill_scripts()

        self.assertEqual(
            scripts["bill:clearance-evidence"],
            ".venv/bin/python scripts/bill_clearance_evidence.py --progress",
        )
        self.assertEqual(
            scripts["bill:clearance-evidence-fast"],
            ".venv/bin/python scripts/bill_clearance_evidence.py --skip-slow-tests --progress",
        )

    def test_state_unifier_scripts_are_available(self):
        scripts = bill_scripts()

        self.assertEqual(scripts["bill:state-unifier"], ".venv/bin/python scripts/bill_state_unifier.py")
        self.assertEqual(scripts["bill:state-unifier-apply"], ".venv/bin/python scripts/bill_state_unifier.py --apply")
        self.assertEqual(scripts["bill:canonicalize-roots"], ".venv/bin/python scripts/bill_canonicalize_roots.py")
        self.assertEqual(
            scripts["bill:canonicalize-roots-apply"],
            ".venv/bin/python scripts/bill_canonicalize_roots.py --apply",
        )

    def test_free_data_feed_audit_script_is_available(self):
        scripts = bill_scripts()

        self.assertEqual(scripts["bill:free-data-feed-audit"], ".venv/bin/python scripts/free_data_feed_audit.py")
        self.assertEqual(scripts["bill:data-master-csv"], ".venv/bin/python scripts/build_data_master_csv.py")

    def test_gex_backtest_script_is_available_as_research_only_tooling(self):
        scripts = bill_scripts()

        self.assertEqual(scripts["bill:gex-backtest"], ".venv/bin/python scripts/gex_backtest.py")

    def test_strategy_diagnostic_script_is_available_as_research_only_tooling(self):
        scripts = bill_scripts()

        self.assertEqual(scripts["bill:strategy-diagnostic"], ".venv/bin/python scripts/strategy_diagnostic.py")
        self.assertEqual(
            scripts["bill:strategy-factory-one-variable-research"],
            ".venv/bin/python scripts/strategy_factory_one_variable_research.py",
        )
        self.assertEqual(
            scripts["bill:ai-scientist-data-access-audit"],
            ".venv/bin/python scripts/ai_scientist_data_access_audit.py",
        )
        self.assertEqual(
            scripts["bill:ai-scientist-hermes-research-access"],
            ".venv/bin/python scripts/ai_scientist_hermes_research_access.py",
        )
        self.assertEqual(
            scripts["bill:adaptive-strategy-research-audit"],
            ".venv/bin/python scripts/adaptive_strategy_research_audit.py",
        )
        self.assertEqual(
            scripts["bill:multitf-entry-research-audit"],
            ".venv/bin/python scripts/multitf_entry_research_audit.py",
        )
        self.assertEqual(
            scripts["bill:entry-hypothesis-research"],
            ".venv/bin/python scripts/entry_hypothesis_research.py",
        )
        self.assertEqual(
            scripts["bill:session-shadow-premarket"],
            ".venv/bin/python scripts/session_shadow_premarket.py",
        )
        self.assertEqual(
            scripts["bill:session-shadow-trade-log"],
            ".venv/bin/python scripts/session_shadow_trade_logger.py",
        )
        self.assertEqual(
            scripts["bill:session-shadow-postmarket"],
            ".venv/bin/python scripts/session_shadow_postmarket.py",
        )
        self.assertEqual(
            scripts["bill:strategy-test-framework-status"],
            ".venv/bin/python scripts/strategy_test_framework_status.py",
        )

    def test_topstep_session_safety_clearance_script_is_available(self):
        scripts = bill_scripts()

        self.assertEqual(
            scripts["bill:topstep-session-safety-clearance"],
            ".venv/bin/python scripts/topstep_session_safety_clearance.py",
        )
        self.assertEqual(
            scripts["bill:topstep-demo-observation-posture"],
            ".venv/bin/python scripts/topstep_demo_observation_posture.py",
        )
        self.assertEqual(
            scripts["bill:topstep-demo-observation"],
            ".venv/bin/python scripts/topstep_demo_observation_posture.py",
        )

    def test_founder_quant_cto_metaprompt_script_is_available(self):
        scripts = bill_scripts()

        self.assertEqual(
            scripts["bill:founder-quant-cto-metaprompt"],
            ".venv/bin/python scripts/founder_quant_cto_metaprompt.py",
        )

    def test_ws_is_direct_dependency_for_polymarket_clob_recorder(self):
        package = json.loads(PACKAGE.read_text())

        self.assertIn("ws", package.get("dependencies", {}))
        self.assertIn("scripts/polymarket_clob_recorder.mjs", target_tokens(package["scripts"]["bill:polymarket-clob-recorder"]))
        self.assertIn('from "ws"', (ROOT / "scripts/polymarket_clob_recorder.mjs").read_text())

    def test_execution_adjacent_scripts_are_firewall_or_existing_wrappers(self):
        scripts = bill_scripts()
        allowed = {
            "bill:dashboard",
            "bill:dom-edge-bridge",
            "bill:fund-os-completion-audit",
            "bill:live-readiness",
            "bill:live-readiness-gate",
            "bill:pm-futures-bridge",
            "bill:prediction-execute",
            "bill:topstep-realtime-bridge",
            "bill:verify-60m-bridge-firewall",
            "bill:verify-execution-quarantine",
            "bill:verify-master-bridge-firewall",
            "bill:verify-no-execution-processes",
            "bill:verify-prediction-funding-firewall",
            "bill:verify-signal-router-firewall",
            "bill:verify-topstep-demo-bridge-firewall",
        }
        adjacent = {
            name
            for name, command in scripts.items()
            if any(term in f"{name} {command}".lower() for term in ("execute", "fund", "live", "bridge", "route"))
        }

        self.assertTrue(adjacent)
        self.assertLessEqual(adjacent, allowed)

    def test_n8n_activation_helper_is_manual_first_and_dry_run_by_default(self):
        text = N8N_ACTIVATION_HELPER.read_text()

        self.assertIn("This script is operator-facing", text)
        self.assertIn("It does not use SSH, MCP, or the n8n API", text)
        self.assertIn("Dry run only", text)
        self.assertIn("Open $N8N_URL/workflows", text)
        self.assertIn("click the Active toggle", text)
        self.assertIn('if [[ "${1:-}" == "--apply" ]]', text)
        self.assertIn("Any workflow-local APPROVED value is not BILL_ROUTE_APPROVAL: APPROVED", text)
        self.assertIn("Refusing --apply: N8N_DB_PATH was not explicitly set", text)
        self.assertIn("BILL_N8N_WORKFLOW_ACTIVATION_APPLY_OK=I_UNDERSTAND_N8N_APPROVED_IS_NOT_TRADE_APPROVAL", text)
        self.assertIn("N8N_WORKFLOW_CHANGE_APPROVAL: APPROVED", text)
        self.assertIn("n8n update:workflow --id=", text)


if __name__ == "__main__":
    unittest.main()
