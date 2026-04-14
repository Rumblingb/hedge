import type { BillMarketTrackId, BillTrackPolicy } from "./tracks.js";

export type BillSourceCategory =
  | "discovery"
  | "prediction-market"
  | "market-data"
  | "macro"
  | "symbology"
  | "filings"
  | "universe";

export type BillSourceAccess = "public" | "free-tier" | "keyed" | "local-package";
export type BillSourceMode = "active" | "optional" | "missing-config" | "catalog-only";
export type BillSourcePriority = "primary" | "supplemental";
export type BillSourceCollectionKind =
  | "bars"
  | "crypto"
  | "discovery"
  | "equities"
  | "filings"
  | "fundamentals"
  | "futures"
  | "historical"
  | "macro"
  | "options"
  | "prediction"
  | "realtime"
  | "streaming"
  | "symbology"
  | "universe";

export interface BillSourceStatus {
  id: string;
  name: string;
  category: BillSourceCategory;
  tracks: BillMarketTrackId[];
  collectionKinds: BillSourceCollectionKind[];
  access: BillSourceAccess;
  priority: BillSourcePriority;
  configured: boolean;
  requiredForActiveTrack: boolean;
  automationReady: boolean;
  mode: BillSourceMode;
  env: string[];
  optionalEnv: string[];
  reference: string;
  collectionCommand: string | null;
  trainingUse: string;
  reason: string;
}

interface BillSourceDefinition {
  id: string;
  name: string;
  category: BillSourceCategory;
  tracks: BillMarketTrackId[];
  collectionKinds: BillSourceCollectionKind[];
  access: BillSourceAccess;
  priority: BillSourcePriority;
  automationReady: boolean;
  env?: string[];
  optionalEnv?: string[];
  reference: string;
  collectionCommand?: string | null;
  trainingUse: string;
  configured?: (env: NodeJS.ProcessEnv) => boolean;
  reason: (configured: boolean) => string;
}

function activeTracks(policy: BillTrackPolicy): Set<BillMarketTrackId> {
  return new Set(policy.tracks.filter((track) => track.mode === "active").map((track) => track.id));
}

function hasAllEnv(env: NodeJS.ProcessEnv, keys: string[]): boolean {
  return keys.every((key) => Boolean(env[key]));
}

function resolveMode(args: {
  configured: boolean;
  requiredForActiveTrack: boolean;
  automationReady: boolean;
}): BillSourceMode {
  if (!args.configured) {
    return "missing-config";
  }

  if (!args.automationReady) {
    return "catalog-only";
  }

  if (args.requiredForActiveTrack) {
    return "active";
  }

  return "optional";
}

function buildSourceStatus(args: {
  definition: BillSourceDefinition;
  env: NodeJS.ProcessEnv;
  active: Set<BillMarketTrackId>;
}): BillSourceStatus {
  const { definition, env, active } = args;
  const requiredEnv = definition.env ?? [];
  const optionalEnv = definition.optionalEnv ?? [];
  const configured = definition.configured
    ? definition.configured(env)
    : hasAllEnv(env, requiredEnv);
  const requiredForActiveTrack = definition.priority === "primary"
    && definition.tracks.some((track) => active.has(track));

  return {
    id: definition.id,
    name: definition.name,
    category: definition.category,
    tracks: definition.tracks,
    collectionKinds: definition.collectionKinds,
    access: definition.access,
    priority: definition.priority,
    configured,
    requiredForActiveTrack,
    automationReady: definition.automationReady,
    mode: resolveMode({
      configured,
      requiredForActiveTrack,
      automationReady: definition.automationReady
    }),
    env: requiredEnv,
    optionalEnv,
    reference: definition.reference,
    collectionCommand: definition.collectionCommand ?? null,
    trainingUse: definition.trainingUse,
    reason: definition.reason(configured)
  };
}

