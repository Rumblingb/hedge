#!/usr/bin/env python3
"""
# Self-Evolving Brain — Orchestrator
# =========================================
# The pipeline is one processing pathway within the brain architecture.
# Brain consciousness (brain_cortex.py) runs every 30m during market hours,
# ingesting ALL inputs simultaneously and routing through weighted pathways.
#
# This orchestrator runs the deep processing pipeline that the brain
# triggers when it needs deeper strategy extraction and testing.
#
# Brain regions:
#   SENSORY CORTEX — ingests 17 signal state files + research + agent messages
#   HIPPOCAMPUS — associative memory, recalls similar past states
#   ASSOCIATION CORTEX — builds integrated awareness from ALL inputs
#   MOTOR CORTEX — routes decisions to execution engines
#   LIMBIC SYSTEM — Bayesian source quality, neural pathway plasticity
#   BRAIN STEM — kill switch, circadian rhythm, health monitoring
#
# The "pipeline" (bridge → collect → extract → multi-d-test → dispatch → learn)
# is a DEEP PROCESSING PATHWAY triggered when the brain detects:
#   - Novel regime (needs more research)
#   - Strong signal (needs deeper testing)
#   - New research content (needs extraction)
#
# Usage:
#   python3 scripts/self_evolving_loop.py          # Run brain cycle + pipeline
#   python3 scripts/self_evolving_loop.py --brain-only  # Brain consciousness only

Usage:
  python3 scripts/self_evolving_loop.py          # Run full pipeline
  python3 scripts/self_evolving_loop.py --status  # Show system status
  python3 scripts/self_evolving_loop.py --collect-only   # Run collection only
  python3 scripts/self_evolving_loop.py --extract-only   # Run extraction only
  python3 scripts/self_evolving_loop.py --test-only      # Run multi-D testing only
  python3 scripts/self_evolving_loop.py --dispatch-only  # Run dispatch only
  python3 scripts/self_evolving_loop.py --learn-only     # Run learning loop only
  python3 scripts/self_evolving_loop.py --dry-run        # Show what would run without executing
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS_DIR = Path(os.path.expanduser("~/hedge/scripts"))
STATE_DIR = Path(os.path.expanduser("~/.rumbling-hedge"))
LEARNING_DIR = STATE_DIR / "learning"
RESEARCH_DIR = STATE_DIR / "research"
EXTRACTED_DIR = RESEARCH_DIR / "extracted"
DISPATCHER_DIR = STATE_DIR / "dispatcher"

SCRIPTS = {
    "brain": SCRIPTS_DIR / "brain_cortex.py",
    "bridge": SCRIPTS_DIR / "agent_bridge.py",
    "collect": SCRIPTS_DIR / "research_collector.py",
    "extract": SCRIPTS_DIR / "signal_extractor.py",
    "multi-d-test": SCRIPTS_DIR / "multi_d_test_engine.py",
    "dispatch": SCRIPTS_DIR / "strategy_dispatcher.py",
    "learn": SCRIPTS_DIR / "learning_loop.py",
}

PIPELINE_LOG = STATE_DIR / "self-evolving-loop.jsonl"


def log_event(event_type: str, data: dict):
    """Append structured event to pipeline log."""
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event_type,
        **data,
    }
    PIPELINE_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(PIPELINE_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")


def check_dependencies() -> list[str]:
    """Check which scripts exist and which are missing."""
    missing = []
    for name, path in SCRIPTS.items():
        if not path.exists():
            missing.append(name)
            print(f"  ⚠️  {path.name} not found at {path}")
    return missing


def run_script(name: str, args: list[str] | None = None) -> dict:
    """Run a pipeline script and return its status."""
    script_path = SCRIPTS[name]
    cmd = ["python3", str(script_path)]
    if args:
        cmd.extend(args)

    log_event("pipeline-step-start", {"step": name, "cmd": " ".join(cmd)})
    print(f"\n  ⚡ Running {name}...")

    start = time.time()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,  # 10 min per step
            cwd=str(SCRIPTS_DIR.parent),
        )
        duration = time.time() - start
        status = "ok" if result.returncode == 0 else "error"
        summary = result.stdout.strip()[-2000:] if result.stdout else ""
        error = result.stderr.strip()[-1000:] if result.stderr else ""

        log_event("pipeline-step-end", {
            "step": name,
            "status": status,
            "duration_s": round(duration, 1),
            "returncode": result.returncode,
        })

        if status == "ok":
            print(f"  ✅ {name} completed in {duration:.1f}s")
        else:
            print(f"  ❌ {name} failed (code {result.returncode}) in {duration:.1f}s")
            if error:
                print(f"     stderr: {error[:500]}")

        return {
            "status": status,
            "duration": duration,
            "summary": summary,
            "error": error,
            "returncode": result.returncode,
        }

    except subprocess.TimeoutExpired:
        duration = time.time() - start
        log_event("pipeline-step-timeout", {"step": name, "duration_s": round(duration, 1)})
        print(f"  ⏰ {name} timed out after {duration:.1f}s")
        return {"status": "timeout", "duration": duration, "summary": "", "error": "timeout", "returncode": -1}

    except FileNotFoundError:
        log_event("pipeline-step-missing", {"step": name})
        print(f"  ❌ {name}: script not found")
        return {"status": "missing", "duration": 0, "summary": "", "error": "not found", "returncode": -1}


def print_section(title: str):
    """Print a section header."""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def show_status():
    """Show the current state of the self-evolving loop."""
    print_section("SELF-EVOLVING LOOP — STATUS")

    # Source quality
    sq_file = LEARNING_DIR / "source-quality.json"
    if sq_file.exists():
        with open(sq_file) as f:
            sources = json.load(f)
        print(f"\n📊 Source Quality Tracking:")
        print(f"   {'Source':<30} {'Type':<12} {'Qual':<6} {'Conf':<7} {'Priority':<8}")
        print(f"   {'-'*63}")
        for s in sorted(sources, key=lambda x: x.get("quality", 0), reverse=True)[:15]:
            qual = s.get("quality", 0)
            conf = s.get("confidence", 0)
            pri = s.get("priority", "medium")
            print(f"   {s.get('name','?'):<30} {s.get('type','?'):<12} {qual:<6.3f} {conf:<7.1f} {pri:<8}")
        print(f"   ({len(sources)} total sources tracked)")
    else:
        print(f"\n📊 Source Quality: Not yet initialized")
        print(f"   (run the pipeline or 'learning_loop.py --add-source' to start tracking)")

    # Dispatch summary
    disp_status = run_script("dispatch", ["--status"])
    # Already printed above

    # Agent bridge status
    bridge_status = run_script("bridge", ["--status"])

    # Gold signals
    extract_status = run_script("extract", ["--summary"])

    # Scanner status
    collect_status = run_script("collect", ["--status"])

    # Multi-D test engine status
    test_status = run_script("multi-d-test", ["--status"])

    # Pipeline log stats
    if PIPELINE_LOG.exists():
        with open(PIPELINE_LOG) as f:
            entries = [json.loads(l) for l in f if l.strip()]
        total_runs = len([e for e in entries if e.get("event") == "pipeline-run-complete"])
        last_run = entries[-1]["ts"] if entries else "never"
        print(f"\n📈 Pipeline Runs: {total_runs}")
        print(f"   Last Run: {last_run}")
    else:
        print(f"\n📈 Pipeline Runs: 0 (not yet executed)")


def run_pipeline(stages: list[str] | None = None, dry_run: bool = False):
    """
    Run the full pipeline or specific stages.
    Stages: collect, extract, multi-d-test, dispatch, learn
    """
    if stages is None:
        stages = ["collect", "extract", "dispatch", "learn"]

    print_section("SELF-EVOLVING CLOSED LOOP")

    # Check dependencies first
    missing = check_dependencies()
    if missing:
        print(f"\n⚠️  Missing scripts: {', '.join(missing)}")
        print("Create them before running the pipeline.")
        return False

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    print(f"  Date: {date_str}")
    print(f"  Stages: {' → '.join(stages)}")

    if dry_run:
        print(f"\n  🏁 DRY RUN — no scripts executed")
        for stage in stages:
            print(f"     Would run: {SCRIPTS[stage].name}")
        return True

    results = {}
    pipeline_ok = True

    for i, stage in enumerate(stages):
        print_section(f"STAGE {i+1}/{len(stages)}: {stage.upper()}")

        # Bridge stage needs --wire-crons flag
        if stage == "bridge":
            result = run_script(stage, ["--wire-crons"])
        else:
            result = run_script(stage)
        results[stage] = result

        if result["status"] != "ok":
            # Don't abort the whole pipeline — let subsequent stages try
            # (they handle missing inputs gracefully)
            pipeline_ok = False
            print(f"  ⚠️  Continuing despite {stage} failure...")

    # Log pipeline completion
    log_event("pipeline-run-complete", {
        "date": date_str,
        "stages": stages,
        "results": {k: v["status"] for k, v in results.items()},
        "all_ok": pipeline_ok,
    })

    print_section("PIPELINE SUMMARY")
    for stage, result in results.items():
        icon = "✅" if result["status"] == "ok" else "❌" if result["status"] == "error" else "⏰"
        print(f"  {icon} {stage}: {result['status']} ({result['duration']:.1f}s)")

    if pipeline_ok:
        print(f"\n  🎯 Full pipeline completed successfully")
    else:
        print(f"\n  ⚠️  Pipeline completed with {sum(1 for r in results.values() if r['status'] != 'ok')} failure(s)")

    return pipeline_ok


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Self-Evolving Closed Loop — trading research pipeline orchestrator"
    )
    parser.add_argument("--status", action="store_true", help="Show system status")
    parser.add_argument("--dry-run", action="store_true", help="Show what would run without executing")
    parser.add_argument("--brain-only", action="store_true", help="Run brain consciousness only")
    parser.add_argument("--bridge-only", action="store_true", help="Wire existing crons into loop")
    parser.add_argument("--collect-only", action="store_true", help="Run collection only")
    parser.add_argument("--extract-only", action="store_true", help="Run extraction only")
    parser.add_argument("--test-only", action="store_true", help="Run multi-D testing only")
    parser.add_argument("--dispatch-only", action="store_true", help="Run dispatch only")
    parser.add_argument("--learn-only", action="store_true", help="Run learning loop only")

    args = parser.parse_args()

    if args.status:
        show_status()
        return

    # Determine stages — brain runs first, then pipeline stages
    if args.brain_only:
        stages = ["brain"]
    elif args.bridge_only:
        stages = ["bridge"]
    elif args.collect_only:
        stages = ["bridge", "collect"]
    elif args.extract_only:
        stages = ["extract"]
    elif args.test_only:
        stages = ["multi-d-test"]
    elif args.dispatch_only:
        stages = ["dispatch"]
    elif args.learn_only:
        stages = ["learn"]
    else:
        stages = ["brain", "bridge", "collect", "extract", "multi-d-test", "dispatch", "learn"]

    run_pipeline(stages, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
