import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { resolve } from "node:path";

export interface GexLevels {
  gammaFlip: number | null;
  callWall: number | null;
  putWall: number | null;
  timestamp: string;
}

export interface GexSnapshot {
  spx: GexLevels;
  qqq: GexLevels;
}

const GEX_PATH = resolve(homedir(), ".rumbling-hedge/state/gex_levels.json");

export function loadGexLevels(): GexSnapshot | null {
  try {
    const raw = readFileSync(GEX_PATH, "utf8");
    const data = JSON.parse(raw);
    return {
      spx: {
        gammaFlip: data.spx?.gamma_flip ?? null,
        callWall: data.spx?.call_wall ?? null,
        putWall: data.spx?.put_wall ?? null,
        timestamp: data.timestamp,
      },
      qqq: {
        gammaFlip: data.qqq?.gamma_flip ?? null,
        callWall: data.qqq?.call_wall ?? null,
        putWall: data.qqq?.put_wall ?? null,
        timestamp: data.timestamp,
      },
    };
  } catch {
    return null;
  }
}
