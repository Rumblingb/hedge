#!/usr/bin/env python3
"""Deterministic no-agent signal quality advisor for Bill/Hermes.

This replaces an LLM-backed cron review when model quota is exhausted. It reads
state artifacts, scores freshness/consistency/sizing sanity, and writes a
research-only JSON report. It never routes, sizes, or submits orders.
"""

from __future__ import annotations

import json
import math
import time
from datetime import datetime, time as dt_time, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


HOME = Path.home()
REPO_STATE = HOME / "hedge/.rumbling-hedge/state"
REPO_BRAIN = HOME / "hedge/.rumbling-hedge/brain"
HOME_STATE = HOME / ".rumbling-hedge/state"
HOME_BRAIN = HOME / ".rumbling-hedge/brain"
OUT = REPO_STATE / "signal-quality-advisor.latest.json"
MAX_FRESH_AGE_S = 2 * 3600
EASTERN = ZoneInfo("America/New_York")
US_EQUITY_OPEN = dt_time(9, 30)
US_EQUITY_CLOSE = dt_time(16, 0)

INPUTS = {
    "vol_regime_gate": "vol-regime-gate.latest.json",
    "microstructure": "microstructure-filter.latest.json",
    "failure_rag": "failure-rag.latest.json",
    "multitf_confirmation": "multitf-confirmation.latest.json",
    "risk_sizing": "risk-aware-sizing.latest.json",
    "arbitration": "arbitration.latest.json",
    "noise": "noise-analysis.latest.json",
    "brain_state": "brain-state.latest.json",
}

SHADOW_INPUTS = {
    "dom_proxy": "dom-proxy-signal.latest.json",
    "kalman_pairs": "kalman-pairs-signal.latest.json",
    "whale_flow": "whale-flow-signal.latest.json",
    "rolling_window": "rolling-window-params.latest.json",
}


def read_json(name: str) -> tuple[dict[str, Any], Path | None, int | None]:
    paths = [REPO_STATE / name, HOME_STATE / name]
    if name == "brain-state.latest.json":
        paths = [REPO_BRAIN / name, HOME_BRAIN / name, REPO_STATE / name, HOME_STATE / name]
    candidates: list[tuple[dict[str, Any], Path, int]] = []
    for path in paths:
        if not path.exists():
            continue
        try:
            age = int(time.time() - path.stat().st_mtime)
            candidates.append((json.loads(path.read_text()), path, age))
        except Exception:
            return {}, path, None
    fresh = [candidate for candidate in candidates if candidate[2] <= MAX_FRESH_AGE_S]
    if fresh:
        return fresh[0]
    if candidates:
        return min(candidates, key=lambda candidate: candidate[2])
    return {}, None, None


def parse_payload_timestamp(payload: dict[str, Any]) -> datetime | None:
    if not isinstance(payload, dict):
        return None
    raw = payload.get("timestamp") or payload.get("ts") or payload.get("generatedAt") or payload.get("generated_at")
    if not raw:
        return None
    text = str(raw)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def payload_timestamp_age_seconds(payload: dict[str, Any], now: float | None = None) -> int | None:
    parsed = parse_payload_timestamp(payload)
    if parsed is None:
        return None
    now = time.time() if now is None else now
    return max(0, int(now - parsed.timestamp()))


def parse_shadow_data_timestamp(payload: dict[str, Any]) -> datetime | None:
    if not isinstance(payload, dict):
        return None
    for key in (
        "last_bar_time",
        "lastBarTime",
        "last_bar_timestamp",
        "lastBarTimestamp",
        "sourceLastTimestamp",
        "source_last_timestamp",
        "latestBarTime",
    ):
        value = payload.get(key)
        if not value:
            continue
        text = str(value)
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    return None


def shadow_data_age_seconds(payload: dict[str, Any], now: float | None = None) -> int | None:
    parsed = parse_shadow_data_timestamp(payload)
    if parsed is None:
        return None
    now = time.time() if now is None else now
    return max(0, int(now - parsed.timestamp()))


def previous_weekday(day):
    day = day - timedelta(days=1)
    while day.weekday() >= 5:
        day = day - timedelta(days=1)
    return day


def next_weekday(day):
    day = day + timedelta(days=1)
    while day.weekday() >= 5:
        day = day + timedelta(days=1)
    return day


