import { execFile } from "node:child_process";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { promisify } from "node:util";
import { describe, expect, it } from "vitest";

const execFileAsync = promisify(execFile);

function priceChange(localTs: string, bid: number, ask: number) {
  return JSON.stringify({
    localTs,
    eventType: "price_change",
    market: "0xtest",
    priceChanges: [
      {
        asset_id: "asset-1",
        best_bid: bid,
        best_ask: ask
      }
    ]
  });
}

describe("Polymarket CLOB persistence lab", () => {
  it("requires samples to reach the requested horizon instead of using the final stale quote", async () => {
    const root = await mkdtemp(join(tmpdir(), "clob-persistence-"));
    const input = join(root, "market-channel.jsonl");
    const output = join(root, "persistence.json");
    const samples = join(root, "samples.jsonl");
    try {
      await writeFile(input, [
        priceChange("2026-05-30T00:00:00.000Z", 0.49, 0.51),
        priceChange("2026-05-30T00:00:03.000Z", 0.50, 0.52),
        priceChange("2026-05-30T00:00:05.100Z", 0.51, 0.53)
      ].join("\n") + "\n", "utf8");

      await execFileAsync("node", [
        "scripts/polymarket_clob_persistence_lab.mjs",
        "--input", input,
        "--output", output,
        "--samples-output", samples,
        "--windows", "5,10",
        "--min-observations", "2"
      ], { cwd: "/Users/brain/hedge" });

      const report = JSON.parse(await readFile(output, "utf8"));
      const sampleLines = (await readFile(samples, "utf8")).trim().split(/\r?\n/).filter(Boolean);

      expect(report.windows.find((window: any) => window.windowSec === 5)?.samples).toBe(1);
      expect(report.windows.find((window: any) => window.windowSec === 10)?.samples).toBe(0);
      expect(sampleLines).toHaveLength(1);
      expect(JSON.parse(sampleLines[0]).dtSec).toBeGreaterThanOrEqual(5);
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  it("writes a research-only blocked artifact when today's capture file is missing", async () => {
    const root = await mkdtemp(join(tmpdir(), "clob-persistence-missing-"));
    const input = join(root, "missing-market-channel.jsonl");
    const output = join(root, "persistence.json");
    const samples = join(root, "samples.jsonl");
    try {
      await execFileAsync("node", [
        "scripts/polymarket_clob_persistence_lab.mjs",
        "--input", input,
        "--output", output,
        "--samples-output", samples,
        "--windows", "5,15",
        "--min-observations", "2"
      ], { cwd: "/Users/brain/hedge" });

      const report = JSON.parse(await readFile(output, "utf8"));
      const sampleText = await readFile(samples, "utf8");

      expect(report.decision).toBe("missing-capture-file-collect-forward-clob-data");
      expect(report.blocker).toBe("input-jsonl-missing");
      expect(report.researchOnly).toBe(true);
      expect(report.writesOrders).toBe(false);
      expect(report.touchesBroker).toBe(false);
      expect(report.recordsRead).toBe(0);
      expect(report.windows.map((window: any) => window.samples)).toEqual([0, 0]);
      expect(sampleText).toBe("");
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });
});
