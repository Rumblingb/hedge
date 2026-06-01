import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.alpha_research_tooling_check import ROOT, module_origin_leaks, module_status


class AlphaResearchToolingCheckTests(unittest.TestCase):
    def test_module_status_fails_closed_on_import_timeout(self):
        with patch(
            "scripts.alpha_research_tooling_check.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd=["python"], timeout=15),
        ):
            status = module_status("numpy", "numpy")

        self.assertFalse(status["ok"])
        self.assertEqual(status["package"], "numpy")
        self.assertIn("TimeoutExpired", status["error"])

    def test_module_origin_leaks_blocks_sibling_env_imports(self):
        leaks = module_origin_leaks(
            [
                {
                    "package": "numpy",
                    "module": "numpy",
                    "ok": True,
                    "file": "/Users/brain/Kronos/venv/lib/python3.11/site-packages/numpy/__init__.py",
                },
                {
                    "package": "pandas",
                    "module": "pandas",
                    "ok": True,
                    "file": str(ROOT / ".venv/lib/python3.11/site-packages/pandas/__init__.py"),
                },
            ]
        )

        self.assertEqual(len(leaks), 1)
        self.assertIn("numpy", leaks[0])
        self.assertIn("Kronos", leaks[0])

    def test_module_origin_leaks_allows_repo_venv_imports(self):
        module_file = Path(ROOT / ".venv/lib/python3.11/site-packages/numpy/__init__.py")
        leaks = module_origin_leaks(
            [
                {
                    "package": "numpy",
                    "module": "numpy",
                    "ok": True,
                    "file": str(module_file),
                }
            ]
        )

        self.assertEqual(leaks, [])


if __name__ == "__main__":
    unittest.main()
