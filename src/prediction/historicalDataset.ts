import { mkdir, readdir, stat, statfs, writeFile } from "node:fs/promises";
import { dirname, join, parse, resolve } from "node:path";

export type PredictionMarketAnalysisStatus = "missing" | "blocked" | "ready";

export interface PredictionMarketAnalysisTableStatus {
  key: string;
  path: string;
  required: boolean;
  exists: boolean;
  parquetFiles: number;
  bytes: number;
}

export interface PredictionMarketAnalysisReadiness {
  command: "prediction-market-analysis-status";
  ts: string;
  status: PredictionMarketAnalysisStatus;
  dataRoot: string;
  outputDir: string;
  importScriptPath: string;
  duckdbAvailable: boolean;
  disk: {
    path: string;
    availableBytes: number;
    availableGiB: number;
    recommendedFreeGiB: number;
  } | null;
  limits: {
    maxDatasetBytes: number;
    maxDatasetGiB: number;
    maxFilesPerTable: number;
  };
  tables: PredictionMarketAnalysisTableStatus[];
  totalParquetFiles: number;
  totalBytes: number;
  totalGiB: number;
  blockers: string[];
  warnings: string[];
  nextCommands: string[];
  hermesSummary: string;
}

const GIB = 1024 ** 3;

const TABLES = [
  { key: "kalshi.markets", relativePath: "kalshi/markets", required: true },
  { key: "kalshi.trades", relativePath: "kalshi/trades", required: true },
  { key: "polymarket.markets", relativePath: "polymarket/markets", required: true },
  { key: "polymarket.trades", relativePath: "polymarket/trades", required: true },
  { key: "polymarket.legacy_trades", relativePath: "polymarket/legacy_trades", required: false },
  { key: "polymarket.blocks", relativePath: "polymarket/blocks", required: false }
] as const;

function round(value: number, decimals = 2): number {
  return Number(value.toFixed(decimals));
}

async function directoryExists(path: string): Promise<boolean> {
  try {
    return (await stat(path)).isDirectory();
  } catch {
    return false;
  }
}

async function scanParquetFiles(dir: string): Promise<{ files: number; bytes: number }> {
  let files = 0;
  let bytes = 0;

  async function walk(path: string): Promise<void> {
    let entries;
    try {
      entries = await readdir(path, { withFileTypes: true });
    } catch {
      return;
    }

    for (const entry of entries) {
      const child = join(path, entry.name);
      if (entry.isDirectory()) {
        await walk(child);
        continue;
      }
      if (!entry.isFile() || !entry.name.endsWith(".parquet")) {
        continue;
      }
      files += 1;
      bytes += (await stat(child)).size;
    }
  }

  await walk(dir);
  return { files, bytes };
}

async function hasPythonDuckDb(): Promise<boolean> {
  const { spawn } = await import("node:child_process");
  return new Promise((resolvePromise) => {
    const child = spawn("python3", ["-c", "import duckdb"], {
      stdio: "ignore"
    });
    child.on("error", () => resolvePromise(false));
    child.on("close", (code) => resolvePromise(code === 0));
  });
}

async function diskFor(path: string, recommendedFreeGiB: number): Promise<PredictionMarketAnalysisReadiness["disk"]> {
  let target = resolve(path);
  const root = parse(target).root;
  while (!(await directoryExists(target)) && target !== root) {
    target = dirname(target);
  }
  try {
    const stats = await statfs(target);
    const availableBytes = Number(stats.bavail) * Number(stats.bsize);
    return {
      path: target,
      availableBytes,
      availableGiB: round(availableBytes / GIB),
      recommendedFreeGiB
    };
  } catch {
    return null;
  }
}

