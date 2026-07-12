#!/usr/bin/env python3
"""Guard against stale strategy docs being read as execution approval.

This is a read-only source-hygiene check. It scans high-signal Bill/Hermes
research notes for old "trade now" style claims and requires those claims to
be locally superseded by current research-only/gated language.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
VAULT = Path.home() / "Documents" / "memorybrain"
DEFAULT_OUTPUT = STATE / "stale-strategy-claim-guard.latest.json"

DEFAULT_SCAN_PATHS = [
    ROOT / "docs" / "STRATEGY_AUDIT.md",
    VAULT / "Research-Catalog",
    VAULT / "Agent-Hermes",
]

RISK_PATTERNS = [
    re.compile(r"\bpaper\s+trade\s+immediately\b", re.IGNORECASE),
    re.compile(r"\bcan\s+trade\s+today\b", re.IGNORECASE),
    re.compile(r"\btrade\s+immediately\b", re.IGNORECASE),
    re.compile(r"\bready\s+for\s+(?:demo|live|execution|paper)\b", re.IGNORECASE),
    re.compile(r"\bexecution[- ]?ready\b", re.IGNORECASE),
]

SAFE_PATTERNS = [
    re.compile(r"\bsuperseded\b", re.IGNORECASE),
    re.compile(r"\bresearch[- ]only\b", re.IGNORECASE),
    re.compile(r"\bnot\s+(?:execution|trading|paper|demo|live)\s+(?:evidence|approval|permission|ready)\b", re.IGNORECASE),
    re.compile(r"\bmust\s+not\s+be\s+read\b", re.IGNORECASE),
    re.compile(r"\bblocked\b", re.IGNORECASE),
    re.compile(r"\bno\s+new\s+bill/hermes\s+orders\s+approved\b", re.IGNORECASE),
    re.compile(r"\bready\s+for\s+execution/demo/live:\s*`?false`?\b", re.IGNORECASE),
    re.compile(r"\bready\s+for\s+(?:execution|execution data|paper|paper/live/demo|demo|demo expansion|live):\s*`?false`?\b", re.IGNORECASE),
    re.compile(r"\breadyFor(?:Execution|Paper|DemoExpansion|Live)`?,?\s*`?false`?\b", re.IGNORECASE),
    re.compile(r"\bnot\s+ready\s+for\s+(?:paper|demo|live|execution)\b", re.IGNORECASE),
    re.compile(r"\bskipped\b", re.IGNORECASE),
    re.compile(r"\bnot\s+complete\b", re.IGNORECASE),
    re.compile(r"\bcurrent\s+authority\s+lives\b", re.IGNORECASE),
    re.compile(r"\bgates?\s+(?:remain\s+)?(?:blocked|pass)\b", re.IGNORECASE),
]

SKIP_DIRS = {
    ".git",
    ".venv",
    "node_modules",
    "dist",
    "__pycache__",
    ".pytest_cache",
}
GENERATED_REPORT_PREFIXES = (
    "stale-strategy-claim-guard-",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def current_utc_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def default_markdown_path() -> Path:
    return VAULT / "Agent-Hermes" / f"stale-strategy-claim-guard-{current_utc_date()}.md"


DEFAULT_MARKDOWN = default_markdown_path()


def is_generated_report(path: Path) -> bool:
    return path.suffix.lower() in {".md", ".markdown"} and any(
        path.name.startswith(prefix) for prefix in GENERATED_REPORT_PREFIXES
    )


def iter_markdown_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_file() and path.suffix.lower() in {".md", ".markdown"}:
            if is_generated_report(path):
                continue
            files.append(path)
        elif path.is_dir():
            for child in path.rglob("*"):
                if not child.is_file() or child.suffix.lower() not in {".md", ".markdown"}:
                    continue
                if any(part in SKIP_DIRS for part in child.parts):
                    continue
                if is_generated_report(child):
                    continue
                files.append(child)
    return sorted(set(files))


def has_safe_context(lines: list[str], index: int, window: int = 4) -> bool:
    start = max(0, index - window)
    end = min(len(lines), index + window + 1)
    context = "\n".join(lines[start:end])
    return any(pattern.search(context) for pattern in SAFE_PATTERNS)


def scan_file(path: Path) -> list[dict[str, Any]]:
    try:
        text = path.read_text(errors="ignore")
    except Exception as exc:
        return [{
            "path": str(path),
            "line": None,
            "phrase": "read-error",
            "lineText": str(exc),
            "safeContext": False,
        }]
    findings: list[dict[str, Any]] = []
    lines = text.splitlines()
    for index, line in enumerate(lines):
        for pattern in RISK_PATTERNS:
            match = pattern.search(line)
            if not match:
                continue
            safe = has_safe_context(lines, index)
            if safe:
                continue
            findings.append({
                "path": str(path),
                "line": index + 1,
                "phrase": match.group(0),
                "lineText": line.strip()[:500],
                "safeContext": False,
            })
    return findings


def build_report(scan_paths: list[Path]) -> dict[str, Any]:
    files = iter_markdown_files(scan_paths)
    findings: list[dict[str, Any]] = []
    for path in files:
        findings.extend(scan_file(path))
    return {
        "command": "stale-strategy-claim-guard",
        "generatedAt": now_iso(),
        "decision": "stale-claim-guard-pass" if not findings else "stale-claim-guard-blocked",
        "status": "PASS" if not findings else "BLOCKED",
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "readyForExecution": False,
        "scanPathCount": len(scan_paths),
        "fileCount": len(files),
        "findingCount": len(findings),
        "findings": findings,
        "operatorRead": (
            "No unsuperseded trade-now claims found in scanned Bill/Hermes notes."
            if not findings
            else "Patch or quarantine each finding so future agents cannot treat stale research labels as execution approval."
        ),
        "hardRules": [
            "Old GOOD/gold/source labels are hypotheses, not route approval.",
            "A risky phrase is allowed only when nearby text says superseded, research-only, blocked, or not approval.",
            "This guard never approves paper, demo, live, funding, broker access, or orders.",
        ],
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Stale Strategy Claim Guard",
        "",
        f"Generated: `{report['generatedAt']}`",
        f"Decision: `{report['decision']}`",
        f"Status: `{report['status']}`",
        f"Findings: `{report['findingCount']}`",
        "",
        "Research-only. This note does not approve orders, paper trading, demo routing, funding, or live execution.",
        "",
        "## Operator Read",
        "",
        report["operatorRead"],
        "",
    ]
    if report["findings"]:
        lines.extend(["## Findings", ""])
        for item in report["findings"]:
            lines.append(f"- `{item['path']}:{item.get('line')}` `{item['phrase']}` — {item['lineText']}")
        lines.append("")
    lines.extend(["## Hard Rules", ""])
    for rule in report["hardRules"]:
        lines.append(f"- {rule}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))
    parser.add_argument("paths", nargs="*")
    args = parser.parse_args()

    scan_paths = [Path(path).expanduser() for path in args.paths] if args.paths else DEFAULT_SCAN_PATHS
    report = build_report(scan_paths)

    output = Path(args.output)
    markdown = Path(args.markdown)
    output.parent.mkdir(parents=True, exist_ok=True)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    markdown.write_text(render_markdown(report))
    print(json.dumps({
        "status": report["status"],
        "decision": report["decision"],
        "findingCount": report["findingCount"],
        "json": str(output),
        "markdown": str(markdown),
    }, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
