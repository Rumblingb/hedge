import type { Bar, LabConfig, TradeRecord } from "../domain.js";
import type { NewsGate } from "../news/base.js";
import { buildDailyStrategyPlan } from "./dailyPlan.js";
import { readJournal } from "./journal.js";
import { summarizeTrades } from "./report.js";
import { readKillSwitch } from "./killSwitch.js";
import { buildDemoAccountStrategyLanes, isDemoAccountLockSatisfied, listAllowedDemoAccounts } from "../live/demoAccounts.js";

function summarizeRecentTrades(trades: TradeRecord[]): Array<{
  symbol: string;
  strategyId: string;
  side: string;
  netRMultiple: number;
  exitReason: string;
  exitTs: string;
}> {
  return trades
    .slice(-5)
    .reverse()
    .map((trade) => ({
      symbol: trade.symbol,
      strategyId: trade.strategyId,
      side: trade.side,
      netRMultiple: Number(trade.netRMultiple.toFixed(4)),
      exitReason: trade.exitReason,
      exitTs: trade.exitTs
    }));
}

export async function buildDashboardSnapshot(args: {
  bars: Bar[];
  baseConfig: LabConfig;
  newsGate: NewsGate;
}): Promise<{
  timestamp: string;
  operator: {
    username: string | null;
    accountLabel: string | null;
    accountId: string | null;
    allowedAccountId: string | null;
    allowedAccountIds: string[];
    demoOnly: boolean;
    readOnly: boolean;
    liveExecutionEnabled: boolean;
    demoAccountLockSatisfied: boolean;
    demoAccountLanes: ReturnType<typeof buildDemoAccountStrategyLanes>;
  };
  tradingScope: {
    allowedSymbols: string[];
    accountPhase: string;
    mode: string;
  };
  killSwitch: {
    path: string;
    state: Awaited<ReturnType<typeof readKillSwitch>>;
  };
  dayPlan: Awaited<ReturnType<typeof buildDailyStrategyPlan>>;
  journal: {
    path: string;
    totalTrades: number;
    summary: ReturnType<typeof summarizeTrades>;
    recentTrades: ReturnType<typeof summarizeRecentTrades>;
  };
}> {
  const [dayPlan, trades, killSwitchState] = await Promise.all([
    buildDailyStrategyPlan(args),
    readJournal(args.baseConfig.journalPath),
    readKillSwitch(args.baseConfig.killSwitchPath)
  ]);

  return {
    timestamp: new Date().toISOString(),
    operator: {
      username: args.baseConfig.live.username ?? null,
      accountLabel: args.baseConfig.live.allowedAccountLabel ?? null,
      accountId: args.baseConfig.live.accountId ?? null,
      allowedAccountId: args.baseConfig.live.allowedAccountId ?? null,
      allowedAccountIds: listAllowedDemoAccounts(args.baseConfig.live).map((account) => account.accountId),
      demoOnly: args.baseConfig.live.demoOnly,
      readOnly: args.baseConfig.live.readOnly,
      liveExecutionEnabled: args.baseConfig.live.enabled,
      demoAccountLockSatisfied: isDemoAccountLockSatisfied(args.baseConfig.live),
      demoAccountLanes: buildDemoAccountStrategyLanes({
        config: args.baseConfig.live,
        enabledStrategies: args.baseConfig.enabledStrategies
      })
    },
    tradingScope: {
      allowedSymbols: args.baseConfig.guardrails.allowedSymbols,
      accountPhase: args.baseConfig.accountPhase,
      mode: args.baseConfig.mode
    },
    killSwitch: {
      path: args.baseConfig.killSwitchPath,
      state: killSwitchState
    },
    dayPlan,
    journal: {
      path: args.baseConfig.journalPath,
      totalTrades: trades.length,
      summary: summarizeTrades(trades),
      recentTrades: summarizeRecentTrades(trades)
    }
  };
}
