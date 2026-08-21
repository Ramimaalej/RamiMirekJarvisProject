import requests
import logging

logger = logging.getLogger(__name__)

def get_latest_news(parameters: dict | None = None, player=None) -> str:
    parameters = parameters or {}
    topic = (parameters.get("topic") or "general").strip()
    
    try:
        # Using a free news aggregator or direct RSS parsing (here simple mock/public api)
        # For real use, NewsAPI.org or similar would be better
        url = f"https://saurav.tech/NewsAPI/top-headlines/category/{topic}/us.json"
        resp = requests.get(url, timeout=10)
        data = resp.json()
        articles = data.get("articles", [])[:5]
        
        if not articles:
            return f"No news found for topic '{topic}'."
            
        lines = [f"- {a['title']} ({a['source']['name']})" for a in articles]
        return f"Top {topic} news:\n" + "\n".join(lines)
    except Exception as e:
        return f"Could not fetch news: {e}"