export function buildBillSourceCatalog(env: NodeJS.ProcessEnv, policy: BillTrackPolicy): BillSourceStatus[] {
  const active = activeTracks(policy);
  const definitions: BillSourceDefinition[] = [
    {
      id: "polymarket-public-api",
      name: "Polymarket Public API",
      category: "prediction-market",
      tracks: ["prediction"],
      collectionKinds: ["prediction", "realtime", "historical"],
      access: "public",
      priority: "primary",
      automationReady: true,
      reference: "Bill native collector + public Polymarket market endpoints",
      collectionCommand: "npm run bill:prediction-collect -- polymarket",
      trainingUse: "Core live probability surface and cross-venue dislocation features.",
      reason: () => "Prediction lane already uses Polymarket snapshots for autonomous venue comparison."
    },
    {
      id: "kalshi-public-api",
      name: "Kalshi Public API",
      category: "prediction-market",
      tracks: ["prediction"],
      collectionKinds: ["prediction", "realtime", "historical", "streaming"],
      access: "public",
      priority: "primary",
      automationReady: true,
      reference: "Bill native collector + public Kalshi market endpoints",
      collectionCommand: "npm run bill:prediction-collect -- kalshi",
      trainingUse: "Primary second venue for cross-venue edge restoration and fillability-aware pricing.",
      reason: () => "Kalshi is a first-class prediction venue in Bill's current cashflow wedge."
    },
    {
      id: "manifold-public-api",
      name: "Manifold Public API",
      category: "prediction-market",
      tracks: ["prediction"],
      collectionKinds: ["prediction", "realtime", "historical"],
      access: "public",
      priority: "primary",
      automationReady: true,
      reference: "Bill native collector + public Manifold market endpoints",
      collectionCommand: "npm run bill:prediction-collect -- manifold",
      trainingUse: "Cheap public benchmark venue for event probabilities, candidate generation, and sanity checks.",
      reason: () => "Manifold is already collected as a free comparison venue."
    },
    {
      id: "pmxt-unified-prediction-feed",
      name: "PMXT Unified Prediction Feed",
      category: "prediction-market",
      tracks: ["prediction"],
      collectionKinds: ["prediction", "realtime", "historical", "streaming"],
      access: "local-package",
      priority: "supplemental",
      automationReady: false,
      reference: "GitHub qoery-com/pmxt",
      trainingUse: "Normalize Polymarket and Kalshi into one schema when Bill needs a stronger shared training corpus.",
      reason: () => "Cataloged from the founder-supplied research, but not wired into Bill's collectors yet."
    },
    {
      id: "pykalshi-sdk",
      name: "pykalshi SDK",
      category: "prediction-market",
      tracks: ["prediction"],
      collectionKinds: ["prediction", "realtime", "historical", "streaming"],
      access: "local-package",
      priority: "supplemental",
      automationReady: false,
      reference: "Python client pykalshi",
      trainingUse: "Useful if Bill later needs richer websocket capture or authenticated Kalshi workflows outside the native collector.",
      reason: () => "Cataloged Python SDK for future deeper Kalshi data collection; not part of the current Node runtime."
    },
    {
      id: "polymarket-sdk",
      name: "Polymarket SDK",
      category: "prediction-market",
      tracks: ["prediction"],
      collectionKinds: ["prediction", "realtime", "historical"],
      access: "local-package",
      priority: "supplemental",
      automationReady: false,
      reference: "GitHub Polymarket/polymarket-sdk",
      trainingUse: "Useful for future wallet-aware or on-chain enriched Polymarket collection paths.",
      reason: () => "Cataloged SDK for later deeper venue instrumentation; current Bill collectors stay on public endpoints."
    },
    {
      id: "public-apis-finance-index",
      name: "Public APIs Finance Index",
      category: "discovery",
      tracks: ["prediction", "futures-core", "options-us", "crypto-liquid", "macro-rates"],
      collectionKinds: ["discovery"],
      access: "public",
      priority: "supplemental",
      automationReady: false,
      reference: "GitHub public-apis/public-apis Finance section",
      trainingUse: "Discovery index for new free-tier vendors when Bill needs to widen training inputs without ad hoc searching.",
      reason: () => "Acts as a maintained discovery surface, not as a direct collection endpoint."
    },
    {
      id: "finance-database-universe",
      name: "FinanceDatabase Universe",
      category: "universe",
      tracks: ["futures-core", "options-us", "crypto-liquid", "macro-rates"],
      collectionKinds: ["universe", "equities", "crypto", "futures"],
      access: "local-package",
      priority: "supplemental",
      automationReady: false,
      reference: "GitHub JerBouma/FinanceDatabase",
      trainingUse: "Generate large ticker universes for downstream bar, fundamentals, and options collection.",
      reason: () => "Cataloged universe builder for later bulk symbol expansion; not yet wired into the Node collector path."
    },
    {
      id: "yahoo-finance-free",
      name: "Yahoo Finance Free Bars",
      category: "market-data",
      tracks: ["futures-core"],
      collectionKinds: ["bars", "historical", "realtime", "futures"],
      access: "public",
      priority: "primary",
      automationReady: true,
      reference: "Bill freeSources yahoo adapter",
      collectionCommand: "npm run bill:research-collect",
      trainingUse: "Cheap futures context bars for regime labeling, market-state features, and daily retraining inputs.",
      reason: () => "Bill already uses Yahoo as the zero-key default for public futures data."
    },
    {
      id: "stooq-daily-bars",
      name: "Stooq Daily Bars",
      category: "market-data",
      tracks: ["futures-core"],
      collectionKinds: ["bars", "historical", "futures"],
      access: "public",
      priority: "primary",
      automationReady: true,
      reference: "Bill freeSources stooq adapter",
      collectionCommand: "npm run bill:research-collect",
      trainingUse: "Daily fallback for futures context when Yahoo coverage or freshness is thin.",
      reason: () => "Bill already falls back to Stooq for free daily futures history."
    },
    {
      id: "yfinance-python-client",
      name: "yfinance Python Client",
      category: "market-data",
      tracks: ["futures-core", "options-us"],
      collectionKinds: ["bars", "historical", "options", "futures"],
      access: "local-package",
      priority: "supplemental",
      automationReady: false,
      reference: "GitHub ranaroussi/yfinance",
      trainingUse: "Convenient bulk historical and options-chain pull path when Bill needs cheap Python-side experimentation.",
      reason: () => "Cataloged because the founder requested it specifically, but not wired into the native Node collectors."
    },
    {
      id: "polygon-market-data",
      name: "Polygon Market Data",
      category: "market-data",
      tracks: ["options-us", "crypto-liquid"],
      collectionKinds: ["bars", "historical", "options", "equities", "crypto", "futures"],
      access: "free-tier",
      priority: "primary",
      automationReady: true,
      env: ["RH_POLYGON_API_KEY"],
      optionalEnv: ["RH_POLYGON_BASE_URL"],
      reference: "Bill polygon bars/options collectors",
      collectionCommand: "npm run bill:research-collect",
      trainingUse: "Primary keyed path for options surfaces, better bars, and future multi-asset training upgrades.",
      reason: (configured) => configured
        ? "Polygon is configured and ready for Bill's keyed market-data collection."
        : "Configure RH_POLYGON_API_KEY to unlock Bill's native Polygon-backed options and keyed bar collection."
    },
    {
      id: "alpha-vantage-market-data",
      name: "Alpha Vantage",
      category: "market-data",
      tracks: ["futures-core", "options-us", "crypto-liquid", "macro-rates"],
      collectionKinds: ["historical", "realtime", "equities", "crypto", "macro", "fundamentals"],
      access: "free-tier",
      priority: "supplemental",
      automationReady: false,
      env: ["ALPHA_VANTAGE_API_KEY"],
      reference: "Alpha Vantage free-tier API",
      trainingUse: "Fallback keyed source for technical indicators, equities, forex, crypto, and macro-style feature enrichment.",
      reason: (configured) => configured
        ? "Alpha Vantage credentials are present, but Bill does not have a native collector for it yet."
        : "Configure ALPHA_VANTAGE_API_KEY if you want Bill to have another free-tier fallback data vendor."
    },
    {
      id: "finnhub-market-data",
      name: "Finnhub",
      category: "market-data",
      tracks: ["futures-core", "options-us", "crypto-liquid", "macro-rates"],
      collectionKinds: ["historical", "realtime", "streaming", "equities", "crypto", "fundamentals"],
      access: "free-tier",
      priority: "supplemental",
      automationReady: false,
      env: ["FINNHUB_API_KEY"],
      reference: "Finnhub free-tier API",
      trainingUse: "Realtime/websocket-friendly alternative for equities, crypto, and corporate feature inputs.",
      reason: (configured) => configured
        ? "Finnhub credentials are present, but Bill does not have a native collector for it yet."
        : "Configure FINNHUB_API_KEY to add a websocket-capable free-tier vendor to Bill's source catalog."
    },
    {
      id: "iex-cloud-equities",
      name: "IEX Cloud",
      category: "market-data",
      tracks: ["options-us"],
      collectionKinds: ["historical", "realtime", "equities", "fundamentals"],
      access: "free-tier",
      priority: "supplemental",
      automationReady: false,
      env: ["IEX_CLOUD_API_KEY"],
      reference: "IEX Cloud equities API",
      trainingUse: "Additional US equities and fundamentals surface for later event and factor features.",
      reason: (configured) => configured
        ? "IEX Cloud credentials are present, but Bill does not have a native collector for it yet."
        : "Configure IEX_CLOUD_API_KEY if you want Bill to track IEX as another US-equities training surface."
    },
    {
      id: "databento-market-data",
      name: "Databento",
      category: "market-data",
      tracks: ["futures-core", "options-us"],
      collectionKinds: ["historical", "realtime", "streaming", "futures", "options"],
      access: "keyed",
      priority: "supplemental",
      automationReady: false,
      env: ["DATABENTO_API_KEY"],
      reference: "Databento API",
      trainingUse: "Deeper institutional-grade futures/options history when Bill graduates beyond cheap public feeds.",
      reason: (configured) => configured
        ? "Databento is configured, but the deeper futures/options collector is not wired yet."
        : "Configure DATABENTO_API_KEY to make deeper futures/options history available to Bill later."
    },
    {
      id: "alpaca-market-data-and-paper",
      name: "Alpaca Market Data and Paper Trading",
      category: "market-data",
      tracks: ["options-us", "crypto-liquid"],
      collectionKinds: ["historical", "realtime", "equities", "crypto", "options"],
      access: "keyed",
      priority: "supplemental",
      automationReady: false,
      env: ["ALPACA_API_KEY", "ALPACA_SECRET_KEY"],
      reference: "Alpaca market-data and paper APIs",
      trainingUse: "Future paper/data bridge for equities, crypto, and options once Bill widens beyond the prediction wedge.",
      reason: (configured) => configured
        ? "Alpaca credentials are present, but Bill does not have a native Alpaca collector yet."
        : "Configure ALPACA_API_KEY and ALPACA_SECRET_KEY if you want Alpaca available for future paper/data work."
    },
    {
      id: "fred-macro-data",
      name: "FRED Macro Data",
      category: "macro",
      tracks: ["macro-rates"],
      collectionKinds: ["macro", "historical"],
      access: "free-tier",
      priority: "primary",
      automationReady: true,
      env: ["FRED_API_KEY"],
      optionalEnv: ["FRED_BASE_URL"],
      reference: "Bill native FRED macro collector",
      collectionCommand: "npm run bill:research-collect",
      trainingUse: "Macro and rates regime labels that can condition prediction and futures features.",
      reason: (configured) => configured
        ? "FRED is configured and Bill can already collect macro/rates context."
        : "Configure FRED_API_KEY to unlock Bill's macro/rates context collector."
    },
    {
      id: "openfigi-symbology",
      name: "OpenFIGI",
      category: "symbology",
      tracks: ["futures-core", "options-us", "macro-rates"],
      collectionKinds: ["symbology", "equities", "futures", "options"],
      access: "free-tier",
      priority: "supplemental",
      automationReady: false,
      optionalEnv: ["OPENFIGI_API_KEY"],
      reference: "OpenFIGI mapping API",
      trainingUse: "Normalize symbol identities across vendors before training cross-source models.",
      reason: () => "OpenFIGI is cataloged for symbol normalization; add OPENFIGI_API_KEY later if free-tier throughput becomes a limit."
    },
    {
      id: "sec-edgar-filings",
      name: "SEC EDGAR",
      category: "filings",
      tracks: ["options-us", "macro-rates"],
      collectionKinds: ["filings", "historical", "fundamentals"],
      access: "public",
      priority: "supplemental",
      automationReady: false,
      env: ["SEC_EDGAR_USER_AGENT"],
      reference: "SEC EDGAR APIs and filing feeds",
      trainingUse: "Corporate-event and filing-derived features for later US-equities and options model inputs.",
      reason: (configured) => configured
        ? "SEC EDGAR is ready for polite scripted access once a collector is added."
        : "Set SEC_EDGAR_USER_AGENT before wiring SEC EDGAR collection so Bill presents a valid contact header."
    }
  ];

  const modeOrder: Record<BillSourceMode, number> = {
    active: 0,
    "missing-config": 1,
    optional: 2,
    "catalog-only": 3
  };

  return definitions
    .map((definition) => buildSourceStatus({ definition, env, active }))
    .sort((a, b) => {
      const modeDelta = modeOrder[a.mode] - modeOrder[b.mode];
      if (modeDelta !== 0) return modeDelta;
      const requiredDelta = Number(b.requiredForActiveTrack) - Number(a.requiredForActiveTrack);
      if (requiredDelta !== 0) return requiredDelta;
      return a.name.localeCompare(b.name);
    });
}
