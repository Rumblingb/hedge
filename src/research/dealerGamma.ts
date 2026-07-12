import { mkdirSync } from "node:fs";
import { writeFile } from "node:fs/promises";
import path from "node:path";
import type { PolygonOptionSnapshot } from "./options.js";
import {
  fetchAlpacaOptionSnapshots,
  fetchAlpacaUnderlyingPrice,
  fetchPolygonOptionSnapshots,
  fetchYahooOptionSnapshots
} from "./options.js";

// Dealer Gamma Exposure (GEX)
// netGEX = Σ(call_gamma × call_OI - put_gamma × put_OI) × spot × contract_multiplier
// Positive GEX → dealers long gamma → they sell rallies / buy dips → dampen moves
// Negative GEX → dealers short gamma → they buy rallies / sell dips → amplify moves

export interface GexByStrike {
  strike: number;
  callGex: number;
  putGex: number;
  netGex: number;
}

export interface DealerGammaReport {
  underlying: string;
  source: "polygon" | "alpaca" | "yahoo";
  computedAt: string;
  underlyingPrice?: number;
  selectedExpirationDate?: string;
  contractMultiplier: number;
  totalCallGex: number;
  totalPutGex: number;
  netGex: number;
  netGexMillions: number;
  regime: "long-gamma" | "short-gamma" | "neutral";
  zeroGammaFlip?: number;
  gexByStrike: GexByStrike[];
  contractsWithGamma: number;
  contractsTotal: number;
}

// Standard equity index multiplier: 100 shares per contract
// For futures ETF proxies (SPY, QQQ), use 100
const DEFAULT_MULTIPLIER = 100;

function toNumber(value: unknown): number | undefined {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  return undefined;
}

function standardNormalPdf(x: number): number {
  return Math.exp(-0.5 * x * x) / Math.sqrt(2 * Math.PI);
}

// Compute Black-Scholes gamma when the data source doesn't provide it directly (e.g., Yahoo)
function computeBsGamma(args: {
  spot: number;
  strike: number;
  impliedVolatility: number;
  timeToExpiryYears: number;
  riskFreeRate?: number;
}): number | undefined {
  const { spot, strike, impliedVolatility: sigma, timeToExpiryYears: T, riskFreeRate = 0.05 } = args;
  if (spot <= 0 || strike <= 0 || sigma <= 0 || T <= 0) return undefined;
  const d1 = (Math.log(spot / strike) + (riskFreeRate + 0.5 * sigma * sigma) * T) / (sigma * Math.sqrt(T));
  return standardNormalPdf(d1) / (spot * sigma * Math.sqrt(T));
}

