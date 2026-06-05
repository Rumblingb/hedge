import { mkdtemp, readFile } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { describe, expect, it } from "vitest";
import { buildCapitalAllocator } from "../src/engine/capitalAllocator.js";
import type { CashflowBoardReport } from "../src/engine/cashflowBoard.js";

function board(status: CashflowBoardReport["status"], laneStatus: string): CashflowBoardReport {
  return {
    command: "cashflow-board",
    generatedAt: "2026-05-06T12:00:00.000Z",
    mode: "paper-first",
    status,
    paths: {
      outputPath: "board.json",
      ledgerPath: "ledger.json",
      futuresPolicyPath: "futures.json",
      predictionReviewPath: "prediction.json",
      killSwitchPath: "kill.json",
      ramGuardFlagPath: "ram.flag"
    },
    killSwitch: { active: false, activatedAt: null, reason: null },
    firstLanes: [
      {
        lane: "prediction-markets",
        status: laneStatus,
        key: "candidate-1",
        confidence: 0.8,
        recommendedStage: "paper",
        nextAction: "paper",
        blockers: []
      }
    ],
    futures: { selected: null, policyPatch: null, status: "missing" },
    prediction: { readyForPaper: true, topCandidate: null, blockers: [], recommendation: null },
    unlockPlan: [],
    hardNoGo: [],
    preOpenRunbook: [],
    doctrine: []
  };
}

describe("capital allocator", () => {
  it("allocates only to the active first lane", async () => {
    const root = await mkdtemp(join(tmpdir(), "allocator-"));
    const outputPath = join(root, "capital.json");
    const report = await buildCapitalAllocator({
      outputPath,
      cashflowBoard: board("ready-for-paper-candidate", "active"),
      env: { BILL_FUND_BANKROLL: "200", BILL_FUND_CURRENCY: "GBP" },
      now: () => "2026-05-06T12:00:00.000Z"
    });

    expect(report.status).toBe("paper-budget-ready");
    expect(report.laneBudgets.find((lane) => lane.lane === "prediction-markets")?.budget).toBe(10);
    expect(report.laneBudgets.find((lane) => lane.lane === "options-us")?.status).toBe("locked");
    expect(JSON.parse(await readFile(outputPath, "utf8")).command).toBe("capital-allocator");
  });

  it("keeps budget at zero when the board has no active paper candidate", async () => {
    const report = await buildCapitalAllocator({
      cashflowBoard: {
        ...board("shadow-build", "shadow"),
        hardNoGo: ["no active first-lane paper candidate"]
      },
      env: { BILL_FUND_BANKROLL: "200" },
      now: () => "2026-05-06T12:00:00.000Z"
    });

    expect(report.status).toBe("research-budget-only");
    expect(report.laneBudgets.every((lane) => lane.budget === 0)).toBe(true);
  });
});
