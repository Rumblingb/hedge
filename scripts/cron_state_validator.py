#!/usr/bin/env python3
"""
Hermes cron/state validator for Bill/Hedge holographic loop.

Flags silent no-agent outputs, stale/missing scripts, failed jobs, blank AI
consensus fields, stale state JSONs, and split-state path mismatches.
Safe: read-only, no execution, no secrets.
"""
from __future__ import annotations

import json
import math
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

HOME = Path.home()
HERMES = HOME / ".hermes"
HEDGE = HOME / "hedge"
JOBS = HERMES / "cron" / "jobs.json"
OUTPUT = HERMES / "cron" / "output"
SCRIPT_DIR = HERMES / "scripts"
OUT = HEDGE / ".rumbling-hedge" / "state" / "cron-state-validator.latest.json"
EXECUTION_INTAKE = HEDGE / ".rumbling-hedge" / "state" / "bill-execution-intake-manifest.latest.json"

HEADER_ONLY_PREFIXES = ("# Cron Job:", "**Job ID:**", "**Run Time:**", "**Mode:**", "---")
NOW = time.time()

SHADOW_STATE_SPECS = {
    "dom_proxy": {
        "file": "dom-proxy-signal.latest.json",
        "ttl_s": 2 * 3600,
        "expected_evidence": "proxy_shadow_only",
        "allowed_methods": {"OHLCV_DOM_proxy"},
        "uses_futures_bars": True,
    },
    "kalman_pairs": {
        "file": "kalman-pairs-signal.latest.json",
        "ttl_s": 2 * 3600,
        "expected_evidence": "research_shadow_only",
        "allowed_methods": {"kalman_dynamic_hedge"},
        "uses_futures_bars": True,
    },
    "whale_flow": {
        "file": "whale-flow-signal.latest.json",
        "ttl_s": 6 * 3600,
        "expected_evidence": {"no_live_data_shadow_only", "weekly_cot_shadow_only"},
        "allowed_methods": {"fallback_no_data", "cftc_tff_cot_weekly"},
    },
    "rolling_window": {
        "file": "rolling-window-params.latest.json",
        "ttl_s": 2 * 3600,
        "expected_evidence": "research_shadow_only",
        "allowed_methods": {"performance_scores"},
        "uses_futures_bars": True,
    },
}

TRADING_JOB_PATTERN = re.compile(
    r"(bill|hedge|topstep|futures|strategy|alpha|prediction|polymarket|pm\b|"
    r"signal|whale|dom|kalman|rolling|gengar|agentic|lucidflex|pickmytrade)",
    re.IGNORECASE,
)
QUARANTINED_SCRIPT_PATTERNS = (
    "pm_arb_scanner.py",
    "bill-pm-auto-execute-loop.sh",
)
SHADOW_CRON_SCRIPT_REQUIREMENTS = {
    "dom_proxy_ohlcv.py": [
        "NOT A TRADE SIGNAL",
        "source_data_stale",
        "stale_threshold_seconds",
        "promoted_for_execution",
    ],
    "kalman_pairs.py": [
        "NOT A TRADE SIGNAL",
        "source_data_stale",
        "stale_threshold_seconds",
        "promoted_for_execution",
    ],
    "rolling_window_optimizer.py": [
        "NOT A TRADE SIGNAL",
        "source_data_stale",
        "stale_threshold_seconds",
        "promoted_for_execution",
    ],
    "whale_flow_signal.py": [
        "NOT A TRADE SIGNAL",
        "weekly_cot_shadow_only",
        "promoted_for_execution",
    ],
}


def load_json(path: Path) -> Optional[Any]:
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def job_enabled(job: dict) -> bool:
    return job.get("enabled") is True and job.get("state") != "paused"


def no_agent_script_resolves_inside_scripts(script: str | None) -> bool:
    if not script:
        return False
    try:
        scripts_dir = SCRIPT_DIR.resolve()
        raw = Path(str(script)).expanduser()
        path = raw.resolve() if raw.is_absolute() else (SCRIPT_DIR / raw).resolve()
        path.relative_to(scripts_dir)
        return path.exists() and path.is_file()
    except Exception:
        return False


