import { describe, expect, it } from "vitest";
import type { Bar } from "../src/domain.js";
import { runMarkovOosReport, runMarkovReturnBacktest } from "../src/research/markov.js";

function dailyBars(closes: number[], symbol = "AAPL"): Bar[] {
  return closes.map((close, index) => ({
    ts: `2026-01-${String(index + 1).padStart(2, "0")}T21:00:00.000Z`,
    symbol,
    open: close,
    high: close,
    low: close,
    close,
    volume: 1_000_000
  }));
}

describe("discrete-time Markov return model", () => {
  it("scores next-return predictions against actual walk-forward returns", () => {
    const bars = dailyBars([100, 101, 102.01, 103.0301, 51.51505, 52.0302]);
    const report = runMarkovReturnBacktest(bars, {
      thresholds: [-0.005, 0.005],
      minTrainingTransitions: 2,
      signalThreshold: 0.001,
      smoothing: 0
    });

    const firstPrediction = report.symbols[0]?.latestPredictions[0];
    expect(firstPrediction).toBeDefined();
    expect(firstPrediction?.predictedAtTs).toBe("2026-01-04T21:00:00.000Z");
    expect(firstPrediction?.targetTs).toBe("2026-01-05T21:00:00.000Z");
    expect(firstPrediction?.predictedReturn).toBeGreaterThan(0);
    expect(firstPrediction?.actualReturn).toBeLessThan(0);
    expect(firstPrediction?.hit).toBe(false);
  });

  it("summarizes actionable long and short Markov signals", () => {
    const bars = [
      ...dailyBars([100, 101, 102.01, 103.03, 104.06, 105.1, 106.15], "AAPL"),
      ...dailyBars([100, 99, 98.01, 97.03, 96.06, 95.1, 94.15], "MSFT")
    ];
    const report = runMarkovReturnBacktest(bars, {
      thresholds: [-0.005, 0.005],
      minTrainingTransitions: 2,
      signalThreshold: 0.001,
      smoothing: 0
    });

    expect(report.aggregate.symbols).toBe(2);
    expect(report.aggregate.predictions).toBeGreaterThan(0);
    expect(report.aggregate.longSignals).toBeGreaterThan(0);
    expect(report.aggregate.shortSignals).toBeGreaterThan(0);
    expect(report.aggregate.mae).not.toBeNull();
  });

  it("ranks symbols by OOS edge against the mean-return baseline", () => {
    const bars = [
      ...dailyBars([100, 101, 102.01, 103.03, 104.06, 105.1, 106.15, 107.21, 108.28, 109.36], "TREND"),
      ...dailyBars([100, 101, 99.99, 100.99, 99.98, 100.98, 99.97, 100.97, 99.96, 100.96], "CHOP")
    ];
    const report = runMarkovOosReport(bars, {
      thresholds: [-0.005, 0.005],
      trainReturns: 4,
      testReturns: 2,
      stepReturns: 1,
      smoothing: 0,
      signalThreshold: 0.001
    });

    expect(report.aggregate.windows).toBeGreaterThan(0);
    expect(report.ranking).toHaveLength(2);
    expect(report.ranking[0]?.edgeMae).not.toBeNull();
    expect(report.symbols.every((symbol) => symbol.latestWindows.length > 0)).toBe(true);
  });
});
