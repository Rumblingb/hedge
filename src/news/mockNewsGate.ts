import { DateTime } from "luxon";
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

export interface MockNewsGateOptions {
  headlines?: MockHeadline[];
  blackoutMinutesBefore?: number;
  blackoutMinutesAfter?: number;
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

  private readonly headlines: MockHeadline[];
  private readonly blackoutMinutesBefore: number;
  private readonly blackoutMinutesAfter: number;

  public constructor(options: MockNewsGateOptions = {}) {
    this.headlines = options.headlines ?? SAMPLE_HEADLINES;
    this.blackoutMinutesBefore = options.blackoutMinutesBefore ?? 15;
    this.blackoutMinutesAfter = options.blackoutMinutesAfter ?? 30;
  }

  public score(input: { symbol: string; ts: string; bar: Bar }): NewsScore {
    const barTime = DateTime.fromISO(input.ts, { zone: "utc" });
    const match = this.headlines
      .map((headline) => {
        const eventTime = DateTime.fromISO(headline.ts, { zone: "utc" });
        const minutesFromEvent = barTime.diff(eventTime, "minutes").minutes;
        const active = minutesFromEvent >= -this.blackoutMinutesBefore && minutesFromEvent <= this.blackoutMinutesAfter;

        return {
          headline,
          eventTime,
          minutesFromEvent,
          active
        };
      })
      .filter((candidate) => candidate.headline.symbol === input.symbol && candidate.active)
      .sort((left, right) => Math.abs(left.minutesFromEvent) - Math.abs(right.minutesFromEvent))[0];

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
      direction: match.headline.direction,
      probability: match.headline.probability,
      impact: match.headline.impact,
      headline: match.headline.headline,
      reason: `red-folder news blackout around ${match.headline.headline}`,
      blackout: {
        active: true,
        eventTs: match.headline.ts,
        minutesBefore: this.blackoutMinutesBefore,
        minutesAfter: this.blackoutMinutesAfter,
        label: match.headline.headline
      }
    };
  }
}
