import { createPublicClient, http, createWalletClient } from "viem";
import { polygon } from "viem/chains";
import { privateKeyToAccount } from "viem/accounts";

async function main() {
  const pk = process.env.POLYMARKET_PRIVATE_KEY! as `0x${string}`;
  const account = privateKeyToAccount(pk);
  const walletClient = createWalletClient({ account, chain: polygon, transport: http() });
  const { ClobClient } = await import("@polymarket/clob-client-v2");
  
  const DW = "0x25D10ACCAF13021fbE7648Cbe202C2273408199C";
  
  const client = new ClobClient({
    host: "https://clob.polymarket.com", chain: 137, signer: walletClient,
    signatureType: 3, funderAddress: DW,
  });
  const creds = await client.deriveApiKey();
  client.creds = creds;

  const bal = await client.getBalanceAllowance({
    asset_type: "COLLATERAL",
    owner: DW
  });
  console.log("Bal:", JSON.stringify(bal, null, 2).slice(0, 500));
}

main();
