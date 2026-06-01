#!/usr/bin/env python3
"""
Build a local Bill/Hermes research and runtime corpus map.

The output is deliberately lightweight: it inventories the important local
roots, classifies artifacts, and flags risk terms so agents can navigate the
system without treating every note or cron output as tradable evidence.
"""

from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path


HOME = Path.home()
ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / ".rumbling-hedge" / "state"
REPORT_DIR = ROOT / "docs" / "research"
CATALOG_DIR = HOME / "Documents" / "memorybrain" / "Research-Catalog"
OBSIDIAN_MARKDOWN = CATALOG_DIR / "Bill-Corpus-Audit.md"

SKIP_DIRS = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "dist",
    "target",
    "Library",
    ".cache",
}

ROOTS = [
    ("repo_docs", ROOT / "docs"),
    ("repo_scripts", ROOT / "scripts"),
    ("repo_src", ROOT / "src"),
    ("repo_state", ROOT / ".rumbling-hedge" / "state"),
    ("repo_research", ROOT / ".rumbling-hedge" / "research"),
    ("obsidian_hermes", HOME / "Documents" / "memorybrain" / "Agent-Hermes"),
    ("obsidian_shared", HOME / "Documents" / "memorybrain" / "Agent-Shared"),
    ("obsidian_trading", HOME / "Documents" / "memorybrain" / "Trading"),
    ("hermes_scripts", HOME / ".hermes" / "scripts"),
    ("hermes_cron", HOME / ".hermes" / "cron"),
    ("downloads", HOME / "Downloads"),
    ("seagate_features", Path("/Volumes/Seagate Expansion Drive/hedge-data/features")),
    ("seagate_alpha_manifests", Path("/Volumes/Seagate Expansion Drive/hedge-data/external-alpha-2026-05-25/manifests")),
    ("seagate_local_archives", Path("/Volumes/Seagate Expansion Drive/hedge-data/local-archives")),
    ("seagate_rumbling", Path("/Volumes/Seagate Expansion Drive/rumbling-hedge")),
    ("seagate_rumbling_cold_archives", Path("/Volumes/Seagate Expansion Drive/rumbling-hedge-cold/archives")),
    ("seagate_rumbling_cold_strategy", Path("/Volumes/Seagate Expansion Drive/rumbling-hedge-cold/strategy-lab-history")),
]

ROOT_LIMITS = {
    "downloads": 600,
    "seagate_features": 600,
    "seagate_alpha_manifests": 600,
    "seagate_local_archives": 600,
    "seagate_rumbling": 600,
    "seagate_rumbling_cold_archives": 600,
    "seagate_rumbling_cold_strategy": 600,
    "hermes_cron": 1200,
}

ROOT_DEPTH = {
    "downloads": 3,
    "seagate_features": 5,
    "seagate_alpha_manifests": 3,
    "seagate_local_archives": 3,
    "seagate_rumbling": 5,
    "seagate_rumbling_cold_archives": 4,
    "seagate_rumbling_cold_strategy": 4,
    "hermes_cron": 4,
}

KEYWORDS = {
    "vision": ["vision", "north_star", "master_plan", "goal", "operating-system", "fund"],
    "strategy": ["strategy", "orb", "vol-regime", "trend-mom", "ict", "smc", "donchian", "kalman", "dom", "whale"],
    "evidence": ["backtest", "sweep", "walkforward", "oos", "readiness", "prop-firm", "topstep", "payout"],
    "research": ["research", "paper", "arxiv", "ssrn", "gs-quant", "kronos", "timesfm", "youtube", "yt"],
    "prediction": ["polymarket", "kalshi", "prediction", "gengar"],
    "risk": ["fake", "proxy", "fallback_no_data", "no_data", "stale", "blocked", "quarantine", "not deployable"],
}

HOT_EXTS = {".md", ".json", ".jsonl", ".py", ".ts", ".tsx", ".rs", ".csv", ".parquet", ".pdf", ".txt", ".yaml", ".yml"}


@dataclass
class Artifact:
    root: str
    path: str
    rel: str
    kind: str
    size_bytes: int
    mtime: str
    tags: list[str]
    risk_terms: list[str]
    summary: str | None = None


def iter_files(root: Path, max_files: int = 5000, max_depth: int = 8):
    count = 0
    if not root.exists():
        return
    for dirpath, dirnames, filenames in os.walk(root):
        depth = len(Path(dirpath).relative_to(root).parts)
        if depth >= max_depth:
            dirnames[:] = []
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".Trash")]
        for filename in filenames:
            path = Path(dirpath) / filename
            if path.suffix.lower() not in HOT_EXTS:
                continue
            count += 1
            if count > max_files:
                return
            yield path


