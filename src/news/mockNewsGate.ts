import type { Bar, NewsDirection, NewsScore } from "../domain.js";
import type { NewsGate } from "./base.js";

export interface MockHeadline {
  symbol: string;
  ts: string;
  direction: NewsDirection;
  probability: number;
  impact: "low" | "medium" | "high";
  headline: string;
}

export const SAMPLE_HEADLINES: MockHeadline[] = [
  {
    symbol: "CL",
    ts: "2026-04-01T14:00:00.000Z",
    direction: "long",
    probability: 0.72,
    impact: "high",
    headline: "Inventory draw pushes crude higher"
  },
  {
    symbol: "GC",
    ts: "2026-04-01T15:10:00.000Z",
    direction: "short",
    probability: 0.69,
    impact: "high",
    headline: "Treasury yields firm and pressure gold"
  }
];

export class MockNewsGate implements NewsGate {
  public readonly name = "mock-news-gate";

  public constructor(private readonly headlines: MockHeadline[] = SAMPLE_HEADLINES) {}

  public score(input: { symbol: string; ts: string; bar: Bar }): NewsScore {
    const match = this.headlines.find(
      (headline) => headline.symbol === input.symbol && headline.ts === input.ts
    );

    if (!match) {
      return {
        provider: this.name,
        direction: "flat",
        probability: 0.5,
        impact: "low",
        reason: "no scheduled mock headline"
      };
    }

    return {
      provider: this.name,
      direction: match.direction,
      probability: match.probability,
      impact: match.impact,
      headline: match.headline,
      reason: match.headline
    };
  }
}
