import { createPublicClient, http } from "viem";
import { polygon } from "viem/chains";

async function main() {
  const pc = createPublicClient({ chain: polygon, transport: http() });
  const EOA = "0x3ee8801f4Dbd1A3564383864435040E5b99dAC0D";
  const DW = "0x25D10ACCAF13021fbE7648Cbe202C2273408199C";
  const COLLATERAL = "0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB";
  const USDC = "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359";
  const abi = [{ constant:true, inputs:[{name:"a",type:"address"}], name:"balanceOf", outputs:[{name:"",type:"uint256"}], type:"function" }];

  const eoaM = await pc.getBalance({ address: EOA });
  console.log("EOA MATIC:", (Number(eoaM)/1e18).toFixed(2));
  const dwM = await pc.getBalance({ address: DW });
  console.log("DW MATIC:", (Number(dwM)/1e18).toFixed(2));
  const eoaU = await pc.readContract({ address: USDC, abi, functionName:"balanceOf", args:[EOA] });
  console.log("EOA USDC:", (Number(eoaU)/1e6).toFixed(2));
  const dwU = await pc.readContract({ address: USDC, abi, functionName:"balanceOf", args:[DW] });
  console.log("DW USDC:", (Number(dwU)/1e6).toFixed(2));
  const dwP = await pc.readContract({ address: COLLATERAL, abi, functionName:"balanceOf", args:[DW] });
  console.log("DW pUSD:", (Number(dwP)/1e6).toFixed(2));
}

main();
