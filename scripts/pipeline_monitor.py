#!/usr/bin/env python3
"""
pipeline_monitor.py — Bill/Hedge Data Pipeline Monitoring
==========================================================
Freshness checks, gap detection, and structured alerting for all
data pipeline components.

Pipeline components monitored:
  1. CRITICAL (market hours, high-frequency):
     - realtime-quote.latest.json    (TradingView WS, every 30s)
     - data-freshness-gate.latest.json (freshness check, every 30s)
  
  2. SIGNAL MODULES (market hours, 15-30min):
     - vol-regime-gate.latest.json    (*/30 13-21 UTC)
     - microstructure-filter.latest.json (*/15 13-21 UTC)
     - failure-rag.latest.json        (*/30 13-21 UTC)
     - multitf-confirmation.latest.json (*/15 13-21 UTC)
     - risk-aware-sizing.latest.json  (*/30 13-21 UTC)
  
  3. BRAIN CORTEX (every 30m market hours):
     - arbitration.latest.json
     - master-signal.latest.json
     - 39+ signal reference files
  
  4. TRADE PIPELINE:
     - trade-journal.jsonl            (append on every closed trade)
     - signal-quality-advisor.latest.json (3x daily)
     - trade-performance-analyzer     (EOD 21:00 ET)
  
  5. INFRASTRUCTURE:
     - cron-state-validator.latest.json
     - Strategy engine process check
     - State directory split detection

Usage:
  python3 pipeline_monitor.py              # Full scan, print report
  python3 pipeline_monitor.py --json       # JSON output for cron/alerting
  python3 pipeline_monitor.py --alert      # Only output if there are problems
  python3 pipeline_monitor.py --watchdog   # Single-line status for xbar/menu

Alerting: Non-zero exit on problems. JSON output suitable for Discord webhook.
"""

import json
import os
import pwd
import sys
import time
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

try:
    from scripts.data_freshness_gate import non_execution_grade_reason
except ImportError:
    from data_freshness_gate import non_execution_grade_reason

# ─── PATHS ──────────────────────────────────────────────────────────
# Use real system home (Hermes profiles override Path.home())
HOME = Path(pwd.getpwuid(os.getuid()).pw_dir)
CANONICAL_STATE = HOME / "hedge" / ".rumbling-hedge" / "state"
LEGACY_STATE = HOME / ".rumbling-hedge" / "state"
HEDGE_SCRIPTS = HOME / "hedge" / "scripts"
HERMES_CRON = HOME / ".hermes" / "cron"

# Both state dirs need checking (split-state is a known issue)
ALL_STATE_DIRS = [CANONICAL_STATE, LEGACY_STATE]

NOW = datetime.now(timezone.utc)
NOW_TS = NOW.timestamp()

# ─── MARKET HOURS (ET = UTC-4, BST = UTC+1) ──────────────────────
# NY open: 13:30 UTC (09:30 ET), NY close: 20:00 UTC (16:00 ET)
# Pre-market: 08:00-13:30 UTC, After-hours: 20:00-22:00 UTC
MARKET_OPEN_HOUR = 13   # 09:30 ET
MARKET_CLOSE_HOUR = 20  # 16:00 ET
PRE_MARKET_HOUR = 12    # 08:00 ET
WEEKDAY = NOW.weekday()  # 0=Mon, 6=Sun


def is_market_hours() -> bool:
    """Check if currently within regular market hours (Mon-Fri)."""
    if WEEKDAY >= 5:
        return False
    return MARKET_OPEN_HOUR <= NOW.hour < MARKET_CLOSE_HOUR


def is_pre_market() -> bool:
    if WEEKDAY >= 5:
        return False
    return PRE_MARKET_HOUR <= NOW.hour < MARKET_OPEN_HOUR


def is_trading_day() -> bool:
    return WEEKDAY < 5


def is_active_window() -> bool:
    """Market hours + 1h buffer after close for EOD processing."""
    if WEEKDAY >= 5:
        return False
    return PRE_MARKET_HOUR <= NOW.hour <= (MARKET_CLOSE_HOUR + 1)


# ─── PIPELINE COMPONENT DEFINITIONS ───────────────────────────────
# Each component: (id, display_name, state_filename, max_age_seconds, tier, notes)
# Tiers: CRITICAL, SIGNAL, BRAIN, TRADE, INFRA