def stale_script_path_error_is_fixed(job: dict, detail: Any) -> bool:
    if job.get("no_agent") is not True:
        return False
    if "script path resolves outside the scripts directory" not in str(detail or ""):
        return False
    return no_agent_script_resolves_inside_scripts(job.get("script"))


def job_text(job: dict) -> str:
    return "\n".join(str(job.get(key) or "") for key in ("name", "prompt", "script"))


def job_name_prompt(job: dict) -> str:
    return "\n".join(str(job.get(key) or "") for key in ("name", "prompt"))


def is_trading_related_job(job: dict) -> bool:
    return bool(TRADING_JOB_PATTERN.search(job_name_prompt(job)))


def cron_trust_snapshot(jobs: List[dict]) -> Dict[str, Any]:
    active_no_agent: List[Dict[str, Any]] = []
    active_agent_backed: List[Dict[str, Any]] = []
    no_agent_metadata_mismatch: List[Dict[str, Any]] = []
    quarantined_scripts: List[Dict[str, Any]] = []

    for job in jobs:
        enabled = job_enabled(job)
        text = job_text(job)
        item = {
            "id": job.get("id", ""),
            "name": job.get("name"),
            "enabled": enabled,
            "state": job.get("state"),
            "noAgent": job.get("no_agent") is True,
            "script": job.get("script"),
            "model": job.get("model"),
            "provider": job.get("provider"),
            "lastStatus": job.get("last_status"),
        }
        if enabled and is_trading_related_job(job):
            if job.get("no_agent") is True:
                active_no_agent.append(item)
            else:
                active_agent_backed.append(item)
        if enabled and "Local no-agent cron:" in text and job.get("no_agent") is not True:
            no_agent_metadata_mismatch.append(item)
        if any(pattern in text for pattern in QUARANTINED_SCRIPT_PATTERNS):
            quarantined_scripts.append(item)

    return {
        "activeTradingNoAgentCount": len(active_no_agent),
        "activeTradingAgentBackedCount": len(active_agent_backed),
        "noAgentMetadataMismatchCount": len(no_agent_metadata_mismatch),
        "quarantinedScriptReferenceCount": len(quarantined_scripts),
        "activeTradingNoAgent": active_no_agent,
        "activeTradingAgentBacked": active_agent_backed,
        "noAgentMetadataMismatch": no_agent_metadata_mismatch,
        "quarantinedScripts": quarantined_scripts,
        "policy": [
            "Trading-adjacent cron should be deterministic no-agent unless it is explicitly research-only and cannot route.",
            "Jobs referencing quarantined scripts must remain disabled.",
            "A prompt saying Local no-agent is not enough; the no_agent metadata flag must be true.",
        ],
    }


def execution_live_script_index(manifest: Optional[dict]) -> Dict[str, Dict[str, Any]]:
    """Index dirty execution-live files by script basename for cron cross-checks."""
    if not isinstance(manifest, dict):
        return {}
    index: Dict[str, Dict[str, Any]] = {}
    for item in manifest.get("items", []):
        if not isinstance(item, dict):
            continue
        relative = str(item.get("relativePath") or "")
        if not relative:
            continue
        name = Path(relative).name
        if not name:
            continue
        classification = str(item.get("classification") or "")
        ready = item.get("readyForExecution") is True
        if "quarantined" not in classification and ready:
            continue
        index[name] = {
            "relativePath": relative,
            "classification": classification,
            "gitStatus": item.get("gitStatus"),
            "firewallId": item.get("firewallId"),
            "firewallPassed": item.get("firewallPassed"),
            "readyForExecution": item.get("readyForExecution"),
            "writesOrders": item.get("writesOrders"),
            "touchesBroker": item.get("touchesBroker"),
            "movesFunds": item.get("movesFunds"),
        }
    return index