export async function inspectPredictionMarketAnalysisDataset(args: {
  env?: NodeJS.ProcessEnv;
  dataRoot?: string;
  outputDir?: string;
  importScriptPath?: string;
  maxDatasetBytes?: number;
  maxFilesPerTable?: number;
  recommendedFreeGiB?: number;
  ts?: string;
} = {}): Promise<PredictionMarketAnalysisReadiness> {
  const env = args.env ?? process.env;
  const dataRoot = resolve(args.dataRoot ?? env.BILL_PREDICTION_MARKET_ANALYSIS_DATA_ROOT ?? ".rumbling-hedge/external/prediction-market-analysis/data");
  const outputDir = resolve(args.outputDir ?? env.BILL_PREDICTION_MARKET_ANALYSIS_OUTPUT_DIR ?? ".rumbling-hedge/research/prediction-market-analysis");
  const importScriptPath = resolve(args.importScriptPath ?? "scripts/prediction-market-analysis-import.py");
  const maxDatasetBytes = args.maxDatasetBytes ?? Number.parseInt(env.BILL_PREDICTION_MARKET_ANALYSIS_MAX_BYTES ?? `${80 * GIB}`, 10);
  const maxFilesPerTable = args.maxFilesPerTable ?? Number.parseInt(env.BILL_PREDICTION_MARKET_ANALYSIS_MAX_FILES_PER_TABLE ?? "25", 10);
  const recommendedFreeGiB = args.recommendedFreeGiB ?? Number.parseInt(env.BILL_PREDICTION_MARKET_ANALYSIS_RECOMMENDED_FREE_GIB ?? "100", 10);
  const ts = args.ts ?? new Date().toISOString();

  const rootExists = await directoryExists(dataRoot);
  const tables: PredictionMarketAnalysisTableStatus[] = [];
  for (const table of TABLES) {
    const path = join(dataRoot, table.relativePath);
    const exists = await directoryExists(path);
    const scanned = exists ? await scanParquetFiles(path) : { files: 0, bytes: 0 };
    tables.push({
      key: table.key,
      path,
      required: table.required,
      exists,
      parquetFiles: scanned.files,
      bytes: scanned.bytes
    });
  }

  const totalParquetFiles = tables.reduce((sum, table) => sum + table.parquetFiles, 0);
  const totalBytes = tables.reduce((sum, table) => sum + table.bytes, 0);
  const duckdbAvailable = await hasPythonDuckDb();
  const disk = await diskFor(resolve(dataRoot, ".."), recommendedFreeGiB);
  const blockers: string[] = [];
  const warnings: string[] = [];

  if (!rootExists) {
    blockers.push(`data root does not exist: ${dataRoot}`);
  }
  for (const table of tables.filter((row) => row.required)) {
    if (!table.exists) {
      blockers.push(`missing required dataset directory: ${table.path}`);
    } else if (table.parquetFiles === 0) {
      blockers.push(`required dataset directory has no parquet files: ${table.path}`);
    }
  }
  if (!duckdbAvailable) {
    blockers.push("python duckdb is not installed; importer can still dry-run but cannot read parquet");
  }
  if (totalBytes > maxDatasetBytes) {
    blockers.push(`dataset size ${round(totalBytes / GIB)}GiB exceeds configured budget ${round(maxDatasetBytes / GIB)}GiB`);
  }
  if (disk && disk.availableGiB < recommendedFreeGiB && !rootExists) {
    warnings.push(`available disk is ${disk.availableGiB}GiB; recommended free space before downloading/extracting is ${recommendedFreeGiB}GiB`);
  }
  if (tables.some((table) => !table.required && table.exists && table.parquetFiles === 0)) {
    warnings.push("one or more optional dataset directories exists but has no parquet files");
  }

  const status: PredictionMarketAnalysisStatus =
    blockers.length === 0
      ? "ready"
      : rootExists && totalParquetFiles > 0
        ? "blocked"
        : "missing";

  const nextCommands = [
    `python3 -m pip install --user duckdb`,
    `python3 ${importScriptPath} --data-root ${dataRoot} --out-dir ${outputDir} --dry-run`,
    `python3 ${importScriptPath} --data-root ${dataRoot} --out-dir ${outputDir} --max-files-per-table ${maxFilesPerTable}`
  ];

  return {
    command: "prediction-market-analysis-status",
    ts,
    status,
    dataRoot,
    outputDir,
    importScriptPath,
    duckdbAvailable,
    disk,
    limits: {
      maxDatasetBytes,
      maxDatasetGiB: round(maxDatasetBytes / GIB),
      maxFilesPerTable
    },
    tables,
    totalParquetFiles,
    totalBytes,
    totalGiB: round(totalBytes / GIB),
    blockers,
    warnings,
    nextCommands,
    hermesSummary: status === "ready"
      ? "Prediction-market-analysis dataset is ready for bounded local import."
      : "Prediction-market-analysis dataset is not import-ready; keep it research-only and do not run upstream setup automatically."
  };
}

export function renderPredictionMarketAnalysisMarkdown(report: PredictionMarketAnalysisReadiness): string {
  const lines = [
    "# Prediction Market Analysis Dataset",
    "",
    `Updated: ${report.ts}`,
    "",
    `Status: ${report.status}`,
    "",
    "## Runtime",
    "",
    `- Data root: ${report.dataRoot}`,
    `- Output dir: ${report.outputDir}`,
    `- Import script: ${report.importScriptPath}`,
    `- Python DuckDB available: ${report.duckdbAvailable ? "yes" : "no"}`,
    `- Total parquet files: ${report.totalParquetFiles}`,
    `- Total scanned size: ${report.totalGiB}GiB`,
    "",
    "## Tables",
    "",
    "| Table | Required | Parquet files | Size GiB | Path |",
    "| --- | --- | ---: | ---: | --- |",
    ...report.tables.map((table) =>
      `| ${table.key} | ${table.required ? "yes" : "no"} | ${table.parquetFiles} | ${round(table.bytes / GIB)} | ${table.path} |`
    ),
    "",
    "## Blockers",
    "",
    ...(report.blockers.length > 0 ? report.blockers.map((item) => `- ${item}`) : ["- none"]),
    "",
    "## Warnings",
    "",
    ...(report.warnings.length > 0 ? report.warnings.map((item) => `- ${item}`) : ["- none"]),
    "",
    "## Safe Commands",
    "",
    ...report.nextCommands.map((command) => `- \`${command}\``),
    "",
    "## Hermes Instruction",
    "",
    `${report.hermesSummary} Hermes should monitor this report and escalate blockers, but must not download the archive, install tools, or ingest data without founder approval.`
  ];
  return `${lines.join("\n")}\n`;
}

export async function writePredictionMarketAnalysisReadiness(args: {
  report: PredictionMarketAnalysisReadiness;
  reportPath?: string;
  markdownPath?: string;
}): Promise<{ reportPath: string; markdownPath: string }> {
  const reportPath = resolve(args.reportPath ?? join(args.report.outputDir, "readiness.json"));
  const markdownPath = resolve(args.markdownPath ?? join(args.report.outputDir, "README.md"));
  await mkdir(dirname(reportPath), { recursive: true });
  await mkdir(dirname(markdownPath), { recursive: true });
  await writeFile(reportPath, `${JSON.stringify(args.report, null, 2)}\n`, "utf8");
  await writeFile(markdownPath, renderPredictionMarketAnalysisMarkdown(args.report), "utf8");
  return { reportPath, markdownPath };
}
