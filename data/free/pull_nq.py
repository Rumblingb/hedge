import yfinance as yf
import pandas as pd
from datetime import datetime, timezone

ticker = yf.Ticker("NQ=F")
# Try to get max available 60m data
df = ticker.history(period="730d", interval="60m")
if len(df) < 2000:
    df = ticker.history(period="max", interval="60m")

df = df.reset_index()
df['symbol'] = 'NQ'
df = df.rename(columns={'Datetime': 'ts', 'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close', 'Volume': 'volume'})
df = df[['ts', 'symbol', 'open', 'high', 'low', 'close', 'volume']]
df['ts'] = df['ts'].dt.strftime('%Y-%m-%dT%H:%M:%S.000Z')

output_path = '/Users/brain/hedge/data/free/NQ-60m-1y.csv'
df.to_csv(output_path, index=False)
print(f"Saved {len(df)} rows to {output_path}")

# Print some stats
print(f"Date range: {df['ts'].iloc[0]} to {df['ts'].iloc[-1]}")
print(f"First few rows:")
print(df.head(3))
print(f"Last few rows:")
print(df.tail(3))
