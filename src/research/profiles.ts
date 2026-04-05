import type { LabConfig } from "../domain.js";

type ResearchProfileOverrides = Omit<Partial<LabConfig>, "guardrails" | "live" | "tuning"> & {
  guardrails?: Partial<LabConfig["guardrails"]>;
  live?: Partial<LabConfig["live"]>;
  tuning?: Partial<LabConfig["tuning"]>;
};

export interface ResearchProfile {
  id: string;
  description: string;
  overrides: ResearchProfileOverrides;
}

export function collectResearchUniverse(base: LabConfig, profiles: ResearchProfile[] = RESEARCH_PROFILES): string[] {
  const symbols = new Set<string>(base.guardrails.allowedSymbols);

  for (const profile of profiles) {
    const allowedSymbols = profile.overrides.guardrails?.allowedSymbols;
    if (!allowedSymbols) {
      continue;
    }

    for (const symbol of allowedSymbols) {
      symbols.add(symbol);
    }
  }

  return Array.from(symbols);
}

export const RESEARCH_PROFILES: ResearchProfile[] = [
  {
    id: "topstep-index-open",
    description: "Index opening range reversal plus delayed session momentum.",
    overrides: {
      enabledStrategies: ["opening-range-reversal", "session-momentum"],
      guardrails: {
        allowedSymbols: ["ES", "NQ"]
      }
    }
  },
  {
    id: "index-core-breadth",
    description: "Broad index core basket for opening range and momentum research.",
    overrides: {
      enabledStrategies: ["opening-range-reversal", "session-momentum"],
      guardrails: {
        allowedSymbols: ["ES", "NQ", "MES", "MNQ", "RTY", "M2K", "YM", "MYM"]
      }
    }
  },
  {
    id: "trend-only",
    description: "Cross-asset session momentum only, with fewer moving parts.",
    overrides: {
      enabledStrategies: ["session-momentum"],
      guardrails: {
        allowedSymbols: ["ES", "NQ", "CL", "GC", "6E"]
      }
    }
  },
  {
    id: "liquid-core-mix",
    description: "Liquid futures core mix across index, energy, metals, FX, and rates.",
    overrides: {
      enabledStrategies: ["session-momentum"],
      guardrails: {
        allowedSymbols: ["ES", "NQ", "CL", "GC", "6E", "ZN"]
      }
    }
  },
  {
    id: "balanced-wctc",
    description: "Opening reversal, momentum, and short-horizon reversion together.",
    overrides: {
      enabledStrategies: ["opening-range-reversal", "session-momentum", "liquidity-reversion"],
      guardrails: {
        allowedSymbols: ["ES", "NQ", "CL", "GC", "6E", "ZN"]
      }
    }
  },
  {
    id: "strict-news",
    description: "Opening reversal and momentum with a tighter high-impact news gate.",
    overrides: {
      enabledStrategies: ["opening-range-reversal", "session-momentum"],
      guardrails: {
        allowedSymbols: ["ES", "NQ", "CL", "GC", "6E", "ZN"],
        sessionStartCt: "08:30",
        lastEntryCt: "11:30",
        flatByCt: "15:10",
        minRr: 2.5,
        maxRiskPerTradePct: 1,
        maxContracts: 2,
        maxTradesPerDay: 3,
        maxHoldMinutes: 30,
        maxDailyLossR: 2,
        maxConsecutiveLosses: 2,
        newsProbabilityThreshold: 0.75
      }
    }
  }
];

export function mergeProfile(base: LabConfig, profile: ResearchProfile): LabConfig {
  return {
    ...base,
    ...profile.overrides,
    guardrails: {
      ...base.guardrails,
      ...(profile.overrides.guardrails ?? {})
    },
    live: {
      ...base.live,
      ...(profile.overrides.live ?? {})
    },
    tuning: {
      ...base.tuning,
      ...(profile.overrides.tuning ?? {})
    }
  };
}
