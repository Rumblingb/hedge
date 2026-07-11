import { describe, expect, it } from "vitest";
import { heuristicClassifier } from "../src/research/filter.js";

describe("research filter topic heuristics", () => {
  it("rewards trend-following and carry material when those themes are targeted", () => {
    const text = [
      "Systematic trend following across futures often combines time series momentum with carry and roll-yield awareness.",
      "Managed futures programs size positions by volatility, trade long and short, and diversify across equities, rates, FX, and commodities.",
      "Cross-asset signals use term structure and yield differentials to separate persistent carry from fragile directional bets."
    ].join(" ");

    const result = heuristicClassifier(text, 600, {
      tags: ["trend-following", "carry"],
      topics: ["trend following", "carry"]
    });

    expect(result.score).toBeGreaterThanOrEqual(3);
    expect(result.signals.some((signal) => signal.startsWith("topic-hit:") || signal.startsWith("topic-thin:"))).toBe(true);
    expect(result.signals).not.toContain("topic-miss");
  });

  it("treats execution alpha and market-neutral material as on-topic for those lanes", () => {
    const text = [
      "A market maker prices around a theoretical value, manages inventory risk, and earns the bid-ask spread through disciplined execution quality.",
      "Market-neutral relative-value books pair long and short exposures so alpha comes from spread convergence rather than outright beta."
    ].join(" ");

    const result = heuristicClassifier(text, 600, {
      tags: ["execution-alpha", "market-neutral"],
      topics: ["execution alpha", "market neutral"]
    });

    expect(result.score).toBeGreaterThanOrEqual(3);
    expect(result.signals.some((signal) => signal.startsWith("topic-hit:") || signal.startsWith("topic-thin:"))).toBe(true);
    expect(result.signals).not.toContain("topic-miss");
  });

  it("recognizes short-horizon crypto prediction-market material", () => {
    const text = [
      "Bitcoin up or down contracts over 5-minute and 15-minute windows create a microstructure problem, not a macro view.",
      "The execution question is whether live quote quality, price-to-beat drift, and the reference stream diverge enough to survive fees and slippage.",
      "Short-horizon crypto prediction markets are only attractive when the trader has better timing than the crowd."
    ].join(" ");

    const result = heuristicClassifier(text, 600, {
      tags: ["prediction", "crypto-liquid", "short-horizon", "execution-alpha"],
      topics: ["short-horizon prediction markets", "crypto market microstructure"]
    });

    expect(result.score).toBeGreaterThanOrEqual(3);
    expect(result.signals.some((signal) => signal.startsWith("topic-hit:") || signal.startsWith("topic-thin:"))).toBe(true);
    expect(result.signals).not.toContain("topic-miss");
  });
});
