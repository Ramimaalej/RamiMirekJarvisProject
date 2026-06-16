import urllib.request
import urllib.parse
import json

BASE_URL = "https://openlibrary.org"

def _fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "Jarvis/1.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))

def book_search(parameters: dict = None, **kwargs) -> str:
    params = parameters or {}
    query = params.get("query", "")
    title = params.get("title", "")
    author = params.get("author", "")

    if not query:
        parts = []
        if title:
            parts.append(f"title={urllib.parse.quote(title)}")
        if author:
            parts.append(f"author={urllib.parse.quote(author)}")
        if parts:
            query = "&".join(parts)
        else:
            return "No search query provided."

    if "title=" not in query and "author=" not in query and "q=" not in query:
        query = f"q={urllib.parse.quote(query)}"

    url = f"{BASE_URL}/search.json?{query}&limit=5"
    data = _fetch_json(url)

    docs = data.get("docs", [])
    if not docs:
        return f"No books found for: {query}"

    lines = [f"Books found ({len(docs)}):"]
    for b in docs:
        t = b.get("title", "?")
        a = ", ".join(b.get("author_name", ["?"]))
        y = b.get("first_publish_year", "?")
        k = b.get("key", "")
        lines.append(f"  {t} by {a} ({y})")

    return "\n".join(lines)

def book_info(parameters: dict = None, **kwargs) -> str:
    params = parameters or {}
    key = params.get("key", "")
    if not key:
        return "No book key provided."

    url = f"{BASE_URL}{key}.json"
    data = _fetch_json(url)

    title = data.get("title", "?")
    authors_data = data.get("authors", [])
    authors = []
    for a in authors_data:
        ak = a.get("author", {}).get("key", "")
        if ak:
            try:
                au = _fetch_json(f"{BASE_URL}{ak}.json")
                authors.append(au.get("name", "?"))
            except Exception:
                authors.append("?")
    desc = data.get("description", "")
    if isinstance(desc, dict):
        desc = desc.get("value", "")
    subjects = ", ".join(data.get("subjects", [])[:5])

    lines = [f"Title: {title}"]
    if authors:
        lines.append(f"Author(s): {', '.join(authors)}")
    if desc:
        shortened = desc[:500] + "..." if len(desc) > 500 else desc
        lines.append(f"Description: {shortened}")
    if subjects:
        lines.append(f"Subjects: {subjects}")

    return "\n".join(lines)

BOOK_ACTION_MAP = {
    "search": book_search,
    "info": book_info,
    "query": book_search,
}

def book_controller(parameters: dict = None, **kwargs) -> str:
    params = parameters or {}
    action = params.get("action", "search").lower().strip()
    handler = BOOK_ACTION_MAP.get(action, book_search)
    return handler(parameters, **kwargs)
