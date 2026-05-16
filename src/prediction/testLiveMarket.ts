import { createWalletClient, http } from "viem";
import { polygon } from "viem/chains";
import { privateKeyToAccount } from "viem/accounts";

async function main() {
  const pk = process.env.POLYMARKET_PRIVATE_KEY!;
  const account = privateKeyToAccount(pk as `0x${string}`);
  const walletClient = createWalletClient({ account, chain: polygon, transport: http() });
  const { ClobClient, Side } = await import("@polymarket/clob-client-v2");

  const client = new ClobClient({
    host: "https://clob.polymarket.com", chain: 137, signer: walletClient,
    signatureType: 3, funderAddress: "0x25D10ACCAF13021fbE7648Cbe202C2273408199C",
  });
  const creds = await client.deriveApiKey();
  client.creds = creds;

  // Try multiple approachs to find an active market
  for (const endpoint of [
    "https://clob.polymarket.com/markets?limit=50&closed=false",
    "https://clob.polymarket.com/midpoints?token_id=0"
  ]) {
    try {
      const res = await fetch(endpoint, { headers: { "User-Agent": "Mozilla/5.0" } });
      const data = await res.json();
      const markets = Array.isArray(data) ? data : data.data || data.results || [];
      const btcMarkets = markets.filter((m: any) => 
        (m.question || "").toLowerCase().includes("bitcoin") ||
        (m.question || "").toLowerCase().includes("btc")
      );
      if (btcMarkets.length > 0) {
        const m = btcMarkets[0];
        const tid = m.clobTokenId || m.token_id || "";
        console.log(`Found: ${(m.question||"").substring(0,50)}`);
        console.log(`Token: ${tid.substring(0,20)}...`);
        if (tid) {
          try {
            const r = await client.createAndPostOrder({
              tokenID: tid, price: 0.50, size: 7, side: Side.BUY
            });
            console.log(`Order result: ${JSON.stringify(r).substring(0,200)}`);
          } catch(e: any) {
            console.log(`Order error: ${e.message.substring(0,100)}`);
          }
        }
      } else {
        console.log(`No BTC markets in ${endpoint.substring(0,40)}...`);
      }
    } catch(e: any) { console.log(`Failed ${endpoint.substring(0,40)}: ${e.message.substring(0,50)}`); }
  }
}

main().catch(e => console.error("FATAL:", e.message));
