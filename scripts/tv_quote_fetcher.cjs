/**
 * tv_quote_fetcher.cjs — Fetch real-time NQ/ES quotes from TradingView WebSocket.
 * 
 * Connects to TV prodata WebSocket with session auth (TV_SESSION env var).
 * Subscribes to quote streams for CME_MINI:NQ1! and CME_MINI:ES1!.
 * Accumulates partial quote updates across multiple packets.
 * 
 * Usage: node tv_quote_fetcher.cjs [--json]
 * Output: { timestamp, price_nq, price_es, source, latency_ms, error }
 */

const https = require("https");
const WebSocket = require("ws");

const TV_SESSION = process.env.TV_SESSION || "";
const TV_SESSION_SIGN = process.env.TV_SESSION_SIGN || "";

const SYMBOLS = {
  nq: "CME_MINI:NQ1!",
  es: "CME_MINI:ES1!"
};

const ALL_QUOTE_FIELDS = [
  "base-currency-logoid", "ch", "chp", "currency-logoid", "currency_code",
  "current_session", "description", "exchange", "format", "fractional",
  "high_price", "is_tradable", "last_local", "last_time", "local_description",
  "logoid", "lp", "lp_time", "minmov", "minmove2", "name", "open_price",
  "original_name", "pricescale", "pro_name", "rch", "rchp", "short_name",
  "source", "type", "update_mode", "volume", "ask", "bid", "fundamentals",
  "rtc", "high", "low", "prev_close_price"
];

function extractAuthToken() {
  return new Promise((resolve) => {
    if (!TV_SESSION) {
      console.error("[TV] No TV_SESSION — using public feed (delayed)");
      resolve(null);
      return;
    }

    const url = new URL("https://www.tradingview.com/disclaimer/");
    const options = {
      hostname: url.hostname,
      path: url.pathname,
      method: "GET",
      headers: {
        "Cookie": `sessionid=${TV_SESSION}${TV_SESSION_SIGN ? `; sessionid_sign=${TV_SESSION_SIGN}` : ""}`,
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
      }
    };

    const req = https.request(options, (res) => {
      let body = "";
      res.on("data", (chunk) => { body += chunk; });
      res.on("end", () => {
        const match = body.match(/"auth_token"\s*:\s*"([^"]+)"/);
        if (match) {
          console.error("[TV] Auth token extracted successfully");
          resolve(match[1]);
        } else {
          console.error(`[TV] No auth_token in disclaimer page (HTTP ${res.statusCode})`);
          resolve(null);
        }
      });
    });

    req.on("error", (e) => {
      console.error("[TV] Disclaimer fetch error:", e.message);
      resolve(null);
    });
    
    req.setTimeout(10000, () => { req.destroy(); resolve(null); });
    req.end();
  });
}

