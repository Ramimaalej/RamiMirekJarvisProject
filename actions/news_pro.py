import requests
import logging

logger = logging.getLogger(__name__)

def get_latest_news(parameters: dict | None = None, player=None) -> str:
    parameters = parameters or {}
    query = (parameters.get("query") or parameters.get("topic") or "general").lower().strip()
    
    # Map common queries to categories
    category = "general"
    if any(w in query for w in ["tech", "informatique", "technologie"]): category = "technology"
    elif any(w in query for w in ["business", "economie", "argent"]): category = "business"
    elif any(w in query for w in ["sport", "foot", "tennis"]): category = "sports"
    elif any(w in query for w in ["science", "espace"]): category = "science"
    elif any(w in query for w in ["health", "sante", "medecine"]): category = "health"
    elif any(w in query for w in ["entertainment", "cinema", "musique", "star"]): category = "entertainment"

    try:
        # Priority 1: Public News API (Saurav)
        url = f"https://saurav.tech/NewsAPI/top-headlines/category/{category}/us.json"
        resp = requests.get(url, timeout=10)
        data = resp.json()
        articles = data.get("articles", [])[:8]
        
        if not articles:
            # Priority 2: Google News RSS fallback (simplified)
            return f"I couldn't find live news for '{query}' right now. Please try a general category like 'tech' or 'business'."
            
        lines = []
        for a in articles:
            title = a.get('title', 'No title')
            source = a.get('source', {}).get('name', 'Unknown')
            lines.append(f"• {title} [{source}]")
            
        header = f"LATEST {category.upper()} NEWS (MARK XL LIVE FEED):"
        return f"{header}\n\n" + "\n".join(lines)
    except Exception as e:
        return f"News feed error: {e}. Please check your internet connection."
