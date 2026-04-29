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

function clampProfileSymbols(baseAllowedSymbols: string[], profileAllowedSymbols?: string[]): string[] {
  if (!profileAllowedSymbols || profileAllowedSymbols.length === 0) {
    return [...baseAllowedSymbols];
  }

  const baseSet = new Set(baseAllowedSymbols);
  const intersection = profileAllowedSymbols.filter((symbol) => baseSet.has(symbol));
  return intersection.length > 0 ? intersection : [...baseAllowedSymbols];
}

export function collectResearchUniverse(base: LabConfig, profiles: ResearchProfile[] = RESEARCH_PROFILES): string[] {
  const symbols = new Set<string>(base.guardrails.allowedSymbols);

  for (const profile of profiles) {
    for (const symbol of clampProfileSymbols(base.guardrails.allowedSymbols, profile.overrides.guardrails?.allowedSymbols)) {
      symbols.add(symbol);
    }
  }

  return Array.from(symbols);
}

export const RESEARCH_PROFILES: ResearchProfile[] = [
  {
    id: "topstep-index-open",
    description: "Index opening range reversal on ES and NQ.",
    overrides: {
      enabledStrategies: ["opening-range-reversal"],
      guardrails: {
        allowedSymbols: ["ES", "NQ"]
      }
    }
  },
  {
    id: "index-core-breadth",
    description: "Broad index basket for opening range reversal research.",
    overrides: {
      enabledStrategies: ["opening-range-reversal"],
      guardrails: {
        allowedSymbols: ["ES", "NQ", "MES", "MNQ", "RTY", "M2K", "YM", "MYM"]
      }
    }
  },
  {
    id: "ict-killzone-core",
    description: "ICT-style liquidity sweep, displacement, and fair value gap continuation in the morning kill zone.",
    overrides: {
      enabledStrategies: ["ict-displacement"],
      guardrails: {
        allowedSymbols: ["ES", "NQ"],
        lastEntryCt: "10:30",
        minRr: 2.6,
        maxTradesPerDay: 2,
        maxHoldMinutes: 20
      }
    }
  },
  {
    id: "session-momentum-index-core",
    description: "Pure index session momentum for trend-day continuation and open-drive follow-through.",
    overrides: {
      enabledStrategies: ["session-momentum"],
      guardrails: {
        allowedSymbols: ["ES", "NQ"],
        lastEntryCt: "10:45",
        minRr: 2.5,
        maxTradesPerDay: 2,
        maxHoldMinutes: 24
      }
    }
  },
  {
    id: "convex-index-asymmetry",
    description: "High-R convex index mix focused on displacement and sweep-reversion edges.",
    overrides: {
      enabledStrategies: ["ict-displacement", "liquidity-reversion"],
      guardrails: {
        allowedSymbols: ["ES", "NQ"],
        lastEntryCt: "10:15",
        minRr: 3.1,
        maxTradesPerDay: 2,
        maxHoldMinutes: 18
      }
    }
  },
  {
    id: "nq-convex-focus",
    description: "NQ-only convex focus — displacement and sweep-reversion with the same tight parameters as convex-index-asymmetry.",
    overrides: {
      enabledStrategies: ["ict-displacement", "liquidity-reversion"],
      guardrails: {
        allowedSymbols: ["NQ"],
        lastEntryCt: "10:15",
        minRr: 3.1,
        maxTradesPerDay: 2,
        maxHoldMinutes: 18
      }
    }
  },
  {
    id: "cross-asset-convex",
    description: "Cross-asset convex mix for index, metals, and FX dislocations with tighter selectivity.",
    overrides: {
      enabledStrategies: ["ict-displacement", "liquidity-reversion", "opening-range-reversal"],
      guardrails: {
        allowedSymbols: ["ES", "NQ", "GC", "6E"],
        lastEntryCt: "10:30",
        minRr: 3,
        maxTradesPerDay: 2,
        maxHoldMinutes: 20
      }
    }
  },
  {
    id: "balanced-wctc",
    description: "Opening reversal and short-horizon reversion blended on liquid index and commodity futures.",
    overrides: {
      enabledStrategies: ["opening-range-reversal", "liquidity-reversion"],
      guardrails: {
        allowedSymbols: ["ES", "NQ", "CL", "GC", "6E"]
      }
    }
  },
  {
    id: "strict-news",
    description: "Opening reversal with tighter high-impact news gate and session constraints.",
    overrides: {
      enabledStrategies: ["opening-range-reversal"],
      guardrails: {
        allowedSymbols: ["ES", "NQ", "CL", "GC", "6E"],
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
  },
  {
    id: "liq-rev-index-pure",
    description: "Pure index liquidity sweep-and-reversion on ES and NQ for the morning session.",
    overrides: {
      enabledStrategies: ["liquidity-reversion"],
      guardrails: {
        allowedSymbols: ["ES", "NQ"],
        lastEntryCt: "09:15",
        minRr: 2.5,
        maxTradesPerDay: 3,
        maxHoldMinutes: 15
      }
    }
  },
  {
    id: "orr-liq-index-blend",
    description: "Opening range reversal and liquidity reversion blended on ES and NQ.",
    overrides: {
      enabledStrategies: ["opening-range-reversal", "liquidity-reversion"],
      guardrails: {
        allowedSymbols: ["ES", "NQ"],
        lastEntryCt: "10:00",
        minRr: 2.5,
        maxTradesPerDay: 3,
        maxHoldMinutes: 20
      }
    }
  }
];

export function mergeProfile(base: LabConfig, profile: ResearchProfile): LabConfig {
  const clampedSymbols = clampProfileSymbols(base.guardrails.allowedSymbols, profile.overrides.guardrails?.allowedSymbols);

  return {
    ...base,
    ...profile.overrides,
    guardrails: {
      ...base.guardrails,
      ...(profile.overrides.guardrails ?? {}),
      allowedSymbols: clampedSymbols
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
