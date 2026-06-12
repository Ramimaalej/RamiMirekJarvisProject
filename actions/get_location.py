"""
get_location.py — Device-accurate location for JARVIS on Linux.

Priority chain:
  1. GeoClue2  — the GNOME/Linux location daemon (WiFi + GPS positioning).
                 Accurate to street level. Requires the user to allow
                 location access in GNOME Settings → Privacy → Location.
  2. Browser Geolocation (HTML5 API via Playwright) — fallback when
                 GeoClue2 is unavailable.
  3. IP geolocation — last resort, city-level only (may show ISP city,
                 not your actual city).

Reverse geocoding: Nominatim / OpenStreetMap (free, no API key).
"""

from __future__ import annotations
import threading
import requests

from memory.memory_manager import load_memory as _load_memory


_TIMEOUT   = 8   # seconds to wait for a location fix
_REV_TIMEOUT = 5  # seconds for reverse-geocode HTTP request


# ── Reverse geocoding (lat/lon → human address) ───────────────────────────────

def _reverse_geocode(lat: float, lon: float) -> dict:
    """Use Nominatim (OSM) to convert coordinates to a city/country."""
    try:
        r = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"lat": lat, "lon": lon, "format": "json", "zoom": 10},
            headers={"User-Agent": "JARVIS-MarkXL/1.0"},
            timeout=_REV_TIMEOUT,
        )
        if r.status_code == 200:
            d = r.json()
            addr = d.get("address", {})
            city = (
                addr.get("city")
                or addr.get("town")
                or addr.get("village")
                or addr.get("municipality")
                or addr.get("county", "")
            )
            return {
                "city":     city,
                "region":   addr.get("state", ""),
                "country":  addr.get("country", ""),
                "postcode": addr.get("postcode", ""),
            }
    except Exception:
        pass
    return {}


# ── Method 1: GeoClue2 (Linux system location service) ───────────────────────

def _geoclue2_location() -> tuple[float, float] | None:
    """
    Query the GeoClue2 daemon via PyGObject.
    GeoClue2 uses WiFi SSID scanning + Mozilla Location Service / GPS
    for accurate positioning without requiring a hardware GPS chip.

    Requires: python3-gobject  (dnf install python3-gobject)
    The user must allow location access once in:
      GNOME Settings → Privacy → Location Services → ON
    """
    result: list = []
    done  = threading.Event()

    def _worker():
        try:
            import gi
            gi.require_version("Geoclue", "2.0")
            from gi.repository import Geoclue, GLib

            # Run inside its own GLib main context so we don't block the UI
            ctx    = GLib.MainContext.new()
            loop   = GLib.MainLoop.new(ctx, False)

            def _on_notify(*_):
                loop.quit()

            ctx.push_thread_default()
            try:
                simple = Geoclue.Simple.new_sync(
                    "com.markxl.jarvis",          # app ID
                    Geoclue.AccuracyLevel.STREET, # street-level accuracy
                    None,                          # no cancellable
                )
                simple.connect("notify::location", _on_notify)

                loc = simple.get_location()
                if loc is None:
                    # Wait for the first fix (up to _TIMEOUT seconds)
                    import time
                    deadline = time.time() + _TIMEOUT
                    while loc is None and time.time() < deadline:
                        ctx.iteration(may_block=False)
                        time.sleep(0.05)
                        loc = simple.get_location()

                if loc:
                    result.append((
                        loc.get_property("latitude"),
                        loc.get_property("longitude"),
                    ))
            finally:
                ctx.pop_thread_default()
        except Exception as exc:
            print(f"[Location] GeoClue2 error: {exc}")
        finally:
            done.set()

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    done.wait(timeout=_TIMEOUT + 2)

    return result[0] if result else None


# ── Method 2: Browser HTML5 Geolocation (Playwright) ─────────────────────────

def _browser_location() -> tuple[float, float] | None:
    """
    Open a headless browser page and use the HTML5 Geolocation API.
    Playwright must be installed: pip install playwright && playwright install chromium
    """
    try:
        from playwright.sync_api import sync_playwright

        html = """
        <script>
        navigator.geolocation.getCurrentPosition(
            p => document.title = p.coords.latitude + ',' + p.coords.longitude,
            e => document.title = 'ERROR:' + e.message,
            {enableHighAccuracy: true, timeout: 6000}
        );
        </script>"""

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            ctx     = browser.new_context(
                permissions=["geolocation"],
                geolocation=None,          # let the OS supply it
            )
            page = ctx.new_page()
            page.set_content(html)
            page.wait_for_timeout(7000)    # wait up to 7 s for fix
            title = page.title()
            browser.close()

            if title and "," in title and not title.startswith("ERROR"):
                parts = title.split(",")
                return float(parts[0]), float(parts[1])
    except Exception as exc:
        print(f"[Location] Browser geolocation error: {exc}")
    return None


