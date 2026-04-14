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
  activeTracks: BillMarketTrackId[];
  executionTracks: BillMarketTrackId[];
  researchTracks: BillMarketTrackId[];
  tracks: BillMarketTrack[];
  futuresSymbols: string[];
  optionsUnderlyings: string[];
  cryptoSymbols: string[];
  macroSeries: string[];
}

const DEFAULT_ACTIVE_TRACK: BillMarketTrackId = "prediction";
const DEFAULT_ACTIVE_TRACKS: BillMarketTrackId[] = ["prediction", "futures-core"];
const DEFAULT_EXECUTION_TRACKS: BillMarketTrackId[] = ["prediction", "futures-core"];
const DEFAULT_RESEARCH_ONLY_TRACKS: BillMarketTrackId[] = ["options-us", "crypto-liquid", "macro-rates"];
const DEFAULT_DISABLED_TRACKS: BillMarketTrackId[] = [];

const TRACK_PURPOSES: Record<BillMarketTrackId, { purpose: string; cadence: string; notes: string[] }> = {
  prediction: {
    purpose: "Equal-first execution track for cross-venue prediction-market collection, review, and paper promotion.",
    cadence: "5m",
    notes: [
      "Keep this as an active execution wedge with bounded paper routing and review.",
      "Do not widen permissions just because the venue scan is temporarily dry."
    ]
  },
  "futures-core": {
    purpose: "Equal-first futures execution track with demo-lane testing plus broad regime context.",
    cadence: "30m-1d",
    notes: [
      "Keep Topstep demo lanes active and account-aware even while the adapter stays read-only.",
      "Use this for both execution discipline and broader futures context, not context alone."
    ]
  },
  "options-us": {
    purpose: "Research-only US options surface and chain context for later vol/dispersion execution work.",
    cadence: "30m",
    notes: ["Keep collecting and ranking evidence, but do not promote to execution until its own venue path is ready."]
  },
  "crypto-liquid": {
    purpose: "Research-only liquid crypto market context for continuous collection and training.",
    cadence: "30m",
    notes: [
      "Keep this inside the domain and collect bars by default.",
      "Do not promote to execution until there is a venue-specific paper path and risk model."
    ]
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
  const executionTracks = new Set<BillMarketTrackId>([
    ...DEFAULT_EXECUTION_TRACKS,
    ...parseCsv<BillMarketTrackId>(env.BILL_EXECUTION_TRACKS)
  ]);
  for (const disabled of parseCsv<BillMarketTrackId>(env.BILL_DISABLED_TRACKS)) {
    activeTracks.delete(disabled);
    researchOnlyTracks.delete(disabled);
    executionTracks.delete(disabled);
  }
  for (const disabled of DEFAULT_DISABLED_TRACKS) {
    if (!activeTracks.has(disabled)) {
      researchOnlyTracks.delete(disabled);
    }
    executionTracks.delete(disabled);
  }

  const ids: BillMarketTrackId[] = ["prediction", "futures-core", "options-us", "crypto-liquid", "macro-rates"];
  const resolvedTracks = ids.map((id) => ({
    id,
    mode: resolveTrackMode(id, activeTracks, researchOnlyTracks),
    purpose: TRACK_PURPOSES[id].purpose,
    cadence: TRACK_PURPOSES[id].cadence,
    notes: TRACK_PURPOSES[id].notes
  }));

  return {
    activeTrack,
    activeTracks: resolvedTracks.filter((track) => track.mode === "active").map((track) => track.id),
    executionTracks: [...executionTracks].filter((id) => resolvedTracks.find((track) => track.id === id)?.mode === "active"),
    researchTracks: resolvedTracks.filter((track) => track.mode !== "disabled").map((track) => track.id),
    tracks: resolvedTracks,
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
