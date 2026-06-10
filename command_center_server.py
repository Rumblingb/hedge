#!/usr/bin/env python3
"""Agentic Fund Command Center — serves live system state as JSON API."""

import json, os, subprocess, time, glob, re
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

HOME = os.path.expanduser("~")
REPO_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = os.path.join(HOME, ".rumbling-hedge", "state")
REPO_STATE_DIR = os.path.join(REPO_DIR, ".rumbling-hedge", "state")
HERMES_SCRIPTS = os.path.join(HOME, ".hermes", "scripts")
CRON_OUT = os.path.join(HOME, ".hermes", "cron", "output")
OBSIDIAN_HERMES = os.path.join(HOME, "Documents", "memorybrain", "Agent-Hermes")
CONTROL_HUB = os.path.join(OBSIDIAN_HERMES, "BILL-CONTROL-HUB.md")
ACCOUNT_RE = re.compile(r"\b\d{2,3}KTC(?:-[A-Z0-9]+)+(?:-[A-Z0-9]+)*\b")
TRADING_TIMEZONE = ZoneInfo(os.environ.get("BILL_TRADING_TIMEZONE", "Europe/London"))

def daily_plan_path():
    trading_date = datetime.now(timezone.utc).astimezone(TRADING_TIMEZONE).date().isoformat()
    return os.path.join(OBSIDIAN_HERMES, "daily", f"{trading_date}-bill-trading-plan.md")

def load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except: return None

def load_text(path):
    try:
        with open(path, errors="replace") as f:
            return f.read()
    except:
        return ""

def redact_account(value):
    return ACCOUNT_RE.sub("<REDACTED_ACCOUNT>", str(value or ""))

def state_json(name):
    """Prefer repo state for Bill control-plane audits; fall back to home state."""
    for root in (REPO_STATE_DIR, STATE_DIR):
        data = load_json(os.path.join(root, name))
        if data is not None:
            return data, root
    return None, None

def state_mtime(name):
    for root in (REPO_STATE_DIR, STATE_DIR):
        path = os.path.join(root, name)
        if os.path.exists(path):
            return os.path.getmtime(path), root
    return None, None

def http_json(url, timeout=2):
    try:
        import urllib.request
        resp = urllib.request.urlopen(url, timeout=timeout)
        raw = resp.read()
        data = json.loads(raw) if raw else {}
        return True, data
    except Exception as e:
        return False, {"error": str(e)}

def get_system():
    """CPU, RAM, swap, disk, uptime, load."""
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=0.5)
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()
        disk = psutil.disk_usage("/")
        boot = psutil.boot_time()
        return {
            "cpu_pct": cpu,
            "ram_used_pct": mem.percent,
            "ram_total_gb": round(mem.total / 1e9, 1),
            "ram_used_gb": round(mem.used / 1e9, 1),
            "swap_used_pct": swap.percent,
            "swap_total_gb": round(swap.total / 1e9, 1),
            "disk_used_pct": disk.percent,
            "disk_free_gb": round(disk.free / 1e9, 1),
            "uptime_seconds": time.time() - boot,
            "load_1m": os.getloadavg()[0],
            "load_5m": os.getloadavg()[1],
            "load_15m": os.getloadavg()[2],
        }
    except ImportError:
        return {"error": "psutil not installed", "load_1m": os.getloadavg()[0]}

def get_process_info(name_filter):
    """Check if a process is running by name."""
    try:
        out = subprocess.check_output(["pgrep", "-f", name_filter], timeout=3).decode().strip()
        pids = [int(x) for x in out.split("\n") if x]
        return {"running": len(pids) > 0, "count": len(pids), "pids": pids}
    except:
        return {"running": False, "count": 0, "pids": []}

def get_bridge_status():
    """Prefer bridge HTTP health over process-name guesses."""
    ok, health = http_json("http://127.0.0.1:8788/health", timeout=2)
    status_ok, status = http_json("http://127.0.0.1:8788/status", timeout=2)
    if ok or status_ok:
        postiz = status.get("postiz", {}) if isinstance(status, dict) else {}
        return {
            "running": True,
            "http": True,
            "health": health,
            "postiz": {
                "integrations": postiz.get("integrations", 0),
                "connected": [x.get("identifier") for x in postiz.get("connected", []) if isinstance(x, dict)],
                "missingCore": postiz.get("missingCore", []),
            },
        }
    proc = get_process_info("master_bridge")
    proc["http"] = False
    proc["health"] = health
    return proc

def get_signal_state():
    """Read all signal state files."""
    signals = {}
    for fname in sorted(os.listdir(STATE_DIR)):
        if fname.endswith(".json"):
            path = os.path.join(STATE_DIR, fname)
            try:
                data = load_json(path)
                if data:
                    key = fname.replace(".latest.json", "").replace(".json", "")
                    signals[key] = {
                        "mtime": os.path.getmtime(path),
                        "size": os.path.getsize(path),
                        "verdict": data.get("verdict", data.get("regime", "unknown")),
                        "confidence": data.get("confidence", data.get("details", {}).get("confidence_modifier", 0)),
                    }
            except: pass
    return signals

def get_n8n_status():
    """Check n8n health and summarize the real Postgres-backed control plane."""
    health_ok, health = http_json("http://localhost:5678/healthz", timeout=3)
    audit, audit_root = state_json("bill-runtime-architecture-audit.latest.json")
    n8n = audit.get("n8n", {}) if isinstance(audit, dict) else {}
    self_heal, _ = state_json("n8n-self-heal.json")
    self_heal = self_heal if isinstance(self_heal, dict) else {}
    bridge_ok, bridge_status = http_json("http://127.0.0.1:8788/status", timeout=2)
    bridge_n8n = bridge_status.get("n8n", {}) if isinstance(bridge_status, dict) else {}
    bridge_workflows = bridge_n8n.get("workflows", []) if isinstance(bridge_n8n, dict) else []
    workflow_errors = self_heal.get("errors") if isinstance(self_heal.get("errors"), list) else []
    workflows_healthy = bool(self_heal.get("workflows_healthy", True))

    return {
        "running": health_ok,
        "health": health,
        "workflowHealth": "healthy" if workflows_healthy else "errors",
        "workflowErrors": workflow_errors[:5],
        "source": n8n.get("source", "unknown"),
        "path": n8n.get("path"),
        "auditRoot": audit_root,
        "workflowCount": n8n.get("workflowCount", len(bridge_workflows) if bridge_workflows else 0),
        "activeCount": n8n.get("activeCount", sum(1 for w in bridge_workflows if w.get("active"))),
        "billWorkflowCount": n8n.get("billWorkflowCount", 0),
        "activeBillWorkflowCount": n8n.get("activeBillWorkflowCount", 0),
        "executionAuthority": False,
        "role": "monitoring/research/review/notifications only",
        "warnings": (audit.get("warnings", []) if isinstance(audit, dict) else [])[:5],
        "operatorRead": (
            "n8n workflow errors are monitoring/automation health issues only; they do not grant or remove trade permission."
            if workflow_errors
            else "n8n monitoring/research workflows visible; execution authority remains false."
        ),
        "bridgeVisible": bridge_ok,
    }

def get_control_plane():
    """Founder-safe summary: what is allowed, what is blocked, and why."""
    audit, audit_root = state_json("bill-runtime-architecture-audit.latest.json")
    preflight, preflight_root = state_json("realtime-data-preflight.latest.json")
    audit = audit if isinstance(audit, dict) else {}
    preflight = preflight if isinstance(preflight, dict) else {}
    return {
        "decision": audit.get("decision", "unknown"),
        "researchOnly": audit.get("researchOnly", True),
        "readyForPaper": audit.get("readyForPaper", False),
        "readyForDemoExpansion": audit.get("readyForDemoExpansion", False),
        "readyForExecution": audit.get("readyForExecution", False),
        "writesOrders": audit.get("writesOrders", False),
        "touchesBroker": audit.get("touchesBroker", False),
        "movesFunds": audit.get("movesFunds", False),
        "realtimeDataReady": preflight.get("readyForExecutionData", False),
        "dataDecision": preflight.get("decision", "unknown"),
        "dataBlockers": preflight.get("blockers", [])[:5],
        "safeEnv": preflight.get("proofTiming", {}).get("safeEnv", {}),
        "auditRoot": audit_root,
        "preflightRoot": preflight_root,
        "operatorGuidance": audit.get("operatorGuidance", [])[:4],
        "warnings": audit.get("warnings", [])[:5],
    }

def parse_daily_control():
    """Extract the human control lines that matter before any route decision."""
    daily_plan = daily_plan_path()
    daily = load_text(daily_plan)
    hub = load_text(CONTROL_HUB)

    def match(pattern, text, default="unknown"):
        m = re.search(pattern, text, re.I | re.M)
        return m.group(1).strip() if m else default

    decision = match(r"\*\*Decision:\*\*\s*(.+)", daily, "No new Bill/Hermes orders approved.")
    route = match(r"^BILL_ROUTE_APPROVAL:\s*(.+)$", daily, "UNKNOWN")
    broker = match(r"^BROKER_RECONCILIATION:\s*(.+)$", daily, "UNKNOWN")
    mode = match(r"\*\*Mode:\*\*\s*(.+)", hub, "research / shadow / broker-flat monitoring")
    execution = match(r"\*\*Execution:\*\*\s*(.+)", hub, "locked")
    return {
        "decision": decision,
        "routeApproval": route,
        "brokerReconciliation": broker,
        "mode": mode,
        "execution": execution,
        "dailyPlan": daily_plan,
        "controlHub": CONTROL_HUB,
    }

def get_market_data_plane():
    """Data provenance and execution-grade status."""
    preflight, preflight_root = state_json("realtime-data-preflight.latest.json")
    quote, quote_root = state_json("realtime-quote.latest.json")
    freshness, freshness_root = state_json("data-freshness-gate.latest.json")
    databento, databento_root = state_json("databento-realtime-smoke.latest.json")
    feed_audit, _ = state_json("free-data-feed-audit.latest.json")
    preflight = preflight if isinstance(preflight, dict) else {}
    quote = quote if isinstance(quote, dict) else {}
    freshness = freshness if isinstance(freshness, dict) else {}
    databento = databento if isinstance(databento, dict) else {}
    feed_audit = feed_audit if isinstance(feed_audit, dict) else {}
    quote_mtime, _ = state_mtime("realtime-quote.latest.json")
    quote_age = round(time.time() - quote_mtime, 1) if quote_mtime else None
    freshness_checks = freshness.get("checks", []) if isinstance(freshness.get("checks"), list) else []
    max_quote_age = next(
        (
            check.get("max_age")
            for check in freshness_checks
            if isinstance(check, dict) and isinstance(check.get("max_age"), (int, float))
        ),
        60,
    )
    quote_execution_grade = bool(quote.get("execution_grade"))
    quote_fresh = quote_age is not None and quote_age <= max_quote_age
    freshness_verdict = freshness.get("verdict", "unknown")
    effective_freshness_verdict = (
        "PASS"
        if freshness_verdict == "PASS" and quote_execution_grade and quote_fresh
        else "STALE"
        if quote_age is not None and not quote_fresh
        else freshness_verdict
    )
    effective_blockers = list(preflight.get("blockers", [])[:5])
    if quote_age is None:
        effective_blockers.append("canonical realtime quote state is missing")
    elif not quote_fresh:
        effective_blockers.append(f"canonical realtime quote is stale ({quote_age}s old; max {max_quote_age}s)")
    if not quote_execution_grade:
        effective_blockers.append("canonical realtime quote is not execution-grade")
    topstep = get_topstep_data_plane()
    broker_grade_data_proof = (
        bool(topstep.get("topstepRealtimeProofPassed"))
        and bool(topstep.get("executionGradeRealtimeProofPassed"))
        and bool(topstep.get("currentBarsProofPassed"))
    )
    feed_providers = feed_audit.get("providers") if isinstance(feed_audit.get("providers"), list) else []
    alpaca = next(
        (row for row in feed_providers if isinstance(row, dict) and row.get("id") == "alpaca-paper"),
        {},
    )
    fresh_enough_for_execution = quote_execution_grade and quote_fresh
    ready_for_execution_data = bool(preflight.get("readyForExecutionData", False)) and fresh_enough_for_execution
    return {
        "readyForExecutionData": ready_for_execution_data,
        "brokerGradeDataProofPassed": broker_grade_data_proof,
        "brokerGradeDataProofSource": "topstepx_projectx",
        "brokerGradeDataProofMode": "read-only-current-bars-and-realtime-proof",
        "decision": preflight.get("decision", "unknown") if ready_for_execution_data else "block-execution-data",
        "blockers": effective_blockers[:6],
        "preferredSource": "topstepx_projectx",
        "source": quote.get("source", "unknown"),
        "executionGrade": quote_execution_grade,
        "quoteFresh": quote_fresh,
        "freshEnoughForExecution": fresh_enough_for_execution,
        "ageSeconds": quote_age,
        "freshnessVerdict": effective_freshness_verdict,
        "databentoStatus": databento.get("status", "unknown"),
        "databentoRole": "optional-secondary-depth-research",
        "alpacaSandbox": {
            "status": alpaca.get("mode") or "available-via-plugin-manifest",
            "configured": bool(alpaca.get("configured", False)),
            "wired": bool(alpaca.get("wired", False)),
            "role": alpaca.get("role") or "equities-options-crypto-research-and-paper-sandbox",
            "command": alpaca.get("command"),
            "notFor": "Topstep futures broker truth or futures route approval",
            "executionAuthority": False,
        },
        "topstepStatus": topstep.get("status"),
        "topstepCurrentBarsProofPassed": topstep.get("currentBarsProofPassed", False),
        "topstepBrokerParityPassed": topstep.get("brokerParityPassed", False),
        "topstepRealtimeProofPassed": topstep.get("topstepRealtimeProofPassed", False),
        "topstepExecutionGradeRealtimeProofPassed": topstep.get("executionGradeRealtimeProofPassed", False),
        "topstepReadyForFiveMinuteResearch": topstep.get("readyForFiveMinuteResearch", False),
        "recommendedPath": (
            "Use TopstepX/ProjectX as the primary 5m+ broker-grade data path; keep TradingView as alert/context "
            "and Databento as optional future depth/order-flow research. Use Alpaca only as an equities/options/crypto "
            "paper/research sandbox. Execution remains blocked until deterministic gates pass."
        ),
        "quote": {
            "source": quote.get("source", "unknown"),
            "executionGrade": quote_execution_grade,
            "ageSeconds": quote_age,
            "maxAgeSeconds": max_quote_age,
            "updateModeNq": quote.get("update_mode_nq"),
            "updateModeEs": quote.get("update_mode_es"),
            "priceNqPresent": quote.get("price_nq") is not None,
            "priceEsPresent": quote.get("price_es") is not None,
            "blockReason": quote.get("execution_block_reason"),
        },
        "freshness": {
            "verdict": effective_freshness_verdict,
            "artifactVerdict": freshness_verdict,
            "action": "allow_trades" if ready_for_execution_data else "block_all_trades",
            "checks": freshness_checks[:4],
        },
        "databento": {
            "status": databento.get("status", "unknown"),
            "readyForExecutionDataProof": databento.get("readyForExecutionDataProof", False),
            "reason": databento.get("quoteSummary", {}).get("reason") or databento.get("reason"),
        },
        "topstep": topstep,
        "safeEnv": preflight.get("proofTiming", {}).get("safeEnv", {}),
        "roots": {
            "preflight": preflight_root,
            "quote": quote_root,
            "freshness": freshness_root,
            "databento": databento_root,
        },
    }

