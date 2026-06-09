# Bill/Hedge Trading System — Architectural & Infrastructure Audit
**Date:** 2026-06-09  
**Auditor:** Hermes Agent (deepseek-v4-flash)  
**Scope:** Production readiness, SRE reliability, data pipeline integrity

---

## 1. DUAL STATE DIRECTORIES — SYNC STATUS

**Finding: PARTIALLY SYNCED via symlinks, but with divergent content representing a sync gap.**

| Path | Size | Key Content |
|------|------|-------------|
| `~/.rumbling-hedge/` | **30 MB** | agent-inbox (29 MB, 3951 files), dispatcher, learning, models, multi-d-testing, research, retired-roots, self-evolving-loop.jsonl |
| `hedge/.rumbling-hedge/` | **1.3 GB** | logs (486 MB), state (24 MB, 418 files), brain (476 KB), credentials, journal, research, all runtime artifacts |

**Symlink bridge (synced):**
- `~/.rumbling-hedge/brain` → `hedge/.rumbling-hedge/brain`
- `~/.rumbling-hedge/events` → `hedge/.rumbling-hedge/events`
- `~/.rumbling-hedge/state` → `hedge/.rumbling-hedge/state`

**NOT synced (divergent):**
- **`~/.rumbling-hedge/logs/`** = 8 KB (shallow) vs **`hedge/.rumbling-hedge/logs/`** = 486 MB (full runtime logs)
- **`~/.rumbling-hedge/agent-inbox/`** = 29 MB (3951 files, Hermes agent messages) — exists ONLY in `~`
- **`hedge/.rumbling-hedge/credentials/`** = only in hedge/ (polymarket.json)
- **`hedge/.rumbling-hedge/features/`, `iterations/`, `iterations-combined/`, `backtrader/`, `archive/`** = only in hedge/

**Risk:** The agent-inbox (3951 files, 29 MB) lives only in `~/.rumbling-hedge/` and is NOT backed up to the main repo state. If `~/.rumbling-hedge/` is lost, those messages are gone. The logs gap means any process reading `~/.rumbling-hedge/logs/` gets a stale view.

**Severity: MEDIUM** — the symlinks cover the critical state files, but the agent-inbox is a hidden single point of data loss.

---

## 2. DISK SPACE CONSTRAINTS

**Finding: CRITICAL — 15 GB free on a 93%-full APFS volume with known growth patterns that will fill within weeks.**

| Partition | Size | Used | Free | Capacity |
|-----------|------|------|------|----------|
| `/` (SS) | 228 GB | 12 GB | 15 GB | 43% |
| `/System/Volumes/Data` | 228 GB | **184 GB** | **15 GB** | **93%** |
| Seagate HDD | 932 GB | 820 GB | **112 GB** (88% full) | 88% |

**Key Working Set (sorted by size):**
| Asset | Size | Notes |
|-------|------|-------|
| `~/.npm-global/` | **3.8 GB** | n8n alone = 2.4 GB |
| `hedge/data/free/` | **2.8 GB** | CSV market data files |
| `hedge/.venv/` | **1.7 GB** | Python virtual env |
| `hedge/.rumbling-hedge/` | **1.3 GB** | State + logs |
| `hedge/bill-core/target/` | **403 MB** | Rust build artifacts |
| `hedge/node_modules/` | **198 MB** | JS dependencies |
| `~/.hermes/cron/output/` | **118 MB** | 27,368 files, NO cleanup |
| `hedge/.rumbling-hedge/logs/` | **486 MB** | Active + rotated logs |

**Growth velocity estimate:**
- **Prediction cycle logs:** ~30-40 MB/week (40 MB active + 192 MB rotated)
- **Launchd health logs:** ~16 MB/week (8.5 MB active + 48 MB rotated)
- **Cron output:** grows unbounded (118 MB with 27K+ files, NO rotation)
- **Market data CSVs:** 2.8 GB static for now
- **Total weekly growth estimate:** ~50-80 MB/week

**At 15 GB free + ~60 MB/week growth:** ~250 weeks headroom, BUT the real constraint is `/System/Volumes/Data` at 93% — APFS performance degrades above 95%, and macOS may refuse writes.