def cron_execution_live_references(
    jobs: List[dict],
    execution_index: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Return active trading-adjacent crons pointing at dirty execution-live files."""
    if not execution_index:
        return []
    references: List[Dict[str, Any]] = []
    for job in jobs:
        if not (job_enabled(job) and is_trading_related_job(job)):
            continue
        script = str(job.get("script") or "")
        if not script:
            continue
        matched = execution_index.get(Path(script).name)
        if matched:
            validation_commands = [
                "npm run --silent bill:verify-60m-bridge-firewall"
                if matched.get("firewallId") == "verify-60m-bridge-firewall"
                else "npm run --silent bill:verify-execution-quarantine",
                "npm run --silent bill:execution-intake-manifest",
                "npm run --silent bill:cron-state-validator",
                "npm run --silent bill:goal-completion-audit",
                "npm run --silent bill:obsidian-sync",
            ]
            references.append({
                "id": job.get("id", ""),
                "name": job.get("name"),
                "script": script,
                "noAgent": job.get("no_agent") is True,
                "lastStatus": job.get("last_status"),
                "source": matched,
                "operatorRemediation": {
                    "approvalRequired": True,
                    "safeAutomaticAction": False,
                    "requiredAction": (
                        "operator must either disable/pause this cron until the dirty execution-live "
                        "source is reviewed, or clear the source through the execution-live review packet"
                    ),
                    "doNotAutoDisableReason": "changing active cron schedules is an operator-visible control-plane action",
                    "validationCommands": validation_commands,
                },
            })
    return references


def cron_trust_issues(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    for job in snapshot.get("activeTradingAgentBacked", []):
        severity = "P1" if job.get("model") or job.get("provider") else "P2"
        issues.append({
            "severity": severity,
            "job": job.get("name"),
            "id": job.get("id"),
            "type": "active_trading_adjacent_agent_backed_cron",
            "detail": job,
        })
    for job in snapshot.get("noAgentMetadataMismatch", []):
        issues.append({
            "severity": "P1",
            "job": job.get("name"),
            "id": job.get("id"),
            "type": "no_agent_metadata_mismatch",
            "detail": job,
        })
    for job in snapshot.get("quarantinedScripts", []):
        if job.get("enabled"):
            issues.append({
                "severity": "P0",
                "job": job.get("name"),
                "id": job.get("id"),
                "type": "quarantined_script_enabled",
                "detail": job,
            })
    for job in snapshot.get("activeDirtyExecutionLiveScriptReferences", []):
        source = job.get("source") or {}
        severity = "P1" if source.get("firewallPassed") is True else "P0"
        issues.append({
            "severity": severity,
            "job": job.get("name"),
            "id": job.get("id"),
            "type": "active_cron_references_dirty_execution_live_script",
            "detail": job,
        })
    return issues


def script_guardrail_text(path: Path) -> str:
    """Read a Hermes script plus its canonical target when it is a runpy wrapper."""
    try:
        text = path.read_text(errors="ignore")
    except Exception:
        return ""
    combined = text
    for raw_target in re.findall(r'Path\("([^"]+)"\)', text):
        try:
            target = Path(raw_target)
            if target.exists() and target.is_file():
                combined += "\n" + target.read_text(errors="ignore")
        except Exception:
            continue
    return combined


def shadow_cron_script_guardrails(jobs: List[dict]) -> List[Dict[str, Any]]:
    """Verify active Hermes shadow cron scripts carry no-trade guardrail text."""
    rows: List[Dict[str, Any]] = []
    for job in jobs:
        script = str(job.get("script") or "")
        requirements = SHADOW_CRON_SCRIPT_REQUIREMENTS.get(Path(script).name)
        if not requirements or not job_enabled(job):
            continue
        path = (SCRIPT_DIR / script).resolve()
        text = script_guardrail_text(path) if path.exists() else ""
        missing_tokens = [token for token in requirements if token not in text]
        rows.append({
            "id": job.get("id", ""),
            "name": job.get("name"),
            "script": script,
            "path": str(path),
            "exists": path.exists(),
            "noAgent": job.get("no_agent") is True,
            "requiredTokens": requirements,
            "missingTokens": missing_tokens,
            "guardrailPresent": path.exists() and not missing_tokens,
            "operatorRead": (
                "Active Hermes shadow cron scripts must make research-only/no-trade status "
                "obvious in the script path actually run by cron, not only in repo copies."
            ),
        })
    return rows


def shadow_cron_script_guardrail_issues(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    for row in rows:
        if row.get("guardrailPresent") is True:
            continue
        issues.append({
            "severity": "P1",
            "job": row.get("name"),
            "id": row.get("id"),
            "type": "active_shadow_cron_script_guardrail_drift",
            "detail": row,
            "operatorRemediation": {
                "approvalRequired": False,
                "safeAutomaticAction": False,
                "requiredAction": (
                    "patch the active Hermes script or wrapper to include explicit research-only, "
                    "stale-source, and no-trade guardrails; then rerun the cron state validator"
                ),
                "validationCommands": [
                    "python3 -m py_compile /Users/brain/.hermes/scripts/" + str(row.get("script")),
                    "npm run --silent bill:cron-state-validator",
                    "npm run --silent bill:obsidian-sync",
                ],
            },
        })
    return issues


def cron_trust_handoff_fields(cron_trust: Dict[str, Any], issues: List[Dict[str, Any]]) -> Dict[str, Any]:
    dirty_refs = (
        cron_trust.get("activeDirtyExecutionLiveScriptReferences")
        if isinstance(cron_trust.get("activeDirtyExecutionLiveScriptReferences"), list)
        else []
    )
    blocking_issues = [
        issue
        for issue in issues
        if isinstance(issue, dict) and issue.get("severity") in {"P0", "P1"}
    ]
    return {
        "cronTrustCleared": len(blocking_issues) == 0 and not dirty_refs,
        "blockingIssueCount": len(blocking_issues),
        "blockingIssues": blocking_issues,
        "diagnosticIssueCount": len([
            issue
            for issue in issues
            if isinstance(issue, dict) and issue.get("severity") not in {"P0", "P1"}
        ]),
        "activeDirtyExecutionLiveScriptReferenceCount": int(
            cron_trust.get("activeDirtyExecutionLiveScriptReferenceCount") or len(dirty_refs)
        ),
        "activeDirtyExecutionLiveScriptReferences": dirty_refs,
        "activeTradingAgentBackedCount": cron_trust.get("activeTradingAgentBackedCount"),
        "noAgentMetadataMismatchCount": cron_trust.get("noAgentMetadataMismatchCount"),
        "quarantinedScriptReferenceCount": cron_trust.get("quarantinedScriptReferenceCount"),
    }


def issue_severity_counts(issues: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        severity = str(issue.get("severity") or "unknown")
        counts[severity] = counts.get(severity, 0) + 1
    return counts


def validator_summary(handoff_fields: Dict[str, Any], issue_counts: Dict[str, int]) -> str:
    issue_total = sum(issue_counts.values())
    if issue_total == 0:
        return "ok"
    blocking = int(handoff_fields.get("blockingIssueCount") or 0)
    diagnostics = int(handoff_fields.get("diagnosticIssueCount") or 0)
    dirty_refs = int(handoff_fields.get("activeDirtyExecutionLiveScriptReferenceCount") or 0)
    if blocking == 0 and dirty_refs == 0 and handoff_fields.get("cronTrustCleared") is True:
        return f"cron trust clear; {diagnostics} diagnostic issues flagged"
    return f"{blocking} blocking and {diagnostics} diagnostic issues flagged"


def latest_output(job_id: str) -> Optional[Path]:
    d = OUTPUT / job_id
    if not d.exists():
        return None
    files = sorted(d.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def has_meaningful_body(text: str) -> bool:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    body = []
    in_response = False
    for l in lines:
        if l in ("## Response", "---"):
            in_response = True
            continue
        if not in_response and (l.startswith("# Cron Job:") or l.startswith("**") or l.startswith("## Prompt")):
            continue
        if in_response:
            body.append(l)
    if not body:
        body = [l for l in lines if not l.startswith(HEADER_ONLY_PREFIXES) and l not in ("## Prompt", "## Response")]
    content = "\n".join(body).strip()
    if not content:
        return False
    boilerplate = {"=== 30m ===", "=== 60m ===", "=== 240m ==="}
    useful = [l for l in body if l not in boilerplate and len(l) > 3]
    return bool(useful)


def stale_strategy_bars(text: str, max_age_hours: int = 8) -> List[Dict[str, Any]]:
    """Extract stale 'last bar:' timestamps from strategy cron output."""
    stale: List[Dict[str, Any]] = []
    for match in re.finditer(r"(?P<label>[^\n]*?)\(last bar:\s*(?P<ts>\d{4}-\d{2}-\d{2}T[^\)\s]+)", text):
        raw_ts = match.group("ts")
        clean_ts = raw_ts.rstrip(",.;")
        try:
            dt = datetime.fromisoformat(clean_ts.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            age_h = (datetime.fromtimestamp(NOW, timezone.utc) - dt.astimezone(timezone.utc)).total_seconds() / 3600
        except Exception:
            age_h = float("inf")
        if age_h > max_age_hours:
            stale.append({
                "label": match.group("label").strip()[-80:],
                "last_bar": raw_ts,
                "age_h": round(age_h, 1),
                "max_age_h": max_age_hours,
            })
    return stale


def state_summary(path: Path, ttl_s: int, required: Optional[List[str]] = None) -> Dict[str, Any]:
    item: Dict[str, Any] = {"path": str(path), "exists": path.exists()}
    if not path.exists():
        item["status"] = "missing"
        return item
    age = int(NOW - path.stat().st_mtime)
    item.update({"age_s": age, "stale": age > ttl_s})
    data = load_json(path)
    if data is None:
        item["status"] = "invalid-json"
        return item
    item["status"] = "ok"
    if required:
        missing = [k for k in required if k not in data]
        if missing:
            item["missing_fields"] = missing
    summary_keys = {
        "llm_available",
        "final_decision",
        "confidence",
        "liveExecution",
        "readyForLive",
        "decision",
        "execution",
        "status",
    }
    if required:
        summary_keys.update(required)
    for key in summary_keys:
        if key in data:
            item[key] = data[key]
    return item


def parse_state_ts(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def age_seconds(dt: datetime) -> int:
    return int((datetime.fromtimestamp(NOW, timezone.utc) - dt).total_seconds())


def is_futures_weekend_closure(now: Optional[datetime] = None) -> bool:
    """Approximate CME futures weekend closure in UTC for shadow last-bar checks."""
    now_utc = now or datetime.fromtimestamp(NOW, timezone.utc)
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    now_utc = now_utc.astimezone(timezone.utc)
    weekday = now_utc.weekday()
    seconds = now_utc.hour * 3600 + now_utc.minute * 60 + now_utc.second
    if weekday == 4 and seconds >= 22 * 3600:
        return True
    if weekday == 5:
        return True
    if weekday == 6 and seconds < 22 * 3600:
        return True
    return False


def finite_scores(data: dict) -> bool:
    scores = data.get("scores")
    if not isinstance(scores, dict):
        return True
    for value in scores.values():
        if isinstance(value, dict):
            value = value.get("score")
        if isinstance(value, (int, float)) and not math.isfinite(value):
            return False
    return True


def audit_shadow_state(label: str, spec: dict) -> Dict[str, Any]:
    path = HEDGE / ".rumbling-hedge/state" / spec["file"]
    summary: Dict[str, Any] = {
        "file": spec["file"],
        "path": str(path),
        "exists": path.exists(),
    }
    if not path.exists():
        summary["status"] = "missing"
        return summary
    summary["fileAgeSeconds"] = int(NOW - path.stat().st_mtime)
    data = load_json(path)
    if not isinstance(data, dict):
        summary["status"] = "invalid-json"
        return summary

    timestamp_dt = parse_state_ts(data.get("timestamp"))
    last_bar_dt = parse_state_ts(data.get("last_bar_time"))
    last_bar_age = age_seconds(last_bar_dt) if last_bar_dt else None
    stale_threshold = data.get("stale_threshold_seconds")
    if not isinstance(stale_threshold, (int, float)) or not math.isfinite(stale_threshold):
        stale_threshold = spec.get("ttl_s")
    explicit_source_stale = data.get("source_data_stale")
    if explicit_source_stale is None and isinstance(last_bar_age, int) and isinstance(stale_threshold, (int, float)):
        explicit_source_stale = last_bar_age > stale_threshold
    summary.update({
        "status": "ok",
        "method": data.get("method"),
        "evidenceLevel": data.get("evidence_level"),
        "executionRole": data.get("execution_role"),
        "tradableSignal": data.get("tradable_signal"),
        "promotedForExecution": data.get("promoted_for_execution"),
        "sourceDataStale": explicit_source_stale,
        "staleThresholdSeconds": int(stale_threshold) if isinstance(stale_threshold, (int, float)) else None,
        "direction": data.get("direction", data.get("action")),
        "confidence": data.get("confidence"),
        "timestampAgeSeconds": age_seconds(timestamp_dt) if timestamp_dt else None,
        "lastBarAgeSeconds": last_bar_age,
        "finiteScores": finite_scores(data),
    })
    return summary


def shadow_state_issues(label: str, spec: dict, summary: dict) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    base = {"job": label, "stateFile": spec["file"]}
    if not summary.get("exists"):
        return [{**base, "severity": "P1", "type": "missing_shadow_state", "detail": summary}]
    if summary.get("status") != "ok":
        return [{**base, "severity": "P1", "type": "invalid_shadow_state", "detail": summary}]
    if summary.get("promotedForExecution") is True or summary.get("tradableSignal") is True:
        issues.append({**base, "severity": "P0", "type": "shadow_signal_promoted", "detail": summary})
    expected_evidence = spec.get("expected_evidence")
    if isinstance(expected_evidence, set):
        evidence_ok = summary.get("evidenceLevel") in expected_evidence
    else:
        evidence_ok = summary.get("evidenceLevel") == expected_evidence
    if not evidence_ok:
        issues.append({
            **base,
            "severity": "P1",
            "type": "unexpected_shadow_evidence_level",
            "expected": sorted(expected_evidence) if isinstance(expected_evidence, set) else expected_evidence,
            "detail": summary,
        })
    allowed = spec.get("allowed_methods") or set()
    if allowed and summary.get("method") not in allowed:
        issues.append({
            **base,
            "severity": "P1",
            "type": "unexpected_shadow_method",
            "expected": sorted(allowed),
            "detail": summary,
        })
    if isinstance(summary.get("timestampAgeSeconds"), int) and summary["timestampAgeSeconds"] > spec["ttl_s"]:
        issues.append({**base, "severity": "P1", "type": "stale_shadow_state_timestamp", "detail": summary})
    last_bar_age = summary.get("lastBarAgeSeconds")
    market_closed_ok = (
        spec.get("uses_futures_bars") is True
        and isinstance(last_bar_age, int)
        and is_futures_weekend_closure()
        and last_bar_age <= 72 * 3600
    )
    if isinstance(last_bar_age, int) and last_bar_age > spec["ttl_s"] and not market_closed_ok:
        issues.append({**base, "severity": "P1", "type": "stale_shadow_state_last_bar", "detail": summary})
    if summary.get("finiteScores") is False:
        issues.append({**base, "severity": "P1", "type": "non_finite_shadow_scores", "detail": summary})
    if summary.get("method") == "fallback_no_data":
        issues.append({**base, "severity": "P1", "type": "fallback_no_data_shadow_only", "detail": summary})
    return issues


def brain_path_issues(states: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    home_brain = states.get("brain_state") or {}
    hedge_brain = states.get("hedge_brain_state") or {}
    if not (home_brain.get("exists") and hedge_brain.get("exists")):
        return []
    if (
        hedge_brain.get("status") == "ok"
        and hedge_brain.get("stale") is False
        and home_brain.get("stale") is True
    ):
        return []
    return [{
        "severity": "P2",
        "type": "split_brain_paths",
        "detail": "Both ~/.rumbling-hedge/brain and ~/hedge/.rumbling-hedge/brain exist; verify consumers use intended path",
        "operatorRemediation": {
            "approvalRequired": True,
            "safeAutomaticAction": False,
            "requiredAction": (
                "choose one canonical brain state path for consumers; until then treat both brain-state files "
                "as diagnostic context only and do not use either as an execution signal"
            ),
            "preferredCanonicalPath": str(HEDGE / ".rumbling-hedge/brain/brain-state.latest.json"),
            "legacyPath": str(HOME / ".rumbling-hedge/brain/brain-state.latest.json"),
            "validationCommands": [
                "rg -n \"\\.rumbling-hedge/brain|brain-state.latest.json\" /Users/brain/hedge /Users/brain/.hermes/scripts",
                "npm run --silent bill:cron-state-validator",
                "npm run --silent bill:obsidian-sync",
            ],
        },
    }]


def main() -> int:
    jobs_obj = load_json(JOBS) or {"jobs": []}
    jobs = jobs_obj.get("jobs", [])
    issues: List[Dict[str, Any]] = []
    counts = {"jobs_total": len(jobs), "active": 0, "paused": 0, "error": 0, "silent_output": 0, "missing_script": 0}

    for job in jobs:
        jid = job.get("id", "")
        enabled = bool(job.get("enabled"))
        state = job.get("state")
        if enabled:
            counts["active"] += 1
        else:
            counts["paused"] += 1
        if job.get("last_status") == "error" or job.get("last_error"):
            counts["error"] += 1
            detail = job.get("last_error") or job.get("last_status")
            if not enabled:
                issues.append({
                    "severity": "P2",
                    "job": job.get("name"),
                    "id": jid,
                    "type": "paused_job_stale_error",
                    "detail": detail,
                })
            elif jid == "5d5989b498cb" and "account-invalidation conditions" in (job.get("prompt") or ""):
                issues.append({
                    "severity": "P1",
                    "job": job.get("name"),
                    "id": jid,
                    "type": "stale_metadata_pending_next_run",
                    "detail": detail,
                })
            elif stale_script_path_error_is_fixed(job, detail):
                issues.append({
                    "severity": "P2",
                    "job": job.get("name"),
                    "id": jid,
                    "type": "stale_script_path_error_fixed_pending_next_run",
                    "detail": detail,
                    "script": job.get("script"),
                    "path": str((SCRIPT_DIR / str(job.get("script"))).resolve()),
                    "operatorRemediation": {
                        "approvalRequired": False,
                        "safeAutomaticAction": False,
                        "requiredAction": "wait for the cron job to run again or manually inspect the latest job output; the script path now resolves inside ~/.hermes/scripts",
                        "validationCommands": [
                            "npm run --silent bill:cron-state-validator",
                            "ls -l /Users/brain/.hermes/scripts/check_expiry.sh",
                        ],
                    },
                })
            else:
                issues.append({"severity": "P0", "job": job.get("name"), "id": jid, "type": "last_error", "detail": detail})
        script = job.get("script")
        if enabled and job.get("no_agent") and script:
            if not (SCRIPT_DIR / script).exists():
                counts["missing_script"] += 1
                issues.append({"severity": "P0", "job": job.get("name"), "id": jid, "type": "missing_script", "path": str(SCRIPT_DIR / script)})
            out = latest_output(jid)
            if out and out.exists():
                try:
                    text = out.read_text(errors="ignore")
                    if not has_meaningful_body(text):
                        counts["silent_output"] += 1
                        issues.append({"severity": "P1", "job": job.get("name"), "id": jid, "type": "silent_or_header_only_output", "output": str(out)})
                    if job.get("name") in {"agentic-fund-cycle", "master-strategy-bridge"}:
                        stale_bars = stale_strategy_bars(text)
                        if stale_bars:
                            issues.append({
                                "severity": "P1",
                                "job": job.get("name"),
                                "id": jid,
                                "type": "stale_strategy_bars",
                                "output": str(out),
                                "detail": stale_bars[:10],
                            })
                except Exception as e:
                    issues.append({"severity": "P2", "job": job.get("name"), "id": jid, "type": "output_read_error", "detail": str(e)})

    states = {
        "ai_debate": state_summary(
            HEDGE / ".rumbling-hedge/state/ai-debate.latest.json",
            6 * 3600,
            [
                "llm_available",
                "final_decision",
                "confidence",
                "deterministic_fallback",
                "tradable_signal",
                "promoted_for_execution",
                "writesOrders",
            ],
        ),
        "live_seal": state_summary(HEDGE / ".rumbling-hedge/state/live-money-lane-seal.latest.json", 2 * 3600, ["liveExecution"]),
        "arbitration": state_summary(HEDGE / ".rumbling-hedge/state/arbitration.latest.json", 2 * 3600, ["decision", "active_signals"]),
        "brain_state": state_summary(HOME / ".rumbling-hedge/brain/brain-state.latest.json", 4 * 3600, ["fused_direction", "active_signals"]),
        "hedge_brain_state": state_summary(HEDGE / ".rumbling-hedge/brain/brain-state.latest.json", 4 * 3600),
    }
    ai_unavailable = states["ai_debate"].get("llm_available") is False
    ai_confidence = states["ai_debate"].get("confidence")
    ai_safe_wait = (
        states["ai_debate"].get("final_decision") == "WAIT"
        and isinstance(ai_confidence, (int, float))
        and ai_confidence <= 0
    )
    ai_deterministic_safe = (
        ai_safe_wait
        and states["ai_debate"].get("deterministic_fallback") is True
        and states["ai_debate"].get("tradable_signal") is False
        and states["ai_debate"].get("promoted_for_execution") is False
        and states["ai_debate"].get("writesOrders") is False
    )
    if ai_unavailable and not ai_safe_wait:
        issues.append({"severity": "P0", "type": "unsafe_ai_fallback", "detail": states["ai_debate"]})
    if ai_unavailable and ai_safe_wait and not ai_deterministic_safe:
        issues.append({
            "severity": "P2",
            "type": "llm_unavailable_safe_wait",
            "detail": "AI debate LLM is unavailable, but the artifact is fail-closed: final_decision=WAIT and confidence=0",
        })
    issues.extend(brain_path_issues(states))

    shadow_states = {
        label: audit_shadow_state(label, spec)
        for label, spec in SHADOW_STATE_SPECS.items()
    }
    for label, summary in shadow_states.items():
        issues.extend(shadow_state_issues(label, SHADOW_STATE_SPECS[label], summary))

    execution_index = execution_live_script_index(load_json(EXECUTION_INTAKE))
    dirty_execution_references = cron_execution_live_references(jobs, execution_index)
    cron_trust = cron_trust_snapshot(jobs)
    active_shadow_cron_scripts = shadow_cron_script_guardrails(jobs)
    cron_trust["activeDirtyExecutionLiveScriptReferenceCount"] = len(dirty_execution_references)
    cron_trust["activeDirtyExecutionLiveScriptReferences"] = dirty_execution_references
    cron_trust["activeShadowCronScriptGuardrails"] = active_shadow_cron_scripts
    cron_trust["activeShadowCronScriptGuardrailDriftCount"] = len([
        row for row in active_shadow_cron_scripts if row.get("guardrailPresent") is not True
    ])
    cron_trust["executionIntakeManifest"] = str(EXECUTION_INTAKE)
    issues.extend(cron_trust_issues(cron_trust))
    issues.extend(shadow_cron_script_guardrail_issues(active_shadow_cron_scripts))
    handoff_fields = cron_trust_handoff_fields(cron_trust, issues)
    issue_counts = issue_severity_counts(issues)

    report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(NOW)),
        "counts": counts,
        "cron_trust": cron_trust,
        **handoff_fields,
        "issueSeverityCounts": issue_counts,
        "states": states,
        "shadow_states": shadow_states,
        "issues": issues,
        "summary": validator_summary(handoff_fields, issue_counts),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
