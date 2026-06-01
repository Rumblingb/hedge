#!/usr/bin/env python3
"""
Backtrader verification & demo for NQ (NASDAQ-100 E-mini) futures backtesting.

NQ Futures Specifications:
  - Tick size: 0.25 points = $5.00 per contract
  - Point value (multiplier): $20 per point
  - Typical margin: ~$20,000 per contract (varies by broker)
  - Commission: ~$2-$4 per side per contract (varies)

CSV Data Available (in /Users/brain/hedge/data/free/):
  Timeframes: 1m, 5m, 15m, 30m, 60m, 240m, 1d
  Lookbacks: 5d, 21d, 30d, 60d, 1y, 5y, 1825d

  Column format varies by file:
    - Intraday: ts,symbol,open,high,low,close,volume  (ISO 8601: 2026-03-08T22:00:00.000Z)
    - Daily:    timestamp,symbol,open,high,low,close,volume  (2025-05-14 09:30:00)
"""
import backtrader as bt
import datetime
import os


# ── NQ Data Feed Factory ──────────────────────────────────────────────
def load_nq_data(path, timeframe_label=""):
    """
    Load an NQ CSV file with auto-detection of timestamp format.
    
    The CSVs use two timestamp formats:
      - ISO 8601 with 'T' separator and 'Z' suffix (intraday)
      - Space-separated YYYY-MM-DD HH:MM:SS (daily)
    """
    with open(path) as f:
        f.readline()  # skip header
        first_data = f.readline().strip()
    
    # Auto-detect dtformat based on first data row
    # ISO 8601 has a 'T' separator between date and time
    ts_part = first_data.split(',')[0]
    if 'T' in ts_part:
        dtformat = '%Y-%m-%dT%H:%M:%S.%fZ'
    else:
        dtformat = '%Y-%m-%d %H:%M:%S'
    
    data = bt.feeds.GenericCSVData(
        dataname=path,
        dtformat=dtformat,
        datetime=0,    # timestamp column
        open=2,        # open
        high=3,        # high
        low=4,         # low
        close=5,       # close
        volume=6,      # volume
        openinterest=-1,  # not available
        header=0,      # first row is header (skip it)
        timeframe=getattr(bt.TimeFrame, 
            'Minutes' if 'm-' in path else 'Days'),
    )
    
    print(f"Loaded {path.split('/')[-1]:40s} {timeframe_label:>6s}  "
          f"format={dtformat}")
    return data


# ── Built-in Strategy: SMA Crossover ───────────────────────────────────
class NQSMA_CrossOver(bt.Strategy):
    """
    Custom SMA Crossover strategy for NQ futures.
    
    Based on backtrader's built-in MA_CrossOver (alias: SMA_CrossOver).
    
    Parameters:
      - fast (10): fast MA period
      - slow (30): slow MA period
      - movav (bt.indicators.SMA): moving average type
    
    Buy:  fast MA crosses above slow MA (golden cross)
    Sell: fast MA crosses below slow MA (dead cross)
    """
    params = (
        ('fast', 10),
        ('slow', 30),
        ('movav', bt.indicators.SMA),
        ('stake', 1),  # number of contracts
    )
    
    def __init__(self):
        sma_fast = self.p.movav(period=self.p.fast)
        sma_slow = self.p.movav(period=self.p.slow)
        self.crossover = bt.indicators.CrossOver(sma_fast, sma_slow)
        self.order = None
    
    def log(self, txt):
        dt = bt.num2date(self.data.datetime[0])
        print(f"  {dt.date()} {dt.strftime('%H:%M') if hasattr(dt, 'strftime') else ''} | {txt}")
    
    def notify_order(self, order):
        if order.status in [order.Completed]:
            if order.isbuy():
                self.log(f"BUY  @ {order.executed.price:.2f}  size={order.executed.size}")
            else:
                self.log(f"SELL @ {order.executed.price:.2f}  size={order.executed.size}")
            self.order = None
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log(f"ORDER FAILED: {order.getstatusname()}")
            self.order = None
    
    def next(self):
        if self.order:
            return  # pending order
        
        if self.position.size:
            if self.crossover < 0:  # dead cross -> sell
                self.order = self.sell(size=self.p.stake)
        else:
            if self.crossover > 0:  # golden cross -> buy
                self.order = self.buy(size=self.p.stake)


