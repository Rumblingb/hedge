import { describe, expect, it } from "vitest";
import { PayoutLedger } from "../src/risk/payoutLedger.js";

describe("PayoutLedger", () => {
  it("uses current 50K standard path rules without a consistency ratio gate", () => {
    const ledger = new PayoutLedger({ accountTier: 50000, path: "standard" });

    ledger.recordDay("2026-06-01", 800, 1, 1, 0);
    ledger.recordDay("2026-06-02", 150, 1, 1, 0);
    ledger.recordDay("2026-06-03", 150, 1, 1, 0);
    ledger.recordDay("2026-06-04", 150, 1, 1, 0);
    ledger.recordDay("2026-06-05", 150, 1, 1, 0);

    const state = ledger.getState();
    expect(state.qualifyingDays).toBe(5);
    expect(state.bestDayRatioThreshold).toBeNull();
    expect(state.largestDayPct).toBeGreaterThan(0.5);
    expect(state.eligible).toBe(true);
    expect(ledger.checkPreTrade(800, 200).safe).toBe(true);
  });

  it("uses current 50K consistency path rules with three traded days and a 40% largest-day gate", () => {
    const ledger = new PayoutLedger({ accountTier: 50000, path: "consistency" });

    ledger.recordDay("2026-06-01", 400, 1, 1, 0);
    ledger.recordDay("2026-06-02", 350, 1, 1, 0);
    ledger.recordDay("2026-06-03", 300, 1, 1, 0);

    expect(ledger.getState().eligible).toBe(true);

    const concentrated = new PayoutLedger({ accountTier: 50000, path: "consistency" });
    concentrated.recordDay("2026-06-01", 600, 1, 1, 0);
    concentrated.recordDay("2026-06-02", 200, 1, 1, 0);
    concentrated.recordDay("2026-06-03", 200, 1, 1, 0);

    const state = concentrated.getState();
    expect(state.eligible).toBe(false);
    expect(state.ineligibleReason).toContain("Best day");
  });
});

