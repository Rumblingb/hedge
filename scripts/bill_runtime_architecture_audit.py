#!/usr/bin/env python3
"""Runtime architecture audit for Bill/Hermes.

This script is a read-only control-plane audit. It inspects local orchestration
state for n8n, Hermes Kanban, Hermes cron, and the AI-Scientist financial
template. It never touches broker APIs, funding keys, order routes, or execution
flags.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


HOME = Path.home()
ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
VAULT = HOME / "Documents" / "memorybrain"
AGENT_HERMES = VAULT / "Agent-Hermes"

DEFAULT_OUTPUT = STATE / "bill-runtime-architecture-audit.latest.json"
DEFAULT_MARKDOWN = AGENT_HERMES / f"bill-runtime-architecture-audit-{datetime.now(timezone.utc).date()}.md"
DEFAULT_N8N_DB = HOME / ".n8n" / "database.sqlite"
DEFAULT_N8N_ENV = HOME / "ops" / "n8n" / ".env"
DEFAULT_KANBAN_DB = HOME / ".hermes" / "kanban.db"
DEFAULT_CRON = HOME / ".hermes" / "cron" / "jobs.json"
DEFAULT_CRON_VALIDATOR = STATE / "cron-state-validator.latest.json"
DEFAULT_AI_TEMPLATE = ROOT / "ai-scientist-templates" / "financial_strategy"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path, fallback: Any = None) -> Any:
    try:
        return json.loads(path.read_text())
    except Exception:
        return {} if fallback is None else fallback


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def write_markdown(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def load_env_file(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    try:
        for raw in path.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip().strip("'\"")
    except Exception:
        pass
    return env


def summarize_n8n_rows(rows: list[dict[str, Any]], path: str, source: str) -> dict[str, Any]:
    out: dict[str, Any] = {
        "path": path,
        "source": source,
        "exists": True,
        "workflowCount": 0,
        "activeCount": 0,
        "inactiveCount": 0,
        "billWorkflowCount": 0,
        "activeBillWorkflowCount": 0,
        "workflows": [],
        "billWorkflows": [],
    }
    workflows: list[dict[str, Any]] = []
    for row in rows:
        nodes = row.get("nodes")
        if isinstance(nodes, str):
            try:
                nodes = json.loads(nodes)
            except Exception:
                nodes = []
        node_list = nodes if isinstance(nodes, list) else []
        node_types = sorted({str(node.get("type")) for node in node_list if isinstance(node, dict) and node.get("type")})
        name = str(row.get("name") or "")
        item = {
            "id": row.get("id"),
            "name": name,
            "active": bool(row.get("active")),
            "updatedAt": row.get("updatedAt"),
            "nodeCount": len(node_list),
            "nodeTypes": node_types[:12],
            "isBillRelated": any(word in name.lower() for word in ("bill", "hermes", "topstep", "gengar", "prediction")),
        }
        workflows.append(item)

    out["workflows"] = workflows
    out["workflowCount"] = len(workflows)
    out["activeCount"] = sum(1 for item in workflows if item["active"])
    out["inactiveCount"] = sum(1 for item in workflows if not item["active"])
    out["billWorkflows"] = [item for item in workflows if item["isBillRelated"]]
    out["billWorkflowCount"] = len(out["billWorkflows"])
    out["activeBillWorkflowCount"] = sum(1 for item in out["billWorkflows"] if item["active"])
    return out


def n8n_postgres_summary(env_path: Path = DEFAULT_N8N_ENV) -> dict[str, Any] | None:
    env_file = load_env_file(env_path)
    if env_file.get("DB_TYPE") != "postgresdb":
        return None
    db = env_file.get("DB_POSTGRESDB_DATABASE") or "n8n"
    user = env_file.get("DB_POSTGRESDB_USER") or "n8n"
    host = env_file.get("DB_POSTGRESDB_HOST") or "localhost"
    port = env_file.get("DB_POSTGRESDB_PORT") or "5432"
    password = env_file.get("DB_POSTGRESDB_PASSWORD") or ""
    query = """
