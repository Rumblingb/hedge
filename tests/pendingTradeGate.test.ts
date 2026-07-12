import { mkdtemp, readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import type { StrategySignal } from "../src/domain.js";
import type { RegimeAnalysis } from "../src/engine/strategyFusion.js";
import { evaluatePendingTradeGate, markPendingTradeFired } from "../src/engine/pendingTradeGate.js";

function signal(overrides: Partial<StrategySignal> = {}): StrategySignal {
  return {
    symbol: "MNQ",
    strategyId: "session-momentum",
    side: "long",
    entry: 29000,
    stop: 28950,
    target: 29100,
    rr: 2,
    confidence: 0.72,
    contracts: 1,
    maxHoldMinutes: 30,
    ...overrides
  };
}

function regime(session: RegimeAnalysis["session"]): RegimeAnalysis {
  return {
    regime: "breakout",
    confidence: 0.7,
    volatility: "normal",
    session,
    atrPercentile: 0.5,
    trendStrength: 0.6,
    rangeBound: false,
    nqEsDivergence: false
  };
}

describe("pending trade gate", () => {
  it("waits 15 minutes for NY confirmation before allowing one route", async () => {
    const dir = await mkdtemp(join(tmpdir(), "pending-trade-gate-"));
    const path = join(dir, "state.json");
    const first = new Date("2026-05-19T13:30:00.000Z");
    const signalTs = "2026-05-19T13:30:00.000Z";

    const detected = evaluatePendingTradeGate({
      path,
      now: first,
      signal: signal(),
      regime: regime("ny-open"),
      signalTs,
      atrPoints: 100
    });
    expect(detected.allowed).toBe(false);
    expect(detected.action).toBe("wait");

    const early = evaluatePendingTradeGate({
      path,
      now: new Date("2026-05-19T13:44:00.000Z"),
      signal: signal({ entry: 29010 }),
      regime: regime("ny-open"),
      signalTs,
      atrPoints: 100
    });
    expect(early.allowed).toBe(false);
    expect(early.action).toBe("wait");

    const armed = evaluatePendingTradeGate({
      path,
      now: new Date("2026-05-19T13:45:00.000Z"),
      signal: signal({ entry: 29012 }),
      regime: regime("ny-open"),
      signalTs,
      atrPoints: 100
    });
    expect(armed.allowed).toBe(true);
    expect(armed.action).toBe("fire");

    markPendingTradeFired({
      path,
      fingerprint: armed.fingerprint,
      now: new Date("2026-05-19T13:45:01.000Z")
    });

    const duplicate = evaluatePendingTradeGate({
      path,
      now: new Date("2026-05-19T13:46:00.000Z"),
      signal: signal({ entry: 29012 }),
      regime: regime("ny-open"),
      signalTs,
      atrPoints: 100
    });
    expect(duplicate.allowed).toBe(false);
    expect(duplicate.reason).toMatch(/already fired/i);
  });

  it("waits 30 minutes for Asia/London and blocks chased entries", async () => {
    const dir = await mkdtemp(join(tmpdir(), "pending-trade-gate-"));
    const path = join(dir, "state.json");
    const signalTs = "2026-05-19T08:00:00.000Z";

    const detected = evaluatePendingTradeGate({
      path,
      now: new Date("2026-05-19T08:00:00.000Z"),
      signal: signal(),
      regime: regime("london"),
      signalTs,
      atrPoints: 100
    });
    expect(detected.record.earliestFireAt).toBe("2026-05-19T08:30:00.000Z");

    const chased = evaluatePendingTradeGate({
      path,
      now: new Date("2026-05-19T08:31:00.000Z"),
      signal: signal({ entry: 29070 }),
      regime: regime("london"),
      signalTs,
      atrPoints: 100
    });
    expect(chased.allowed).toBe(false);
    expect(chased.action).toBe("block");
    expect(chased.reason).toMatch(/too far/i);

    const raw = JSON.parse(await readFile(path, "utf8"));
    expect(raw.records[0].status).toBe("BLOCKED");
  });

  it("blocks when pre-trade bias conflicts with the strategy side", async () => {
    const dir = await mkdtemp(join(tmpdir(), "pending-trade-gate-"));
    const path = join(dir, "state.json");

    const decision = evaluatePendingTradeGate({
      path,
      now: new Date("2026-05-19T13:30:00.000Z"),
      signal: signal({ side: "short" }),
      regime: regime("ny-open"),
      signalTs: "2026-05-19T13:30:00.000Z",
      atrPoints: 100,
      biasDirection: "LONG"
    });

    expect(decision.allowed).toBe(false);
    expect(decision.action).toBe("block");
    expect(decision.reason).toMatch(/conflicts/i);
  });
});
