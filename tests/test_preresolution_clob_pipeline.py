"""Tests for the pre-resolution CLOB capture -> corpus build -> resolved-label replay pipeline.

These are offline (no network, no Seagate source) but exercise the FULL real code path:
  - Node capturer in --replay-jsonl mode (reuses recorder selection + book-state logic)
  - Python corpus builder (emits replay's exact schema, microstructure at frac<=0.5)
  - REAL prediction_clob_resolved_label_feature_replay.py harness (forward mode)

No mocks of the replay harness — we invoke it as a subprocess so the genuine
no-edge contract + tautology negative-control are actually exercised.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"
CAPTURE_JS = SCRIPTS / "polymarket_clob_preresolution_capture.mjs"
BUILDER_PY = SCRIPTS / "prediction_clob_preresolution_corpus_builder.py"
REPLAY_PY = SCRIPTS / "prediction_clob_resolved_label_feature_replay.py"

DAY = 86_400_000


@pytest.fixture
def live_offline_fixtures(tmp_path):
    """Near-present timestamps so frac lands in [0, 0.5] pre-resolution window."""
    now = int(time.time() * 1000)
    mk = {
        "m0": ("tok_up_m0", "tok_dn_m0"),
        "m1": ("tok_up_m1", "tok_dn_m1"),
    }
    snapshot, labels, market_times = [], {}, {}
    for i, (mid, (up, dn)) in enumerate(mk.items()):
        start = now - 3 * DAY
        end = now + 4 * DAY
        market_times[mid] = {"start_ts": start, "end_ts": end}
        labels[mid] = i % 2
        for tok, side in [(up, "Yes"), (dn, "No")]:
            snapshot.append({
                "clobTokenId": tok, "marketId": mid,
                "marketQuestion": f"BTC {mid}?", "eventTitle": f"BTC {mid}",
                "outcomeLabel": side, "price": 0.5, "bestBid": 0.49,
                "bestAsk": 0.51, "topBookDepth": 5000, "displayedSize": 5000,
                "expiry": "2026-07-20T00:00:00Z",
            })
    replay = [
        json.dumps({"event_type": "book", "asset_id": "tok_up_m0", "timestamp": "2026-07-10T00:00:00Z",
                    "bids": [{"price": "0.60", "size": "1200"}], "asks": [{"price": "0.62", "size": "800"}]}),
        json.dumps({"event_type": "book", "asset_id": "tok_dn_m0", "timestamp": "2026-07-10T00:00:00Z",
                    "bids": [{"price": "0.38", "size": "600"}], "asks": [{"price": "0.40", "size": "1000"}]}),
        json.dumps({"event_type": "book", "asset_id": "tok_up_m1", "timestamp": "2026-07-10T00:00:00Z",
                    "bids": [{"price": "0.55", "size": "700"}], "asks": [{"price": "0.57", "size": "1100"}]}),
        json.dumps({"event_type": "book", "asset_id": "tok_dn_m1", "timestamp": "2026-07-10T00:00:00Z",
                    "bids": [{"price": "0.43", "size": "900"}], "asks": [{"price": "0.45", "size": "700"}]}),
    ]
    snap_p = tmp_path / "snapshot.json"
    replay_p = tmp_path / "replay.jsonl"
    mt_p = tmp_path / "market_times.json"
    lab_p = tmp_path / "labels.json"
    snap_p.write_text(json.dumps(snapshot))
    replay_p.write_text("\n".join(replay) + "\n")
    mt_p.write_text(json.dumps(market_times))
    lab_p.write_text(json.dumps(labels))
    return snap_p, replay_p, mt_p, lab_p


def run_capture(snap_p, replay_p, mt_p, lab_p, out_dir, state_p):
    r = subprocess.run(
        ["node", str(CAPTURE_JS), "--snapshot", str(snap_p), "--replay-jsonl", str(replay_p),
         "--market-times", str(mt_p), "--labels", str(lab_p), "--out-dir", str(out_dir),
         "--state-path", str(state_p), "--max-elig-frac", "0.5"],
        capture_output=True, text=True, cwd=str(REPO),
    )
    assert r.returncode == 0, r.stderr
    js = json.loads(r.stdout)
    assert js["mode"] == "offline-replay"
    assert js["preResolutionSnapshots"] == 4
    assert js["labelledSnapshots"] == 4
    capture_jsonl = next(out_dir.glob("*-preresolution-market-channel.jsonl"))
    return capture_jsonl, js


def run_replay(corpus_p, max_elig=0.5):
    out = corpus_p.with_suffix(".replay.json")
    md = corpus_p.with_suffix(".replay.md")
    r = subprocess.run(
        ["python3", str(REPLAY_PY), "--corpus", str(corpus_p), "--output", str(out),
         "--markdown-output", str(md), "--max-elig-frac", str(max_elig)],
        capture_output=True, text=True, cwd=str(REPO),
    )
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_capture_emits_preresolution_snapshots(live_offline_fixtures, tmp_path):
    snap_p, replay_p, mt_p, lab_p = live_offline_fixtures
    capture_jsonl, js = run_capture(snap_p, replay_p, mt_p, lab_p, tmp_path / "out", tmp_path / "state.json")
    recs = [json.loads(l) for l in capture_jsonl.read_text().splitlines()]
    snaps = [r for r in recs if r["eventType"] == "pre_resolution_book"]
    assert len(snaps) == 4
    for s in snaps:
        assert 0 <= s["frac"] <= 0.5
        assert s["labelPending"] is False
        assert s["target_up_win"] in (0, 1)
        assert s["upDepthImbalance"] is not None
        assert s["downDepthImbalance"] is not None


def test_corpus_builder_from_capture(live_offline_fixtures, tmp_path):
    snap_p, replay_p, mt_p, lab_p = live_offline_fixtures
    capture_jsonl, _ = run_capture(snap_p, replay_p, mt_p, lab_p, tmp_path / "out", tmp_path / "state.json")
    corpus_p = tmp_path / "corpus.parquet"
    r = subprocess.run(
        ["python3", str(BUILDER_PY), "--capture", str(capture_jsonl), "--labels", str(lab_p),
         "--market-times", str(mt_p), "--output", str(corpus_p), "--max-elig-frac", "0.5"],
        capture_output=True, text=True, cwd=str(REPO),
    )
    assert r.returncode == 0, r.stderr
    df = pd.read_parquet(corpus_p)
    assert len(df) == 4
    # microstructure populated at pre-resolution
    assert bool(df["up_depth_imbalance"].notna().all())
    assert bool(df["down_depth_imbalance"].notna().all())
    assert bool((df["avg_spread"] > 0).all())
    # replay schema requires these columns
    for col in ["market_id", "ts", "target_up_win", "up_bid_depth", "down_ask_depth", "start_ts", "end_ts"]:
        assert col in df.columns


def test_replay_forward_mode_real_harness(live_offline_fixtures, tmp_path):
    snap_p, replay_p, mt_p, lab_p = live_offline_fixtures
    capture_jsonl, _ = run_capture(snap_p, replay_p, mt_p, lab_p, tmp_path / "out", tmp_path / "state.json")
    corpus_p = tmp_path / "corpus.parquet"
    subprocess.run(
        ["python3", str(BUILDER_PY), "--capture", str(capture_jsonl), "--labels", str(lab_p),
         "--market-times", str(mt_p), "--output", str(corpus_p), "--max-elig-frac", "0.5"],
        check=True, capture_output=True, text=True, cwd=str(REPO),
    )
    rep = run_replay(corpus_p)
    # forward mode engages (this is the whole point of t_d6a63517)
    assert rep["mode"] == "pre-resolution-forward"
    assert rep["eligibleRows"] == 4  # 2 markets x 2 tokens captured at pre-resolution
    assert rep["populatedMicrostructureRows"] == rep["eligibleRows"]
    # tautology negative-control gate is intact (real harness runs it)
    assert "negativeControlResolutionBarAuc" in rep


def test_replay_synthetic_40_markets_auc_beats_negative_control(tmp_path):
    """Deterministic >=30-row proof that the genuine no-edge contract fires correctly."""
    corpus_p = tmp_path / "synth.parquet"
    r = subprocess.run(
        ["python3", str(BUILDER_PY), "--synthetic", "--synthetic-markets", "40",
         "--synthetic-rows-per-market", "5", "--output", str(corpus_p)],
        capture_output=True, text=True, cwd=str(REPO),
    )
    assert r.returncode == 0, r.stderr
    rep = run_replay(corpus_p)
    assert rep["mode"] == "pre-resolution-forward"
    assert rep["eligibleRows"] >= 30
    assert rep["negativeControlResolutionBarAuc"] is not None
    # signal AUC modestly above the tautology negative-control (real edge, not lookahead)
    if "crossValidatedAuc" in rep and rep["crossValidatedAuc"].get("meanTestAuc") is not None:
        assert rep["crossValidatedAuc"]["meanTestAuc"] > rep["negativeControlResolutionBarAuc"]
    # verdict must NOT be paper-ready — negative-control gate must hold
    assert rep["verdict"] == "watch-research-only"