select json_build_object(
  'id', id,
  'name', name,
  'active', active,
  'updatedAt', "updatedAt",
  'nodes', nodes
)::text
from workflow_entity
order by "updatedAt" desc;
"""
    try:
        completed = subprocess.run(
            ["psql", "-h", host, "-p", port, "-U", user, "-d", db, "-Atc", query],
            env={**os.environ, "PGPASSWORD": password},
            text=True,
            capture_output=True,
            timeout=8,
            check=True,
        )
    except Exception:
        return None
    rows: list[dict[str, Any]] = []
    for line in completed.stdout.splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    summary = summarize_n8n_rows(rows, f"postgres://{host}:{port}/{db}", "postgres")
    summary["envPath"] = str(env_path)
    return summary


def n8n_db_summary(db_path: Path) -> dict[str, Any]:
    out: dict[str, Any] = {
        "path": str(db_path),
        "exists": db_path.exists(),
        "workflowCount": 0,
        "activeCount": 0,
        "inactiveCount": 0,
        "billWorkflowCount": 0,
        "activeBillWorkflowCount": 0,
        "workflows": [],
        "billWorkflows": [],
    }
    if not db_path.exists():
        out["error"] = "n8n database missing"
        return out
    try:
        con = sqlite3.connect(str(db_path))
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "select id, name, active, updatedAt, nodes from workflow_entity order by updatedAt desc"
        ).fetchall()
        con.close()
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
        return out

    rows_as_dicts: list[dict[str, Any]] = []
    for row in rows:
        rows_as_dicts.append({
            "id": row["id"],
            "name": row["name"],
            "active": bool(row["active"]),
            "updatedAt": row["updatedAt"],
            "nodes": row["nodes"],
        })
    return summarize_n8n_rows(rows_as_dicts, str(db_path), "sqlite")


def n8n_summary(db_path: Path, env_path: Path = DEFAULT_N8N_ENV) -> dict[str, Any]:
    return n8n_postgres_summary(env_path) or n8n_db_summary(db_path)


def exported_n8n_workflows(paths: list[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for root in paths:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.json")):
            payload = read_json(path, {})
            if not isinstance(payload, dict) or "nodes" not in payload:
                continue
            rows.append({
                "path": str(path),
                "id": payload.get("id"),
                "name": payload.get("name"),
                "active": bool(payload.get("active")),
                "nodeCount": len(payload.get("nodes") if isinstance(payload.get("nodes"), list) else []),
                "settings": payload.get("settings") if isinstance(payload.get("settings"), dict) else {},
            })
    return rows


def n8n_export_mismatches(db_summary: dict[str, Any], exported: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {str(item.get("id")): item for item in db_summary.get("workflows", []) if item.get("id")}
    by_name = {str(item.get("name")): item for item in db_summary.get("workflows", []) if item.get("name")}
    mismatches: list[dict[str, Any]] = []
    for item in exported:
        live = by_id.get(str(item.get("id"))) or by_name.get(str(item.get("name")))
        if not live:
            mismatches.append({
                "path": item.get("path"),
                "name": item.get("name"),
                "issue": "exported-workflow-not-present-in-live-db",
            })
            continue
        if bool(live.get("active")) != bool(item.get("active")):
            mismatches.append({
                "path": item.get("path"),
                "name": item.get("name"),
                "issue": "export-active-state-disagrees-with-live-db",
                "exportActive": bool(item.get("active")),
                "liveActive": bool(live.get("active")),
            })
    return mismatches


def kanban_summary(db_path: Path) -> dict[str, Any]:
    out: dict[str, Any] = {
        "path": str(db_path),
        "exists": db_path.exists(),
        "taskCount": 0,
        "statusCounts": {},
        "activeRelevantTasks": [],
        "blockedRelevantTasks": [],
    }
    if not db_path.exists():
        out["error"] = "kanban database missing"
        return out
    try:
        con = sqlite3.connect(str(db_path))
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "select id, title, body, status, priority, worker_pid, current_step_key, consecutive_failures, created_at "
            "from tasks order by created_at desc limit 120"
        ).fetchall()
        con.close()
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
        return out

    tasks = [dict(row) for row in rows]
    out["taskCount"] = len(tasks)
    counts: dict[str, int] = {}
    for task in tasks:
        counts[str(task.get("status"))] = counts.get(str(task.get("status")), 0) + 1
    out["statusCounts"] = counts
    relevant = [
        task for task in tasks
        if any(word in f"{task.get('title', '')} {task.get('body', '')}".lower() for word in (
            "bill", "hermes", "n8n", "ai-scientist", "prediction", "topstep", "gengar", "firecrawl"
        ))
    ]
    out["activeRelevantTasks"] = [
        compact_task(task) for task in relevant if task.get("status") in {"running", "ready"}
    ][:20]
    out["blockedRelevantTasks"] = [
        compact_task(task) for task in relevant if task.get("status") == "blocked"
    ][:20]
    return out


def compact_task(task: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": task.get("id"),
        "status": task.get("status"),
        "priority": task.get("priority"),
        "title": task.get("title"),
        "workerPid": task.get("worker_pid"),
        "currentStepKey": task.get("current_step_key"),
        "consecutiveFailures": task.get("consecutive_failures"),
    }


def kanban_blocked_task_triage(kanban: dict[str, Any]) -> dict[str, Any]:
    blocked = kanban.get("blockedRelevantTasks") if isinstance(kanban.get("blockedRelevantTasks"), list) else []
    rows: list[dict[str, Any]] = []
    for task in blocked:
        if not isinstance(task, dict):
            continue
        title = str(task.get("title") or "").lower()
        if "firecrawl" in title or "searxng" in title:
            classification = "parked-optional-research-tooling"
            next_action = "Keep parked until Firecrawl/SearXNG is explicitly installed and scoped as read-only research intake."
        elif "n8n" in title and "activate" in title and "bill" in title:
            classification = "parked-obsolete-n8n-activation"
            next_action = "Do not activate paused Bill workflows from Kanban; live n8n already has reviewed Bill monitoring/research workflows, so any additional workflow must be designed intentionally and kept non-routing."
        elif "prediction" in title or "arbitrage" in title:
            classification = "parked-alpha-research-backlog"
            next_action = "Keep as research backlog until source cards, no-lookahead replay, fillability, and paper-promotion gates exist."
        elif "topstep" in title and "realtime" in title and ("proof" in title or "quote" in title):
            classification = "fulfilled-readonly-topstep-quote-refresh"
            next_action = "Treat as fulfilled read-only quote proof work; current Topstep realtime bridge, data freshness, and preflight artifacts are the deterministic evidence, not execution clearance."
        else:
            classification = "needs-operator-triage"
            next_action = "Review task body and either unblock with deterministic artifacts or park it as research-only."
        triaged = classification != "needs-operator-triage"
        rows.append({
            "id": task.get("id"),
            "title": task.get("title"),
            "status": task.get("status"),
            "classification": classification,
            "triaged": triaged,
            "writesOrders": False,
            "touchesBroker": False,
            "movesFunds": False,
            "readyForExecution": False,
            "nextAction": next_action,
        })
    untriaged = [row for row in rows if not row.get("triaged")]
    return {
        "blockedRelevantCount": len(blocked),
        "triagedCount": sum(1 for row in rows if row.get("triaged")),
        "untriagedCount": len(untriaged),
        "allBlockedRelevantTasksTriaged": bool(blocked) and not untriaged if blocked else True,
        "rows": rows,
        "operatorRead": "Blocked Kanban research/tooling tasks are not execution blockers when triaged as parked, no-order, no-broker research backlog.",
    }


def cron_summary(path: Path) -> dict[str, Any]:
    payload = read_json(path, {})
    jobs = payload.get("jobs", payload if isinstance(payload, list) else [])
    if isinstance(jobs, dict):
        jobs = list(jobs.values())
    jobs = [job for job in jobs if isinstance(job, dict)]
    active = [job for job in jobs if job.get("enabled") is True or job.get("active") is True or job.get("status") is True]
    execution_like_terms = ("bridge", "execute", "execution", "fund", "swap", "deposit", "topstep", "gengar")
    active_execution_like = [
        {
            "id": job.get("id"),
            "name": job.get("name"),
            "schedule": job.get("schedule"),
            "promptSample": str(job.get("prompt") or job.get("command") or "")[:220],
        }
        for job in active
        if any(term in f"{job.get('name', '')} {job.get('prompt', '')} {job.get('command', '')}".lower() for term in execution_like_terms)
    ]
    return {
        "path": str(path),
        "exists": path.exists(),
        "jobCount": len(jobs),
        "activeCount": len(active),
        "activeExecutionLikeCount": len(active_execution_like),
        "activeExecutionLike": active_execution_like[:30],
        "operatorRead": "Execution-like active cron names are review targets only unless cron-state-validator has cleared them; execution still remains locked unless daily/broker gates pass.",
    }


def cron_validator_review(path: Path) -> dict[str, Any]:
    payload = read_json(path, {})
    trust = payload.get("cron_trust") if isinstance(payload.get("cron_trust"), dict) else {}
    issues = payload.get("issues") if isinstance(payload.get("issues"), list) else []
    blocking_issues = [
        item for item in issues
        if isinstance(item, dict) and item.get("severity") in {"P0", "P1"}
    ]
    cleared = (
        bool(payload)
        and trust.get("activeDirtyExecutionLiveScriptReferenceCount", 0) == 0
        and trust.get("quarantinedScriptReferenceCount", 0) == 0
        and trust.get("activeTradingAgentBackedCount", 0) == 0
        and trust.get("noAgentMetadataMismatchCount", 0) == 0
        and trust.get("activeShadowCronScriptGuardrailDriftCount", 0) == 0
        and blocking_issues == []
    )
    return {
        "path": str(path),
        "exists": path.exists(),
        "summary": payload.get("summary", "missing"),
        "cleared": cleared,
        "blockingIssueCount": len(blocking_issues),
        "diagnosticIssueCount": len(issues) - len(blocking_issues),
        "activeDirtyExecutionLiveScriptReferenceCount": trust.get("activeDirtyExecutionLiveScriptReferenceCount", "missing"),
        "quarantinedScriptReferenceCount": trust.get("quarantinedScriptReferenceCount", "missing"),
        "activeTradingAgentBackedCount": trust.get("activeTradingAgentBackedCount", "missing"),
        "noAgentMetadataMismatchCount": trust.get("noAgentMetadataMismatchCount", "missing"),
        "activeShadowCronScriptGuardrailDriftCount": trust.get("activeShadowCronScriptGuardrailDriftCount", "missing"),
        "operatorRead": "Execution-like cron names are considered reviewed only when cron-state-validator has no P0/P1 issues and no dirty/quarantined execution references.",
    }


def latest_ai_scientist_final_info(template_dir: Path) -> Path:
    candidates = sorted(
        template_dir.glob("test_run*/final_info.json"),
        key=lambda path: path.stat().st_mtime if path.exists() else 0,
        reverse=True,
    )
    for path in candidates:
        info = read_json(path, {})
        if isinstance(info, dict) and isinstance(info.get("AlphaStrategyTemplate"), dict):
            return path
    return template_dir / "test_run" / "final_info.json"


def ai_scientist_template_summary(template_dir: Path) -> dict[str, Any]:
    experiment = template_dir / "experiment.py"
    prompt = template_dir / "prompt.json"
    ideas = template_dir / "ideas.json"
    final_info = latest_ai_scientist_final_info(template_dir)
    info = read_json(final_info, {})
    strategy = info.get("AlphaStrategyTemplate") if isinstance(info, dict) else None
    safety = strategy.get("safety", {}) if isinstance(strategy, dict) else {}
    means = strategy.get("means", {}) if isinstance(strategy, dict) else {}
    experiment_payload = strategy.get("experiment", {}) if isinstance(strategy, dict) else {}
    text = experiment.read_text(errors="ignore") if experiment.exists() else ""
    banned_imports = [needle for needle in ("requests", "httpx", "websocket", "subprocess", "socket") if f"import {needle}" in text or f"from {needle}" in text]
    hard_safety_ok = (
        safety.get("research_only") is True
        and safety.get("writes_orders") is False
        and safety.get("touches_broker") is False
        and safety.get("moves_funds") is False
        and means.get("ready_for_execution") is False
        and "template-output-is-not-paper-demo-or-execution-promotion" in (experiment_payload.get("promotion_blockers") or [])
    )
    return {
        "path": str(template_dir),
        "exists": template_dir.exists(),
        "experimentExists": experiment.exists(),
        "promptExists": prompt.exists(),
        "ideasExists": ideas.exists(),
        "finalInfoExists": final_info.exists(),
        "finalInfoPath": str(final_info),
        "decision": experiment_payload.get("decision"),
        "safety": safety,
        "means": means,
        "promotionBlockers": experiment_payload.get("promotion_blockers") or [],
        "bannedRuntimeImports": banned_imports,
        "hardSafetyOk": hard_safety_ok and not banned_imports,
        "readyForPaper": False,
        "readyForExecution": False,
        "operatorRead": "AI-Scientist templates may generate hypotheses and research artifacts only; they cannot approve paper, demo, live, funding, or routing.",
    }


def build_audit(
    *,
    n8n_db: Path = DEFAULT_N8N_DB,
    n8n_env: Path = DEFAULT_N8N_ENV,
    n8n_export_roots: list[Path] | None = None,
    kanban_db: Path = DEFAULT_KANBAN_DB,
    cron_path: Path = DEFAULT_CRON,
    cron_validator_path: Path = DEFAULT_CRON_VALIDATOR,
    ai_template: Path = DEFAULT_AI_TEMPLATE,
    generated_at: str | None = None,
) -> dict[str, Any]:
    exports = exported_n8n_workflows(n8n_export_roots or [ROOT / "ops" / "n8n"])
    n8n = n8n_summary(n8n_db, n8n_env)
    mismatches = n8n_export_mismatches(n8n, exports)
    kanban = kanban_summary(kanban_db)
    kanban_triage = kanban_blocked_task_triage(kanban)
    kanban["blockedTaskTriage"] = kanban_triage
    cron = cron_summary(cron_path)
    cron_review = cron_validator_review(cron_validator_path)
    cron["validatorReview"] = cron_review
    ai_template_summary = ai_scientist_template_summary(ai_template)
    blockers: list[str] = []
    warnings: list[str] = []
    if not ai_template_summary.get("hardSafetyOk"):
        blockers.append("ai-scientist-template-safety-not-cleared")
    if mismatches:
        warnings.append("n8n-export-live-db-mismatch")
    if n8n.get("activeBillWorkflowCount", 0):
        warnings.append("active-bill-related-n8n-workflow-present-review-before-use")
    if kanban.get("blockedRelevantTasks") and not kanban_triage.get("allBlockedRelevantTasksTriaged"):
        warnings.append("blocked-hermes-kanban-tasks-present")
    if cron.get("activeExecutionLikeCount", 0) and not cron_review.get("cleared"):
        warnings.append("active-execution-like-cron-names-require-review")
    operator_actions: list[dict[str, Any]] = []
    if mismatches:
        operator_actions.append({
            "id": "n8n-export-live-db-reconcile",
            "priority": 1,
            "action": "Make exported n8n workflow active flags match the live n8n DB, or explicitly document the intended activation change before import.",
            "writesOrders": False,
            "touchesBroker": False,
        })
    if n8n.get("activeBillWorkflowCount", 0):
        operator_actions.append({
            "id": "n8n-active-bill-workflow-review",
            "priority": 2,
            "action": "Review active Bill/Hermes n8n workflows as monitoring/research only before treating them as part of the control plane.",
            "writesOrders": False,
            "touchesBroker": False,
        })
    if kanban.get("blockedRelevantTasks") and not kanban_triage.get("allBlockedRelevantTasksTriaged"):
        operator_actions.append({
            "id": "hermes-kanban-blocked-task-triage",
            "priority": 3,
            "action": "Triage blocked Hermes Kanban tasks and either unblock with deterministic artifacts or mark them as parked research.",
            "writesOrders": False,
            "touchesBroker": False,
        })
    if cron.get("activeExecutionLikeCount", 0) and not cron_review.get("cleared"):
        operator_actions.append({
            "id": "execution-like-cron-name-review",
            "priority": 4,
            "action": "Review execution-like active cron names against firewall artifacts; names alone do not approve routing.",
            "writesOrders": False,
            "touchesBroker": False,
        })
    return {
        "command": "bill-runtime-architecture-audit",
        "generatedAt": generated_at or utc_now(),
        "decision": "runtime-architecture-visible-execution-locked",
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "movesFunds": False,
        "readyForPaper": False,
        "readyForDemoExpansion": False,
        "readyForExecution": False,
        "blockers": blockers,
        "warnings": warnings,
        "n8n": n8n,
        "n8nExportedWorkflows": exports,
        "n8nExportMismatches": mismatches,
        "hermesKanban": kanban,
        "hermesCron": cron,
        "aiScientistTemplate": ai_template_summary,
        "operatorActions": operator_actions,
        "operatorGuidance": [
            "Use n8n for monitoring, read-only research runs, and notifications only.",
            "Treat Hermes Kanban workers as research assistants until their output is backed by deterministic artifacts.",
            "Keep AI-Scientist templates sandboxed and research-only; never give them broker credentials or execution-path write authority.",
            "Do not clear prediction live, Topstep demo expansion, copy trading, or brokerage routing from this audit.",
        ],
    }


def markdown(payload: dict[str, Any]) -> str:
    n8n = payload.get("n8n", {})
    kanban = payload.get("hermesKanban", {})
    cron = payload.get("hermesCron", {})
    ai = payload.get("aiScientistTemplate", {})
    lines = [
        "# Bill Runtime Architecture Audit",
        "",
        f"Generated: `{payload.get('generatedAt')}`",
        "",
        f"- Decision: `{payload.get('decision')}`",
        f"- Research only: `{payload.get('researchOnly')}`",
        f"- Ready for execution: `{payload.get('readyForExecution')}`",
        f"- Blockers: `{payload.get('blockers')}`",
        f"- Warnings: `{payload.get('warnings')}`",
        "",
        "## n8n",
        "",
        f"- DB: `{n8n.get('path')}`",
        f"- Workflows: `{n8n.get('workflowCount')}` active `{n8n.get('activeCount')}` inactive `{n8n.get('inactiveCount')}`",
        f"- Bill/Hermes workflows: `{n8n.get('billWorkflowCount')}` active `{n8n.get('activeBillWorkflowCount')}`",
        f"- Export/live mismatches: `{payload.get('n8nExportMismatches')}`",
        "",
        "## Hermes Kanban",
        "",
        f"- Task statuses: `{kanban.get('statusCounts')}`",
        f"- Active relevant tasks: `{kanban.get('activeRelevantTasks')}`",
        f"- Blocked relevant tasks: `{kanban.get('blockedRelevantTasks')}`",
        f"- Blocked task triage: `{kanban.get('blockedTaskTriage')}`",
        "",
        "## Hermes Cron",
        "",
        f"- Jobs: `{cron.get('jobCount')}` active `{cron.get('activeCount')}`",
        f"- Active execution-like names: `{cron.get('activeExecutionLikeCount')}`",
        f"- Validator review: `{cron.get('validatorReview')}`",
        f"- Operator read: {cron.get('operatorRead')}",
        "",
        "## AI-Scientist Template",
        "",
        f"- Path: `{ai.get('path')}`",
        f"- Hard safety OK: `{ai.get('hardSafetyOk')}`",
        f"- Decision: `{ai.get('decision')}`",
        f"- Safety: `{ai.get('safety')}`",
        f"- Promotion blockers: `{ai.get('promotionBlockers')}`",
        f"- Banned runtime imports: `{ai.get('bannedRuntimeImports')}`",
        "",
        "## Operator Actions",
        "",
    ]
    for item in payload.get("operatorActions", []):
        lines.append(
            f"- P{item.get('priority')} `{item.get('id')}`: {item.get('action')} "
            f"(writesOrders=`{item.get('writesOrders')}`, touchesBroker=`{item.get('touchesBroker')}`)"
        )
    if not payload.get("operatorActions"):
        lines.append("- None.")
    lines.extend([
        "",
        "## Operator Guidance",
        "",
    ])
    lines.extend(f"- {item}" for item in payload.get("operatorGuidance", []))
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit Bill/Hermes runtime architecture posture")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))
    parser.add_argument("--n8n-db", default=str(DEFAULT_N8N_DB))
    parser.add_argument("--n8n-env", default=str(DEFAULT_N8N_ENV))
    parser.add_argument("--kanban-db", default=str(DEFAULT_KANBAN_DB))
    parser.add_argument("--cron", default=str(DEFAULT_CRON))
    parser.add_argument("--cron-validator", default=str(DEFAULT_CRON_VALIDATOR))
    parser.add_argument("--ai-template", default=str(DEFAULT_AI_TEMPLATE))
    args = parser.parse_args()
    payload = build_audit(
        n8n_db=Path(args.n8n_db),
        n8n_env=Path(args.n8n_env),
        kanban_db=Path(args.kanban_db),
        cron_path=Path(args.cron),
        cron_validator_path=Path(args.cron_validator),
        ai_template=Path(args.ai_template),
    )
    write_json(Path(args.output), payload)
    write_markdown(Path(args.markdown), markdown(payload))
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
