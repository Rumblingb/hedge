/**
 * tvLiveBridge.mjs — Real-time NQ price from the Chrome TradingView tab.
 * 
 * Uses Apple Events (JXA) to execute JavaScript in the authenticated 
 * Chrome TradingView tab and read the current NQ price.
 * Requires "Allow JavaScript from Apple Events" enabled in Chrome.
 */

import { execSync } from "node:child_process";
import { existsSync, writeFileSync, readFileSync } from "node:fs";
import { join } from "node:path";

const CACHE_PATH = join(process.cwd(), ".rumbling-hedge/state/tv-live-price.json");
const POLL_MS = 5_000; // poll every 5s

const JXA_SCRIPT = `
(() => {
  const tabs = Application("Google Chrome").windows.flatMap(w => w.tabs());
  const tvTab = tabs.find(t => t.url && (t.url.includes("tradingview.com/chart") || t.url.includes("tradingview.com/chart")));
  if (!tvTab) return JSON.stringify({ error: "no TV chart tab found" });
  const title = tvTab.title();
  // Parse "NQ1! 29,262.25 ▲ +0.1% Unnamed"
  const match = title.match(/[\\d,]+\\.\\d{2}/);
  if (!match) return JSON.stringify({ error: "could not parse price from title", title });
  const price = parseFloat(match[0].replace(/,/g, ""));
  return JSON.stringify({ price, title, ts: Date.now() });
})();
`;

let lastPrice = null;

function getPriceFromChrome() {
  try {
    const result = execSync(
      `/usr/bin/osascript -l JavaScript -e '${JXA_SCRIPT.replace(/'/g, "'\\''")}'`,
      { encoding: "utf8", timeout: 10_000 }
    );
    const data = JSON.parse(result.trim());
    if (data.error) {
      console.error("[TVBridge] Chrome error:", data.error);
      return null;
    }
    return data;
  } catch (e) {
    console.error("[TVBridge] Execution error:", e.message?.slice(0, 100));
    return null;
  }
}

function readPrice() {
  const data = getPriceFromChrome();
  if (data && data.price) {
    lastPrice = data.price;
    // Write to shared state file
    const state = { 
      price: data.price, 
      ts: data.ts || Date.now(),
      source: "tradingview-prodata"
    };
    writeFileSync(CACHE_PATH, JSON.stringify(state, null, 2));
    console.log(`[TVBridge] NQ: $${data.price.toFixed(2)} — LIVE`);
    return data.price;
  }
  return lastPrice;
}

// Poll loop
console.log("[TVBridge] Starting TradingView live price poller...");
console.log(`[TVBridge] Interval: ${POLL_MS}ms | Cache: ${CACHE_PATH}`);

// Read immediately
readPrice();

setInterval(readPrice, POLL_MS);

// Handle graceful shutdown
process.on("SIGINT", () => process.exit(0));
process.on("SIGTERM", () => process.exit(0));
