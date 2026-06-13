import math
import re

import requests

_GEO_TIMEOUT = 5
_NOMINATIM_UA = "JARVIS-MarkXL/1.0"


def _geocode(query: str) -> dict | None:
    try:
        r = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": query, "format": "json", "limit": 1},
            headers={"User-Agent": _NOMINATIM_UA},
            timeout=_GEO_TIMEOUT,
        )
        if r.status_code == 200 and len(r.json()) > 0:
            data = r.json()[0]
            return {
                "lat": float(data["lat"]),
                "lon": float(data["lon"]),
                "display_name": data["display_name"],
                "type": data.get("type", ""),
            }
    except Exception:
        pass
    return None


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def maps_action(parameters: dict | None = None, player=None) -> str:
    if parameters is None:
        parameters = {}
    action = parameters.get("action", "geocode")
    query = parameters.get("query", "")
    origin = parameters.get("origin", "")
    destination = parameters.get("destination", "")

    if action == "geocode" and query:
        result = _geocode(query)
        if not result:
            return f"Could not find: {query}"
        lat, lon = result["lat"], result["lon"]
        name = result["display_name"].split(",")[0]
        return (
            f"{name} is at {lat:.4f}°N, {lon:.4f}°E. "
            f"Full address: {result['display_name']}."
        )

    if action == "distance" and origin and destination:
        o = _geocode(origin)
        d = _geocode(destination)
        if not o:
            return f"Could not find: {origin}"
        if not d:
            return f"Could not find: {destination}"
        km = _haversine_km(o["lat"], o["lon"], d["lat"], d["lon"])
        miles = km * 0.621371
        o_name = o["display_name"].split(",")[0]
        d_name = d["display_name"].split(",")[0]
        return (
            f"{o_name} to {d_name} is approximately {km:.0f} km ({miles:.0f} miles) "
            f"as the crow flies."
        )

    if action == "distance" and query:
        parts = re.split(r"\s+(?:to|from|and)\s+", query, maxsplit=1)
        if len(parts) == 2:
            return maps_action({"action": "distance", "origin": parts[0].strip(), "destination": parts[1].strip()}, player)
        return 'Usage: "distance from A to B"'

    if action == "coords" and query:
        result = _geocode(query)
        if not result:
            return f"Could not find: {query}"
        return f"{result['display_name'].split(',')[0]}: {result['lat']:.4f}°N, {result['lon']:.4f}°E."

    return 'Usage: maps with action="geocode" & query, or action="distance" & origin & destination.'