PIPELINE_COMPONENTS = [
    # === CRITICAL (market hours) ===
    {
        "id": "realtime_quote",
        "name": "Real-time Quote (TV WebSocket)",
        "files": ["realtime-quote.latest.json"],
        "max_age": 120,          # 2min during market hours
        "max_age_offhours": 3600, # 1hr tolerance off-hours
        "tier": "CRITICAL",
        "script": "realtime_data_bridge.py",
        "cron_hint": "every 30s during market hours",
    },
    {
        "id": "freshness_gate",
        "name": "Data Freshness Gate",
        "files": ["data-freshness-gate.latest.json"],
        "max_age": 300,           # 5min
        "max_age_offhours": 7200,
        "tier": "CRITICAL",
        "script": "data_freshness_gate.py",
        "cron_hint": "with realtime bridge",
    },

    # === SIGNAL MODULES ===
    {
        "id": "vol_regime_gate",
        "name": "Volatility Regime Gate",
        "files": ["vol-regime-gate.latest.json"],
        "max_age": 2400,          # 40min (runs every 30m)
        "max_age_offhours": 86400,
        "tier": "SIGNAL",
        "script": "vol_regime_gate.py",
        "cron_hint": "*/30 13-21 Mon-Fri",
    },
    {
        "id": "microstructure_filter",
        "name": "Microstructure Filter",
        "files": ["microstructure-filter.latest.json"],
        "max_age": 1500,          # 25min (runs every 15m)
        "max_age_offhours": 86400,
        "tier": "SIGNAL",
        "script": "microstructure_filter.py",
        "cron_hint": "*/15 13-21 Mon-Fri",
    },
    {
        "id": "failure_rag",
        "name": "Failure RAG",
        "files": ["failure-rag.latest.json", "failure_rag_trades.json"],
        "max_age": 2400,          # 40min
        "max_age_offhours": 86400,
        "tier": "SIGNAL",
        "script": "failure_rag.py",
        "cron_hint": "*/30 13-21 Mon-Fri",
    },
    {
        "id": "multitf_confirmation",
        "name": "Multi-TF Confirmation",
        "files": ["multitf-confirmation.latest.json"],
        "max_age": 1500,          # 25min (runs every 15m)
        "max_age_offhours": 86400,
        "tier": "SIGNAL",
        "script": "multitf_confirmation.py",
        "cron_hint": "*/15 13-21 Mon-Fri",
    },
    {
        "id": "risk_aware_sizing",
        "name": "Risk-Aware Sizing",
        "files": ["risk-aware-sizing.latest.json"],
        "max_age": 2400,          # 40min
        "max_age_offhours": 86400,
        "tier": "SIGNAL",
        "script": "risk_aware_sizing.py",
        "cron_hint": "*/30 13-21 Mon-Fri",
    },

    # === BRAIN CORTEX ===
    {
        "id": "arbitration",
        "name": "Signal Arbitration",
        "files": ["arbitration.latest.json"],
        "max_age": 2400,          # 40min
        "max_age_offhours": 86400,
        "tier": "BRAIN",
        "script": "brain_cortex.py (sensory cortex)",
        "cron_hint": "every 30m market hours",
    },
    {
        "id": "master_signal",
        "name": "Master Signal",
        "files": ["master-signal.latest.json"],
        "max_age": 2400,
        "max_age_offhours": 86400,
        "tier": "BRAIN",
        "script": "master_bridge.py",
        "cron_hint": "with brain cortex",
    },

    # === TRADE PIPELINE ===
    {
        "id": "trade_journal",
        "name": "Trade Journal",
        "files": ["trade-journal.jsonl"],
        "max_age": 86400,         # Daily check (append-only)
        "max_age_offhours": 172800,
        "tier": "TRADE",
        "script": "trade_journal.py",
        "cron_hint": "on every closed trade",
    },
    {
        "id": "signal_quality_advisor",
        "name": "Signal Quality Advisor",
        "files": ["signal-quality-advisor.latest.json"],
        "max_age": 14400,         # 4h (runs 3x daily)
        "max_age_offhours": 86400,
        "tier": "TRADE",
        "script": "signal_quality_advisor.py",
        "cron_hint": "14/17/20 ET",
    },

    # === INFRASTRUCTURE ===
    {
        "id": "cron_validator",
        "name": "Cron State Validator",
        "files": ["cron-state-validator.latest.json"],
        "max_age": 7200,          # 2h
        "max_age_offhours": 86400,
        "tier": "INFRA",
        "script": "cron_state_validator.py",
        "cron_hint": "periodic",
    },
]


