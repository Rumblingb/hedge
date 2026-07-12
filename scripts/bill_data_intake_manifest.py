#!/usr/bin/env python3
"""Create a read-only manifest for Bill/Hermes dirty market data files."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
VAULT = Path.home() / "Documents" / "memorybrain"
HERMES = VAULT / "Agent-Hermes"
OUT = STATE / "bill-data-intake-manifest.latest.json"


def default_markdown_path() -> Path:
    plan_date = datetime.now(timezone.utc).date().isoformat()
    return HERMES / f"bill-data-intake-manifest-{plan_date}.md"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_ts(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def first_header(headers: list[str], candidates: tuple[str, ...]) -> str | None:
    by_lower = {header.lower(): header for header in headers}
    for candidate in candidates:
        found = by_lower.get(candidate.lower())
        if found:
            return found
    return None


def git_status_text() -> str:
    proc = subprocess.run(
        ["git", "status", "--short", "--untracked-files=all"],
        cwd=ROOT,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return proc.stdout if proc.returncode == 0 else ""


def parse_git_status(text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in text.splitlines():
        if len(line) < 4:
            continue
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        if path.startswith("data/"):
            rows.append({"status": line[:2].strip() or "modified", "path": path})
    return rows


def classify_path(path: Path) -> str:
    text = str(path).lower()
    name = path.name.lower()
    if not path.exists():
        return "missing"
    if name.endswith(".txt") or name.endswith(".md"):
        return "external-storage-pointer"
    if path.suffix.lower() == ".csv" and "1m-5d" in name:
        return "research-refresh-current-window"
    if path.suffix.lower() == ".csv":
        return "research-dataset"
    if path.suffix.lower() == ".parquet":
        return "research-feature-store"
    return "data-reference"


def inspect_csv(path: Path, max_rows_for_symbols: int = 2_000_000) -> dict[str, Any]:
    rows = 0
    malformed_ts = 0
    symbols: set[str] = set()
    symbol_counts: Counter[str] = Counter()
    ts_by_symbol: dict[str, list[datetime]] = defaultdict(list)
    headers: list[str] = []
    timestamp_column: str | None = None
    symbol_column: str | None = None
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        headers = list(reader.fieldnames or [])
        timestamp_column = first_header(headers, ("ts", "timestamp", "datetime", "date", "time"))
        symbol_column = first_header(headers, ("symbol", "ticker", "instrument"))
        for row in reader:
            rows += 1
            symbol = str(row.get(symbol_column or "") or "").strip()
            if symbol:
                symbols.add(symbol)
                symbol_counts[symbol] += 1
            if rows <= max_rows_for_symbols:
                raw_ts = str(row.get(timestamp_column or "") or "").strip()
                ts = parse_ts(raw_ts) if raw_ts else None
                if ts:
                    ts_by_symbol[symbol or "UNKNOWN"].append(ts)
                elif timestamp_column and raw_ts:
                    malformed_ts += 1
    all_ts = [ts for values in ts_by_symbol.values() for ts in values]
    symbol_rows = {
        symbol: symbol_counts[symbol]
        for symbol in sorted(symbol_counts)
        if symbol != "UNKNOWN"
    }
    return {
        "headers": headers,
        "timestampColumn": timestamp_column,
        "symbolColumn": symbol_column,
        "rows": rows,
        "symbols": sorted(symbols),
        "symbolRows": symbol_rows,
        "startTs": min(all_ts).isoformat().replace("+00:00", "Z") if all_ts else None,
        "endTs": max(all_ts).isoformat().replace("+00:00", "Z") if all_ts else None,
        "malformedTsRows": malformed_ts,
    }


def inspect_file(row: dict[str, str]) -> dict[str, Any]:
    rel = row["path"]
    path = ROOT / rel
    exists = path.exists()
    stat = path.stat() if exists else None
    classification = classify_path(path)
    item: dict[str, Any] = {
        "path": str(path),
        "relativePath": rel,
        "gitStatus": row.get("status", ""),
        "exists": exists,
        "classification": classification,
        "bytes": stat.st_size if stat else None,
        "modifiedAt": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat() if stat else None,
        "researchOnly": True,
        "executionGrade": False,
        "usableForRouting": False,
    }
    if exists and path.suffix.lower() == ".csv":
        item.update(inspect_csv(path))
    elif exists:
        try:
            item["preview"] = path.read_text(errors="ignore")[:500]
        except Exception:
            item["preview"] = ""
    item["risk"] = risk_for_item(item)
    return item


def risk_for_item(item: dict[str, Any]) -> str:
    if item.get("classification") == "missing":
        return "quarantine-missing"
    if item.get("classification") == "external-storage-pointer":
        return "pointer-only-verify-target-before-use"
    if item.get("classification") == "research-refresh-current-window":
        return "research-only-current-window-not-execution-grade"
    if item.get("malformedTsRows"):
        return "quarantine-malformed-timestamps"
    return "research-only"


def build_manifest(rows: list[dict[str, str]], generated_at: str | None = None) -> dict[str, Any]:
    items = [inspect_file(row) for row in rows]
    counts = Counter(str(item.get("classification")) for item in items)
    risks = Counter(str(item.get("risk")) for item in items)
    csv_items = [item for item in items if Path(str(item.get("path", ""))).suffix.lower() == ".csv"]
    next_commands = [
        "npm run --silent bill:data-intake-manifest",
        "npm run --silent bill:data-freshness-gate || true",
        "npm run --silent bill:futures-data-requirements",
        "npm run --silent bill:futures-broker-parity-plan",
        "npm run --silent bill:open-session-data-proof -- --run-data-only",
        "npm run --silent bill:goal-completion-audit",
        "npm run --silent bill:obsidian-sync",
    ]
    return {
        "command": "bill-data-intake-manifest",
        "generatedAt": generated_at or now_iso(),
        "decision": "data-intake-visible-execution-locked",
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "readyForExecution": False,
        "readyForDemoExpansion": False,
        "readyForLive": False,
        "readyForExecutionData": False,
        "executionGradeData": False,
        "dirtyDataFileCount": len(items),
        "csvFileCount": len(csv_items),
        "classificationCounts": dict(sorted(counts.items())),
        "riskCounts": dict(sorted(risks.items())),
        "items": items,
        "nextCommands": next_commands,
        "validationCommandSets": {
            "dataVisibilityRefresh": [
                "npm run --silent bill:data-intake-manifest",
                "npm run --silent bill:obsidian-sync",
            ],
            "futuresDataEvidence": [
                "npm run --silent bill:data-freshness-gate || true",
                "npm run --silent bill:futures-data-requirements",
                "npm run --silent bill:futures-broker-parity-plan",
                "npm run --silent bill:open-session-data-proof -- --run-data-only",
            ],
            "operatorRead": "These commands are evidence for data review only. Research CSVs remain non-execution-grade until realtime and broker/current parity gates pass.",
        },
        "hardRules": [
            "Dirty data files are research inputs only until source, timestamp range, and freshness are independently verified.",
            "Research CSV freshness does not satisfy execution-grade realtime data requirements.",
            "Do not route futures demo/live trades from these files.",
            "Do not move/delete data files from this manifest without operator approval.",
        ],
    }


def render_markdown(payload: dict[str, Any]) -> str:
    manifest_date = str(payload.get("generatedAt") or now_iso())[:10]
    lines = [
        f"# Bill Data Intake Manifest - {manifest_date}",
        "",
        "Parent hub: [[BILL-CONTROL-HUB]]",
        "",
        "Read-only dirty data map. These files are research inputs, not execution-grade routing data.",
        "",
        "## Decision",
        "",
        f"- Decision: `{payload.get('decision')}`",
        f"- Dirty data files: `{payload.get('dirtyDataFileCount')}`",
        f"- CSV files: `{payload.get('csvFileCount')}`",
        f"- Execution-grade data: `{payload.get('executionGradeData')}`",
        f"- Ready for execution data: `{payload.get('readyForExecutionData')}`",
        "",
        "## Counts",
        "",
        f"- Classifications: `{payload.get('classificationCounts')}`",
        f"- Risks: `{payload.get('riskCounts')}`",
        "",
        "## Files",
        "",
    ]
    for item in payload.get("items") or []:
        lines.append(f"### `{item.get('relativePath')}`")
        lines.append("")
        lines.append(f"- Status: `{item.get('gitStatus')}`")
        lines.append(f"- Classification: `{item.get('classification')}`")
        lines.append(f"- Risk: `{item.get('risk')}`")
        lines.append(f"- Rows: `{item.get('rows', 'n/a')}`")
        lines.append(f"- Range: `{item.get('startTs', 'n/a')}` to `{item.get('endTs', 'n/a')}`")
        lines.append(f"- Symbols: `{item.get('symbols', [])}`")
        lines.append("")
    if payload.get("nextCommands"):
        lines.extend(["## Next Commands", ""])
        for command in payload.get("nextCommands") or []:
            lines.append(f"- `{command}`")
        lines.append("")
    validation = payload.get("validationCommandSets") if isinstance(payload.get("validationCommandSets"), dict) else {}
    if validation:
        lines.extend(["## Validation Command Sets", ""])
        lines.append("These are data-review commands only. They do not clear realtime/broker parity or approve routing.")
        lines.append("")
        for key, commands in validation.items():
            if isinstance(commands, list):
                lines.append(f"### `{key}`")
                for command in commands:
                    lines.append(f"- `{command}`")
                lines.append("")
        if validation.get("operatorRead"):
            lines.append(f"- Operator read: {validation.get('operatorRead')}")
            lines.append("")
    lines.extend(["## Hard Rules", ""])
    for rule in payload.get("hardRules") or []:
        lines.append(f"- {rule}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Bill/Hermes read-only data intake manifest.")
    parser.add_argument("--output", default=str(OUT))
    parser.add_argument("--markdown", default=None)
    args = parser.parse_args()

    payload = build_manifest(parse_git_status(git_status_text()))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    markdown = Path(args.markdown) if args.markdown else default_markdown_path()
    markdown.parent.mkdir(parents=True, exist_ok=True)
    markdown.write_text(render_markdown(payload))
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
