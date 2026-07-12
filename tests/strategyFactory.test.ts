import { mkdtemp, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { isSameCsvInputForOosGuard, runStrategyFactory } from "../src/engine/strategyFactory.js";

describe("runStrategyFactory", () => {
  it("rejects identical training and OOS CSV paths before producing research evidence", async () => {
    await expect(runStrategyFactory({
      csvPath: "data/free/NQ-15m-60d.csv",
      oosCsvPath: "data/free/NQ-15m-60d.csv",
      outputPath: ".rumbling-hedge/state/test-strategy-factory-should-not-write.json",
      env: {
        BILL_ENABLE_FUTURES_DEMO_EXECUTION: "false",
        RH_LIVE_EXECUTION_ENABLED: "false",
      } as NodeJS.ProcessEnv,
    })).rejects.toThrow(/DATA LEAKAGE GUARD/);
  });

  it("treats symlinked CSV aliases as the same input", async () => {
    const dir = await mkdtemp(join(tmpdir(), "strategy-factory-oos-guard-"));
    const csvPath = join(dir, "train.csv");
    const aliasPath = join(dir, "alias.csv");
    await writeFile(csvPath, "ts,symbol,open,high,low,close,volume\n", "utf8");
    await symlink(csvPath, aliasPath);

    expect(isSameCsvInputForOosGuard(csvPath, aliasPath)).toBe(true);
  });
});
