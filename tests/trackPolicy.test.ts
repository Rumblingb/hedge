import { describe, expect, it } from "vitest";
import { buildTrackPolicyFromEnv } from "../src/research/tracks.js";

describe("track policy", () => {
  it("keeps prediction active, futures active, and options research-only by default", () => {
    const policy = buildTrackPolicyFromEnv({});
    expect(policy.activeTrack).toBe("prediction");
    expect(policy.tracks.find((track) => track.id === "prediction")?.mode).toBe("active");
    expect(policy.tracks.find((track) => track.id === "futures-core")?.mode).toBe("active");
    expect(policy.tracks.find((track) => track.id === "options-us")?.mode).toBe("research-only");
    expect(policy.tracks.find((track) => track.id === "crypto-liquid")?.mode).toBe("disabled");
  });
});
