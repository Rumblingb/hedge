#!/usr/bin/env python3
"""Build a read-only timestamp/coverage dataset for prediction event research.

This sits between strict news-to-market mapping and event-lag replay. It makes
the event timestamp, CLOB token, pre-event quote coverage, and post-event quote
coverage explicit so agents do not confuse stale mappings with paper evidence.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.prediction_event_lag_replay import (
    candidate_rows,
    clob_paths_from_glob,
    load_quotes,
    parse_time_ms,
    quote_at_or_after,
    quote_before,
    read_json,
)


STATE = ROOT / ".rumbling-hedge" / "state"
CLOB_DIR = ROOT / ".rumbling-hedge" / "prediction" / "clob"
MAPPING_PLAN = STATE / "prediction-event-market-mapping-plan.latest.json"
OUT = STATE / "prediction-event-timestamp-dataset.latest.json"
VAULT = Path.home() / "Documents" / "memorybrain"


def now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def current_utc_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def default_markdown_path() -> Path:
    return VAULT / "Agent-Hermes" / f"prediction-event-timestamp-dataset-{current_utc_date()}.md"


def iso_from_ms(value: int | None) -> str | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc).isoformat()


def coverage_status(*, asset: str, event_ts_ms: int | None, quote_count: int, has_pre: bool, complete_windows: int) -> str:
    if not asset:
        return "missing-clob-token"
    if event_ts_ms is None:
        return "invalid-event-timestamp"
    if quote_count <= 0:
        return "no-quotes-for-clob-token"
    if has_pre and complete_windows > 0:
        return "window-range-present"
    if has_pre:
        return "missing-post-event-window"
    if complete_windows > 0:
        return "missing-pre-event-window"
    return "missing-pre-and-post-window"


def build_dataset(
    *,
    mapping_plan: dict[str, Any],
    clob_paths: list[Path],
    pre_minutes: int = 30,
    horizons_minutes: list[int] | None = None,
    generated_at_ms: int | None = None,
) -> dict[str, Any]:
    horizons_minutes = horizons_minutes or [15, 30, 60, 120]
    generated_at_ms = generated_at_ms if generated_at_ms is not None else now_ms()
    quotes_by_asset = load_quotes(clob_paths)
    rows: list[dict[str, Any]] = []
    for candidate in candidate_rows(mapping_plan):
        asset = str(candidate.get("clobTokenId") or "")
        event_ts_ms = parse_time_ms(candidate.get("articleDatetime") or candidate.get("published"))
        asset_quotes = quotes_by_asset.get(asset, [])
        pre = quote_before(asset_quotes, event_ts_ms, pre_minutes * 60 * 1000) if event_ts_ms is not None else None
        horizon_rows: list[dict[str, Any]] = []
        if event_ts_ms is not None:
            for horizon in horizons_minutes:
                target_ts = event_ts_ms + horizon * 60 * 1000
                post = quote_at_or_after(asset_quotes, target_ts, target_ts + 60 * 1000)
                horizon_rows.append({
                    "horizonMinutes": horizon,
                    "targetTs": iso_from_ms(target_ts),
                    "hasPostQuote": post is not None,
                    "postQuoteTs": iso_from_ms(post.get("tsMs")) if post else None,
                    "postDelaySec": round((post["tsMs"] - event_ts_ms) / 1000, 3) if post else None,
                })
        complete_windows = sum(1 for item in horizon_rows if item.get("hasPostQuote"))
        status = coverage_status(
            asset=asset,
            event_ts_ms=event_ts_ms,
            quote_count=len(asset_quotes),
            has_pre=pre is not None,
            complete_windows=complete_windows,
        )
        event_age_minutes = round((generated_at_ms - event_ts_ms) / 60000, 3) if event_ts_ms is not None else None
        pre_event_recoverable = bool(event_ts_ms is not None and generated_at_ms < event_ts_ms and pre is None)
        unrecoverable_pre_event = bool(event_ts_ms is not None and generated_at_ms >= event_ts_ms and pre is None)
        rows.append({
            "externalId": candidate.get("externalId"),
            "venue": candidate.get("venue"),
            "category": candidate.get("category"),
            "headline": candidate.get("headline"),
            "question": candidate.get("question"),
            "source": candidate.get("source"),
            "published": candidate.get("published"),
            "articleDatetime": candidate.get("articleDatetime"),
            "eventTs": iso_from_ms(event_ts_ms),
            "eventAgeMinutes": event_age_minutes,
            "clobTokenId": asset,
            "quoteCount": len(asset_quotes),
            "firstQuoteTs": iso_from_ms(asset_quotes[0]["tsMs"]) if asset_quotes else None,
            "lastQuoteTs": iso_from_ms(asset_quotes[-1]["tsMs"]) if asset_quotes else None,
            "hasPreEventQuote": pre is not None,
            "preQuoteTs": iso_from_ms(pre.get("tsMs")) if pre else None,
            "preAgeSec": round((event_ts_ms - pre["tsMs"]) / 1000, 3) if pre and event_ts_ms is not None else None,
            "completePostWindowCount": complete_windows,
            "horizons": horizon_rows,
            "coverageStatus": status,
            "preEventWindowRecoverable": pre_event_recoverable,
            "unrecoverablePreEvent": unrecoverable_pre_event,
            "researchOnly": True,
            "writesOrders": False,
            "touchesBroker": False,
        })

    status_counts = Counter(str(row.get("coverageStatus") or "missing") for row in rows)
    complete_rows = [row for row in rows if row.get("coverageStatus") == "window-range-present"]
    unrecoverable = [row for row in rows if row.get("unrecoverablePreEvent")]
    forward_required = bool(unrecoverable or not complete_rows)
    return {
        "command": "prediction-event-timestamp-dataset",
        "generatedAt": now_iso(),
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "readyForPaper": False,
        "readyForExecution": False,
        "mappingDecision": mapping_plan.get("decision"),
        "candidateCount": len(rows),
        "preMinutes": pre_minutes,
        "horizonsMinutes": horizons_minutes,
        "clobPaths": [str(path) for path in clob_paths],
        "assetsWithQuotes": len(quotes_by_asset),
        "coverageStatusCounts": dict(status_counts),
        "completeWindowTargetCount": len(complete_rows),
        "unrecoverablePreEventTargetCount": len(unrecoverable),
        "forwardCaptureRequired": forward_required,
        "rows": rows,
        "decision": "research-only-event-timestamp-dataset-ready" if rows else "research-only-event-timestamp-dataset-empty",
        "nextAction": (
            "Run standing public CLOB capture before future news windows, then rebuild this dataset before replay."
            if forward_required
            else "Run no-lookahead event-lag replay and keep paper approval blocked until resolved labels and fillability pass."
        ),
        "hardRules": [
            "This timestamp dataset is coverage evidence only, not a directional signal.",
            "Past events without pre-event quotes are unrecoverable; use forward capture for the next event window.",
            "No paper, funding, demo, live, sizing, or broker route is approved by this artifact.",
        ],
    }


def render_markdown(payload: dict[str, Any]) -> str:
    generated_date = str(payload.get("generatedAt") or current_utc_date())[:10]
    lines = [
        f"# Prediction Event Timestamp Dataset - {generated_date}",
        "",
        "Parent hub: [[BILL-CONTROL-HUB]]",
        "",
        "Research-only timestamp and CLOB coverage dataset for event-lag studies.",
        "",
        "## Summary",
        "",
        f"- Decision: `{payload.get('decision')}`",
        f"- Candidates: `{payload.get('candidateCount')}`",
        f"- Coverage status counts: `{payload.get('coverageStatusCounts')}`",
        f"- Complete window targets: `{payload.get('completeWindowTargetCount')}`",
        f"- Unrecoverable pre-event targets: `{payload.get('unrecoverablePreEventTargetCount')}`",
        f"- Forward capture required: `{payload.get('forwardCaptureRequired')}`",
        f"- Ready for paper: `{payload.get('readyForPaper')}`",
        "",
        "## Sample Rows",
        "",
    ]
    for row in (payload.get("rows") or [])[:12]:
        lines.append(
            f"- `{row.get('coverageStatus')}` age `{row.get('eventAgeMinutes')}`m "
            f"pre `{row.get('hasPreEventQuote')}` postWindows `{row.get('completePostWindowCount')}` - {row.get('question')}"
        )
    lines.extend(["", "## Hard Rules", ""])
    for rule in payload.get("hardRules") or []:
        lines.append(f"- {rule}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build prediction event timestamp coverage dataset.")
    parser.add_argument("--mapping-plan", default=str(MAPPING_PLAN))
    parser.add_argument("--clob-glob", default=str(CLOB_DIR / "*-market-channel.jsonl"))
    parser.add_argument("--pre-minutes", type=int, default=30)
    parser.add_argument("--horizons-minutes", default="15,30,60,120")
    parser.add_argument("--output", default=str(OUT))
    parser.add_argument("--markdown-output", default=str(default_markdown_path()))
    args = parser.parse_args()

    horizons = [int(part.strip()) for part in args.horizons_minutes.split(",") if part.strip()]
    payload = build_dataset(
        mapping_plan=read_json(Path(args.mapping_plan)),
        clob_paths=clob_paths_from_glob(args.clob_glob),
        pre_minutes=args.pre_minutes,
        horizons_minutes=horizons,
    )
    out = Path(args.output)
    md = Path(args.markdown_output)
    out.parent.mkdir(parents=True, exist_ok=True)
    md.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    md.write_text(render_markdown(payload))
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
