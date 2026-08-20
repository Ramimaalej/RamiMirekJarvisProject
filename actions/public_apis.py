"""Public APIs hub — free public APIs requiring no API key.

Crypto prices (CoinGecko public), currency info (open.er API),
time zones (WorldTimeAPI), quotes (Quotable), currency codes (Frankfurter).
All endpoints are public and keyless. Failures degrade gracefully —
the caller should fall back to web_search.
"""
import logging

import requests

logger = logging.getLogger("public_apis")

_TIMEOUT = 8

# ── helpers ────────────────────────────────────────────────────────────

def _get(url: str, params: dict | None = None, timeout: int = _TIMEOUT) -> dict | None:
    try:
        r = requests.get(url, params=params, timeout=timeout)
        if r.status_code == 200:
            try:
                return r.json()
            except ValueError:
                return None
        logger.debug("HTTP %s for %s", r.status_code, url)
    except Exception as exc:  # noqa: BLE001
        logger.debug("public_apis request error: %s", exc)
    return None


# ── crypto prices (CoinGecko public API) ──────────────────────────────

_CRYPTO_IDS = {
    "bitcoin": "bitcoin", "btc": "bitcoin",
    "ethereum": "ethereum", "eth": "ethereum",
    "solana": "solana", "sol": "solana",
    "ripple": "ripple", "xrp": "ripple",
    "cardano": "cardano", "ada": "cardano",
    "dogecoin": "dogecoin", "doge": "dogecoin",
    "tether": "tether", "usdt": "tether",
    "binancecoin": "binancecoin", "bnb": "binancecoin",
    "polkadot": "polkadot", "dot": "polkadot",
    "litecoin": "litecoin", "ltc": "litecoin",
}


def check_crypto(crypto: str, currency: str = "usd") -> str:
    """Price + 24h change of a coin. Returns short human text or error."""
    cid = _CRYPTO_IDS.get(crypto.lower().strip())
    if not cid:
        return f"Unknown coin: {crypto}. I know: " + ", ".join(sorted(set(_CRYPTO_IDS.values())))[:200]
    data = _get("https://api.coingecko.com/api/v3/simple/price",
                params={"ids": cid, "vs_currencies": currency.lower(),
                        "include_24hr_change": "true"})
    coin = (data or {}).get(cid)
    if not coin:
        return f"Could not fetch {crypto} price. CoinGecko may be rate-limited — try again later or search the web."
    price = coin.get(currency.lower())
    change = coin.get(f"{currency.lower()}_24h_change")
    direction = "up" if (change or 0) >= 0 else "down"
    change_txt = f"{abs(change):.2f}% in the last 24h ({direction})" if change is not None else ""
    return f"{cid.title()} is at {price:,.2f} {currency.upper()} {change_txt}".strip()


# ── currency info ─────────────────────────────────────────────────────

def check_currency(base: str = "USD") -> str:
    """Top rates for a base currency from open.er API (free, keyless)."""
    data = _get(f"https://open.er-api.com/v6/latest/{base.upper()}")
    result = (data or {}).get("result")
    if result != "success":
        return "Could not fetch currency rates."
    rates = (data or {}).get("rates", {})
    if not rates:
        return "Could not fetch currency rates."
    interesting = ["EUR", "GBP", "TND", "JPY", "CAD", "AUD", "CNY", "TRY"]
    lines = [f"{base.upper()} = {rates.get(c, 0):,.4f} {c}" for c in interesting if c in rates]
    return "Rates: " + "; ".join(lines) or "Could not fetch currency rates."


def check_time(city_or_tz: str) -> str:
    """Current time for a city/timezone via WorldTimeAPI (free, keyless)."""
    tz = (city_or_tz or "").strip()
    if "/" not in tz:
        # try common aliases
        tz = {"tunis": "Africa/Tunis", "sfax": "Africa/Tunis", "tunisia": "Africa/Tunis",
              "london": "Europe/London", "paris": "Europe/Paris", "berlin": "Europe/Berlin",
              "dubai": "Asia/Dubai", "tokyo": "Asia/Tokyo", "new york": "America/New_York",
              "newyork": "America/New_York", "los angeles": "America/Los_Angeles"}.get(tz.lower(), tz)
    data = _get(f"https://worldtimeapi.org/api/timezone/{tz}")
    dt = (data or {}).get("datetime")
    if not dt:
        # Fallback: compute locally with the stdlib timezone DB
        import datetime as _dt
        try:
            from zoneinfo import ZoneInfo  # Python 3.9+
            _tz_obj = ZoneInfo(tz)
            _now = _dt.datetime.now(_tz_obj)
            return f"Current time in {city_or_tz}: {_now.strftime('%H:%M')} on {_now.strftime('%Y-%m-%d')}. (approx.)"
        except Exception as _ze:
            return f"Could not get time for {city_or_tz}."
    # dt like 2026-08-20T12:00:00+01:00
    try:
        date_part, time_part = dt.split("T")
        time_part = time_part.split("+")[0].split("-")[0][:5]
    except Exception:  # noqa: BLE001
        return f"Current time in {city_or_tz}: {dt}"
    return f"Current time in {city_or_tz}: {time_part} on {date_part}."


def check_rate(symbol: str) -> str:
    """FX rate for any pair from Frankfurter (free, keyless, ECB data)."""
    _clean = symbol.upper().replace("/", "").replace("-", "")
    if len(_clean) == 6:
        parts = [_clean[:3], _clean[3:]]
    else:
        parts = _clean.split()
    if len(parts) != 2 or len(parts[0]) != 3 or len(parts[1]) != 3:
        return "Use a 3-letter pair like EURUSD or EUR-USD."
    base, target = parts
    data = _get(f"https://api.frankfurter.dev/v1/latest?base={base}&symbols={target}")
    # frankfurter.dev returns rates at the top level (not under "data")
    rates = (data or {}).get("rates")
    if not rates or target not in rates:
        return f"Could not fetch the {base}/{target} rate. Try again or search the web."
    return f"1 {base} = {rates[target]:,.4f} {target} (ECB reference rate)."


_QUOTE_FALLBACK = [
    ("The best way to predict the future is to create it.", "Peter Drucker"),
    ("Talk is cheap. Show me the code.", "Linus Torvalds"),
    ("First, solve the problem. Then, write the code.", "John Johnson"),
    ("Simplicity is the soul of efficiency.", "Austin Freeman"),
    ("Code is like humor. When you have to explain it, it's bad.", "Cory House"),
    ("The only way to do great work is to love what you do.", "Steve Jobs"),
    ("It does not do to dwell on dreams and forget to live.", "J.K. Rowling"),
    ("Whether you think you can or you think you can't, you're right.", "Henry Ford"),
    ("The secret of getting ahead is getting started.", "Mark Twain"),
    ("Done is better than perfect.", "Sheryl Sandberg"),
]


def check_quote() -> str:
    """Random inspirational quote (Quotable, free, keyless) with local fallback."""
    data = _get("https://api.quotable.io/random")
    content = (data or {}).get("content")
    author = (data or {}).get("author")
    if not content:
        import random  # local fallback list (API often offline)
        content, author = random.choice(_QUOTE_FALLBACK)
    return f'"{content}" — {author}' if author else f'"{content}"'
