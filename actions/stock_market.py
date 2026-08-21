import requests
import logging

logger = logging.getLogger(__name__)

def get_stock_price(parameters: dict | None = None, player=None) -> str:
    parameters = parameters or {}
    symbol = (parameters.get("symbol") or parameters.get("text") or parameters.get("query") or "").strip().upper()
    
    # Handle common commodity/forex mappings for Yahoo Finance
    mappings = {
        "XAUUSD": "XAUUSD=X",
        "GOLD": "GC=F",
        "SILVER": "SI=F",
        "XAGUSD": "XAGUSD=X",
        "EURUSD": "EURUSD=X",
        "GBPUSD": "GBPUSD=X",
        "BTCUSD": "BTC-USD",
        "ETHUSD": "ETH-USD"
    }
    
    if symbol in mappings:
        symbol = mappings[symbol]
    
    if not symbol:
        return "Please provide a symbol (e.g., AAPL, XAUUSD, or BTC)."
    
    try:
        url = f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=1d"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=10)
        data = resp.json()
        
        if "chart" not in data or not data["chart"]["result"]:
            return f"No market data found for {symbol}."
            
        result = data["chart"]["result"][0]
        meta = result["meta"]
        price = meta.get("regularMarketPrice")
        prev_close = meta.get("previousClose")
        currency = meta.get("currency", "USD")
        
        if price is None:
            return f"Market price for {symbol} is currently unavailable."
            
        change = price - prev_close if prev_close else 0
        pct = (change / prev_close * 100) if prev_close else 0
        sign = "+" if change >= 0 else ""
        
        return f"MARKET DATA ({symbol}): {price:.2f} {currency} ({sign}{change:.2f}, {sign}{pct:.2f}%)"
    except Exception as e:
        logger.error("Market error: %s", e)
        return f"Could not fetch data for {symbol}. (API Error)"
