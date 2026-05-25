const { TradingViewAPI } = require("tradingview-scraper");

async function main() {
  console.log("[TEST] Connecting to TV WebSocket with full cookie set...");
  const client = new TradingViewAPI();
  
  // Add error handler for unhandled WS errors
  process.on('uncaughtException', (err) => {
    console.error("[UNCAUGHT]", err.message);
    process.exit(1);
  });
  
  try {
    const startTime = Date.now();
    await client.setup();
    const setupTime = Date.now() - startTime;
    console.log(`[TEST] Setup took ${setupTime}ms`);
    
    if (setupTime < 500) {
      console.log("[TEST] ⚠️ Setup resolved too fast - WS may not have connected");
    }
    
    console.log("[TEST] Getting ticker for NQ...");
    const t0 = Date.now();
    const data = await client.getTicker("CME_MINI:NQ1!");
    const t1 = Date.now();
    console.log(`[TEST] getTicker took ${t1-t0}ms`);
    
    console.log("[TEST] Full data keys:", Object.keys(data || {}));
    console.log("[TEST] tickerData:", data?.tickerData);
    
    if (data && data.tickerData) {
      const td = data.tickerData;
      console.log(`[RESULT] Last: ${td.lp}, Bid: ${td.bid}, Ask: ${td.ask}`);
      console.log(`[RESULT] Update mode: ${td.update_mode}`);
      if (td.update_mode === "realtime") {
        console.log("[RESULT] ✅ REAL-TIME DATA!");
      } else {
        console.log("[RESULT] ⚠️ DATA STATUS:", td.update_mode);
      }
    } else {
      console.log("[TEST] No ticker data");
    }
    
    process.exit(0);
  } catch (e) {
    console.error("[TEST] Error:", e.message || e);
    console.error("[TEST] Stack:", e.stack?.slice(0,500));
    process.exit(1);
  }
}

main();
// Safety timeout 25s
setTimeout(() => { 
  console.log("[TIMEOUT] 25s - forcing exit"); 
  process.exit(1); 
}, 25000);
