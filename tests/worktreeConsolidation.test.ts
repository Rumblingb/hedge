import { describe, expect, it } from "vitest";
import { buildWorktreeConsolidationReport, categorizeWorktreePath, parseGitWorktreeList } from "../src/engine/worktreeConsolidation.js";

describe("worktree consolidation", () => {
  it("parses git worktree porcelain output", () => {
    const parsed = parseGitWorktreeList([
      "worktree /Users/brain/hedge",
      "HEAD abc123",
      "branch refs/heads/master",
      "",
      "worktree /Users/brain/worktrees/hedge-goal-live",
      "HEAD def456",
      "branch refs/heads/codex/goal-live-market-readiness"
    ].join("\n"));

    expect(parsed).toEqual([
      { path: "/Users/brain/hedge", head: "abc123", branch: "master" },
      { path: "/Users/brain/worktrees/hedge-goal-live", head: "def456", branch: "codex/goal-live-market-readiness" }
    ]);
  });

  it("classifies dirty files into intake lanes", () => {
    expect(categorizeWorktreePath("src/engine/riskPolicyGuard.ts")).toBe("governance-risk");
    expect(categorizeWorktreePath("src/promotion/state.ts")).toBe("governance-risk");
    expect(categorizeWorktreePath("src/strategies/openingRangeReversal.ts")).toBe("strategy-research");
    expect(categorizeWorktreePath("data/free/ALL-6MARKETS-1m-30d.csv")).toBe("data");
    expect(categorizeWorktreePath("src/live/demoExecution.ts")).toBe("execution-live");
    expect(categorizeWorktreePath("scripts/master_bridge.py")).toBe("execution-live");
    expect(categorizeWorktreePath("scripts/pre_trade_check.py")).toBe("execution-live");
    expect(categorizeWorktreePath("scripts/position_sizing_engine.py")).toBe("execution-live");
    expect(categorizeWorktreePath("scripts/cron_position_sizing.sh")).toBe("execution-live");
    expect(categorizeWorktreePath("scripts/deposit-clob.ts")).toBe("execution-live");
    expect(categorizeWorktreePath("scripts/deposit-simple.ts")).toBe("execution-live");
    expect(categorizeWorktreePath("scripts/fund-and-trade.ts")).toBe("execution-live");
    expect(categorizeWorktreePath("scripts/wire-up.ts")).toBe("execution-live");
    expect(categorizeWorktreePath("scripts/swap-and-fund.ts")).toBe("execution-live");
    expect(categorizeWorktreePath("scripts/verify_master_bridge_firewall.py")).toBe("execution-live");
    expect(categorizeWorktreePath("scripts/verify_60m_exec_bridge_firewall.py")).toBe("execution-live");
    expect(categorizeWorktreePath("scripts/verify_signal_router_firewall.ts")).toBe("execution-live");
    expect(categorizeWorktreePath("scripts/data_freshness_gate.py")).toBe("data");
    expect(categorizeWorktreePath("scripts/refresh_futures_research_data.py")).toBe("data");
    expect(categorizeWorktreePath("scripts/realtime_data_bridge.py")).toBe("data");
    expect(categorizeWorktreePath("scripts/realtime_data_preflight.py")).toBe("data");
    expect(categorizeWorktreePath("scripts/realtime_cron.sh")).toBe("data");
    expect(categorizeWorktreePath("scripts/pipeline_monitor.py")).toBe("data");
    expect(categorizeWorktreePath("scripts/bill_fund_os_completion_audit.py")).toBe("governance-risk");
    expect(categorizeWorktreePath("scripts/bill_next_research_actions.py")).toBe("governance-risk");
    expect(categorizeWorktreePath("scripts/bill_research_closed_loop_contract.py")).toBe("governance-risk");
    expect(categorizeWorktreePath("scripts/vol_regime_oos_replay.py")).toBe("strategy-research");
    expect(categorizeWorktreePath("scripts/futures_cost_slippage_gate.py")).toBe("strategy-research");
    expect(categorizeWorktreePath("scripts/futures_evidence_triage.py")).toBe("strategy-research");
    expect(categorizeWorktreePath("scripts/futures_no_edge_ledger.py")).toBe("strategy-research");
    expect(categorizeWorktreePath("backtrader_verify.py")).toBe("strategy-research");
    expect(categorizeWorktreePath("scripts/prediction-market-analysis-import.py")).toBe("strategy-research");
    expect(categorizeWorktreePath("scripts/prediction_market_calibration_gate.py")).toBe("strategy-research");
    expect(categorizeWorktreePath("scripts/prediction_research_watchlist.py")).toBe("strategy-research");
    expect(categorizeWorktreePath("scripts/prediction_category_drilldown.py")).toBe("strategy-research");
    expect(categorizeWorktreePath("scripts/prediction_narrow_scan_runner.py")).toBe("strategy-research");
    expect(categorizeWorktreePath("scripts/prediction_evidence_triage.py")).toBe("strategy-research");
    expect(categorizeWorktreePath("scripts/prediction_resolved_outcome_join.py")).toBe("strategy-research");
    expect(categorizeWorktreePath("scripts/prediction_no_edge_ledger.py")).toBe("strategy-research");
    expect(categorizeWorktreePath("scripts/polymarket_clob_recorder.mjs")).toBe("strategy-research");
    expect(categorizeWorktreePath("scripts/polymarket_clob_persistence_lab.mjs")).toBe("strategy-research");
    expect(categorizeWorktreePath("scripts/polymarket_clob_edge_gate.mjs")).toBe("strategy-research");
    expect(categorizeWorktreePath("scripts/signal_quality_advisor.py")).toBe("strategy-research");
    expect(categorizeWorktreePath("scripts/probe-60m-signals.ts")).toBe("strategy-research");
    expect(categorizeWorktreePath("scripts/cron_state_validator.py")).toBe("governance-risk");
    expect(categorizeWorktreePath("scripts/sync_bill_obsidian.py")).toBe("governance-risk");
    expect(categorizeWorktreePath("src/engine/autonomyStatus.ts")).toBe("governance-risk");
    expect(categorizeWorktreePath("src/engine/dashboardSnapshot.ts")).toBe("governance-risk");
    expect(categorizeWorktreePath("src/utils/markets.ts")).toBe("strategy-research");
    expect(categorizeWorktreePath("tests/worktreeConsolidation.test.ts")).toBe("governance-risk");
    expect(categorizeWorktreePath("tests/test_bill_next_research_actions.py")).toBe("governance-risk");
    expect(categorizeWorktreePath("tests/test_bill_research_closed_loop_contract.py")).toBe("governance-risk");
    expect(categorizeWorktreePath("tests/test_sync_bill_obsidian.py")).toBe("governance-risk");
    expect(categorizeWorktreePath("ops/kill_switch.sh")).toBe("governance-risk");
    expect(categorizeWorktreePath("ops/mac-mini/bin/60m-strategy-eval-shadow.sh")).toBe("strategy-research");
    expect(categorizeWorktreePath("ops/mac-mini/bin/bill-pm-auto-execute-loop.sh")).toBe("execution-live");
    expect(categorizeWorktreePath("scripts/cftc_tff_positioning_ingest.py")).toBe("data");
    expect(categorizeWorktreePath("external/qlib/README.md")).toBe("external-vendor");
    expect(categorizeWorktreePath("research-repos")).toBe("external-vendor");
    expect(categorizeWorktreePath("package-lock.json")).toBe("dependencies");
    expect(categorizeWorktreePath(".env.example")).toBe("ops-docs");
    expect(categorizeWorktreePath("ops/mac-mini/env/bill.env.example")).toBe("ops-docs");
  });

  it("adds a reviewable clearance queue to the report", async () => {
    const report = await buildWorktreeConsolidationReport({
      repoRoot: process.cwd(),
      outputPath: "/tmp/worktree-consolidation-test.json",
      now: () => "2026-05-29T00:00:00.000Z"
    });

    expect(report.posture).toBe("organized-blocked-for-live-money");
    expect(report.sourceCleanBlockers.length).toBeGreaterThan(0);
    expect(report.canonicalSource.path).toBe(process.cwd());
    expect(report.canonicalSource.dirtyFiles).toBeGreaterThan(0);
    expect(report.canonicalSource.categories["execution-live"]).toBeGreaterThan(0);
    expect(report.canonicalSource.executionLiveFiles.length).toBeGreaterThan(0);
    expect(report.canonicalSource.laneSummaries.length).toBe(report.clearanceQueue.length);
    expect(report.clearanceQueue.length).toBeGreaterThan(0);
    expect(report.clearanceQueue[0]?.requiredEvidence.length).toBeGreaterThan(0);
    const executionLane = report.clearanceQueue.find((item) => item.lane === "execution-live");
    expect(executionLane?.requiredEvidence).toContain("npm run --silent bill:verify-signal-router-firewall");
    expect(executionLane?.requiredEvidence).toContain("npm run --silent bill:verify-prediction-funding-firewall");
    expect(report.canonicalSource.executionLiveFiles).toContain("scripts/master_bridge.py");
    const dataLane = report.clearanceQueue.find((item) => item.lane === "data");
    expect(dataLane?.requiredEvidence).toContain("npm run --silent bill:realtime-data-preflight || true");
    expect(dataLane?.requiredEvidence).toContain("npm run --silent bill:cftc-tff-positioning || true");
    expect(report.dirtySiblingWorktrees.count).toBeGreaterThanOrEqual(0);
    expect(report.clearanceQueue.map((item) => item.priority)).toEqual(
      [...report.clearanceQueue.map((item) => item.priority)].sort((a, b) => a - b)
    );
  });
});
