# TAKEOVER.md — Bill/Hedge System — 2026-05-06 14:25 UTC

## Critical: SWAP 93.3% | DISK 91% — REBOOT MANDATORY

**Swap at 93.3% (12,421/13,312 MB)** — CRITICAL (>90%). Only reboot resolves.
**Disk at 91% (162/228Gi)** — CRITICAL (>85%). 3 APFS OS update snapshots stuck.
**Pages free: 47,684 (~764MB)** — HEALTHY. Recovered from 4,857 at 14:00Z.

## Services (8/8 UP)
| Service | Status | Note |
|---------|--------|------|
| Hermes Gateway | UP (PID 586) | |
| OpenClaw Gateway | UP (PID 1392) | |
| Labs Bridge :8788 | UP | {"ok":true} |
| Dashboard :8765 | UP | {"ok":true} |
| Kronos :8787 | UP | |
| n8n :5678 | UP | PM2-managed, 123 historical restarts, currently stable |
| Ollama :11434 | UP | 4.8GB RSS essential |
| Postiz API :3000 | UP | |
| Postiz FE :4200 | UP (orphan) | Zombie respawn pattern, functional |

## Hedge Pipeline
- **Prediction Cycle**: RESTARTED at 14:15 UTC. Ran 14:22-14:23. 3 venues healthy (poly/kalshi/manifold). Monitor history JSONL for next entry.
- **Strategy Factory**: IDLE (last 09:49Z). 0/3 OOS deployable. Cannot restart (swap >80%).
- **Paper Loop**: Skipping correctly (disk 17GB free < 25GB threshold).
- **Live-Readiness**: Stale (05:43Z). 0 test trades. Thin evidence.
- **Promotion**: Blocked (committee-watch, operator-approval-for-demo, operator-approval-for-live).
- **PMA**: Ready ✅
- **TimesFM**: Functional (venv OK, npm false negative)

## Recurring Issues
- APFS snapshots: 3 present, can't thin (POSIXError 70 → reboot needed)
- Postiz FE zombie: Behavior B respawn, PM2 stopped, orphan on :4200
- arxiv-metadata.json: Cross-session reversion (EIGHTH time). Recovery protocol works.
- Bill prediction cycle self-maintaining loop: DIED ~08:52Z. Manual kickstart required.

## Next Steps (When System Recovers Post-Reboot)
1. Run strategy-factory on specific profiles (1-3 max on 60d+ data)
2. Force full strategy-lab with live-readiness
3. Clear APFS snapshots
4. Verify prediction cycle auto-maintaining