def get_data_master_plane():
    """Machine-readable historical data catalog, kept separate from broker truth."""
    catalog, root = state_json("bill-data-master.latest.json")
    catalog = catalog if isinstance(catalog, dict) else {}
    top = catalog.get("topDatasets") if isinstance(catalog.get("topDatasets"), list) else []
    tier_counts = catalog.get("tierCounts") if isinstance(catalog.get("tierCounts"), dict) else {}
    output_csv = catalog.get("outputCsv")
    csv_exists = bool(output_csv and os.path.exists(str(output_csv)))
    quarantine = int(tier_counts.get("quarantine-review") or 0)
    gold_walkforward = int(tier_counts.get("gold-walkforward") or 0)
    dataset_count = int(catalog.get("datasetCount") or 0)
    return {
        "decision": "data-master-visible-execution-locked" if catalog else "data-master-missing-execution-locked",
        "present": bool(catalog),
        "datasetCount": dataset_count,
        "tierCounts": tier_counts,
        "goldWalkforwardCount": gold_walkforward,
        "quarantineReviewCount": quarantine,
        "outputCsv": output_csv,
        "csvExists": csv_exists,
        "freshness": freshness_for_state("bill-data-master.latest.json", stale_after_seconds=24 * 3600),
        "topDatasets": top[:6],
        "hardRules": first_list(catalog.get("hardRules"), 4),
        "readyForExecution": False,
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "movesFunds": False,
        "operatorRead": (
            "Data Master CSV is inventory/trust-tier truth for research. "
            "TopstepX/ProjectX remains broker/current-bar truth for demo observation."
        ),
        "root": root,
    }

def age_for_state(name):
    mtime, _ = state_mtime(name)
    return round(time.time() - mtime, 1) if mtime else None

def freshness_for_state(name, stale_after_seconds=6 * 3600):
    age = age_for_state(name)
    if age is None:
        return {
            "status": "missing",
            "ageSeconds": None,
            "staleAfterSeconds": stale_after_seconds,
        }
    return {
        "status": "stale" if age > stale_after_seconds else "fresh",
        "ageSeconds": age,
        "staleAfterSeconds": stale_after_seconds,
    }

def age_label(age_seconds):
    if age_seconds is None:
        return "missing"
    if age_seconds < 120:
        return f"{int(age_seconds)}s old"
    if age_seconds < 7200:
        return f"{round(age_seconds / 60, 1)}m old"
    return f"{round(age_seconds / 3600, 1)}h old"

def get_topstep_data_plane():
    """TopstepX/ProjectX is the preferred broker-relevant data path for 5m+ work."""
    smoke, _ = state_json("topstep-market-data-smoke.latest.json")
    archive, _ = state_json("topstep-readonly-bar-archive.latest.json")
    parity, _ = state_json("topstep-broker-local-bar-parity.latest.json")
    realtime, _ = state_json("topstep-realtime-proof.latest.json")
    requirements, _ = state_json("futures-data-requirements.latest.json")
    monitor, _ = state_json("topstep-100k-monitor.latest.json")
    screen, _ = state_json("topstepx-dashboard-screen-proof.latest.json")
    session_safety, _ = state_json("topstep-session-safety.latest.json")
    session_clearance, _ = state_json("topstep-session-safety-clearance.latest.json")
    demo_observation, _ = state_json("topstep-demo-observation-posture.latest.json")
    demo_learning, _ = state_json("topstep-daily-learning.latest.json")
    broker_parity_plan, _ = state_json("futures-broker-parity-plan.latest.json")
    smoke = smoke if isinstance(smoke, dict) else {}
    archive = archive if isinstance(archive, dict) else {}
    parity = parity if isinstance(parity, dict) else {}
    realtime = realtime if isinstance(realtime, dict) else {}
    requirements = requirements if isinstance(requirements, dict) else {}
    monitor = monitor if isinstance(monitor, dict) else {}
    screen = screen if isinstance(screen, dict) else {}
    session_safety = session_safety if isinstance(session_safety, dict) else {}
    session_clearance = session_clearance if isinstance(session_clearance, dict) else {}
    demo_observation = demo_observation if isinstance(demo_observation, dict) else {}
    demo_learning = demo_learning if isinstance(demo_learning, dict) else {}
    broker_parity_plan = broker_parity_plan if isinstance(broker_parity_plan, dict) else {}
    next_window = (
        broker_parity_plan.get("nextOpenSessionProofWindow")
        if isinstance(broker_parity_plan.get("nextOpenSessionProofWindow"), dict)
        else {}
    )
    broker = monitor.get("broker_reconciliation", {}) if isinstance(monitor.get("broker_reconciliation"), dict) else {}
    current_bars = bool(smoke.get("brokerCurrentBarsProofPassed"))
    parity_passed = bool(parity.get("brokerParityPassed"))
    archive_sessions = int(archive.get("nqArchiveRthSessionCount") or 0)
    archive_symbols = archive.get("symbols") if isinstance(archive.get("symbols"), dict) else {}
    archive_nq = archive_symbols.get("NQ") if isinstance(archive_symbols.get("NQ"), dict) else {}
    archive_rows = int(archive_nq.get("rowCount") or 0)
    direct_topstep_source_ok = current_bars and archive.get("status") == "PASS" and archive_rows > 0
    execution_grade = bool(requirements.get("executionGradeRealtimeProofPassed"))
    realtime_proof = bool(realtime.get("readyForExecutionDataProof"))
    ready_research = direct_topstep_source_ok or (current_bars and parity_passed)
    blockers = []
    if not current_bars:
        blockers.append("topstep-current-bars-proof-missing")
    if not parity_passed and not direct_topstep_source_ok:
        blockers.append("topstep-broker-local-parity-missing")
    if archive_sessions < int(archive.get("minimumSessionsForResearch") or 20):
        blockers.append("topstep-readonly-archive-depth-thin")
    if not realtime_proof:
        blockers.append("topstep-realtime-signalr-proof-not-cleared")
    if session_safety.get("pauseBrokerTouchingProofs") is True:
        blockers.append("topstep-session-safety-paused")
    if realtime_proof and not execution_grade:
        blockers.append("topstep-realtime-proof-not-promoted-to-canonical-freshness")
    elif not execution_grade:
        blockers.append("execution-grade-realtime-proof-not-cleared")
    return {
        "status": "PASS" if ready_research else "BLOCKED",
        "preferredFor": "5m+ futures research and broker-relevant current bars",
        "apiBase": "https://api.topstepx.com",
        "officialApi": True,
        "subscription": "$29/mo list; Topstep help says code topstep gives 50% monthly discount while available",
        "localDeviceRequired": True,
        "currentBarsProofPassed": current_bars,
        "currentBarsAgeSeconds": age_for_state("topstep-market-data-smoke.latest.json"),
        "brokerParityChecked": bool(parity.get("brokerParityChecked")),
        "brokerParityPassed": parity_passed,
        "brokerParityAgeSeconds": age_for_state("topstep-broker-local-bar-parity.latest.json"),
        "directTopstepSourceOk": direct_topstep_source_ok,
        "archiveNqRows": archive_rows,
        "archiveStatus": archive.get("status", "unknown"),
        "archiveRthSessions": archive_sessions,
        "archiveMinimumSessions": archive.get("minimumSessionsForResearch"),
        "archivePreferredSessions": archive.get("preferredSessionsForPromotionReview"),
        "archiveAgeSeconds": age_for_state("topstep-readonly-bar-archive.latest.json"),
        "topstepRealtimeProofPassed": realtime_proof,
        "topstepRealtimeProofStatus": realtime.get("status", "not-run"),
        "topstepRealtimeProofAgeSeconds": age_for_state("topstep-realtime-proof.latest.json"),
        "topstepRealtimeSymbols": realtime.get("symbols") if isinstance(realtime.get("symbols"), dict) else {},
        "writesRealtimeQuoteState": realtime.get("writesRealtimeQuoteState"),
        "executionGradeRealtimeProofPassed": execution_grade,
        "dataRequirementsDecision": requirements.get("decision", "unknown"),
        "dataRequirementsPassCount": requirements.get("passCount"),
        "dataRequirementsBlockedCount": requirements.get("blockedCount"),
        "nextOpenSessionProofWindow": next_window,
        "brokerFlat": broker.get("broker_flat"),
        "openPositions": broker.get("open_positions"),
        "account": redact_account(monitor.get("account_label")),
        "readyForFiveMinuteResearch": ready_research,
        "readyForExecutionData": execution_grade,
        "screenProofStatus": screen.get("status", "not-run"),
        "screenProofAgeSeconds": age_for_state("topstepx-dashboard-screen-proof.latest.json"),
        "sessionSafety": {
            "present": bool(session_safety),
            "pauseBrokerTouchingProofs": bool(session_safety.get("pauseBrokerTouchingProofs")),
            "reason": session_safety.get("reason", "missing"),
            "safeUntil": session_safety.get("safeUntil"),
            "lastMitigation": session_safety.get("lastMitigation"),
            "notesPath": session_safety.get("notesPath"),
            "ageSeconds": age_for_state("topstep-session-safety.latest.json"),
        },
        "sessionSafetyClearance": {
            "present": bool(session_clearance),
            "decision": session_clearance.get("decision", "missing"),
            "machineChecksPassed": bool(session_clearance.get("machineChecksPassed")),
            "operatorConfirmationRequired": bool(session_clearance.get("operatorConfirmationRequired", True)),
            "readyForReadOnlyProofWindow": bool(session_clearance.get("readyForReadOnlyProofWindow")),
            "blockers": first_list(session_clearance.get("blockers"), 5),
            "ageSeconds": age_for_state("topstep-session-safety-clearance.latest.json"),
        },
        "demoObservation": {
            "present": bool(demo_observation),
            "decision": demo_observation.get("decision", "missing"),
            "readyForHumanDemoObservation": bool(demo_observation.get("readyForHumanDemoObservation")),
            "readyForAlgoDemoExpansion": bool(demo_observation.get("readyForAlgoDemoExpansion")),
            "learningDecision": demo_learning.get("decision", "missing"),
            "learningStatus": demo_learning.get("learningStatus"),
            "learningIssueCount": int(demo_learning.get("issueCount") or 0),
            "learningIssues": first_list([
                item.get("id")
                for item in demo_learning.get("issues", [])
                if isinstance(item, dict)
            ], 5),
            "matchedTradeSize": (
                demo_learning.get("brokerReconciliation", {}).get("totalMatchedSize")
                if isinstance(demo_learning.get("brokerReconciliation"), dict) else None
            ),
            "estimatedPnlDollars": (
                demo_learning.get("brokerReconciliation", {}).get("estimatedPnlDollars")
                if isinstance(demo_learning.get("brokerReconciliation"), dict) else None
            ),
            "operatorReportedPnlDollars": (
                demo_observation.get("operatorDemoContext", {}).get("reportedPnlDollars")
                if isinstance(demo_observation.get("operatorDemoContext"), dict) else None
            ),
            "observationBlockers": first_list(demo_observation.get("observationBlockers"), 5),
            "algoExpansionBlockers": first_list(demo_observation.get("algoExpansionBlockers"), 5),
            "ageSeconds": age_for_state("topstep-demo-observation-posture.latest.json"),
        },
        "blockers": blockers,
        "safeCommands": [
            "BILL_ENABLE_FUTURES_DEMO_EXECUTION=false RH_TOPSTEP_READ_ONLY=true RH_LIVE_EXECUTION_ENABLED=false npm run --silent bill:topstep-session-safety-clearance",
            "BILL_ENABLE_FUTURES_DEMO_EXECUTION=false RH_TOPSTEP_READ_ONLY=true RH_LIVE_EXECUTION_ENABLED=false npm run --silent bill:topstep-market-data-smoke",
            "BILL_ENABLE_FUTURES_DEMO_EXECUTION=false RH_TOPSTEP_READ_ONLY=true RH_LIVE_EXECUTION_ENABLED=false npm run --silent bill:topstep-readonly-bar-archive",
            "BILL_ENABLE_FUTURES_DEMO_EXECUTION=false RH_TOPSTEP_READ_ONLY=true RH_LIVE_EXECUTION_ENABLED=false npm run --silent bill:topstep-broker-local-bar-parity",
            "BILL_ENABLE_FUTURES_DEMO_EXECUTION=false RH_TOPSTEP_READ_ONLY=true RH_LIVE_EXECUTION_ENABLED=false npm run --silent bill:topstep-realtime-proof",
            "npm run --silent bill:futures-data-requirements",
        ],
    }

