import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { readKillSwitch, writeKillSwitch } from "../src/engine/killSwitch.js";

describe("kill switch", () => {
  it("defaults off and can be toggled on and off", async () => {
    const tempDir = await mkdtemp(join(tmpdir(), "rumbling-hedge-kill-"));
    const killSwitchPath = join(tempDir, "kill-switch.json");

    try {
      const initial = await readKillSwitch(killSwitchPath);
      expect(initial.active).toBe(false);

      const active = await writeKillSwitch({
        path: killSwitchPath,
        active: true,
        reason: "manual operator stop"
      });
      expect(active.active).toBe(true);
      expect(active.reason).toContain("manual operator stop");
      expect(active.activatedAt).toBeTruthy();

      const disabled = await writeKillSwitch({
        path: killSwitchPath,
        active: false,
        reason: "resume after review"
      });
      expect(disabled.active).toBe(false);
      expect(disabled.activatedAt).toBeNull();
    } finally {
      await rm(tempDir, { recursive: true, force: true });
    }
  });
});