def classify(path: Path) -> str:
    name = path.name.lower()
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return "paper_or_pdf"
    if suffix in {".csv", ".parquet"}:
        return "dataset"
    if "backtest" in name or "sweep" in name or "oos" in name:
        return "evidence"
    if "strategy" in name or "signal" in name:
        return "strategy_signal"
    if "cron" in str(path).lower() or "job" in name:
        return "automation"
    if suffix in {".py", ".ts", ".tsx", ".rs"}:
        return "code"
    if suffix in {".md", ".txt"}:
        return "note"
    return "artifact"


def read_sample(path: Path, limit: int = 4096) -> str:
    if path.suffix.lower() in {".pdf", ".parquet"}:
        return ""
    try:
        return path.read_text(errors="ignore")[:limit]
    except Exception:
        return ""


def tags_for(path: Path, sample: str) -> tuple[list[str], list[str]]:
    hay = f"{path.name} {path.parent} {sample}".lower()
    tags = []
    risks = []
    for tag, words in KEYWORDS.items():
        matched = [word for word in words if word in hay]
        if matched:
            tags.append(tag)
            if tag == "risk":
                risks.extend(matched)
    return sorted(set(tags)), sorted(set(risks))


def summarize(path: Path, sample: str) -> str | None:
    if not sample:
        return None
    for line in sample.splitlines():
        stripped = line.strip(" #\t")
        if stripped:
            return stripped[:220]
    return None


def build_report() -> dict:
    artifacts: list[Artifact] = []
    missing_roots = []

    total_cap = 4500
    for label, root in ROOTS:
        if len(artifacts) >= total_cap:
            break
        if not root.exists():
            missing_roots.append({"label": label, "path": str(root)})
            continue
        print(f"indexing {label}: {root}", flush=True)
        for path in iter_files(root, ROOT_LIMITS.get(label, 1800), ROOT_DEPTH.get(label, 8)):
            if len(artifacts) >= total_cap:
                break
            try:
                stat = path.stat()
            except OSError:
                continue
            sample = read_sample(path)
            tags, risks = tags_for(path, sample)
            if not tags and path.suffix.lower() not in {".pdf", ".parquet", ".csv"}:
                continue
            artifacts.append(Artifact(
                root=label,
                path=str(path),
                rel=str(path.relative_to(root)) if path.is_relative_to(root) else str(path),
                kind=classify(path),
                size_bytes=stat.st_size,
                mtime=datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                tags=tags,
                risk_terms=risks,
                summary=summarize(path, sample),
            ))

    by_kind = Counter(a.kind for a in artifacts)
    by_root = Counter(a.root for a in artifacts)
    by_tag = Counter(tag for a in artifacts for tag in a.tags)
    risk_artifacts = [a for a in artifacts if a.risk_terms]

    important = sorted(
        artifacts,
        key=lambda a: (
            len(set(a.tags) & {"vision", "evidence", "strategy", "research"}),
            "risk" in a.tags,
            a.mtime,
            a.size_bytes,
        ),
        reverse=True,
    )[:160]

    return {
        "command": "bill-corpus-audit",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "roots": [{"label": label, "path": str(root), "present": root.exists()} for label, root in ROOTS],
        "missingRoots": missing_roots,
        "counts": {
            "artifacts": len(artifacts),
            "byKind": dict(by_kind),
            "byRoot": dict(by_root),
            "byTag": dict(by_tag),
            "riskArtifacts": len(risk_artifacts),
        },
        "importantArtifacts": [asdict(a) for a in important],
        "riskArtifacts": [asdict(a) for a in sorted(risk_artifacts, key=lambda a: a.mtime, reverse=True)[:120]],
    }


def write_markdown(report: dict) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / "bill-corpus-audit-2026-05-26.md"
    counts = report["counts"]
    lines = [
        "# Bill/Hermes Corpus Audit — 2026-05-26",
        "",
        "Purpose: give agents a clean map of research, evidence, runtime state, and risky/proxy artifacts.",
        "",
        "## Counts",
        "",
        f"- Artifacts indexed: {counts['artifacts']}",
        f"- Risk/proxy/stale artifacts: {counts['riskArtifacts']}",
        f"- By kind: `{json.dumps(counts['byKind'], sort_keys=True)}`",
        f"- By tag: `{json.dumps(counts['byTag'], sort_keys=True)}`",
        "",
        "## Roots",
        "",
    ]
    for root in report["roots"]:
        lines.append(f"- `{root['label']}`: `{root['path']}` ({'present' if root['present'] else 'missing'})")
    lines.extend(["", "## Most Important Artifacts", ""])
    for item in report["importantArtifacts"][:80]:
        summary = f" — {item['summary']}" if item.get("summary") else ""
        lines.append(f"- `{item['kind']}` `{item['path']}` tags={item['tags']}{summary}")
    lines.extend(["", "## Risk/Proxy Watchlist", ""])
    for item in report["riskArtifacts"][:60]:
        summary = f" — {item['summary']}" if item.get("summary") else ""
        lines.append(f"- `{item['path']}` risk={item['risk_terms']}{summary}")
    path.write_text("\n".join(lines) + "\n")
    return path


