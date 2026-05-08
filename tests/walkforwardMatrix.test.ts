import { mkdtemp, readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { getConfig } from "../src/config.js";
import { generateSyntheticBars } from "../src/data/synthetic.js";
import { buildWalkforwardMatrixReport } from "../src/engine/walkforwardMatrix.js";
import { NoopNewsGate } from "../src/news/base.js";

describe("walkforward matrix", () => {
  it("compares fixed, anchored, stitched pseudo-live, and varying IS/OOS windows", async () => {
    const dir = await mkdtemp(join(tmpdir(), "walkforward-matrix-"));
    const outputPath = join(dir, "matrix.json");
    const report = await buildWalkforwardMatrixReport({
      bars: generateSyntheticBars({ symbols: ["NQ", "ES"], days: 35, seed: 92 }),
      baseConfig: getConfig(),
      newsGate: new NoopNewsGate(),
      csvPath: "synthetic.csv",
      outputPath,
      maxWindows: 3,
      maxProfiles: 4,
      now: () => "2026-05-07T10:00:00.000Z"
    });

    expect(report.command).toBe("walkforward-matrix");
    expect(report.configs.map((config) => config.configId)).toEqual(expect.arrayContaining([
      "fixed-20d-5d",
      "anchored-20d-5d",
      "fixed-10d-5d",
      "fixed-30d-3d"
    ]));
    expect(report.configs.some((config) => config.mode === "anchored")).toBe(true);
    expect(report.configs.some((config) => config.stitchedOos.wfe >= 0)).toBe(true);
    expect(report.configs[0]?.sigmaStress.oneShockEquityR["6sigma"]).toBeTypeOf("number");
    expect(JSON.parse(await readFile(outputPath, "utf8")).command).toBe("walkforward-matrix");
  }, 60000);
});
