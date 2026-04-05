import type { MarketCategory } from "../domain.js";

const INDEX_SYMBOLS = new Set(["ES", "NQ", "RTY", "MES", "MNQ", "M2K", "NKD", "YM", "MYM"]);
const FX_SYMBOLS = new Set(["6A", "6B", "6C", "6E", "E7", "6J", "6S", "6M", "6N", "M6E", "M6A", "M6B"]);
const ENERGY_SYMBOLS = new Set(["CL", "NG", "QM", "QG", "MCL", "MNG", "RB", "HO"]);
const METAL_SYMBOLS = new Set(["GC", "SI", "HG", "MGC", "SIL", "MHG", "PL"]);
const BOND_SYMBOLS = new Set(["UB", "TN", "ZF", "ZT", "ZN", "ZB"]);
const AG_SYMBOLS = new Set(["HE", "LE", "ZC", "ZW", "ZS", "ZM", "ZL"]);
const CRYPTO_SYMBOLS = new Set(["MBT", "MET"]);

export function getMarketCategory(symbol: string): MarketCategory {
  const upper = symbol.toUpperCase();

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