def get_risk_plane():
    """Portfolio, source, and execution evidence gates."""
    monitor, _ = state_json("topstep-100k-monitor.latest.json")
    goal, _ = state_json("bill-goal-completion-audit.latest.json")
    source, _ = state_json("bill-source-intake-manifest.latest.json")
    worktree, _ = state_json("worktree-consolidation.latest.json")
    execution, _ = state_json("bill-execution-intake-manifest.latest.json")
    live, _ = state_json("live-readiness.latest.json")
    cron, _ = state_json("cron-state-validator.latest.json")
    automation, _ = state_json("codex-automation-audit.latest.json")
    monitor = monitor if isinstance(monitor, dict) else {}
    goal = goal if isinstance(goal, dict) else {}
    source = source if isinstance(source, dict) else {}
    worktree = worktree if isinstance(worktree, dict) else {}
    execution = execution if isinstance(execution, dict) else {}
    live = live if isinstance(live, dict) else {}
    cron = cron if isinstance(cron, dict) else {}
    automation = automation if isinstance(automation, dict) else {}
    live_report = live.get("final", {}).get("report", {}) if isinstance(live.get("final"), dict) else {}
    broker = monitor.get("broker_reconciliation", {}) if isinstance(monitor.get("broker_reconciliation"), dict) else {}
    canonical = worktree.get("canonicalSource", {}) if isinstance(worktree.get("canonicalSource"), dict) else {}
    dirty_siblings = worktree.get("dirtySiblingWorktrees", {}) if isinstance(worktree.get("dirtySiblingWorktrees"), dict) else {}
    source_clean_blockers = worktree.get("sourceCleanBlockers") if isinstance(worktree.get("sourceCleanBlockers"), list) else []
    canonical_dirty_files = int(canonical.get("dirtyFiles") or source.get("dirtyStatusCount") or 0)
    execution_live_dirty = int(
        source.get("executionLiveDirtyCount")
        or source.get("canonicalExecutionLiveDirtyCount")
        or 0
    )
    canonical_source_clean = bool(source.get("sourceClean")) and canonical_dirty_files == 0 and execution_live_dirty == 0
    return {
        "topstep": {
            "status": monitor.get("status", "unknown"),
            "account": redact_account(monitor.get("account_label")),
            "hardBlockers": monitor.get("hard_blockers", []),
            "warnings": monitor.get("warnings", []),
            "brokerFlat": broker.get("broker_flat"),
            "openPositions": broker.get("open_positions"),
        },
        "goal": {
            "decision": goal.get("decision", "unknown"),
            "passCount": goal.get("passCount"),
            "checkCount": goal.get("checkCount"),
            "blockedIds": goal.get("blockedIds", [])[:8],
            "readyForExecution": goal.get("readyForExecution", False),
        },
        "source": {
            "decision": source.get("decision", "unknown"),
            "classificationCounts": source.get("classificationCounts", {}),
            "reviewBacklogCount": source.get("reviewBacklogCount"),
            "sourceClean": source.get("sourceClean", False),
            "canonicalSourceClean": canonical_source_clean,
            "canonicalDirtyFiles": canonical_dirty_files,
            "sourceCleanBlockers": source_clean_blockers,
            "siblingQuarantineCount": int(dirty_siblings.get("count") or 0),
            "sourceIntakeVisible": source.get("sourceIntakeVisible", False),
            "executionLiveDirtyCount": execution_live_dirty,
            "readyForExecution": source.get("readyForExecution", False),
        },
        "execution": {
            "decision": execution.get("decision", "unknown"),
            "locked": execution.get("executionLocked", True),
            "firewallEvidenceStatus": execution.get("firewallEvidenceStatus", "unknown"),
            "dirtyExecutionFileCount": execution.get("dirtyExecutionFileCount"),
            "writesOrders": execution.get("writesOrders", False),
            "touchesBroker": execution.get("touchesBroker", False),
            "movesFunds": execution.get("movesFunds", False),
        },
        "liveReadiness": {
            "status": live_report.get("status", "unknown"),
            "survivabilityScore": live_report.get("survivabilityScore", 0),
            "profitableNow": live_report.get("profitableNow", False),
            "deployableNow": live_report.get("deployableNow", False),
            "failedChecks": live_report.get("failedChecks", [])[:6],
        },
        "automation": {
            "decision": automation.get("decision", "unknown"),
            "activeBillAutomationCount": automation.get("activeBillAutomationCount", 0),
            "blockers": automation.get("blockers", [])[:6],
        },
        "cron": {
            "summary": cron.get("summary", "unknown"),
            "cronTrustCleared": cron.get("cronTrustCleared", False),
            "diagnosticIssueCount": cron.get("diagnosticIssueCount", 0),
        },
    }

def get_signal_quality_plane():
    """Deterministic signal-quality evidence; advisory only, never execution authority."""
    quality, _ = state_json("signal-quality-advisor.latest.json")
    source_truth, _ = state_json("signal-source-truth-audit.latest.json")
    arbitration, _ = state_json("arbitration.latest.json")
    brain, _ = state_json("brain-state.latest.json")
    quality = quality if isinstance(quality, dict) else {}
    source_truth = source_truth if isinstance(source_truth, dict) else {}
    arbitration = arbitration if isinstance(arbitration, dict) else {}
    brain = brain if isinstance(brain, dict) else {}
    blockers = quality.get("blockers") if isinstance(quality.get("blockers"), list) else []
    warnings = quality.get("warnings") if isinstance(quality.get("warnings"), list) else []
    shadow_rows = quality.get("shadowSignalRows") if isinstance(quality.get("shadowSignalRows"), list) else []
    stale_shadow_rows = (
        quality.get("staleShadowSourceRows")
        if isinstance(quality.get("staleShadowSourceRows"), list)
        else []
    )
    issues = source_truth.get("issues") if isinstance(source_truth.get("issues"), list) else []
    promoted_issues = [
        issue for issue in issues
        if isinstance(issue, dict) and issue.get("issue") == "research-or-advisory-source-promoted"
    ]
    safe_visible = (
        quality.get("command") == "signal-quality-advisor"
        and quality.get("researchOnly") is True
        and quality.get("writesOrders") is False
        and quality.get("touchesBroker") is False
        and quality.get("readyForExecution") is False
        and blockers == []
        and promoted_issues == []
        and source_truth.get("command") == "signal-source-truth-audit"
        and source_truth.get("writesOrders") is False
        and source_truth.get("touchesBroker") is False
        and source_truth.get("readyForExecution") is False
    )
    return {
        "decision": quality.get("decision", "unknown"),
        "rating": quality.get("overallRating"),
        "scoreParts": quality.get("scoreParts", {}),
        "blockers": blockers,
        "warnings": warnings[:8],
        "warningCount": len(warnings),
        "shadowSignalCount": len(shadow_rows),
        "staleShadowSignalCount": len(stale_shadow_rows),
        "sourceTruthIssueCount": source_truth.get("issueCount", len(issues)),
        "promotedSourceIssueCount": len(promoted_issues),
        "safeVisible": safe_visible,
        "readyForExecution": False,
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "movesFunds": False,
        "arbitration": {
            "decision": arbitration.get("decision"),
            "direction": arbitration.get("direction"),
            "conviction": arbitration.get("conviction"),
            "activeSignals": arbitration.get("active_signals"),
            "totalSignals": arbitration.get("total_signals"),
            "weightedDir": arbitration.get("weighted_dir"),
        },
        "brain": {
            "fusedDirection": brain.get("fused_direction"),
            "activeSignals": brain.get("active_signals"),
            "topSignals": brain.get("top_signals", [])[:3] if isinstance(brain.get("top_signals"), list) else [],
            "readyForExecution": brain.get("readyForExecution", False),
        },
        "freshness": {
            "quality": freshness_for_state("signal-quality-advisor.latest.json", 2 * 3600),
            "sourceTruth": freshness_for_state("signal-source-truth-audit.latest.json", 2 * 3600),
            "arbitration": freshness_for_state("arbitration.latest.json", 2 * 3600),
        },
    }

def get_prediction_paper_plane():
    """Prediction-market paper-promotion state; research-only and no funding/order authority."""
    gate, _ = state_json("prediction-event-paper-promotion-gate.latest.json")
    triage, _ = state_json("prediction-evidence-triage.latest.json")
    capture, _ = state_json("prediction-event-capture-cycle.latest.json")
    manual, _ = state_json("prediction-event-lag-manual-review.latest.json")
    gate = gate if isinstance(gate, dict) else {}
    triage = triage if isinstance(triage, dict) else {}
    capture = capture if isinstance(capture, dict) else {}
    manual = manual if isinstance(manual, dict) else {}
    checklist = gate.get("checklist") if isinstance(gate.get("checklist"), list) else []
    pass_count = int(gate.get("passCount") or sum(1 for row in checklist if isinstance(row, dict) and row.get("status") == "pass"))
    blocked_count = int(gate.get("blockedCount") or sum(1 for row in checklist if isinstance(row, dict) and row.get("status") != "pass"))
    next_tests = triage.get("nextTests") if isinstance(triage.get("nextTests"), list) else []
    next_test = next_tests[0] if next_tests and isinstance(next_tests[0], dict) else {}
    event_forward = triage.get("eventForwardCapture") if isinstance(triage.get("eventForwardCapture"), dict) else {}
    latest_recorder = capture.get("latestRecorder") if isinstance(capture.get("latestRecorder"), dict) else {}
    live_quality = latest_recorder.get("liveQualityDiagnostics") if isinstance(latest_recorder.get("liveQualityDiagnostics"), dict) else {}
    safety_ok = (
        gate.get("researchOnly") is True
        and gate.get("writesOrders") is False
        and gate.get("touchesBroker") is False
        and gate.get("movesFunds") is False
        and triage.get("researchOnly") is True
        and triage.get("writesOrders") is False
        and triage.get("touchesBroker") is False
        and capture.get("researchOnly") is True
        and capture.get("writesOrders") is False
        and capture.get("touchesBroker") is False
    )
    ranked_blockers = [
        {
            "id": row.get("id"),
            "status": row.get("status"),
            "blocker": row.get("blocker"),
            "requirement": row.get("requirement"),
            "evidence": row.get("evidence") if isinstance(row.get("evidence"), dict) else {},
        }
        for row in checklist
        if isinstance(row, dict) and row.get("status") != "pass"
    ]
    return {
        "decision": gate.get("decision", "unknown"),
        "readyForPaper": gate.get("readyForPaper", False),
        "readyForPaperReview": gate.get("readyForPaperReview", False),
        "readyForExecution": False,
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "movesFunds": False,
        "safetyOk": safety_ok,
        "passCount": pass_count,
        "blockedCount": blocked_count,
        "blockedIds": gate.get("blockedIds", []),
        "rankedBlockers": ranked_blockers[:8],
        "operatorRead": gate.get("operatorRead"),
        "nextAction": gate.get("nextAction"),
        "nextTest": {
            "id": next_test.get("id"),
            "track": next_test.get("track"),
            "oneVariable": next_test.get("oneVariable"),
            "commandHint": next_test.get("commandHint"),
            "blockedBy": next_test.get("blockedBy", []) if isinstance(next_test.get("blockedBy"), list) else [],
            "promotionRule": next_test.get("promotionRule"),
        },
        "forwardCapture": {
            "decision": event_forward.get("cycleDecision") or capture.get("decision"),
            "forwardCaptureRequired": event_forward.get("forwardCaptureRequired", capture.get("forwardRequired")),
            "standingRecorderCommand": event_forward.get("standingRecorderCommand"),
            "reviewLeadRecorderCommand": event_forward.get("reviewLeadRecorderCommand"),
            "fillableLiveBookCount": live_quality.get("fillableLiveBookCount"),
            "completeWindowCount": capture.get("completeWindowCount"),
            "repricedWindowCount": capture.get("repricedWindowCount"),
            "publicCaptureReviewLeadCount": event_forward.get("publicCaptureReviewLeadCount"),
            "eventLagResearchWatchReady": event_forward.get("eventLagResearchWatchReady", capture.get("eventLagResearchWatchReady")),
            "eventLagReplayWatchReady": event_forward.get("eventLagReplayWatchReady", capture.get("eventLagReplayWatchReady")),
        },
        "manualReview": {
            "decision": manual.get("decision"),
            "decisionCounts": manual.get("decisionCounts", {}),
            "forwardCaptureEvidencePresent": manual.get("forwardCaptureEvidencePresent"),
            "blockers": manual.get("blockers", []) if isinstance(manual.get("blockers"), list) else [],
        },
        "freshness": {
            "gate": freshness_for_state("prediction-event-paper-promotion-gate.latest.json", 6 * 3600),
            "triage": freshness_for_state("prediction-evidence-triage.latest.json", 6 * 3600),
            "capture": freshness_for_state("prediction-event-capture-cycle.latest.json", 6 * 3600),
        },
    }

