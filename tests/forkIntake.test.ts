import { mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { runForkIntake } from "../src/research/forkIntake.js";

function jsonResponse(value: unknown): Response {
  return new Response(JSON.stringify(value), {
    status: 200,
    headers: { "content-type": "application/json" }
  });
}

describe("runForkIntake", () => {
  it("distills fork manifest entries into compact integration cards without cloning repos", async () => {
    const dir = await mkdtemp(join(tmpdir(), "fork-intake-"));
    const manifestPath = join(dir, "manifest.json");
    const outputDir = join(dir, "forks");
    await writeFile(manifestPath, JSON.stringify({
      forked: [
        {
          upstream: "TauricResearch/TradingAgents",
          fork: "Rumblingb/TradingAgents",
          url: "https://github.com/Rumblingb/TradingAgents",
          lane: "financial multi-agent research",
          use: "Extract risk, analyst, and trader role separation."
        }
      ]
    }));

    const fetchImpl = (async (url: string | URL | Request) => {
      const value = String(url);
      if (value.includes("/contents/README.md")) {
        return jsonResponse({
          type: "file",
          path: "README.md",
          sha: "abc",
          html_url: "https://github.com/Rumblingb/TradingAgents/blob/main/README.md",
          download_url: "https://raw.test/README.md"
        });
      }
      if (value === "https://raw.test/README.md") {
        return new Response("Multi agent analyst researcher risk trader graph with paper trading and backtest controls.", { status: 200 });
      }
      return new Response("not found", { status: 404 });
    }) as typeof fetch;

    const report = await runForkIntake({
      manifestPath,
      outputDir,
      fetchImpl,
      now: () => "2026-04-30T00:00:00.000Z"
    });

    expect(report.written).toBe(1);
    expect(report.failed).toBe(0);
    const card = JSON.parse(await readFile(join(outputDir, "rumblingb-tradingagents.json"), "utf8")) as {
      fork: string;
      sourceFiles: Array<{ path: string }>;
      extractedSignals: string[];
      guardrails: string[];
    };
    expect(card.fork).toBe("Rumblingb/TradingAgents");
    expect(card.sourceFiles[0]?.path).toBe("README.md");
    expect(card.extractedSignals).toContain("agent role separation");
    expect(card.extractedSignals).toContain("backtest or paper/live separation");
    expect(card.guardrails.some((line) => line.includes("do not wire external code"))).toBe(true);
  });
});

