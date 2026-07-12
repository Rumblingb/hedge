#!/usr/bin/env python3
"""Deterministic manual review for prediction event-lag watch windows.

This is intentionally conservative. It turns sensitivity watch windows into
explicit keep/reject notes so the research loop can learn without converting a
threshold artifact into paper-trading permission.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge/state"
VAULT = Path.home() / "Documents" / "memorybrain"
HERMES = VAULT / "Agent-Hermes"
WATCH_REVIEW = STATE / "prediction-event-lag-watch-review.latest.json"
CAPTURE_CYCLE = STATE / "prediction-event-capture-cycle.latest.json"
OUT = STATE / "prediction-event-lag-manual-review.latest.json"


def default_markdown_path() -> Path:
    review_date = datetime.now(timezone.utc).date().isoformat()
    return HERMES / f"prediction-event-lag-manual-review-{review_date}.md"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def numeric(value: Any, default: float = 0.0) -> float:
    return float(value) if isinstance(value, (int, float)) else default


def fanout_key(window: dict[str, Any]) -> tuple[str, str]:
    return (str(window.get("headline") or ""), str(window.get("eventIso") or ""))


def review_window(window: dict[str, Any], fanout_count: int) -> dict[str, Any]:
    reasons: list[str] = []
    abs_after_spread = numeric(window.get("absMoveAfterHalfSpread"))
    if abs_after_spread <= 0:
        reasons.append("move-does-not-clear-half-spread")
    if fanout_count > 1:
        reasons.append("same-headline-maps-to-multiple-markets")
    horizon_seconds = max(0, numeric(window.get("horizonMinutes")) * 60)
    post_delay = numeric(window.get("postDelaySec"))
    if horizon_seconds and post_delay > horizon_seconds + 90:
        reasons.append("post-quote-outside-horizon-tolerance")
    if numeric(window.get("preAgeSec")) > 1800:
        reasons.append("pre-quote-too-old")

    if "move-does-not-clear-half-spread" in reasons:
        decision = "reject-paper"
        next_action = "Do not retest this threshold as edge; keep only as no-edge context."
    elif reasons:
        decision = "keep-research"
        next_action = "Improve event-market mapping and require fresh forward capture before any paper review."
    else:
        decision = "keep-watch"
        next_action = "Keep as watch-only and require strict replay plus forward capture before paper review."

    return {
        "externalId": window.get("externalId"),
        "clobTokenId": window.get("clobTokenId"),
        "question": window.get("question"),
        "headline": window.get("headline"),
        "eventIso": window.get("eventIso"),
        "scenarioLabel": window.get("scenarioLabel"),
        "horizonMinutes": window.get("horizonMinutes"),
        "midMove": window.get("midMove"),
        "absMoveAfterHalfSpread": window.get("absMoveAfterHalfSpread"),
        "preSpread": window.get("preSpread"),
        "fanoutCount": fanout_count,
        "decision": decision,
        "reasons": reasons,
        "nextAction": next_action,
        "readyForPaper": False,
        "readyForExecution": False,
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
    }


def capture_cycle_observed_reviewed_windows(capture_cycle: dict[str, Any], reviewed: list[dict[str, Any]]) -> bool:
    executed = capture_cycle.get("executedRecorder") if isinstance(capture_cycle.get("executedRecorder"), dict) else {}
    token_ids = {str(token) for token in executed.get("tokenIds", [])} if isinstance(executed.get("tokenIds"), list) else set()
    reviewed_tokens = {str(item.get("clobTokenId")) for item in reviewed if item.get("clobTokenId")}
    if (
        executed.get("publicMarketDataOnly") is True
        and executed.get("writesOrders") is not True
        and executed.get("touchesBroker") is not True
        and bool(reviewed_tokens)
        and bool(token_ids & reviewed_tokens)
    ):
        return True

    latest = capture_cycle.get("latestRecorder") if isinstance(capture_cycle.get("latestRecorder"), dict) else {}
    latest_tokens = {
        str(item.get("tokenId"))
        for item in latest.get("selectedAssets", [])
        if isinstance(item, dict) and item.get("tokenId")
    }
    latest_quality = latest.get("liveQualityDiagnostics") if isinstance(latest.get("liveQualityDiagnostics"), dict) else {}
    latest_tokens.update(
        str(item.get("tokenId"))
        for item in latest_quality.get("assets", [])
        if isinstance(item, dict) and item.get("tokenId")
    )
    latest_is_public_read = (
        latest.get("evidencePresent") is True
        and latest.get("status") == "ok"
        and latest.get("writesOrders") is not True
        and capture_cycle.get("touchesBroker") is not True
        and capture_cycle.get("writesOrders") is not True
    )
    return bool(latest_is_public_read and reviewed_tokens and latest_tokens & reviewed_tokens)


def capture_cycle_covers_reviewed_windows(capture_cycle: dict[str, Any], reviewed: list[dict[str, Any]]) -> bool:
    return (
        capture_cycle.get("captureCycleEvidencePassed") is True
        and capture_cycle_observed_reviewed_windows(capture_cycle, reviewed)
    )


def build_manual_review(watch_review: dict[str, Any], capture_cycle: dict[str, Any] | None = None) -> dict[str, Any]:
    capture_cycle = capture_cycle or {}
    windows = watch_review.get("watchWindows") if isinstance(watch_review.get("watchWindows"), list) else []
    fanout = Counter(fanout_key(window) for window in windows if isinstance(window, dict))
    reviewed = [
        review_window(window, fanout[fanout_key(window)])
        for window in windows
        if isinstance(window, dict)
    ]
    forward_capture_observed = capture_cycle_observed_reviewed_windows(capture_cycle, reviewed)
    forward_capture_evidence_present = capture_cycle_covers_reviewed_windows(capture_cycle, reviewed)
    decision_counts = dict(Counter(str(item.get("decision")) for item in reviewed))
    keep_watch_count = decision_counts.get("keep-watch", 0)
    keep_research_count = decision_counts.get("keep-research", 0)
    reject_count = decision_counts.get("reject-paper", 0)

    blockers: list[str] = []
    if not reviewed:
        blockers.append("no-watch-windows-to-review")
    if keep_watch_count == 0:
        blockers.append("no-window-clears-manual-review-for-paper-discussion")
    if keep_research_count or reject_count:
        blockers.append("event-market-mapping-or-spread-quality-not-paper-grade")
    if forward_capture_evidence_present:
        blockers.append("paper-promotion-evidence-still-required-after-forward-capture")
    elif forward_capture_observed:
        blockers.append("forward-public-clob-capture-observed-but-not-paper-grade")
    else:
        blockers.append("forward-public-clob-capture-still-required")

    return {
        "command": "prediction-event-lag-manual-review",
        "generatedAt": now_iso(),
        "sourceArtifact": ".rumbling-hedge/state/prediction-event-lag-watch-review.latest.json",
        "decision": "research-only-manual-review-no-paper" if keep_watch_count == 0 else "research-only-manual-review-watch",
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "readyForPaper": False,
        "readyForExecution": False,
        "watchReviewDecision": watch_review.get("decision", "missing"),
        "captureCycleDecision": capture_cycle.get("decision", "missing"),
        "captureCycleBlockers": capture_cycle.get("blockers") if isinstance(capture_cycle.get("blockers"), list) else [],
        "forwardCaptureObserved": forward_capture_observed,
        "forwardCaptureEvidencePresent": forward_capture_evidence_present,
        "watchWindowCount": len(windows),
        "reviewedWindowCount": len(reviewed),
        "decisionCounts": decision_counts,
        "reviewedWindows": reviewed,
        "blockers": blockers,
        "nextAction": (
            "Stop threshold chasing on these stale windows; improve event-market mapping and keep standing public CLOB capture running through future news windows."
            if keep_watch_count == 0
            else "Forward capture exists for the watch token; require resolved-label/post-spread paper gate review before any paper discussion."
            if forward_capture_evidence_present
            else "Forward capture observed the watch token, but failed the paper-grade evidence gate; fix fillability, mapping, and no-lookahead windows before more paper discussion."
            if forward_capture_observed
            else "Treat surviving watch windows as research-only until strict no-lookahead replay and forward capture pass."
        ),
        "hardRules": [
            "This review never approves paper, funding, demo, live, sizing, or broker routes.",
            "A threshold-sensitive move must clear spread and mapping review before it can remain a watch candidate.",
            "Forward public CLOB capture is only a research input; resolved labels, spread-adjusted evidence, and manual/model review remain required.",
        ],
    }


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Prediction Event Lag Manual Review",
        "",
        "Parent hub: [[BILL-CONTROL-HUB]]",
        "",
        "Research-only keep/reject notes for the event-lag watch windows.",
        "",
        "## Summary",
        "",
        f"- Decision: `{payload.get('decision')}`",
        f"- Reviewed windows: `{payload.get('reviewedWindowCount')}`",
        f"- Decision counts: `{payload.get('decisionCounts')}`",
        f"- Forward capture observed: `{payload.get('forwardCaptureObserved')}`",
        f"- Forward capture evidence present: `{payload.get('forwardCaptureEvidencePresent')}`",
        f"- Capture cycle blockers: `{payload.get('captureCycleBlockers')}`",
        f"- Ready for paper: `{payload.get('readyForPaper')}`",
        f"- Blockers: `{payload.get('blockers')}`",
        f"- Next action: {payload.get('nextAction')}",
        "",
        "## Window Reviews",
        "",
    ]
    for item in payload.get("reviewedWindows") or []:
        lines.append(
            f"- `{item.get('decision')}` external `{item.get('externalId')}` "
            f"move `{item.get('midMove')}` afterHalfSpread `{item.get('absMoveAfterHalfSpread')}` "
            f"fanout `{item.get('fanoutCount')}` reasons `{item.get('reasons')}` "
            f"question `{item.get('question')}`"
        )
    lines.extend(["", "## Hard Rules", ""])
    for rule in payload.get("hardRules") or []:
        lines.append(f"- {rule}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Review prediction event-lag watch windows conservatively.")
    parser.add_argument("--watch-review", default=str(WATCH_REVIEW))
    parser.add_argument("--capture-cycle", default=str(CAPTURE_CYCLE))
    parser.add_argument("--output", default=str(OUT))
    parser.add_argument("--markdown-output", default=None)
    args = parser.parse_args()

    payload = build_manual_review(
        read_json(Path(args.watch_review)),
        capture_cycle=read_json(Path(args.capture_cycle)),
    )
    out = Path(args.output)
    md = Path(args.markdown_output) if args.markdown_output else default_markdown_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    md.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    md.write_text(render_markdown(payload))
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