# ─── HELPERS ──────────────────────────────────────────────────────

def find_state_file(filename: str) -> Optional[Path]:
    """Find a state file across both canonical and legacy state dirs."""
    for d in ALL_STATE_DIRS:
        p = d / filename
        if p.exists():
            return p
    return None


def file_age_seconds(path: Path) -> float:
    """Return file age in seconds based on mtime."""
    return NOW_TS - path.stat().st_mtime


def file_age_human(seconds: float) -> str:
    """Human-readable age string."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    elif seconds < 3600:
        return f"{seconds/60:.0f}m"
    elif seconds < 86400:
        return f"{seconds/3600:.1f}h"
    else:
        return f"{seconds/86400:.1f}d"


def read_json_safe(path: Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def check_process_running(pattern: str) -> bool:
    """Check if a process matching pattern is running."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", pattern],
            capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False


# ─── CORE CHECKS ──────────────────────────────────────────────────

def check_component_freshness(component: dict) -> dict:
    """Check freshness of a pipeline component."""
    cid = component["id"]
    max_age = component["max_age"] if is_active_window() else component.get("max_age_offhours", component["max_age"] * 10)

    results = []
    for fname in component["files"]:
        path = find_state_file(fname)
        if path is None:
            results.append({
                "file": fname,
                "status": "MISSING",
                "age_seconds": None,
                "age_human": "N/A",
                "path": None,
                "max_age": max_age,
            })
            continue

        age = file_age_seconds(path)
        status = "PASS" if age <= max_age else "STALE"
        
        result = {
            "file": fname,
            "status": status,
            "age_seconds": round(age, 1),
            "age_human": file_age_human(age),
            "path": str(path),
            "max_age": max_age,
            "mtime": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(),
        }

        # Deep check: read JSON and validate content
        if fname.endswith(".json"):
            data = read_json_safe(path)
            if data is None:
                result["content_status"] = "CORRUPT_JSON"
                result["status"] = "ERROR"
            else:
                result["content_status"] = "VALID"
                # Check for error fields in the data
                if isinstance(data, dict):
                    if data.get("error"):
                        result["data_error"] = str(data["error"])
                    if data.get("verdict") == "BLOCK":
                        result["data_verdict"] = "BLOCK"

        results.append(result)

    # Component-level status
    if all(r["status"] == "PASS" for r in results):
        comp_status = "PASS"
    elif any(r["status"] in ("MISSING", "ERROR") for r in results):
        comp_status = "ERROR"
    else:
        comp_status = "STALE"

    return {
        "component_id": cid,
        "name": component["name"],
        "tier": component["tier"],
        "status": comp_status,
        "script": component["script"],
        "cron_hint": component["cron_hint"],
        "files": results,
    }


def check_split_state() -> dict:
    """Detect state files that exist only in legacy dir (split-state issue)."""
    canonical_files = set()
    legacy_files = set()

    if CANONICAL_STATE.exists():
        canonical_files = {f.name for f in CANONICAL_STATE.iterdir() if f.is_file()}
    if LEGACY_STATE.exists():
        legacy_files = {f.name for f in LEGACY_STATE.iterdir() if f.is_file()}

    # Files only in legacy (script writes to wrong path)
    legacy_only = legacy_files - canonical_files
    # Files in both (duplication)
    duplicated = canonical_files & legacy_files

    issues = []
    if legacy_only:
        issues.append({
            "type": "LEGACY_ONLY",
            "severity": "WARNING",
            "description": f"{len(legacy_only)} state files only in legacy dir (~/.rumbling-hedge/state/)",
            "files": sorted(legacy_only)[:10],  # Cap at 10
            "fix": "Update scripts to write to ~/hedge/.rumbling-hedge/state/",
        })
    if duplicated:
        issues.append({
            "type": "DUPLICATED",
            "severity": "INFO",
            "description": f"{len(duplicated)} state files exist in both directories",
            "files": sorted(duplicated)[:10],
            "fix": "Remove legacy copies after confirming canonical is up-to-date",
        })

    return {
        "check": "split_state_detection",
        "canonical_dir": str(CANONICAL_STATE),
        "legacy_dir": str(LEGACY_STATE),
        "canonical_count": len(canonical_files),
        "legacy_count": len(legacy_files),
        "legacy_only_count": len(legacy_only),
        "duplicated_count": len(duplicated),
        "issues": issues,
        "status": "WARNING" if issues else "PASS",
    }


