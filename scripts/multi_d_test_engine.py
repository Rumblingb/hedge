#!/usr/bin/env python3
"""
Multi-Dimensional Strategy Test Engine
=======================================
Tests every extracted strategy across ALL dimensions:
  - Timeframes: 1m, 5m, 15m, 30m, 60m, daily
  - Tickers: NQ, ES, CL, GC, 6E, ZN
  - Day-of-week: Mon-Fri performance breakdown
  - Market regimes: trend, range, reversal, event, low-vol
  - Correlation with existing strategies

The engine doesn't implement strategies itself. It:
  1. Creates a multi-D test plan from extraction metadata
  2. Checks existing data availability for each dimension
  3. Submits test jobs to the Rust full_strategy_pipeline or Bill TS factory
  4. Collects results (reading state files)
  5. Tracks which dimensions produce edge vs noise
  6. Updates the learning loop with dimensional findings

Usage:
  python3 scripts/multi_d_test_engine.py --plan <extraction-file>
  python3 scripts/multi_d_test_engine.py --run <plan-file>
  python3 scripts/multi_d_test_engine.py --results <plan-file>
  python3 scripts/multi_d_test_engine.py --status
  python3 scripts/multi_d_test_engine.py --auto
"""

import json
import os
import subprocess
import sys
import hashlib
import glob
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HEDGE = Path(os.path.expanduser("~/hedge"))
STATE_DIR = Path(os.path.expanduser("~/.rumbling-hedge"))
TEST_DIR = STATE_DIR / "multi-d-testing"
EXTRACTED_DIR = STATE_DIR / "research" / "extracted"
DATA_DIR = HEDGE / "data" / "free"
SCRIPTS_DIR = HEDGE / "scripts"

TIMEFRAMES = ["1m", "5m", "15m", "30m", "60m", "1d"]
TICKERS = ["NQ", "ES", "CL", "GC", "6E", "ZN"]
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
REGIMES = ["trend", "range", "reversal", "event", "low_vol"]

KNOWN_STRATEGIES = [
    "orb-breakout", "wq-trend-mom", "wq-vol-regime",
    "wq-alpha-001", "wq-alpha-012", "vol-imbalance",
    "ict-displacement", "prop-fvg-scalp", "prop-liq-grab",
    "prop-orb-scalp", "prop-vwap-bounce", "prop-momentum-scalp",
    "regime-orb-breakout", "donchian-breakout", "insider-flow",
    "cot-reversal", "vwap-reversion", "heiken-ashi-trend",
    "manipulation-4h", "opening-candle-classifier",
    "sr-proximity", "ichimoku-full", "kalman-pairs",
    "pead-earnings", "noise-stepforward",
]


def log(msg: str):
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"  [{ts}] {msg}")


# ─── DATA AVAILABILITY ──────────────────────────────────────────────

def get_available_data() -> dict[str, dict[str, list[str]]]:
    """Check what timeframe/ticker CSV files exist."""
    available = {}
    for tf in TIMEFRAMES:
        available[tf] = {}
        for ticker in TICKERS:
            patterns = [
                str(DATA_DIR / f"{ticker}-{tf}-*.csv"),
                str(DATA_DIR / f"*{ticker}*{tf}*.csv"),
                str(DATA_DIR / f"ALL*{tf}*.csv"),
            ]
            found = []
            for p in patterns:
                found.extend(glob.glob(p))
            if found:
                available[tf][ticker] = found
    return available


def check_existing_edges() -> dict[str, Any]:
    """Read existing edge data from known state files."""
    edges = {}
    
    # Check signal arbitration for current regime
    arb_path = STATE_DIR / "state" / "arbitration.latest.json"
    if arb_path.exists():
        try:
            with open(arb_path) as f:
                edges["arbitration"] = json.load(f)
        except (json.JSONDecodeError, Exception):
            pass
    
    # Check 60m strategy eval results
    eval_files = list(TEST_DIR.glob("*-eval-result.json")) + list(STATE_DIR.glob("state/60m-strategy*.json"))
    for ef in eval_files:
        if ef.exists():
            try:
                with open(ef) as f:
                    edges[ef.stem] = json.load(f)
            except Exception:
                pass
    
    return edges


