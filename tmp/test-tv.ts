import { fetchBars, isInSession } from '../src/engine/tvDataFetcher.js';

async function main() {
  console.log('In session:', isInSession());
  console.log('TV_SESSION set:', !!process.env.TV_SESSION);
  console.log('TV_SESSION:', process.env.TV_SESSION?.substring(0, 20) + '...');
  const bars = await fetchBars();
  console.log('Bars:', JSON.stringify(bars));
}

main().catch(e => console.error('Error:', e.message));
