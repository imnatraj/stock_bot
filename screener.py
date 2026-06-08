import yfinance as yf
import pandas as pd

print("⏳ Scraping live Nifty 50 and Nifty Bank constituent lists...")
watchlist = set()

# 1. Fetch Nifty 50
try:
    nifty50_tables = pd.read_html("https://en.wikipedia.org/wiki/NIFTY_50")
    for symbol in nifty50_tables[2]['Symbol'].tolist():
        watchlist.add(f"{symbol}.NS")
    print(f"✅ Loaded Nifty 50 stocks.")
except Exception as e:
    print(f"⚠️ Nifty 50 scrape failed: {e}")

# 2. Fetch Nifty Bank 
try:
    # Pulls the official 12 structural bank stocks
    niftybank_tables = pd.read_html("https://en.wikipedia.org/wiki/NIFTY_Bank")
    for symbol in niftybank_tables[1]['Symbol'].tolist():
        watchlist.add(f"{symbol}.NS")
    print(f"✅ Loaded Nifty Bank stocks.")
except Exception as e:
    print(f"⚠️ Nifty Bank scrape failed: {e}")

# Convert set back to a clean list
watchlist = list(watchlist)
print(f"📊 Total unique structural stocks to process: {len(watchlist)}\n")

print(f"{'Stock':<15} | {'Action':<15} | {'Buy Trigger':<12} | {'Target (+4%)':<13} | {'Stop-Loss (-2%)':<15}")
print("-" * 78)

# 3. Optimize with a single Batch API Request
batch_data = yf.download(watchlist, period="60d", group_by='ticker', progress=False)

for ticker_symbol in watchlist:
    try:
        df = batch_data[ticker_symbol].dropna()
        if len(df) < 20:
            continue
            
        # Calculate Technical Moving Average
        df['EMA_20'] = df['Close'].ewm(span=20, adjust=False).mean()
        
        yesterday = df.iloc[-2]
        yesterday_high = yesterday['High']
        yesterday_close = yesterday['Close']
        ema_20 = yesterday['EMA_20']
        
        # Algorithmic Parameters
        is_near_ema = abs(yesterday_close - ema_20) / ema_20 <= 0.025
        is_above_ema = yesterday_close > ema_20
        
        if is_above_ema and is_near_ema:
            buy_trigger = round(yesterday_high + 1.0, 2)
            target = round(buy_trigger * 1.04, 2)
            stop_loss = round(buy_trigger * 0.98, 2)
            
            print(f"{ticker_symbol:<15} | {'READY TO BUY':<15} | ₹{buy_trigger:<11} | ₹{target:<12} | ₹{stop_loss:<14}")
            
    except Exception:
        pass