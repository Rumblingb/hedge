#!/usr/bin/env python3
"""Audit free/keyed research feeds without granting execution authority."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
HERMES = Path.home() / "Documents" / "memorybrain" / "Agent-Hermes"
DEFAULT_OUTPUT = STATE / "free-data-feed-audit.latest.json"
DEFAULT_MARKDOWN = HERMES / f"free-data-feed-audit-{datetime.now(timezone.utc).date().isoformat()}.md"
ENV_PATHS = [
    Path.home() / ".hermes/.env",
    Path.home() / "Library/Application Support/AgentPay/bill/bill.env",
]


def read_secure_env(key: str, env_paths: list[Path] | None = None) -> str | None:
    value = os.environ.get(key)
    if value:
        return value.strip().strip("'\"")
    for path in env_paths or ENV_PATHS:
        if not path.exists():
            continue
        for line in path.read_text(errors="ignore").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.startswith("export "):
                stripped = stripped[7:]
            if "=" not in stripped:
                continue
            name, raw = stripped.split("=", 1)
            if name.strip() == key:
                return raw.strip().strip("'\"")
    return None


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def env_status(keys: list[str], env_paths: list[Path] | None = None) -> dict[str, Any]:
    present = [key for key in keys if read_secure_env(key, env_paths)]
    return {
        "required": keys,
        "present": present,
        "configured": len(present) == len(keys),
        "missing": [key for key in keys if key not in present],
    }


def provider(
    provider_id: str,
    name: str,
    keys: list[str],
    role: str,
    command: str | None = None,
    artifact: dict[str, Any] | None = None,
    env_paths: list[Path] | None = None,
    native_collector: bool = False,
    current_plan_available: bool = True,
    notes: list[str] | None = None,
) -> dict[str, Any]:
    status = env_status(keys, env_paths)
    artifact = artifact or {}
    usable_artifact = artifact.get("status") == "PASS" or artifact.get("dataUsable") is True
    wired = bool(command or native_collector)
    configured = bool(status["configured"] or usable_artifact)
    if not current_plan_available:
        mode = "optional-future"
    else:
        mode = "wired-research" if wired and configured else "configured-not-wired" if configured else "missing-config"
    return {
        "id": provider_id,
        "name": name,
        "configured": configured,
        "wired": wired,
        "mode": mode,
        "env": status,
        "command": command,
        "artifactStatus": artifact.get("status"),
        "artifactDataUsable": artifact.get("dataUsable"),
        "role": role,
        "allowedInfluence": [
            "research hypotheses",
            "context labels",
            "macro/news timing",
            "prediction-market event studies",
            "shadow/advisory filters",
        ],
        "notAllowed": [
            "futures broker truth",
            "route approval",
            "position sizing approval",
            "demo/live enablement",
            "funding or withdrawals",
        ],
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "movesFunds": False,
        "executionAuthority": False,
        "readyForExecution": False,
        "notes": notes or [],
    }


def build_audit(env_paths: list[Path] | None = None) -> dict[str, Any]:
    finnhub = read_json(STATE / "finnhub-news.latest.json")
    topstep_realtime = read_json(STATE / "topstep-realtime-proof.latest.json")
    topstep_market_data = read_json(STATE / "topstep-market-data-smoke.latest.json")
    topstep_artifact = topstep_realtime if topstep_realtime.get("status") == "PASS" else topstep_market_data
    providers = [
        provider(
            "topstepx-projectx",
            "TopstepX / ProjectX",
            ["RH_TOPSTEP_USERNAME", "RH_TOPSTEP_API_KEY"],
            "Primary broker-relevant futures market-data and reconciliation path when session safety is clear.",
            command="bill:topstep-market-data-smoke / bill:topstep-realtime-proof",
            artifact=topstep_artifact,
            env_paths=env_paths,
            native_collector=True,
            notes=["Not a free data hack; this is the broker-relevant path. Still cannot grant trade permission by itself."],
        ),
        provider(
            "finnhub",
            "Finnhub",
            ["FINNHUB_API_KEY"],
            "News, economic-calendar, sentiment, and prediction event-lag context.",
            command="npm run --silent bill:finnhub-news",
            artifact=finnhub,
            env_paths=env_paths,
            native_collector=True,
        ),
        provider(
            "fred",
            "FRED",
            ["FRED_API_KEY"],
            "Macro/rates regime labels and historical context.",
            command="npm run bill:research-collect",
            env_paths=env_paths,
            native_collector=True,
            notes=["FRED can produce false positives in calendar context; cross-check red-folder events before using as a gate."],
        ),
        provider(
            "alpha-vantage",
            "Alpha Vantage",
            ["ALPHA_VANTAGE_API_KEY"],
            "Supplemental equities, FX, crypto, fundamentals, and indicator research.",
            env_paths=env_paths,
            native_collector=False,
        ),
        provider(
            "polygon",
            "Polygon",
            ["RH_POLYGON_API_KEY"],
            "Options/equities/crypto bars and future keyed research collection.",
            command="npm run bill:research-collect",
            env_paths=env_paths,
            native_collector=True,
        ),
        provider(
            "alpaca-paper",
            "Alpaca Paper/Data",
            ["ALPACA_API_KEY", "ALPACA_SECRET_KEY"],
            "Equities/options/crypto paper and research sandbox; not Topstep futures broker truth.",
            command="bill:positioning-status / bill:dealer-gamma-status",
            env_paths=env_paths,
            native_collector=True,
            notes=[
                "Native repo collectors can use Alpaca for options snapshots and underlying equity snapshots.",
                "Alpaca remains non-futures research/paper context; it cannot clear Topstep broker truth, route approval, or futures sizing gates.",
            ],
        ),
        provider(
            "databento",
            "Databento",
            ["DATABENTO_API_KEY"],
            "Optional future depth/order-flow research once billing is solved.",
            command="bill:databento-realtime-smoke / bill:databento-orderflow-feature-smoke",
            env_paths=env_paths,
            native_collector=True,
            current_plan_available=False,
            notes=[
                "Optional future depth/order-flow research only; keep it out of current blocker clearance because billing/cost is not part of the near-term Topstep path.",
                "Current blocker path should not depend on Databento because TopstepX/ProjectX is the broker-relevant futures path.",
            ],
        ),
        provider(
            "nous",
            "Nous Portal",
            ["NOUS_API_KEY"],
            "Model provider for research/analysis agents, not a market-data source.",
            env_paths=env_paths,
            native_collector=False,
            notes=["Treat present keys as unverified until a provider smoke test passes; never expose the secret value."],
        ),
    ]
    wired = [row["id"] for row in providers if row["mode"] == "wired-research"]
    configured_not_wired = [row["id"] for row in providers if row["mode"] == "configured-not-wired"]
    optional_future = [row["id"] for row in providers if row["mode"] == "optional-future"]
    missing = [row["id"] for row in providers if row["mode"] == "missing-config"]
    return {
        "command": "free-data-feed-audit",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "decision": "research-feeds-visible-execution-locked",
        "preferredFuturesDataPath": "topstepx-projectx",
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "movesFunds": False,
        "executionAuthority": False,
        "readyForExecution": False,
        "summary": {
            "wiredResearchFeeds": wired,
            "configuredButNotNative": configured_not_wired,
            "optionalFutureResearch": optional_future,
            "missingConfig": missing,
            "providerCount": len(providers),
        },
        "policy": [
            "TopstepX/ProjectX remains futures broker truth when session safety is clear.",
            "Finnhub/FRED/Alpha Vantage/Polygon/Alpaca can add research context only.",
            "Databento stays optional future depth/order-flow research, not a current blocker dependency.",
            "Free feeds may improve labels, timing, filters, and prediction-market studies; they cannot approve orders.",
            "Daily plan, broker reconciliation, source hygiene, and goal audit still gate any capital risk.",
        ],
        "providers": providers,
    }


def render_markdown(audit: dict[str, Any]) -> str:
    lines = [
        "# Free Data Feed Audit",
        "",
        f"Generated: `{audit['generatedAt']}`",
        "",
        f"Decision: `{audit['decision']}`",
        "",
        "## Policy",
        "",
    ]
    lines.extend(f"- {item}" for item in audit["policy"])
    lines.extend(["", "## Providers", ""])
    for row in audit["providers"]:
        lines.append(f"### {row['name']}")
        lines.append(f"- Mode: `{row['mode']}`")
        lines.append(f"- Role: {row['role']}")
        lines.append(f"- Command: `{row['command'] or 'not wired'}`")
        lines.append(f"- Execution authority: `{row['executionAuthority']}`")
        if row["notes"]:
            for note in row["notes"]:
                lines.append(f"- Note: {note}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit free/keyed Bill research feeds.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--compact", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    audit = build_audit()
    if not args.dry_run:
        output = Path(args.output)
        markdown = Path(args.markdown)
        output.parent.mkdir(parents=True, exist_ok=True)
        markdown.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n")
        markdown.write_text(render_markdown(audit))
    if args.compact:
        print(json.dumps({
            "decision": audit["decision"],
            "wiredResearchFeeds": audit["summary"]["wiredResearchFeeds"],
            "configuredButNotNative": audit["summary"]["configuredButNotNative"],
            "missingConfig": audit["summary"]["missingConfig"],
            "readyForExecution": audit["readyForExecution"],
        }, sort_keys=True))
    else:
        print(json.dumps(audit, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
