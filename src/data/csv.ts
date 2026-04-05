import { readFile } from "node:fs/promises";
import type { Bar } from "../domain.js";
import { normalizeFuturesSymbol } from "../utils/markets.js";

type CsvField = "ts" | "symbol" | "open" | "high" | "low" | "close" | "volume";

const FIELD_ALIASES: Record<CsvField, string[]> = {
  ts: ["ts", "timestamp", "datetime", "date_time", "time_stamp"],
  symbol: ["symbol", "root", "ticker", "contract", "instrument"],
  open: ["open", "o"],
  high: ["high", "h"],
  low: ["low", "l"],
  close: ["close", "c"],
  volume: ["volume", "vol", "v"]
};

function normalizeHeaderToken(value: string): string {
  return value.trim().toLowerCase().replace(/[^a-z0-9]+/g, "");
}

function parseCsvLine(line: string): string[] {
  const values: string[] = [];
  let current = "";
  let inQuotes = false;

  for (let index = 0; index < line.length; index += 1) {
    const char = line[index];

    if (inQuotes) {
      if (char === "\"") {
        if (line[index + 1] === "\"") {
          current += "\"";
          index += 1;
        } else {
          inQuotes = false;
        }
      } else {
        current += char;
      }
      continue;
    }

    if (char === ",") {
      values.push(current.trim());
      current = "";
      continue;
    }

    if (char === "\"") {
      inQuotes = true;
      continue;
    }

    current += char;
  }

  values.push(current.trim());
  return values.map((value) => value.replace(/^\uFEFF/, ""));
}

function isCommentOrBlank(line: string): boolean {
  const trimmed = line.trim();
  return trimmed.length === 0 || trimmed.startsWith("#");
}

function findHeaderRow(rows: string[][]): Record<CsvField, number> | null {
  const headers = rows[0] ?? [];
  const lookup = new Map<string, number>();

  headers.forEach((header, index) => {
    const token = normalizeHeaderToken(header);
    if (token) {
      lookup.set(token, index);
    }
  });

  const mapping = {} as Record<CsvField, number>;

  for (const field of Object.keys(FIELD_ALIASES) as CsvField[]) {
    const aliases = FIELD_ALIASES[field];
    const index = aliases
      .map((alias) => lookup.get(normalizeHeaderToken(alias)))
      .find((value): value is number => value !== undefined);

    if (index === undefined) {
      return null;
    }

    mapping[field] = index;
  }

  return mapping;
}

function parseFiniteNumber(value: string, filePath: string, lineNumber: number, field: CsvField): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    throw new Error(`Invalid ${field} value in ${filePath} at line ${lineNumber}: ${value}`);
  }
  return parsed;
}

function parseTs(value: string, filePath: string, lineNumber: number): string {
  const trimmed = value.trim();
  if (!trimmed) {
    throw new Error(`Missing ts value in ${filePath} at line ${lineNumber}`);
  }

  return trimmed;
}

function getCell(row: string[], index: number, filePath: string, lineNumber: number, field: CsvField): string {
  const value = row[index];
  if (value === undefined || value.trim() === "") {
    throw new Error(`Missing ${field} value in ${filePath} at line ${lineNumber}`);
  }
  return value;
}

export interface CsvInspectionIssue {
  lineNumber: number;
  message: string;
}

export interface CsvInspection {
  path: string;
  hasHeader: boolean;
  dataRows: number;
  symbols: string[];
  startTs?: string;
  endTs?: string;
  orderedByTimestamp: boolean;
  issues: CsvInspectionIssue[];
}

function isValidTimestamp(value: string): boolean {
  return !Number.isNaN(Date.parse(value));
}

function compareIsoTs(left: string, right: string): number {
  return Date.parse(left) - Date.parse(right);
}