def check_data_gaps() -> dict:
    """Detect gaps in time-series data (trade journal, quote history)."""
    issues = []

    # Trade journal gap check
    journal_path = find_state_file("trade-journal.jsonl")
    if journal_path and journal_path.exists():
        try:
            lines = journal_path.read_text().strip().splitlines()
            entries = []
            for i, line in enumerate(lines):
                try:
                    entry = json.loads(line)
                    entries.append(entry)
                except json.JSONDecodeError:
                    issues.append({
                        "type": "CORRUPT_LINE",
                        "file": "trade-journal.jsonl",
                        "line": i + 1,
                        "severity": "WARNING",
                    })

            total = len(entries)
            # Check for timestamp gaps (entries > 24h apart during trading days)
            if len(entries) >= 2:
                timestamps = []
                for e in entries:
                    ts = e.get("timestamp") or e.get("closed_at") or e.get("time")
                    if ts:
                        try:
                            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                            timestamps.append(dt)
                        except ValueError:
                            pass
                
                if len(timestamps) >= 2:
                    gaps = []
                    for i in range(1, len(timestamps)):
                        gap = (timestamps[i] - timestamps[i-1]).total_seconds()
                        if gap > 86400 * 3:  # >3 days gap
                            gaps.append({
                                "from": timestamps[i-1].isoformat(),
                                "to": timestamps[i].isoformat(),
                                "gap_days": round(gap / 86400, 1),
                            })
                    if gaps:
                        issues.append({
                            "type": "JOURNAL_GAP",
                            "severity": "WARNING",
                            "description": f"{len(gaps)} gaps > 3 days in trade journal",
                            "gaps": gaps,
                        })

            issues_status = "PASS" if not any(i.get("type") in ("JOURNAL_GAP", "CORRUPT_LINE") for i in issues) else "WARNING"
            return {
                "check": "data_gaps",
                "trade_journal": {
                    "total_entries": total,
                    "file": str(journal_path),
                    "status": issues_status,
                },
                "issues": issues,
                "status": issues_status,
            }
        except Exception as e:
            return {
                "check": "data_gaps",
                "status": "ERROR",
                "error": str(e),
            }
    else:
        return {
            "check": "data_gaps",
            "status": "WARNING",
            "trade_journal": {"total_entries": 0, "status": "MISSING"},
            "issues": [{"type": "MISSING_JOURNAL", "severity": "WARNING",
                        "description": "trade-journal.jsonl not found"}],
        }


def check_realtime_quote_quality() -> dict:
    """Deep check on realtime quote data quality."""
    path = find_state_file("realtime-quote.latest.json")
    if not path:
        return {"check": "quote_quality", "status": "MISSING"}

    data = read_json_safe(path)
    if not data:
        return {"check": "quote_quality", "status": "CORRUPT"}

    issues = []
    source = data.get("source", "unknown")
    mode_nq = data.get("update_mode_nq", "unknown")
    mode_es = data.get("update_mode_es", "unknown")
    price_nq = data.get("price_nq")
    price_es = data.get("price_es")

    # Check source quality. Fresh timestamps do not make delayed feeds execution-grade.
    blocked_reasons = [
        reason for reason in (
            non_execution_grade_reason(source, mode_nq),
            non_execution_grade_reason(source, mode_es),
        )
        if reason
    ]
    if blocked_reasons:
        issues.append({
            "type": "NON_EXECUTION_GRADE_QUOTE",
            "severity": "CRITICAL" if is_market_hours() else "WARNING",
            "description": "; ".join(sorted(set(blocked_reasons))),
            "source": source,
            "update_mode_nq": mode_nq,
            "update_mode_es": mode_es,
        })

    # Check if prices look reasonable (NQ should be ~25000-35000 in 2026)
    if price_nq is not None and not (20000 < price_nq < 40000):
        issues.append({
            "type": "PRICE_ANOMALY",
            "severity": "CRITICAL",
            "description": f"NQ price {price_nq} outside expected range 20000-40000",
        })
    if price_es is not None and not (4000 < price_es < 10000):
        issues.append({
            "type": "PRICE_ANOMALY",
            "severity": "CRITICAL",
            "description": f"ES price {price_es} outside expected range 4000-10000",
        })

    status = "PASS" if not issues else ("CRITICAL" if any(i["severity"] == "CRITICAL" for i in issues) else "WARNING")

    return {
        "check": "quote_quality",
        "status": status,
        "source": source,
        "update_mode_nq": mode_nq,
        "update_mode_es": mode_es,
        "price_nq": price_nq,
        "price_es": price_es,
        "issues": issues,
    }


