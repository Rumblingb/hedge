import { getMarketCategory } from "./markets.js";

export interface BlockedWindow {
  startCt: string;
  endCt: string;
  reason: string;
}

export interface SessionWindow {
  startCt: string;
  endCt?: string;
  blockedWindows: BlockedWindow[];
}

const TOPSTEP_BLOCKED_WINDOWS: BlockedWindow[] = [
  {
    startCt: "16:20",
    endCt: "17:00",
    reason: "topstep maintenance window"
  }
];

export function getMarketSessionWindow(symbol: string, fallbackStartCt: string): SessionWindow {
  const upper = symbol.toUpperCase();
  const category = getMarketCategory(upper);

  switch (category) {
    case "index":
      return { startCt: "08:30", endCt: "15:00", blockedWindows: TOPSTEP_BLOCKED_WINDOWS };
    case "energy":
      return upper === "CL" || upper === "QM" || upper === "MCL"
        ? { startCt: "08:00", endCt: "13:30", blockedWindows: TOPSTEP_BLOCKED_WINDOWS }
        : { startCt: fallbackStartCt, blockedWindows: TOPSTEP_BLOCKED_WINDOWS };
    case "metal":
      return { startCt: "08:20", endCt: "13:30", blockedWindows: TOPSTEP_BLOCKED_WINDOWS };
    case "ag":
    case "bond":
      return { startCt: "08:30", endCt: "13:20", blockedWindows: TOPSTEP_BLOCKED_WINDOWS };
    default:
      return { startCt: fallbackStartCt, blockedWindows: TOPSTEP_BLOCKED_WINDOWS };
  }
}