export async function inspectBarsFromCsv(path: string): Promise<CsvInspection> {
  const raw = await readFile(path, "utf8");
  const lines = raw
    .replace(/^\uFEFF/, "")
    .split(/\r?\n/)
    .map((line, index) => ({ line, lineNumber: index + 1 }))
    .filter(({ line }) => !isCommentOrBlank(line));

  if (lines.length === 0) {
    return {
      path,
      hasHeader: false,
      dataRows: 0,
      symbols: [],
      orderedByTimestamp: true,
      issues: [{ lineNumber: 1, message: "CSV file is empty." }]
    };
  }

  const parsedRows = lines.map(({ line }) => parseCsvLine(line));
  const hasHeader = findHeaderRow(parsedRows) !== null;
  const dataRows = hasHeader ? lines.slice(1) : lines;
  const issues: CsvInspectionIssue[] = [];
  const symbols = new Set<string>();
  const timestamps: string[] = [];

  dataRows.forEach(({ line, lineNumber }) => {
    const cells = parseCsvLine(line);
    if (cells.length < 7) {
      issues.push({
        lineNumber,
        message: `Expected at least 7 columns, found ${cells.length}.`
      });
      return;
    }

    const ts = cells[0]?.trim();
    const symbol = normalizeFuturesSymbol(cells[1] ?? "");

    if (!ts) {
      issues.push({ lineNumber, message: "Missing timestamp." });
    } else if (!isValidTimestamp(ts)) {
      issues.push({ lineNumber, message: `Invalid timestamp: ${ts}` });
    } else {
      timestamps.push(ts);
    }

    if (!symbol) {
      issues.push({ lineNumber, message: "Missing symbol." });
    } else {
      symbols.add(symbol);
    }

    ["open", "high", "low", "close", "volume"].forEach((field, offset) => {
      const value = cells[offset + 2];
      if (value === undefined || value.trim() === "") {
        issues.push({ lineNumber, message: `Missing ${field} value.` });
        return;
      }

      if (!Number.isFinite(Number(value))) {
        issues.push({ lineNumber, message: `Invalid ${field} value: ${value}` });
      }
    });
  });

  const orderedByTimestamp = timestamps.every((timestamp, index) => index === 0 || compareIsoTs(timestamps[index - 1], timestamp) <= 0);
  if (!orderedByTimestamp) {
    issues.push({
      lineNumber: 0,
      message: "Rows are not ordered by timestamp."
    });
  }

  return {
    path,
    hasHeader,
    dataRows: dataRows.length,
    symbols: Array.from(symbols),
    startTs: timestamps[0],
    endTs: timestamps[timestamps.length - 1],
    orderedByTimestamp,
    issues
  };
}

export async function loadBarsFromCsv(path: string): Promise<Bar[]> {
  const raw = await readFile(path, "utf8");
  const lines = raw
    .replace(/^\uFEFF/, "")
    .split(/\r?\n/)
    .map((line, index) => ({ line, lineNumber: index + 1 }))
    .filter(({ line }) => !isCommentOrBlank(line));

  if (lines.length === 0) {
    throw new Error(`CSV file ${path} is empty.`);
  }

  const parsedRows = lines.map(({ line }) => parseCsvLine(line));
  const headerMap = findHeaderRow(parsedRows);
  const dataRows = headerMap ? lines.slice(1) : lines;

  return dataRows.map(({ line, lineNumber }) => {
    const cells = parseCsvLine(line);
    const read = (field: CsvField, fallbackIndex: number): string => {
      const index = headerMap ? headerMap[field] : fallbackIndex;
      return getCell(cells, index, path, lineNumber, field);
    };

    const ts = parseTs(read("ts", 0), path, lineNumber);
    const symbol = normalizeFuturesSymbol(read("symbol", 1));

    if (!symbol) {
      throw new Error(`Missing symbol value in ${path} at line ${lineNumber}`);
    }

    return {
      ts,
      symbol,
      open: parseFiniteNumber(read("open", 2), path, lineNumber, "open"),
      high: parseFiniteNumber(read("high", 3), path, lineNumber, "high"),
      low: parseFiniteNumber(read("low", 4), path, lineNumber, "low"),
      close: parseFiniteNumber(read("close", 5), path, lineNumber, "close"),
      volume: parseFiniteNumber(read("volume", 6), path, lineNumber, "volume")
    };
  });
}
