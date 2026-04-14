export type BillMarketTrackId =
  | "prediction"
  | "futures-core"
  | "options-us"
  | "crypto-liquid"
  | "macro-rates";

export type BillMarketTrackMode = "active" | "research-only" | "disabled";

export interface BillMarketTrack {
  id: BillMarketTrackId;
  mode: BillMarketTrackMode;
  purpose: string;
  cadence: string;
  notes: string[];
}

export interface BillTrackPolicy {
  activeTrack: BillMarketTrackId;
  tracks: BillMarketTrack[];
  futuresSymbols: string[];
  optionsUnderlyings: string[];
  cryptoSymbols: string[];
  macroSeries: string[];
}

const DEFAULT_ACTIVE_TRACK: BillMarketTrackId = "prediction";
const DEFAULT_ACTIVE_TRACKS: BillMarketTrackId[] = ["prediction", "futures-core"];
const DEFAULT_RESEARCH_ONLY_TRACKS: BillMarketTrackId[] = ["options-us", "macro-rates"];
const DEFAULT_DISABLED_TRACKS: BillMarketTrackId[] = ["crypto-liquid"];

const TRACK_PURPOSES: Record<BillMarketTrackId, { purpose: string; cadence: string; notes: string[] }> = {
  prediction: {
    purpose: "Primary cashflow wedge. Cross-venue prediction-market collection, review, and promotion.",
    cadence: "5m",
    notes: ["This is the only active autonomous cashflow wedge by default."]
  },
  "futures-core": {
    purpose: "Context track for rates, energy, metals, FX, and index regime awareness.",
    cadence: "30m-1d",
    notes: ["Use as context and later backtest input, not as a second live wedge."]
  },
  "options-us": {
    purpose: "Research-only options surface and chain context for later vol/dispersion work.",
    cadence: "30m",
    notes: ["Stay off until a proper options data provider is configured."]
  },
  "crypto-liquid": {
    purpose: "Research-only liquid crypto context. No autonomous execution by default.",
    cadence: "30m",
    notes: ["Keep disabled until there is a venue-specific paper and risk path."]
  },
  "macro-rates": {
    purpose: "Research-only macro and rates context for higher-level regime labeling.",
    cadence: "1h-1d",
    notes: ["Useful as context, not as an autonomous trading wedge."]
  }
};

function parseCsv<T extends string>(value: string | undefined): T[] {
  return (value ?? "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean) as T[];
}

function resolveTrackMode(id: BillMarketTrackId, active: Set<BillMarketTrackId>, researchOnly: Set<BillMarketTrackId>): BillMarketTrackMode {
  if (active.has(id)) return "active";
  if (researchOnly.has(id)) return "research-only";
  return "disabled";
}

export function buildTrackPolicyFromEnv(env: NodeJS.ProcessEnv = process.env): BillTrackPolicy {
  const activeTrack = (env.BILL_ACTIVE_TRACK as BillMarketTrackId | undefined) ?? DEFAULT_ACTIVE_TRACK;
  const activeTracks = new Set<BillMarketTrackId>([
    ...DEFAULT_ACTIVE_TRACKS,
    ...parseCsv<BillMarketTrackId>(env.BILL_ACTIVE_TRACKS)
  ]);
  activeTracks.add(activeTrack);

  const researchOnlyTracks = new Set<BillMarketTrackId>([
    ...DEFAULT_RESEARCH_ONLY_TRACKS,
    ...parseCsv<BillMarketTrackId>(env.BILL_RESEARCH_ONLY_TRACKS)
  ]);
  for (const disabled of parseCsv<BillMarketTrackId>(env.BILL_DISABLED_TRACKS)) {
    activeTracks.delete(disabled);
    researchOnlyTracks.delete(disabled);
  }
  for (const disabled of DEFAULT_DISABLED_TRACKS) {
    if (!activeTracks.has(disabled)) {
      researchOnlyTracks.delete(disabled);
    }
  }

  const ids: BillMarketTrackId[] = ["prediction", "futures-core", "options-us", "crypto-liquid", "macro-rates"];
  return {
    activeTrack,
    tracks: ids.map((id) => ({
      id,
      mode: resolveTrackMode(id, activeTracks, researchOnlyTracks),
      purpose: TRACK_PURPOSES[id].purpose,
      cadence: TRACK_PURPOSES[id].cadence,
      notes: TRACK_PURPOSES[id].notes
    })),
    futuresSymbols: parseCsv(env.BILL_FUTURES_SYMBOLS).length > 0
      ? parseCsv(env.BILL_FUTURES_SYMBOLS)
      : ["NQ", "ES", "CL", "GC", "6E", "ZN"],
    optionsUnderlyings: parseCsv(env.BILL_OPTIONS_UNDERLYINGS).length > 0
      ? parseCsv(env.BILL_OPTIONS_UNDERLYINGS)
      : ["SPY", "QQQ", "IWM", "TLT", "GLD"],
    cryptoSymbols: parseCsv(env.BILL_CRYPTO_SYMBOLS).length > 0
      ? parseCsv(env.BILL_CRYPTO_SYMBOLS)
      : ["BTCUSD", "ETHUSD"],
    macroSeries: parseCsv(env.BILL_MACRO_SERIES).length > 0
      ? parseCsv(env.BILL_MACRO_SERIES)
      : ["DFF", "DGS10", "VIXCLS"]
  };
}

export function trackEnabled(policy: BillTrackPolicy, id: BillMarketTrackId): boolean {
  return policy.tracks.find((track) => track.id === id)?.mode !== "disabled";
}