def get_agent_governance():
    """Agentic-AI controls: permissions, HITL, and auditability."""
    audit, _ = state_json("bill-runtime-architecture-audit.latest.json")
    control = get_control_plane()
    n8n = get_n8n_status()
    audit = audit if isinstance(audit, dict) else {}
    kanban = audit.get("hermesKanban", {}) if isinstance(audit.get("hermesKanban"), dict) else {}
    cron = audit.get("hermesCron", {}) if isinstance(audit.get("hermesCron"), dict) else {}
    return {
        "humanInLoop": True,
        "dailyPlanRequired": True,
        "executionAuthority": False,
        "agentMayWriteOrders": control.get("writesOrders", False),
        "agentMayTouchBroker": control.get("touchesBroker", False),
        "agentMayMoveFunds": control.get("movesFunds", False),
        "n8nRole": n8n.get("role"),
        "n8nActiveBillWorkflows": n8n.get("activeBillWorkflowCount", 0),
        "kanban": {
            "blockedRelevant": len(kanban.get("blockedRelevantTasks", []) or []),
            "activeRelevant": len(kanban.get("activeRelevantTasks", []) or []),
            "triaged": kanban.get("blockedTaskTriage", {}).get("allBlockedRelevantTasksTriaged", False),
        },
        "cronExecutionLike": {
            "activeCount": cron.get("activeExecutionLikeCount", 0),
            "operatorRead": cron.get("operatorRead", ""),
        },
        "operatorActions": audit.get("operatorActions", [])[:5],
    }

def get_strategy_validation_summary():
    """Current strategy-validation truth for gate displays."""
    status, _ = state_json("strategy-test-framework-status.latest.json")
    status = status if isinstance(status, dict) else {}
    live, _ = state_json("live-readiness.latest.json")
    live = live if isinstance(live, dict) else {}
    live_report = live.get("final", {}).get("report", {}) if isinstance(live.get("final"), dict) else {}
    matrix = status.get("walkforwardMatrix") if isinstance(status.get("walkforwardMatrix"), dict) else {}
    factory = status.get("strategyFactory") if isinstance(status.get("strategyFactory"), dict) else {}
    one_var = status.get("oneVariableResearch") if isinstance(status.get("oneVariableResearch"), dict) else {}
    result_summary = one_var.get("resultSummary") if isinstance(one_var.get("resultSummary"), dict) else {}
    best = result_summary.get("bestObserved") if isinstance(result_summary.get("bestObserved"), dict) else {}
    blocked_ids = first_list(status.get("blockedIds"), 6)

    framework_present = bool(status)
    deployable = (
        framework_present
        and not blocked_ids
        and matrix.get("status") == "robust-candidate"
        and factory.get("walkforwardDeployable") is True
        and best.get("researchCandidate") is True
    )
    if framework_present:
        evidence = (
            f"framework={status.get('decision', 'unknown')}, "
            f"matrix={matrix.get('status', 'missing')}, "
            f"factory={factory.get('status') or factory.get('decision') or 'missing'}, "
            f"bestCandidate={best.get('researchCandidate', False)}"
        )
    else:
        deployable = bool(live_report.get("deployableNow"))
        evidence = (
            f"liveReadiness={live_report.get('status', 'unknown')}, "
            f"survivability={live_report.get('survivabilityScore', 0)}"
        )

    return {
        "deployable": deployable,
        "evidence": evidence,
        "blockedIds": blocked_ids,
        "decision": status.get("decision") or live_report.get("status", "unknown"),
        "matrixStatus": matrix.get("status"),
        "factoryStatus": factory.get("status") or factory.get("decision"),
        "bestObserved": best,
    }

def get_institutional_benchmark():
    """Research-backed checklist for a founder/PM/CTO command center."""
    control = get_control_plane()
    data = get_market_data_plane()
    topstep = data.get("topstep", {})
    risk = get_risk_plane()
    goal = get_goal_audit()
    n8n = get_n8n_status()
    daily = parse_daily_control()
    strategy = get_strategy_validation_summary()
    source = risk.get("source", {}) if isinstance(risk.get("source"), dict) else {}
    goal_blocked = set(goal.get("blockedIds") or [])
    source_artifact_ok = bool(source.get("canonicalSourceClean")) and int(source.get("executionLiveDirtyCount") or 0) == 0
    source_hygiene_ok = source_artifact_ok and "source-hygiene-not-cleared" not in goal_blocked
    broker_grade_data_ok = bool(data.get("brokerGradeDataProofPassed") or data.get("readyForExecutionData"))
    data_evidence = (
        f"{data.get('brokerGradeDataProofSource', data.get('quote', {}).get('source'))} / "
        f"topstepRealtime={data.get('topstepRealtimeProofPassed')}, "
        f"executionGradeProof={data.get('topstepExecutionGradeRealtimeProofPassed')}, "
        f"quoteFreshness={data.get('freshness', {}).get('verdict')}"
    )
    items = [
        {
            "id": "human-approval",
            "label": "Human route approval",
            "status": "blocked" if daily.get("routeApproval") == "BLOCKED" else "review",
            "evidence": f"Daily plan route={daily.get('routeApproval')}, broker={daily.get('brokerReconciliation')}",
        },
        {
            "id": "pre-trade-risk",
            "label": "Pre-trade risk firewall",
            "status": "pass" if control.get("researchOnly") and not control.get("writesOrders") else "review",
            "evidence": "LLMs/n8n have no execution authority; deterministic gates remain locked.",
        },
        {
            "id": "market-data-provenance",
            "label": "Execution-grade market data",
            "status": "pass" if broker_grade_data_ok else "blocked",
            "evidence": data_evidence,
        },
        {
            "id": "topstep-data-path",
            "label": "TopstepX broker data path",
            "status": "pass" if topstep.get("readyForFiveMinuteResearch") else "blocked",
            "evidence": f"bars={topstep.get('currentBarsProofPassed')}, parity={topstep.get('brokerParityPassed')}, sessions={topstep.get('archiveRthSessions')}",
        },
        {
            "id": "broker-reconciliation",
            "label": "Broker reconciliation",
            "status": "pass" if risk.get("topstep", {}).get("brokerFlat") and daily.get("brokerReconciliation") == "GREEN" else "review",
            "evidence": f"brokerFlat={risk.get('topstep', {}).get('brokerFlat')}, daily={daily.get('brokerReconciliation')}",
        },
        {
            "id": "model-validation",
            "label": "Model / strategy validation",
            "status": "pass" if strategy.get("deployable") else "blocked",
            "evidence": strategy.get("evidence"),
        },
        {
            "id": "source-hygiene",
            "label": "Source and change hygiene",
            "status": "pass" if source_hygiene_ok else "blocked",
            "evidence": (
                f"canonicalClean={source.get('canonicalSourceClean')}, "
                f"execution/live dirty={source.get('executionLiveDirtyCount')}, "
                f"sibling quarantine={source.get('siblingQuarantineCount', 0)}, "
                f"goalBlocked={'source-hygiene-not-cleared' in goal_blocked}"
            ),
        },
        {
            "id": "observability",
            "label": "Automation observability",
            "status": "pass" if n8n.get("source") == "postgres" and n8n.get("running") else "review",
            "evidence": f"n8n={n8n.get('source')}, workflows={n8n.get('activeCount')}/{n8n.get('workflowCount')}",
        },
        {
            "id": "agent-governance",
            "label": "Agent permissions and audit",
            "status": "pass" if control.get("researchOnly") and not control.get("movesFunds") else "review",
            "evidence": "Research-only agent posture with operator actions exposed.",
        },
    ]
    score = sum(1 for x in items if x["status"] == "pass")
    blocked_items = [x for x in items if x.get("status") == "blocked"]
    review_items = [x for x in items if x.get("status") not in ("pass", "blocked")]
    status_counts = {
        "pass": score,
        "blocked": len(blocked_items),
        "review": len(review_items),
    }
    return {
        "score": score,
        "passed": score,
        "passCount": score,
        "blockedCount": len(blocked_items),
        "blockerCount": len(blocked_items),
        "reviewCount": len(review_items),
        "openIssueCount": len(blocked_items) + len(review_items),
        "statusCounts": status_counts,
        "total": len(items),
        "blockers": blocked_items,
        "reviewItems": review_items,
        "items": items,
        "sources": [
            {"label": "SEC Rule 15c3-5 market access controls", "url": "https://www.sec.gov/rules-regulations/2011/06/risk-management-controls-brokers-or-dealers-market-access"},
            {"label": "CFTC automated trading risk controls and system safeguards", "url": "https://www.cftc.gov/PressRoom/PressReleases/6683-13"},
            {"label": "CME Globex Credit Controls and Kill Switch", "url": "https://www.cmegroup.com/tools-information/webhelp/globex-credit-controls/Content/Home.html"},
            {"label": "NIST AI Risk Management Framework", "url": "https://www.nist.gov/itl/ai-risk-management-framework"},
            {"label": "NIST Cybersecurity Framework 2.0", "url": "https://www.nist.gov/cyberframework"},
            {"label": "Federal Reserve SR 11-7 model risk management", "url": "https://www.federalreserve.gov/supervisionreg/srletters/sr1107.htm"},
            {"label": "Grafana dashboard best practices and runbook links", "url": "https://grafana.com/docs/grafana/latest/visualizations/dashboards/build-dashboards/best-practices/"},
            {"label": "OWASP Agentic Skills Top 10", "url": "https://owasp.org/www-project-agentic-skills-top-10/"},
            {"label": "TradingView webhook alert requirements", "url": "https://www.tradingview.com/support/solutions/43000529348-how-to-configure-webhook-alerts/"},
            {"label": "TopstepX API Access", "url": "https://help.topstep.com/en/articles/11187768-topstepx-api-access"},
            {"label": "ProjectX market data retrieve bars", "url": "https://gateway.docs.projectx.com/docs/api-reference/market-data/retrieve-bars/"},
            {"label": "ProjectX realtime SignalR overview", "url": "https://gateway.docs.projectx.com/docs/realtime/"},
            {"label": "Databento live data API docs", "url": "https://databento.com/docs/api-reference-live"},
        ],
    }

def first_list(value, limit=5):
    return value[:limit] if isinstance(value, list) else []

def get_source_clearance_runway(source_plan):
    source_plan = source_plan if isinstance(source_plan, dict) else {}
    canonical = source_plan.get("sourceClearanceRunway")
    bundles = canonical if isinstance(canonical, list) else source_plan.get("bundles")
    bundles = bundles if isinstance(bundles, list) else []
    runway = []
    for item in bundles[:8]:
        if not isinstance(item, dict):
            continue
        commands = item.get("evidenceCommands") or item.get("commands")
        commands = commands if isinstance(commands, list) else []
        blockers = item.get("blockers") if isinstance(item.get("blockers"), list) else []
        samples = item.get("samplePaths") if isinstance(item.get("samplePaths"), list) else []
        runway.append({
            "id": item.get("bundleId") or item.get("id"),
            "title": item.get("title") or item.get("bundleId") or item.get("id"),
            "count": item.get("count", 0),
            "status": item.get("decision") or "review",
            "safe": not item.get("writesOrders") and not item.get("touchesBroker") and not item.get("movesFunds"),
            "firstCommand": item.get("firstEvidenceCommand") or (commands[0] if commands else None),
            "samplePaths": samples[:4],
            "blockers": blockers[:3],
            "clearanceRule": item.get("clearanceRule") or "manual review + named verification evidence; no auto staging, deletion, routing, or funding",
        })
    return {
        "decision": source_plan.get("decision", "missing"),
        "dirtyStatusCount": source_plan.get("dirtyStatusCount"),
        "automaticCleanupAllowed": source_plan.get("automaticCleanupAllowed", False),
        "safeAutoStage": source_plan.get("safeAutoStage", False),
        "runway": runway,
        "hardRules": first_list(source_plan.get("hardRules"), 5),
    }

