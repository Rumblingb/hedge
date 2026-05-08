import { mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { describe, expect, it } from "vitest";
import { buildPmFuturesBridgeReport } from "../src/prediction/futuresBridge.js";

async function writeJson(path: string, value: unknown): Promise<void> {
  await mkdir(dirname(path), { recursive: true });
  await writeFile(path, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

describe("PM futures bridge", () => {
  it("turns prediction-market copy context into futures indicators without execution authority", async () => {
    const root = await mkdtemp(join(tmpdir(), "pm-futures-bridge-"));
    const reviewPath = join(root, "prediction-review.latest.json");
    const copyPath = join(root, "prediction-copy-demo.latest.json");
    const outputPath = join(root, "pm-futures-bridge.latest.json");

    await writeJson(reviewPath, {
      ts: "2026-05-08T00:00:00.000Z",
      counts: { watch: 0, reject: 0, "paper-trade": 0 },
      readyForPaper: false
    });
    await writeJson(copyPath, {
      ts: "2026-05-08T00:00:00.000Z",
      ideas: [{
        id: "btc-up",
        slug: "bitcoin-above-150k-in-2026",
        title: "Will Bitcoin be above $150k in 2026?",
        outcome: "Yes",
        action: "shadow-buy",
        consensusPct: 0.8,
        supporterCount: 5,
        totalCurrentValue: 20_000,
        exhaust: {
          domain: "crypto",
          inferredStrategy: "crowded-consensus"
        }
      }]
    });

    const report = await buildPmFuturesBridgeReport({
      predictionReviewPath: reviewPath,
      predictionCopyDemoPath: copyPath,
      outputPath,
      now: () => "2026-05-08T00:01:00.000Z"
    });

    expect(report.status).toBe("active-context");
    expect(report.executionAllowed).toBe(false);
    expect(report.authority).toBe("indicator-only");
    expect(report.indicators.some((indicator) => indicator.symbol === "NQ" && indicator.bias === "risk-on")).toBe(true);
    expect(report.blockers).toContain("indicator-only-no-execution-authority");

    const persisted = JSON.parse(await readFile(outputPath, "utf8")) as typeof report;
    expect(persisted.indicators.length).toBeGreaterThan(0);
  });
});
