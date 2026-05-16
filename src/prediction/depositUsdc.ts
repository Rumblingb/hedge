import { createWalletClient, http, parseUnits } from 'viem';
import { polygon } from 'viem/chains';
import { privateKeyToAccount } from 'viem/accounts';

const PRIVATE_KEY = process.env.POLYMARKET_PRIVATE_KEY;

if (!PRIVATE_KEY) {
  console.error('POLYMARKET_PRIVATE_KEY not set');
  process.exit(1);
}

const USDC = '0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359';
const EXCHANGE = '0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E'; // Polymarket CTF Exchange

const account = privateKeyToAccount(PRIVATE_KEY as `0x${string}`);
const client = createWalletClient({
  account,
  chain: polygon,
  transport: http('https://polygon.drpc.org')
});

console.log('Depositing USDC into Polymarket Exchange...');
console.log('Address:', account.address);

// Approve USDC for exchange (we already did this, check if needed)
console.log('Sending approve...');
const approveHash = await client.writeContract({
  address: USDC,
  abi: [{
    name: 'approve', type: 'function',
    inputs: [{ name: 'spender', type: 'address' }, { name: 'amount', type: 'uint256' }],
    outputs: [{ name: '', type: 'bool' }],
    stateMutability: 'nonpayable'
  }],
  functionName: 'approve',
  args: [EXCHANGE, parseUnits('132', 6)]
});
console.log('✅ Approve:', `https://polygonscan.com/tx/${approveHash}`);
console.log('Waiting...');
await new Promise(r => setTimeout(r, 15000));

// Use exact deposit function signature on exchange
// deposit(address token, uint256 amount)
console.log('Sending deposit...');
const depositHash = await client.writeContract({
  address: EXCHANGE,
  abi: [{
    name: 'deposit', type: 'function',
    inputs: [
      { name: 'token', type: 'address' },
      { name: 'amount', type: 'uint256' }
    ],
    outputs: [],
    stateMutability: 'nonpayable'
  }],
  functionName: 'deposit',
  args: [USDC, parseUnits('100', 6)]
});
console.log('✅ Deposit:', `https://polygonscan.com/tx/${depositHash}`);
console.log('Done! Gengar ready to trade.');
