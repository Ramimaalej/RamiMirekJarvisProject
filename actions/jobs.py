import json
import os
import urllib.request
import urllib.parse

BASE_URL = "https://data.fantastic.jobs/v1"

def _get_api_key() -> str:
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        cfg = json.loads(open(os.path.join(base, "config", "api_keys.json")).read())
        return cfg.get("fantastic_jobs_api_key", "")
    except Exception:
        return ""

def _fetch_json(url: str, api_key: str) -> dict:
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {api_key}",
        "User-Agent": "Jarvis/1.0",
    })
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))

def job_search(parameters: dict = None, player=None) -> str:
    api_key = _get_api_key()
    if not api_key and player and hasattr(player, 'request_api_key'):
        api_key = player.request_api_key("Fantastic.jobs", "fantastic_jobs_api_key")
    if not api_key:
        return "No Fantastic.jobs API key found. Set 'fantastic_jobs_api_key' in config/api_keys.json."

    params = parameters or {}
    query = params.get("query", "")
    title = params.get("title", "")
    location = params.get("location", "")
    limit = min(int(params.get("limit", 10)), 50)
    remote = params.get("remote", "")

    url_params = {"time_frame": "24h", "limit": limit}
    if query:
        url_params["title"] = query
    if title:
        url_params["title"] = title
    if location:
        url_params["location"] = location
    if remote:
        url_params["ai_work_arrangement"] = remote

    url = f"{BASE_URL}/active-ats?{urllib.parse.urlencode(url_params)}"
    try:
        data = _fetch_json(url, api_key)
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return "Fantastic.jobs API key is invalid or missing."
        return f"Job search failed (HTTP {e.code})."
    except urllib.error.URLError:
        return "Could not reach Fantastic.jobs API."

    if not isinstance(data, list) or not data:
        return "No jobs found matching your criteria."

    lines = [f"Jobs found ({len(data)}):"]
    for i, job in enumerate(data[:limit], 1):
        org = job.get("organization", job.get("org_linkedin_name", "?"))
        loc = ", ".join(job.get("cities_derived", [])) or job.get("locations_derived", [{}])[0].get("text", "") if isinstance(job.get("locations_derived"), list) and job.get("locations_derived") else "?"
        location_str = loc[:60] if isinstance(loc, str) else str(loc)[:60]
        lines.append(f"  {i}. {job.get('title', '?')} @ {org} ({location_str})")

    return "\n".join(lines)

def job_search_action(parameters: dict = None, **kwargs) -> str:
    return job_search(parameters, player=kwargs.get('player'))
