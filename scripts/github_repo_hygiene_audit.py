#!/usr/bin/env python3
"""Audit Rumblingb GitHub repos for CI, security hygiene, and open work.

Read-only against GitHub API. Writes machine artifacts for agents and humans.
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
DEFAULT_OUTPUT = STATE / "github-repo-audit.latest.json"
DEFAULT_CSV = ROOT / "Agent-Hermes" / "github-repo-audit.csv"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def gh_json(args: list[str]) -> Any:
    result = subprocess.run(["gh", *args], capture_output=True, text=True)
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return result.stdout.strip()


def gh_ok(args: list[str]) -> bool:
    return subprocess.run(["gh", *args], capture_output=True).returncode == 0


def list_repos(owner: str, limit: int) -> list[dict[str, Any]]:
    payload = gh_json(
        [
            "repo",
            "list",
            owner,
            "--limit",
            str(limit),
            "--json",
            "nameWithOwner,isFork,isArchived,updatedAt,defaultBranchRef,visibility",
        ]
    )
    if not isinstance(payload, list):
        raise SystemExit("gh repo list failed — run `gh auth status`")
    return [row for row in payload if not row.get("isFork") and not row.get("isArchived")]


def audit_repo(row: dict[str, Any]) -> dict[str, Any]:
    repo = row["nameWithOwner"]
    branch = (row.get("defaultBranchRef") or {}).get("name") or "main"
    wf_len = gh_json(["api", f"repos/{repo}/contents/.github/workflows", "-q", "length"])
    has_ci = isinstance(wf_len, int) and wf_len > 0
    has_dependabot = gh_ok(["api", f"repos/{repo}/contents/.github/dependabot.yml"])
    has_protection = gh_ok(["api", f"repos/{repo}/branches/{branch}/protection"])
    open_prs = gh_json(["api", f"repos/{repo}/pulls?state=open&per_page=1", "--jq", "length"]) or 0
    open_issues = (
        gh_json(
            [
                "api",
                f"repos/{repo}/issues?state=open&per_page=100",
                "--jq",
                '[.[] | select(.pull_request == null)] | length',
            ]
        )
        or 0
    )
    vuln_enabled = gh_ok(["api", f"repos/{repo}/vulnerability-alerts", "-i", "-X", "HEAD"])
    return {
        "repo": repo.split("/", 1)[1],
        "full": repo,
        "visibility": row.get("visibility", "UNKNOWN"),
        "updated": (row.get("updatedAt") or "")[:10],
        "branch": branch,
        "ci": has_ci,
        "dependabot": has_dependabot,
        "protection": has_protection,
        "open_prs": int(open_prs),
        "open_issues": int(open_issues),
        "vuln_alerts": vuln_enabled,
    }


def gaps(row: dict[str, Any]) -> list[str]:
    out: list[str] = []
    if not row["ci"]:
        out.append("add_ci")
    if not row["dependabot"]:
        out.append("add_dependabot")
    if not row["protection"]:
        out.append("add_branch_protection")
    if row["open_prs"]:
        out.append(f"review_{row['open_prs']}_prs")
    if row["open_issues"]:
        out.append(f"triage_{row['open_issues']}_issues")
    return out


def priority(row: dict[str, Any]) -> str:
    if row["open_prs"] or row["updated"] >= "2026-07-01":
        return "HIGH"
    if row["updated"] >= "2026-06-01":
        return "MED"
    return "LOW"


def write_csv(path: Path, repos: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    headers = [
        "repo",
        "full",
        "visibility",
        "updated",
        "branch",
        "ci",
        "dependabot",
        "branch_protection",
        "open_prs",
        "open_issues",
        "vuln_alerts",
        "status",
        "priority",
        "action_required",
    ]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        for row in sorted(repos, key=lambda item: (item["open_prs"] + item["open_issues"], item["updated"]), reverse=True):
            row_gaps = gaps(row)
            writer.writerow(
                {
                    "repo": row["repo"],
                    "full": row["full"],
                    "visibility": row["visibility"],
                    "updated": row["updated"],
                    "branch": row["branch"],
                    "ci": row["ci"],
                    "dependabot": row["dependabot"],
                    "branch_protection": row["protection"],
                    "open_prs": row["open_prs"],
                    "open_issues": row["open_issues"],
                    "vuln_alerts": row["vuln_alerts"],
                    "status": "COMPLETE" if not row_gaps else "NEEDS_WORK",
                    "priority": priority(row),
                    "action_required": ";".join(row_gaps) if row_gaps else "none",
                }
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit GitHub repo hygiene for Rumblingb")
    parser.add_argument("--owner", default="Rumblingb")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    args = parser.parse_args()

    repos = list_repos(args.owner, args.limit)
    audited = [audit_repo(row) for row in repos]
    complete = sum(1 for row in audited if not gaps(row))
    payload = {
        "generated_at": now_iso(),
        "account": args.owner,
        "repos": audited,
        "summary": {
            "total": len(audited),
            "complete": complete,
            "with_ci": sum(1 for row in audited if row["ci"]),
            "with_dependabot": sum(1 for row in audited if row["dependabot"]),
            "with_protection": sum(1 for row in audited if row["protection"]),
            "open_prs": sum(row["open_prs"] for row in audited),
            "open_issues": sum(row["open_issues"] for row in audited),
            "needs_work": len(audited) - complete,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2))
    write_csv(args.csv, audited)
    print(json.dumps(payload["summary"], indent=2))
    print(f"wrote {args.output}")
    print(f"wrote {args.csv}")


if __name__ == "__main__":
    main()
