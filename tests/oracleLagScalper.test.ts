import { describe, it, expect } from "vitest";
import {
  evaluateTick,
  type ScalperTick,
  DEFAULT_SCALPER_CONFIG,
  estimateProb,
} from "../src/prediction/oracleLagScalper.js";

/** Tick inside the entry window: 100s elapsed → 200s remaining (inside 240→10) */
function makeTick(overrides: Partial<ScalperTick>): ScalperTick {
  return {
    btcOpen: 74000,
    btcNow: 74000,
    upPrice: 0.50,
    downPrice: 0.50,
    secondsElapsed: 100,
    secondsTotal: 300,
    ts: Date.now(),
    ...overrides,
  };
}

describe("oracleLagScalper", () => {
  describe("estimateProb", () => {
    it("returns ~0.5 when delta is zero", () => {
      const p = estimateProb(0, 180, 0.12);
      expect(p).toBeCloseTo(0.50, 1);
    });

    it("returns high prob for large delta", () => {
      const p = estimateProb(0.5, 180, 0.12);
      expect(p).toBeGreaterThan(0.80);
    });
  });

  describe("evaluateTick gates", () => {
    it("rejects zero delta", () => {
      const signal = evaluateTick(makeTick({ btcNow: 74000 }));
      expect(signal).not.toBeNull();
      expect(signal!.skipReason).toBe("delta_too_small");
    });

    it("rejects when outside entry window", () => {
      expect(evaluateTick(makeTick({ btcNow: 74370, secondsElapsed: 5 }))
        ?.skipReason).toBe("outside_window");
      expect(evaluateTick(makeTick({ btcNow: 74370, secondsElapsed: 295 }))
        ?.skipReason).toBe("outside_window");
    });

    it("rejects when price too high", () => {
      const signal = evaluateTick(
        makeTick({ btcNow: 74400, upPrice: 0.95 })
      );
      expect(signal?.skipReason).toBe("price_out_of_range");
    });

    it("rejects when edge too thin (market mostly efficient)", () => {
      // 0.08% move with market at 72¢ → prob ~76% (below 80%), gets rejected
      const signal = evaluateTick(
        makeTick({ btcNow: 74059, upPrice: 0.72 }) // 0.08% move
      );
      expect(signal?.skipReason).toBe("prob_below_min");
    });

    it("rejects delta below 0.06%", () => {
      // 74030 / 74000 = +0.04% < 0.06%
      const signal = evaluateTick(makeTick({ btcNow: 74030 }));
      expect(signal?.skipReason).toBe("delta_too_small");
    });
  });

  describe("valid entries", () => {
    it("enters UP on bullish move with PM price lag", () => {
      // BTC +0.54% (BTC at 74400, open 74000), PM UP at 0.68 (lagging)
      const signal = evaluateTick(
        makeTick({
          btcNow: 74400,
          upPrice: 0.68,
          downPrice: 0.35,
          secondsElapsed: 60,
        })
      );
      expect(signal).not.toBeNull();
      if (signal) {
        expect(signal.skipReason).toBeUndefined();
        expect(signal.side).toBe("UP");
        expect(signal.prob).toBeGreaterThan(0.80);
        expect(signal.edge).toBeGreaterThanOrEqual(DEFAULT_SCALPER_CONFIG.minEdge);
        expect(signal.recommendedBet).toBeGreaterThanOrEqual(5);
        expect(signal.recommendedBet).toBeLessThanOrEqual(25);
      }
    });

    it("enters DOWN on bearish move with PM price lag", () => {
      // BTC -0.27% (BTC at 73800, open 74000), PM DOWN at 0.66 (lagging)
      const signal = evaluateTick(
        makeTick({
          btcNow: 73800,
          upPrice: 0.37,
          downPrice: 0.66,
          secondsElapsed: 60,
        })
      );
      expect(signal).not.toBeNull();
      if (signal) {
        expect(signal.skipReason).toBeUndefined();
        expect(signal.side).toBe("DOWN");
        expect(signal.prob).toBeGreaterThan(0.80);
        expect(signal.edge).toBeGreaterThanOrEqual(DEFAULT_SCALPER_CONFIG.minEdge);
      }
    });
  });
});
