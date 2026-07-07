"""
interface.py - low-level market data interface. Talks directly to yfinance (primary,
free, no key) and Alpha Vantage (fallback, free tier, needs key). Nothing here knows
about the app's domain concepts (theses, memory, verification) - it only fetches and
normalizes raw market data. services/finance.py is the layer that gives this meaning.
"""
import os
import requests
import yfinance as yf

ALPHAVANTAGE_KEY = os.environ.get("ALPHAVANTAGE_API_KEY", "")
ALPHAVANTAGE_BASE = "https://www.alphavantage.co/query"


def yf_snapshot(ticker):
    t = yf.Ticker(ticker)
    fast = t.fast_info
    price = float(fast.get("last_price")) if fast.get("last_price") else None

    if price is None:
        # fast_info occasionally comes back thin, fall back to the last close from
        # a short history pull rather than declaring the price unavailable too eagerly
        try:
            hist = t.history(period="5d", interval="1d")
            if not hist.empty:
                price = float(hist["Close"].iloc[-1])
        except Exception:
            pass

    return {
        "price": price,
        "previous_close": float(fast.get("previous_close")) if fast.get("previous_close") else None,
        "day_high": float(fast.get("day_high")) if fast.get("day_high") else None,
        "day_low": float(fast.get("day_low")) if fast.get("day_low") else None,
        "volume": int(fast.get("last_volume")) if fast.get("last_volume") else None,
        "currency": fast.get("currency"),
    }


def yf_history(ticker, period="6mo", interval="1d"):
    t = yf.Ticker(ticker)
    df = t.history(period=period, interval=interval)
    return df


def yf_history_range(ticker, start, end, interval="1d"):
    """Historical closes between two dates. yfinance treats `end` as exclusive, so a
    single-day range (start == end, e.g. a position opened today) returns nothing and
    yfinance misreports it as a delisting. Padding end by one day fixes that without
    changing the actual data returned for longer ranges."""
    import datetime as dt
    padded_end = end + dt.timedelta(days=1)
    t = yf.Ticker(ticker)
    return t.history(start=start, end=padded_end, interval=interval)


def yf_news(ticker):
    t = yf.Ticker(ticker)
    try:
        raw = t.news or []
    except Exception:
        raw = []
    items = []
    for n in raw[:8]:
        content = n.get("content", n)  # yfinance news schema has shifted across versions
        title = content.get("title") or n.get("title")
        summary = content.get("summary") or n.get("summary") or ""
        link = (content.get("canonicalUrl") or {}).get("url") if isinstance(content.get("canonicalUrl"), dict) else n.get("link")
        if title:
            items.append({"title": title, "summary": summary, "link": link})
    return items


def web_search(query, max_results=6):
    """Real web search, no API key required. This is what lets research answer
    open questions instead of only what yfinance happens to have on a ticker."""
    from ddgs import DDGS
    try:
        with DDGS() as ddgs:
            raw = list(ddgs.text(query, max_results=max_results))
    except Exception:
        return []
    results = []
    for r in raw:
        results.append({
            "title": r.get("title", ""),
            "summary": r.get("body", ""),
            "link": r.get("href") or r.get("link"),
        })
    return results


def alphavantage_quote(ticker):
    if not ALPHAVANTAGE_KEY:
        return None
    params = {"function": "GLOBAL_QUOTE", "symbol": ticker, "apikey": ALPHAVANTAGE_KEY}
    resp = requests.get(ALPHAVANTAGE_BASE, params=params, timeout=15)
    if resp.status_code != 200:
        return None
    data = resp.json().get("Global Quote", {})
    if not data:
        return None
    return {
        "price": float(data.get("05. price", 0)) or None,
        "previous_close": float(data.get("08. previous close", 0)) or None,
        "volume": int(float(data.get("06. volume", 0))) or None,
    }
