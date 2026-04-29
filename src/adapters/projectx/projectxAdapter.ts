import type { LiveAdapterConfig, StrategySignal } from "../../domain.js";
import { HARD_GUARDRAIL_BOUNDS } from "../../risk/guardrails.js";
import { pointsToTicks, ticksToDollars } from "../../utils/markets.js";
import type { ExecutionAdapter, ExecutionReceipt } from "../topstep/topstepAdapter.js";
import { isDemoAccountLockSatisfied, listAllowedDemoAccounts } from "../../live/demoAccounts.js";
import { resolveProjectXApiBaseUrl } from "./baseUrl.js";

const ORDER_SIDE = {
  buy: 0,
  sell: 1
} as const;

const ORDER_TYPE = {
  limit: 1,
  market: 2,
  stop: 4
} as const;

type FetchLike = typeof fetch;

interface ProjectXEnvelope<T> {
  success: boolean;
  errorCode?: number | null;
  errorMessage?: string | null;
  token?: string;
  accounts?: ProjectXAccount[];
  contracts?: ProjectXContract[];
  positions?: ProjectXPosition[];
  orderId?: number;
  newToken?: string;
}

interface ProjectXAccount {
  id: number;
  name: string;
  canTrade: boolean;
  isVisible: boolean;
  simulated?: boolean;
}

interface ProjectXContract {
  id: string;
  name: string;
  description?: string;
  tickSize: number;
  tickValue?: number;
  activeContract?: boolean;
  symbolId?: string;
}

interface ProjectXPosition {
  contractId: string;
}

export interface ProjectXOrderSpec {
  accountId: string;
  symbol: string;
  side: "buy" | "sell";
  contracts: number;
  limitPrice: number;
  stopPrice: number;
  targetPrice: number;
  stopDistanceTicks: number;
  stopDistanceDollars: number;
  targetDistanceTicks: number;
  strategyTag: string;
}

export interface ProjectXPlaceOrderRequest {
  accountId: number;
  contractId: string;
  type: number;
  side: number;
  size: number;
  limitPrice: null;
  stopPrice: null;
  trailPrice: null;
  customTag: string;
  stopLossBracket: {
    ticks: number;
    type: number;
  };
  takeProfitBracket: {
    ticks: number;
    type: number;
  };
}

function assertDemoOnlyAccountLock(config: LiveAdapterConfig): void {
  if (!config.demoOnly) {
    return;
  }

  if (listAllowedDemoAccounts(config).length === 0) {
    throw new Error("ProjectX live adapter requires RH_TOPSTEP_ALLOWED_ACCOUNT_ID or RH_TOPSTEP_ALLOWED_ACCOUNT_IDS when demo-only mode is enabled.");
  }

  if (!isDemoAccountLockSatisfied(config)) {
    throw new Error("Configured ProjectX account does not match the demo-only allowed account set.");
  }
}

function normalizeBaseUrl(baseUrl: string): string {
  return resolveProjectXApiBaseUrl(baseUrl)?.replace(/\/$/, "") ?? baseUrl.replace(/\/$/, "");
}

function assertGatewaySuccess<T>(payload: ProjectXEnvelope<T> | null | undefined, action: string): asserts payload is ProjectXEnvelope<T> {
  if (!payload) {
    throw new Error(`ProjectX ${action} returned an empty response.`);
  }

  if (!payload.success) {
    throw new Error(
      `ProjectX ${action} failed${payload.errorCode != null ? ` (${payload.errorCode})` : ""}${payload.errorMessage ? `: ${payload.errorMessage}` : "."}`
    );
  }
}

async function parseJson<T>(response: Response, action: string): Promise<ProjectXEnvelope<T>> {
  if (!response.ok) {
    throw new Error(`ProjectX ${action} failed with HTTP ${response.status}.`);
  }

  return response.json() as Promise<ProjectXEnvelope<T>>;
}

async function postGateway<T>(args: {
  fetchImpl: FetchLike;
  baseUrl: string;
  path: string;
  body: unknown;
  token?: string;
  action: string;
}): Promise<ProjectXEnvelope<T>> {
  const response = await args.fetchImpl(`${normalizeBaseUrl(args.baseUrl)}${args.path}`, {
    method: "POST",
    headers: {
      accept: "application/json",
      "content-type": "application/json",
      ...(args.token ? { Authorization: `Bearer ${args.token}` } : {})
    },
    body: JSON.stringify(args.body)
  });

  return parseJson<T>(response, args.action);
}

function resolveContractForSymbol(args: {
  contracts: ProjectXContract[];
  symbol: string;
}): ProjectXContract {
  const normalizedSymbol = args.symbol.trim().toUpperCase();
  const active = args.contracts.filter((contract) => contract.activeContract !== false);
  const direct = active.find((contract) => contract.name.toUpperCase().startsWith(normalizedSymbol));
  if (direct) {
    return direct;
  }

  const loose = active.find((contract) =>
    contract.symbolId?.toUpperCase().endsWith(`.${normalizedSymbol}`)
    || contract.description?.toUpperCase().includes(normalizedSymbol)
  );
  if (loose) {
    return loose;
  }

  throw new Error(`ProjectX could not resolve an active contract for symbol ${normalizedSymbol}.`);
}