def get_blocker_actions():
    """Actionable blocker queue for founder/operator review; never route approval."""
    goal, _ = state_json("bill-goal-completion-audit.latest.json")
    source_plan, _ = state_json("bill-source-hygiene-plan.latest.json")
    runtime, _ = state_json("bill-runtime-architecture-audit.latest.json")
    next_actions, _ = state_json("bill-next-research-actions.latest.json")
    futures_req, _ = state_json("futures-data-requirements.latest.json")
    prediction_gate, _ = state_json("prediction-event-paper-promotion-gate.latest.json")
    fund_os, _ = state_json("bill-fund-os-completion-audit.latest.json")
    alpha_watch, _ = state_json("current-alpha-watch.latest.json")
    source_plan = source_plan if isinstance(source_plan, dict) else {}
    runtime = runtime if isinstance(runtime, dict) else {}
    next_actions = next_actions if isinstance(next_actions, dict) else {}
    goal = goal if isinstance(goal, dict) else {}
    futures_req = futures_req if isinstance(futures_req, dict) else {}
    prediction_gate = prediction_gate if isinstance(prediction_gate, dict) else {}
    fund_os = fund_os if isinstance(fund_os, dict) else {}
    alpha_watch = alpha_watch if isinstance(alpha_watch, dict) else {}
    topstep = get_topstep_data_plane()
    topstep_session_safety = topstep.get("sessionSafety") if isinstance(topstep.get("sessionSafety"), dict) else {}
    topstep_broker_touch_paused = bool(topstep_session_safety.get("pauseBrokerTouchingProofs"))
    prediction_gate_freshness = freshness_for_state("prediction-event-paper-promotion-gate.latest.json")
    prediction_blocked_ids = first_list(prediction_gate.get("blockedIds"), 4)

    source_bundles = first_list(source_plan.get("bundles"), 4)
    source_queue = [
        {
            "id": item.get("id"),
            "title": item.get("title") or item.get("id"),
            "count": item.get("count"),
            "lane": "source-hygiene",
            "status": "review",
            "safe": not item.get("writesOrders") and not item.get("touchesBroker") and not item.get("movesFunds"),
            "command": first_list(item.get("commands"), 1)[0] if first_list(item.get("commands"), 1) else None,
            "why": item.get("action"),
        }
        for item in source_bundles
        if isinstance(item, dict)
    ]

    research_actions = [
        {
            "id": item.get("id"),
            "title": item.get("id"),
            "lane": item.get("lane", "research"),
            "status": "research-only",
            "safe": not item.get("writesOrders") and not item.get("touchesBroker"),
            "command": item.get("firstCommand") or item.get("command"),
            "why": item.get("oneVariable") or "Next queued one-variable/control-plane action",
        }
        for item in first_list(next_actions.get("nextActions"), 5)
        if isinstance(item, dict)
    ]

    worktree, _ = state_json("worktree-consolidation.latest.json")
    source_intake, _ = state_json("bill-source-intake-manifest.latest.json")
    worktree = worktree if isinstance(worktree, dict) else {}
    source_intake = source_intake if isinstance(source_intake, dict) else {}
    source_blockers = worktree.get("sourceCleanBlockers") if isinstance(worktree.get("sourceCleanBlockers"), list) else []
    canonical_source_clean = bool(source_intake.get("sourceClean")) and int(
        (worktree.get("canonicalSource") or {}).get("dirtyFiles") or source_intake.get("dirtyStatusCount") or 0
    ) == 0
    source_hygiene_goal_blocked = "source-hygiene-not-cleared" in goal.get("blockedIds", [])
    source_hygiene_action_title = (
        "Confirm source hygiene stays clean"
        if canonical_source_clean and not source_hygiene_goal_blocked
        else "Resolve sibling source quarantine"
        if canonical_source_clean
        else "Reduce source hygiene backlog"
    )
    source_hygiene_action_why = (
        "Canonical source clean; sibling quarantine clear; no source blockers."
        if canonical_source_clean and not source_hygiene_goal_blocked
        else f"Canonical source clean; remaining blockers: {', '.join(source_blockers) or 'none'}."
        if canonical_source_clean
        else f"{source_plan.get('dirtyStatusCount', 'unknown')} dirty status rows; no auto staging."
    )

    priority = [
        *([
            {
                "id": "topstep-session-safety",
                "title": "Clear TopstepX session-safety pause",
                "lane": "futures",
                "status": "blocked",
                "safe": True,
                "command": "BILL_ENABLE_FUTURES_DEMO_EXECUTION=false RH_TOPSTEP_READ_ONLY=true RH_LIVE_EXECUTION_ENABLED=false npm run --silent bill:topstep-session-safety-clearance",
                "why": (
                    "Topstep broker-touching read-only proofs are paused after a multiple-session warning. "
                    "Build the clearance checklist, close extra ProjectX/TopstepX sessions manually, then refresh session safety before any broker data loop."
                ),
            }
        ] if topstep_broker_touch_paused else []),
        {
            "id": "topstep-archive-depth",
            "title": "Accumulate TopstepX read-only archive depth",
            "lane": "futures",
            "status": "paused" if topstep_broker_touch_paused else ("blocked" if "topstep-readonly-archive-depth-thin" in topstep.get("blockers", []) else "pass"),
            "safe": not topstep_broker_touch_paused,
            "command": first_list(topstep.get("safeCommands"), 2)[1] if len(first_list(topstep.get("safeCommands"), 2)) > 1 else None,
            "why": (
                "Paused by Topstep session safety; do not reopen broker-touching data loops until the warning is cleared."
                if topstep_broker_touch_paused
                else f"{topstep.get('archiveRthSessions', 0)} RTH sessions captured; keep building broker-relevant 5m+ evidence."
            ),
        },
        {
            "id": "n8n-active-bill-workflow-review",
            "title": "Review active Bill/Hermes n8n workflows",
            "lane": "orchestration",
            "status": "review" if runtime.get("warnings") else "pass",
            "safe": True,
            "command": "npm run --silent bill:runtime-architecture-audit",
            "why": "; ".join(first_list(runtime.get("warnings"), 2)) or "n8n is visible and research-only.",
        },
        {
            "id": "prediction-paper-promotion",
            "title": "Clear prediction paper-promotion evidence",
            "lane": "prediction",
            "status": "blocked" if not prediction_gate.get("readyForPaper") else "pass",
            "safe": True,
            "command": "npm run --silent bill:prediction-event-paper-promotion-gate",
            "nextCommand": "npm run --silent bill:prediction-evidence-triage",
            "freshness": prediction_gate_freshness,
            "why": (
                f"Gate {prediction_gate_freshness['status']} ({age_label(prediction_gate_freshness['ageSeconds'])}); "
                f"blocked: {', '.join(prediction_blocked_ids) or 'none'}"
            ),
        },
        {
            "id": "source-hygiene",
            "title": source_hygiene_action_title,
            "lane": "source-hygiene",
            "status": (
                "review" if canonical_source_clean and source_hygiene_goal_blocked
                else "blocked" if source_hygiene_goal_blocked
                else "pass"
            ),
            "safe": True,
            "command": "npm run --silent bill:sibling-worktree-intake" if canonical_source_clean else "npm run --silent bill:source-hygiene-plan",
            "why": source_hygiene_action_why,
        },
        {
            "id": "futures-demo-expansion",
            "title": "Futures demo expansion gate",
            "lane": "futures",
            "status": "blocked" if not futures_req.get("readyForDemoExpansion") else "pass",
            "safe": True,
            "command": "npm run --silent bill:futures-data-requirements",
            "why": f"Data req pass={futures_req.get('passCount')}, blocked={futures_req.get('blockedCount')}.",
        },
    ]
    priority = sorted(
        priority,
        key=lambda item: (
            {"blocked": 0, "paused": 1, "review": 2, "research-only": 3, "pass": 4}.get(item.get("status"), 2),
            0 if item.get("id") == "topstep-archive-depth" else 1,
        ),
    )

    capital_phases = [
        {"id": "l0", "label": "Research-only control plane", "status": "pass", "why": "Execution locked; evidence visible."},
        {"id": "l1", "label": "Topstep demo calibration", "status": "blocked" if "futures-demo-not-cleared" in goal.get("blockedIds", []) else "review", "why": "Needs broker-grade depth, model validation, and goal audit clearance."},
        {"id": "l2", "label": "Prediction paper", "status": "blocked" if "prediction-paper-not-cleared" in goal.get("blockedIds", []) else "review", "why": "Needs fillable forward capture, labels, and manual review."},
        {"id": "l3", "label": "Challenge/live trading", "status": "locked", "why": "Only after demo/paper gates and broker reconciliation are green."},
        {"id": "l4", "label": "Compound payouts", "status": "locked", "why": "Compound only from realized payouts, not forecast P&L."},
    ]
    capital_cockpit = {
        "mode": "L0_RESEARCH_CONTROL_PLANE",
        "capitalAtRisk": "ZERO_NEW_RISK",
        "northStar": "Compound only from verified realized payouts after evidence gates clear.",
        "nextCapitalMilestone": next((item for item in priority if item.get("status") == "blocked" and item.get("safe")), {}),
        "killSwitches": [
            {
                "id": "daily-route-approval",
                "status": "armed" if "futures-demo-not-cleared" in goal.get("blockedIds", []) else "watch",
                "why": "Daily plan must explicitly approve any route.",
            },
            {
                "id": "source-hygiene",
                "status": "review" if canonical_source_clean and "source-hygiene-not-cleared" in goal.get("blockedIds", []) else "armed" if "source-hygiene-not-cleared" in goal.get("blockedIds", []) else "watch",
                "why": "Canonical source is clean; sibling worktree remains quarantine/selective-intake." if canonical_source_clean else "Dirty execution/live source blocks promotion.",
            },
            {
                "id": "prediction-paper-gate",
                "status": "armed" if "prediction-paper-not-cleared" in goal.get("blockedIds", []) else "watch",
                "why": "Prediction markets remain paper-blocked until evidence clears.",
            },
            {
                "id": "topstep-session-safety",
                "status": "armed" if topstep_broker_touch_paused else "watch",
                "why": "Broker-touching read-only proofs stay paused while the Topstep warning is active.",
            },
        ],
        "allocationLadder": [
            {"id": "topstep-demo", "label": "Topstep demo", "status": "blocked", "budgetRule": "0 new risk until gates clear"},
            {"id": "prop-payout-defense", "label": "Prop payout defense", "status": "locked", "budgetRule": "realized payout only"},
            {"id": "prediction-paper", "label": "Prediction paper", "status": "blocked", "budgetRule": "paper fills first"},
            {"id": "options-brokerage-crypto", "label": "Options / brokerage / crypto", "status": "locked", "budgetRule": "separate risk budget after durable evidence"},
        ],
    }

    return {
        "decision": goal.get("decision", "continue-research-only-locked"),
        "readyForExecution": False,
        "blockedIds": first_list(goal.get("blockedIds"), 8),
        "priority": priority,
        "capitalCockpit": capital_cockpit,
        "sourceQueue": source_queue,
        "sourceClearanceRunway": get_source_clearance_runway(source_plan),
        "researchQueue": research_actions,
        "capitalPhases": capital_phases,
        "compoundingRule": "Preserve capital until gates clear; no-trade days are valid. Compound only after realized payout/reconciliation evidence.",
        "alphaDirection": {
            "decision": alpha_watch.get("decision", "unknown"),
            "continue": first_list(alpha_watch.get("continue"), 5),
            "retire": first_list(alpha_watch.get("retire"), 5),
            "readyForExecution": alpha_watch.get("readyForExecution", False),
        },
        "fundOs": {
            "overallStatus": fund_os.get("overallStatus"),
            "tradingReadinessStatus": fund_os.get("tradingReadinessStatus"),
            "warnings": first_list(fund_os.get("warnings"), 5),
        },
    }

def automation_row(audit, automation_id):
    audit = audit if isinstance(audit, dict) else {}
    automations = audit.get("automations") if isinstance(audit.get("automations"), list) else []
    for item in automations:
        if isinstance(item, dict) and item.get("id") == automation_id:
            return item
    return {}

def summarize_automation(audit, automation_id, label):
    item = automation_row(audit, automation_id)
    active = bool(item.get("active"))
    safe = (
        bool(item.get("forbidsExecution"))
        and bool(item.get("hasSafeLocks"))
        and not item.get("writesOrders")
        and not item.get("touchesBroker")
        and not item.get("movesFunds")
    )
    return {
        "id": automation_id,
        "label": label,
        "status": item.get("status", "missing"),
        "active": active,
        "safe": safe,
        "rrule": item.get("rrule"),
        "writesOrders": bool(item.get("writesOrders")),
        "touchesBroker": bool(item.get("touchesBroker")),
        "movesFunds": bool(item.get("movesFunds")),
        "readyForExecution": bool(item.get("readyForExecution")),
        "operatorRead": "Active and safe-lock checked." if active and safe else "Review automation config before relying on this loop.",
    }

def get_founder_daily_brief():
    """Daily founder brief: premarket, dreaming, feeds, and next safe command."""
    daily = parse_daily_control()
    premarket, _ = state_json("premarket-risk-brief.latest.json")
    automation, _ = state_json("codex-automation-audit.latest.json")
    feeds, _ = state_json("free-data-feed-audit.latest.json")
    demo_observation, _ = state_json("topstep-demo-observation-posture.latest.json")
    demo_learning, _ = state_json("topstep-daily-learning.latest.json")
    goal = get_goal_audit()
    actions = get_blocker_actions()
    premarket = premarket if isinstance(premarket, dict) else {}
    automation = automation if isinstance(automation, dict) else {}
    feeds = feeds if isinstance(feeds, dict) else {}
    demo_observation = demo_observation if isinstance(demo_observation, dict) else {}
    demo_learning = demo_learning if isinstance(demo_learning, dict) else {}

    next_safe = next((item for item in actions.get("priority", []) if item.get("safe")), None)
    feed_summary = feeds.get("summary") if isinstance(feeds.get("summary"), dict) else {}
    hard_risks = [
        item for item in premarket.get("risks", [])
        if isinstance(item, dict) and item.get("severity") == "hard"
    ]
    watch_items = [
        item for item in premarket.get("risks", [])
        if isinstance(item, dict) and item.get("severity") in {"watch", "reduce"}
    ]
    loops = [
        summarize_automation(automation, "bill-premarket-risk-brief", "Premarket risk brief"),
        summarize_automation(automation, "bill-eod-dreaming-synthesis", "EOD dreaming synthesis"),
        summarize_automation(automation, "bill-prediction-forward-clob-capture", "Prediction forward CLOB capture"),
    ]
    loop_safe = all(item["safe"] for item in loops if item["status"] != "missing")
    return {
        "decision": "daily-brief-visible-execution-locked",
        "dailyPlan": {
            "routeApproval": daily.get("routeApproval"),
            "brokerReconciliation": daily.get("brokerReconciliation"),
            "decision": daily.get("decision"),
        },
        "premarket": {
            "decision": premarket.get("decision", "missing"),
            "freshness": freshness_for_state("premarket-risk-brief.latest.json"),
            "algoMaxContracts": premarket.get("sizingPosture", {}).get("algoMaxContracts"),
            "hardRiskCount": len(hard_risks),
            "watchRiskCount": len(watch_items),
            "topHardRisks": [item.get("kind") for item in hard_risks[:5]],
            "macro": premarket.get("macro", {}),
            "operatorRead": premarket.get("operatorRead"),
        },
        "loops": loops,
        "loopSafe": loop_safe,
        "feeds": {
            "decision": feeds.get("decision", "missing"),
            "preferredFuturesDataPath": feeds.get("preferredFuturesDataPath"),
            "wiredResearchFeeds": feed_summary.get("wiredResearchFeeds", []),
            "configuredButNotNative": feed_summary.get("configuredButNotNative", []),
            "readyForExecution": bool(feeds.get("readyForExecution")),
            "executionAuthority": bool(feeds.get("executionAuthority")),
        },
        "demoObservation": {
            "decision": demo_observation.get("decision", "missing"),
            "freshness": freshness_for_state("topstep-demo-observation-posture.latest.json"),
            "readyForHumanDemoObservation": bool(demo_observation.get("readyForHumanDemoObservation")),
            "readyForAlgoDemoExpansion": bool(demo_observation.get("readyForAlgoDemoExpansion")),
            "learningDecision": demo_learning.get("decision", "missing"),
            "learningStatus": demo_learning.get("learningStatus"),
            "learningIssueCount": demo_learning.get("issueCount", 0),
            "learningIssues": first_list([
                item.get("id")
                for item in demo_learning.get("issues", [])
                if isinstance(item, dict)
            ], 5),
            "matchedTradeSize": (
                demo_learning.get("brokerReconciliation", {}).get("totalMatchedSize")
                if isinstance(demo_learning.get("brokerReconciliation"), dict) else None
            ),
            "estimatedPnlDollars": (
                demo_learning.get("brokerReconciliation", {}).get("estimatedPnlDollars")
                if isinstance(demo_learning.get("brokerReconciliation"), dict) else None
            ),
            "operatorReportedPnlDollars": (
                demo_observation.get("operatorDemoContext", {}).get("reportedPnlDollars")
                if isinstance(demo_observation.get("operatorDemoContext"), dict) else None
            ),
        },
        "nextSafeAction": next_safe,
        "goalBlockedIds": first_list(goal.get("blockedIds"), 8),
        "readyForExecution": False,
        "readyForDemoExpansion": False,
        "readyForLive": False,
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "movesFunds": False,
    }

