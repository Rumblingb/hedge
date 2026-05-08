import { describe, expect, it } from "vitest";
import {
  assessHypothesisNovelty,
  dedupeStrategyHypotheses,
  deriveFallbackTranscriptHypotheses,
  deriveStrategyHypothesesFromResearchChunks,
  hypothesisMechanicsHash,
  isStrategySeedEligible
} from "../src/research/strategyHypotheses.js";

describe("research strategy hypothesis derivation", () => {
  it("does not turn generic market news into strategy hypotheses", () => {
    const chunk = {
      sourceId: "yahoo-finance-stock-market-news",
      sourceKind: "web",
      url: "https://finance.yahoo.com/news/",
      title: "Latest Stock Market News",
      tags: ["prediction", "futures-core", "macro-rates", "event-driven"],
      text: `${"Stocks moved before earnings while investors watched macro headlines, liquidity, spreads, and futures. ".repeat(20)}`
    };

    expect(isStrategySeedEligible(chunk)).toBe(false);
    expect(deriveStrategyHypothesesFromResearchChunks([chunk])).toEqual([]);
  });

  it("keeps high-signal paper-like research as test-only hypotheses", () => {
    const chunk = {
      sourceId: "managed-futures-trend",
      sourceKind: "web",
      title: "Managed Futures Trend Research",
      tags: ["futures-core", "trend-following", "volatility-targeting"],
      text: [
        "Managed futures research studies trend following, volatility targeting, breakout continuation, and time series momentum across liquid futures markets.",
        "The process must be tested with walk-forward validation, out-of-sample regime splits, slippage, and transaction cost stress before any paper promotion."
      ].join(" ")
    };

    const hypotheses = deriveStrategyHypothesesFromResearchChunks([chunk]);

    expect(isStrategySeedEligible(chunk)).toBe(true);
    expect(hypotheses.map((hypothesis) => hypothesis.title)).toContain("Research-seeded session momentum with volatility filter");
  });

  it("builds a low-confidence transcript fallback when model extraction fails", () => {
    const hypotheses = deriveFallbackTranscriptHypotheses({
      targetId: "ict-youtube-transcripts",
      videoId: "abc123",
      title: "ICT NQ futures fair value gap lesson",
      channel: "ICT Desk",
      url: "https://www.youtube.com/watch?v=abc123",
      language: "en",
      transcriptText: [
        "After the New York open, wait for a liquidity sweep below the session low.",
        "The entry is only after displacement leaves a fair value gap and price retests that gap.",
        "The stop belongs beyond the sweep extreme and the target is the opposing liquidity pool near the prior high."
      ].join(" ")
    });

    expect(hypotheses).toHaveLength(1);
    expect(hypotheses[0]?.automationReadiness).toBe("low");
    expect(hypotheses[0]?.symbols).toEqual(["NQ"]);
    expect(hypotheses[0]?.sourceVideoIds).toEqual(["abc123"]);
  });

  it("dedupes repeated strategy titles while preserving video provenance", () => {
    const first = deriveFallbackTranscriptHypotheses({
      targetId: "ict-youtube-transcripts",
      videoId: "abc123",
      title: "ICT NQ futures fair value gap lesson",
      channel: "ICT Desk",
      url: "https://www.youtube.com/watch?v=abc123",
      transcriptText: "Liquidity sweep below the low. Displacement leaves a fair value gap. Stop below the sweep and target the prior high liquidity pool."
    })[0]!;
    const second = {
      ...first,
      sourceVideoIds: ["def456"],
      sourceVideoTitles: ["ICT ES futures fair value gap lesson"],
      sourceUrls: ["https://www.youtube.com/watch?v=def456"]
    };

    const deduped = dedupeStrategyHypotheses([first, second]);

    expect(deduped).toHaveLength(1);
    expect(deduped[0]?.sourceVideoIds.sort()).toEqual(["abc123", "def456"]);
  });

  it("dedupes renamed exact-copy mechanics and flags graveyard variants", () => {
    const base = deriveFallbackTranscriptHypotheses({
      targetId: "ict-youtube-transcripts",
      videoId: "abc123",
      title: "ICT NQ futures fair value gap lesson",
      channel: "ICT Desk",
      url: "https://www.youtube.com/watch?v=abc123",
      transcriptText: "Liquidity sweep below the low. Displacement leaves a fair value gap. Stop below the sweep and target the prior high liquidity pool."
    })[0]!;
    const renamed = {
      ...base,
      id: "renamed-id",
      title: "Renamed ICT FVG replay"
    };
    const variant = {
      ...base,
      id: "variant-id",
      title: "ICT FVG replay with volume filter",
      confluence: [...base.confluence, "volume expansion"]
    };

    expect(dedupeStrategyHypotheses([base, renamed])).toHaveLength(1);

    const graveyard = {
      version: 1 as const,
      updatedAt: "2026-05-08T00:00:00.000Z",
      entries: [{
        id: "old-tested-id",
        title: "Old ICT FVG replay",
        status: "dead" as const,
        reason: "negative OOS",
        mechanics: [`sha1:${hypothesisMechanicsHash(base)}`],
        killedAt: "2026-05-08T00:00:00.000Z",
        killedBy: "oos-failure" as const
      }]
    };

    expect(assessHypothesisNovelty(renamed, graveyard).verdict).toBe("duplicate");
    expect(assessHypothesisNovelty(variant, {
      ...graveyard,
      entries: [{
        ...graveyard.entries[0]!,
        mechanics: [
          [
            base.setupSummary,
            ...base.entryRules,
            ...base.stopRules,
            ...base.targetRules,
            ...base.riskRules,
            ...base.invalidationRules
          ].join(" ")
        ],
        mechanicsHash: undefined
      }]
    }, { duplicateSimilarity: 0.99 }).verdict).toBe("variant");
  });
});
