import { describe, expect, it } from "vitest";
import { MockNewsGate } from "../src/news/mockNewsGate.js";

describe("MockNewsGate", () => {
  it("marks red-folder events as active across the 15 minute before and 30 minute after window", () => {
    const gate = new MockNewsGate({
      headlines: [
        {
          symbol: "NQ",
          ts: "2026-04-01T14:00:00.000Z",
          direction: "flat",
          probability: 0.92,
          impact: "high",
          headline: "FOMC red-folder release"
        }
      ],
      blackoutMinutesBefore: 15,
      blackoutMinutesAfter: 30
    });

    const before = gate.score({
      symbol: "NQ",
      ts: "2026-04-01T13:50:00.000Z",
      bar: {
        ts: "2026-04-01T13:50:00.000Z",
        symbol: "NQ",
        open: 100,
        high: 100,
        low: 100,
        close: 100,
        volume: 1
      }
    });
    const after = gate.score({
      symbol: "NQ",
      ts: "2026-04-01T14:20:00.000Z",
      bar: {
        ts: "2026-04-01T14:20:00.000Z",
        symbol: "NQ",
        open: 100,
        high: 100,
        low: 100,
        close: 100,
        volume: 1
      }
    });
    const outside = gate.score({
      symbol: "NQ",
      ts: "2026-04-01T14:31:00.000Z",
      bar: {
        ts: "2026-04-01T14:31:00.000Z",
        symbol: "NQ",
        open: 100,
        high: 100,
        low: 100,
        close: 100,
        volume: 1
      }
    });

    expect(before.blackout?.active).toBe(true);
    expect(after.blackout?.active).toBe(true);
    expect(outside.blackout).toBeUndefined();
    expect(before.reason).toContain("red-folder news blackout");
  });
});