async function fetchQuotes() {
  const start = Date.now();
  let authToken = null;

  if (TV_SESSION) {
    authToken = await extractAuthToken();
  }

  const isPro = !!authToken;
  const wsUrl = isPro
    ? "wss://prodata.tradingview.com/socket.io/websocket?auth=sessionid"
    : "wss://data.tradingview.com/socket.io/websocket";

  const wsOpts = { 
    origin: "https://data.tradingview.com",
    handshakeTimeout: 10000
  };

  if (isPro) {
    wsOpts.headers = {
      Cookie: [
        `sessionid=${TV_SESSION}`,
        `sessionid_sign=${TV_SESSION_SIGN}`,
      ].join("; "),
    };
    wsOpts.origin = "https://prodata.tradingview.com";
  }

  return new Promise((resolve) => {
    const ws = new WebSocket(wsUrl, wsOpts);
    // Accumulated quote data per symbol - merge partial updates
    const quotesAcc = { nq: {}, es: {} };
    const errors = [];
    let resolved = false;
    
    const symbolKeyMap = {};
    for (const [key, sym] of Object.entries(SYMBOLS)) {
      symbolKeyMap[sym] = key;
    }

    const finish = () => {
      if (resolved) return;
      resolved = true;
      
      const latencyMs = Date.now() - start;
      const nq = quotesAcc.nq;
      const es = quotesAcc.es;
      
      const result = {
        timestamp: new Date().toISOString(),
        price_nq: nq.lp ?? null,
        price_es: es.lp ?? null,
        bid_nq: nq.bid ?? null,
        ask_nq: nq.ask ?? null,
        bid_es: es.bid ?? null,
        ask_es: es.ask ?? null,
        source: isPro ? "tradingview_pro" : "tradingview_public",
        latency_ms: latencyMs,
        session_nq: nq.current_session ?? null,
        session_es: es.current_session ?? null,
        update_mode_nq: nq.update_mode ?? null,
        update_mode_es: es.update_mode ?? null,
        change_nq: nq.ch ?? null,
        change_pct_nq: nq.chp ?? null,
        change_es: es.ch ?? null,
        change_pct_es: es.chp ?? null,
        error: errors.length > 0 ? errors.join("; ") : null
      };

      try { ws.close(); } catch {}
      resolve(result);
    };

    // Timeout after 12 seconds
    const timeout = setTimeout(() => {
      const missing = [];
      if (quotesAcc.nq.lp == null) missing.push("NQ");
      if (quotesAcc.es.lp == null) missing.push("ES");
      if (missing.length > 0) errors.push(`timeout waiting for: ${missing.join(", ")}`);
      finish();
    }, 12000);

    ws.on("open", () => {
      console.error(`[TV] Connected to ${wsUrl}`);
    });

    ws.on("error", (err) => {
      errors.push(`websocket: ${err.message}`);
      finish();
    });

    ws.on("close", (code, reason) => {
      console.error(`[TV] Closed: ${code} ${reason || ""}`);
    });

    ws.on("message", (raw) => {
      const msg = raw.toString();
      const parts = msg.split(/~m~\d+~m~/).filter(Boolean);
      
      for (const part of parts) {
        if (part.startsWith("~h~")) {
          ws.send(`~m~${part.length}~m~${part}`);
          continue;
        }

        try {
          const data = JSON.parse(part);
          
          // Session established - authenticate and create quote session
          if (data.session_id) {
            const token = authToken || "unauthorized_user_token";
            sendMessage(ws, "set_auth_token", [token]);
            const qs = "qs_" + randomAlpha(12);
            sendMessage(ws, "quote_create_session", [qs]);
            sendMessage(ws, "quote_set_fields", [qs, ...ALL_QUOTE_FIELDS]);
            for (const symbol of Object.values(SYMBOLS)) {
              sendMessage(ws, "quote_add_symbols", [qs, symbol]);
            }
            console.error("[TV] Quote session created, symbols subscribed");
            return;
          }

          // Quote data (qsd = quote stream data)
          if (data.m === "qsd" && Array.isArray(data.p) && data.p.length >= 2) {
            const tickerData = data.p[1];
            if (!tickerData || !tickerData.n || !tickerData.v) continue;
            
            const symbol = tickerData.n;
            const key = symbolKeyMap[symbol];
            if (!key) continue;
            
            // Merge partial update into accumulated quote
            const update = tickerData.v;
            Object.assign(quotesAcc[key], update);
            
            // Log only when we get lp (last price)
            if (update.lp != null) {
              console.error(`[TV] ${key.toUpperCase()}: $${update.lp} | mode: ${quotesAcc[key].update_mode || "?"}`);
            }
            
            // Check if both symbols have lp
            if (quotesAcc.nq.lp != null && quotesAcc.es.lp != null) {
              clearTimeout(timeout);
              finish();
            }
          }
        } catch (e) {
          // Ignore parse errors
        }
      }
    });
  });
}

function sendMessage(ws, func, args) {
  const msg = JSON.stringify({ m: func, p: args });
  const framed = `~m~${msg.length}~m~${msg}`;
  ws.send(framed);
}

function randomAlpha(length) {
  const chars = "abcdefghijklmnopqrstuvwxyz";
  let result = "";
  for (let i = 0; i < length; i++) {
    result += chars[Math.floor(Math.random() * chars.length)];
  }
  return result;
}

async function main() {
  const result = await fetchQuotes();
  if (process.argv.includes("--json") || process.argv.includes("-j")) {
    console.log(JSON.stringify(result));
  } else {
    console.log(`NQ: $${result.price_nq?.toFixed(2) ?? "N/A"} | ES: $${result.price_es?.toFixed(2) ?? "N/A"}`);
    console.log(`Source: ${result.source} | Latency: ${result.latency_ms}ms`);
    if (result.error) console.log(`Errors: ${result.error}`);
  }
  process.exit(result.price_nq && result.price_es ? 0 : 1);
}

main().catch(e => {
  console.error("FATAL:", e.message || e);
  process.exit(2);
});
