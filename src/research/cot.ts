import { mkdirSync } from "node:fs";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

// CFTC COT — disaggregated futures (CL, GC) and TFF financial futures (ES, NQ, ZN, 6E)
// Published Fridays ~3:30 PM ET. Free from cftc.gov as CSV ZIP.
// TFF "Dealer/Intermediary" category = prime brokerage proxy (banks report here).

export interface CotRecord {
  reportDate: string;
  market: string;
  contractCode: string;
  largeSpecLong: number;
  largeSpecShort: number;
  largeSpecNet: number;
  dealerLong: number;
  dealerShort: number;
  dealerNet: number;
  assetMgrLong: number;
  assetMgrShort: number;
  assetMgrNet: number;
  leveragedFundsLong: number;
  leveragedFundsShort: number;
  leveragedFundsNet: number;
  openInterest: number;
}

export interface CotSeries {
  contractCode: string;
  market: string;
  reportType: "tff" | "disaggregated";
  records: CotRecord[];
  latestDate?: string;
  weekOverWeekChange?: {
    largeSpecNet: number;
    dealerNet: number;
    assetMgrNet: number;
    leveragedFundsNet: number;
  };
  zScore52w?: {
    largeSpecNet: number;
    dealerNet: number;
  };
}

export interface CotReport {
  fetchedAt: string;
  year: number;
  tff: CotSeries[];
  disaggregated: CotSeries[];
}

// CFTC contract codes
const TFF_CODES: Record<string, string> = {
  "13874A": "ES",
  "209742": "NQ",
  "043602": "ZN",
  "099741": "6E"
};

const DISAGG_CODES: Record<string, string> = {
  "067651": "CL",
  "088691": "GC"
};

function toInt(value: string | undefined): number {
  if (!value) return 0;
  const parsed = Number.parseInt(value.trim().replace(/,/g, ""), 10);
  return Number.isFinite(parsed) ? parsed : 0;
}

function zScore(values: number[]): number {
  if (values.length < 2) return 0;
  const mean = values.reduce((a, b) => a + b, 0) / values.length;
  const variance = values.reduce((sum, v) => sum + (v - mean) ** 2, 0) / values.length;
  const std = Math.sqrt(variance);
  if (std === 0) return 0;
  return Number((((values.at(-1) ?? 0) - mean) / std).toFixed(2));
}

function parseCsvRow(line: string, header: string[]): (name: string) => string {
  const cols = line.split(",").map((c) => c.trim().replace(/^"|"$/g, ""));
  return (name: string) => cols[header.indexOf(name)] ?? "";
}

function parseTffCsv(csv: string): Map<string, CotRecord[]> {
  const lines = csv.split(/\r?\n/).filter(Boolean);
  if (lines.length < 2) return new Map();
  const header = lines[0]!.split(",").map((h) => h.trim().replace(/^"|"$/g, ""));
  const result = new Map<string, CotRecord[]>();

  for (const line of lines.slice(1)) {
    const idx = parseCsvRow(line, header);
    const contractCode = idx("CFTC_Contract_Market_Code").trim();
    if (!TFF_CODES[contractCode]) continue;
    const reportDate = idx("Report_Date_as_YYYY-MM-DD") || idx("As_of_Date_In_Form_YYMMDD");
    if (!reportDate) continue;

    const record: CotRecord = {
      reportDate,
      market: idx("Market_and_Exchange_Names") || TFF_CODES[contractCode]!,
      contractCode,
      // TFF Dealer/Intermediary = prime brokerage proxy
      dealerLong: toInt(idx("Dealer_Positions_Long_All")),
      dealerShort: toInt(idx("Dealer_Positions_Short_All")),
      dealerNet: toInt(idx("Dealer_Positions_Long_All")) - toInt(idx("Dealer_Positions_Short_All")),
      assetMgrLong: toInt(idx("Asset_Mgr_Positions_Long_All")),
      assetMgrShort: toInt(idx("Asset_Mgr_Positions_Short_All")),
      assetMgrNet: toInt(idx("Asset_Mgr_Positions_Long_All")) - toInt(idx("Asset_Mgr_Positions_Short_All")),
      leveragedFundsLong: toInt(idx("Lev_Money_Positions_Long_All")),
      leveragedFundsShort: toInt(idx("Lev_Money_Positions_Short_All")),
      leveragedFundsNet: toInt(idx("Lev_Money_Positions_Long_All")) - toInt(idx("Lev_Money_Positions_Short_All")),
      // Other Reportables = remaining large spec in TFF
      largeSpecLong: toInt(idx("Other_Rept_Positions_Long_All")),
      largeSpecShort: toInt(idx("Other_Rept_Positions_Short_All")),
      largeSpecNet: toInt(idx("Other_Rept_Positions_Long_All")) - toInt(idx("Other_Rept_Positions_Short_All")),
      openInterest: toInt(idx("Open_Interest_All"))
    };

    const existing = result.get(contractCode) ?? [];
    existing.push(record);
    result.set(contractCode, existing);
  }

  return result;
}

