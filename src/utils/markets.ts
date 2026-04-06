import type { MarketCategory } from "../domain.js";

const INDEX_SYMBOLS = new Set(["ES", "NQ", "RTY", "MES", "MNQ", "M2K", "NKD", "YM", "MYM"]);
const FX_SYMBOLS = new Set(["6A", "6B", "6C", "6E", "E7", "6J", "6S", "6M", "6N", "M6E", "M6A", "M6B"]);
const ENERGY_SYMBOLS = new Set(["CL", "NG", "QM", "QG", "MCL", "MNG", "RB", "HO"]);
const METAL_SYMBOLS = new Set(["GC", "SI", "HG", "MGC", "SIL", "MHG", "PL"]);
const BOND_SYMBOLS = new Set(["UB", "TN", "ZF", "ZT", "ZN", "ZB"]);
const AG_SYMBOLS = new Set(["HE", "LE", "ZC", "ZW", "ZS", "ZM", "ZL"]);
const CRYPTO_SYMBOLS = new Set(["MBT", "MET"]);
const ALLOWED_SYMBOLS_BY_LENGTH = [...INDEX_SYMBOLS, ...FX_SYMBOLS, ...ENERGY_SYMBOLS, ...METAL_SYMBOLS, ...BOND_SYMBOLS, ...AG_SYMBOLS, ...CRYPTO_SYMBOLS]
  .sort((left, right) => right.length - left.length);

export interface MarketSpec {
  symbol: string;
  category: MarketCategory;
  label: string;
  contractStyle: "standard" | "mini" | "micro" | "other";
}

export interface FuturesTickSpec {
  tickSize: number;
  tickValueUsd: number;
}

const FUTURES_TICK_SPECS: Record<string, FuturesTickSpec> = {
  ES: { tickSize: 0.25, tickValueUsd: 12.5 },
  MES: { tickSize: 0.25, tickValueUsd: 1.25 },
  NQ: { tickSize: 0.25, tickValueUsd: 5 },
  MNQ: { tickSize: 0.25, tickValueUsd: 0.5 },
  RTY: { tickSize: 0.1, tickValueUsd: 5 },
  M2K: { tickSize: 0.1, tickValueUsd: 0.5 },
  YM: { tickSize: 1, tickValueUsd: 5 },
  MYM: { tickSize: 1, tickValueUsd: 0.5 },
  CL: { tickSize: 0.01, tickValueUsd: 10 },
  MCL: { tickSize: 0.01, tickValueUsd: 1 },
  GC: { tickSize: 0.1, tickValueUsd: 10 },
  MGC: { tickSize: 0.1, tickValueUsd: 1 },
  SI: { tickSize: 0.005, tickValueUsd: 25 },
  HG: { tickSize: 0.0005, tickValueUsd: 12.5 },
  ZN: { tickSize: 0.015625, tickValueUsd: 15.625 },
  ZB: { tickSize: 0.03125, tickValueUsd: 31.25 },
  ZF: { tickSize: 0.0078125, tickValueUsd: 7.8125 },
  ZT: { tickSize: 0.00390625, tickValueUsd: 7.8125 },
  "6E": { tickSize: 0.00005, tickValueUsd: 6.25 },
  "6J": { tickSize: 0.0000005, tickValueUsd: 6.25 },
  "6B": { tickSize: 0.0001, tickValueUsd: 6.25 },
  "6A": { tickSize: 0.0001, tickValueUsd: 10 },
  "6C": { tickSize: 0.0001, tickValueUsd: 10 },
  "6S": { tickSize: 0.0001, tickValueUsd: 12.5 }
};

function isFuturesMonthCode(value: string): boolean {
  return /^[FGHJKMNQUVXZ]$/.test(value);
}

function isContractSuffix(value: string): boolean {
  if (!value) {
    return true;
  }

  if (/^[FGHJKMNQUVXZ]\d{1,2}$/.test(value)) {
    return true;
  }

  if (/^\d{1,2}$/.test(value)) {
    return true;
  }

  if (/^\d{1,2}[A-Z]?$/.test(value)) {
    return true;
  }

  if (value.length === 1 && isFuturesMonthCode(value)) {
    return true;
  }

  return false;
}

export function normalizeFuturesSymbol(symbol: string): string {
  const cleaned = symbol.trim().toUpperCase().replace(/[^A-Z0-9]/g, "");

  if (!cleaned) {
    return cleaned;
  }

  if ((ALLOWED_SYMBOLS_BY_LENGTH as readonly string[]).includes(cleaned)) {
    return cleaned;
  }

  const match = ALLOWED_SYMBOLS_BY_LENGTH.find((candidate) => {
    if (!cleaned.startsWith(candidate)) {
      return false;
    }

    const suffix = cleaned.slice(candidate.length);
    return isContractSuffix(suffix);
  });

  return match ?? cleaned;
}

export function getMarketCategory(symbol: string): MarketCategory {
  const upper = normalizeFuturesSymbol(symbol);

  if (INDEX_SYMBOLS.has(upper)) {
    return "index";
  }
  if (FX_SYMBOLS.has(upper)) {
    return "fx";
  }
  if (ENERGY_SYMBOLS.has(upper)) {
    return "energy";
  }
  if (METAL_SYMBOLS.has(upper)) {
    return "metal";
  }
  if (BOND_SYMBOLS.has(upper)) {
    return "bond";
  }
  if (AG_SYMBOLS.has(upper)) {
    return "ag";
  }
  if (CRYPTO_SYMBOLS.has(upper)) {
    return "crypto";
  }

  return "index";
}

export function isIndexSymbol(symbol: string): boolean {
  return getMarketCategory(symbol) === "index";
}

export function getMarketSpec(symbol: string): MarketSpec {
  const normalized = normalizeFuturesSymbol(symbol);
  const category = getMarketCategory(normalized);
  const contractStyle: MarketSpec["contractStyle"] = normalized.startsWith("M") && normalized.length > 1 ? "micro" : "standard";

  return {
    symbol: normalized,
    category,
    label: `${normalized} ${category} futures`,
    contractStyle
  };
}

export function getFuturesTickSpec(symbol: string): FuturesTickSpec {
  const normalized = normalizeFuturesSymbol(symbol);
  return FUTURES_TICK_SPECS[normalized] ?? { tickSize: 0.25, tickValueUsd: 5 };
}

export function pointsToTicks(symbol: string, points: number): number {
  const spec = getFuturesTickSpec(symbol);
  if (spec.tickSize <= 0) {
    return 0;
  }
  return points / spec.tickSize;
}

export function ticksToDollars(symbol: string, ticks: number, contracts: number): number {
  const spec = getFuturesTickSpec(symbol);
  return ticks * spec.tickValueUsd * Math.max(1, contracts);
}