# ── Method 3: IP geolocation (last resort) ────────────────────────────────────

def _ip_location() -> dict | None:
    for url in [
        "https://ipapi.co/json/",
        "http://ip-api.com/json/",
        "https://ipinfo.io/json",
    ]:
        try:
            r = requests.get(url, timeout=5, headers={"User-Agent": "JARVIS-MarkXL/1.0"})
            if r.status_code != 200:
                continue
            d = r.json()
            city = d.get("city") or ""
            if not city:
                continue
            return {
                "city":     city,
                "region":   d.get("region") or d.get("regionName") or "",
                "country":  d.get("country_name") or d.get("country") or "",
                "timezone": d.get("timezone") or "",
                "latitude": d.get("latitude") or d.get("lat") or "",
                "longitude":d.get("longitude") or d.get("lon") or "",
                "isp":      d.get("org") or d.get("isp") or "",
                "ip":       d.get("ip") or d.get("query") or "",
                "source":   "ip",
            }
        except Exception:
            pass
    return None


# ── Public entry point ────────────────────────────────────────────────────────

def get_location(
    parameters: dict | None = None,
    player=None,
    session_memory=None,
) -> str:
    """
    Detect the user's real location.
    Tries GeoClue2 → browser geolocation → IP (last resort).
    """
    data: dict = {}
    source = "unknown"

    # ── Method 1: GeoClue2 ───────────────────────────────────────────────────
    coords = _geoclue2_location()

    # ── Method 2: Browser geolocation ───────────────────────────────────────
    if coords is None:
        _log("GeoClue2 unavailable, trying browser geolocation…", player)
        coords = _browser_location()

    # ── Reverse-geocode device coordinates ───────────────────────────────────
    if coords:
        lat, lon = coords
        geo = _reverse_geocode(lat, lon)
        data = {
            "city":      geo.get("city", ""),
            "region":    geo.get("region", ""),
            "country":   geo.get("country", ""),
            "postcode":  geo.get("postcode", ""),
            "latitude":  round(lat, 4),
            "longitude": round(lon, 4),
            "timezone":  "",
            "source":    "device",
        }
        source = "device (WiFi/GPS)"

    # ── Check memory for user-stated city before IP fallback ────────────────
    if not data or not data.get("city"):
        try:
            mem = _load_memory()
            saved_city = mem.get("identity", {}).get("city", {})
            if isinstance(saved_city, dict):
                saved_city = saved_city.get("value", "")
            if saved_city:
                data = {
                    "city":      saved_city,
                    "region":    "",
                    "country":   "",
                    "latitude":  "",
                    "longitude": "",
                    "source":    "memory",
                }
                source = "saved (you told me)"
                _log(f"Using saved city from memory: {saved_city}", player)
        except Exception as exc:
            print(f"[Location] Memory check failed: {exc}")

    # ── Method 3: IP fallback ────────────────────────────────────────────────
    if not data or not data.get("city"):
        _log("Device location unavailable, falling back to IP geolocation "
             "(may be inaccurate — reflects ISP location).", player)
        ip_data = _ip_location()
        if ip_data:
            data   = ip_data
            source = "IP (approximate)"

    if not data or not data.get("city"):
        msg = (
            "Sir, I was unable to determine your current location. "
            "Please make sure Location Services are enabled in "
            "GNOME Settings → Privacy → Location Services."
        )
        _log(msg, player)
        return msg

    # ── Build spoken response ─────────────────────────────────────────────────
    city    = data.get("city", "")
    region  = data.get("region", "")
    country = data.get("country", "")
    lat     = data.get("latitude", "")
    lon     = data.get("longitude", "")

    location_str = city
    if region and region != city:
        location_str += f", {region}"
    location_str += f", {country}"

    parts = [f"You are currently in {location_str}."]
    if lat and lon:
        parts.append(f"Coordinates: {lat}°N, {lon}°E.")
    if source == "IP (approximate)":
        parts.append(
            "Note: this location is based on your IP address and may "
            "not reflect your exact city."
        )

    msg = " ".join(parts)

    summary = (
        f"Location ({source}): {location_str} | "
        f"Coords: {lat}, {lon}"
    )
    _log(summary, player)

    if session_memory:
        try:
            session_memory.set_last_search(query="get_location", response=summary)
        except Exception:
            pass

    return msg


def _log(message: str, player=None) -> None:
    print(f"[Location] {message}")
    if player:
        try:
            player.write_log(f"JARVIS: {message}")
        except Exception:
            pass
