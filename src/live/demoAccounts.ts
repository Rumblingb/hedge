import type { LiveAdapterConfig } from "../domain.js";

export interface DemoAccountBinding {
  accountId: string;
  label: string | null;
  slot: number;
  selected: boolean;
}

export interface DemoAccountStrategyLane extends DemoAccountBinding {
  strategies: string[];
  primaryStrategy: string | null;
}

function uniqueNonEmpty(values: string[]): string[] {
  const seen = new Set<string>();
  const normalized: string[] = [];

  for (const value of values) {
    const trimmed = value.trim();
    if (!trimmed || seen.has(trimmed)) {
      continue;
    }
    seen.add(trimmed);
    normalized.push(trimmed);
  }

  return normalized;
}

export function listAllowedDemoAccounts(config: LiveAdapterConfig): DemoAccountBinding[] {
  const ids = uniqueNonEmpty([
    ...(config.allowedAccountIds ?? []),
    ...(config.allowedAccountId ? [config.allowedAccountId] : [])
  ]);
  const labels = [
    ...(config.allowedAccountLabels ?? []),
    ...(config.allowedAccountLabel ? [config.allowedAccountLabel] : [])
  ]
    .map((value) => value.trim())
    .filter(Boolean);

  return ids.map((accountId, index) => ({
    accountId,
    label: labels[index] ?? (ids.length === 1 ? (config.allowedAccountLabel ?? null) : null),
    slot: index + 1,
    selected: config.accountId === accountId
  }));
}

export function isDemoAccountLockSatisfied(config: LiveAdapterConfig): boolean {
  if (!config.demoOnly) {
    return true;
  }

  const accounts = listAllowedDemoAccounts(config);
  if (accounts.length === 0) {
    return false;
  }

  return !config.accountId || accounts.some((account) => account.accountId === config.accountId);
}

export function buildDemoAccountStrategyLanes(args: {
  config: LiveAdapterConfig;
  enabledStrategies: string[];
}): DemoAccountStrategyLane[] {
  const accounts = listAllowedDemoAccounts(args.config);
  const strategies = uniqueNonEmpty(args.enabledStrategies);

  if (accounts.length === 0) {
    return [];
  }

  return accounts.map((account, index) => {
    const assigned = strategies.filter((_, strategyIndex) => strategyIndex % accounts.length === index);
    const fallback = strategies[index % Math.max(strategies.length, 1)];
    const laneStrategies = assigned.length > 0
      ? assigned
      : (fallback ? [fallback] : []);

    return {
      ...account,
      strategies: laneStrategies,
      primaryStrategy: laneStrategies[0] ?? null
    };
  });
}