export function computeGex(args: {
  snapshots: PolygonOptionSnapshot[];
  underlyingPrice: number;
  contractMultiplier?: number;
  expirationDate?: string;
}): Pick<DealerGammaReport, "totalCallGex" | "totalPutGex" | "netGex" | "netGexMillions" | "gexByStrike" | "zeroGammaFlip" | "contractsWithGamma" | "contractsTotal" | "regime"> {
  const multiplier = args.contractMultiplier ?? DEFAULT_MULTIPLIER;
  const snapshots = args.expirationDate
    ? args.snapshots.filter((s) => s.expirationDate === args.expirationDate)
    : args.snapshots;

  const strikeMap = new Map<number, GexByStrike>();
  let contractsWithGamma = 0;

  for (const snap of snapshots) {
    let gamma = toNumber(snap.gamma);
    const oi = toNumber(snap.openInterest);
    const strike = toNumber(snap.strike);
    if (oi === undefined || strike === undefined) continue;

    // When gamma is missing (Yahoo source), approximate via Black-Scholes
    if (gamma === undefined) {
      const iv = toNumber(snap.impliedVolatility);
      const expDate = snap.expirationDate;
      if (iv !== undefined && iv > 0 && expDate) {
        const T = Math.max(0, (Date.parse(`${expDate}T23:59:59Z`) - Date.now()) / (365.25 * 24 * 3600 * 1000));
        gamma = computeBsGamma({ spot: args.underlyingPrice, strike, impliedVolatility: iv, timeToExpiryYears: T });
      }
    }
    if (gamma === undefined) continue;

    contractsWithGamma++;
    const gexContrib = gamma * oi * args.underlyingPrice * multiplier;

    const existing = strikeMap.get(strike) ?? { strike, callGex: 0, putGex: 0, netGex: 0 };
    if (snap.contractType === "call") {
      existing.callGex += gexContrib;
    } else if (snap.contractType === "put") {
      existing.putGex += gexContrib;
    }
    existing.netGex = existing.callGex - existing.putGex;
    strikeMap.set(strike, existing);
  }

  const gexByStrike = [...strikeMap.values()].sort((a, b) => a.strike - b.strike);
  const totalCallGex = gexByStrike.reduce((sum, row) => sum + row.callGex, 0);
  const totalPutGex = gexByStrike.reduce((sum, row) => sum + row.putGex, 0);
  const netGex = totalCallGex - totalPutGex;
  const netGexMillions = Number((netGex / 1_000_000).toFixed(2));

  // Zero-gamma flip: strike where cumulative GEX crosses zero
  let zeroGammaFlip: number | undefined;
  let cumulative = 0;
  let prevStrike: number | undefined;
  for (const row of gexByStrike) {
    const prevCumulative = cumulative;
    cumulative += row.netGex;
    if (prevStrike !== undefined && prevCumulative * cumulative < 0) {
      // Linear interpolation between prevStrike and row.strike
      const fraction = Math.abs(prevCumulative) / (Math.abs(prevCumulative) + Math.abs(cumulative));
      zeroGammaFlip = Number((prevStrike + fraction * (row.strike - prevStrike)).toFixed(2));
      break;
    }
    prevStrike = row.strike;
  }

  const regime: DealerGammaReport["regime"] =
    netGex > 0 ? "long-gamma" : netGex < 0 ? "short-gamma" : "neutral";

  return {
    totalCallGex: Number(totalCallGex.toFixed(0)),
    totalPutGex: Number(totalPutGex.toFixed(0)),
    netGex: Number(netGex.toFixed(0)),
    netGexMillions,
    regime,
    zeroGammaFlip,
    gexByStrike,
    contractsWithGamma,
    contractsTotal: snapshots.length
  };
}

