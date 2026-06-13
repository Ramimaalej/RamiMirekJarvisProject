import requests

_WEATHER_EMOJIS = {
    0: "☀️", 1: "🌤️", 2: "⛅", 3: "☁️",
    45: "🌫️", 48: "🌫️",
    51: "🌦️", 53: "🌦️", 55: "🌦️",
    56: "🌧️", 57: "🌧️",
    61: "🌧️", 63: "🌧️", 65: "🌧️",
    66: "🌧️", 67: "🌧️",
    71: "❄️", 73: "❄️", 75: "❄️", 77: "❄️",
    80: "🌦️", 81: "🌦️", 82: "🌦️",
    85: "❄️", 86: "❄️",
    95: "⛈️", 96: "⛈️", 99: "⛈️",
}

def _geocode(city: str) -> tuple[float, float] | None:
    try:
        r = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 1, "language": "en", "format": "json"},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        if data.get("results"):
            r2 = data["results"][0]
            return r2["latitude"], r2["longitude"]
    except Exception:
        pass
    return None


def weather_action(
    parameters: dict,
    player=None,
    session_memory=None,
) -> str:
    city = (parameters or {}).get("city", "").strip()
    if not city:
        return "Sir, which city do you want the weather for?"

    coords = _geocode(city)
    if not coords:
        return f"Sir, I couldn't find a city named '{city}'."

    lat, lon = coords
    try:
        r = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat,
                "longitude": lon,
                "current": ["temperature_2m", "relative_humidity_2m",
                            "apparent_temperature", "weather_code",
                            "wind_speed_10m", "wind_direction_10m"],
                "daily": ["temperature_2m_max", "temperature_2m_min",
                          "precipitation_sum", "weather_code"],
                "timezone": "auto",
                "forecast_days": 1,
            },
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        return f"Sir, I couldn't fetch the weather: {e}"

    current = data.get("current", {})
    daily = data.get("daily", {})

    temp = current.get("temperature_2m")
    feels = current.get("apparent_temperature")
    humidity = current.get("relative_humidity_2m")
    wind = current.get("wind_speed_10m")
    wcode = current.get("weather_code", 0)
    emoji = _WEATHER_EMOJIS.get(wcode, "")

    parts = [f"Currently {emoji} {temp}°C in {city.title()}, feels like {feels}°C."]
    if humidity is not None:
        parts.append(f"Humidity {humidity}%.")
    if wind is not None:
        parts.append(f"Wind {wind} km/h.")

    if daily:
        high = daily.get("temperature_2m_max", [None])[0]
        low = daily.get("temperature_2m_min", [None])[0]
        precip = daily.get("precipitation_sum", [None])[0]
        if high is not None and low is not None:
            parts.append(f"Today: H{high}°C L{low}°C.")
        if precip and precip > 0:
            parts.append(f"Precipitation {precip}mm.")

    msg = " ".join(parts)
    print(f"[Weather] {msg}")
    return msg
