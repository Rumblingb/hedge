#!/usr/bin/env python3
"""Open bootstrap PRs that add standard GitHub security hygiene files to repos.

Dry-run by default. Targets HIGH-priority repos from github-repo-audit.latest.json.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
TEMPLATE_ROOT = ROOT / ".github"
DEFAULT_AUDIT = STATE / "github-repo-audit.latest.json"

HYGIENE_FILES = [
    "dependabot.yml",
    "workflows/dependency-review.yml",
    "workflows/codeql.yml",
    "workflows/security-audit.yml",
]


def normalize_repo_token(name: str) -> str:
    return name.split("/", 1)[-1].lower()


def load_priority_repos(audit_path: Path, only: list[str] | None, limit: int) -> list[str]:
    payload = json.loads(audit_path.read_text())
    rows = payload["repos"]
    if only:
        wanted = {normalize_repo_token(name) for name in only}
        rows = [row for row in rows if normalize_repo_token(row["repo"]) in wanted]
    else:
        rows = [row for row in rows if row.get("open_prs") or row.get("updated", "") >= "2026-07-01"]
    rows = [row for row in rows if not row["dependabot"] or not row["ci"]]
    return [row["full"] for row in rows[:limit]]


def clone_repo(full_name: str, workdir: Path) -> Path:
    dest = workdir / full_name.split("/", 1)[1]
    subprocess.run(["gh", "repo", "clone", full_name, str(dest), "--", "--depth", "1"], check=True)
    return dest


def copy_hygiene_files(repo_dir: Path) -> list[str]:
    changed: list[str] = []
    github_dir = repo_dir / ".github"
    github_dir.mkdir(parents=True, exist_ok=True)
    for rel in HYGIENE_FILES:
        src = TEMPLATE_ROOT / rel
        if not src.exists():
            continue
        dest = github_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            continue
        shutil.copy2(src, dest)
        changed.append(f".github/{rel}")
    return changed


def open_pr(full_name: str, repo_dir: Path, changed: list[str], dry_run: bool) -> None:
    branch = "chore/github-security-hygiene"
    subprocess.run(["git", "checkout", "-b", branch], cwd=repo_dir, check=True)
    subprocess.run(["git", "add", *changed], cwd=repo_dir, check=True)
    subprocess.run(
        [
            "git",
            "commit",
            "-m",
            "chore: add dependabot, dependency review, CodeQL, and security audit",
        ],
        cwd=repo_dir,
        check=True,
    )
    if dry_run:
        print(f"[dry-run] would push {full_name} with {len(changed)} files")
        return
    subprocess.run(["git", "push", "-u", "origin", branch], cwd=repo_dir, check=True)
    subprocess.run(
        [
            "gh",
            "pr",
            "create",
            "--repo",
            full_name,
            "--head",
            branch,
            "--title",
            "chore: add GitHub security hygiene (dependabot, CodeQL, dependency review)",
            "--body",
            "Adds standard security hygiene from Rumblingb/hedge templates:\n"
            "- dependabot.yml\n"
            "- dependency-review workflow\n"
            "- CodeQL analysis\n"
            "- scheduled npm audit\n",
        ],
        check=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--repo", action="append", dest="repos")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    targets = load_priority_repos(args.audit, args.repos, args.limit)
    if not targets:
        print("no bootstrap targets")
        return

    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        for full_name in targets:
            print(f"bootstrapping {full_name}")
            repo_dir = clone_repo(full_name, workdir)
            changed = copy_hygiene_files(repo_dir)
            if not changed:
                print(f"  skip — hygiene files already present")
                continue
            open_pr(full_name, repo_dir, changed, dry_run=not args.apply)


if __name__ == "__main__":
    main()
