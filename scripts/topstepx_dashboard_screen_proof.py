#!/usr/bin/env python3
"""Capture a read-only TopstepX dashboard screenshot for reconciliation proof.

This is a visual audit helper, not a market-data feed and not an execution
tool. It does not click, type, route orders, read browser cookies, or touch
broker APIs. Put the TopstepX dashboard on screen, run the script, and use the
result as supporting evidence when reconciling broker-flat/account UI state.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
PROOF_DIR = STATE / "screen-proofs"
OUT = STATE / "topstepx-dashboard-screen-proof.latest.json"


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def run_capture(path: Path, timeout: int) -> tuple[bool, str | None]:
    screencapture = shutil.which("screencapture")
    if not screencapture:
        return False, "macOS screencapture binary not found"
    try:
        subprocess.run(
            [screencapture, "-x", str(path)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=timeout,
            text=True,
        )
        return True, None
    except subprocess.CalledProcessError as exc:
        return False, (exc.stderr or str(exc)).strip()
    except Exception as exc:
        return False, str(exc)


def run_ocr(path: Path, timeout: int) -> tuple[str | None, str | None]:
    tesseract = shutil.which("tesseract")
    if not tesseract:
        return None, "tesseract not installed; screenshot captured without OCR"
    try:
        result = subprocess.run(
            [tesseract, str(path), "stdout"],
            check=True,
            capture_output=True,
            timeout=timeout,
            text=True,
        )
        text = result.stdout.strip()
        return text, None
    except subprocess.CalledProcessError as exc:
        return None, (exc.stderr or str(exc)).strip()
    except Exception as exc:
        return None, str(exc)


def summarize_text(text: str | None) -> dict[str, Any]:
    lower = (text or "").lower()
    return {
        "containsTopstep": "topstep" in lower or "projectx" in lower or "project x" in lower,
        "mentionsFlat": "flat" in lower,
        "mentionsPosition": "position" in lower or "positions" in lower,
        "mentionsPnL": "p&l" in lower or "pnl" in lower or "profit" in lower,
        "textSample": (text or "")[:1000],
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    ts = now_utc()
    PROOF_DIR.mkdir(parents=True, exist_ok=True)
    screenshot = PROOF_DIR / f"topstepx-dashboard-{ts.strftime('%Y%m%dT%H%M%SZ')}.png"
    captured, capture_error = run_capture(screenshot, args.timeout_sec)
    ocr_text = None
    ocr_error = None
    if captured and args.ocr:
        ocr_text, ocr_error = run_ocr(screenshot, args.timeout_sec)

    return {
        "command": "topstepx-dashboard-screen-proof",
        "generatedAt": ts.isoformat(),
        "status": "CAPTURED" if captured else "ERROR",
        "researchOnly": True,
        "screenOnly": True,
        "writesOrders": False,
        "placesOrders": False,
        "modifiesOrders": False,
        "cancelsOrders": False,
        "touchesBroker": False,
        "readsCookies": False,
        "clicksOrTypes": False,
        "readyForExecution": False,
        "screenshotPath": str(screenshot) if captured else None,
        "captureError": capture_error,
        "ocrEnabled": bool(args.ocr),
        "ocrAvailable": ocr_text is not None,
        "ocrError": ocr_error,
        "ocrSummary": summarize_text(ocr_text),
        "operatorRead": (
            "Use this as supporting visual reconciliation only. The authoritative data path is "
            "TopstepX/ProjectX API read-only evidence plus broker/daily plan reconciliation."
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout-sec", type=int, default=10)
    parser.add_argument("--ocr", action="store_true", help="Run tesseract OCR if installed.")
    return parser.parse_args()


def main() -> int:
    payload = build_report(parse_args())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload.get("status") == "CAPTURED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