# ─── TEST PLAN GENERATION ──────────────────────────────────────────

def get_signal_from_extraction(extraction: dict) -> dict | None:
    """Extract signal info from an extraction entry."""
    signal = extraction.get("signal", {})
    if not signal:
        return None
    return {
        "name": signal.get("signal_name", "unknown"),
        "instrument": signal.get("instrument_type", "futures"),
        "timeframe_hint": signal.get("timeframe", "any"),
        "direction": signal.get("direction_rule", "BOTH"),
        "entry": signal.get("entry_condition", ""),
        "exit": signal.get("exit_condition", ""),
        "market_logic": signal.get("market_logic", ""),
        "confidence": signal.get("confidence_score", 0.5),
    }


def generate_test_plan(extraction: dict) -> dict | None:
    """Generate a multi-D test plan from an extraction."""
    signal = get_signal_from_extraction(extraction)
    if not signal:
        return None

    plan_id = hashlib.md5(
        (signal["name"] + extraction.get("source_url", "")).encode()
    ).hexdigest()[:12]

    # Determine priority timeframes from signal hint
    hint = signal["timeframe_hint"]
    priority_tfs = [hint] if hint in TIMEFRAMES else ["15m", "60m", "5m"]
    if hint == "intraday":
        priority_tfs = ["5m", "15m", "30m", "60m"]
    elif hint == "any":
        priority_tfs = ["15m", "60m", "5m", "1d"]

    # Determine target tickers from instrument type
    instr = signal.get("instrument", "futures")
    if instr == "futures":
        target_tickers = TICKERS
    elif instr == "crypto":
        target_tickers = ["BTC", "ETH"]
    elif instr == "stocks":
        target_tickers = ["ES"]
    else:
        target_tickers = ["NQ", "ES"]

    plan = {
        "plan_id": plan_id,
        "signal_name": signal["name"],
        "source_url": extraction.get("source_url", ""),
        "market_logic": signal["market_logic"],
        "entry_logic": signal["entry"],
        "exit_logic": signal["exit"],
        "confidence": signal["confidence"],
        "status": "planned",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dimensions": {
            "timeframes": {
                "priority": priority_tfs,
                "all": TIMEFRAMES,
            },
            "tickers": {
                "priority": target_tickers[:3],  # Top 3
                "all": target_tickers,
            },
            "days": DAYS,
            "regimes": REGIMES,
        },
        "existing_data": {},
        "correlation_with": [],
    }

    # Check existing data
    available = get_available_data()
    for tf in priority_tfs:
        plan["existing_data"][tf] = {}
        for t in target_tickers[:3]:
            files = available.get(tf, {}).get(t, [])
            plan["existing_data"][tf][t] = {
                "available": len(files) > 0,
                "files": files
            }

    return plan


def generate_all_plans() -> list[dict]:
    """Generate test plans for all unplanned extractions."""
    plans = []
    seen_ids = set()
    
    # Load existing plans to avoid duplicates
    existing_plans = load_plans("active")
    for p in existing_plans:
        seen_ids.add(p.get("plan_id", ""))
    
    # Scan extraction files
    extract_files = sorted(EXTRACTED_DIR.glob("signals-*.json"))
    for ef in extract_files:
        try:
            with open(ef) as f:
                data = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            continue
        
        extractions = data.get("extractions", [])
        for ext in extractions:
            plan = generate_test_plan(ext)
            if plan and plan["plan_id"] not in seen_ids:
                plans.append(plan)
                seen_ids.add(plan["plan_id"])
    
    return plans


# ─── PLAN PERSISTENCE ──────────────────────────────────────────────

def load_plans(status: str | None = None) -> list[dict]:
    """Load test plans, optionally filtered by status."""
    TEST_DIR.mkdir(parents=True, exist_ok=True)
    plans = []
    for f in TEST_DIR.glob("plan-*.json"):
        try:
            with open(f) as pf:
                plan = json.load(pf)
            if status is None or plan.get("status") == status:
                plans.append(plan)
        except (json.JSONDecodeError, Exception):
            continue
    return plans


