import type { LabConfig } from "../domain.js";

export interface ResearchProfile {
  id: string;
  description: string;
  overrides: Partial<LabConfig>;
}

export const RESEARCH_PROFILES: ResearchProfile[] = [
  {
    id: "topstep-index-open",
    description: "Index opening range reversal plus delayed session momentum.",
    overrides: {
      enabledStrategies: ["opening-range-reversal", "session-momentum"]
    }
  },
  {
    id: "trend-only",
    description: "Cross-asset session momentum only, with fewer moving parts.",
    overrides: {
      enabledStrategies: ["session-momentum"]
    }
  },
  {
    id: "balanced-wctc",
    description: "Opening reversal, momentum, and short-horizon reversion together.",
    overrides: {
      enabledStrategies: ["opening-range-reversal", "session-momentum", "liquidity-reversion"]
    }
  },
  {
    id: "strict-news",
    description: "Opening reversal and momentum with a tighter high-impact news gate.",
    overrides: {
      enabledStrategies: ["opening-range-reversal", "session-momentum"],
      guardrails: {
        allowedSymbols: ["NQ", "ES", "CL", "GC", "6E"],
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
