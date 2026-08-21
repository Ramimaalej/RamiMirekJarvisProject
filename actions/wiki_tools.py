import requests
import logging

logger = logging.getLogger(__name__)

def search_wikipedia(parameters: dict | None = None, player=None) -> str:
    parameters = parameters or {}
    query = (parameters.get("query") or "").strip()
    lang = (parameters.get("lang") or "en").strip()
    
    if not query:
        return "What should I search on Wikipedia?"
        
    try:
        url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{query.replace(' ', '_')}"
        resp = requests.get(url, timeout=10)
        if resp.status_code == 404:
            return f"No Wikipedia page found for '{query}'."
        data = resp.json()
        extract = data.get("extract", "No summary available.")
        link = data.get("content_urls", {}).get("desktop", {}).get("page", "")
        return f"Wikipedia: {extract}\nRead more: {link}"
    except Exception as e:
        return f"Wikipedia search failed: {e}"
