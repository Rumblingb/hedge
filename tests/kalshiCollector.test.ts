import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchKalshiLiveSnapshot } from "../src/prediction/adapters/kalshi.js";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("kalshi collector", () => {
  it("normalizes kalshi markets into prediction snapshots", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true,
      json: async () => ({
        markets: [
          {
            ticker: "KXCOMBO-IGNORE",
            title: "yes Charlotte,yes Diana Shnaider",
            yes_sub_title: "yes Charlotte,yes Diana Shnaider",
            close_time: "2026-04-28T23:30:00Z",
            last_price_dollars: "0",
            volume_24h_fp: "0",
            rules_primary: "Combo market."
          },
          {
            ticker: "KXWORLDCUP-SPAIN",
            title: "Will Spain win the 2026 FIFA World Cup?",
            yes_sub_title: "Yes",
            close_time: "2026-07-20T00:00:00Z",
            last_price_dollars: "0.36",
            volume_24h_fp: "400",
            rules_primary: "Resolves yes if Spain wins the tournament."
          }
        ]
      })
    })));

    const rows = await fetchKalshiLiveSnapshot(5);
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({
      venue: "kalshi",
      externalId: "KXWORLDCUP-SPAIN",
      eventTitle: "Will Spain win the 2026 FIFA World Cup?",
      outcomeLabel: "Yes",
      price: 0.36,
      displayedSize: 400
    });
  });
});