def us_equity_session_context(now_utc: datetime, payload_dt: datetime | None) -> dict[str, Any] | None:
    if payload_dt is None:
        return None
    now_et = now_utc.astimezone(EASTERN)
    payload_et = payload_dt.astimezone(EASTERN)
    today = now_et.date()
    if today.weekday() < 5 and now_et.time() >= US_EQUITY_OPEN:
        current_session_day = today
    else:
        current_session_day = previous_weekday(today)
    current_close = datetime.combine(current_session_day, US_EQUITY_CLOSE, tzinfo=EASTERN)
    next_day = today if today.weekday() < 5 and now_et.time() < US_EQUITY_OPEN else next_weekday(today)
    next_open = datetime.combine(next_day, US_EQUITY_OPEN, tzinfo=EASTERN)
    market_open = today.weekday() < 5 and US_EQUITY_OPEN <= now_et.time() <= US_EQUITY_CLOSE
    no_regular_session_since_payload = (
        payload_et.date() == current_session_day
        and payload_et <= current_close
        and not market_open
        and now_et < next_open
    )
    return {
        "market": "US equities regular session proxy",
        "marketOpenNow": market_open,
        "currentSessionDay": current_session_day.isoformat(),
        "currentSessionClose": current_close.astimezone(timezone.utc).isoformat(),
        "nextRegularOpen": next_open.astimezone(timezone.utc).isoformat(),
        "payloadSessionDay": payload_et.date().isoformat(),
        "noRegularSessionSincePayload": no_regular_session_since_payload,
    }


def expected_market_closed_staleness(label: str | None, payload: dict[str, Any], now: float | None = None) -> dict[str, Any] | None:
    if label != "microstructure":
        return None
    payload_dt = parse_payload_timestamp(payload)
    if payload_dt is None:
        return None
    now_dt = datetime.fromtimestamp(time.time() if now is None else now, tz=timezone.utc)
    session = us_equity_session_context(now_dt, payload_dt)
    if session and session["noRegularSessionSincePayload"]:
        return {
            "staleReason": "market-closed-no-new-regular-session",
            "session": session,
        }
    return None


def source_summary(payload: dict[str, Any], path: Path | None, file_age: int | None, label: str | None = None, now: float | None = None) -> dict[str, Any]:
    payload_age = payload_timestamp_age_seconds(payload, now=now)
    effective_age = payload_age if payload_age is not None else file_age
    closure_context = expected_market_closed_staleness(label, payload, now=now)
    fresh = isinstance(effective_age, int) and effective_age <= MAX_FRESH_AGE_S
    fresh_for_advisory = fresh or bool(closure_context)
    return {
        "path": str(path) if path else None,
        "ageSeconds": effective_age,
        "fileAgeSeconds": file_age,
        "payloadAgeSeconds": payload_age,
        "fresh": fresh_for_advisory,
        "payloadFresh": fresh,
        "staleReason": closure_context.get("staleReason") if closure_context else None,
        "sessionContext": closure_context.get("session") if closure_context else None,
        "present": bool(path),
    }


def clamp(value: float, low: float = 0.0, high: float = 10.0) -> float:
    return max(low, min(high, value))


def number(value: Any, default: float = 0.0) -> float:
    if isinstance(value, (int, float)) and math.isfinite(value):
        return float(value)
    if isinstance(value, str):
        try:
            parsed = float(value)
            if math.isfinite(parsed):
                return parsed
        except Exception:
            return default
    return default


def direction_value(value: Any) -> float:
    if isinstance(value, (int, float)) and math.isfinite(value):
        if value > 0:
            return 1.0
        if value < 0:
            return -1.0
        return 0.0
    text = str(value or "").lower()
    if text in {"1", "+1", "long", "bullish", "buy", "aligned_long"}:
        return 1.0
    if text in {"-1", "short", "bearish", "sell", "aligned_short"}:
        return -1.0
    return 0.0


