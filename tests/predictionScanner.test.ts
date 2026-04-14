import { describe, expect, it } from "vitest";
import { scanPredictionCandidates } from "../src/prediction/matcher.js";
import { lineCompatible } from "../src/prediction/normalize.js";
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

  it("treats close numeric lines as compatible instead of requiring an exact match", () => {
    expect(lineCompatible(100, 98)).toBe(true);
    expect(lineCompatible(100, 90)).toBe(false);
  });

  it("does not reject same-month contracts with overlapping settlement language", () => {
    const rows = scanPredictionCandidates({
      markets: [
        {
          venue: "polymarket",
          externalId: "wti-same-month-a",
          eventTitle: "WTI Crude Oil April",
          marketQuestion: "Will WTI crude oil be above $100 in April 2026?",
          outcomeLabel: "Yes",
          side: "yes",
          expiry: "2026-04-30T00:00:00Z",
          settlementText: "Resolves yes if WTI crude oil trades above 100 at any point in April 2026.",
          price: 0.41,
          displayedSize: 500
        },
        {
          venue: "manifold",
          externalId: "wti-same-month-b",
          eventTitle: "WTI Crude Oil April",
          marketQuestion: "Will WTI crude oil be above $100 in April 2026?",
          outcomeLabel: "Yes",
          side: "yes",
          expiry: "2026-04-20T00:00:00Z",
          settlementText: "Resolves yes if WTI crude oil goes above 100 sometime in April 2026.",
          price: 0.48,
          displayedSize: 500
        }
      ],
      fees: DEFAULT_PREDICTION_FEES,
      sizing: DEFAULT_PREDICTION_SIZING,
      ts: "2026-04-13T17:26:00Z"
    });

    expect(rows).toHaveLength(1);
    expect(rows[0].reasons).not.toContain("expiry-mismatch");
    expect(rows[0].reasons).not.toContain("settlement-unclear");
    expect(rows[0].verdict).not.toBe("reject");
  });

  it("filters structurally different resolution styles even when the asset overlap is high", () => {
    const rows = scanPredictionCandidates({
      markets: [
        {
          venue: "polymarket",
          externalId: "touch-high",
          eventTitle: "What will WTI Crude Oil (WTI) hit in April 2026?",
          marketQuestion: "Will WTI Crude Oil (WTI) hit (HIGH) $100 in April?",
          outcomeLabel: "Yes",
          side: "yes",
          expiry: "2026-04-30T00:00:00Z",
          settlementText: "Resolves yes if any 1-minute candle high is equal to or above 100 during April 2026.",
          price: 0.62,
          displayedSize: 2000
        },
        {
          venue: "manifold",
          externalId: "snapshot-above",
          eventTitle: "Will the WTI Crude Oil Spot Price be above $98 on April 20, 2026?",
          marketQuestion: "Will the WTI Crude Oil Spot Price be above $98 on April 20, 2026?",
          outcomeLabel: "Yes",
          side: "yes",
          expiry: "2026-04-20T23:59:00.000Z",
          settlementText: "Will the WTI Crude Oil Spot Price be above $98 on April 20, 2026?",
          price: 0.53,
          displayedSize: 2900
        }
      ],
      fees: DEFAULT_PREDICTION_FEES,
      sizing: DEFAULT_PREDICTION_SIZING,
      ts: "2026-04-13T17:26:00Z"
    });

    expect(rows).toHaveLength(0);
  });
});