def save_plan(plan: dict):
    TEST_DIR.mkdir(parents=True, exist_ok=True)
    path = TEST_DIR / f"plan-{plan['plan_id']}.json"
    with open(path, "w") as f:
        json.dump(plan, f, indent=2)
    return path


# ─── CORRELATION ANALYSIS ──────────────────────────────────────────

def check_strategy_overlap(signal_name: str, entry_logic: str) -> list[dict]:
    """
    Check how a new strategy relates to known strategies.
    Uses keyword matching against known strategy descriptions.
    This is a heuristic — the real overlap check happens in the
    Rust pipeline via the correlation matrix.
    """
    relations = []
    entry_lower = entry_logic.lower()

    # Relationship mapping based on market logic keywords
    overlap_map = {
        "breakout": ["orb-breakout", "regime-orb-breakout", "prop-orb-scalp"],
        "trend": ["wq-trend-mom", "heiken-ashi-trend"],
        "reversal": ["cot-reversal", "vwap-reversion"],
        "mean.reversion": ["vwap-reversion", "sr-proximity"],
        "volume": ["wq-vol-regime", "vol-imbalance"],
        "fvg": ["prop-fvg-scalp", "ict-displacement"],
        "liquidity": ["prop-liq-grab", "ict-displacement"],
        "momentum": ["prop-momentum-scalp", "wq-trend-mom"],
        "insider": ["insider-flow"],
        "manipulation": ["manipulation-4h"],
        "opening": ["opening-candle-classifier"],
        "ichimoku": ["ichimoku-full"],
        "donchian": ["donchian-breakout"],
        "vmap": ["vwap-reversion"],
        "fibonacci": [] if signal_name == "fibonacci-signal" else [],
        "kalman": ["kalman-pairs"],
        "cot": ["cot-reversal"],
        "pead": ["pead-earnings"],
    }

    for keyword, related in overlap_map.items():
        if keyword in entry_lower:
            for r in related:
                if r != signal_name:  # Don't compare with self
                    relations.append({
                        "keyword": keyword,
                        "existing_strategy": r,
                        "relationship": "overlap" if keyword in entry_lower else "complement",
                    })

    if not relations:
        relations.append({
            "keyword": "none",
            "existing_strategy": "uncorrelated",
            "relationship": "novel",
        })

    return relations


# ─── RUN PIPELINE TESTS ────────────────────────────────────────────

def submit_test_job(plan: dict) -> dict:
    """
    Submit a test job to the existing pipeline infrastructure.
    For now, this creates a test request file that the Rust/TS
    pipeline can pick up. The actual testing happens in batch.
    """
    job = {
        "plan_id": plan["plan_id"],
        "signal_name": plan["signal_name"],
        "priority_timeframes": plan["dimensions"]["timeframes"]["priority"],
        "priority_tickers": plan["dimensions"]["tickers"]["priority"],
        "days_to_test": plan["dimensions"]["days"],
        "regimes_to_test": plan["dimensions"]["regimes"],
        "entry_logic": plan["entry_logic"],
        "exit_logic": plan["exit_logic"],
        "market_logic": plan["market_logic"],
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "status": "submitted",
    }
    
    job_dir = TEST_DIR / "jobs"
    job_dir.mkdir(parents=True, exist_ok=True)
    
    job_path = job_dir / f"job-{plan['plan_id']}.json"
    with open(job_path, "w") as f:
        json.dump(job, f, indent=2)
    
    return job


