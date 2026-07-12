import { mkdir, readFile, writeFile, mkdtemp } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { runForkSynthesis } from "../src/research/forkSynthesis.js";

async function writeCard(dir: string, file: string, card: Record<string, unknown>): Promise<void> {
  await writeFile(join(dir, file), `${JSON.stringify({
    generatedAt: "2026-05-02T00:00:00.000Z",
    url: "https://github.com/example/repo",
    sourceFiles: [{ path: "README.md", excerpt: "paper dry-run risk research" }],
    extractedSignals: ["backtest or paper/live separation", "risk and execution controls"],
    integrationNotes: [],
    guardrails: ["Reference only; do not wire external code into live trading directly."],
    ...card
  }, null, 2)}\n`, "utf8");
}

describe("runForkSynthesis", () => {
  it("turns fork cards into adoptable Bill/Hedge directives without vendoring repos", async () => {
    const dir = await mkdtemp(join(tmpdir(), "fork-synthesis-"));
    const inputDir = join(dir, "forks");
    await mkdir(inputDir, { recursive: true });
    await writeCard(inputDir, "tradingagents.json", {
      id: "tradingagents",
      upstream: "TauricResearch/TradingAgents",
      fork: "Rumblingb/TradingAgents",
      lane: "financial multi-agent research",
      intendedUse: "Role-separated market research and risk review."
    });
    await writeCard(inputDir, "qlib.json", {
      id: "qlib",
      upstream: "microsoft/qlib",
      fork: "Rumblingb/qlib",
      lane: "quant research platform",
      intendedUse: "Experiment tracking and OOS evaluation."
    });
    await writeCard(inputDir, "hummingbot.json", {
      id: "hummingbot",
      upstream: "hummingbot/hummingbot",
      fork: "Rumblingb/hummingbot",
      lane: "market making and connectors",
      intendedUse: "Connector and market-making reference."
    });

    const outputPath = join(dir, "synthesis.json");
    const markdownPath = join(dir, "synthesis.md");
    const report = await runForkSynthesis({
      inputDir,
      outputPath,
      markdownPath,
      now: () => "2026-05-02T00:00:00.000Z"
    });

    expect(report.cardsRead).toBe(3);
    expect(report.adoptedPatterns.map((pattern) => pattern.id)).toContain("role-separated-investment-committee");
    expect(report.adoptedPatterns.map((pattern) => pattern.id)).toContain("reproducible-experiment-ledger");
    expect(report.candidates.find((candidate) => candidate.fork === "Rumblingb/hummingbot")?.status).toBe("watch-only");
    expect(report.strategyLabDirectives.map((directive) => directive.strategyId)).toContain("session-momentum");
    expect(report.blockers).toEqual([]);

    const persisted = JSON.parse(await readFile(outputPath, "utf8")) as typeof report;
    expect(persisted.adoptedCount).toBe(report.adoptedCount);
    const markdown = await readFile(markdownPath, "utf8");
    expect(markdown).toContain("Bill/Hedge Fork Synthesis");
    expect(markdown).toContain("Role-separated investment committee");
  });
});
