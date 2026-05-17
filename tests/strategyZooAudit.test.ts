import { mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { buildStrategyZooAudit } from "../src/engine/strategyZooAudit.js";

describe("strategy zoo audit", () => {
  it("keeps strategy inventory separate from execution promotion", async () => {
    const dir = await mkdtemp(join(tmpdir(), "strategy-zoo-"));
    const matrixPath = join(dir, "matrix.json");
    const outputPath = join(dir, "audit.json");
    await writeFile(matrixPath, JSON.stringify({
      lanes: [
        {
          laneId: "donchian-breakout-nq",
          score: 0.7,
          status: "research",
          blockers: ["negative-worst-fold-net-edge"]
        }
      ]
    }), "utf8");

    const report = await buildStrategyZooAudit({
      outputPath,
      propFirmMatrixPath: matrixPath,
      now: () => "2026-05-17T08:00:00.000Z"
    });

    expect(report.command).toBe("strategy-zoo-audit");
    expect(report.rules.join(" ")).toContain("never promotes execution");
    expect(report.items.find((item) => item.strategyId === "donchian-breakout")).toMatchObject({
      phase: "candidate-retest",
      executable: false
    });
    expect(report.items.find((item) => item.strategyId === "orb-breakout")?.phase).toBe("quarantine");
    expect(JSON.parse(await readFile(outputPath, "utf8")).command).toBe("strategy-zoo-audit");
  });
});
