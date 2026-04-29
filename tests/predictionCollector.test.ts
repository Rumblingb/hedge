import { afterEach, describe, expect, it, vi } from "vitest";
import { mkdir, rm, writeFile } from "node:fs/promises";
import { fetchPolymarketLiveSnapshot } from "../src/prediction/adapters/polymarket.js";
import { collectPredictionSnapshots } from "../src/prediction/collector.js";
import * as kalshiAdapter from "../src/prediction/adapters/kalshi.js";
import * as manifoldAdapter from "../src/prediction/adapters/manifold.js";
import * as polymarketAdapter from "../src/prediction/adapters/polymarket.js";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("prediction collector", () => {
  it("normalizes polymarket gamma events into prediction snapshots", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true,
      json: async () => ([
        {
          id: "event-1",
          title: "Will X happen?",
          endDate: "2026-11-03",
          markets: [
            {
              id: "market-1",
              question: "Will X happen?",
              description: "Resolves yes if X happens",
              outcomes: JSON.stringify(["Yes", "No"]),
              outcomePrices: JSON.stringify([0.42, 0.58]),
              liquidity: "1200"
            }
          ]
        }
      ])
    })));

    const rows = await fetchPolymarketLiveSnapshot(5);
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({
      venue: "polymarket",
      externalId: "market-1",
      eventTitle: "Will X happen?",
      outcomeLabel: "Yes",
      price: 0.42,
      displayedSize: 1200
    });
  });

  it("keeps combined collection alive with fallback snapshots when one venue fails", async () => {
    await mkdir(".rumbling-hedge/runtime/prediction", { recursive: true });
    await writeFile(
      ".rumbling-hedge/runtime/prediction/kalshi-live-snapshot.json",
      JSON.stringify([
        {
          venue: "kalshi",
          externalId: "fallback-kalshi",
          eventTitle: "Fallback Kalshi market",
          marketQuestion: "Fallback Kalshi market?",
          outcomeLabel: "Yes",
          side: "yes",
          price: 0.41
        }
      ]),
      "utf8"
    );

    vi.spyOn(polymarketAdapter, "fetchPolymarketLiveSnapshot").mockResolvedValue([
      {
        venue: "polymarket",
        externalId: "pm-1",
        eventTitle: "Polymarket live",
        marketQuestion: "Polymarket live?",
        outcomeLabel: "Yes",
        side: "yes",
        price: 0.49
      }
    ]);
    vi.spyOn(kalshiAdapter, "fetchKalshiLiveSnapshot").mockRejectedValue(new Error("kalshi timeout"));
    vi.spyOn(manifoldAdapter, "fetchManifoldLiveSnapshot").mockResolvedValue([]);

    const result = await collectPredictionSnapshots({
      source: "combined",
      limit: 10,
      env: process.env
    });

    expect(result.markets.map((row) => row.externalId)).toContain("pm-1");
    expect(result.markets.map((row) => row.externalId)).toContain("fallback-kalshi");
    expect(result.diagnostics.find((item) => item.source === "kalshi")?.status).toBe("fallback");

    await rm(".rumbling-hedge/runtime/prediction/kalshi-live-snapshot.json", { force: true });
  });
});
