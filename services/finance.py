"""
finance.py - the service layer the rest of the app actually talks to. Decides which
data source to use, normalizes shapes, and prepares chart-ready series. tool.py calls
this; nothing above tool.py should ever import interface.py directly.
"""
from services import interface as I


def get_snapshot(ticker):
    ticker = ticker.upper().strip()
    try:
        snap = I.yf_snapshot(ticker)
        if snap.get("price"):
            snap["ticker"] = ticker
            snap["source"] = "yfinance"
            return snap
    except Exception:
        pass

    fallback = I.alphavantage_quote(ticker)
    if fallback:
        fallback["ticker"] = ticker
        fallback["source"] = "alphavantage"
        return fallback

    return {"ticker": ticker, "price": None, "source": "unavailable"}


def get_history(ticker, period="6mo", interval="1d"):
    ticker = ticker.upper().strip()
    df = I.yf_history(ticker, period=period, interval=interval)
    series = []
    if not df.empty:
        intraday = interval not in ("1d", "1wk", "1mo")
        for date, row in df.iterrows():
            series.append({
                "date": date.strftime("%Y-%m-%d %H:%M") if intraday else date.strftime("%Y-%m-%d"),
                "time": int(date.timestamp()),
                "open": round(float(row["Open"]), 2),
                "high": round(float(row["High"]), 2),
                "low": round(float(row["Low"]), 2),
                "close": round(float(row["Close"]), 2),
                "volume": int(row["Volume"]) if not pd_isna(row["Volume"]) else 0,
            })
    return {"ticker": ticker, "series": series, "dataframe": df}


def get_history_range(ticker, start, end, interval="1d"):
    """Raw dataframe of real historical closes between two dates, used to
    reconstruct actual past portfolio value from actual trade history."""
    ticker = ticker.upper().strip()
    return I.yf_history_range(ticker, start, end, interval=interval)


def pd_isna(value):
    try:
        return value != value  # NaN check without importing pandas here
    except Exception:
        return False


SECTOR_TICKERS = {
    "Technology": ["AAPL", "MSFT", "NVDA"],
    "Finance": ["GTCO", "JPM", "V"],
    "Healthcare": ["JNJ", "UNH"],
    "Energy": ["SEPLAT", "XOM"],
    "Consumer": ["KO", "AMZN"],
    "Industrials": ["CAT", "BA"],
    "Crypto-adjacent": ["COIN", "MSTR"],
}
DEFAULT_FEED_TICKERS = ["AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "GOOGL", "MTNN", "DANGCEM"]


def get_feed_articles(sectors=None, limit_per_ticker=3, max_articles=24):
    """Pull a broad news feed across the user's chosen sectors, falling back to a
    diverse default set. Each article is tagged with the ticker it came from so
    the feed and the highlight-to-ask flow can carry that context along."""
    tickers = []
    if sectors:
        for s in sectors:
            for t in SECTOR_TICKERS.get(s.strip(), []):
                if t not in tickers:
                    tickers.append(t)
    for t in DEFAULT_FEED_TICKERS:
        if t not in tickers:
            tickers.append(t)

    articles = []
    for ticker in tickers:
        if len(articles) >= max_articles:
            break
        try:
            items = I.yf_news(ticker)[:limit_per_ticker]
        except Exception:
            items = []
        for item in items:
            item["ticker"] = ticker
            articles.append(item)
    return articles[:max_articles]


def get_news(query):
    # if it looks like a ticker, pull ticker-specific news AND run a broader web
    # search so the research desk can speak to context, not just headlines
    candidate = query.strip()
    results = []
    if " " not in candidate and len(candidate) <= 6:
        try:
            results.extend(I.yf_news(candidate.upper()))
        except Exception:
            pass

    web_results = I.web_search(query)
    results.extend(web_results)
    return results