def check_strategy_engine() -> dict:
    """Check if the strategy engine process is running."""
    running = check_process_running("strategy_dispatcher|brain_cortex|strategy.engine")
    return {
        "check": "strategy_engine_process",
        "status": "PASS" if running else "WARNING",
        "running": running,
        "severity": "WARNING" if not running and is_market_hours() else "INFO",
    }


# ─── MAIN REPORT ──────────────────────────────────────────────────

def run_full_scan() -> dict:
    """Run all monitoring checks and return structured report."""
    # Freshness checks for all components
    component_results = []
    for comp in PIPELINE_COMPONENTS:
        component_results.append(check_component_freshness(comp))

    # Additional checks
    split_state = check_split_state()
    data_gaps = check_data_gaps()
    quote_quality = check_realtime_quote_quality()
    engine = check_strategy_engine()

    # Summary
    statuses = [c["status"] for c in component_results]
    additional_checks = [split_state, data_gaps, quote_quality, engine]
    additional_statuses = [c.get("status") for c in additional_checks]
    critical_issues = [c for c in component_results if c["tier"] == "CRITICAL" and c["status"] != "PASS"]
    all_issues = [c for c in component_results if c["status"] != "PASS"]

    overall = "HEALTHY"
    if critical_issues or "CRITICAL" in additional_statuses:
        overall = "CRITICAL"
    elif any(c["status"] == "ERROR" for c in component_results) or "ERROR" in additional_statuses:
        overall = "ERROR"
    elif all_issues or any(status not in (None, "PASS") for status in additional_statuses):
        overall = "DEGRADED"

    report = {
        "timestamp": NOW.isoformat(),
        "market_hours": is_market_hours(),
        "trading_day": is_trading_day(),
        "active_window": is_active_window(),
        "overall_status": overall,
        "summary": {
            "total_components": len(component_results),
            "passing": statuses.count("PASS"),
            "stale": statuses.count("STALE"),
            "errors": statuses.count("ERROR"),
            "critical_issues": len(critical_issues),
            "additional_warnings": sum(1 for status in additional_statuses if status not in (None, "PASS", "ERROR", "CRITICAL")),
        },
        "components": component_results,
        "checks": {
            "split_state": split_state,
            "data_gaps": data_gaps,
            "quote_quality": quote_quality,
            "strategy_engine": engine,
        },
    }

    # Write state
    report_path = CANONICAL_STATE / "pipeline-monitor.latest.json"
    CANONICAL_STATE.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, default=str))

    return report


