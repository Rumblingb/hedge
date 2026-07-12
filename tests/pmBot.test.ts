import { mkdtemp, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { describe, expect, it } from "vitest";
import { authorizePmBotLiveRequest } from "../src/prediction/pmBot.js";
import { DEFAULT_PREDICTION_SOURCE_POLICY } from "../src/prediction/policy.js";

describe("pm bot live authorization", () => {
  async function writeArtifacts(args: {
    readyForPaper: boolean;
    currentStage: string;
    recommendedStage: string;
    blockers?: string[];
  }) {
    const dir = await mkdtemp(join(tmpdir(), "pm-bot-gate-"));
    const reviewPath = join(dir, "prediction-review.latest.json");
    const promotionPath = join(dir, "promotion-state.json");
    await writeFile(reviewPath, JSON.stringify({
      ts: "2026-04-23T00:00:00.000Z",
      policy: DEFAULT_PREDICTION_SOURCE_POLICY,
      venueCounts: { polymarket: 20, kalshi: 12 },
      counts: { reject: 0, watch: 0, "paper-trade": args.readyForPaper ? 1 : 0 },
      topCandidate: null,
      checks: [],
      blockers: args.blockers ?? [],
      recommendation: args.readyForPaper ? "queue for live" : "stay in research",
      readyForPaper: args.readyForPaper
    }, null, 2));
    await writeFile(promotionPath, JSON.stringify({
      track: "prediction-markets",
      currentStage: args.currentStage,
      recommendedStage: args.recommendedStage,
      updatedAt: "2026-04-23T00:00:00.000Z",
      blockers: args.blockers ?? [],
      approvalsRequired: [],
      checks: [],
      notes: []
    }, null, 2));
    return { reviewPath, promotionPath };
  }

  it("refuses live when env live execution is not explicitly enabled", async () => {
    const { reviewPath, promotionPath } = await writeArtifacts({
      readyForPaper: true,
      currentStage: "live",
      recommendedStage: "live"
    });

    const result = await authorizePmBotLiveRequest({
      BILL_PREDICTION_REVIEW_PATH: reviewPath,
      BILL_PROMOTION_STATE_PATH: promotionPath,
      BILL_PREDICTION_EXECUTION_MODE: "live",
      BILL_PREDICTION_LIVE_EXECUTION_ENABLED: "false",
      BILL_PREDICTION_LIVE_ACKNOWLEDGED: "true",
      BILL_PREDICTION_LIVE_MAX_STAKE: "1",
      BILL_PREDICTION_BANKROLL_CURRENCY: "USD",
      RH_MODE: "live"
    } as NodeJS.ProcessEnv);

    expect(result.ok).toBe(false);
    expect(result.blockers).toContain("BILL_PREDICTION_LIVE_EXECUTION_ENABLED must be exactly 'true'.");
  });

  it("refuses live when prediction review is blocked by no-edge memory", async () => {
    const { reviewPath, promotionPath } = await writeArtifacts({
      readyForPaper: false,
      currentStage: "research",
      recommendedStage: "research",
      blockers: ["no-edge-memory-active"]
    });

    const result = await authorizePmBotLiveRequest({
      BILL_PREDICTION_REVIEW_PATH: reviewPath,
      BILL_PROMOTION_STATE_PATH: promotionPath,
      BILL_PREDICTION_EXECUTION_MODE: "live",
      BILL_PREDICTION_LIVE_EXECUTION_ENABLED: "true",
      BILL_PREDICTION_LIVE_ACKNOWLEDGED: "true",
      BILL_PREDICTION_LIVE_MAX_STAKE: "1",
      BILL_PREDICTION_BANKROLL_CURRENCY: "USD",
      RH_MODE: "live"
    } as NodeJS.ProcessEnv);

    expect(result.ok).toBe(false);
    expect(result.authorization.reason).toBe("prediction review has blockers: no-edge-memory-active");
  });

  it("allows live only when env, review, and promotion all agree", async () => {
    const { reviewPath, promotionPath } = await writeArtifacts({
      readyForPaper: true,
      currentStage: "live",
      recommendedStage: "live"
    });

    const result = await authorizePmBotLiveRequest({
      BILL_PREDICTION_REVIEW_PATH: reviewPath,
      BILL_PROMOTION_STATE_PATH: promotionPath,
      BILL_PREDICTION_EXECUTION_MODE: "live",
      BILL_PREDICTION_LIVE_EXECUTION_ENABLED: "true",
      BILL_PREDICTION_LIVE_ACKNOWLEDGED: "true",
      BILL_PREDICTION_LIVE_MAX_STAKE: "1",
      BILL_PREDICTION_BANKROLL_CURRENCY: "USD",
      RH_MODE: "live"
    } as NodeJS.ProcessEnv);

    expect(result.ok).toBe(true);
    expect(result.blockers).toEqual([]);
  });
});