**Severity: HIGH** — 15 GB free is sufficient for day-to-day operations but leaves no emergency margin. The Seagate HDD is also 88% full.

---

## 3. MEMORY PRESSURE

**Finding: MODERATE PRESSURE with significant swap usage — high-load scenarios will push the system into thrashing.**

| Metric | Value |
|--------|-------|
| Physical RAM | 16 GB |
| Free | ~346 MB (2.1%) |
| Active | ~5.1 GB (31%) |
| Inactive | ~4.5 GB (28%) |
| Wired | ~2.9 GB (18%) |
| Swap used | **4.1 GB / 5.0 GB (82%)** |
| Swapins | 1.63 M |
| Swapouts | 2.24 M |

**Current running processes (memory):**
- Chrome renderer: 826 MB
- n8n (3 processes): 333+60+21 MB = ~414 MB
- Hermes dashboard: 240 MB
- Hermes gateway (main): 72 MB
- 8× Hermes profile gateway processes: ~30-40 MB each = ~280 MB
- gengarMonitor (Node): 53 MB
- SearXNG: 10 MB
- Hermes MCP servers (2): 105+115 MB = 220 MB

**High-load scenario analysis:** Running all 47 cron jobs concurrently + command center + TradingView WebSocket could spike memory by 1-2 GB. With only 346 MB truly free and 4.1 GB already in swap, the system would start thrashing (high page fault rate, degraded performance). The 5 GB swap partition has only 986 MB left.

**Potential memory-leak processes:**
- **n8n** (333 MB, running since 3:55 PM) — known for memory growth during long workflows
- **gengarMonitor** (persistent Node.js process with 3-second polling loops) — no explicit memory limit
- **Hermes gateway processes** — 8 persistent Python processes with no restart policy

**Severity: HIGH** — 82% swap utilization with active swapping indicates the system is already near its memory limit. Adding TradingView WebSocket or running all cron jobs simultaneously would likely trigger OOM or severe degradation.

---

## 4. CRASH-MID-TRADE ANALYSIS

**Finding: NO ATOMIC TRANSACTION LOG — flat JSON file writes are susceptible to partial writes on crash.**

**Current safeguards:**
1. **LiveGate** (`liveGate.ts`): Conservative gate — requires 4 env vars to be explicitly set before allowing live execution. Default posture is REFUSE.
2. **Repeat-fill cooldown** (24h): Prevents duplicate fills after restart.
3. **Fills journal** (`.rumbling-hedge/runtime/prediction/fills.jsonl`): Append-only JSONL — this is the closest thing to a WAL, but no atomic-write guarantee.
4. **Kill switch** (`.rumbling-hedge/kill-switch.json`): Manual override, currently `triggered: false`.
5. **.env.ops**: `RH_LIVE_EXECUTION_ENABLED=false` and `RH_TOPSTEP_READ_ONLY=true` — safe default posture.

**Gaps:**
- **No write-ahead log (WAL):** State files are written with `writeFile` (atomic on most OS, but not ACID). A crash during `JSON.stringify` + write can produce truncated files.
- **No transaction boundaries:** Multiple state files may be updated sequentially — a crash in the middle creates inconsistent state.
- **No order-idempotency tokens:** If the same signal fires twice after restart (before cooldown expires), it's handled, but if the cooldown state file was corrupted, duplicates are possible.
- **No database:** No PostgreSQL, SQLite, or Redis for persistent transaction state.

**Severity: MEDIUM** — the conservative gating and cooldown provide reasonable protection, but a crash during state file writes could corrupt state. The good news: paper mode is the default, and live mode requires explicit env vars.

---

## 5. HERMES CRASH DURING CRON FIX SESSION

**Finding: NO RECOVERY MECHANISM for interrupted agent fix sessions.**

- Hermes cron jobs are one-shot: they run, produce output, and finish. If Hermes crashes mid-job, the cron system logs a delivery error and retries at the next scheduled time.
- However, if a cron fix session (multi-step agent interaction) is interrupted, there is NO:
  - Session persistence
  - State rollback
  - Resumption mechanism