function parseDisaggCsv(csv: string): Map<string, CotRecord[]> {
  // CFTC disaggregated futures uses legacy column names (different from TFF)
  // Swap Dealers = closest to prime brokerage dealer positioning in commodities
  // Managed Money (M_Money) = hedge funds / leveraged funds
  // Prod_Merc = commercial hedgers (producers / commercials)
  const lines = csv.split(/\r?\n/).filter(Boolean);
  if (lines.length < 2) return new Map();
  const header = lines[0]!.split(",").map((h) => h.trim().replace(/^"|"$/g, ""));
  const result = new Map<string, CotRecord[]>();

  for (const line of lines.slice(1)) {
    const idx = parseCsvRow(line, header);
    const contractCode = idx("CFTC_Contract_Market_Code").trim();
    if (!DISAGG_CODES[contractCode]) continue;
    const reportDate = idx("Report_Date_as_YYYY-MM-DD") || idx("As_of_Date_In_Form_YYMMDD");
    if (!reportDate) continue;

    const record: CotRecord = {
      reportDate,
      market: idx("Market_and_Exchange_Names") || DISAGG_CODES[contractCode]!,
      contractCode,
      // Swap Dealers = dealer proxy for commodities (double-underscore short column is a CFTC quirk)
      dealerLong: toInt(idx("Swap_Positions_Long_All")),
      dealerShort: toInt(idx("Swap__Positions_Short_All")),
      dealerNet: toInt(idx("Swap_Positions_Long_All")) - toInt(idx("Swap__Positions_Short_All")),
      // Prod_Merc = commercial hedgers (naturally short in commodities)
      assetMgrLong: toInt(idx("Prod_Merc_Positions_Long_All")),
      assetMgrShort: toInt(idx("Prod_Merc_Positions_Short_All")),
      assetMgrNet: toInt(idx("Prod_Merc_Positions_Long_All")) - toInt(idx("Prod_Merc_Positions_Short_All")),
      // Managed Money = hedge funds / trend followers
      leveragedFundsLong: toInt(idx("M_Money_Positions_Long_All")),
      leveragedFundsShort: toInt(idx("M_Money_Positions_Short_All")),
      leveragedFundsNet: toInt(idx("M_Money_Positions_Long_All")) - toInt(idx("M_Money_Positions_Short_All")),
      largeSpecLong: toInt(idx("Other_Rept_Positions_Long_All")),
      largeSpecShort: toInt(idx("Other_Rept_Positions_Short_All")),
      largeSpecNet: toInt(idx("Other_Rept_Positions_Long_All")) - toInt(idx("Other_Rept_Positions_Short_All")),
      openInterest: toInt(idx("Open_Interest_All"))
    };

    const existing = result.get(contractCode) ?? [];
    existing.push(record);
    result.set(contractCode, existing);
  }

  return result;
}

function buildSeries(
  contractCode: string,
  records: CotRecord[],
  reportType: "tff" | "disaggregated",
  symbolMap: Record<string, string>
): CotSeries {
  const sorted = [...records].sort((a, b) => a.reportDate.localeCompare(b.reportDate));
  const latest = sorted.at(-1);
  const prev = sorted.at(-2);
  const market = symbolMap[contractCode] ?? contractCode;
  const window52 = 52;

  return {
    contractCode,
    market,
    reportType,
    records: sorted,
    latestDate: latest?.reportDate,
    weekOverWeekChange: prev && latest
      ? {
          largeSpecNet: latest.largeSpecNet - prev.largeSpecNet,
          dealerNet: latest.dealerNet - prev.dealerNet,
          assetMgrNet: latest.assetMgrNet - prev.assetMgrNet,
          leveragedFundsNet: latest.leveragedFundsNet - prev.leveragedFundsNet
        }
      : undefined,
    zScore52w: sorted.length >= 4
      ? {
          largeSpecNet: zScore(sorted.slice(-window52).map((r) => r.largeSpecNet)),
          dealerNet: zScore(sorted.slice(-window52).map((r) => r.dealerNet))
        }
      : undefined
  };
}

