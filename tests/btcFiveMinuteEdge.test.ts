import { describe, expect, it } from "vitest";
import type { Bar } from "../src/domain.js";
import { buildBtcFiveMinuteEdgeReport } from "../src/prediction/btcFiveMinuteEdge.js";

function bar(ts: string, open: number, close: number): Bar {
  const high = Math.max(open, close) + 0.5;
  const low = Math.min(open, close) - 0.5;
  return { ts, symbol: "BTCUSD", open, high, low, close, volume: 1 };
}

describe("buildBtcFiveMinuteEdgeReport", () => {
  it("counts flat bars as part of the >= up bucket", () => {
    const bars: Bar[] = [
      bar("2026-04-01T00:00:00.000Z", 100, 101),
      bar("2026-04-01T00:05:00.000Z", 101, 102),
      bar("2026-04-01T00:10:00.000Z", 102, 103),
      bar("2026-04-01T00:15:00.000Z", 103, 103),
      bar("2026-04-01T00:20:00.000Z", 103, 102),
      bar("2026-04-01T00:25:00.000Z", 102, 102)
    ];

    const report = buildBtcFiveMinuteEdgeReport({
      bars,
      trendLookbackBars: 2,
      volatilityLookbackBars: 2,
      trendThresholdZ: 0.25
    });

    expect(report.sampleSize).toBe(4);
    expect(report.unconditional.flatCount).toBe(2);
    expect(report.unconditional.pGe).toBe(0.75);
  });

  it("surfaces bullish and bearish conditional buckets", () => {
    const bars: Bar[] = [
      bar("2026-04-01T00:00:00.000Z", 100, 101),
      bar("2026-04-01T00:05:00.000Z", 101, 102),
      bar("2026-04-01T00:10:00.000Z", 102, 103),
      bar("2026-04-01T00:15:00.000Z", 103, 104),
      bar("2026-04-01T00:20:00.000Z", 104, 105),
      bar("2026-04-01T00:25:00.000Z", 105, 106),
      bar("2026-04-01T00:30:00.000Z", 106, 105),
      bar("2026-04-01T00:35:00.000Z", 105, 104),
      bar("2026-04-01T00:40:00.000Z", 104, 103),
      bar("2026-04-01T00:45:00.000Z", 103, 102),
      bar("2026-04-01T00:50:00.000Z", 102, 101),
      bar("2026-04-01T00:55:00.000Z", 101, 100)
    ];

    const report = buildBtcFiveMinuteEdgeReport({
      bars,
      trendLookbackBars: 3,
      volatilityLookbackBars: 3,
      trendThresholdZ: 0.4
    });

    expect(report.states.find((bucket) => bucket.label === "bullish")?.count).toBeGreaterThan(0);
    expect(report.states.find((bucket) => bucket.label === "bearish")?.count).toBeGreaterThan(0);
    expect(report.latestSignal).not.toBeNull();
  });
});
