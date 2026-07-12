#!/usr/bin/env python3
"""Bill/Hermes alpha research tooling verifier.

This is a research-only environment check. It records whether the Mac has the
local tooling needed for futures and prediction-market alpha research. It does
not touch broker APIs, credentials, orders, fills, or promotion state.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
DEFAULT_OUTPUT = STATE / "alpha-research-tooling-check.latest.json"

REQUIRED_COMMANDS = [
    "node",
    "npm",
    "python3",
    "rg",
    "jq",
    "yt-dlp",
    "ffmpeg",
    "cargo",
    "rustc",
]

OPTIONAL_COMMANDS = [
    "duckdb",
    "ollama",
]

REQUIRED_MODULES = [
    ("backtrader", "backtrader"),
    ("duckdb", "duckdb"),
    ("polars", "polars"),
    ("pyarrow", "pyarrow"),
    ("pandas", "pandas"),
    ("numpy", "numpy"),
    ("scipy", "scipy"),
    ("scikit-learn", "sklearn"),
    ("statsmodels", "statsmodels"),
    ("matplotlib", "matplotlib"),
    ("seaborn", "seaborn"),
    ("ta", "ta"),
    ("yfinance", "yfinance"),
    ("youtube-transcript-api", "youtube_transcript_api"),
    ("pypdf", "pypdf"),
    ("databento", "databento"),
    ("polygon-api-client", "polygon"),
    ("websocket-client", "websocket"),
]

REQUIRED_PATHS = [
    "requirements.bill-alpha.txt",
    "config/external_alpha_catalog.yaml",
    "scripts/backtrader_research_loop.py",
    "scripts/databento_realtime_smoke.py",
    "scripts/hermes_storage_audit.py",
    "scripts/bill_clearance_evidence.py",
    "scripts/cftc_tff_positioning_ingest.py",
    "scripts/futures_cost_slippage_gate.py",
    "scripts/prediction_resolved_outcome_join.py",
    "scripts/kalshi_fillability_snapshot.py",
    "scripts/prediction_category_drilldown.py",
    "scripts/polymarket_clob_recorder.mjs",
]

DATA_PATHS = [
    "data/free/ALL-6MARKETS-15m-60d-normalized.csv",
    "data/free/ALL-6MARKETS-30m-60d-normalized.csv",
    "data/free/ALL-6MARKETS-60m-60d-normalized.csv",
]


def command_status(command: str) -> dict[str, Any]:
    path = shutil.which(command)
    return {
        "command": command,
        "ok": bool(path),
        "path": path,
    }


def module_status(package: str, module_name: str) -> dict[str, Any]:
    code = """
import importlib
import json
import sys

package = sys.argv[1]
module_name = sys.argv[2]
try:
    module = importlib.import_module(module_name)
    version = getattr(module, "__version__", "")
    if callable(version):
        try:
            version = version()
        except Exception:
            version = ""
    payload = {
        "package": package,
        "module": module_name,
        "ok": True,
        "version": str(version),
        "file": str(getattr(module, "__file__", "") or ""),
    }
except Exception as exc:
    payload = {"package": package, "module": module_name, "ok": False, "error": f"{type(exc).__name__}: {exc}"}