def collect_job_results() -> list[dict]:
    """Collect any available test results from jobs."""
    results = []
    jobs_dir = TEST_DIR / "jobs"
    if not jobs_dir.exists():
        return results
    
    # Check if Rust pipeline results exist for these plans
    for job_file in jobs_dir.glob("job-*.json"):
        try:
            with open(job_file) as f:
                job = json.load(f)
        except Exception:
            continue
        
        if job.get("status") == "completed":
            results.append(job)
            continue
        
        # Check for Rust pipeline output for this signal
        signal = job["signal_name"]
        # Look in standard state files
        for pattern in [
            STATE_DIR / "logs" / "full-strategy-pipeline*.json",
            STATE_DIR / "state" / "*.latest.json",
        ]:
            for log_file in glob.glob(str(pattern)):
                try:
                    with open(log_file) as f:
                        data = json.load(f)
                    if isinstance(data, dict) and signal in str(data):
                        job["status"] = "completed"
                        job["result_data"] = data
                        with open(job_file, "w") as f:
                            json.dump(job, f, indent=2)
                        results.append(job)
                        break
                except Exception:
                    continue
    
    return results


# ─── TEST RESULTS → LEARNING FEEDBACK ─────────────────────────────

def build_feedback_payload(plan: dict, results: dict | None = None) -> dict | None:
    """
    Build a structured payload for the learning loop from test results.
    This tells the learning loop which dimensions produced edge.
    """
    if not results:
        return None
    
    feedback = {
        "plan_id": plan["plan_id"],
        "signal_name": plan["signal_name"],
        "source_url": plan.get("source_url", ""),
        "dimensional_results": {
            "best_timeframe": None,
            "best_ticker": None,
            "best_day": None,
            "best_regime": None,
        },
        "edge_found": False,
        "total_r": 0,
        "win_rate": 0,
        "notes": [],
    }
    
    # Parse results for dimensional breakdown
    rd = results.get("result_data", {})
    
    # Look for per-timeframe breakdowns
    if isinstance(rd, dict):
        for key, val in rd.items():
            key_lower = key.lower()
            
            # Check for R-multiple data
            if "total_r" in key_lower or "r_multiple" in key_lower:
                try:
                    r = float(val) if not isinstance(val, dict) else float(val.get("value", 0))
                    feedback["total_r"] = r
                    feedback["edge_found"] = r > 0
                except (ValueError, TypeError):
                    pass
            
            if "win_rate" in key_lower or "wr" in key_lower:
                try:
                    wr = float(val) if not isinstance(val, dict) else float(val.get("value", 0))
                    feedback["win_rate"] = wr
                except (ValueError, TypeError):
                    pass
    
    return feedback


# ─── MAIN OPERATIONS ────────────────────────────────────────────────

def cmd_plan(extraction_path: str | None = None):
    """Generate test plans from extractions."""
    if extraction_path:
        with open(extraction_path) as f:
            extractions = json.load(f).get("extractions", [])
        plans = []
        for ext in extractions:
            plan = generate_test_plan(ext)
            if plan:
                save_plan(plan)
                plans.append(plan)
        log(f"Generated {len(plans)} test plans from {extraction_path}")
    else:
        plans = generate_all_plans()
        for p in plans:
            save_plan(p)
        log(f"Generated {len(plans)} test plans from all extractions")
    
    # Show plan summary
    for p in plans:
        corr = check_strategy_overlap(p["signal_name"], p["entry_logic"])
        rel_types = set(c["relationship"] for c in corr)
        log(f"  📋 {p['signal_name']}: tf={p['dimensions']['timeframes']['priority']} "
            f"tickers={p['dimensions']['tickers']['priority'][:2]} "
            f"relations={rel_types}")
    
    return plans


def cmd_submit():
    """Submit planned tests to pipeline."""
    plans = load_plans("planned")
    for p in plans:
        job = submit_test_job(p)
        p["status"] = "submitted"
        save_plan(p)
        log(f"  📤 Submitted: {p['signal_name']} ({p['plan_id']})")
    
    log(f"Submitted {len(plans)} test jobs")
    return plans


