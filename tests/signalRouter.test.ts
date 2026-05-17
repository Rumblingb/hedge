import { describe, expect, it } from "vitest";
import { validatePreTradeDecision, type OrbSignal } from "../src/live/signalRouter.js";

const signal: OrbSignal = {
  ticker: "MNQ",
  action: "buy",
  quantity: 1,
  entryPrice: 29000,
  stopLoss: 28970,
  takeProfit: 29050
};

function decision(overrides: Record<string, unknown> = {}) {
  return {
    timestamp: "2026-05-17T10:00:00.000Z",
    decision: "TRADE",
    direction: "LONG",
    conviction: "HIGH",
    contracts: 1,
    sl_pts: 30,
    tp1_pts: 50,
    tp2_pts: 100,
    trail_pts: 30,
    account_split: { Topstep: 1 },
    stagger_min: 5,
    warnings: [],
    ...overrides
  } as any;
}

describe("validatePreTradeDecision", () => {
  const now = new Date("2026-05-17T10:05:00.000Z");

  it("fails closed when the pre-trade artifact is missing", () => {
    expect(validatePreTradeDecision(null, signal, now)).toEqual({
      ok: false,
      reason: "missing pre-trade decision"
    });
  });

  it("requires an explicit TRADE decision", () => {
    expect(validatePreTradeDecision(decision({ decision: "REDUCED" }), signal, now).ok).toBe(false);
    expect(validatePreTradeDecision(decision({ decision: "NO_TRADE" }), signal, now).ok).toBe(false);
  });

  it("blocks stale, forced, and direction-mismatched decisions", () => {
    expect(validatePreTradeDecision(decision({ timestamp: "2026-05-17T09:40:00.000Z" }), signal, now).reason).toContain("stale");
    expect(validatePreTradeDecision(decision({ warnings: ["STALE DATA - use --force to override"] }), signal, now).reason).toContain("blocking warning");
    expect(validatePreTradeDecision(decision({ direction: "SHORT" }), signal, now).reason).toContain("conflicts");
  });

  it("allows a fresh matched TRADE decision inside the approved size", () => {
    expect(validatePreTradeDecision(decision(), signal, now)).toEqual({ ok: true });
  });
});
