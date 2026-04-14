import { describe, expect, it } from "vitest";
import { scanPredictionCandidates } from "../src/prediction/matcher.js";
import { buildPredictionReport } from "../src/prediction/report.js";
import { DEFAULT_PREDICTION_FEES } from "../src/prediction/fees.js";

const markets = [
  { venue: "polymarket", externalId: "1", eventTitle: "Election Winner", marketQuestion: "Will X win?", outcomeLabel: "Yes", side: "yes" as const, expiry: "2026-11-03", settlementText: "If X wins", price: 0.41, displayedSize: 500 },
  { venue: "kalshi", externalId: "A", eventTitle: "Will X win?", marketQuestion: "Will X win?", outcomeLabel: "Yes", side: "yes" as const, expiry: "2026-11-03", settlementText: "If X wins", price: 0.36, displayedSize: 400 },
  { venue: "kalshi", externalId: "B", eventTitle: "Will Y win?", marketQuestion: "Will Y win?", outcomeLabel: "Yes", side: "yes" as const, expiry: "2026-11-03", settlementText: "If Y wins", price: 0.33, displayedSize: 50 }
];

describe("prediction scanner", () => {
  it("classifies exact overlap candidates and rejects weak ones", () => {
    const rows = scanPredictionCandidates({ markets, fees: DEFAULT_PREDICTION_FEES, ts: "2026-04-13T17:26:00Z" });
    expect(rows.some((row) => row.verdict === "paper-trade")).toBe(true);
    expect(rows.some((row) => row.verdict === "reject")).toBe(true);
    const report = buildPredictionReport(rows);
    expect(report.counts["paper-trade"]).toBe(1);
  });
});
