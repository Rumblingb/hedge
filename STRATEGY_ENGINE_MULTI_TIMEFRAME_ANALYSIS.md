# Strategy Engine Multi-Timeframe Support Analysis

## Current Data Flow

### 1. StrategyEngineRunner.ts (Main Runner)
- **Data fetching**: 
  - `tvFetchBars()` from tvDataFetcher.ts (returns single current bar)
  - `fetchBarsYahoo()` (returns historical bars array)
  - Combines: replaces last Yahoo bar with TV's current price
- **Strategy calling**:
  - Builds StrategyContext with `bar` (current) and `history` (all bars)
  - Uses `classifyRegime(bars)` and `fuseStrategies(context, regime)`
  - Falls back to naive ensemble if needed
- **Signal routing**: Calls `signalRouter.route(orbSig)`

### 2. tvDataFetcher.ts (Data Source)
- **Current**: `fetchBars()` returns ONLY `[bar]` (single current bar)
- **Limitation**: No historical data fetching capability
- **Cache**: Single bar cached for 15s

### 3. strategyFusion.ts (Strategy Aggregation)
- Receives context with `bar` + `history` array
- Strategies get full context for calculations

### 4. signalRouter.ts (Signal Routing)
- Routes validated signals to brokers (no data logic)

## What Needs to Change for 5m/15m/30m/1h Multi-Timeframe

### 1. tvDataFetcher.ts Modifications (PRIMARY BOTTLENECK)
**Problem**: Only fetches 1 current bar, no historical data
**Solution**:
- Modify `fetchBars(timeframe: string, lookbackBars: number): Promise<Bar[]>`
- Support timeframes: '1m', '5m', '15m', '30m', '1h'
- Fetch appropriate historical data (50-100 bars per timeframe)
- Implement per-timeframe caching with suitable TTL
- Maintain backward compatibility (default to current behavior)

### 2. StrategyEngineRunner.ts Modifications
**Problem**: 
- Hardcoded 15m assumptions (BAR_INTERVAL_S, URLs)
- INTERVAL_MS = 60_000 may be suboptimal for different timeframes
**Solution**:
- Make timeframe configurable: `const TIMEFRAMES = ['1m', '5m', '15m', '30m', '1h']`
- Fetch/update each timeframe at appropriate intervals:
  - 1m: check every 15-30s
  - 5m: check every 60s
  - 15m: check every 60s
  - 30m: check every 120s
  - 1h: check every 300s
- Build multi-timeframe context for strategies
- Update URL construction to be timeframe-aware

### 3. StrategyContext Enhancement (domain.ts)
**Problem**: Single `bar: Bar` and `history: Bar[]` assumes one timeframe
**Solution**:
```typescript
export interface StrategyContext {
  symbol: string;
  currentBars: Record<string, Bar>;   // timeframe -> current bar
  history: Record<string, Bar[]>;     // timeframe -> historical bars
  // ... rest unchanged (config, dailyTradeCount, etc.)
}
```
*Alternative*: Keep backward compatibility by adding new fields while preserving old ones

### 4. Strategy Updates (wctcEnsemble.js)
**Problem**: Strategies expect single timeframe context
**Solution**:
- Update strategies to use multi-timeframe context
- Example usage:
  - Higher timeframes (15m/1h) for trend/filter context
  - Lower timeframes (1m/5m) for entry timing and precision
- Strategies can reference `context.history['1h']` for trend, `context.history['5m']` for entries

### 5. Key Bottlenecks
1. **tvDataFetcher.ts**: Main bottleneck - lacks historical data fetching
2. **Hardcoded timeframe assumptions**: Fixed URLs/intervals throughout runner
3. **Context structure**: Single timeframe assumption in StrategyContext
4. **Strategy logic**: May need updates to properly utilize multiple timeframes
5. **Fetching efficiency**: Need smart scheduling to avoid redundant requests

## Implementation Recommendation

### Phase 1: Data Layer Enhancement
- Update tvDataFetcher.ts to fetch historical bars per timeframe
- Add caching with timeframe-appropriate TTL (1m: 30s, 5m: 60s, etc.)
- Support configurable lookback (e.g., 100 bars)

### Phase 2: Runner Logic Updates
- Make timeframe array configurable
- Implement staggered update schedule per timeframe
- Build enriched StrategyContext with multi-timeframe data

### Phase 3: Context & Strategy Updates
- Extend StrategyContext for multi-timeframe support
- Update key strategies to leverage higher timeframe context

### Phase 4: Validation
- Ensure backward compatibility
- Test strategies receive proper multi-timeframe data
- Verify signal quality improvement with additional context

The critical path is enhancing tvDataFetcher.ts to provide historical multi-timeframe data, with corresponding updates to the runner to consume and distribute this data to strategies.