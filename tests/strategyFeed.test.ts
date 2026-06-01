import { mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { loadLatestResearchStrategyFeed, writeResearchStrategyFeedArtifact } from "../src/research/strategyFeed.js";
import { hasDurableStrategyEvidence, hypothesisMechanicsHash, type StrategyHypothesisArtifact } from "../src/research/strategyHypotheses.js";

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

  it("does not promote vague transcript cards into strategy directives", async () => {
    const dir = await mkdtemp(join(tmpdir(), "strategy-feed-"));
    const artifactPath = join(dir, "strategy-hypotheses.latest.json");
    await writeFile(
      artifactPath,
      JSON.stringify(buildArtifact({
        hypotheses: [
          {
            ...buildArtifact().hypotheses[0],
            title: "Vague ICT motivation card",
            entryRules: ["Wait for confirmation and trust smart money."],
            stopRules: [],
            targetRules: [],
            riskRules: ["Be careful."],
            invalidationRules: [],
            evidence: ["Be patient."],
            automationReadiness: "high",
            confidence: 0.99
          }
        ]
      })),
      "utf8"
    );

    const feed = await loadLatestResearchStrategyFeed(artifactPath, { maxAgeMs: 60_000 });

    expect(feed?.preferredStrategies).toEqual([]);
    expect(feed?.directives).toEqual([]);
  });

  it("keeps promotional backtest/video claims out of strategy directives", async () => {
    const dir = await mkdtemp(join(tmpdir(), "strategy-feed-"));
    const artifactPath = join(dir, "strategy-hypotheses.latest.json");
    await writeFile(
      artifactPath,
      JSON.stringify(buildArtifact({
        hypotheses: [
          {
            ...buildArtifact().hypotheses[0],
            title: "Promotional FVG backtest card",
            evidence: [
              "Example trade: $945 risk for $1,900 profit in 35 minutes",
              "Backtest: $15,400 profit with 81% win rate over 16 trades"
            ],
            automationReadiness: "high",
            confidence: 0.99
          }
        ]
      })),
      "utf8"
    );

    const feed = await loadLatestResearchStrategyFeed(artifactPath, { maxAgeMs: 60_000 });

    expect(hasDurableStrategyEvidence([
      "New mechanics hash sha1:abc123.",
      "179% profit in backtest vs. market -66% over the same period",
      "Backtest: $15,400 profit with 81% win rate over 16 trades"
    ])).toBe(false);
    expect(feed?.preferredStrategies).toEqual([]);
    expect(feed?.directives).toEqual([]);
  });

  it("writes a compact latest strategy-feed artifact from hypotheses", async () => {
    const dir = await mkdtemp(join(tmpdir(), "strategy-feed-"));
    const artifactPath = join(dir, "strategy-hypotheses.latest.json");
    const outputPath = join(dir, "strategy-feed.latest.json");
    const artifact = buildArtifact();

    const result = await writeResearchStrategyFeedArtifact({
      artifact,
      artifactPath,
      outputPath,
      blockedStrategies: []
    });

    expect(result.feed.preferredStrategies).toContain("ict-displacement");
    const persisted = JSON.parse(await readFile(outputPath, "utf8")) as Awaited<ReturnType<typeof loadLatestResearchStrategyFeed>>;
    expect(persisted?.directives.length).toBeGreaterThan(0);
    expect(persisted?.artifactPath).toBe(artifactPath);
  });

  it("filters strategies that the no-edge ledger has quarantined", async () => {
    const dir = await mkdtemp(join(tmpdir(), "strategy-feed-"));
    const artifactPath = join(dir, "strategy-hypotheses.latest.json");
    await writeFile(artifactPath, JSON.stringify(buildArtifact()), "utf8");

    const feed = await loadLatestResearchStrategyFeed(artifactPath, {
      maxAgeMs: 60_000,
      blockedStrategies: ["ict-displacement", "liquidity-reversion"]
    });

    expect(feed?.preferredStrategies).not.toContain("ict-displacement");
    expect(feed?.directives.some((directive) => directive.strategyId === "ict-displacement")).toBe(false);
    expect(feed?.blockedDirectiveCount).toBeGreaterThanOrEqual(1);
    expect(feed?.blockedDirectives.map((directive) => directive.strategyId)).toContain("ict-displacement");
    expect(feed?.directiveBlockReason).toBe("all machine-testable directive candidates are blocked by no-edge/non-promotable memory");
  });

  it("ignores exact mechanics already buried in the graveyard", async () => {
    const artifact = buildArtifact();
    const dir = await mkdtemp(join(tmpdir(), "strategy-feed-"));
    const artifactPath = join(dir, "strategy-hypotheses.latest.json");
    await writeFile(artifactPath, JSON.stringify(artifact), "utf8");

    const feed = await loadLatestResearchStrategyFeed(artifactPath, {
      maxAgeMs: 60_000,
      graveyard: {
        version: 1,
        updatedAt: "2026-05-08T00:00:00.000Z",
        entries: [{
          id: "dead-ict",
          title: "Dead renamed ICT setup",
          status: "dead",
          reason: "negative OOS",
          mechanics: [`sha1:${hypothesisMechanicsHash(artifact.hypotheses[0]!)}`],
          killedAt: "2026-05-08T00:00:00.000Z",
          killedBy: "oos-failure"
        }]
      }
    });

    expect(feed?.strategyCount).toBe(0);
    expect(feed?.directives).toEqual([]);
  });

  it("normalizes futures symbols without matching ordinary words like close", async () => {
    const dir = await mkdtemp(join(tmpdir(), "strategy-feed-"));
    const artifactPath = join(dir, "strategy-hypotheses.latest.json");
    await writeFile(
      artifactPath,
      JSON.stringify(buildArtifact({
        hypotheses: [
          {
            ...buildArtifact().hypotheses[0],
            title: "ORB and IFVG card for NAS 100 and Gold",
            symbols: ["NAS 100", "Gold (implied, e.g., GC)"],
            setupSummary: "A close through an inversion fair value gap creates a replay setup.",
            evidence: ["Close below bullish FVG then target opposing liquidity."]
          }
        ]
      })),
      "utf8"
    );

    const feed = await loadLatestResearchStrategyFeed(artifactPath, { maxAgeMs: 60_000 });

    expect(feed?.preferredSymbols).toEqual(expect.arrayContaining(["NQ", "GC"]));
    expect(feed?.preferredSymbols).not.toContain("CL");
  });
});
