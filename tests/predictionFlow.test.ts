import { describe, it, expect, vi, afterEach } from "vitest";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  computeFlowAcceleration,
  appendFlowSnapshots,
  loadFlowHistory,
  fetchPolymarketActiveMarkets,
  type MarketFlowSnapshot
} from "../src/prediction/flowSignals.js";

function makeSnapshot(
  marketId: string,
  tsOffsetMin: number,
  price: number,
  volumeTotal: number
): MarketFlowSnapshot {
  const base = Date.parse("2026-04-16T00:00:00Z");
  return {
    venue: "polymarket",
    marketId,
    title: "Test market",
    ts: new Date(base + tsOffsetMin * 60_000).toISOString(),
    price,
    volumeTotal,
    volume24h: volumeTotal
  };
}

describe("computeFlowAcceleration", () => {
  it("flags accelerating + directional flow with high score", () => {
    const history: MarketFlowSnapshot[] = [];
    // 12-hour window, 6 buckets of 2h. Place snapshots per bucket.
    // Buckets at 0,120,240,360,480,600 min offsets (from start of window).
    // We want endMs to be the last ts; window starts 12h prior.
    // Spread snapshots at 0, 120, 240, 360, 480, 600, 720 (minutes) price rising, volume exploding at end.
    const prices = [0.3, 0.33, 0.37, 0.42, 0.48, 0.55, 0.62];
    const volumes = [1000, 1100, 1200, 1300, 1400, 1500, 10000];
    for (let i = 0; i < prices.length; i++) {
      history.push(makeSnapshot("m1", i * 120, prices[i], volumes[i]));
    }
    const score = computeFlowAcceleration(history, { windowHours: 12, nBuckets: 6 });
    expect(score).not.toBeNull();
    expect(score!.priceChange).toBeGreaterThan(0.1);
    expect(score!.oneSidednessScore).toBeGreaterThan(0.8);
    expect(score!.compositeScore).toBeGreaterThan(0.6);
    expect(score!.reasons).toContain("consistent-directional-push");
    expect(score!.reasons).toContain("large-absolute-move");
  });

  it("gives low score to flat markets", () => {
    const history: MarketFlowSnapshot[] = [];
    for (let i = 0; i < 7; i++) {
      history.push(makeSnapshot("m2", i * 120, 0.5, 1000 + i));
    }
    const score = computeFlowAcceleration(history, { windowHours: 12, nBuckets: 6 });
    expect(score).not.toBeNull();
    expect(Math.abs(score!.priceChange)).toBeLessThan(0.05);
    expect(score!.compositeScore).toBeLessThan(0.4);
  });

  it("returns null when fewer than 3 data points", () => {
    const history: MarketFlowSnapshot[] = [
      makeSnapshot("m3", 0, 0.5, 100),
      makeSnapshot("m3", 60, 0.55, 150)
    ];
    expect(computeFlowAcceleration(history)).toBeNull();
  });
});

describe("append + load roundtrip", () => {
  let dir: string | null = null;
  afterEach(async () => {
    if (dir) {
      await rm(dir, { recursive: true, force: true });
      dir = null;
    }
  });

  it("appends JSONL and loads grouped by venue:marketId", async () => {
    dir = await mkdtemp(join(tmpdir(), "flow-test-"));
    const path = join(dir, "nested", "history.jsonl");
    const nowIso = new Date().toISOString();
    const rows: MarketFlowSnapshot[] = [
      {
        venue: "polymarket",
        marketId: "x1",
        title: "A",
        ts: nowIso,
        price: 0.5
      },
      {
        venue: "polymarket",
        marketId: "x1",
        title: "A",
        ts: nowIso,
        price: 0.52
      },
      {
        venue: "kalshi",
        marketId: "K1",
        title: "B",
        ts: nowIso,
        price: 0.3
      }
    ];
    await appendFlowSnapshots(path, rows);
    const loaded = await loadFlowHistory(path);
    expect(loaded.get("polymarket:x1")?.length).toBe(2);
    expect(loaded.get("kalshi:K1")?.length).toBe(1);
  });
});

describe("fetchPolymarketActiveMarkets", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("parses gamma-api response into snapshots", async () => {
    const sampleBody = [
      {
        id: 42,
        conditionId: "0xabc",
        slug: "will-it-rain",
        question: "Will it rain tomorrow?",
        outcomes: JSON.stringify(["Yes", "No"]),
        outcomePrices: JSON.stringify(["0.65", "0.35"]),
        lastTradePrice: "0.65",
        volume24hr: "12345.6",
        volume: "98765.4",
        liquidity: "4321"
      }
    ];
    const fakeFetch = vi.fn(async () =>
      new Response(JSON.stringify(sampleBody), {
        status: 200,
        headers: { "content-type": "application/json" }
      })
    );
    vi.stubGlobal("fetch", fakeFetch);
    const rows = await fetchPolymarketActiveMarkets({ limit: 10 });
    expect(fakeFetch).toHaveBeenCalledTimes(1);
    expect(rows).toHaveLength(1);
    expect(rows[0].venue).toBe("polymarket");
    expect(rows[0].marketId).toBe("0xabc");
    expect(rows[0].price).toBeCloseTo(0.65, 5);
    expect(rows[0].volume24h).toBeCloseTo(12345.6, 2);
    expect(rows[0].title).toBe("Will it rain tomorrow?");
    expect(rows[0].outcome).toBe("Yes");
  });
});
