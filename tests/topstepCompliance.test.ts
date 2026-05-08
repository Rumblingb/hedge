import { describe, it, expect } from "vitest";
import { TopstepComplianceTracker, TOPSTEP_50K, type ComplianceState } from "../src/risk/topstepCompliance.js";

function makeState(overrides: Partial<ComplianceState>): ComplianceState {
  return {
    totalPnL: 0,
    peakEquity: 0,
    currentDD: 0,
    maxDDHit: false,
    bestDayPnL: 0,
    bestDayRatio: 0,
    consistencyViolated: false,
    profitTargetHit: false,
    tradingDays: 0,
    minDaysMet: false,
    passed: false,
    failed: false,
    failReason: null,
    dailyHistory: [],
    ...overrides,
  };
}

describe("TopstepComplianceTracker", () => {
  it("starts clean", () => {
    const t = new TopstepComplianceTracker();
    expect(t.getState().totalPnL).toBe(0);
    expect(t.getState().passed).toBe(false);
  });

  it("tracks daily P&L", () => {
    const t = new TopstepComplianceTracker();
    t.recordTrade(100, true);
    t.recordTrade(-50, false);
    t.recordTrade(200, true);
    expect(t.getState().totalPnL).toBe(250);
    expect(t.getState().dailyHistory[0]!.trades).toBe(3);
  });

  it("detects profit target", () => {
    const t = new TopstepComplianceTracker();
    t.recordTrade(1500, true);
    t.recordTrade(1500, true);
    expect(t.getState().profitTargetHit).toBe(true);
  });

  it("fails on trailing drawdown", () => {
    const t = new TopstepComplianceTracker();
    t.recordTrade(1000, true);
    t.recordTrade(-3000, false);
    expect(t.getState().failed).toBe(true);
    expect(t.getState().failReason).toContain("drawdown");
  });

  it("fails on consistency violation at EOD", () => {
    const state = makeState({
      totalPnL: 3000,
      peakEquity: 3000,
      bestDayPnL: 2800,
      bestDayRatio: 2800 / 3000,
      profitTargetHit: true,
      tradingDays: 2,
      minDaysMet: true,
      dailyHistory: [
        { date: "2026-05-06", pnl: 2800, trades: 5, wins: 4, losses: 1 },
        { date: "2026-05-07", pnl: 200, trades: 1, wins: 1, losses: 0 },
      ],
    });
    const t = new TopstepComplianceTracker(TOPSTEP_50K, state);
    t.endOfDay();
    expect(t.getState().failed).toBe(true);
    expect(t.getState().failReason).toContain("Consistency");
  });

  it("passes with 50/50 split (exactly at limit)", () => {
    const state = makeState({
      totalPnL: 3000,
      peakEquity: 3000,
      bestDayPnL: 1500,
      bestDayRatio: 0.50,
      profitTargetHit: true,
      tradingDays: 2,
      minDaysMet: true,
      dailyHistory: [
        { date: "2026-05-06", pnl: 1500, trades: 3, wins: 3, losses: 0 },
        { date: "2026-05-07", pnl: 1500, trades: 3, wins: 3, losses: 0 },
      ],
    });
    const t = new TopstepComplianceTracker(TOPSTEP_50K, state);
    t.endOfDay();
    expect(t.getState().failed).toBe(false);
  });

  it("reports progress", () => {
    const t = new TopstepComplianceTracker();
    t.recordTrade(1500, true);
    const p = t.getProgress();
    expect(p.profitPct).toBe(50);
    expect(p.consistencyStatus).toBe("warning");
  });

  it("warns at 90% of consistency limit", () => {
    const state = makeState({
      totalPnL: 2000,
      bestDayPnL: 900,
      bestDayRatio: 0.45,
      tradingDays: 1,
      dailyHistory: [
        { date: "2026-05-06", pnl: 900, trades: 3, wins: 3, losses: 0 },
      ],
    });
    const t = new TopstepComplianceTracker(TOPSTEP_50K, state);
    expect(t.getProgress().consistencyStatus).toBe("warning");
  });

  it("blocks trading when combine passed", () => {
    const state = makeState({ passed: true });
    const t = new TopstepComplianceTracker(TOPSTEP_50K, state);
    const result = t.canTrade();
    expect(result.allowed).toBe(false);
    expect(result.reason).toContain("passed");
  });

  it("computes max additional profit today", () => {
    const state = makeState({
      totalPnL: 2000,
      bestDayPnL: 900,
      dailyHistory: [
        { date: new Date().toISOString().slice(0, 10), pnl: 900, trades: 3, wins: 3, losses: 0 },
      ],
    });
    const t = new TopstepComplianceTracker(TOPSTEP_50K, state);
    const max = t.maxAdditionalProfitToday();
    // 900 / 0.50 - 2000 = -200 → 0 (already at limit, no more room)
    expect(max).toBeGreaterThanOrEqual(0);
  });
});
