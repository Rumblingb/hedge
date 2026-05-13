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
    id: "ict-displacement-5m-index",
    description: "ICT displacement on 5-min bars. Range > 2.5x ATR, 3R target. Topstep pass: 190 trades, +$8.7K MNQ.",
    overrides: {
      enabledStrategies: ["ict-displacement-5m"],
      guardrails: {
        allowedSymbols: ["NQ", "ES"],
        lastEntryCt: "11:00",
        minRr: 2.5,
        maxTradesPerDay: 4,
        maxHoldMinutes: 60
      }
    }
  },
  {
    id: "ict-narrative-nq",
    description: "ICT narrative trading: FHDR break + first FVG entry with daily bias filter. ES/NQ only, kill zone 08:30-11:00 ET.",
    overrides: {
      enabledStrategies: ["ict-narrative"],
      guardrails: {
        allowedSymbols: ["ES", "NQ"],
        sessionStartCt: "08:30",
        lastEntryCt: "11:00",
        minRr: 2.5,
        maxTradesPerDay: 3,
        maxHoldMinutes: 45
      }
    }
  },
  {
    id: "ict-sweep-reversion-nq",
    description: "ICT liquidity sweep into order block with FVG confirmation. Conservative entries on ES/NQ during London-NY overlap.",
    overrides: {
      enabledStrategies: ["ict-sweep-reversion"],
      guardrails: {
        allowedSymbols: ["ES", "NQ"],
        sessionStartCt: "08:30",
        lastEntryCt: "11:30",
        minRr: 2.5,
        maxTradesPerDay: 2,
        maxHoldMinutes: 30
      }
    }
  },
  {
    id: "ict-breakout-nq",
    description: "ICT market structure shift breakout with displacement confirmation and three-candle trailing stop. ES/NQ morning session.",
    overrides: {
      enabledStrategies: ["ict-breakout"],
      guardrails: {
        allowedSymbols: ["ES", "NQ"],
        sessionStartCt: "08:30",
        lastEntryCt: "11:00",
        minRr: 2,
        maxTradesPerDay: 3,
        maxHoldMinutes: 30
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
  },
  {
    id: "vwap-reversion-index",
    description: "Pure VWAP mean-reversion on ES and NQ — fires when price stretches 2+ ATR from session VWAP.",
    overrides: {
      enabledStrategies: ["vwap-reversion"],
      guardrails: {
        allowedSymbols: ["ES", "NQ"],
        lastEntryCt: "11:00",
        minRr: 2.5,
        maxTradesPerDay: 4,
        maxHoldMinutes: 20
      }
    }
  },
  {
    id: "vwap-liq-index-blend",
    description: "VWAP reversion and liquidity sweep-fade blended on ES and NQ for range sessions.",
    overrides: {
      enabledStrategies: ["vwap-reversion", "liquidity-reversion"],
      guardrails: {
        allowedSymbols: ["ES", "NQ"],
        lastEntryCt: "11:00",
        minRr: 2.5,
        maxTradesPerDay: 4,
        maxHoldMinutes: 20
      }
    }
  },
  {
    id: "opening-stop-hunt-index",
    description: "Opening stop hunt on ES and NQ — fade the first-bar sweep of prior session high/low that closes back inside range.",
    overrides: {
      enabledStrategies: ["opening-stop-hunt"],
      guardrails: {
        allowedSymbols: ["ES", "NQ"],
        lastEntryCt: "10:30",
        minRr: 2.5,
        maxTradesPerDay: 3,
        maxHoldMinutes: 30
      }
    }
  },
  {
    id: "event-spike-fade-index",
    description: "Event spike fade on ES and NQ — fade the post-event momentum spike after FOMC/NFP/CPI announcements revert.",
    overrides: {
      enabledStrategies: ["event-spike-fade"],
      guardrails: {
        allowedSymbols: ["ES", "NQ", "CL"],
        lastEntryCt: "14:00",
        minRr: 2.5,
        maxTradesPerDay: 3,
        maxHoldMinutes: 30
      }
    }
  },
  {
    id: "opening-hunt-liq-blend",
    description: "Opening stop hunt and liquidity reversion blended — captures both the AM sweep and subsequent VWAP reversion on ES/NQ.",
    overrides: {
      enabledStrategies: ["opening-stop-hunt", "liquidity-reversion"],
      guardrails: {
        allowedSymbols: ["ES", "NQ"],
        lastEntryCt: "11:00",
        minRr: 2.5,
        maxTradesPerDay: 4,
        maxHoldMinutes: 30
      }
    }
  },
  {
    id: "structural-flows-blend",
    description: "Institutional structural flows with liquidity reversion base — calendar-timed flows (quarterly roll, OPEX gamma pin, FOMC fade) on top of daily VWAP reversion.",
    overrides: {
      enabledStrategies: ["structural-flows", "liquidity-reversion"],
      guardrails: {
        allowedSymbols: ["ES", "NQ", "ZN", "CL"],
        lastEntryCt: "14:30",
        minRr: 2.0,
        maxTradesPerDay: 4,
        maxHoldMinutes: 30
      }
    }
  },
  {
    id: "capitulation-score-index",
    description: "Multi-indicator capitulation scoring (COT positioning, HMM regime, macro context) with dynamic position sizing — 1-2 contracts based on 0-5 composite score.",
    overrides: {
      enabledStrategies: ["capitulation-score"],
      guardrails: {
        allowedSymbols: ["ES", "NQ"],
        lastEntryCt: "11:00",
        minRr: 2.5,
        maxTradesPerDay: 2,
        maxHoldMinutes: 30
      }
    }
  },
  {
    id: "expiry-flow-index",
    description: "Gamma-driven expiry flow with VIX contango signals — captures pinning, charm, and volatility term-structure edges around option expiration.",
    overrides: {
      enabledStrategies: ["expiry-flow"],
      guardrails: {
        allowedSymbols: ["ES", "NQ"],
        lastEntryCt: "15:00",
        minRr: 2.0,
        maxTradesPerDay: 3,
        maxHoldMinutes: 45
      }
    }
  },
  {
    id: "intraday-momentum-index",
    description: "First-30-min predicts last-30-min intraday momentum anomaly (Gao, Han, Li, Zhou 2018). Long if RTH open drive >0.3%, short if <-0.3%. ES/NQ only.",
    overrides: {
      enabledStrategies: ["intraday-momentum"],
      guardrails: {
        allowedSymbols: ["ES", "NQ"],
        lastEntryCt: "11:00",
        minRr: 2.0,
        maxTradesPerDay: 1,
        maxHoldMinutes: 120
      }
    }
  },
  {
    id: "kronos-direction-index",
    description: "Kronos 24h forecast direction — reads context.macro.kronosDirection to trade directional bias. ES/NQ only.",
    overrides: {
      enabledStrategies: ["kronos-direction"],
      guardrails: {
        allowedSymbols: ["ES", "NQ"],
        lastEntryCt: "14:00",
        minRr: 2.0,
        maxTradesPerDay: 1,
        maxHoldMinutes: 60
      }
    }
  },
  {
    id: "gap-fade-regime-index",
    description: "Overnight gap fade with HMM regime and COT filter. Fades gaps >0.5% and >1ATR in range-chop/low-vol regimes. ES/NQ/CL/GC.",
    overrides: {
      enabledStrategies: ["gap-fade-regime"],
      guardrails: {
        allowedSymbols: ["ES", "NQ", "CL", "GC"],
        lastEntryCt: "10:30",
        minRr: 2.0,
        maxTradesPerDay: 2,
        maxHoldMinutes: 120
      }
    }
  },
  {
    id: "short-term-reversal-index",
    description: "Short-term reversal from Hanauer (2023) FAJ — 60-bar lookback extreme returns reverse toward VWAP with volume confirmation. ES/NQ/CL/GC.",
    overrides: {
      enabledStrategies: ["short-term-reversal"],
      guardrails: {
        allowedSymbols: ["ES", "NQ", "CL", "GC"],
        lastEntryCt: "14:00",
        minRr: 2.0,
        maxTradesPerDay: 2,
        maxHoldMinutes: 60
      }
    }
  },
  {
    id: "ret-30-momentum-index",
    description: "Alpha-lab verified ret_30:30 momentum — 30-bar return momentum with 30-bar forward horizon. Follows trend, not reversal. Test IC 0.245, net edge +3.1% on NQ. ES/NQ.",
    overrides: {
      enabledStrategies: ["ret-30-momentum"],
      guardrails: {
        allowedSymbols: ["ES", "NQ"],
        sessionStartCt: "08:30",
        lastEntryCt: "15:30",
        minRr: 0.5,
        maxTradesPerDay: 2,
        maxHoldMinutes: 30
      }
    }
  },
  {
    id: "regime-locked-momentum-index",
    description: "Regime-locked momentum — HMM=trending, COT aligned, RTH kill zone (08:30-10:30 CT), SMA(20) crossover with 0.5×ATR. Triple-filtered. ES/NQ.",
    overrides: {
      enabledStrategies: ["regime-locked-momentum"],
      guardrails: {
        allowedSymbols: ["ES", "NQ"],
        sessionStartCt: "08:30",
        lastEntryCt: "10:30",
        minRr: 2.0,
        maxTradesPerDay: 1,
        maxHoldMinutes: 45
      }
    }
  },
  {
    id: "monthly-seasonality-index",
    description: "Monthly seasonality from Hanauer (2023) FAJ — long bias on turn-of-month days (first 3 + last 2 trading days). ES/NQ only.",
    overrides: {
      enabledStrategies: ["monthly-seasonality"],
      guardrails: {
        allowedSymbols: ["ES", "NQ"],
        lastEntryCt: "10:30",
        minRr: 2.0,
        maxTradesPerDay: 1,
        maxHoldMinutes: 120
      }
    }
  },
  {
    id: "rsi2-mean-reversion",
    description: "RSI(2) mean-reversion from Larry Connors — fires when RSI(2)<5 (long) or >95 (short). 10-bar max hold. ES/NQ/CL/GC.",
    overrides: {
      enabledStrategies: ["rsi2-mean-reversion"],
      guardrails: {
        allowedSymbols: ["ES", "NQ", "CL", "GC"],
        lastEntryCt: "15:00",
        minRr: 1.5,
        maxTradesPerDay: 4,
        maxHoldMinutes: 10
      }
    }
  },
  {
    id: "vol-risk-premium-index",
    description: "Volatility Risk Premium harvesting on ES/NQ. Long dips/short spikes when VIX contango (VRP positive). Gated on capitulation < 3, HMM regime, COT dealer alignment. Structural edge — 30+ year persistence.",
    overrides: {
      enabledStrategies: ["vol-risk-premium"],
      guardrails: {
        allowedSymbols: ["ES", "NQ"],
        lastEntryCt: "15:30",
        minRr: 1.5,
        maxTradesPerDay: 3,
        maxHoldMinutes: 45
      }
    }
  },
  {
    id: "csm-v2-index",
    description: "Cross-Sectional Momentum v2: Risk-adjusted (Sharpe-scaled) ranking of ES/NQ/CL/GC. Regime-gated (HMM trending + COT-aligned + Kronos-confirmed + dispersion gate). Structural edge from slow cross-asset information diffusion.",
    overrides: {
      enabledStrategies: ["cross-sectional-momentum"],
      guardrails: {
        allowedSymbols: ["ES", "NQ", "CL", "GC"],
        lastEntryCt: "15:00",
        minRr: 2.0,
        maxTradesPerDay: 4,
        maxHoldMinutes: 30
      },
      tuning: {
        momentumLookbackBars: 40
      }
    }
  },
  // WorldQuant 101 Alphas — institutional alpha signals (Kakushadze 2015)
  // Grouped into 4 profiles to keep factory runs manageable on 16GB Mac Mini.
  // Each profile ~5 strategies. Run 1-2 profiles at a time with BILL_STRATEGY_FACTORY_PROFILE_IDS.
  {
    id: "wq-momentum-trend",
    description: "WQ Momentum/Trend Alphas: 009 (accel/decel), 012 (vol-signed momentum), 021 (mean ret 8d), 049 (open-close×vol corr), 083 (VWAP distance). Trend continuation signals with institutional validation.",
    overrides: {
      enabledStrategies: ["wq-alpha-009", "wq-alpha-012", "wq-alpha-021", "wq-alpha-049", "wq-alpha-083"],
      guardrails: {
        allowedSymbols: ["ES", "NQ", "CL", "GC"],
        lastEntryCt: "15:00",
        minRr: 1.8,
        maxTradesPerDay: 4,
        maxHoldMinutes: 30
      }
    }
  },
  {
    id: "wq-reversal",
    description: "WQ Reversal Alphas: 001 (extreme neg ret), 006 (open-vol reversal), 020 (gap fade), 053 (9d low reversal), 054 (low-close spread), 101 (close-open spread). Mean-reversion at extremes.",
    overrides: {
      enabledStrategies: ["wq-alpha-001", "wq-alpha-006", "wq-alpha-020", "wq-alpha-053", "wq-alpha-054", "wq-alpha-101"],
      guardrails: {
        allowedSymbols: ["ES", "NQ", "CL", "GC"],
        lastEntryCt: "15:00",
        minRr: 1.8,
        maxTradesPerDay: 5,
        maxHoldMinutes: 30
      }
    }
  },
  {
    id: "wq-volume-correlation",
    description: "WQ Volume/Correlation Alphas: 002 (vol-price corr), 003 (open-vol corr), 007 (vol>adv20 momentum), 008 (open×ret cross), 024 (high-rankVol corr), 044 (-high-rankVol corr). Volume-confirmed signals.",
    overrides: {
      enabledStrategies: ["wq-alpha-002", "wq-alpha-003", "wq-alpha-007", "wq-alpha-008", "wq-alpha-024", "wq-alpha-044"],
      guardrails: {
        allowedSymbols: ["ES", "NQ", "CL", "GC"],
        lastEntryCt: "15:00",
        minRr: 1.8,
        maxTradesPerDay: 5,
        maxHoldMinutes: 30
      }
    }
  },
  {
    id: "wq-liquidity-spread",
    description: "WQ Liquidity/Spread Alphas: 033 (inv-open×vol), 057 (close-VWAP decay), 065 (vol exhaustion). Liquidity-weighted and spread-based signals.",
    overrides: {
      enabledStrategies: ["wq-alpha-033", "wq-alpha-057", "wq-alpha-065"],
      guardrails: {
        allowedSymbols: ["ES", "NQ", "CL", "GC"],
        lastEntryCt: "15:00",
        minRr: 1.8,
        maxTradesPerDay: 4,
        maxHoldMinutes: 30
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
