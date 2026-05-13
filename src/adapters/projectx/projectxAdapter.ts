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
  limitPrice: number | null;
  stopPrice: number | null;
  trailPrice: number | null;
  customTag: string;
  stopLossBracket?: {
    ticks: number;
    type: number;
  };
  takeProfitBracket?: {
    ticks: number;
    type: number;
  };
}

export interface ProjectXDemoAccountPreflightLane {
  configuredAccountId: string;
  configuredLabel: string | null;
  matchedAccountId: string | null;
  matchedAccountName: string | null;
  canTrade: boolean | null;
  isVisible: boolean | null;
  simulated: boolean | null;
  status: "ok" | "blocked";
  blockers: string[];
}

export interface ProjectXDemoAccountPreflightReport {
  ok: boolean;
  enabled: boolean;
  demoOnly: boolean;
  readOnly: boolean;
  allowedAccountCount: number;
  discoveredAccountCount: number;
  lanes: ProjectXDemoAccountPreflightLane[];
  blockers: string[];
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

function credentialBlockers(config: LiveAdapterConfig): string[] {
  return [
    ...(config.baseUrl ? [] : ["RH_TOPSTEP_BASE_URL is blank."]),
    ...(config.username ? [] : ["RH_TOPSTEP_USERNAME is blank."]),
    ...(config.apiKey ? [] : ["RH_TOPSTEP_API_KEY is blank."])
  ];
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

function bracketTicks(value: number): number {
  return Math.max(1, Math.round(value));
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
  const request: ProjectXPlaceOrderRequest = {
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
      ticks: bracketTicks(args.spec.stopDistanceTicks),
      type: ORDER_TYPE.stop
    },
    takeProfitBracket: {
      ticks: bracketTicks(args.spec.targetDistanceTicks),
      type: ORDER_TYPE.limit
    }
  };
  return request;
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
  private nextBatchId: number = Date.now();

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

  /** Generate a unique batch ID for correlating entry/SL/TP orders. */
  private generateBatchTag(baseTag: string): string {
    this.nextBatchId += 1;
    return `bt${this.nextBatchId}-${baseTag}`;
  }

  /** Cancel any ACTIVE orders whose customTag starts with the given prefix. */
  private async cancelOrdersByTagPrefix(
    token: string,
    accountId: number,
    contractId: string,
    tagPrefix: string,
    excludeOrderId?: number
  ): Promise<number> {
    try {
      const baseUrl = normalizeBaseUrl(this.config.baseUrl!);
      const response = await this.fetchImpl(`${baseUrl}/api/Order/search`, {
        method: "POST",
        headers: { "content-type": "application/json", accept: "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ accountId, startTimestamp: new Date(0).toISOString() })
      });
      if (!response.ok) return 0;
      const data: any = await response.json();
      const orders: any[] = data.orders ?? [];
      const siblings = orders.filter(
        (o: any) =>
          o.status === 1 && // ACTIVE
          o.contractId === contractId &&
          o.customTag?.startsWith(tagPrefix) &&
          (excludeOrderId == null || o.id !== excludeOrderId)
      );
      let cancelled = 0;
      for (const sib of siblings) {
        try {
          const cancelRes = await this.fetchImpl(`${baseUrl}/api/Order/cancel`, {
            method: "POST",
            headers: { "content-type": "application/json", accept: "application/json", Authorization: `Bearer ${token}` },
            body: JSON.stringify({ accountId, orderId: sib.id })
          });
          if (cancelRes.ok) cancelled++;
        } catch {
          // non-fatal
        }
      }
      return cancelled;
    } catch {
      return 0;
    }
  }

  private assertReady(): void {
    if (!this.config.enabled) {
      throw new Error("ProjectX live execution is disabled.");
    }

    if (!this.config.accountId) {
      throw new Error("ProjectX live adapter is missing RH_TOPSTEP_ACCOUNT_ID for this lane.");
    }

    const missingCredentials = credentialBlockers(this.config);
    if (missingCredentials.length > 0) {
      throw new Error(`ProjectX live adapter is missing required credentials: ${missingCredentials.join(" ")}`);
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

  private async searchAccounts(onlyActiveAccounts = true): Promise<ProjectXAccount[]> {
    const token = await this.authenticate();
    const payload = await postGateway<ProjectXAccount[]>({
      fetchImpl: this.fetchImpl,
      baseUrl: this.config.baseUrl!,
      path: "/api/Account/search",
      token,
      body: {
        onlyActiveAccounts
      },
      action: "account search"
    });
    assertGatewaySuccess(payload, "account search");
    return payload.accounts ?? [];
  }

  public async preflightDemoAccounts(): Promise<ProjectXDemoAccountPreflightReport> {
    const allowedAccounts = listAllowedDemoAccounts(this.config);
    const blockers = [
      ...credentialBlockers(this.config),
      ...(this.config.enabled ? [] : ["RH_LIVE_EXECUTION_ENABLED is not true."]),
      ...(this.config.demoOnly ? [] : ["RH_TOPSTEP_DEMO_ONLY must remain true for demo routing."]),
      ...(allowedAccounts.length > 0 ? [] : ["RH_TOPSTEP_ALLOWED_ACCOUNT_ID or RH_TOPSTEP_ALLOWED_ACCOUNT_IDS is required."]),
      ...(isDemoAccountLockSatisfied(this.config) ? [] : ["Configured ProjectX account does not match the demo-only allowed account set."])
    ];

    if (credentialBlockers(this.config).length > 0) {
      return {
        ok: false,
        enabled: this.config.enabled,
        demoOnly: this.config.demoOnly,
        readOnly: this.config.readOnly,
        allowedAccountCount: allowedAccounts.length,
        discoveredAccountCount: 0,
        lanes: [],
        blockers
      };
    }

    const accounts = await this.searchAccounts(true);
    const allAccounts = await this.searchAccounts(false).catch(() => accounts);
    const lanes = allowedAccounts.map((allowed): ProjectXDemoAccountPreflightLane => {
      let matched: ProjectXAccount | null = null;
      const laneBlockers: string[] = [];

      try {
        matched = resolveConfiguredAccount({
          configuredAccountId: allowed.accountId,
          configuredAccountLabel: allowed.label ?? undefined,
          accounts
        });
      } catch {
        const inactiveMatch = allAccounts.find((account) => matchesConfiguredAccount({
          configuredAccountId: allowed.accountId,
          configuredAccountLabel: allowed.label ?? undefined,
          account
        })) ?? null;

        if (inactiveMatch) {
          matched = inactiveMatch;
          laneBlockers.push(`Allowed account ${allowed.accountId} is present but not active/tradable in Account/search.`);
        } else {
          laneBlockers.push(`Allowed account ${allowed.accountId} was not returned by Account/search.`);
        }
      }

      if (matched) {
        if (this.config.demoOnly && matched.simulated !== true) {
          laneBlockers.push(`Matched account ${matched.name} (${matched.id}) is not marked simulated.`);
        }
        if (!matched.canTrade) {
          laneBlockers.push(`Matched account ${matched.name} (${matched.id}) cannot trade.`);
        }
        if (!matched.isVisible) {
          laneBlockers.push(`Matched account ${matched.name} (${matched.id}) is not visible.`);
        }
      }

      return {
        configuredAccountId: allowed.accountId,
        configuredLabel: allowed.label,
        matchedAccountId: matched ? String(matched.id) : null,
        matchedAccountName: matched?.name ?? null,
        canTrade: matched?.canTrade ?? null,
        isVisible: matched?.isVisible ?? null,
        simulated: matched?.simulated ?? null,
        status: laneBlockers.length === 0 ? "ok" : "blocked",
        blockers: laneBlockers
      };
    });
    const laneBlockers = lanes.flatMap((lane) => lane.blockers);
    const allBlockers = [...blockers, ...laneBlockers];

    return {
      ok: allBlockers.length === 0,
      enabled: this.config.enabled,
      demoOnly: this.config.demoOnly,
      readOnly: this.config.readOnly,
      allowedAccountCount: allowedAccounts.length,
      discoveredAccountCount: accounts.length,
      lanes,
      blockers: allBlockers
    };
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
    const token = await this.authenticate();
    const batchTag = this.generateBatchTag(spec.strategyTag);

    // Before placing new orders, cancel stale sibling orders from previous batches
    this.cancelOrdersByTagPrefix(token, account.id, contract.id, `bt`).catch(() => {});

    if (spec.stopDistanceTicks <= 0 || spec.stopPrice <= 0) {
      throw new Error("ProjectX refused to route: every market entry requires a valid protective stop before submit.");
    }

    // Step 1: Submit market entry order (this account uses Position Brackets, not Auto OCO)
    const entryRequest: ProjectXPlaceOrderRequest = {
      accountId: account.id,
      contractId: contract.id,
      type: ORDER_TYPE.market,
      side: spec.side === "buy" ? ORDER_SIDE.buy : ORDER_SIDE.sell,
      size: spec.contracts,
      limitPrice: null,
      stopPrice: null,
      trailPrice: null,
      customTag: `${batchTag}-entry`
    };

    const entryPayload = await postGateway<never>({
      fetchImpl: this.fetchImpl,
      baseUrl: this.config.baseUrl!,
      path: "/api/Order/place",
      token,
      body: entryRequest,
      action: "market entry order"
    });
    assertGatewaySuccess(entryPayload, "market entry order");

    const orderIds: string[] = [String(entryPayload.orderId ?? "unknown")];

    // Step 2: Submit stop-loss as separate order. If this fails, fail closed and flatten.
    const stopRequest = {
      accountId: account.id,
      contractId: contract.id,
      type: ORDER_TYPE.stop,
      side: spec.side === "buy" ? ORDER_SIDE.sell : ORDER_SIDE.buy,
      size: spec.contracts,
      limitPrice: null,
      stopPrice: spec.stopPrice,
      trailPrice: null,
      customTag: `${batchTag}-SL`
    };
    try {
      const stopPayload = await postGateway<never>({
        fetchImpl: this.fetchImpl,
        baseUrl: this.config.baseUrl!,
        path: "/api/Order/place",
        token,
        body: stopRequest,
        action: "stop-loss order"
      });
      assertGatewaySuccess(stopPayload, "stop-loss order");
      if (stopPayload.orderId == null) {
        throw new Error("ProjectX stop-loss order did not return an order id.");
      }
      orderIds.push(`sl:${stopPayload.orderId}`);
    } catch (error) {
      const flattenError = await this.flattenAll()
        .then(() => null)
        .catch((flattenFailure: unknown) => flattenFailure);
      throw new Error([
        `ProjectX protective stop failed after entry ${orderIds[0]}; fail-closed flatten attempted.`,
        `stopError=${error instanceof Error ? error.message : String(error)}`,
        ...(flattenError ? [`flattenError=${flattenError instanceof Error ? flattenError.message : String(flattenError)}`] : ["flattenStatus=attempted"])
      ].join(" "));
    }

    // Step 3: Submit take-profit as separate order
    if (spec.targetDistanceTicks > 0 && spec.targetPrice > 0) {
      const tpRequest = {
        accountId: account.id,
        contractId: contract.id,
        type: ORDER_TYPE.limit,
        side: spec.side === "buy" ? ORDER_SIDE.sell : ORDER_SIDE.buy,
        size: spec.contracts,
        limitPrice: spec.targetPrice,
        stopPrice: null,
        trailPrice: null,
        customTag: `${batchTag}-TP`
      };
      try {
        const tpPayload = await postGateway<never>({
          fetchImpl: this.fetchImpl,
          baseUrl: this.config.baseUrl!,
          path: "/api/Order/place",
          token,
          body: tpRequest,
          action: "take-profit order"
        });
        if (tpPayload.success) orderIds.push(`tp:${tpPayload.orderId}`);
      } catch {
        // TP failure is non-fatal
      }
    }

    return {
      accepted: true,
      orderId: orderIds.join(","),
      message: `ProjectX filled ${signal.strategyId} ${signal.side} ${signal.symbol} ${spec.contracts}ct @ market on ${account.name}. Entry:${orderIds[0]}${spec.stopPrice > 0 ? ` SL:${spec.stopPrice}` : ""}${spec.targetPrice > 0 ? ` TP:${spec.targetPrice}` : ""}`
    };
  }

  /**
   * Cancel sibling orders (SL/TP) for a given batch after one leg fills.
   * Call this from the demo execution pipeline when it detects a fill.
   */
  public async cleanupAfterFill(token: string, accountId: number, contractId: string, batchTag: string, filledOrderId: number): Promise<number> {
    return this.cancelOrdersByTagPrefix(token, accountId, contractId, batchTag, filledOrderId);
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
