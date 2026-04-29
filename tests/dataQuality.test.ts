import { describe, expect, it } from "vitest";
import { assessBarsForResearch, assertBarsResearchReady } from "../src/data/quality.js";
import type { Bar } from "../src/domain.js";

function bar(symbol: string, minute: number): Bar {
  return {
    ts: `2026-04-24T13:${String(minute).padStart(2, "0")}:00.000Z`,
    symbol,
    open: 1,
    high: 2,
    low: 0.5,
    close: 1.5,
    volume: 100
  };
}

describe("assessBarsForResearch", () => {
  it("fails when a required futures symbol is missing from a partial dataset", () => {
    const report = assessBarsForResearch(
      [bar("NQ", 30), bar("ES", 30), bar("NQ", 31), bar("ES", 31)],
      {
        requiredSymbols: ["NQ", "ES", "6E"]
      }
    );

    expect(report.pass).toBe(false);
    expect(report.checks.find((check) => check.name === "requiredSymbols")?.passed).toBe(false);
    expect(() => assertBarsResearchReady(
      [bar("NQ", 30), bar("ES", 30)],
      { requiredSymbols: ["NQ", "ES", "6E"] }
    )).toThrow(/Missing symbols: 6E/);
  });
});
