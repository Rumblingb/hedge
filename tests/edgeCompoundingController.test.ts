import { mkdtemp, readFile, writeFile, mkdir } from "node:fs/promises";
import { dirname, join } from "node:path";
import { tmpdir } from "node:os";
import { describe, expect, it } from "vitest";
import { buildEdgeCompoundingController } from "../src/engine/edgeCompoundingController.js";

async function writeJson(path: string, value: unknown): Promise<void> {
  await mkdir(dirname(path), { recursive: true });
  await writeFile(path, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

describe("edge compounding controller", () => {
  it("fails closed when source gates are missing", async () => {
    const baseDir = await mkdtemp(join(tmpdir(), "edge-compound-"));
    const report = await buildEdgeCompoundingController({
      baseDir,
      now: () => "2026-05-10T12:00:00.000Z",
      env: { BILL_FUND_BANKROLL: "250", BILL_FUND_CURRENCY: "USD" } as NodeJS.ProcessEnv
    });

    expect(report.status).toBe("blocked");
    expect(report.liveAllowed).toBe(false);
    expect(report.deployablePaperBudget).toBe(0);
    expect(report.blockers).toContain("missing capital allocator artifact");
    expect(report.lanes.find((lane) => lane.lane === "reserve")?.budget).toBe(250);
  });

  it("permits only paper-demo compounding when allocator and demo gates agree", async () => {
    const baseDir = await mkdtemp(join(tmpdir(), "edge-compound-"));
    const stateDir = join(baseDir, ".rumbling-hedge/state");
    await writeJson(join(stateDir, "capital-allocator.latest.json"), {
      command: "capital-allocator",
      generatedAt: "2026-05-10T12:00:00.000Z",
      status: "paper-budget-ready",
      bankroll: 200,
      currency: "USD",
      paths: { outputPath: "capital.json", cashflowBoardPath: "cashflow.json" },
      laneBudgets: [
        {
          lane: "prediction-markets",
          status: "paper",
          budget: 10,
          currency: "USD",
          maxDailyLoss: 2,
          maxSingleTradeRisk: 1,
          reason: "active"
        },
        {
          lane: "futures-prop",
          status: "research",
          budget: 0,
          currency: "USD",
          maxDailyLoss: 0,
          maxSingleTradeRisk: 0,
          reason: "blocked"
        }
      ],
      lockedSpend: [],
      compoundingRules: [],
      blockers: []
    });
    await writeJson(join(stateDir, "live-readiness-gate.latest.json"), {
      command: "live-readiness-gate",
      generatedAt: "2026-05-10T12:00:00.000Z",
      readyForLive: false,
      readyForDemoExpansion: true,
      checks: [],
      blockers: [],
      warnings: [],
      autonomy: {}
    });
    await writeJson(join(stateDir, "competitive-readiness.latest.json"), {
      command: "competitive-readiness",
      generatedAt: "2026-05-10T12:00:00.000Z",
      outputPath: "competitive.json",
      headline: "paper only",
      liveExecutionAllowed: false,
      portfolioScore: 60,
      lanes: [
        { lane: "prediction", status: "paper-ready", score: 72, blockers: [], dataScore: 70, edgeScore: 70, modelScore: 70, executionScore: 70, riskScore: 70, capacityScore: 70, reflexivityPenalty: 0, requiredData: [], methodsToUse: [], nextActions: [] },
        { lane: "futures-core", status: "research", score: 40, blockers: ["missing-positive-oos-deployability"], dataScore: 40, edgeScore: 20, modelScore: 40, executionScore: 20, riskScore: 70, capacityScore: 65, reflexivityPenalty: 10, requiredData: [], methodsToUse: [], nextActions: [] },
        { lane: "long-only-compounder", status: "research", score: 45, blockers: ["capital-allocation-lane-not-cashflow-source-yet"], dataScore: 45, edgeScore: 10, modelScore: 30, executionScore: 0, riskScore: 80, capacityScore: 90, reflexivityPenalty: 4, requiredData: [], methodsToUse: [], nextActions: [] }
      ],
      globalBlockers: [],
      dataShoppingList: [],
      founderDirectivePriority: [],
      operatingDoctrine: [],
      scalingLawAnswer: { verdict: "conditional", why: [], practicalImplication: "gate first" }
    });
    await writeJson(join(stateDir, "two-track-readiness.latest.json"), {
      command: "two-track-readiness",
      demoExpansionAllowed: true,
      predictionMarkets: { blockers: [] },
      propFirms: { blockers: ["walk-forward gate is not deployable"] }
    });

    const outputPath = join(stateDir, "compound.json");
    const report = await buildEdgeCompoundingController({
      baseDir,
      outputPath,
      now: () => "2026-05-10T12:00:00.000Z"
    });

    expect(report.status).toBe("paper-demo-ready");
    expect(report.liveAllowed).toBe(false);
    expect(report.deployablePaperBudget).toBe(10);
    expect(report.lanes.find((lane) => lane.lane === "prediction-markets")?.status).toBe("paper-demo");
    expect(report.lanes.find((lane) => lane.lane === "futures-prop")?.status).toBe("research");
    expect(JSON.parse(await readFile(outputPath, "utf8")).command).toBe("edge-compounding-controller");
  });
});