def get_founder_metaprompt():
    """Current founder/quant/CTO operating prompt. Coordination only."""
    prompt, root = state_json("founder-quant-cto-metaprompt.latest.json")
    prompt = prompt if isinstance(prompt, dict) else {}
    queue = prompt.get("blockerQueue") if isinstance(prompt.get("blockerQueue"), list) else []
    locks = prompt.get("safetyLocks") if isinstance(prompt.get("safetyLocks"), dict) else {}
    return {
        "decision": prompt.get("decision", "missing"),
        "role": prompt.get("role", "founder quant strategist PM CTO"),
        "primeDirective": prompt.get("primeDirective"),
        "blockerQueue": [
            {
                "id": item.get("id"),
                "status": item.get("status"),
                "why": item.get("why"),
                "nextCommand": item.get("nextCommand"),
            }
            for item in queue[:6]
            if isinstance(item, dict)
        ],
        "safetyLocks": locks,
        "staleOverrideRule": prompt.get("staleOverrideRule"),
        "strategyTruth": prompt.get("strategyTruth") if isinstance(prompt.get("strategyTruth"), dict) else {},
        "operatingFocus": prompt.get("operatingFocus") if isinstance(prompt.get("operatingFocus"), dict) else {},
        "laneOperatingContract": prompt.get("laneOperatingContract") if isinstance(prompt.get("laneOperatingContract"), dict) else {},
        "compoundingPath": first_list(prompt.get("compoundingPath"), 6),
        "capitalDoctrine": prompt.get("capitalDoctrine") if isinstance(prompt.get("capitalDoctrine"), dict) else {},
        "killSwitches": first_list(prompt.get("killSwitches"), 8),
        "agentOperatingCommandments": first_list(prompt.get("agentOperatingCommandments"), 8),
        "completionStandard": first_list(prompt.get("completionStandard"), 8),
        "root": root,
        "readyForExecution": False,
        "readyForDemoExpansion": False,
        "readyForLive": False,
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "movesFunds": False,
    }

def get_strategy_test_framework_plane():
    """Research-only strategy framework recovery status."""
    status, root = state_json("strategy-test-framework-status.latest.json")
    status = status if isinstance(status, dict) else {}
    matrix = status.get("walkforwardMatrix") if isinstance(status.get("walkforwardMatrix"), dict) else {}
    factory = status.get("strategyFactory") if isinstance(status.get("strategyFactory"), dict) else {}
    one_variable = status.get("oneVariableResearch") if isinstance(status.get("oneVariableResearch"), dict) else {}
    playbook = status.get("strategyPlaybook") if isinstance(status.get("strategyPlaybook"), dict) else {}
    no_edge = status.get("futuresNoEdgeMemory") if isinstance(status.get("futuresNoEdgeMemory"), dict) else {}
    return {
        "decision": status.get("decision", "missing"),
        "blockedIds": first_list(status.get("blockedIds"), 10),
        "blockedCount": status.get("blockedCount", len(first_list(status.get("blockedIds"), 10))),
        "operatorRead": status.get("operatorRead", "Strategy framework status artifact missing or stale."),
        "walkforwardMatrix": {
            "status": matrix.get("status", "missing"),
            "ageHours": matrix.get("ageHours"),
            "csvPath": matrix.get("csvPath"),
            "totalWindowsEvaluated": matrix.get("totalWindowsEvaluated", 0),
            "maxWindowsEvaluated": matrix.get("maxWindowsEvaluated", 0),
            "bestConfigId": matrix.get("bestConfigId"),
            "commonFailureModes": first_list(matrix.get("commonFailureModes"), 6),
        },
        "strategyFactory": {
            "walkforwardDeployable": bool(factory.get("walkforwardDeployable")),
            "decision": factory.get("decision"),
            "status": factory.get("status"),
        },
        "oneVariableResearch": {
            "present": bool(one_variable.get("present")),
            "decision": one_variable.get("decision"),
            "resultSummary": one_variable.get("resultSummary") if isinstance(one_variable.get("resultSummary"), dict) else {},
            "recommendedOrder": first_list(one_variable.get("recommendedOrder"), 8),
        },
        "futuresNoEdgeMemory": {
            "present": bool(no_edge.get("present")),
            "count": no_edge.get("count", 0),
            "noEdgeCount": no_edge.get("noEdgeCount", 0),
            "needsNewFeatureCount": no_edge.get("needsNewFeatureCount", 0),
            "matrixRejectionRecorded": bool(no_edge.get("matrixRejectionRecorded")),
            "matrixEntryVerdict": no_edge.get("matrixEntryVerdict"),
        },
        "strategyPlaybook": {
            "decision": playbook.get("decision"),
            "ageHours": playbook.get("ageHours"),
            "strategyCount": playbook.get("strategyCount", 0),
        },
        "nextCommands": [
            {
                "id": item.get("id"),
                "command": item.get("command"),
                "why": item.get("why"),
                "touchesBroker": item.get("touchesBroker", False),
                "writesOrders": item.get("writesOrders", False),
                "operatorReviewRequired": item.get("operatorReviewRequired", False),
            }
            for item in first_list(status.get("nextCommands"), 5)
            if isinstance(item, dict)
        ],
        "staleThreadRule": status.get("staleThreadRule"),
        "root": root,
        "readyForExecution": False,
        "readyForDemoExpansion": False,
        "readyForLive": False,
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "movesFunds": False,
    }

def get_monday_readiness_plane():
    """Monday readiness is a runbook/status view only; it cannot clear execution."""
    cron = load_json(os.path.join(HOME, ".hermes", "cron", "jobs.json"))
    jobs = cron if isinstance(cron, list) else cron.get("jobs", []) if isinstance(cron, dict) else []
    by_name = {job.get("name"): job for job in jobs if isinstance(job, dict)}
    premarket_job = by_name.get("session-shadow-premarket", {})
    postmarket_job = by_name.get("session-shadow-postmarket", {})
    session_files = [
        "scripts/session_shadow_premarket.py",
        "scripts/session_shadow_postmarket.py",
        "scripts/session_shadow_trade_logger.py",
    ]
    session_ready = all(os.path.exists(os.path.join(REPO_DIR, path)) for path in session_files)
    latest_journal_path = os.path.join(REPO_STATE_DIR, "trade-journal.latest.json")
    canonical_journal_path = os.path.join(REPO_STATE_DIR, "trade-journal.jsonl")
    logger_text = load_text(os.path.join(REPO_DIR, "scripts", "session_shadow_trade_logger.py"))
    daily_learning_path = os.path.join(REPO_DIR, "scripts", "topstep_daily_learning.py")
    daily_learning_text = load_text(daily_learning_path)
    latest_journal = load_json(latest_journal_path)
    latest_journal_rows = len(latest_journal) if isinstance(latest_journal, list) else 0
    canonical_rows = sum(
        1
        for line in load_text(canonical_journal_path).splitlines()
        if line.strip().startswith("{")
    )
    canonical_intake_ready = (
        os.path.exists(os.path.join(REPO_DIR, "scripts", "session_shadow_trade_logger.py"))
        and os.path.exists(daily_learning_path)
        and "CANONICAL_JOURNAL_PATH" in logger_text
        and "upsert_canonical_journal" in logger_text
        and "observationOnly" in logger_text
        and "brokerProof" in daily_learning_text
    )
    premarket_ready = bool(premarket_job.get("enabled")) and premarket_job.get("state") == "scheduled"
    postmarket_ready = bool(postmarket_job.get("enabled")) and postmarket_job.get("state") == "scheduled"
    multitf_path = os.path.join(REPO_DIR, "src", "signals", "multitfEntry.ts")
    multitf_text = load_text(multitf_path)
    multitf_exists = os.path.exists(multitf_path)
    multitf_research_only = "RESEARCH ONLY" in multitf_text and "execution pipeline" in multitf_text
    goal = get_goal_audit()
    topstep = get_topstep_data_plane()
    canary, _ = state_json("topstep-demo-canary-preflight.latest.json")
    canary = canary if isinstance(canary, dict) else {}
    execution_locked = not goal.get("readyForExecution") and not goal.get("writesOrders") and not goal.get("touchesBroker")
    bridge_steps = [
        {
            "id": "topstep-market-data-smoke",
            "command": "BILL_ENABLE_FUTURES_DEMO_EXECUTION=false RH_TOPSTEP_READ_ONLY=true RH_LIVE_EXECUTION_ENABLED=false npm run --silent bill:topstep-market-data-smoke",
            "status": "ready-to-run-readonly" if execution_locked else "review",
        },
        {
            "id": "topstep-realtime-proof",
            "command": "BILL_ENABLE_FUTURES_DEMO_EXECUTION=false RH_TOPSTEP_READ_ONLY=true RH_LIVE_EXECUTION_ENABLED=false npm run --silent bill:topstep-realtime-proof",
            "status": "ready-to-run-readonly" if execution_locked else "review",
        },
        {
            "id": "topstep-readonly-bar-archive",
            "command": "BILL_ENABLE_FUTURES_DEMO_EXECUTION=false RH_TOPSTEP_READ_ONLY=true RH_LIVE_EXECUTION_ENABLED=false npm run --silent bill:topstep-readonly-bar-archive",
            "status": "ready-to-run-readonly" if execution_locked else "review",
        },
        {
            "id": "demo-observation-trade",
            "command": "manual/operator only after daily plan and broker reconciliation are green",
            "status": "locked",
        },
    ]
    tracks = [
        {
            "id": "session-shadow-loop",
            "label": "Track A: Session Shadow",
            "status": "ready" if session_ready and premarket_ready and postmarket_ready else "review",
            "evidence": {
                "filesPresent": session_ready,
                "premarketCron": premarket_job.get("next_run_at"),
                "postmarketCron": postmarket_job.get("next_run_at"),
            },
            "operatorRead": "Premarket/postmarket learning loop is scheduled and writes memory only.",
        },
        {
            "id": "bridge-hardening-verification",
            "label": "Track B: Bridge Hardening",
            "status": "blocked" if "futures-demo-not-cleared" in (goal.get("blockedIds") or []) else "review",
            "evidence": {
                "nextProofWindow": topstep.get("nextOpenSessionProofWindow"),
                "readOnlySteps": bridge_steps,
                "executionLocked": execution_locked,
            },
            "operatorRead": "Run read-only proof steps at market open; demo observation remains manual and gated.",
        },
        {
            "id": "multi-tf-entry-module",
            "label": "Track C: Multi-TF Entry",
            "status": "research-only-ready" if multitf_exists and multitf_research_only else "review",
            "evidence": {
                "filePresent": multitf_exists,
                "researchOnlyMarker": multitf_research_only,
                "executionAttached": False,
            },
            "operatorRead": "Module may support research review; it is not attached to execution.",
        },
        {
            "id": "demo-trade-intake",
            "label": "Track D: Demo Trade Intake",
            "status": "ready" if canonical_intake_ready else "review",
            "evidence": {
                "latestJournalRows": latest_journal_rows,
                "canonicalJournalRows": canonical_rows,
                "latestJournalPath": latest_journal_path,
                "canonicalJournalPath": canonical_journal_path,
                "writesCanonicalJsonl": "upsert_canonical_journal" in logger_text,
                "observationOnlyProtected": "observationOnly" in logger_text and "brokerProof" in daily_learning_text,
                "dailyLearningReadsJsonl": os.path.exists(daily_learning_path),
            },
            "operatorRead": "Closed manual Topstep demo observations are captured into the canonical JSONL learning journal, marked observation-only until broker reconciliation proves them.",
        },
        {
            "id": "algo-demo-canary",
            "label": "Track E: Algo Demo Canary",
            "status": "ready" if canary.get("decision") == "demo-canary-ready" else "blocked" if canary else "review",
            "evidence": {
                "decision": canary.get("decision", "missing"),
                "canaryEnabled": canary.get("canaryEnabled"),
                "routeBlockerCount": len(canary.get("routeBlockers", [])) if isinstance(canary.get("routeBlockers"), list) else None,
                "routeBlockers": canary.get("routeBlockers", [])[:5] if isinstance(canary.get("routeBlockers"), list) else [],
                "maxOrdersPerRun": ((canary.get("execution") or {}).get("maxOrdersPerRun") if isinstance(canary.get("execution"), dict) else None),
                "readOnly": ((canary.get("execution") or {}).get("readOnly") if isinstance(canary.get("execution"), dict) else None),
                "liveExecutionEnabled": ((canary.get("execution") or {}).get("liveExecutionEnabled") if isinstance(canary.get("execution"), dict) else None),
            },
            "operatorRead": "Optional bounded algo demo data collection: one NQ/MNQ contract, one order per run, only after daily route, broker green, canary approval, and fresh Topstep data proof.",
        },
    ]
    return {
        "decision": "monday-readiness-visible-execution-locked",
        "tracks": tracks,
        "readyTrackCount": sum(1 for track in tracks if track.get("status") in ("ready", "research-only-ready")),
        "trackCount": len(tracks),
        "blockers": goal.get("blockedIds") or [],
        "readyForExecution": False,
        "readyForDemoExpansion": False,
        "writesOrders": False,
        "touchesBroker": False,
        "researchOnly": True,
    }