def status_for(item: dict) -> str:
    """Assign a conservative catalog status for human/agent navigation."""
    kind = item.get("kind")
    tags = set(item.get("tags") or [])
    risks = set(item.get("risk_terms") or [])
    path = str(item.get("path") or "").lower()
    name = Path(path).name
    control_names = {
        "bill-control-hub.md",
        "bill-obsidian-canonical-map.md",
        "bill-obsidian-memory-protocol.md",
        "working-context.md",
    }
    if (
        kind == "note"
        and "/documents/memorybrain/agent-hermes/" in path
        and (name in control_names or "/daily/" in path or "handoff" in name or "next-research-actions" in name)
    ):
        return "active"
    strong_risks = {"fake", "proxy", "fallback_no_data", "no_data", "stale", "quarantine", "not deployable"}
    if risks & strong_risks:
        return "quarantine"
    if "retired" in path or "archive" in path or "cold" in path:
        return "retired"
    if risks or "risk" in tags:
        return "research-only"
    if kind in {"evidence", "dataset"} or "evidence" in tags:
        return "research-only"
    if "strategy" in tags or kind == "strategy_signal":
        return "candidate"
    if "vision" in tags:
        return "active"
    return "research-only"


def write_obsidian_markdown(report: dict, path: Path = OBSIDIAN_MARKDOWN) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    counts = report["counts"]
    status_counts = Counter(status_for(item) for item in report["importantArtifacts"])
    lines = [
        "# Bill Corpus Audit",
        "",
        "Purpose: one Obsidian-facing map of Bill/Hermes research, evidence, code, data, and risky proxy artifacts.",
        "",
        "Execution note: this is memory/navigation only. It does not approve orders, route trades, or override machine gates.",
        "",
        "## Counts",
        "",
        f"- Artifacts indexed: {counts['artifacts']}",
        f"- Risk/proxy/stale artifacts: {counts['riskArtifacts']}",
        f"- Status mix among important artifacts: `{json.dumps(dict(status_counts), sort_keys=True)}`",
        f"- By kind: `{json.dumps(counts['byKind'], sort_keys=True)}`",
        f"- By tag: `{json.dumps(counts['byTag'], sort_keys=True)}`",
        "",
        "## First Read",
        "",
        "- `active`: operator vision, hub, or control context.",
        "- `candidate`: strategy/research seed; needs local implementation and OOS evidence.",
        "- `research-only`: dataset, backtest, paper, transcript, or evidence artifact that cannot route trades.",
        "- `quarantine`: stale, fallback, no-data, proxy, blocked, or risky artifact.",
        "- `retired`: archive/cold/retired material; reference only unless selectively re-tested.",
        "",
        "## Important Artifacts",
        "",
        "| Status | Kind | Tags | Path | Note |",
        "|---|---|---|---|---|",
    ]
    for item in report["importantArtifacts"][:120]:
        summary = (item.get("summary") or "").replace("|", "\\|")
        lines.append(
            f"| `{status_for(item)}` | `{item['kind']}` | `{', '.join(item.get('tags') or [])}` | "
            f"[{Path(item['path']).name}](<{item['path']}>) | {summary} |"
        )
    lines.extend(["", "## Risk/Proxy Watchlist", "", "| Risk Terms | Path | Note |", "|---|---|---|"])
    for item in report["riskArtifacts"][:80]:
        summary = (item.get("summary") or "").replace("|", "\\|")
        lines.append(f"| `{', '.join(item.get('risk_terms') or [])}` | [{Path(item['path']).name}](<{item['path']}>) | {summary} |")
    lines.extend(["", "## Indexed Roots", ""])
    for root in report["roots"]:
        lines.append(f"- `{root['label']}`: `{root['path']}` ({'present' if root['present'] else 'missing'})")
    path.write_text("\n".join(lines) + "\n")
    return path


def main() -> int:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    report = build_report()
    state_path = STATE_DIR / "bill-corpus-audit.latest.json"
    state_path.write_text(json.dumps(report, indent=2) + "\n")
    md_path = write_markdown(report)
    obsidian_path = write_obsidian_markdown(report)
    print(f"wrote {state_path}")
    print(f"wrote {md_path}")
    print(f"wrote {obsidian_path}")
    print(json.dumps(report["counts"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
