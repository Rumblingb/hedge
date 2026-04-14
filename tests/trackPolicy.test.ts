import { describe, expect, it } from "vitest";
import { buildTrackPolicyFromEnv } from "../src/research/tracks.js";

describe("track policy", () => {
  it("keeps prediction and futures as execution tracks while options, crypto, and macro stay in research", () => {
    const policy = buildTrackPolicyFromEnv({});
    expect(policy.activeTrack).toBe("prediction");
    expect(policy.activeTracks).toEqual(["prediction", "futures-core"]);
    expect(policy.executionTracks).toEqual(["prediction", "futures-core"]);
    expect(policy.tracks.find((track) => track.id === "prediction")?.mode).toBe("active");
    expect(policy.tracks.find((track) => track.id === "futures-core")?.mode).toBe("active");
    expect(policy.tracks.find((track) => track.id === "options-us")?.mode).toBe("research-only");
    expect(policy.tracks.find((track) => track.id === "crypto-liquid")?.mode).toBe("research-only");
    expect(policy.tracks.find((track) => track.id === "macro-rates")?.mode).toBe("research-only");
  });
});