# ── More Advanced Strategy Example: Bollinger Bands + RSI ──────────────
class NQBollingerRSI(bt.Strategy):
    """
    Bollinger Bands + RSI strategy for NQ futures.
    
    Entry: Price touches lower band AND RSI < 30 (oversold bounce)
    Exit:  Price touches upper band OR RSI > 70 (overbought)
    """
    params = (
        ('bb_period', 20),
        ('bb_dev', 2.0),
        ('rsi_period', 14),
        ('rsi_low', 30),
        ('rsi_high', 70),
        ('stake', 1),
    )
    
    def __init__(self):
        self.bb = bt.indicators.BollingerBands(
            self.data.close, 
            period=self.p.bb_period, 
            devfactor=self.p.bb_dev
        )
        self.rsi = bt.indicators.RSI(self.data.close, period=self.p.rsi_period)
        self.order = None
    
    def log(self, txt):
        dt = bt.num2date(self.data.datetime[0])
        print(f"  {dt.date()} | {txt}")
    
    def notify_order(self, order):
        if order.status == order.Completed:
            side = "BUY" if order.isbuy() else "SELL"
            self.log(f"{side} @ {order.executed.price:.2f}  "
                     f"size={order.executed.size}")
            self.order = None
    
    def next(self):
        if self.order:
            return
        
        if self.position.size:
            # Exit: price above upper band OR RSI overbought
            if self.data.close[0] >= self.bb.top[0] or self.rsi[0] > self.p.rsi_high:
                self.order = self.sell(size=self.p.stake)
        else:
            # Entry: price at/below lower band AND RSI oversold
            if self.data.close[0] <= self.bb.bot[0] and self.rsi[0] < self.p.rsi_low:
                self.order = self.buy(size=self.p.stake)


# ── Demo Run ──────────────────────────────────────────────────────────
def run_demo(strategy_class, strategy_name, data_path, commission=2.5, 
             margin=20000.0, mult=20.0, cash=50000.0):
    """
    Run a backtest with NQ futures commission scheme.
    
    NQ: $20/point multiplier, ~$2.50 commission/side, $20k margin
    """
    cerebro = bt.Cerebro()
    
    # Load data
    data = load_nq_data(data_path)
    cerebro.adddata(data)
    
    # Add strategy
    cerebro.addstrategy(strategy_class)
    
    # NQ futures commission scheme
    cerebro.broker.setcommission(
        commission=commission,  # $2.50 per side per contract
        margin=margin,          # $20,000 initial margin
        mult=mult,              # $20 per point multiplier
    )
    cerebro.broker.setcash(cash)
    
    # Add analyzers for performance metrics
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
    cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
    
    print(f"\n{'='*60}")
    print(f"  Strategy: {strategy_name}")
    print(f"  Data: {os.path.basename(data_path)}")
    print(f"  Commission: ${commission}/side, Margin: ${margin:,}, Mult: {mult}x")
    print(f"  Starting Cash: ${cash:,}")
    print(f"{'='*60}")
    
    start_value = cerebro.broker.getvalue()
    results = cerebro.run()
    final_value = cerebro.broker.getvalue()
    
    strat = results[0]
    
    # Print results
    print(f"\n  Final Portfolio Value: ${final_value:,.2f}")
    print(f"  Total Return: {((final_value - start_value) / start_value * 100):.2f}%")
    
    # Trade statistics
    trades = strat.analyzers.trades.get_analysis()
    total_trades = trades.get('total', {}).get('total', 0)
    won = trades.get('won', {}).get('total', 0)
    lost = trades.get('lost', {}).get('total', 0)
    print(f"  Total Trades: {total_trades}  |  Won: {won}  |  Lost: {lost}")
    
    if total_trades > 0 and won + lost > 0:
        print(f"  Win Rate: {won/(won+lost)*100:.1f}%")
    
    # Sharpe ratio
    sharpe = strat.analyzers.sharpe.get_analysis()
    if sharpe.get('sharperatio'):
        print(f"  Sharpe Ratio: {sharpe['sharperatio']:.2f}")
    
    # Drawdown
    dd = strat.analyzers.drawdown.get_analysis()
    if dd.get('max', {}).get('drawdown'):
        print(f"  Max Drawdown: {dd['max']['drawdown']:.2f}%")
    
    print()
    return results


# ── Main ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("  BACKTRADER NQ FUTURES VERIFICATION")
    print(f"  backtrader version: {bt.__version__}")
    print("=" * 60)
    
    # Demo 1: SMA Crossover on daily data
    run_demo(
        NQSMA_CrossOver, 
        "SMA Crossover (10/30)",
        "/Users/brain/hedge/data/free/NQ-1d-1y-fresh.csv"
    )
    
    # Demo 2: Bollinger + RSI on daily data
    run_demo(
        NQBollingerRSI,
        "Bollinger Bands + RSI",
        "/Users/brain/hedge/data/free/NQ-1d-1y-fresh.csv"
    )
    
    # Demo 3: SMA Crossover on 60-minute intraday data
    run_demo(
        NQSMA_CrossOver,
        "SMA Crossover (10/30) - 60m",
        "/Users/brain/hedge/data/free/NQ-60m-60d.csv"
    )
