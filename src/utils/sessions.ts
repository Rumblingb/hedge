import { getMarketCategory } from "./markets.js";

export interface SessionWindow {
  startCt: string;
  endCt?: string;
}

export function getMarketSessionWindow(symbol: string, fallbackStartCt: string): SessionWindow {
  const upper = symbol.toUpperCase();
  const category = getMarketCategory(upper);

  switch (category) {
    case "index":
      return { startCt: "08:30", endCt: "15:00" };
    case "energy":
      return upper === "CL" || upper === "QM" || upper === "MCL"
        ? { startCt: "08:00", endCt: "13:30" }
        : { startCt: fallbackStartCt };
    case "metal":
      return { startCt: "08:20", endCt: "13:30" };
    case "ag":
    case "bond":
      return { startCt: "08:30", endCt: "13:20" };
    default:
      return { startCt: fallbackStartCt };
  }
}
