#!/usr/bin/env python3
"""Run one AI-Scientist financial_strategy seed safely (research-only).

Reads ai-scientist-templates/financial_strategy/seed_ideas.json, enforces
hardSafety env, executes the seed command, and writes a state artifact.
Never arms execution or touches the broker.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SEED_PATH = ROOT / "ai-scientist-templates" / "financial_strategy" / "seed_ideas.json"
STATE = ROOT / ".rumbling-hedge" / "state"
DEFAULT_OUT = STATE / "ai-scientist-seed-runner.latest.json"
HERMES = Path.home() / "Documents" / "memorybrain" / "Agent-Hermes"

REQUIRED_ENV = {
    "BILL_ENABLE_FUTURES_DEMO_EXECUTION": "false",
    "RH_TOPSTEP_READ_ONLY": "true",
    "RH_LIVE_EXECUTION_ENABLED": "false",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_seeds() -> dict[str, Any]:
    return json.loads(SEED_PATH.read_text())


def list_seeds(data: dict[str, Any]) -> list[dict[str, Any]]:
    return list(data.get("queue") or [])


def expand_command(cmd: str) -> str:
    # Expand $(date +%Y%m%d) for out_dir uniqueness
    today = datetime.now().strftime("%Y%m%d")
    return re.sub(r"\$\(date \+%Y%m%d\)", today, cmd)


def enforce_env() -> dict[str, str]:
    env = os.environ.copy()
    for key, value in REQUIRED_ENV.items():
        env[key] = value
    return env


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str) + "\n")


def find_final_info(out_dir_hint: str | None) -> Path | None:
    if not out_dir_hint:
        return None
    path = Path(out_dir_hint)
    if not path.is_absolute():
        path = ROOT / path
    candidate = path / "final_info.json"
    return candidate if candidate.exists() else None


def extract_out_dir(cmd: str) -> str | None:
    m = re.search(r"--out_dir\s+(\S+)", cmd)
    return m.group(1) if m else None


def run_seed(seed_id: str, *, dry_run: bool = False) -> dict[str, Any]:
    data = load_seeds()
    seeds = list_seeds(data)
    seed = next((s for s in seeds if s.get("id") == seed_id), None)
    if seed is None:
        known = [s.get("id") for s in seeds]
        raise SystemExit(f"Unknown seed id {seed_id!r}. Known: {known}")

    cmd = expand_command(str(seed.get("command") or ""))
    if not cmd:
        raise SystemExit(f"Seed {seed_id} has no command")

    out_dir = extract_out_dir(cmd)
    payload: dict[str, Any] = {
        "ts": now_iso(),
        "seedId": seed_id,
        "lane": seed.get("lane"),
        "priority": seed.get("priority"),
        "statusBefore": seed.get("status"),
        "oneVariable": seed.get("oneVariable"),
        "command": cmd,
        "outDir": out_dir,
        "dryRun": dry_run,
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "readyForExecution": False,
        "hardSafety": data.get("hardSafety"),
        "requiredEnv": REQUIRED_ENV,
    }

    if dry_run:
        payload["decision"] = "dry-run-only"
        payload["ok"] = True
        return payload

    env = enforce_env()
    started = datetime.now(timezone.utc)
    proc = subprocess.run(
        ["bash", "-lc", cmd],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
    )
    ended = datetime.now(timezone.utc)
    payload["exitCode"] = proc.returncode
    payload["durationSec"] = round((ended - started).total_seconds(), 3)
    payload["stdoutTail"] = (proc.stdout or "")[-4000:]
    payload["stderrTail"] = (proc.stderr or "")[-4000:]
    payload["ok"] = proc.returncode == 0

    final_info = find_final_info(out_dir)
    if final_info is not None:
        try:
            info = json.loads(final_info.read_text())
            payload["finalInfoPath"] = str(final_info)
            # Template nests metrics under AlphaStrategyTemplate.means
            means = (
                (info.get("AlphaStrategyTemplate") or {}).get("means")
                if isinstance(info.get("AlphaStrategyTemplate"), dict)
                else {}
            ) or {}
            safety = (
                (info.get("AlphaStrategyTemplate") or {}).get("safety")
                if isinstance(info.get("AlphaStrategyTemplate"), dict)
                else {}
            ) or {}
            oos_pf = means.get("oos_profit_factor")
            oos_n = means.get("oos_trade_count")
            wf_share = means.get("walkforward_positive_fold_share")
            go_live_bar = {
                "oosPfAtLeast1_5": bool(oos_pf is not None and float(oos_pf) >= 1.5),
                "oosTradesAtLeast30": bool(oos_n is not None and int(oos_n) >= 30),
                "walkforwardShareAtLeast0_6": bool(
                    wf_share is not None and float(wf_share) >= 0.6
                ),
            }
            go_live_bar["passed"] = all(go_live_bar.values())
            payload["finalInfoSummary"] = {
                "ready_for_execution": means.get("ready_for_execution", info.get("ready_for_execution")),
                "ready_for_paper": means.get("ready_for_paper", info.get("ready_for_paper")),
                "research_only": safety.get("research_only", info.get("research_only")),
                "promotion_blockers": info.get("promotion_blockers"),
                "metric_blockers": info.get("metric_blockers"),
                "oos": {
                    "oos_total_net_points": means.get("oos_total_net_points"),
                    "oos_profit_factor": oos_pf,
                    "oos_trade_count": oos_n,
                    "oos_win_rate": means.get("oos_win_rate"),
                    "walkforward_positive_fold_share": wf_share,
                },
                "goLiveLadderBar": go_live_bar,
            }
            if go_live_bar["passed"]:
                payload["decision"] = "seed-cleared-research-bar-not-promotable"
        except Exception as exc:
            payload["finalInfoError"] = str(exc)

    payload["decision"] = (
        "seed-run-complete-research-only"
        if payload["ok"]
        else "seed-run-failed-research-only"
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one AI-Scientist seed (research-only)")
    parser.add_argument("--id", help="Seed id from seed_ideas.json")
    parser.add_argument("--list", action="store_true", help="List seeds and exit")
    parser.add_argument("--dry-run", action="store_true", help="Print command only")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    data = load_seeds()
    if args.list or not args.id:
        rows = [
            {
                "id": s.get("id"),
                "priority": s.get("priority"),
                "lane": s.get("lane"),
                "status": s.get("status"),
                "oneVariable": s.get("oneVariable"),
            }
            for s in list_seeds(data)
        ]
        print(json.dumps({"seeds": rows, "count": len(rows)}, indent=2))
        if not args.id:
            return 0

    result = run_seed(args.id, dry_run=args.dry_run)
    write_json(args.out, result)

    # Lightweight Obsidian note for today's run
    note = HERMES / f"ai-scientist-seed-run-{datetime.now(timezone.utc).date().isoformat()}.md"
    try:
        note.write_text(
            "\n".join(
                [
                    f"# AI Scientist Seed Run — {result['seedId']}",
                    "",
                    f"Parent: [[BILL-CONTROL-HUB]]",
                    "",
                    f"- ts: `{result['ts']}`",
                    f"- decision: `{result.get('decision')}`",
                    f"- ok: `{result.get('ok')}`",
                    f"- outDir: `{result.get('outDir')}`",
                    f"- artifact: `{args.out}`",
                    "",
                    "Research-only. Template output is never route approval.",
                    "",
                ]
            )
        )
        result["obsidianNote"] = str(note)
        write_json(args.out, result)
    except Exception:
        pass

    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
