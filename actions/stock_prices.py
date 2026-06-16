import logging

logger = logging.getLogger("stock_prices")


def _try_get_stock(symbol: str) -> dict | None:
    try:
        import yfinance as yf

        ticker = yf.Ticker(symbol)
        info = ticker.info or {}
        price = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose")
        if price is None:
            hist = ticker.history(period="1d")
            if not hist.empty:
                price = round(float(hist["Close"].iloc[-1]), 2)
        change = info.get("regularMarketChangePercent") or info.get("regularMarketChange")
        name = info.get("shortName") or info.get("longName") or symbol.upper()
        currency = info.get("currency", "USD")
        return {
            "symbol": symbol.upper(),
            "name": name,
            "price": price,
            "change_pct": change,
            "currency": currency,
        }
    except Exception as exc:
        logger.debug("yfinance lookup failed for %s: %s", symbol, exc)
    return None


def stock_price_action(parameters: dict | None = None, player=None) -> str:
    if parameters is None:
        parameters = {}
    symbols = parameters.get("symbols") or parameters.get("symbol") or ""
    if isinstance(symbols, str):
        symbols = [s.strip() for s in symbols.replace(",", " ").split() if s.strip()]

    # Map common names to Yahoo Finance symbols
    crypto_map = {
        "bitcoin": "BTC-USD", "btc": "BTC-USD",
        "ethereum": "ETH-USD", "eth": "ETH-USD",
        "solana": "SOL-USD", "sol": "SOL-USD",
        "ripple": "XRP-USD", "xrp": "XRP-USD",
        "cardano": "ADA-USD", "ada": "ADA-USD",
        "dogecoin": "DOGE-USD", "doge": "DOGE-USD",
        "polkadot": "DOT-USD", "dot": "DOT-USD",
        "litecoin": "LTC-USD", "ltc": "LTC-USD",
        "chainlink": "LINK-USD", "link": "LINK-USD",
        "avalanche": "AVAX-USD", "avax": "AVAX-USD",
    }
    symbols = [crypto_map.get(s.lower(), s) for s in symbols]
    if not symbols:
        return "Please provide a stock symbol (e.g. AAPL, TSLA, MSFT)."

    results = []
    for sym in symbols:
        data = _try_get_stock(sym)
        if data and data.get("price"):
            price = data["price"]
            symbol = data["symbol"]
            name = data["name"]
            change = data.get("change_pct")
            change_str = ""
            if change is not None:
                sign = "+" if change >= 0 else ""
                change_str = f" ({sign}{change:.2f}%)"
            results.append(f"{name} ({symbol}): ${price:.2f}{change_str}")
        else:
            results.append(f"{sym.upper()}: could not fetch")
    return " | ".join(results)