function buildCustomTag(signal: StrategySignal, now: Date): string {
  const compactStrategy = signal.strategyId.replace(/[^a-z0-9]+/gi, "-").slice(0, 40);
  return `${compactStrategy}-${signal.symbol}-${now.toISOString().replace(/[:.]/g, "")}`;
}

export function buildProjectXOrderSpec(args: {
  signal: StrategySignal;
  accountId: string;
}): ProjectXOrderSpec {
  const { signal, accountId } = args;
  if (!Number.isInteger(signal.contracts) || signal.contracts <= 0) {
    throw new Error(`ProjectX order spec has invalid contracts: ${signal.contracts}`);
  }

  if (signal.contracts > HARD_GUARDRAIL_BOUNDS.maxContracts) {
    throw new Error(`ProjectX order spec breaches hard max contracts: ${signal.contracts}`);
  }

  const stopDistancePoints = Math.max(0.000001, Math.abs(signal.entry - signal.stop));
  const stopDistanceTicks = pointsToTicks(signal.symbol, stopDistancePoints);
  const stopDistanceDollars = ticksToDollars(signal.symbol, stopDistanceTicks, signal.contracts);
  const targetDistancePoints = Math.max(0.000001, Math.abs(signal.target - signal.entry));
  const targetDistanceTicks = pointsToTicks(signal.symbol, targetDistancePoints);

  return {
    accountId,
    symbol: signal.symbol,
    side: signal.side === "long" ? "buy" : "sell",
    contracts: signal.contracts,
    limitPrice: signal.entry,
    stopPrice: signal.stop,
    targetPrice: signal.target,
    stopDistanceTicks: Number(stopDistanceTicks.toFixed(4)),
    stopDistanceDollars: Number(stopDistanceDollars.toFixed(2)),
    targetDistanceTicks: Number(targetDistanceTicks.toFixed(4)),
    strategyTag: signal.strategyId
  };
}

export function buildProjectXPlaceOrderRequest(args: {
  spec: ProjectXOrderSpec;
  resolvedAccountId: number;
  contractId: string;
  now?: Date;
}): ProjectXPlaceOrderRequest {
  const now = args.now ?? new Date();
  return {
    accountId: args.resolvedAccountId,
    contractId: args.contractId,
    type: ORDER_TYPE.market,
    side: args.spec.side === "buy" ? ORDER_SIDE.buy : ORDER_SIDE.sell,
    size: args.spec.contracts,
    limitPrice: null,
    stopPrice: null,
    trailPrice: null,
    customTag: buildCustomTag({
      symbol: args.spec.symbol,
      strategyId: args.spec.strategyTag,
      side: args.spec.side === "buy" ? "long" : "short",
      entry: args.spec.limitPrice,
      stop: args.spec.stopPrice,
      target: args.spec.targetPrice,
      rr: 0,
      confidence: 0,
      contracts: args.spec.contracts,
      maxHoldMinutes: 0
    }, now),
    stopLossBracket: {
      ticks: Math.max(1, Math.round(args.spec.stopDistanceTicks)),
      type: ORDER_TYPE.stop
    },
    takeProfitBracket: {
      ticks: Math.max(1, Math.round(args.spec.targetDistanceTicks)),
      type: ORDER_TYPE.limit
    }
  };
}

function matchesConfiguredAccount(args: {
  configuredAccountId?: string;
  configuredAccountLabel?: string;
  account: ProjectXAccount;
}): boolean {
  const configured = [args.configuredAccountId, args.configuredAccountLabel]
    .map((value) => value?.trim().toLowerCase())
    .filter((value): value is string => Boolean(value));

  if (configured.length === 0) {
    return false;
  }

  const accountId = String(args.account.id).trim().toLowerCase();
  const accountName = String(args.account.name ?? "").trim().toLowerCase();
  return configured.some((value) => value === accountId || value === accountName);
}

function resolveConfiguredAccount(args: {
  configuredAccountId?: string;
  configuredAccountLabel?: string;
  accounts: ProjectXAccount[];
}): ProjectXAccount {
  const match = args.accounts.find((account) => matchesConfiguredAccount({
    configuredAccountId: args.configuredAccountId,
    configuredAccountLabel: args.configuredAccountLabel,
    account
  }));

  if (!match) {
    throw new Error(
      `ProjectX could not match configured account ${args.configuredAccountId ?? args.configuredAccountLabel ?? "blank"} against Account/search results.`
    );
  }

  return match;
}

function assertDemoOnlyAccountIsSimulated(config: LiveAdapterConfig, account: ProjectXAccount): void {
  if (!config.demoOnly) {
    return;
  }

  if (account.simulated !== true) {
    throw new Error(`ProjectX demo-only routing refused account ${account.name} (${account.id}) because Account/search did not mark it as simulated.`);
  }
}

export class ProjectXLiveAdapter implements ExecutionAdapter {
  private token: string | null = null;

  public constructor(
    private readonly config: LiveAdapterConfig,
    private readonly deps: {
      fetchImpl?: FetchLike;
      now?: () => Date;
    } = {}
  ) {}