export async function fetchDealerGamma(args: {
  underlying: string;
  apiKey?: string;
  secretKey?: string;
  polygonApiKey?: string;
  source?: "polygon" | "alpaca" | "yahoo";
  expirationDate?: string;
  contractMultiplier?: number;
}): Promise<DealerGammaReport> {
  const sourceCandidates: Array<"polygon" | "alpaca" | "yahoo"> = args.source
    ? [args.source]
    : [
        ...(args.polygonApiKey ? ["polygon" as const] : []),
        ...(args.apiKey && args.secretKey ? ["alpaca" as const] : []),
        "yahoo" as const
      ];
  const errors: string[] = [];

  for (const source of sourceCandidates) {
    try {
      const report = await fetchDealerGammaFromSource({
        ...args,
        source
      });
      if (!args.source && report.contractsWithGamma === 0 && source !== sourceCandidates.at(-1)) {
        errors.push(`${source}: options data had ${report.contractsWithGamma}/${report.contractsTotal} contracts with usable gamma`);
        continue;
      }
      return report;
    } catch (error) {
      errors.push(`${source}: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  throw new Error(`dealer gamma fetch failed for ${args.underlying}: ${errors.join(" | ")}`);
}

async function fetchDealerGammaFromSource(args: {
  underlying: string;
  apiKey?: string;
  secretKey?: string;
  polygonApiKey?: string;
  source: "polygon" | "alpaca" | "yahoo";
  expirationDate?: string;
  contractMultiplier?: number;
}): Promise<DealerGammaReport> {
  const source = args.source;
  let snapshots: PolygonOptionSnapshot[] = [];
  let underlyingPrice: number | undefined;
  let selectedExpirationDate: string | undefined;

  if (source === "polygon" && args.polygonApiKey) {
    snapshots = await fetchPolygonOptionSnapshots({
      underlying: args.underlying,
      apiKey: args.polygonApiKey,
      limit: 250
    });
  } else if (source === "alpaca" && args.apiKey && args.secretKey) {
    let pageToken: string | undefined;
    let page = 0;
    while (page < 5) {
      const result = await fetchAlpacaOptionSnapshots({
        underlying: args.underlying,
        apiKey: args.apiKey,
        secretKey: args.secretKey,
        feed: "indicative",
        limit: 1000,
        pageToken
      });
      snapshots.push(...result.snapshots);
      if (!result.nextPageToken) break;
      pageToken = result.nextPageToken;
      page++;
    }
    underlyingPrice = await fetchAlpacaUnderlyingPrice({
      underlying: args.underlying,
      apiKey: args.apiKey,
      secretKey: args.secretKey
    });
  } else {
    const result = await fetchYahooOptionSnapshots({
      underlying: args.underlying,
      expirationDate: args.expirationDate
    });
    snapshots = result.snapshots;
    underlyingPrice = result.underlyingPrice;
    selectedExpirationDate = result.selectedExpirationDate;
  }

  if (!underlyingPrice && snapshots.length > 0) {
    // Estimate from ATM strike
    const strikes = snapshots.map((s) => s.strike).filter((s): s is number => s !== undefined);
    if (strikes.length > 0) {
      underlyingPrice = strikes.reduce((a, b) => a + b, 0) / strikes.length;
    }
  }

  if (!underlyingPrice) {
    throw new Error(`Could not determine underlying price for ${args.underlying}`);
  }

  const gex = computeGex({
    snapshots,
    underlyingPrice,
    contractMultiplier: args.contractMultiplier ?? DEFAULT_MULTIPLIER,
    expirationDate: args.expirationDate ?? selectedExpirationDate
  });

  return {
    underlying: args.underlying,
    source,
    computedAt: new Date().toISOString(),
    underlyingPrice,
    selectedExpirationDate: args.expirationDate ?? selectedExpirationDate,
    contractMultiplier: args.contractMultiplier ?? DEFAULT_MULTIPLIER,
    ...gex
  };
}

export async function fetchAndSaveDealerGamma(args: {
  underlyings: string[];
  apiKey?: string;
  secretKey?: string;
  polygonApiKey?: string;
  source?: "polygon" | "alpaca" | "yahoo";
  outDir?: string;
}): Promise<DealerGammaReport[]> {
  const outDir = args.outDir ?? ".rumbling-hedge/research/dealer-gamma";
  mkdirSync(outDir, { recursive: true });

  const reports = await Promise.allSettled(
    args.underlyings.map((underlying) =>
      fetchDealerGamma({
        underlying,
        apiKey: args.apiKey,
        secretKey: args.secretKey,
        polygonApiKey: args.polygonApiKey,
        source: args.source
      })
    )
  );

  const successful: DealerGammaReport[] = [];
  for (const result of reports) {
    if (result.status === "fulfilled") {
      successful.push(result.value);
      const outPath = path.join(outDir, `${result.value.underlying}-gex.json`);
      await writeFile(outPath, JSON.stringify(result.value, null, 2));
    }
  }

  return successful;
}

export function formatGexSummary(reports: DealerGammaReport[]): string {
  const lines: string[] = [];
  for (const r of reports) {
    lines.push(
      `${r.underlying} GEX (${r.computedAt.slice(0, 16)} UTC):` +
      ` net=${r.netGexMillions}M [${r.regime}]` +
      `${r.zeroGammaFlip !== undefined ? ` flip@${r.zeroGammaFlip}` : ""}` +
      ` spot=${r.underlyingPrice ?? "?"}` +
      ` contracts=${r.contractsWithGamma}/${r.contractsTotal} with gamma`
    );
  }
  return lines.join("\n");
}

export function defaultGexOutDir(): string {
  return ".rumbling-hedge/research/dealer-gamma";
}
