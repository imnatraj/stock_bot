import urllib.request
import yfinance as yf
import pandas as pd

print("⏳ Scraping live Nifty 50 and Nifty Bank constituent lists...")
watchlist = set()

def fetch_symbols_from_wikipedia(url: str) -> list:
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
        with urllib.request.urlopen(req) as response:
            html = response.read()
        tables = pd.read_html(html)
        for table in tables:
            if 'Symbol' in table.columns:
                return table['Symbol'].tolist()
    except Exception as e:
        print(f"⚠️ Scrape failed for {url}: {e}")
    return []

# 1. Fetch Nifty 50
nifty50_symbols = fetch_symbols_from_wikipedia("https://en.wikipedia.org/wiki/NIFTY_50")
if nifty50_symbols:
    for symbol in nifty50_symbols:
        watchlist.add(f"{symbol}.NS")
    print(f"✅ Loaded {len(nifty50_symbols)} Nifty 50 stocks.")
else:
    print("⚠️ Loaded 0 Nifty 50 stocks.")

# 2. Fetch Nifty Bank
niftybank_symbols = fetch_symbols_from_wikipedia("https://en.wikipedia.org/wiki/NIFTY_Bank")
if niftybank_symbols:
    for symbol in niftybank_symbols:
        watchlist.add(f"{symbol}.NS")
    print(f"✅ Loaded {len(niftybank_symbols)} Nifty Bank stocks from Wikipedia.")
else:
    niftybank_fallback = [
        "AUBANK", "AXISBANK", "BANDHANBNK", "BANKBARODA", "FEDERALBNK",
        "HDFCBANK", "ICICIBANK", "IDFCFIRSTB", "INDUSINDBK", "KOTAKBANK",
        "PNB", "SBIN"
    ]
    for symbol in niftybank_fallback:
        watchlist.add(f"{symbol}.NS")
    print(f"✅ Loaded {len(niftybank_fallback)} Nifty Bank stocks from fallback list.")

# Convert set back to a clean list
watchlist = list(watchlist)
print(f"📊 Total unique structural stocks to process: {len(watchlist)}\n")

print(f"{'Stock':<15} | {'Action':<15} | {'Buy Trigger':<12} | {'Target (+4%)':<13} | {'Stop-Loss (-2%)':<15}")
print("-" * 78)

# 3. Optimize with a single Batch API Request
if not watchlist:
    print("❌ Watchlist is empty. No stocks to process.")
else:
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