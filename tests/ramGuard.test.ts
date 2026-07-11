import { access, mkdtemp } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { describe, expect, it } from "vitest";
import { isMemoryPressureActive, runRamGuard } from "../src/engine/ramGuard.js";

describe("ram guard", () => {
  it("writes and clears the memory pressure flag deterministically", async () => {
    const root = await mkdtemp(join(tmpdir(), "ram-guard-"));
    const flagPath = join(root, "memory-pressure.flag");

    const wrote = await runRamGuard({
      flagPath,
      pressureLevel: "warn",
      now: () => "2026-05-06T12:00:00.000Z"
    });
    expect(wrote.action).toBe("wrote-flag");
    expect(wrote.flagActive).toBe(true);
    expect(await isMemoryPressureActive(flagPath)).toBe(true);

    const cleared = await runRamGuard({
      flagPath,
      pressureLevel: "normal",
      now: () => "2026-05-06T12:01:00.000Z"
    });
    expect(cleared.action).toBe("cleared-flag");
    expect(cleared.flagActive).toBe(false);
    await expect(access(flagPath)).rejects.toThrow();
  });
});
