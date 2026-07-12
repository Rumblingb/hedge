#!/usr/bin/env python3
"""London Strategic Edge research client — vault/WS smoke + lane pulls.

Research-only. Never grants route approval, broker truth, sizing, or execution.
Requires LSE_API_KEY in the environment or AgentPay bill.env after email verify
+ key mint at https://londonstrategicedge.com/data
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STATE = Path(os.environ.get("BILL_STATE_DIR", str(ROOT / ".rumbling-hedge/state"))).expanduser()
OUT_DIR = Path(
    os.environ.get(
        "BILL_LSE_RESEARCH_DIR",
        str(ROOT / ".rumbling-hedge/research/lse"),
    )
).expanduser()
DEFAULT_OUTPUT = STATE / "lse-research-smoke.latest.json"
HERMES = Path.home() / "Documents" / "memorybrain" / "Agent-Hermes"
ENV_PATHS = [
    Path.home() / ".hermes/.env",
    Path.home() / "Library/Application Support/AgentPay/bill/bill.env",
]

# Lane-mapped symbols (cash/index proxies — not Topstep CME contract truth)
FUTURES_PROXIES = {
    "NQ": "NAS100/USD",
    "ES": "SPX500/USD",
    "YM": "US30/USD",
    "RTY": "US2000/USD",
}
COT_CODES = ["ES", "NQ", "GC", "CL", "ZW"]
MACRO_SERIES = ["fdtr", "cpi_yoy", "US10Y"]
OPTIONS_UNDERLYINGS = ["QQQ", "SPY", "AAPL"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_secure_env(key: str) -> str | None:
    value = os.environ.get(key)
    if value:
        return value.strip().strip("'\"")
    for path in ENV_PATHS:
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


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str) + "\n")


def base_result(status: str, **extra: Any) -> dict[str, Any]:
    payload = {
        "command": "lse-research-smoke",
        "generatedAt": now_iso(),
        "status": status,
        "decision": "research-only-execution-locked",
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "movesFunds": False,
        "executionAuthority": False,
        "readyForExecution": False,
        "notAllowed": [
            "futures broker truth",
            "route approval",
            "position sizing approval",
            "demo/live enablement",
        ],
        "docs": {
            "home": "https://londonstrategicedge.com/",
            "data": "https://londonstrategicedge.com/data/",
            "api": "https://londonstrategicedge.com/docs/api/",
            "websocket": "https://londonstrategicedge.com/docs/websocket/",
            "python": "https://github.com/londonstrategicedge/lse-data",
        },
        "laneMap": {
            "futures": {
                "use": "NAS100/USD + SPX500/USD candles as cash-index research proxies; COT for ES/NQ positioning context",
                "not": "Topstep/ProjectX broker bars, DOM, or clearance evidence",
                "proxies": FUTURES_PROXIES,
            },
            "options": {
                "use": "options chain/flow/greeks for PUT/VRP research; QQQ/SPY underlyings",
                "not": "brokerage funding or live options orders",
            },
            "prediction": {
                "use": "economic_calendar (US Fed/CPI/NFP) for event-lag mapping context",
                "not": "CLOB truth or paper-promotion clearance",
            },
            "macro": {
                "use": "fdtr/cpi_yoy/US10Y series + bond yields as regime labels",
                "not": "intraday route gates without separate promotion artifact",
            },
        },
    }
    payload.update(extra)
    return payload


def get_client(api_key: str):
    try:
        from lse import LSE
    except ImportError as exc:
        raise SystemExit(
            "lse-data not installed. Run: .venv/bin/pip install 'lse-data[frames]'"
        ) from exc
    return LSE(api_key=api_key)


def sample_rows(rows: Any, n: int = 3) -> list[Any]:
    if rows is None:
        return []
    if hasattr(rows, "head") and callable(rows.head):
        try:
            return rows.head(n).to_dict(orient="records")  # type: ignore[no-any-return]
        except Exception:
            pass
    if isinstance(rows, list):
        return rows[:n]
    return [str(type(rows))]


def safe_call(label: str, fn, *args, **kwargs) -> dict[str, Any]:
    try:
        data = fn(*args, **kwargs)
        count = len(data) if hasattr(data, "__len__") else None
        return {
            "ok": True,
            "label": label,
            "count": count,
            "sample": sample_rows(data),
        }
    except Exception as exc:
        return {"ok": False, "label": label, "error": f"{type(exc).__name__}: {exc}"}


def run_smoke(client, deep: bool = False) -> dict[str, Any]:
    checks: dict[str, Any] = {}
    checks["catalog_futures"] = safe_call("catalog_futures", client.catalog, "futures")
    checks["catalog_index"] = safe_call("catalog_index", client.catalog, "index")
    checks["nq_proxy_1d"] = safe_call(
        "nq_proxy_1d",
        client.candles,
        FUTURES_PROXIES["NQ"],
        "1d",
        start="2026-01-01",
        limit=30,
        order="desc",
    )
    checks["es_proxy_1d"] = safe_call(
        "es_proxy_1d",
        client.candles,
        FUTURES_PROXIES["ES"],
        "1d",
        start="2026-01-01",
        limit=30,
        order="desc",
    )
    checks["cot_es"] = safe_call("cot_es", client.cot, "ES")
    checks["econ_calendar_us"] = safe_call(
        "econ_calendar_us",
        client.economic_calendar,
        region="US",
        order="desc",
        limit=20,
    )
    checks["macro_fdtr"] = safe_call("macro_fdtr", client.economics, "fdtr")
    checks["us10y"] = safe_call("us10y", client.series, "US10Y", start="2020-01-01")

    if deep:
        checks["options_qqq"] = safe_call(
            "options_qqq", client.options, "QQQ", type="put", max_dte=45
        )
        checks["options_flow_puts"] = safe_call(
            "options_flow_puts",
            client.options_flow,
            "SPY",
            type="put",
            min_premium=100_000,
        )
        checks["nq_proxy_5m"] = safe_call(
            "nq_proxy_5m",
            client.candles,
            FUTURES_PROXIES["NQ"],
            "5m",
            start="2026-07-01",
            limit=200,
            order="desc",
        )

    ok = all(v.get("ok") for v in checks.values() if isinstance(v, dict) and "ok" in v)
    return {
        "ok": ok,
        "checks": checks,
        "passCount": sum(1 for v in checks.values() if isinstance(v, dict) and v.get("ok")),
        "failCount": sum(1 for v in checks.values() if isinstance(v, dict) and v.get("ok") is False),
    }


def pull_lane_samples(client) -> dict[str, Any]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    saved: dict[str, Any] = {}

    for label, symbol in FUTURES_PROXIES.items():
        rows = client.candles(symbol, "1d", start="2024-01-01", limit=5000, order="asc")
        path = OUT_DIR / f"{label.lower()}-proxy-1d.json"
        write_json(path, {"symbol": symbol, "timeframe": "1d", "rows": rows})
        saved[label] = {"path": str(path), "rows": len(rows) if hasattr(rows, "__len__") else None}

    for code in COT_CODES:
        try:
            rows = client.cot(code)
            path = OUT_DIR / f"cot-{code.lower()}.json"
            write_json(path, {"code": code, "rows": rows})
            saved[f"cot_{code}"] = {"path": str(path), "rows": len(rows) if hasattr(rows, "__len__") else None}
        except Exception as exc:
            saved[f"cot_{code}"] = {"error": f"{type(exc).__name__}: {exc}"}

    events = client.economic_calendar(region="US", order="desc", limit=200)
    path = OUT_DIR / "economic-calendar-us.json"
    write_json(path, {"region": "US", "rows": events})
    saved["economic_calendar_us"] = {
        "path": str(path),
        "rows": len(events) if hasattr(events, "__len__") else None,
    }

    cpi_events = client.economic_calendar(region="US", event="CPI", order="desc", limit=500)
    cpi_path = OUT_DIR / "economic-calendar-us-cpi-event500-desc.json"
    write_json(
        cpi_path,
        {"region": "US", "event": "CPI", "order": "desc", "limit": 500, "rows": cpi_events},
    )
    saved["economic_calendar_us_cpi_event500"] = {
        "path": str(cpi_path),
        "rows": len(cpi_events) if hasattr(cpi_events, "__len__") else None,
    }

    for series in MACRO_SERIES:
        try:
            rows = client.economics(series) if series != "US10Y" else client.series(series)
            path = OUT_DIR / f"macro-{series.lower()}.json"
            write_json(path, {"series": series, "rows": rows})
            saved[series] = {"path": str(path), "rows": len(rows) if hasattr(rows, "__len__") else None}
        except Exception as exc:
            saved[series] = {"error": f"{type(exc).__name__}: {exc}"}

    return {"outDir": str(OUT_DIR), "artifacts": saved}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deep", action="store_true", help="Include options flow/chain checks")
    parser.add_argument("--pull", action="store_true", help="Write lane sample JSON under research/lse")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--markdown", type=Path, default=None)
    args = parser.parse_args()

    api_key = read_secure_env("LSE_API_KEY")
    if not api_key:
        payload = base_result(
            "BLOCKED",
            reason="missing-LSE_API_KEY",
            nextSteps=[
                "Verify email for vishar.rumbling+lse@gmail.com (LSE sent VERIFY_EMAIL)",
                "Sign in at https://londonstrategicedge.com/data and mint/copy lse_live_ key",
                "export LSE_API_KEY=... into AgentPay bill.env",
                "Re-run: npm run bill:lse-research-smoke",
            ],
            accountEmail=read_secure_env("LSE_ACCOUNT_EMAIL"),
            accountConfigured=bool(read_secure_env("LSE_ACCOUNT_EMAIL")),
        )
        write_json(args.output, payload)
        print(json.dumps({"status": "BLOCKED", "reason": "missing-LSE_API_KEY", "output": str(args.output)}))
        return 2

    client = get_client(api_key)
    smoke = run_smoke(client, deep=args.deep)
    pulls = pull_lane_samples(client) if args.pull else None
    status = "PASS" if smoke["ok"] else "FAIL"
    payload = base_result(
        status,
        apiKeyConfigured=True,
        smoke=smoke,
        pulls=pulls,
        outputDir=str(OUT_DIR) if args.pull else None,
    )
    write_json(args.output, payload)

    md_path = args.markdown or (HERMES / f"lse-research-smoke-{datetime.now(timezone.utc).date().isoformat()}.md")
    try:
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(
            "\n".join(
                [
                    f"# LSE Research Smoke - {datetime.now(timezone.utc).date().isoformat()}",
                    "",
                    f"- Status: `{status}`",
                    f"- Artifact: `{args.output}`",
                    "- Authority: research-only / execution locked",
                    f"- Pass/fail: {smoke.get('passCount')}/{smoke.get('failCount')}",
                    "",
                    "Lane map: futures cash-index proxies + COT; options greeks/flow; US econ calendar; macro series.",
                    "Never use LSE as Topstep broker truth.",
                    "",
                ]
            )
        )
        payload["markdown"] = str(md_path)
        write_json(args.output, payload)
    except Exception:
        pass

    print(json.dumps({"status": status, "passCount": smoke.get("passCount"), "failCount": smoke.get("failCount"), "output": str(args.output)}))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
