import { describe, expect, it } from "vitest";
import { normalizeUniverseByInnerTimestamp } from "../src/data/normalize.js";

describe("normalizeUniverseByInnerTimestamp", () => {
  it("keeps only timestamps present for all symbols", () => {
    const bars = [
      { ts: "2026-04-01T00:00:00.000Z", symbol: "NQ", open: 1, high: 2, low: 1, close: 2, volume: 10 },
      { ts: "2026-04-01T00:00:00.000Z", symbol: "ES", open: 1, high: 2, low: 1, close: 2, volume: 10 },
      { ts: "2026-04-01T00:01:00.000Z", symbol: "NQ", open: 2, high: 3, low: 2, close: 3, volume: 11 },
      { ts: "2026-04-01T00:02:00.000Z", symbol: "NQ", open: 3, high: 4, low: 3, close: 4, volume: 12 },
      { ts: "2026-04-01T00:02:00.000Z", symbol: "ES", open: 3, high: 4, low: 3, close: 4, volume: 12 }
    ];

    const result = normalizeUniverseByInnerTimestamp(bars);

    expect(result.keptTimestamps).toBe(2);
    expect(result.droppedTimestamps).toBe(1);
    expect(result.outputRows).toBe(4);
    expect(result.coverageAfter.NQ).toBe(1);
    expect(result.coverageAfter.ES).toBe(1);
  });
});
