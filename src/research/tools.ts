import type { BillMarketTrackId, BillTrackPolicy } from "./tracks.js";

export interface BillToolStatus {
  id: string;
  name: string;
  tracks: BillMarketTrackId[];
  configured: boolean;
  requiredForActiveTrack: boolean;
  mode: "active" | "optional" | "missing-config";
  reason: string;
}

function activeTracks(policy: BillTrackPolicy): Set<BillMarketTrackId> {
  return new Set(policy.tracks.filter((track) => track.mode === "active").map((track) => track.id));
}

export function buildBillToolRegistry(env: NodeJS.ProcessEnv, policy: BillTrackPolicy): BillToolStatus[] {
  const active = activeTracks(policy);
  const polygonConfigured = Boolean(env.RH_POLYGON_API_KEY);
  const databentoConfigured = Boolean(env.DATABENTO_API_KEY);
  const alpacaConfigured = Boolean(env.ALPACA_API_KEY && env.ALPACA_SECRET_KEY);
  const fredConfigured = Boolean(env.FRED_API_KEY);

  const tools: BillToolStatus[] = [
    {
      id: "kalshi-public-api",
      name: "Kalshi API",
      tracks: ["prediction"],
      configured: true,
      requiredForActiveTrack: active.has("prediction"),
      mode: "active",
      reason: "Prediction lane uses public venue snapshots today."
    },
    {
      id: "manifold-public-api",
      name: "Manifold API",
      tracks: ["prediction"],
      configured: true,
      requiredForActiveTrack: active.has("prediction"),
      mode: "active",
      reason: "Prediction lane uses public manifold snapshots today."
    },
    {
      id: "polygon-market-data",
      name: "Polygon Market Data",
      tracks: ["futures-core", "options-us", "crypto-liquid"],
      configured: polygonConfigured,
      requiredForActiveTrack: active.has("options-us") || active.has("crypto-liquid"),
      mode: polygonConfigured ? "optional" : "missing-config",
      reason: polygonConfigured
        ? "Use Polygon when keyed market data is needed for options or higher-quality bars."
        : "Configure RH_POLYGON_API_KEY to unlock options and better keyed market data."
    },
    {
      id: "databento-market-data",
      name: "Databento",
      tracks: ["futures-core", "options-us"],
      configured: databentoConfigured,
      requiredForActiveTrack: false,
      mode: databentoConfigured ? "optional" : "missing-config",
      reason: databentoConfigured
        ? "Databento is available for deeper futures/options data when you decide to wire it."
        : "Configure DATABENTO_API_KEY for deeper futures/options market data."
    },
    {
      id: "alpaca-market-data-and-paper",
      name: "Alpaca Market Data and Paper Trading",
      tracks: ["options-us", "crypto-liquid"],
      configured: alpacaConfigured,
      requiredForActiveTrack: false,
      mode: alpacaConfigured ? "optional" : "missing-config",
      reason: alpacaConfigured
        ? "Alpaca is available as a paper/data surface for later options or crypto lanes."
        : "Configure ALPACA_API_KEY and ALPACA_SECRET_KEY if you want Alpaca-backed paper/data workflows."
    },
    {
      id: "fred-macro-data",
      name: "FRED Macro Data",
      tracks: ["macro-rates"],
      configured: fredConfigured,
      requiredForActiveTrack: active.has("macro-rates"),
      mode: fredConfigured ? "optional" : "missing-config",
      reason: fredConfigured
        ? "FRED is available for macro/rates series collection."
        : "Configure FRED_API_KEY to unlock macro and rates series collection."
    }
  ];

  return tools;
}
