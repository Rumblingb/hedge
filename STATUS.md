# STATUS.md — Bill/Hedge System Health

## Component Status (2026-05-06 12:57 UTC)

| # | Component | Status |
|---|-----------|--------|
| 1 | Hermes gateway | UP (PID 586) |
| 2 | OpenClaw gateway | UP (PID 1392, ~1GB RSS) |
| 3 | Bridge (8788) | UP |
| 4 | Dashboard (8765) | UP |
| 5 | Kronos (8787) | UP |
| 6 | n8n (5678) | UP — PM2: online 9h, 86.8MB |
| 7 | Ollama (11434) | UP |
| 8 | Postiz API (3000) | UP — PM2: online 9h |
| 9 | Postiz FE (4200) | UP (orphan next-server, PM2 stopped) |
| 10 | Prediction cycle | STALE (last entry 07:27Z, 5.5h ago). No running process. Snapshot mtime fresh (12:57). 3 venues (PM=525, Kalshi=54, Manifold=6). |
| 11 | Strategy-factory | NOT RUNNING. Last run 04:17Z (8.5h ago). Blocked (0/3 OOS windows deployable, survivability 78). |
| 12 | Paper-loop | STOPPED (launchd PID `-`) |
| 13 | Research-collect | STOPPED (launchd PID `-`) |
| 14 | Researcher-run | STOPPED (launchd PID `-`) |
| 15 | Prediction-market-analysis | Ready |
| 16 | TimesFM | Ready (venv functional by direct check) |

## Resources
- **Swap**: 93.7% (12469/13312 MB) — CRITICAL (>90%)
- **Disk**: 91% (162/228Gi) — CRITICAL (>85%)
- **Pages free**: 6,061 (~99MB) — CRITICAL (<10,000 threshold)
- **Memory pressure**: Normal (but raw pages free critically low)
- **HDD**: Present (not checked this cycle)
- **Load**: 2.46 / 2.06 / 1.97, CPU 84.7% idle

## Escalations (COMPOUND CRISIS)
- **SWAP >90%** + **DISK >85%** + **PAGES FREE <10K** = triple-threshold breach
- **PREDICTION CYCLE STALE**: No running process, last history entry 5.5h ago
- **ALL BILL JOBS STOPPED**: prediction-cycle, paper-loop, research-collect, researcher-run all show PID `-`
- **APFS SNAPSHOTS**: 3 snapshots present, thinning fails (POSIXError 70). REBOOT REQUIRED.
- **ALL SAFE CLEANUP EXHAUSTED**: npm cache, pip cache, npx cache cleaned this cycle. ~70MB node-gyp + python caches freed.
- **NO HEAVY OPS POSSIBLE**: Swap >80% + pages free <10K blocks strategy-factory, TimesFM, researcher-run.
