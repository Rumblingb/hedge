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