def cmd_collect():
    """Collect test results and update learning state."""
    results = collect_job_results()
    feedbacks = []
    
    for r in results:
        plan_id = r.get("plan_id", "")
        plans = [p for p in load_plans() if p["plan_id"] == plan_id]
        if plans:
            plan = plans[0]
            feedback = build_feedback_payload(plan, r)
            if feedback:
                plan["status"] = "completed"
                plan["feedback"] = feedback
                save_plan(plan)
                feedbacks.append(feedback)
                log(f"  ✅ {plan['signal_name']}: edge={feedback['edge_found']} "
                    f"R={feedback['total_r']:.1f} WR={feedback['win_rate']:.1%}")
    
    # Write consolidated feedback for learning loop
    if feedbacks:
        feedback_file = STATE_DIR / "multi-d-testing" / "dimensional-feedback.json"
        with open(feedback_file, "w") as f:
            json.dump({
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "feedback_count": len(feedbacks),
                "feedbacks": feedbacks,
            }, f, indent=2)
        log(f"Wrote {len(feedbacks)} dimensional feedback entries")
    
    return feedbacks


def cmd_status():
    """Show test engine status."""
    plans = load_plans()
    active = [p for p in plans if p["status"] in ("planned", "submitted")]
    completed = [p for p in plans if p["status"] == "completed"]
    
    print(f"\n📊 MULTI-D TEST ENGINE STATUS")
    print(f"{'='*60}")
    print(f"    Plans: {len(plans)} total ({len(active)} active, {len(completed)} completed)")
    print(f"    Tickers: {', '.join(TICKERS)}")
    print(f"    Timeframes: {', '.join(TIMEFRAMES)}")
    print(f"    Known strategies: {len(KNOWN_STRATEGIES)}")
    
    if active:
        print(f"\n  Active plans:")
        for p in active:
            print(f"    ⏳ {p['signal_name']:30s} [{p['status']}] "
                  f"tf={p['dimensions']['timeframes']['priority']}")
    
    if completed:
        print(f"\n  Completed:")
        for p in completed[:5]:
            fb = p.get("feedback", {})
            edge = "✅ EDGE" if fb.get("edge_found") else "❌ NO EDGE"
            print(f"    {edge} {p['signal_name']:30s} R={fb.get('total_r', 0):.1f}")
    
    # Data availability
    avail = get_available_data()
    print(f"\n  Available data:")
    for tf in TIMEFRAMES:
        tickers_avail = [t for t in TICKERS if tf in avail and t in avail[tf]]
        if tickers_avail:
            print(f"    {tf:5s}: {', '.join(tickers_avail)}")
    
    print()


def cmd_auto():
    """Full auto cycle: plan → submit → collect."""
    log("Multi-D Test Engine: AUTO CYCLE")
    log("────────────────────────────────")
    
    # 1. Generate plans from new extractions
    plans = cmd_plan(None)
    
    # 2. Submit planned tests
    if plans:
        cmd_submit()
    
    # 3. Collect results from completed jobs
    feedbacks = cmd_collect()
    
    # 4. Write summary state
    summary = {
        "last_auto_cycle": datetime.now(timezone.utc).isoformat(),
        "new_plans": len(plans),
        "collected_feedback": len(feedbacks),
        "plans_total": len(load_plans()),
        "completed_total": len(load_plans("completed")),
    }
    summary_file = TEST_DIR / "test-engine-summary.latest.json"
    with open(summary_file, "w") as f:
        json.dump(summary, f, indent=2)
    
    log(f"\n  Summary: {summary['new_plans']} new plans, "
        f"{summary['collected_feedback']} feedback entries")
    return summary


# ─── CLI ────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Multi-Dimensional Strategy Test Engine"
    )
    parser.add_argument("--plan", nargs="?", const=None, metavar="FILE",
                        help="Generate test plans (optional: specific extraction file)")
    parser.add_argument("--submit", action="store_true", help="Submit planned tests")
    parser.add_argument("--collect", action="store_true", help="Collect test results")
    parser.add_argument("--status", action="store_true", help="Show test engine status")
    parser.add_argument("--auto", action="store_true", help="Auto cycle: plan → submit → collect")
    
    args = parser.parse_args()
    
    if args.status:
        cmd_status()
    elif args.auto:
        cmd_auto()
    elif args.plan is not None:
        cmd_plan(args.plan)
    elif args.submit:
        cmd_submit()
    elif args.collect:
        cmd_collect()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
