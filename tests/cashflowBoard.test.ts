import { mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { buildCashflowBoard } from "../src/engine/cashflowBoard.js";

describe("cashflow board", () => {
  it("combines kill switch, first-lane ledger, futures policy, and prediction review", async () => {
    const dir = await mkdtemp(join(tmpdir(), "cashflow-board-"));
    const futuresPolicyPath = join(dir, "macro-policy.json");
    const predictionReviewPath = join(dir, "prediction-review.json");
    const predictionResolvedPath = join(dir, "resolved.jsonl");
    const killSwitchPath = join(dir, "kill.json");

    await writeFile(killSwitchPath, JSON.stringify({ active: false, activatedAt: null, reason: null }), "utf8");
    await writeFile(futuresPolicyPath, JSON.stringify({
      command: "macro-conditioned-policy",
      status: "candidate-ready",
      blockers: [],
      selected: {
        profileId: "convex-index-asymmetry",
        symbol: "NQ",
        strategyId: "liquidity-reversion",
        macroGate: { riskRegime: "normal", vixTermStructure: "contango", creditRiskProxy: "normal", equityTrendProxy: "risk-on", maxTailScore: 6.9 },
        action: "paper-allow",
        score: 0.8,
        trades: 12,
        netTotalR: 8,
        averageR: 0.66,
        winRate: 0.67,
        profitFactor: 2.2,
        sharpePerTrade: 0.5,
        cvar95TradeR: -1,
        riskOfRuinProb: 0.04,
        maxConsecutiveLosses: 1,
        rationale: []
      },
      policyPatch: {
        RH_ENABLED_STRATEGIES: "liquidity-reversion",
        RH_ALLOWED_SYMBOLS: "NQ",
        RH_MAX_CONTRACTS: 1,
        RH_MAX_TRADES_PER_DAY: 1,
        RH_MAX_DAILY_LOSS_R: 1,
        RH_MAX_CONSECUTIVE_LOSSES: 1
      }
    }), "utf8");
    await writeFile(predictionReviewPath, JSON.stringify({
      readyForPaper: false,
      blockers: ["no-paper-candidates"],
      recommendation: "Keep collecting.",
      topCandidate: null
    }), "utf8");
    await writeFile(predictionResolvedPath, "", "utf8");

    const report = await buildCashflowBoard({
      outputPath: join(dir, "board.json"),
      ledgerOutputPath: join(dir, "ledger.json"),
      futuresPolicyPath,
      predictionReviewPath,
      killSwitchPath,
      env: {
        BILL_PREDICTION_RESOLVED_PATH: predictionResolvedPath,
        RH_LIVE_EXECUTION_ENABLED: "false",
        BILL_PREDICTION_EXECUTION_MODE: "paper",
        BILL_PREDICTION_LIVE_EXECUTION_ENABLED: "false"
      } as NodeJS.ProcessEnv,
      now: () => "2026-05-06T14:00:00.000Z"
    });

    expect(report.command).toBe("cashflow-board");
    expect(report.futures.selected?.symbol).toBe("NQ");
    expect(report.prediction.blockers).toContain("no-paper-candidates");
    expect(report.killSwitch.active).toBe(false);
    expect(report.doctrine.join(" ")).toMatch(/Prediction markets can be both/i);
  });
});
