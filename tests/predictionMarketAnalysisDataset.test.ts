import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { describe, expect, it } from "vitest";
import { inspectPredictionMarketAnalysisDataset, renderPredictionMarketAnalysisMarkdown } from "../src/prediction/historicalDataset.js";

async function makeDatasetRoot(): Promise<string> {
  const root = await mkdtemp(join(tmpdir(), "pma-dataset-"));
  for (const relative of [
    "kalshi/markets",
    "kalshi/trades",
    "polymarket/markets",
    "polymarket/trades"
  ]) {
    await mkdir(join(root, relative), { recursive: true });
    await writeFile(join(root, relative, "part-000.parquet"), "fixture", "utf8");
  }
  return root;
}

describe("prediction market analysis dataset readiness", () => {
  it("scans required parquet directories and renders Hermes-readable markdown", async () => {
    const root = await makeDatasetRoot();
    try {
      const report = await inspectPredictionMarketAnalysisDataset({
        env: {},
        dataRoot: root,
        maxDatasetBytes: 1024 * 1024,
        recommendedFreeGiB: 1,
        ts: "2026-04-22T00:00:00.000Z"
      });

      expect(report.totalParquetFiles).toBe(4);
      expect(report.tables.filter((table) => table.required && table.parquetFiles === 1)).toHaveLength(4);
      expect(report.blockers).not.toContain(expect.stringContaining("data root does not exist"));

      const markdown = renderPredictionMarketAnalysisMarkdown(report);
      expect(markdown).toContain("Prediction Market Analysis Dataset");
      expect(markdown).toContain("Hermes should monitor this report");
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  it("keeps the dataset missing when the external root is absent", async () => {
    const report = await inspectPredictionMarketAnalysisDataset({
      env: {},
      dataRoot: join(tmpdir(), "does-not-exist-pma"),
      ts: "2026-04-22T00:00:00.000Z"
    });

    expect(report.status).toBe("missing");
    expect(report.blockers.some((blocker) => blocker.includes("data root does not exist"))).toBe(true);
    expect(report.hermesSummary).toContain("not import-ready");
  });
});
