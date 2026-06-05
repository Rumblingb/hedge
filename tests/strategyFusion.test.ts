import { describe, expect, it } from "vitest";
import {
  allowsProxyOptionsFusion,
  CORRELATION_GROUPS,
  isHmmRegimeFusionEnabled,
  isOptionsZoneStrategy,
  shouldBlockOptionsZoneFusionStrategy
} from "../src/engine/strategyFusion.js";

describe("strategy fusion safety gates", () => {
  it("keeps no-edge strategies out of the active deconfliction groups", () => {
    expect(CORRELATION_GROUPS.breakout).not.toContain("donchian-breakout");
    expect(CORRELATION_GROUPS.momentum).not.toContain("session-momentum");
  });

  it("keeps HMM regime fusion opt-in", () => {
    expect(isHmmRegimeFusionEnabled({} as NodeJS.ProcessEnv)).toBe(false);
    expect(isHmmRegimeFusionEnabled({ BILL_ENABLE_HMM_REGIME_FUSION: "true" } as NodeJS.ProcessEnv)).toBe(true);
  });

  it("blocks proxy options strategies from fusion unless explicitly allowed", () => {
    expect(isOptionsZoneStrategy("gamma-stability")).toBe(true);
    expect(allowsProxyOptionsFusion({} as NodeJS.ProcessEnv)).toBe(false);
    expect(shouldBlockOptionsZoneFusionStrategy("gamma-stability", {} as NodeJS.ProcessEnv)).toBe(true);
    expect(shouldBlockOptionsZoneFusionStrategy(
      "gamma-stability",
      { BILL_ALLOW_PROXY_OPTIONS_FUSION: "true" } as NodeJS.ProcessEnv
    )).toBe(false);
    expect(shouldBlockOptionsZoneFusionStrategy("orb-breakout", {} as NodeJS.ProcessEnv)).toBe(false);
  });
});
