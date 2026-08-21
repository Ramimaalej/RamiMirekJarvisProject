import requests
import logging

logger = logging.getLogger(__name__)

def get_stock_price(parameters: dict | None = None, player=None) -> str:
    parameters = parameters or {}
    symbol = (parameters.get("symbol") or parameters.get("text") or "").strip().upper()
    if not symbol:
        return "Please provide a stock symbol, e.g., 'price of AAPL'."
    
    try:
        # Using a public API (Yahoo Finance via query2)
        url = f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=1d"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=10)
        data = resp.json()
        
        meta = data["chart"]["result"][0]["meta"]
        price = meta["regularMarketPrice"]
        currency = meta["currency"]
        change = meta.get("regularMarketPrice", 0) - meta.get("previousClose", 0)
        pct = (change / meta.get("previousClose", 1)) * 100
        
        sign = "+" if change >= 0 else ""
        return f"Stock {symbol}: {price} {currency} ({sign}{price-meta['previousClose']:.2f}, {sign}{pct:.2f}%)"
    except Exception as e:
        logger.error("Stock error: %s", e)
        return f"Could not fetch stock price for {symbol}. Error: {str(e)}"
