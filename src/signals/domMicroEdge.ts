import { readFile } from "node:fs/promises";
import { existsSync } from "node:fs";

const DOM_EDGE_PATH = process.env.HOME + "/.rumbling-hedge/state/dom_micro_edges.json";

interface DomEdgeData {
  timestamp: string;
  signals: string[];
  ofi_3: number;
  cd_10: number;
  iceberg_count: number;
}

export interface DomEdgeAdjustment {
  confidenceBoost: number;
  sizingDelta: number;
  metadata: {
    hasIceberg: boolean;
    ofi3: number;
    cd10: number;
    vwapDeviation: number;
    hasStopHunt: boolean;
  };
}

export async function getDomEdgeAdjustment(): Promise<DomEdgeAdjustment> {
  if (!existsSync(DOM_EDGE_PATH)) {
    return { confidenceBoost: 0, sizingDelta: 0, metadata: { hasIceberg: false, ofi3: 0, cd10: 0, vwapDeviation: 0, hasStopHunt: false } };
  }

  try {
    const raw = await readFile(DOM_EDGE_PATH, "utf8");
    const data: DomEdgeData = JSON.parse(raw);

    let confidenceBoost = 0;
    let sizingDelta = 0;

    // Iceberg detection → bullish for edge
    if (data.iceberg_count > 0) {
      confidenceBoost += 0.05;
      sizingDelta += 0.2;
    }

    // Order Flow Imbalance (OFI) — strong directional bias
    if (Math.abs(data.ofi_3) > 0.3) {
      const ofiDir = Math.sign(data.ofi_3);
      confidenceBoost += 0.03 * ofiDir;
      sizingDelta += 0.1 * ofiDir;
    }

    // Cumulative Delta (CD) — sustained direction
    if (Math.abs(data.cd_10) > 0.4) {
      const cdDir = Math.sign(data.cd_10);
      confidenceBoost += 0.04 * cdDir;
    }

    // VWAP stop-hunt detection
    let vwapDeviation = 0;
    let hasStopHunt = false;
    const signals = data.signals as unknown as string[];
    for (const s of signals) {
      if (typeof s === "string" && s.startsWith("VWAP_STOP_HUNT_")) {
        hasStopHunt = true;
        const dir = s.endsWith("LONG") ? 1 : -1;
        confidenceBoost += 0.06 * dir;
        sizingDelta += 0.15 * dir;
      }
      if (typeof s === "string" && s.startsWith("VWAP_DEVIATION_")) {
        const dir = s.endsWith("LONG") ? 1 : -1;
        vwapDeviation = 0.3 * dir;
      }
    }

    // Clamp
    confidenceBoost = Math.max(-0.1, Math.min(0.15, confidenceBoost));
    sizingDelta = Math.max(-0.3, Math.min(0.5, sizingDelta));

    return {
      confidenceBoost,
      sizingDelta,
      metadata: {
        hasIceberg: data.iceberg_count > 0,
        ofi3: data.ofi_3,
        cd10: data.cd_10,
        vwapDeviation,
        hasStopHunt,
      },
    };
  } catch {
    return { confidenceBoost: 0, sizingDelta: 0, metadata: { hasIceberg: false, ofi3: 0, cd10: 0, vwapDeviation: 0, hasStopHunt: false } };
  }
}
