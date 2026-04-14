import { describe, expect, it } from "vitest";
import { scanPredictionCandidates } from "../src/prediction/matcher.js";
import { buildPredictionReport } from "../src/prediction/report.js";
import { DEFAULT_PREDICTION_FEES } from "../src/prediction/fees.js";
import { DEFAULT_PREDICTION_SIZING } from "../src/prediction/sizing.js";

const markets = [
  { venue: "polymarket", externalId: "1", eventTitle: "2026 FIFA World Cup Winner", marketQuestion: "Will Spain win the 2026 FIFA World Cup?", outcomeLabel: "Yes", side: "yes" as const, expiry: "2026-11-03", settlementText: "If Spain wins", price: 0.41, displayedSize: 500 },
  { venue: "polymarket", externalId: "2", eventTitle: "2026 FIFA World Cup Winner", marketQuestion: "Will Spain win the 2026 FIFA World Cup?", outcomeLabel: "No", side: "yes" as const, expiry: "2026-11-03", settlementText: "If Spain does not win", price: 0.59, displayedSize: 500 },
  { venue: "kalshi", externalId: "A", eventTitle: "Spain to win the 2026 FIFA World Cup", marketQuestion: "Will Spain win the 2026 FIFA World Cup?", outcomeLabel: "Yes", side: "yes" as const, expiry: "2026-11-03", settlementText: "If Spain wins", price: 0.36, displayedSize: 400 },
  { venue: "kalshi", externalId: "B", eventTitle: "Will Y win?", marketQuestion: "Will Y win?", outcomeLabel: "Yes", side: "yes" as const, expiry: "2026-11-03", settlementText: "If Y wins", price: 0.33, displayedSize: 50 }
];

describe("prediction scanner", () => {
  it("normalizes equivalent contracts and emits bankroll-aware sizing", () => {
    const rows = scanPredictionCandidates({ markets, fees: DEFAULT_PREDICTION_FEES, sizing: DEFAULT_PREDICTION_SIZING, ts: "2026-04-13T17:26:00Z" });
    expect(rows).toHaveLength(1);
    expect(rows[0].verdict).toBe("paper-trade");
    expect(rows[0].normalizedOutcomeKey).toBe("yes");
    expect(rows[0].entityOverlap).toBeGreaterThan(0.7);
    expect(rows[0].sizing?.venue).toBe("kalshi");
    expect(rows[0].sizing?.recommendedStake).toBeGreaterThan(0);
    const report = buildPredictionReport(rows);
    expect(report.counts["paper-trade"]).toBe(1);
    expect(report.counts.reject).toBe(0);
  });
});
