import { describe, expect, it } from "vitest";
import { buildBillSourceCatalog } from "../src/research/sources.js";
import { buildTrackPolicyFromEnv } from "../src/research/tracks.js";

describe("Bill source catalog", () => {
  it("marks existing prediction venues as active by default", () => {
    const policy = buildTrackPolicyFromEnv({});
    const catalog = buildBillSourceCatalog({}, policy);

    expect(catalog.find((source) => source.id === "polymarket-public-api")).toMatchObject({
      mode: "active",
      automationReady: true,
      requiredForActiveTrack: true
    });
    expect(catalog.find((source) => source.id === "kalshi-public-api")).toMatchObject({
      mode: "active",
      automationReady: true,
      requiredForActiveTrack: true
    });
    expect(catalog.find((source) => source.id === "manifold-public-api")).toMatchObject({
      mode: "active",
      automationReady: true,
      requiredForActiveTrack: true
    });
    expect(catalog.find((source) => source.id === "yahoo-finance-free")).toMatchObject({
      mode: "active",
      automationReady: true,
      tracks: ["futures-core", "crypto-liquid"]
    });
  });

  it("flags keyed sources that are not configured", () => {
    const policy = buildTrackPolicyFromEnv({});
    const catalog = buildBillSourceCatalog({}, policy);

    expect(catalog.find((source) => source.id === "alpha-vantage-market-data")).toMatchObject({
      mode: "missing-config",
      configured: false,
      automationReady: false
    });
    expect(catalog.find((source) => source.id === "finnhub-market-data")).toMatchObject({
      mode: "missing-config",
      configured: false,
      automationReady: false
    });
    expect(catalog.find((source) => source.id === "fred-macro-data")).toMatchObject({
      mode: "missing-config",
      configured: false,
      automationReady: true
    });
  });

  it("recognizes configured keyed and catalog-only sources separately", () => {
    const policy = buildTrackPolicyFromEnv({});
    const catalog = buildBillSourceCatalog({
      RH_POLYGON_API_KEY: "polygon",
      FRED_API_KEY: "fred",
      ALPHA_VANTAGE_API_KEY: "alpha",
      FINNHUB_API_KEY: "finn",
      IEX_CLOUD_API_KEY: "iex",
      SEC_EDGAR_USER_AGENT: "Bill/1.0 bill@example.com"
    }, policy);

    expect(catalog.find((source) => source.id === "polygon-market-data")).toMatchObject({
      configured: true,
      automationReady: true,
      mode: "optional"
    });
    expect(catalog.find((source) => source.id === "fred-macro-data")).toMatchObject({
      configured: true,
      automationReady: true,
      mode: "optional"
    });
    expect(catalog.find((source) => source.id === "alpha-vantage-market-data")).toMatchObject({
      configured: true,
      automationReady: false,
      mode: "catalog-only"
    });
    expect(catalog.find((source) => source.id === "sec-edgar-filings")).toMatchObject({
      configured: true,
      automationReady: false,
      mode: "catalog-only"
    });
  });
});
