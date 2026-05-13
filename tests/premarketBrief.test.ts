import { mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { buildPremarketBrief } from "../src/research/premarketBrief.js";

function yahooPayload(): unknown {
  const timestamp = Array.from({ length: 70 }, (_, index) => 1_766_000_000 + index * 86_400);
  const close = Array.from({ length: 70 }, (_, index) => 100 + index * 0.1);
  return {
    chart: {
      result: [{
        timestamp,
        indicators: { quote: [{ close }] }
      }],
      error: null
    }
  };
}

describe("buildPremarketBrief", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("distills search, macro, and red-folder context without authorizing trades", async () => {
    const workspace = await mkdtemp(join(tmpdir(), "premarket-brief-"));
    const redFolderPath = resolve(workspace, "red-folder-events.json");
    await writeFile(redFolderPath, JSON.stringify({
      events: [{
        symbol: "NQ",
        ts: "2026-05-13T13:30:00.000Z",
        headline: "CPI red folder release",
        direction: "flat",
        probability: 0.9,
        impact: "high"
      }]
    }));

    vi.stubGlobal("fetch", async (input: RequestInfo | URL) => {
      const url = new URL(String(input));
      if (url.hostname === "query1.finance.yahoo.com") {
        return new Response(JSON.stringify(yahooPayload()), { status: 200 });
      }
      return new Response(JSON.stringify({
        results: [{
          title: "Nasdaq futures watch Fed yields and Nvidia premarket",
          url: "https://example.com/nq",
          content: "VIX and Treasury yields are key for Nasdaq mega-cap AI stocks before the open.",
          engine: "test"
        }, {
          title: "Polymarket election and crypto odds move",
          url: "https://example.com/pm",
          content: "Prediction market odds moved around crypto and election catalysts.",
          engine: "test"
        }]
      }), { status: 200 });
    });

    const report = await buildPremarketBrief({
      outputPath: resolve(workspace, "premarket.json"),
      markdownPath: resolve(workspace, "premarket.md"),
      macroOutputPath: resolve(workspace, "macro.json"),
      macroCsvPath: resolve(workspace, "macro.csv"),
      queries: ["NQ futures premarket", "Polymarket today"],
      maxResults: 2,
      timeoutMs: 500,
      now: () => "2026-05-13T12:00:00.000Z",
      env: {
        BILL_RED_FOLDER_EVENTS_PATH: redFolderPath,
        BILL_PREMARKET_OPENROUTER_ENABLED: "false"
      } as NodeJS.ProcessEnv
    });

    expect(report.command).toBe("premarket-brief");
    expect(report.deterministicRead.tradePermission).toBe("advisory-only");
    expect(report.deterministicRead.themes).toContain("rates-policy");
    expect(report.deterministicRead.themes).toContain("nasdaq-megacap");
    expect(report.deterministicRead.riskFlags).toContain("red-folder-events-present");
    expect(report.deterministicRead.predictionMarketFocus).toContain("prediction-market-catalysts");
    expect(report.redFolders.upcomingHighImpact[0]?.headline).toBe("CPI red folder release");
    expect(report.advisory.provider).toBe("none");

    const persisted = JSON.parse(await readFile(resolve(workspace, "premarket.json"), "utf8")) as typeof report;
    expect(persisted.search.queries).toHaveLength(2);
    expect(await readFile(resolve(workspace, "premarket.md"), "utf8")).toContain("Bill/Hedge Premarket Brief");
  });
});