- The `bill-hermes-takeover` script is the only fallback — it runs on a schedule and assesses system posture, but does NOT resume interrupted fix sessions.
- Cron job backoff: jobs have no exponential backoff — they retry on the normal schedule.

**Severity: LOW-MEDIUM** — most cron jobs are idempotent scripts. The risk is only for multi-step fix sessions that Hermes orchestrates across multiple cron iterations.

---

## 6. BACKUP/RECOVERY PROCEDURES

**Finding: MINIMAL — single cold-archive script with no state backup, no restore procedures.**

| Mechanism | Status |
|-----------|--------|
| Cold archive to HDD | ✅ Exists — copies files >30 days to Seagate (but `REMOVE_AFTER_COPY=false`, so it's copy-only, not cleanup) |
| State snapshot | ❌ No automated snapshot/backup of `.rumbling-hedge/state/` |
| State restore | ❌ No documented restore procedure |
| Database backup | ❌ No database to backup |
| Git backup | ✅ Code is version-controlled |
| Credential backup | ❌ `bill.env` (containing Topstep/Polygon/etc API keys) is NOT backed up |
| Agent inbox backup | ❌ 29 MB of agent messages in `~/.rumbling-hedge/agent-inbox/` have NO backup |
| Worktree snapshots | ⚠️ 2 snapshots exist (last from May 5), but mechanism is unclear |
| Secrets backup | ❌ `.env` and `.env.ops` contain credentials without backup |

**Severity: HIGH** — no backup strategy means complete data loss if the SSD fails or `.rumbling-hedge/` is corrupted.

---

## 7. REBOOT SURVIVABILITY

**Finding: PARTIAL — core services auto-restart, but Hermes itself does not.**

**LaunchD agents (16 total, auto-start on reboot):**
- `com.agentpay.bill.*`: 16 plists with `RunAtLoad=true`
  - 13 have `KeepAlive=true` (gengar, health, paper-loop, prediction-cycle, etc.)
  - 3 use `StartInterval` (cold-archive daily, health every 15 min, macro-context-free)
- These will auto-restart after reboot

**What does NOT auto-restart:**
- **Hermes agent itself** — no launchd plist, requires manual startup
- **Hermes gateway profiles** (8 gateway profile processes) — no launchd plist
- **Command center server** — not registered with launchd
- **n8n** — no launchd plist (currently started manually or via another mechanism)
- **Swap contents** — ~4.1 GB of hot data lost on reboot

**Impact:** On reboot, the launchd-launched agents will fire, but without Hermes running:
- The 47 cron jobs won't execute (Hermes cron engine is offline)
- The command center won't serve
- Gateway bridge processes won't run
- The system will be in a degraded state requiring manual intervention to start Hermes

**Severity: HIGH** — the system cannot survive a reboot without manual intervention.

---

## 8. EXTERNAL DEPENDENCIES

**Finding: HEAVY EXTERNAL DEPENDENCY — 10+ external services, many with single-point-of-failure API keys.**

| Service | Purpose | Alternatives? | Key Present? |
|---------|---------|--------------|-------------|
| **TopstepX API** (`api.topstepx.com`) | Broker connectivity | ❌ No fallback | ✅ |
| **Polygon.io** (`api.polygon.io`) | Market data | ❌ None configured | ✅ |
| **OpenRouter** (`openrouter.ai`) | LLM cloud reviews | ⚠️ Could use local models | ✅ |
| **Polymarket Gamma API** | Prediction market data | ❌ None configured | N/A (public) |
| **Binance API** | BTC price feed (gengar) | ⚠️ Could use CoinGecko | N/A (public) |
| **Databento** | Historical market data | ❌ None configured | ✅ |
| **FRED API** | Economic indicators | ⚠️ Federal Reserve, unique | ✅ |
| **HuggingFace** | TimesFM model weights | ❌ Must be cached locally | N/A |
| **YouTube/Invidious** | Research content | ⚠️ Multiple mirrors configured | ✅ |
| **npm registry** | JS packages | ❌ Self-host possible but not done | N/A |
| **crates.io** | Rust packages | ❌ Self-host possible but not done | N/A |

**Risk:** If TopstepX, Polygon, or OpenRouter disappear or change their API, the system loses core trading, market data, and AI review capability. There are NO configured fallback providers.

**Severity: HIGH** — TopstepX is the single broker adapter, Polygon is the single market data source, and there's no provider abstraction layer with fallback logic visible in the codebase.

---

## 9. NETWORK DEPENDENCY CHAIN

**Finding: DEEP — most features break without internet.**

| Feature | Without Internet | Impact |
|---------|-----------------|--------|
| Topstep bridge | ❌ Breaks | No trade execution |
| Market data (Polygon/Databento) | ❌ Breaks | No fresh data |
| Prediction markets (Polymarket) | ❌ Breaks | No signal generation |
| LLM cloud reviews (OpenRouter) | ❌ Breaks | No AI analysis |
| YouTube research | ❌ Breaks | No content ingestion |
| npm/cargo operations | ❌ Breaks | No dependency installs |
| TimesFM (if not cached) | ❌ Breaks | No ML forecasting |
| **Local paper loop** | ✅ Works | CSV-based backtesting |
| **Local strategy evaluation** | ✅ Works | Self-contained algorithms |
| **Local signal generation** | ✅ Works | Bill-core Rust binaries |
| **Command center dashboard** | ✅ Works | Static HTML/JS |
| **Local backtesting** | ✅ Works | Historical data on disk |
| **Hermes agent (local)** | ✅ Works | Self-contained |
| **n8n workflows** | ⚠️ Partial | Local workflows, but webhooks fail |

**Severity: MEDIUM** — the core trading simulation features work offline, but all market-facing features (execution, data, signals) require internet.

---

## 10. GIT COMPLEXITY

**Finding: MANAGEABLE — 2 worktrees, 5 local branches, no merge conflicts visible.**

| Metric | Value |
|--------|-------|
| Worktrees | **2** (`hedge`, `hedge-goal-live`) |
| Local branches | **5** (codex/bill-hedge-autonomy-spine, codex/bill-mac-mini-ops, codex/goal-live-market-readiness, codex/june3-fund-operating-system, master) |
| Remote branches | **4** (including copilot/add-csv-inspection-budget-research) |
| Stash entries | **3** (WIP param_sweep, WIP master, WIP Lucid fix) |
| Divergence | Main worktree on `codex/june3-fund-operating-system`, second on `codex/goal-live-market-readiness` |

**Risk:** Low. Worktrees are clean, no detached HEAD, no conflicts. The 3 stashes represent unfinished work that could be lost. The GitNexus index (67,934 symbols) is well-maintained.

**Severity: LOW**

---

## 11. MONOREPO BLOAT

**Finding: LARGE BUT NOT CRITICAL — 12,196 files, but most are small.**

| Metric | Value |
|--------|-------|
| Root-level dirs | 85 |
| `run_*` directories | 55+ (1.7 MB total — negligible) |
| Top-level scripts | 8 (.sh, .py, .js) |
| Total files | **12,196** (excluding .git, node_modules, .venv, target, __pycache__) |
| Total scripts | ~80 in `ops/mac-mini/bin/` alone |
| TypeScript src/ | 3.1 MB |
| Python src | ~200 KB (scattered in root) |
| Rust src | ~0.5 MB (bill-core/) |

**The 55+ `run_*` directories:** Total 1.7 MB — negligible. These appear to be strategy parameter sweep output dirs (run_thresh_*, run_atr_*, run_sl*, run_holdbars_*, run_orb_*, etc.). Each is 8-44 KB. They are messy but not space-consuming.

**Real bloat:** The scatter pattern — Python scripts in root, Rust in `bill-core/`, TypeScript in `src/`, shell scripts in `ops/mac-mini/bin/`, and configs everywhere — makes it hard to find things.

**Severity: LOW** — cosmetic issue, not a functional risk.

---

## 12. LOG ROTATION AND DISK CLEANUP

**Finding: INCOMPLETE — JSONL logs rotate but standard logs don't, and cron output grows unbounded.**

**Rotation status:**
| Log Type | Configured Max | Actual | Rotations | Cleanup |
|----------|---------------|--------|-----------|---------|
| `BILL_LOG_MAX_MB` | **16 MB** | N/A | 3 | ✅ Configured |
| `BILL_JSONL_MAX_MB` | **64 MB** | 40 MB active | 3 | ✅ Configured |
| **Prediction JSONL** | 64 MB | 40 MB + 3×64 MB = **232 MB** | ✅ Rotates | but maxed at 3 |
| **Launchd health** | Implicit | 8.5 MB + 3×16 MB = **57 MB** | ✅ 3 rotations | good |
| **Command center** | ❌ None | 1-3 KB | ❌ No rotation | minimal |
| **Cron output** | ❌ **None** | **27,368 files, 118 MB** | ❌ **NO rotation** | **GROWS UNBOUNDED** |

**Critical gap:** The cron output directory at `~/.hermes/cron/output/` has **27,368 files consuming 118 MB** with **no cleanup policy**. Each cron job run creates a new markdown output file. At ~50-100 runs/week, this grows at ~2-5 MB/week indefinitely.

**Also missing:** No cleanup of old `launchd-*.log.4+` beyond rotation 3. The cold-archive script copies old files to HDD but doesn't remove them by default.

**Severity: MEDIUM** — the JSONL rotation works, but the unbounded cron output growth will eventually exhaust inodes (extreme edge case but real).

---

## 13. MEMORY LEAK RISKS

**Finding: THREE PROCESSES WITH KNOWN LEAK PROFILES.**

| Process | RSS | Runtime | Risk |
|---------|-----|---------|------|
| **n8n** (main) | 333 MB | Since 3:55 PM today | **HIGH** — n8n is known for memory growth with long workflows, no restart policy |
| **gengarMonitor** (Node) | 53 MB | Since Sun 3 PM (24h+) | **MEDIUM** — persistent polling loop, no memory limit configured |
| **Hermes dashbboard** | 240 MB | Since Sun 3 PM | **LOW** — stable, TUI-based |
| **8× Hermes gateway profiles** | ~30-40 MB each | Since Sun 3 PM | **LOW** — Python, relatively stable |
| **Chrome** | 826 MB | Since 2:29 PM | **LOW** — browser, not trading system |

**Of particular concern:** n8n and gengarMonitor have been running for extended periods with no restart mechanism. n8n at 333 MB could grow to 1 GB+ over days/weeks.

**Severity: MEDIUM** — no active memory leak detected, but n8n and gengarMonitor lack restart policies.

---

## 14. SINGLE POINTS OF FAILURE

**Finding: FIVE CRITICAL SPOFs.**

| SPOF | Why It's Critical | Mitigation |
|------|------------------|------------|
| **Hermes agent** | Cron engine (47 jobs), dashboard, gateway orchestration | ❌ No backup Hermes instance |
| **TopstepX API** | Only broker adapter | ❌ No fallback broker |
| **Polygon.io** | Only market data provider | ❌ No fallback data source |
| **Single macOS machine** | Everything runs on one laptop | ❌ No failover, no redundancy |
| **Flat file state** | No database; crash = corruption risk | ⚠️ Append-only JSONL for fills, but state files are overwritten |

**Secondary SPOFs:**
- **Seagate HDD**: Cold archive destination — if unplugged, `cold-archive` silently skips (which is correct behavior, but creates a blind spot)
- **OpenRouter API key**: If rate-limited or expired, LLM cloud reviews silently degrade
- **npm/crates.io**: If registry is down, new dependency installations fail

**Severity: HIGH** — the system runs on a single machine with no failover for any critical component.

---

## 15. TOPSTEP BRIDGE CREDENTIAL EXPIRATION

**Finding: GRACEFUL DEGRADATION — the system detects blockers and refuses execution.**

**Credential details:**
- Username: `vishar.rumbling@gmail.com`
- Account: `100KTC-V2-DLL-507159-83651531` (100K Trading Combine challenge)
- API Key: Present (partially obscured)
- Mode: Demo/read-only (`RH_TOPSTEP_DEMO_ONLY=true`, `RH_TOPSTEP_READ_ONLY=true`)

**If credentials expire:**
1. The `two-track-readiness` pipeline (runs every 30 min via cron) will detect authentication failure
2. Blockers will be reported in `state/two-track-readiness.latest.json`
3. `bill-hermes-takeover` will report the system posture as blocked
4. `liveGate` will refuse execution (liveAllowed=false)
5. The system continues in paper-only mode

**However:** There is NO credential expiry monitoring or alert. If the API key expires silently:
- Paper loop continues running
- Signal generation continues
- But demo execution stops silently
- The operator must discover the failure by reading state files

**Severity: MEDIUM** — graceful degradation exists, but no proactive alerting.

---

## SUMMARY OF FINDINGS

| # | Area | Severity | Issue |
|---|------|----------|-------|
| 1 | Disk space | **HIGH** | 15 GB free on 93%-full volume; 4.1 GB swap at 82% |
| 2 | Memory | **HIGH** | 82% swap used; adding TradingView WS could trigger OOM |
| 3 | Reboot | **HIGH** | Hermes not registered in launchd; requires manual start |
| 4 | Backup | **HIGH** | No state backup; no restore procedures; credentials not backed up |
| 5 | SPOF | **HIGH** | Single machine, single broker adapter, single data provider |
| 6 | Log rotation | **MEDIUM** | Cron output (27K+ files, 118 MB) grows unbounded with no cleanup |
| 7 | Dual state dirs | **MEDIUM** | Agent inbox (29 MB, 3951 files) lives only in `~/.rumbling-hedge/` |
| 8 | Crash mid-trade | **MEDIUM** | No WAL or atomic writes; flat files can be corrupted on crash |
| 9 | External deps | **MEDIUM** | 10+ external services; no fallback providers configured |
| 10 | Topstep expiry | **MEDIUM** | Graceful degradation exists, but no proactive alert |
| 11 | Memory leaks | **MEDIUM** | n8n (333 MB, no restart) and gengarMonitor (no memory limit) |
| 12 | Network chain | **MEDIUM** | Core simulation works offline, but all market features break |
| 13 | Hermes crash | **LOW-MEDIUM** | Cron fix sessions not resumable; idempotent jobs mitigate |
| 14 | Git complexity | **LOW** | 2 worktrees, 5 branches, 3 stashes — manageable |
| 15 | Monorepo bloat | **LOW** | 12K files, 85 root dirs — messy but not harmful |

---

## RECOMMENDATIONS (PRIORITY ORDER)

### P0 — Critical (immediate action)
1. **Register Hermes in launchd** (`com.agentpay.bill.hermes.plist` with KeepAlive=true) so the system survives reboot.
2. **Add cron output cleanup** — rotate/delete files older than 30 days in `~/.hermes/cron/output/`.
3. **Backup bill.env** — copy credentials to Seagate HDD (cold archive target).

### P1 — High (this week)
4. **Set up state file backup** — rsync `.rumbling-hedge/state/` to HDD every hour.
5. **Add n8n restart policy** — restart if memory exceeds 500 MB, or add `--max-old-space-size` limit.
6. **Implement credential expiry monitoring** — check Topstep API key validity in the health pipeline.

### P2 — Medium (this month)
7. **Add Polygon/OpenRouter fallback providers** — at minimum, configure secondary API keys.
8. **Implement atomic state writes** — write to `.tmp` file, then `rename()` for atomicity.
9. **Add swap monitoring alert** — warn when swap exceeds 80%.
10. **Consolidate dual state dirs** — move agent-inbox into the symlinked subtree, or add backup.

### P3 — Low (nice to have)
11. **Clean up 55+ `run_*` dirs** — move to a `runs/` subdirectory or archive.
12. **Remove Rust build artifacts** (`target/debug/` = 308 MB) — keep only release builds.
13. **Document restore procedure** for state directory.
14. **Add `@reboot` cron-style job** in Hermes for post-reboot health check.

---

*Report generated by Hermes Agent · 2026-06-09T16:00:00Z*