def get_lane_coordination_plane():
    """Canonical divide-and-conquer contract for live command work vs research work."""
    goal = get_goal_audit()
    blocker_actions = get_blocker_actions()
    next_actions, _ = state_json("bill-next-research-actions.latest.json")
    ai_data, _ = state_json("ai-scientist-data-access-audit.latest.json")
    strategy = get_strategy_test_framework_plane()
    alpha_watch, _ = state_json("current-alpha-watch.latest.json")
    runtime, _ = state_json("bill-runtime-architecture-audit.latest.json")
    stale_guard, _ = state_json("stale-strategy-claim-guard.latest.json")
    source_intake, _ = state_json("bill-source-intake-manifest.latest.json")
    lane_note = os.path.join(HOME, "Documents", "memorybrain", "Agent-Hermes", "codex-lane-coordination-2026-06-06.md")
    lane_note_present = os.path.exists(lane_note)
    goal_blockers = goal.get("blockedIds") if isinstance(goal.get("blockedIds"), list) else []
    priority = blocker_actions.get("priority") if isinstance(blocker_actions.get("priority"), list) else []
    next_safe = priority[0] if priority else {}
    one_var = {}
    try:
        one_var = strategy.get("oneVariableResearch", {}).get("resultSummary", {}).get("nextFollowUp", {})
    except Exception:
        one_var = {}
    futures_next = {}
    if isinstance(alpha_watch.get("nextOneVariableTest"), dict):
        futures_next = alpha_watch.get("nextOneVariableTest")
    elif isinstance(next_actions.get("dataOnlyProof"), dict):
        futures_next = next_actions.get("dataOnlyProof")
    research_gaps = ai_data.get("featureGaps") if isinstance(ai_data.get("featureGaps"), list) else []
    stale_finding_count = stale_guard.get("findingCount", 0) if isinstance(stale_guard, dict) else 0
    source_review_backlog = source_intake.get("reviewBacklog") if isinstance(source_intake, dict) else None
    lanes = [
        {
            "id": "command-lane",
            "label": "Command Lane",
            "owner": "live Codex command thread",
            "status": "active-blocked" if goal_blockers else "active-clear",
            "owns": [
                "Command Center UI/API truth",
                "Topstep/ProjectX read-only proof and broker parity",
                "daily plan, Obsidian sync, source hygiene, goal audit",
                "execution lock enforcement",
            ],
            "mustNotTouch": [
                "Do not enable route approval or master bridge from dashboard claims.",
                "Do not convert 100K demo P&L notes into payout/promotion proof.",
            ],
            "nextAction": {
                "id": next_safe.get("id") or "review-goal-blockers",
                "title": next_safe.get("title") or "Review current goal blockers",
                "command": next_safe.get("command") or "npm run --silent bill:goal-completion-audit",
            },
            "evidence": {
                "goalBlockers": goal_blockers,
                "staleStrategyClaimFindings": stale_finding_count,
                "sourceReviewBacklog": source_review_backlog,
                "laneNotePresent": lane_note_present,
            },
        },
        {
            "id": "research-lane",
            "label": "Research Lane",
            "owner": "strategy variable / AI-Scientist research loop",
            "status": "research-only-active",
            "owns": [
                "one-variable strategy experiments",
                "multi-TF pullback entry tests",
                "AI-Scientist dataset visibility and hypothesis harness",
                "no-edge memory and cost/slippage stress",
            ],
            "mustNotTouch": [
                "Do not patch execution flags, broker routes, goal audit, or command-center safety gates.",
                "Do not call a strategy promotable without OOS, coverage, and cost evidence.",
            ],
            "nextAction": {
                "id": futures_next.get("id") or one_var.get("id") or "ai-scientist-1m-entry-data",
                "title": futures_next.get("oneVariable") or one_var.get("oneVariable") or "Add NQ/ES 1m datasets as selectable research inputs only",
                "command": futures_next.get("command") or one_var.get("command") or "npm run --silent bill:ai-scientist-data-access-audit",
            },
            "evidence": {
                "aiScientistDecision": ai_data.get("decision"),
                "visibleGoldWalkforward": f"{ai_data.get('visibleGoldWalkforwardCount', 0)}/{ai_data.get('goldWalkforwardCount', 0)}",
                "strategyDecision": strategy.get("decision"),
                "featureGapIds": [gap.get("id") for gap in research_gaps[:4] if isinstance(gap, dict)],
            },
        },
    ]
    return {
        "decision": "lane-coordination-visible-execution-locked",
        "source": {
            "obsidianLaneNote": lane_note,
            "obsidianLaneNotePresent": lane_note_present,
            "runtimeDecision": runtime.get("decision") if isinstance(runtime, dict) else None,
        },
        "lanes": lanes,
        "sharedRule": "Claims become truth only after they land in artifacts with source, one changed variable, OOS/coverage/cost evidence, blockers, and researchOnly=true.",
        "blockers": goal_blockers,
        "readyForExecution": False,
        "readyForDemoExpansion": False,
        "writesOrders": False,
        "touchesBroker": False,
        "movesFunds": False,
        "researchOnly": True,
    }

def get_founder_operating_state():
    """One-scan founder state: permission, gate ledger, and next safe move."""
    daily = parse_daily_control()
    topstep = get_topstep_data_plane()
    risk = get_risk_plane()
    market = get_market_data_plane()
    goal = get_goal_audit()
    blockers = get_blocker_actions()
    strategy = get_strategy_validation_summary()
    live = risk.get("liveReadiness", {}) if isinstance(risk.get("liveReadiness"), dict) else {}
    source = risk.get("source", {}) if isinstance(risk.get("source"), dict) else {}
    broker = risk.get("topstep", {}) if isinstance(risk.get("topstep"), dict) else {}
    goal_blocked = set(goal.get("blockedIds") or [])

    route_ok = str(daily.get("routeApproval", "")).upper() in {"GREEN", "APPROVED", "ALLOW"}
    broker_recon_ok = str(daily.get("brokerReconciliation", "")).upper() == "GREEN"
    source_artifact_ok = bool(source.get("canonicalSourceClean")) and int(source.get("executionLiveDirtyCount") or 0) == 0
    source_ok = source_artifact_ok and "source-hygiene-not-cleared" not in goal_blocked
    strategy_ok = bool(strategy.get("deployable"))
    prediction_ok = "prediction-paper-not-cleared" not in goal_blocked
    archive_ok = "topstep-readonly-archive-depth-thin" not in set(topstep.get("blockers") or [])
    execution_data_ok = bool(market.get("readyForExecutionData"))
    broker_flat = bool(broker.get("brokerFlat") or topstep.get("brokerFlat"))

    gates = [
        {
            "id": "daily-route",
            "label": "Daily route approval",
            "status": "pass" if route_ok else "blocked",
            "evidence": daily.get("routeApproval", "UNKNOWN"),
            "blocksTrading": True,
        },
        {
            "id": "broker-reconciliation",
            "label": "Broker reconciliation",
            "status": "pass" if broker_recon_ok else "review",
            "evidence": daily.get("brokerReconciliation", "UNKNOWN"),
            "blocksTrading": True,
        },
        {
            "id": "broker-flat",
            "label": "Broker flat",
            "status": "pass" if broker_flat else "review",
            "evidence": f"{broker.get('openPositions', topstep.get('openPositions', 0))} open positions",
            "blocksTrading": False,
        },
        {
            "id": "execution-data",
            "label": "Execution-grade data",
            "status": "pass" if execution_data_ok else "blocked",
            "evidence": market.get("source", "unknown"),
            "blocksTrading": True,
        },
        {
            "id": "archive-depth",
            "label": "Topstep archive depth",
            "status": "pass" if archive_ok else "blocked",
            "evidence": f"{topstep.get('archiveRthSessions', 0)} RTH sessions",
            "blocksTrading": False,
        },
        {
            "id": "model-validation",
            "label": "Model validation",
            "status": "pass" if strategy_ok else "blocked",
            "evidence": strategy.get("decision") or live.get("status", "unknown"),
            "blocksTrading": True,
        },
        {
            "id": "source-hygiene",
            "label": "Source hygiene",
            "status": "pass" if source_ok else "blocked",
            "evidence": (
                f"canonical clean; sibling quarantine={source.get('siblingQuarantineCount', 0)}; goal blocker remains"
                if source_artifact_ok and not source_ok
                else
                f"canonical clean; sibling quarantine={source.get('siblingQuarantineCount', 0)}"
                if source_ok
                else f"{source.get('canonicalDirtyFiles', 0)} canonical dirty; {source.get('executionLiveDirtyCount', 0)} execution/live dirty"
            ),
            "blocksTrading": True,
        },
        {
            "id": "prediction-paper",
            "label": "Prediction paper gate",
            "status": "pass" if prediction_ok else "blocked",
            "evidence": "blocked" if not prediction_ok else "clear",
            "blocksTrading": False,
        },
    ]
    pass_count = sum(1 for gate in gates if gate["status"] == "pass")
    blocking_gates = [gate for gate in gates if gate["blocksTrading"] and gate["status"] != "pass"]
    priority = blockers.get("priority") if isinstance(blockers.get("priority"), list) else []
    priority = sorted(
        priority,
        key=lambda item: (
            {"blocked": 0, "paused": 1, "review": 2, "research-only": 3, "pass": 4}.get(item.get("status"), 2),
            0 if item.get("id") == "topstep-archive-depth" else 1,
        ),
    )
    safe_next = next((item for item in priority if isinstance(item, dict) and item.get("safe") and item.get("command")), None)
    burn_down = [
        {
            "rank": index + 1,
            "id": item.get("id"),
            "title": item.get("title") or item.get("id"),
            "lane": item.get("lane", "control"),
            "status": item.get("status", "review"),
            "safe": bool(item.get("safe")),
            "command": item.get("command"),
            "nextCommand": item.get("nextCommand"),
            "why": item.get("why"),
        }
        for index, item in enumerate(priority[:6])
        if isinstance(item, dict)
    ]
    trade_permission = "ALLOWED" if not blocking_gates and route_ok and broker_recon_ok else "BLOCKED"
    return {
        "tradePermission": trade_permission,
        "researchPermission": "ALLOWED",
        "operatorRead": (
            "Data readiness is necessary but not sufficient. Route approval, broker reconciliation, "
            "source hygiene, and model validation still decide whether capital can be put at risk."
        ),
        "gatePassCount": pass_count,
        "gateTotal": len(gates),
        "gates": gates,
        "blockingGateIds": [gate["id"] for gate in blocking_gates],
        "blockerBurnDown": burn_down,
        "nextSafeAction": safe_next or {},
        "doNow": [
            "Work only safe research/control-plane commands.",
            "Build Topstep archive depth, broker parity, realtime freshness, and model-validation evidence.",
            "Keep Obsidian, dashboard, and machine artifacts synchronized.",
        ],
        "doNot": [
            "Do not route orders or fund accounts.",
            "Do not treat data-ready as trade-ready.",
            "Do not auto-stage dirty source packets.",
        ],
        "env": {
            "BILL_ENABLE_FUTURES_DEMO_EXECUTION": "false",
            "RH_TOPSTEP_READ_ONLY": "true",
            "RH_LIVE_EXECUTION_ENABLED": "false",
        },
    }

def get_recent_cron_output():
    """Get last run status of key cron jobs."""
    crons = {}
    if os.path.isdir(CRON_OUT):
        for job_dir in os.listdir(CRON_OUT):
            job_path = os.path.join(CRON_OUT, job_dir)
            if os.path.isdir(job_path):
                files = sorted(glob.glob(os.path.join(job_path, "*")), reverse=True)
                if files:
                    mtime = os.path.getmtime(files[0])
                    age_s = time.time() - mtime
                    crons[job_dir] = {"last_run_s": int(age_s), "file": files[0]}
    return crons

def get_trade_performance():
    """Latest trade performance report."""
    path = os.path.join(STATE_DIR, "trade-performance-report.latest.json")
    data = load_json(path)
    if data:
        return {
            "total_trades": data.get("total_trades", 0),
            "win_rate": data.get("overall_win_rate", 0),
            "profit_factor": data.get("profit_factor", 0),
            "total_pnl": data.get("total_pnl"),
            "mtime": os.path.getmtime(path),
        }
    return {"total_trades": 0, "error": "no report"}

def get_discord_status():
    """Check discord bridge and gateway."""
    return {
        "gateway": get_process_info("gateway run"),
        "searxng": get_process_info("searxng"),
        "n8n": get_n8n_status(),
        "bridge": get_bridge_status(),
    }

def get_goal_audit():
    """Completion audit summary. Read-only; never clears gates or approves routing."""
    goal, root = state_json("bill-goal-completion-audit.latest.json")
    goal = goal if isinstance(goal, dict) else {}
    blocked_ids = first_list(goal.get("blockedIds"), 12)
    blocked_count = goal.get("blockedCount")
    if not isinstance(blocked_count, int):
        blocked_count = len(blocked_ids)
    return {
        "decision": goal.get("decision", "missing"),
        "passCount": goal.get("passCount", 0),
        "checkCount": goal.get("checkCount", 0),
        "blockedCount": blocked_count,
        "blockedIds": blocked_ids,
        "promptUncoveredIds": first_list(goal.get("promptUncoveredIds"), 12),
        "readyForExecution": goal.get("readyForExecution", False),
        "readyForDemoExpansion": goal.get("readyForDemoExpansion", False),
        "readyForLive": goal.get("readyForLive", False),
        "researchOnly": goal.get("researchOnly", True),
        "writesOrders": goal.get("writesOrders", False),
        "touchesBroker": goal.get("touchesBroker", False),
        "root": root,
    }

