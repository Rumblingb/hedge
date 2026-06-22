import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = [
    "agentic_fund_controller.py",
    "entry_exit_mtf_test.py",
    "entry_refinement_test.py",
    "fund_shadow_digest.py",
    "gc_orb_5m_signal.py",
    "gc_orb_retest_validate.py",
    "gc_orb_validate.py",
    "mtf_shadow_run.py",
    "orb_cross_instrument_test.py",
    "orb_shadow_run.py",
    "vol_scaled_overlay.py",
]
FORBIDDEN_IMPORTS = {"requests", "urllib", "httpx", "websocket", "socket", "subprocess"}
FORBIDDEN_CALL_MARKERS = {
    "submit_order",
    "place_order",
    "create_order",
    "cancel_order",
    "deposit",
    "withdraw",
    "fund_and_trade",
}
REQUIRED_FAIL_CLOSED_MARKERS = [
    '"writesOrders": False',
    '"touchesBroker": False',
    '"movesFunds": False',
    '"readyForExecution": False',
    '"readyForDemoExpansion": False',
    '"readyForLive": False',
]


class ShadowResearchPacketSafetyTests(unittest.TestCase):
    def test_packet_is_local_only_and_emits_fail_closed_metadata(self):
        for name in SCRIPTS:
            with self.subTest(script=name):
                path = ROOT / "scripts" / name
                source = path.read_text()
                tree = ast.parse(source, filename=str(path))

                imported_roots = set()
                call_names = set()
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
                    elif isinstance(node, ast.ImportFrom) and node.module:
                        imported_roots.add(node.module.split(".", 1)[0])
                    elif isinstance(node, ast.Call):
                        if isinstance(node.func, ast.Name):
                            call_names.add(node.func.id.lower())
                        elif isinstance(node.func, ast.Attribute):
                            call_names.add(node.func.attr.lower())

                self.assertFalse(imported_roots & FORBIDDEN_IMPORTS)
                self.assertFalse(call_names & FORBIDDEN_CALL_MARKERS)
                for marker in REQUIRED_FAIL_CLOSED_MARKERS:
                    self.assertIn(marker, source)


if __name__ == "__main__":
    unittest.main()