def details(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("details") if isinstance(payload, dict) else {}
    return value if isinstance(value, dict) else {}


def freshness_score(ages: list[int | None]) -> float:
    present = [age for age in ages if isinstance(age, int)]
    if not present:
        return 0.0
    fresh = sum(1 for age in present if age <= MAX_FRESH_AGE_S)
    return round(10 * fresh / len(ages), 2)


def extract_signals(payloads: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    arb = payloads.get("arbitration") or {}
    rows.append({
        "name": "arbitration",
        "direction": direction_value(arb.get("direction") or arb.get("final_direction")),
        "confidence": number(arb.get("confidence"), 0.0),
        "raw": arb.get("decision") or arb.get("direction"),
    })

    mtf = payloads.get("multitf_confirmation") or {}
    mtf_details = details(mtf)
    rows.append({
        "name": "multitf_confirmation",
        "direction": direction_value(mtf.get("direction") if mtf.get("direction") is not None else mtf.get("alignment")),
        "confidence": number(mtf.get("confidence") if mtf.get("confidence") is not None else mtf.get("modifier"), 0.0),
        "raw": mtf_details.get("confirmation") or mtf.get("alignment") or mtf.get("direction"),
    })

    micro = payloads.get("microstructure") or {}
    micro_details = details(micro)
    verdict = str(micro.get("verdict") or micro.get("status") or micro_details.get("filter_verdict") or "").lower()
    rows.append({
        "name": "microstructure",
        "direction": 0.0,
        "confidence": number(micro.get("confidence"), 1.0 if verdict in {"tight", "pass", "ok"} else 0.3 if verdict else 0.0),
        "raw": verdict or None,
    })

    vol = payloads.get("vol_regime_gate") or {}
    vol_details = details(vol)
    rows.append({
        "name": "vol_regime_gate",
        "direction": 0.0,
        "confidence": number(vol.get("confidence") if vol.get("confidence") is not None else vol_details.get("confidence_multiplier"), 0.0),
        "raw": vol.get("regime") or vol.get("status") or vol_details.get("regime"),
    })

    return rows


def consistency_score(rows: list[dict[str, Any]]) -> float:
    directional = [row for row in rows if row["direction"] != 0 and row["confidence"] > 0]
    if len(directional) < 2:
        return 5.0
    weighted = sum(row["direction"] * row["confidence"] for row in directional)
    total = sum(abs(row["confidence"]) for row in directional) or 1.0
    return round(clamp(abs(weighted / total) * 10), 2)


def microstructure_health_score(rows: list[dict[str, Any]]) -> float:
    row = next((item for item in rows if item.get("name") == "microstructure"), None)
    if not row:
        return 4.0
    raw = str(row.get("raw") or "").lower()
    confidence = number(row.get("confidence"), 0.0)
    if raw in {"tight", "pass", "ok"} and confidence >= 0.8:
        return 8.0
    if raw in {"normal"} or confidence >= 0.5:
        return 5.0
    return 4.0


def sizing_score(payload: dict[str, Any]) -> tuple[float, list[str]]:
    notes: list[str] = []
    payload_details = details(payload)
    contracts = number(
        payload.get("contracts")
        if payload.get("contracts") is not None
        else payload.get("recommended_contracts")
        if payload.get("recommended_contracts") is not None
        else payload.get("size")
        if payload.get("size") is not None
        else payload_details.get("recommended_contracts"),
        0.0,
    )
    if abs(contracts) > 1:
        notes.append(f"recommended size {contracts} exceeds 1-contract research/demo envelope")
        return 2.0, notes
    if not payload:
        notes.append("risk-aware sizing artifact missing")
        return 0.0, notes
    return 8.0, notes


def shadow_signal_integrity(payloads: dict[str, dict[str, Any]]) -> tuple[float, list[str], list[str], list[dict[str, Any]]]:
    blockers: list[str] = []
    warnings: list[str] = []
    rows: list[dict[str, Any]] = []
    for name, payload in payloads.items():
        method = str(payload.get("method") or "").lower()
        evidence = str(payload.get("evidence_level") or "").lower()
        execution_role = str(payload.get("execution_role") or "").lower()
        promoted = payload.get("promoted_for_execution") is True
        tradable = payload.get("tradable_signal") is True
        confidence = number(payload.get("confidence"), 0.0)
        direction = str(payload.get("direction") or payload.get("action") or "neutral").lower()
        components = payload.get("components") if isinstance(payload.get("components"), dict) else {}
        payload_age = payload_timestamp_age_seconds(payload)
        data_dt = parse_shadow_data_timestamp(payload)
        data_age = shadow_data_age_seconds(payload)
        explicit_source_stale = payload.get("source_data_stale") is True
        refreshed_from_stale_source = (
            explicit_source_stale
            or (
                isinstance(payload_age, int)
                and payload_age <= MAX_FRESH_AGE_S
                and isinstance(data_age, int)
                and data_age > MAX_FRESH_AGE_S
            )
        )
        component_statuses = [
            str(component.get("status") or "").lower()
            for component in components.values()
            if isinstance(component, dict)
        ]
        disconnected_components = [
            component_name
            for component_name, component in components.items()
            if isinstance(component, dict)
            and str(component.get("status") or "").lower() in {"not_connected", "unavailable", "disabled"}
        ]
        no_data = (
            "fallback" in method
            or "no_live_data" in evidence
            or any(status in {"no_data", "missing", "fallback_no_data"} for status in component_statuses)
        )
        proxy_only = "proxy" in method or "proxy" in evidence
        shadow_only = (
            "shadow_only" in evidence
            or execution_role in {"diagnostic_only", "research_only"}
            or payload.get("researchOnly") is True
        )
        row = {
            "name": name,
            "method": method or None,
            "evidenceLevel": evidence or None,
            "executionRole": execution_role or None,
            "promotedForExecution": promoted,
            "tradableSignal": tradable,
            "direction": direction,
            "confidence": confidence,
            "payloadAgeSeconds": payload_age,
            "dataTimestamp": data_dt.isoformat() if data_dt else None,
            "dataAgeSeconds": data_age,
            "sourceDataStale": explicit_source_stale,
            "staleThresholdSeconds": payload.get("stale_threshold_seconds"),
            "refreshedFromStaleSourceData": refreshed_from_stale_source,
            "noData": no_data,
            "proxyOnly": proxy_only,
            "shadowOnly": shadow_only,
            "disconnectedComponents": disconnected_components,
        }
        rows.append(row)
        if no_data:
            blockers.append(f"shadow no-data/fallback input: {name}")
        if disconnected_components:
            warnings.append(f"shadow input has disconnected components: {name} ({', '.join(disconnected_components)})")
        if proxy_only:
            warnings.append(f"proxy shadow input cannot confirm execution: {name}")
        if refreshed_from_stale_source:
            warnings.append(f"shadow input refreshed from stale source data: {name}")
        if promoted and shadow_only:
            blockers.append(f"shadow input promoted for execution: {name}")
        if tradable and not promoted:
            blockers.append(f"tradable shadow signal without promotion: {name}")
        if direction not in {"neutral", "exit", "hold", "none", ""} and confidence > 0 and shadow_only:
            warnings.append(f"directional shadow input is research-only: {name}")

    score = clamp(10.0 - (2.0 * len(blockers)) - (0.5 * len(warnings)))
    return round(score, 2), blockers, warnings, rows


def build_report() -> dict[str, Any]:
    payloads: dict[str, dict[str, Any]] = {}
    sources: dict[str, dict[str, Any]] = {}
    for label, filename in INPUTS.items():
        data, path, age = read_json(filename)
        payloads[label] = data
        sources[label] = source_summary(data, path, age, label=label)
    shadow_payloads: dict[str, dict[str, Any]] = {}
    shadow_sources: dict[str, dict[str, Any]] = {}
    for label, filename in SHADOW_INPUTS.items():
        data, path, age = read_json(filename)
        shadow_payloads[label] = data
        shadow_sources[label] = source_summary(data, path, age, label=label)

    rows = extract_signals(payloads)
    sizing, sizing_notes = sizing_score(payloads.get("risk_sizing") or {})
    shadow_score, shadow_blockers, shadow_warnings, shadow_rows = shadow_signal_integrity(shadow_payloads)
    score_parts = {
        "freshness": freshness_score([source["ageSeconds"] for source in sources.values()]),
        "signalConsistency": consistency_score(rows),
        "microstructureHealth": microstructure_health_score(rows),
        "sizingReasonableness": sizing,
        "shadowSignalIntegrity": shadow_score,
    }
    overall = round(sum(score_parts.values()) / len(score_parts), 2)
    blockers: list[str] = []
    warnings: list[str] = []
    stale = [name for name, source in sources.items() if source["present"] and not source["fresh"]]
    missing = [name for name, source in sources.items() if not source["present"]]
    if stale:
        blockers.append(f"stale inputs: {', '.join(stale)}")
    if missing:
        blockers.append(f"missing inputs: {', '.join(missing)}")
    blockers.extend(sizing_notes)
    blockers.extend(shadow_blockers)
    warnings.extend(shadow_warnings)
    stale_shadow_rows = [
        row
        for row in shadow_rows
        if row.get("refreshedFromStaleSourceData") is True or row.get("sourceDataStale") is True
    ]

    return {
        "command": "signal-quality-advisor",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "movesFunds": False,
        "readyForExecution": False,
        "overallRating": overall,
        "scoreParts": score_parts,
        "inputs": sources,
        "shadowInputs": shadow_sources,
        "signalRows": rows,
        "shadowSignalRows": shadow_rows,
        "staleShadowSourceRows": stale_shadow_rows,
        "blockers": blockers,
        "warnings": warnings,
        "decision": "advisory-only; cannot approve, size, or route trades",
    }


def main() -> int:
    report = build_report()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print("=== SIGNAL QUALITY REPORT ===")
    print(f"Timestamp: {report['generatedAt']}")
    print(f"Overall Rating: {report['overallRating']}/10")
    print(f"Decision: {report['decision']}")
    if report["blockers"]:
        print("Blockers:")
        for blocker in report["blockers"]:
            print(f"- {blocker}")
    else:
        print("Blockers: none for advisory read")
    print(f"Wrote: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