  private get fetchImpl(): FetchLike {
    return this.deps.fetchImpl ?? fetch;
  }

  private get now(): () => Date {
    return this.deps.now ?? (() => new Date());
  }

  private assertReady(): void {
    if (!this.config.enabled) {
      throw new Error("ProjectX live execution is disabled.");
    }

    if (!this.config.baseUrl || !this.config.username || !this.config.accountId || !this.config.apiKey) {
      throw new Error("ProjectX live adapter is missing required credentials.");
    }

    assertDemoOnlyAccountLock(this.config);
  }

  private async authenticate(): Promise<string> {
    if (this.token) {
      return this.token;
    }

    const payload = await postGateway<never>({
      fetchImpl: this.fetchImpl,
      baseUrl: this.config.baseUrl!,
      path: "/api/Auth/loginKey",
      body: {
        userName: this.config.username,
        apiKey: this.config.apiKey
      },
      action: "authentication"
    });
    assertGatewaySuccess(payload, "authentication");

    if (!payload.token) {
      throw new Error("ProjectX authentication succeeded but no session token was returned.");
    }

    this.token = payload.token;
    return payload.token;
  }

  private async searchAccounts(): Promise<ProjectXAccount[]> {
    const token = await this.authenticate();
    const payload = await postGateway<ProjectXAccount[]>({
      fetchImpl: this.fetchImpl,
      baseUrl: this.config.baseUrl!,
      path: "/api/Account/search",
      token,
      body: {
        onlyActiveAccounts: true
      },
      action: "account search"
    });
    assertGatewaySuccess(payload, "account search");
    return payload.accounts ?? [];
  }

  private async listContracts(): Promise<ProjectXContract[]> {
    const token = await this.authenticate();
    const payload = await postGateway<ProjectXContract[]>({
      fetchImpl: this.fetchImpl,
      baseUrl: this.config.baseUrl!,
      path: "/api/Contract/available",
      token,
      body: {
        live: false
      },
      action: "contract discovery"
    });
    assertGatewaySuccess(payload, "contract discovery");
    return payload.contracts ?? [];
  }

  public async submit(signal: StrategySignal): Promise<ExecutionReceipt> {
    this.assertReady();
    if (this.config.readOnly) {
      throw new Error("ProjectX live adapter is in read-only mode. Keep RH_TOPSTEP_READ_ONLY=true until the demo shadow loop is approved.");
    }

    const accounts = await this.searchAccounts();
    const account = resolveConfiguredAccount({
      configuredAccountId: this.config.accountId,
      configuredAccountLabel: this.config.allowedAccountLabel,
      accounts
    });
    assertDemoOnlyAccountIsSimulated(this.config, account);
    if (!account.canTrade) {
      throw new Error(`ProjectX account ${account.name} (${account.id}) cannot trade right now.`);
    }

    const spec = buildProjectXOrderSpec({
      signal,
      accountId: this.config.accountId!
    });
    const contract = resolveContractForSymbol({
      contracts: await this.listContracts(),
      symbol: signal.symbol
    });
    const request = buildProjectXPlaceOrderRequest({
      spec,
      resolvedAccountId: account.id,
      contractId: contract.id,
      now: this.now()
    });
    const token = await this.authenticate();
    const payload = await postGateway<never>({
      fetchImpl: this.fetchImpl,
      baseUrl: this.config.baseUrl!,
      path: "/api/Order/place",
      token,
      body: request,
      action: "order placement"
    });
    assertGatewaySuccess(payload, "order placement");

    return {
      accepted: true,
      orderId: String(payload.orderId ?? "unknown"),
      message: `ProjectX accepted ${signal.strategyId} ${signal.side} ${signal.symbol} on account ${account.name}.`
    };
  }

  public async flattenAll(): Promise<void> {
    this.assertReady();
    if (this.config.readOnly) {
      throw new Error("ProjectX live adapter is in read-only mode. Keep RH_TOPSTEP_READ_ONLY=true until the demo shadow loop is approved.");
    }

    const token = await this.authenticate();
    const account = resolveConfiguredAccount({
      configuredAccountId: this.config.accountId,
      configuredAccountLabel: this.config.allowedAccountLabel,
      accounts: await this.searchAccounts()
    });
    assertDemoOnlyAccountIsSimulated(this.config, account);
    const payload = await postGateway<ProjectXPosition[]>({
      fetchImpl: this.fetchImpl,
      baseUrl: this.config.baseUrl!,
      path: "/api/Position/searchOpen",
      token,
      body: {
        accountId: account.id
      },
      action: "open position search"
    });
    assertGatewaySuccess(payload, "open position search");

    for (const position of payload.positions ?? []) {
      const closePayload = await postGateway<never>({
        fetchImpl: this.fetchImpl,
        baseUrl: this.config.baseUrl!,
        path: "/api/Position/closeContract",
        token,
        body: {
          accountId: account.id,
          contractId: position.contractId
        },
        action: "position close"
      });
      assertGatewaySuccess(closePayload, "position close");
    }
  }
}
