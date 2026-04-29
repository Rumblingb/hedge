import { describe, expect, it, vi } from "vitest";
import {
  buildProjectXOrderSpec,
  buildProjectXPlaceOrderRequest,
  ProjectXLiveAdapter
} from "../src/adapters/projectx/projectxAdapter.js";
import type { StrategySignal } from "../src/domain.js";

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
    expect(request.stopLossBracket.ticks).toBeGreaterThan(0);
    expect(request.takeProfitBracket.ticks).toBeGreaterThan(request.stopLossBracket.ticks);
    expect(request.customTag).toContain("wctc-ensemble-session-momentum");
  });

  it("authenticates, resolves the contract, and places a guarded demo order", async () => {
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
    expect(fetchMock).toHaveBeenCalledTimes(4);

    const placeOrderInit = fetchMock.mock.calls[3]?.[1] as RequestInit | undefined;
    const placeOrderBody = JSON.parse(String(placeOrderInit?.body));
    expect(placeOrderBody.accountId).toBe(465);
    expect(placeOrderBody.contractId).toBe("CON.F.US.ENQ.U26");
    expect(placeOrderBody.side).toBe(0);
    expect(placeOrderBody.stopLossBracket.type).toBe(4);
    expect(placeOrderBody.takeProfitBracket.type).toBe(1);
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
});
