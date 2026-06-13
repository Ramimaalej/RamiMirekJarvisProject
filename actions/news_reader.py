import logging

logger = logging.getLogger("news_reader")

_DEFAULT_FEEDS = {
    "top": "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml",
    "world": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
    "tech": "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml",
    "science": "https://rss.nytimes.com/services/xml/rss/nyt/Science.xml",
    "business": "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml",
}

_FLUXRSS_BASE = "https://api.fluxrss.com"


def _fetch_rss(url: str, limit: int = 5) -> list[dict]:
    try:
        import feedparser

        feed = feedparser.parse(url)
        entries = []
        for entry in feed.entries[:limit]:
            entries.append({
                "title": entry.get("title", ""),
                "link": entry.get("link", ""),
                "published": entry.get("published", ""),
                "summary": entry.get("summary", entry.get("description", "")),
            })
        return entries
    except Exception as exc:
        logger.debug("RSS parse error: %s", exc)
    return []


def news_action(parameters: dict | None = None, player=None) -> str:
    if parameters is None:
        parameters = {}

    topic = (parameters.get("topic") or "top").lower().strip()
    count = int(parameters.get("count", 5))
    feed_url = parameters.get("feed_url", "")

    if not feed_url:
        if topic in _DEFAULT_FEEDS:
            feed_url = _DEFAULT_FEEDS[topic]
        else:
            feed_url = _DEFAULT_FEEDS["top"]

    try:
        import requests as req
        resp = req.get(f"{_FLUXRSS_BASE}/search?q={topic}&count=5", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            items = data.get("articles", data.get("results", []))
            if items:
                lines = [f"📰 {topic.upper()} HEADLINES:"]
                for i, item in enumerate(items[:count], 1):
                    title = item.get("title", "")
                    source = item.get("source", {}).get("name", "")
                    lines.append(f"  {i}. {title} — {source}")
                return "\n".join(lines)
    except Exception:
        pass

    entries = _fetch_rss(feed_url, count)
    if not entries:
        return f"No news found for '{topic}'."

    lines = [f"📰 {topic.upper()} HEADLINES:"]
    for i, entry in enumerate(entries, 1):
        lines.append(f"  {i}. {entry['title']}")
    return "\n".join(lines)