def format_text_report(report: dict) -> str:
    """Format report as human-readable text."""
    lines = []
    lines.append(f"{'='*60}")
    lines.append(f"PIPELINE MONITOR — {report['timestamp'][:19]}")
    lines.append(f"{'='*60}")
    
    status = report["overall_status"]
    status_emoji = {"HEALTHY": "✅", "DEGRADED": "⚠️", "ERROR": "❌", "CRITICAL": "🔴"}.get(status, "?")
    lines.append(f"Status: {status_emoji} {status}")
    lines.append(f"Market: {'OPEN' if report['market_hours'] else 'CLOSED'} | Trading day: {'Yes' if report['trading_day'] else 'No'}")
    
    s = report["summary"]
    lines.append(f"Components: {s['passing']}/{s['total_components']} passing | {s['stale']} stale | {s['errors']} errors")
    lines.append("")

    # Component details (only non-PASS unless verbose)
    lines.append("--- Component Freshness ---")
    for comp in report["components"]:
        emoji = {"PASS": "✅", "STALE": "⚠️", "ERROR": "❌"}.get(comp["status"], "?")
        tier_tag = f"[{comp['tier']}]"
        
        if comp["status"] != "PASS":
            lines.append(f"  {emoji} {tier_tag:12s} {comp['name']}")
            for f in comp["files"]:
                age_str = f.get("age_human", "N/A")
                lines.append(f"      └─ {f['file']}: {f['status']} (age: {age_str})")
        else:
            lines.append(f"  {emoji} {tier_tag:12s} {comp['name']}")
    
    lines.append("")
    lines.append("--- Additional Checks ---")
    
    # Split state
    ss = report["checks"]["split_state"]
    ss_emoji = "✅" if ss["status"] == "PASS" else "⚠️"
    lines.append(f"  {ss_emoji} Split State: {ss['legacy_only_count']} legacy-only, {ss['duplicated_count']} duplicated")
    
    # Quote quality
    qq = report["checks"]["quote_quality"]
    qq_emoji = "✅" if qq["status"] == "PASS" else ("🔴" if qq["status"] == "CRITICAL" else "⚠️")
    lines.append(f"  {qq_emoji} Quote Quality: source={qq.get('source','?')} NQ={qq.get('price_nq','?')} ES={qq.get('price_es','?')}")
    for issue in qq.get("issues", []):
        lines.append(f"      └─ [{issue['severity']}] {issue['description']}")
    
    # Data gaps
    dg = report["checks"]["data_gaps"]
    dg_emoji = "✅" if dg["status"] == "PASS" else "⚠️"
    tj = dg.get("trade_journal", {})
    lines.append(f"  {dg_emoji} Trade Journal: {tj.get('total_entries', 0)} entries")
    
    # Strategy engine
    se = report["checks"]["strategy_engine"]
    se_emoji = "✅" if se["status"] == "PASS" else "⚠️"
    lines.append(f"  {se_emoji} Strategy Engine: {'running' if se['running'] else 'NOT RUNNING'}")

    lines.append(f"\n{'='*60}")
    return "\n".join(lines)


def format_alert_message(report: dict) -> str:
    """Format a concise alert message for Discord/notifications."""
    if report["overall_status"] == "HEALTHY":
        return ""

    lines = [f"🔴 Pipeline Alert: {report['overall_status']}"]
    lines.append(f"Time: {report['timestamp'][:19]} UTC")
    
    # Critical issues first
    for comp in report["components"]:
        if comp["status"] != "PASS" and comp["tier"] == "CRITICAL":
            lines.append(f"\n⚠️ **{comp['name']}** ({comp['status']})")
            for f in comp["files"]:
                if f["status"] != "PASS":
                    lines.append(f"  • {f['file']}: {f['status']} ({f.get('age_human', 'N/A')})")

    # Other issues
    other_issues = [c for c in report["components"] if c["status"] != "PASS" and c["tier"] != "CRITICAL"]
    if other_issues:
        lines.append(f"\n📊 {len(other_issues)} non-critical issue(s):")
        for comp in other_issues[:5]:  # Cap at 5
            lines.append(f"  • {comp['name']}: {comp['status']}")

    # Quote quality issues
    qq = report["checks"]["quote_quality"]
    if qq.get("issues"):
        lines.append(f"\n📈 Quote: {qq.get('source')} mode={qq.get('update_mode_nq')}")

    return "\n".join(lines)


def format_watchdog_line(report: dict) -> str:
    """Single-line status for xbar/menu bar."""
    s = report["summary"]
    status = report["overall_status"]
    emoji = {"HEALTHY": "🟢", "DEGRADED": "🟡", "ERROR": "🔴", "CRITICAL": "🔴"}.get(status, "⚪")
    return f"{emoji} Pipeline: {s['passing']}/{s['total_components']} OK | {report['timestamp'][11:19]} UTC"


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Bill/Hedge Pipeline Monitor")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--alert", action="store_true", help="Only output if problems found")
    parser.add_argument("--watchdog", action="store_true", help="Single-line status")
    parser.add_argument("--verbose", action="store_true", help="Show all components including healthy")
    args = parser.parse_args()

    report = run_full_scan()

    if args.watchdog:
        print(format_watchdog_line(report))
        return 0 if report["overall_status"] == "HEALTHY" else 1

    if args.json:
        print(json.dumps(report, indent=2, default=str))
        return 0 if report["overall_status"] == "HEALTHY" else 1

    if args.alert:
        msg = format_alert_message(report)
        if msg:
            print(msg)
            return 1
        return 0

    # Default: full text report
    print(format_text_report(report))
    return 0 if report["overall_status"] == "HEALTHY" else 1


if __name__ == "__main__":
    sys.exit(main())
