const { TradingViewAPI } = require("tradingview-scraper");

async function main() {
  console.log("[TEST] Connecting to TV WebSocket with full cookie set...");
  const client = new TradingViewAPI();
  try {
    await client.setup();
    await new Promise(r => setTimeout(r, 5000));
    
    console.log("[TEST] Getting ticker for NQ...");
    const data = await client.getTicker("CME_MINI:NQ1!");
    
    if (data && data.tickerData) {
      const td = data.tickerData;
      console.log(`[TEST] Bid: ${td.bid}, Ask: ${td.ask}, Last: ${td.lp}`);
      console.log(`[TEST] Session: ${td.current_session}`);
      console.log(`[TEST] Update mode: ${td.update_mode}`);
      console.log(`[TEST] Type: ${td.type}`);
      if (td.update_mode === "realtime") {
        console.log("[RESULT] ✅ REAL-TIME DATA!");
      } else {
        console.log("[RESULT] ⚠️ Data still delayed. Update mode:", td.update_mode);
      }
    } else {
      console.log("[TEST] No ticker data received");
    }
    
    client.end();
    process.exit(0);
  } catch (e) {
    console.error("[TEST] Error:", e.message);
    process.exit(1);
  }
}

main();
