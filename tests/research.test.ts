import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { getConfig } from "../src/config.js";
import { loadBarsFromCsv } from "../src/data/csv.js";
import { generateSyntheticBars } from "../src/data/synthetic.js";
import { runWalkforwardResearch } from "../src/engine/walkforward.js";
import { NoopNewsGate } from "../src/news/base.js";
import { collectResearchUniverse } from "../src/research/profiles.js";
import { getMarketCategory, getMarketSpec, normalizeFuturesSymbol } from "../src/utils/markets.js";

describe("runWalkforwardResearch", () => {
  it("returns ranked research profiles with a winner", async () => {
    const config = getConfig();
    const result = await runWalkforwardResearch({
      baseConfig: config,
      bars: generateSyntheticBars({ symbols: collectResearchUniverse(config), days: 5, seed: 17 }),
      newsGate: new NoopNewsGate()
    });

    expect(result.profiles.length).toBeGreaterThan(1);
    expect(result.winner).not.toBeNull();
    expect(result.profiles[0]?.profileId).toBe(result.winner?.profileId);
  }, 10000);

  it("builds a wider synthetic universe from the research profiles", () => {
    const config = getConfig();
    const universe = collectResearchUniverse(config);

    expect(universe).toEqual(expect.arrayContaining(["ES", "NQ", "CL", "GC", "6E", "ZN", "MES", "MNQ", "RTY", "M2K", "YM", "MYM"]));
  });
});

describe("real data ingest", () => {
  it("normalizes contract symbols and reads headered minute-bar CSVs", async () => {
    const tempDir = await mkdtemp(join(tmpdir(), "rumbling-hedge-"));
    const csvPath = join(tempDir, "bars.csv");

    try {
      await writeFile(
        csvPath,
        [
          "timestamp,root,open,high,low,close,volume",
          "2026-04-01T13:30:00.000Z,NQM26,18250,18253,18248,18252,1320",
          "2026-04-01T13:31:00.000Z,ESM26,5200,5202,5198,5201,900"
        ].join("\n"),
        "utf8"
      );

      const bars = await loadBarsFromCsv(csvPath);

      expect(bars).toEqual([
        {
          ts: "2026-04-01T13:30:00.000Z",
          symbol: "NQ",
          open: 18250,
          high: 18253,
          low: 18248,
          close: 18252,
          volume: 1320
        },
        {
          ts: "2026-04-01T13:31:00.000Z",
          symbol: "ES",
          open: 5200,
          high: 5202,
          low: 5198,
          close: 5201,
          volume: 900
        }
      ]);
      expect(normalizeFuturesSymbol("NQM26")).toBe("NQ");
      expect(getMarketCategory("ESM26")).toBe("index");
      expect(getMarketSpec("MNQM26")).toMatchObject({
        symbol: "MNQ",
        category: "index",
        contractStyle: "micro"
      });
    } finally {
      await rm(tempDir, { recursive: true, force: true });
    }
  });
});