def get_live_readiness_gate():
    """Live-readiness gate: 21-point checklist, blockers, and deployability flags."""
    data, root = state_json("live-readiness-gate.latest.json")
    if not isinstance(data, dict):
        return {"error": "live-readiness-gate.latest.json not found",
                "readyForLive": False, "readyForDemoExpansion": False}
    checks = data.get("checks", [])
    passed = sum(1 for c in checks if c.get("passed") or c.get("status") == "pass")
    failed = [c for c in checks if not c.get("passed") and c.get("status") != "pass"]
    return {
        "generatedAt": data.get("generatedAt"),
        "readyForLive": data.get("readyForLive", False),
        "readyForDemoExpansion": data.get("readyForDemoExpansion", False),
        "passCount": passed,
        "totalCount": len(checks),
        "failCount": len(failed),
        "blockers": data.get("blockers", []),
        "warnings": data.get("warnings", []),
        "failedChecks": [{"id": c.get("name") or c.get("id", "?"),
                          "summary": c.get("summary", "")} for c in failed],
        "autonomy": data.get("autonomy", {}),
        "root": root,
    }


def get_session_signals():
    """London ORB + Asia session signals with window state. Research-only."""
    london, _ = state_json("london-orb-signal.latest.json")
    asia, _ = state_json("asia-session-signal.latest.json")
    arb, _ = state_json("arbitration.latest.json")

    def sig_summary(name, data):
        if not isinstance(data, dict):
            return {"signal": name, "present": False}
        return {
            "signal": name,
            "present": True,
            "activeWindow": data.get("active_window", False),
            "direction": data.get("direction", "neutral"),
            "confidence": data.get("confidence", 0),
            "session": data.get("session", "?"),
            "window": data.get("window", {}),
            "promotedForExecution": data.get("promoted_for_execution", False),
            "researchOnly": data.get("researchOnly", True),
            "ts": data.get("ts"),
        }

    return {
        "london": sig_summary("london-orb-signal", london),
        "asia": sig_summary("asia-session-signal", asia),
        "arbitration": {
            "decision": arb.get("decision") if arb else None,
            "direction": arb.get("direction") if arb else None,
            "conviction": arb.get("conviction") if arb else None,
            "activeSignals": arb.get("active_signals") if arb else 0,
            "promotedActiveSignals": arb.get("promoted_active_signals", 0) if arb else 0,
            "minPromotedRequired": arb.get("min_promoted_required", 1) if arb else 1,
            "reason": arb.get("reason") if arb else None,
        } if arb else {},
        "operatorNote": "HEURISTIC_UNVERIFIED — research only. Not execution signals.",
    }


def get_trade_journal_summary(limit=10):
    """Parse trade-journal.jsonl: recent trades + lifetime aggregates."""
    path = os.path.join(STATE_DIR, "trade-journal.jsonl")
    trades = []
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    try: trades.append(json.loads(line))
                    except Exception: pass
    except Exception:
        return {"trades": [], "aggregates": {"n": 0}, "error": "no journal"}
    wins = [t for t in trades if (t.get("pnl_dollars") or 0) > 0]
    losses = [t for t in trades if (t.get("pnl_dollars") or 0) < 0]
    gross_win = sum(t.get("pnl_dollars") or 0 for t in wins)
    gross_loss = abs(sum(t.get("pnl_dollars") or 0 for t in losses))
    recent = []
    for t in trades[-limit:]:
        recent.append({k: t.get(k) for k in (
            "trade_id", "entry_ts", "exit_ts", "direction", "size",
            "entry_price", "exit_price", "pnl_pts", "pnl_dollars",
            "duration_minutes", "session", "sl_hit", "tp_hit", "signal_source")})
    return {
        "trades": recent,
        "aggregates": {
            "n": len(trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(len(wins) / len(trades), 3) if trades else None,
            "total_pnl": round(sum(t.get("pnl_dollars") or 0 for t in trades), 2),
            "profit_factor": round(gross_win / gross_loss, 3) if gross_loss else None,
        },
    }

def get_execution_plane():
    """Live execution view: broker position, last submission, quote, DOM, kill switch."""
    now = time.time()
    def age_of(name):
        m, _ = state_mtime(name)
        return int(now - m) if m else None
    recon, _ = state_json("topstep-broker-reconciliation.latest.json")
    recon = recon or {}
    sub, _ = state_json("topstep-demo-submission.latest.json")
    sub = sub or {}
    quote, _ = state_json("realtime-quote.latest.json")
    quote = quote or {}
    dom, _ = state_json("dom-capture.latest.json")
    dom = dom or {}
    kill = load_json(os.path.join(HOME, "hedge", ".rumbling-hedge", "kill-switch.json")) or {}
    master, _ = state_json("master-signal.latest.json")
    master = master or {}
    return {
        "position": {
            "broker_flat": recon.get("broker_flat"),
            "open_positions": recon.get("open_positions"),
            "positions": recon.get("positions", []),
            "fills_today": recon.get("fills_today"),
            "age_s": age_of("topstep-broker-reconciliation.latest.json"),
        },
        "last_submission": {
            "ts": sub.get("ts"),
            "signal": redact_account(sub.get("signal")),
            "side": sub.get("side"),
            "entry": sub.get("entry"),
            "stop": sub.get("stop"),
            "target": sub.get("target"),
            "submitted": sub.get("submitted"),
            "orphan_guard": (sub.get("detail") or {}).get("orphan_guard"),
        },
        "master_signal": {
            "ts": master.get("ts"),
            "signal": master.get("signal"),
            "status": master.get("status"),
            "submitted": master.get("submitted"),
        },
        "quote": {
            "price_nq": quote.get("price_nq"),
            "price_es": quote.get("price_es"),
            "source": quote.get("source"),
            "execution_grade": quote.get("execution_grade"),
            "age_s": age_of("realtime-quote.latest.json"),
        },
        "dom": {
            "status": dom.get("status"),
            "best_bid": dom.get("best_bid"),
            "best_ask": dom.get("best_ask"),
            "depth_events": dom.get("depth_events"),
            "trade_events": dom.get("trade_events"),
            "age_s": age_of("dom-capture.latest.json"),
        },
        "kill_switch": {"triggered": kill.get("triggered"), "blocked": kill.get("blocked")},
        "journal": get_trade_journal_summary(),
    }

def get_full_state():
    full = {
        "ts": time.time(),
        "ts_iso": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "system": get_system(),
        "services": {
            "hermes_gateways": get_process_info("gateway run"),
            "n8n": get_n8n_status(),
            "searxng": get_process_info("searxng"),
            "bridge": get_bridge_status(),
            "postgres": get_process_info("postgres"),
        },
        "control_plane": get_control_plane(),
        "daily_control": parse_daily_control(),
        "market_data": get_market_data_plane(),
        "data_master": get_data_master_plane(),
        "topstep_data": get_topstep_data_plane(),
        "risk_plane": get_risk_plane(),
        "signal_quality": get_signal_quality_plane(),
        "prediction_paper": get_prediction_paper_plane(),
        "goal_audit": get_goal_audit(),
        "founder_operating_state": get_founder_operating_state(),
        "agent_governance": get_agent_governance(),
        "institutional_benchmark": get_institutional_benchmark(),
        "blocker_actions": get_blocker_actions(),
        "founder_daily_brief": get_founder_daily_brief(),
        "founder_metaprompt": get_founder_metaprompt(),
        "strategy_test_framework": get_strategy_test_framework_plane(),
        "monday_readiness": get_monday_readiness_plane(),
        "lane_coordination": get_lane_coordination_plane(),
        "trade": get_trade_performance(),
        "signals": get_signal_state(),
        "cron_jobs": get_recent_cron_output(),
        "data_freshness": load_json(os.path.join(STATE_DIR, "data-freshness-gate.latest.json")),
        "execution_plane": get_execution_plane(),
        "trade_journal": get_trade_journal_summary(),
        "live_readiness_gate": get_live_readiness_gate(),
        "session_signals": get_session_signals(),
    }
    full.update({
        "dailyControl": full["daily_control"],
        "marketData": full["market_data"],
        "dataMaster": full["data_master"],
        "topstepData": full["topstep_data"],
        "riskPlane": full["risk_plane"],
        "signalQuality": full["signal_quality"],
        "predictionPaper": full["prediction_paper"],
        "goalAudit": full["goal_audit"],
        "founderOperatingState": full["founder_operating_state"],
        "agentGovernance": full["agent_governance"],
        "institutionalBenchmark": full["institutional_benchmark"],
        "blockerActions": full["blocker_actions"],
        "founderDailyBrief": full["founder_daily_brief"],
        "founderMetaprompt": full["founder_metaprompt"],
        "strategyTestFramework": full["strategy_test_framework"],
        "mondayReadiness": full["monday_readiness"],
        "laneCoordination": full["lane_coordination"],
        "liveReadinessGate": full["live_readiness_gate"],
        "sessionSignals": full["session_signals"],
        "executionPlane": full["execution_plane"],
    })
    demo_observation = full["topstep_data"].get("demoObservation", {})
    full["topstep_demo_observation"] = demo_observation
    full["topstepDemoObservation"] = demo_observation
    return full

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")

        if path == "/" or path == "":
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            html_path = os.path.join(os.path.dirname(__file__), "command-center.html")
            with open(html_path) as f:
                self.wfile.write(f.read().encode())
            return

        self.send_header("Content-Type", "application/json")
        self.end_headers()

        if path == "/api/full":
            resp = get_full_state()
        elif path == "/api/system":
            resp = get_system()
        elif path == "/api/signals":
            resp = get_signal_state()
        elif path == "/api/execution":
            resp = get_execution_plane()
        elif path == "/api/trade":
            resp = get_trade_performance()
        elif path == "/api/services":
            resp = get_discord_status()
        elif path == "/api/cron":
            resp = get_recent_cron_output()
        elif path == "/api/n8n":
            resp = get_n8n_status()
        elif path == "/api/control-plane":
            resp = get_control_plane()
        elif path == "/api/gex-levels":
            gex_path = os.path.join(os.environ.get("HOME", "/Users/brain"), ".rumbling-hedge/state/gex_levels.json")
            if os.path.exists(gex_path):
                with open(gex_path) as f:
                    resp = json.load(f)
            else:
                resp = {"spx": None, "qqq": None, "error": "No GEX data"}
        elif path == "/tools/gex-heatmap":
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            html_path = os.path.join(os.path.dirname(__file__), "dashboards", "gex-heatmap.html")
            if os.path.exists(html_path):
                with open(html_path) as f:
                    self.wfile.write(f.read().encode())
            else:
                self.wfile.write(b"GEX heatmap not found")
            return
        elif path == "/api/daily-control":
            resp = parse_daily_control()
        elif path == "/api/market-data":
            resp = get_market_data_plane()
        elif path == "/api/data-master":
            resp = get_data_master_plane()
        elif path == "/api/topstep-data":
            resp = get_topstep_data_plane()
        elif path == "/api/risk-plane":
            resp = get_risk_plane()
        elif path == "/api/signal-quality":
            resp = get_signal_quality_plane()
        elif path == "/api/prediction-paper":
            resp = get_prediction_paper_plane()
        elif path == "/api/agent-governance":
            resp = get_agent_governance()
        elif path == "/api/institutional-benchmark":
            resp = get_institutional_benchmark()
        elif path == "/api/blocker-actions":
            resp = get_blocker_actions()
        elif path == "/api/goal-audit":
            resp = get_goal_audit()
        elif path == "/api/founder-operating-state":
            resp = get_founder_operating_state()
        elif path == "/api/founder-daily-brief":
            resp = get_founder_daily_brief()
        elif path == "/api/founder-metaprompt":
            resp = get_founder_metaprompt()
        elif path == "/api/strategy-test-framework":
            resp = get_strategy_test_framework_plane()
        elif path == "/api/monday-readiness":
            resp = get_monday_readiness_plane()
        elif path == "/api/lane-coordination":
            resp = get_lane_coordination_plane()
        elif path == "/api/live-readiness-gate":
            resp = get_live_readiness_gate()
        elif path == "/api/session-signals":
            resp = get_session_signals()
        elif path == "/api/blessed-edges":
            edges_path = os.path.join(os.path.dirname(__file__), ".rumbling-hedge", "state", "blessed-edges.json")
            if os.path.exists(edges_path):
                with open(edges_path) as f:
                    resp = json.load(f)
            else:
                resp = {"edges": [], "error": "blessed-edges.json not found"}
        else:
            resp = {"endpoints": ["/api/full","/api/system","/api/signals","/api/trade","/api/services","/api/cron","/api/n8n","/api/control-plane","/api/daily-control","/api/market-data","/api/data-master","/api/topstep-data","/api/risk-plane","/api/signal-quality","/api/prediction-paper","/api/agent-governance","/api/institutional-benchmark","/api/blocker-actions","/api/goal-audit","/api/founder-operating-state","/api/founder-daily-brief","/api/founder-metaprompt","/api/strategy-test-framework","/api/monday-readiness","/api/lane-coordination","/api/live-readiness-gate","/api/session-signals","/api/blessed-edges"]}

        self.wfile.write(json.dumps(resp, default=str).encode())

    def log_message(self, format, *args):
        pass  # silence logs


class CommandCenterHTTPServer(ThreadingHTTPServer):
    daemon_threads = True


def create_server(port=8766):
    return CommandCenterHTTPServer(("127.0.0.1", port), Handler)


if __name__ == "__main__":
    port = 8766
    print(f"🚀 Command Center API on http://127.0.0.1:{port}")
    print(f"   Full state: http://127.0.0.1:{port}/api/full")
    create_server(port).serve_forever()
