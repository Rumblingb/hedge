import { tmpdir } from "node:os";
import { join } from "node:path";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  buildProjectXOrderSpec,
  buildProjectXPlaceOrderRequest,
  ProjectXLiveAdapter
} from "../src/adapters/projectx/projectxAdapter.js";
import type { StrategySignal } from "../src/domain.js";

// Keep tests off the machine-wide shared token cache so every run exercises
// the mocked loginKey path deterministically. Fresh path per test so a token
// written by one test never leaks into the next.
let tokenCacheCounter = 0;
beforeEach(() => {
  tokenCacheCounter += 1;
  process.env.RH_TOPSTEP_TOKEN_CACHE_PATH = join(
    tmpdir(),
    `projectx-test-token-${process.pid}-${tokenCacheCounter}.json`
  );
});

function jsonResponse(payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: {
      "content-type": "application/json"
    }
  });
}

describe("ProjectXLiveAdapter", () => {
  it("builds a market request with protective brackets", () => {
    const signal: StrategySignal = {
      symbol: "NQ",
      strategyId: "wctc-ensemble:session-momentum",
      side: "long",
      entry: 18250,
      stop: 18240,
      target: 18280,
      rr: 3,
      confidence: 0.8,
      contracts: 1,
      maxHoldMinutes: 20
    };

    const spec = buildProjectXOrderSpec({
      signal,
      accountId: "465"
    });
    const request = buildProjectXPlaceOrderRequest({
      spec,
      resolvedAccountId: 465,
      contractId: "CON.F.US.ENQ.U26",
      now: new Date("2026-04-18T10:00:00.000Z")
    });

    expect(request.type).toBe(2);
    expect(request.side).toBe(0);
    const stopLossBracket = request.stopLossBracket;
    const takeProfitBracket = request.takeProfitBracket;
    expect(stopLossBracket).toBeDefined();
    expect(takeProfitBracket).toBeDefined();
    if (!stopLossBracket || !takeProfitBracket) throw new Error("expected protective brackets");
    expect(stopLossBracket.ticks).toBeLessThan(0);
    expect(takeProfitBracket.ticks).toBeGreaterThan(stopLossBracket.ticks);
    expect(request.customTag).toContain("wctc-ensemble-session-momentum");
  });

  it("uses signed TopstepX OCO bracket ticks by side", () => {
    const longSpec = buildProjectXOrderSpec({
      accountId: "465",
      signal: {
        symbol: "NQ",
        strategyId: "oco-sign-test",
        side: "long",
        entry: 18250,
        stop: 18240,
        target: 18280,
        rr: 3,
        confidence: 0.8,
        contracts: 1,
        maxHoldMinutes: 20
      }
    });
    const shortSpec = buildProjectXOrderSpec({
      accountId: "465",
      signal: {
        symbol: "NQ",
        strategyId: "oco-sign-test",
        side: "short",
        entry: 18250,
        stop: 18260,
        target: 18220,
        rr: 3,
        confidence: 0.8,
        contracts: 1,
        maxHoldMinutes: 20
      }
    });

    const longRequest = buildProjectXPlaceOrderRequest({
      spec: longSpec,
      resolvedAccountId: 465,
      contractId: "CON.F.US.ENQ.U26"
    });
    const shortRequest = buildProjectXPlaceOrderRequest({
      spec: shortSpec,
      resolvedAccountId: 465,
      contractId: "CON.F.US.ENQ.U26"
    });

    expect(longRequest.stopLossBracket).toEqual({ ticks: -40, type: 4 });
    expect(longRequest.takeProfitBracket).toEqual({ ticks: 120, type: 1 });
    expect(shortRequest.stopLossBracket).toEqual({ ticks: 40, type: 4 });
    expect(shortRequest.takeProfitBracket).toEqual({ ticks: -120, type: 1 });
  });

  it("authenticates, resolves the contract, and places one guarded bracket demo order", async () => {
    const signal: StrategySignal = {
      symbol: "NQ",
      strategyId: "wctc-ensemble:session-momentum",
      side: "long",
      entry: 18250,
      stop: 18240,
      target: 18280,
      rr: 3,
      confidence: 0.8,
      contracts: 1,
      maxHoldMinutes: 20
    };

    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({
        token: "session-token",
        success: true,
        errorCode: 0,
        errorMessage: null
      }))
      .mockResolvedValueOnce(jsonResponse({
        accounts: [
          {
            id: 465,
            name: "50KTC-V2-507159-22968721",
            canTrade: true,
            isVisible: true,
            simulated: true
          }
        ],
        success: true,
        errorCode: 0,
        errorMessage: null
      }))
      .mockResolvedValueOnce(jsonResponse({
        contracts: [
          {
            id: "CON.F.US.ENQ.U26",
            name: "NQU6",
            tickSize: 0.25,
            tickValue: 5,
            activeContract: true,
            symbolId: "F.US.ENQ"
          }
        ],
        success: true,
        errorCode: 0,
        errorMessage: null
      }))
      .mockResolvedValueOnce(jsonResponse({
        orders: [],
        success: true,
        errorCode: 0,
        errorMessage: null
      }))
      .mockResolvedValueOnce(jsonResponse({
        orderId: 9056,
        success: true,
        errorCode: 0,
        errorMessage: null
      }));

    const adapter = new ProjectXLiveAdapter({
      enabled: true,
      baseUrl: "https://api.example.com",
      username: "demo-user",
      accountId: "50KTC-V2-507159-22968721",
      allowedAccountIds: ["50KTC-V2-507159-22968721"],
      apiKey: "secret",
      demoOnly: true,
      readOnly: false
    }, {
      fetchImpl: fetchMock as unknown as typeof fetch,
      now: () => new Date("2026-04-18T10:00:00.000Z")
    });

    const receipt = await adapter.submit(signal);

    expect(receipt.accepted).toBe(true);
    expect(receipt.orderId).toBe("9056");
    expect(fetchMock).toHaveBeenCalledTimes(5);

    expect(String(fetchMock.mock.calls[3]?.[0])).toContain("/api/Order/search");
    expect(String(fetchMock.mock.calls[4]?.[0])).toContain("/api/Order/place");
    const placeOrderInit = fetchMock.mock.calls[4]?.[1] as RequestInit | undefined;
    const placeOrderBody = JSON.parse(String(placeOrderInit?.body));
    expect(placeOrderBody.accountId).toBe(465);
    expect(placeOrderBody.contractId).toBe("CON.F.US.ENQ.U26");
    expect(placeOrderBody.side).toBe(0);
    expect(placeOrderBody.type).toBe(2);
    expect(placeOrderBody.stopLossBracket).toEqual({ ticks: -40, type: 4 });
    expect(placeOrderBody.takeProfitBracket).toEqual({ ticks: 120, type: 1 });
    expect(placeOrderBody.customTag).toContain("entry-oco");
  });

  it("fails closed without creating a separate naked entry if the bracket order is rejected", async () => {
    const signal: StrategySignal = {
      symbol: "NQ",
      strategyId: "ret-30-momentum",
      side: "long",
      entry: 18250,
      stop: 18240,
      target: 18280,
      rr: 3,
      confidence: 0.8,
      contracts: 1,
      maxHoldMinutes: 20
    };

    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({
        token: "session-token",
        success: true,
        errorCode: 0,
        errorMessage: null
      }))
      .mockResolvedValueOnce(jsonResponse({
        accounts: [{ id: 465, name: "50KTC-V2-507159-22968721", canTrade: true, isVisible: true, simulated: true }],
        success: true,
        errorCode: 0,
        errorMessage: null
      }))
      .mockResolvedValueOnce(jsonResponse({
        contracts: [{ id: "CON.F.US.ENQ.U26", name: "NQU6", tickSize: 0.25, tickValue: 5, activeContract: true, symbolId: "F.US.ENQ" }],
        success: true,
        errorCode: 0,
        errorMessage: null
      }))
      .mockResolvedValueOnce(jsonResponse({ orders: [], success: true, errorCode: 0, errorMessage: null }))
      .mockResolvedValueOnce(jsonResponse({ success: false, errorCode: 500, errorMessage: "bracket rejected" }));

    const adapter = new ProjectXLiveAdapter({
      enabled: true,
      baseUrl: "https://api.example.com",
      username: "demo-user",
      accountId: "50KTC-V2-507159-22968721",
      allowedAccountIds: ["50KTC-V2-507159-22968721"],
      apiKey: "secret",
      demoOnly: true,
      readOnly: false
    }, {
      fetchImpl: fetchMock as unknown as typeof fetch,
      now: () => new Date("2026-04-18T10:00:00.000Z")
    });

    await expect(adapter.submit(signal)).rejects.toThrow(/market entry order with protective brackets failed/);
    const flattenedCall = fetchMock.mock.calls.find((call) => String(call[0]).includes("/api/Position/closeContract"));
    expect(flattenedCall).toBeUndefined();
    expect(fetchMock).toHaveBeenCalledTimes(5);
  });

  it("refuses demo-only routing when the matched account is not marked simulated", async () => {
    const signal: StrategySignal = {
      symbol: "NQ",
      strategyId: "wctc-ensemble:session-momentum",
      side: "long",
      entry: 18250,
      stop: 18240,
      target: 18280,
      rr: 3,
      confidence: 0.8,
      contracts: 1,
      maxHoldMinutes: 20
    };

    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({
        token: "session-token",
        success: true,
        errorCode: 0,
        errorMessage: null
      }))
      .mockResolvedValueOnce(jsonResponse({
        accounts: [
          {
            id: 465,
            name: "50KTC-V2-507159-22968721",
            canTrade: true,
            isVisible: true,
            simulated: false
          }
        ],
        success: true,
        errorCode: 0,
        errorMessage: null
      }));

    const adapter = new ProjectXLiveAdapter({
      enabled: true,
      baseUrl: "https://api.example.com",
      username: "demo-user",
      accountId: "50KTC-V2-507159-22968721",
      allowedAccountIds: ["50KTC-V2-507159-22968721"],
      apiKey: "secret",
      demoOnly: true,
      readOnly: false
    }, {
      fetchImpl: fetchMock as unknown as typeof fetch
    });

    await expect(adapter.submit(signal)).rejects.toThrow(/did not mark it as simulated/);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("preflights all allowed demo accounts without placing orders", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({
        token: "session-token",
        success: true,
        errorCode: 0,
        errorMessage: null
      }))
      .mockResolvedValueOnce(jsonResponse({
        accounts: [
          {
            id: 1,
            name: "acct-1",
            canTrade: true,
            isVisible: true,
            simulated: true
          },
          {
            id: 2,
            name: "acct-2",
            canTrade: false,
            isVisible: true,
            simulated: true
          },
          {
            id: 3,
            name: "acct-3",
            canTrade: true,
            isVisible: true,
            simulated: false
          }
        ],
        success: true,
        errorCode: 0,
        errorMessage: null
      }))
      .mockResolvedValueOnce(jsonResponse({
        accounts: [
          {
            id: 1,
            name: "acct-1",
            canTrade: true,
            isVisible: true,
            simulated: true
          },
          {
            id: 2,
            name: "acct-2",
            canTrade: false,
            isVisible: true,
            simulated: true
          },
          {
            id: 3,
            name: "acct-3",
            canTrade: true,
            isVisible: true,
            simulated: false
          }
        ],
        success: true,
        errorCode: 0,
        errorMessage: null
      }));

    const adapter = new ProjectXLiveAdapter({
      enabled: true,
      baseUrl: "https://api.example.com",
      username: "demo-user",
      allowedAccountIds: ["acct-1", "acct-2", "acct-3"],
      apiKey: "secret",
      demoOnly: true,
      readOnly: true
    }, {
      fetchImpl: fetchMock as unknown as typeof fetch
    });

    const report = await adapter.preflightDemoAccounts();

    expect(report.ok).toBe(false);
    expect(report.allowedAccountCount).toBe(3);
    expect(report.discoveredAccountCount).toBe(3);
    expect(report.lanes.map((lane) => lane.status)).toEqual(["ok", "blocked", "blocked"]);
    expect(report.blockers).toEqual(expect.arrayContaining([
      "Matched account acct-2 (2) cannot trade.",
      "Matched account acct-3 (3) is not marked simulated."
    ]));
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });
});
