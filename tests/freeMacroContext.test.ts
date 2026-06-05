import { describe, expect, it } from "vitest";
import {
  deriveFreeMacroContext,
  parseYahooMacroChart,
  summarizeFreeMacroSeries,
  type FreeMacroSeries
} from "../src/research/freeMacroContext.js";

function series(id: string, values: number[]): FreeMacroSeries {
  const points = values.map((value, index) => ({
    ts: new Date(Date.UTC(2026, 0, index + 1)).toISOString(),
    value
  }));
  return summarizeFreeMacroSeries({
    id,
    yahooSymbol: id.toUpperCase(),
    title: id,
    points
  });
}

describe("free macro context", () => {
  it("parses Yahoo daily macro closes", () => {
    const points = parseYahooMacroChart({
      payload: {
        chart: {
          result: [{
            timestamp: [1_766_000_000, 1_766_086_400],
            indicators: {
              quote: [{ close: [19.5, null, 21.25] }]
            }
          }]
        }
      }
    });

    expect(points).toEqual([
      { ts: "2025-12-17T19:33:20.000Z", value: 19.5 }
    ]);
  });

  it("raises the risk gate on VIX backwardation and credit stress", () => {
    const values = Array.from({ length: 65 }, (_, index) => 100 - index);
    const derived = deriveFreeMacroContext([
      series("vix", [...Array(64).fill(20), 36]),
      series("vix3m", [...Array(64).fill(23), 32]),
      series("tnx", [...Array(64).fill(4.5), 4.1]),
      series("fvx", [...Array(64).fill(4.2), 4.4]),
      series("hyg", values),
      series("lqd", Array.from({ length: 65 }, () => 100)),
      series("spy", values)
    ]);

    expect(derived.vixTermStructure).toBe("backwardation");
    expect(derived.creditRiskProxy).toBe("weakening");
    expect(derived.riskRegime).toBe("stress");
    expect(derived.tailScore).toBeGreaterThan(65);
  });
});