print(json.dumps(payload, sort_keys=True))
"""
    try:
        env = os.environ.copy()
        env.setdefault("PYTHONUNBUFFERED", "1")
        proc = subprocess.run(
            [sys.executable, "-c", code, package, module_name],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=15,
            env=env,
        )
        if proc.returncode != 0:
            return {
                "package": package,
                "module": module_name,
                "ok": False,
                "error": (proc.stderr or proc.stdout or f"returncode={proc.returncode}").strip(),
            }
        return json.loads(proc.stdout)
    except subprocess.TimeoutExpired:
        return {
            "package": package,
            "module": module_name,
            "ok": False,
            "error": "TimeoutExpired: module import exceeded 15s",
        }
    except Exception as exc:
        return {
            "package": package,
            "module": module_name,
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
        }


def path_status(rel_path: str) -> dict[str, Any]:
    path = ROOT / rel_path
    return {
        "path": str(path),
        "relativePath": rel_path,
        "ok": path.exists(),
        "sizeBytes": path.stat().st_size if path.exists() and path.is_file() else None,
    }


def run_pip_check() -> dict[str, Any]:
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pip", "check"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=45,
        )
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
        }
    except Exception as exc:
        return {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
        }


def module_origin_leaks(modules: list[dict[str, Any]]) -> list[str]:
    """Return successful imports that came from outside this repo venv/root.

    This catches accidental dependency bridges such as .pth files pointing at
    sibling research environments. Standard-library/built-in modules usually
    have no file and are ignored; Bill's required third-party stack should have
    concrete files under the repo venv.
    """
    allowed_roots = [
        (ROOT / ".venv").resolve(),
        ROOT.resolve(),
    ]
    leaks: list[str] = []
    for item in modules:
        if not item.get("ok"):
            continue
        raw_file = str(item.get("file", "") or "")
        if not raw_file:
            continue
        try:
            module_file = Path(raw_file).resolve()
        except OSError:
            leaks.append(f"{item['package']} ({raw_file})")
            continue
        if not any(module_file == root or root in module_file.parents for root in allowed_roots):
            leaks.append(f"{item['package']} ({module_file})")
    return leaks


def build_report() -> dict[str, Any]:
    required_commands = [command_status(command) for command in REQUIRED_COMMANDS]
    optional_commands = [command_status(command) for command in OPTIONAL_COMMANDS]
    modules = [module_status(package, module) for package, module in REQUIRED_MODULES]
    required_paths = [path_status(path) for path in REQUIRED_PATHS]
    data_paths = [path_status(path) for path in DATA_PATHS]
    pip_check = run_pip_check()

    blockers: list[str] = []
    warnings: list[str] = []
    missing_commands = [item["command"] for item in required_commands if not item["ok"]]
    missing_modules = [
        item["package"]
        for item in modules
        if not item["ok"] and str(item.get("error", "")).startswith("ModuleNotFoundError")
    ]
    failed_modules = [
        f"{item['package']} ({item.get('error', 'unknown error')})"
        for item in modules
        if not item["ok"] and not str(item.get("error", "")).startswith("ModuleNotFoundError")
    ]
    missing_paths = [item["relativePath"] for item in required_paths if not item["ok"]]
    missing_data = [item["relativePath"] for item in data_paths if not item["ok"]]
    missing_optional = [item["command"] for item in optional_commands if not item["ok"]]
    external_module_origins = module_origin_leaks(modules)

    if missing_commands:
        blockers.append(f"missing required commands: {', '.join(missing_commands)}")
    if missing_modules:
        blockers.append(f"missing required Python modules: {', '.join(missing_modules)}")
    if failed_modules:
        blockers.append(f"required Python modules failed import: {', '.join(failed_modules)}")
    if missing_paths:
        blockers.append(f"missing alpha research files: {', '.join(missing_paths)}")
    if external_module_origins:
        blockers.append(f"Python modules imported outside repo venv: {', '.join(external_module_origins)}")
    if not pip_check.get("ok"):
        blockers.append("pip check failed")
    if missing_data:
        warnings.append(f"missing research data paths: {', '.join(missing_data)}")
    if missing_optional:
        warnings.append(f"missing optional commands: {', '.join(missing_optional)}")

    return {
        "command": "alpha-research-tooling-check",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "status": "PASS" if not blockers else "BLOCKED",
        "readyForResearchLoop": not blockers,
        "readyForExecution": False,
        "blockers": blockers,
        "warnings": warnings,
        "python": {
            "executable": sys.executable,
            "version": sys.version,
        },
        "commands": {
            "required": required_commands,
            "optional": optional_commands,
        },
        "pythonModules": modules,
        "pipCheck": pip_check,
        "paths": {
            "required": required_paths,
            "data": data_paths,
        },
        "hardRules": [
            "This check only verifies research tooling; it cannot approve trades.",
            "Missing optional tools may slow research but must not be bypassed by routing live/demo orders.",
            "Execution remains gated by Obsidian daily plan, broker state, live-readiness, OOS, and firewall checks.",
        ],
    }


def main() -> int:
    payload = build_report()
    DEFAULT_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