async function downloadAndUnzip(url: string): Promise<string> {
  const response = await fetch(url, {
    headers: { "user-agent": "rumbling-hedge/0.1 (cot-research)" },
    signal: AbortSignal.timeout(60_000)
  });
  if (!response.ok) {
    throw new Error(`COT download failed for ${url}: ${response.status} ${response.statusText}`);
  }
  if (!response.body) throw new Error(`Response body is null for ${url}`);

  const tmpDir = await mkdtemp(path.join(os.tmpdir(), "rumbling-cot-"));
  const zipPath = path.join(tmpDir, "cot.zip");
  try {
    const { Readable } = await import("node:stream");
    const { createWriteStream } = await import("node:fs");
    const { pipeline } = await import("node:stream/promises");
    const nodeStream = Readable.fromWeb(response.body as Parameters<typeof Readable.fromWeb>[0]);
    await pipeline(nodeStream, createWriteStream(zipPath));

    // CFTC ZIPs are standard ZIP (deflate), not gzip
    const { execFileSync: exec } = await import("node:child_process");
    return exec("unzip", ["-p", zipPath], { encoding: "utf8", maxBuffer: 128 * 1024 * 1024 });
  } finally {
    await rm(tmpDir, { recursive: true, force: true });
  }
}

export async function fetchCotData(args: {
  year?: number;
  baseUrl?: string;
  cacheDir?: string;
  forceRefresh?: boolean;
}): Promise<CotReport> {
  const year = args.year ?? new Date().getFullYear();
  const baseUrl = (args.baseUrl ?? "https://www.cftc.gov").replace(/\/$/, "");
  const cacheDir = args.cacheDir ?? ".rumbling-hedge/research/cot";
  mkdirSync(cacheDir, { recursive: true });

  const tffCachePath = path.join(cacheDir, `tff-${year}.csv`);
  const disaggCachePath = path.join(cacheDir, `disagg-${year}.csv`);

  let tffCsv: string | undefined;
  let disaggCsv: string | undefined;

  if (!args.forceRefresh) {
    try {
      [tffCsv, disaggCsv] = await Promise.all([
        readFile(tffCachePath, "utf8"),
        readFile(disaggCachePath, "utf8")
      ]);
    } catch {
      args.forceRefresh = true;
    }
  }

  if (args.forceRefresh) {
    const tffUrl = `${baseUrl}/files/dea/history/fut_fin_txt_${year}.zip`;
    const disaggUrl = `${baseUrl}/files/dea/history/fut_disagg_txt_${year}.zip`;
    [tffCsv, disaggCsv] = await Promise.all([
      downloadAndUnzip(tffUrl),
      downloadAndUnzip(disaggUrl)
    ]);
    await Promise.all([
      writeFile(tffCachePath, tffCsv),
      writeFile(disaggCachePath, disaggCsv)
    ]);
  }

  const tffByCode = parseTffCsv(tffCsv!);
  const disaggByCode = parseDisaggCsv(disaggCsv!);

  const tff = [...tffByCode.entries()].map(([code, records]) =>
    buildSeries(code, records, "tff", TFF_CODES)
  );
  const disaggregated = [...disaggByCode.entries()].map(([code, records]) =>
    buildSeries(code, records, "disaggregated", DISAGG_CODES)
  );

  return { fetchedAt: new Date().toISOString(), year, tff, disaggregated };
}

export function formatCotSummary(report: CotReport): string {
  const lines: string[] = [`COT Report (year=${report.year}, fetched=${report.fetchedAt.slice(0, 10)})`];

  for (const series of [...report.tff, ...report.disaggregated]) {
    const latest = series.records.at(-1);
    if (!latest) continue;
    const wow = series.weekOverWeekChange;
    const z = series.zScore52w;
    lines.push(
      `  ${series.market} [${series.reportType}] ${series.latestDate ?? "?"}:` +
      ` dealer=${latest.dealerNet}${wow ? ` (${wow.dealerNet >= 0 ? "+" : ""}${wow.dealerNet} WoW)` : ""}` +
      `${z ? ` z52=${z.dealerNet}` : ""}` +
      ` lev=${latest.leveragedFundsNet}${wow ? ` (${wow.leveragedFundsNet >= 0 ? "+" : ""}${wow.leveragedFundsNet} WoW)` : ""}` +
      ` oi=${latest.openInterest}`
    );
  }

  return lines.join("\n");
}

export function defaultCotCacheDir(): string {
  return ".rumbling-hedge/research/cot";
}
