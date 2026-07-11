import { mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { loadLatestResearchStrategyFeed } from "../src/research/strategyFeed.js";
import type { StrategyHypothesisArtifact } from "../src/research/strategyHypotheses.js";

function buildArtifact(overrides: Partial<StrategyHypothesisArtifact> = {}): StrategyHypothesisArtifact {
  return {
    generatedAt: new Date().toISOString(),
    runId: "fresh-run",
    count: 1,
    provider: "ollama",
    model: "test-model",
    hypotheses: [
      {
        id: "ict-nq",
        title: "ICT NQ liquidity raid displacement setup",
        market: "futures",
        symbols: ["NQ"],
        timeframes: ["1m"],
        sessions: ["New York AM"],
        setupSummary: "Wait for a liquidity raid, displacement, and fair value gap continuation.",
        biasRules: ["Use session bias only after a clear liquidity sweep."],
        entryRules: ["Enter on displacement through a fair value gap."],
        stopRules: ["Stop beyond the swept liquidity."],
        targetRules: ["Target opposing liquidity."],
        riskRules: ["Skip if reward/risk is poor."],
        confluence: ["ICT", "FVG", "market structure shift"],
        invalidationRules: ["No trade if displacement fails."],
        evidence: ["Liquidity raid then displacement."],
        automationReadiness: "high",
        confidence: 0.9,
        sourceTargetIds: ["ict-youtube-audio"],
        sourceVideoIds: ["abc123"],
        sourceVideoTitles: ["ICT futures lesson"],
        sourceChannels: ["ICT"],
        sourceUrls: ["https://youtube.com/watch?v=abc123"]
      }
    ],
    ...overrides
  };
}

describe("research strategy feed", () => {
  it("rejects strategy artifacts from stale or unrelated researcher runs", async () => {
    const dir = await mkdtemp(join(tmpdir(), "strategy-feed-"));
    const artifactPath = join(dir, "strategy-hypotheses.latest.json");
    await writeFile(artifactPath, JSON.stringify(buildArtifact()), "utf8");

    const fresh = await loadLatestResearchStrategyFeed(artifactPath, {
      requiredRunId: "fresh-run",
      maxAgeMs: 60_000
    });
    expect(fresh?.runId).toBe("fresh-run");
    expect(fresh?.preferredStrategies).toContain("ict-displacement");

    await expect(loadLatestResearchStrategyFeed(artifactPath, {
      requiredRunId: "other-run",
      maxAgeMs: 60_000
    })).resolves.toBeNull();

    await writeFile(
      artifactPath,
      JSON.stringify(buildArtifact({ generatedAt: "2020-01-01T00:00:00.000Z" })),
      "utf8"
    );
    await expect(loadLatestResearchStrategyFeed(artifactPath, {
      requiredRunId: "fresh-run",
      maxAgeMs: 60_000
    })).resolves.toBeNull();
  });
});
