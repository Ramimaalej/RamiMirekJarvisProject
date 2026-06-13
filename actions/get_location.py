"""
get_location.py — Device-accurate location for JARVIS on Linux.

Priority chain:
  1. GeoClue2  — GNOME/Linux location daemon (WiFi + GPS).
  2. NetworkManager (nmcli) — reads the WiFi AP your laptop is connected
                to, then resolves it via geolocation APIs.
  3. IP geolocation — last resort, city-level.

Reverse geocoding: Nominatim / OpenStreetMap (free, no API key).
"""

from __future__ import annotations
import subprocess
import threading
import re
import requests

from memory.memory_manager import load_memory as _load_memory

# ── Module-level cache so we don't re-fetch every time ────────────────────
_LOC_CACHE: dict | None = None

_TIMEOUT    = 8
_REV_TIMEOUT = 5


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


# ── Method 2: NetworkManager (nmcli) — WiFi AP → geolocation ──────────────

def _nmcli_location() -> dict | None:
    """
    Get your laptop's location by reading the connected WiFi AP info
    via nmcli, then looking up the BSSID in a geolocation API.
    """
    try:
        # Get active connection info (no root needed)
        out = subprocess.check_output(
            ["nmcli", "-t", "-f", "NAME,TYPE,DEVICE", "connection", "show", "--active"],
            timeout=8, stderr=subprocess.DEVNULL,
        ).decode("utf-8", errors="replace")

        wifi_conn = None
        for line in out.strip().split("\n"):
            parts = line.split(":")
            if len(parts) >= 2 and parts[1] == "wifi":
                wifi_conn = parts[0]
                break

        if not wifi_conn:
            return None

        # Get BSSID from the active WiFi connection
        out2 = subprocess.check_output(
            ["nmcli", "-t", "-f", "GENERAL.HWADDR", "connection", "show", wifi_conn],
            timeout=8, stderr=subprocess.DEVNULL,
        ).decode("utf-8", errors="replace").strip()

        bssid = out2.split(":")[-1].strip() if ":" in out2 else None
        if not bssid:
            return None

        # Try to look up via Unwired Labs geolocation API
        try:
            r = requests.post(
                "https://us1.unwiredlabs.com/v2/process",
                json={"wifi": [{"bssid": bssid}], "address": 1},
                timeout=5,
            )
            if r.status_code == 200:
                d = r.json()
                if d.get("status") == "ok":
                    lat = d.get("lat")
                    lon = d.get("lon")
                    if lat and lon:
                        geo = _reverse_geocode(lat, lon)
                        return {
                            "city":     geo.get("city", ""),
                            "region":   geo.get("region", ""),
                            "country":  geo.get("country", ""),
                            "latitude": lat,
                            "longitude": lon,
                            "timezone": "",
                            "source":   "wifi",
                            "bssid":    bssid,
                        }
        except Exception:
            pass
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.CalledProcessError):
        pass
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
    force_refresh: bool = False,
) -> str:
    """
    Detect the user's real location.
    Tries GeoClue2 → nmcli WiFi → saved memory → IP (last resort).
    Caches the result so subsequent calls are instant.
    Pass force_refresh=True to re-detect.
    """
    global _LOC_CACHE

    if _LOC_CACHE is not None and not force_refresh:
        data, source = _LOC_CACHE
        _log(f"Location from cache: {data.get('city', '')}", player)
        return _format_location(data, source)

    data: dict = {}
    source = "unknown"

    # ── Method 1: GeoClue2 (GPS/WiFi positioning) ────────────────────────────
    coords = _geoclue2_location()

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
            "source":    "gps",
        }
        source = "GPS/WiFi"

    # ── Method 2: NetworkManager (nmcli) WiFi BSSID → geolocation API ───────
    if not data.get("city"):
        _log("Trying WiFi-based geolocation via nmcli…", player)
        wifi_data = _nmcli_location()
        if wifi_data and wifi_data.get("city"):
            data   = wifi_data
            source = "WiFi (BSSID lookup)"

    # ── Check memory for user-stated city ───────────────────────────────────
    if not data.get("city"):
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
                source = "saved memory"
                _log(f"Using saved city from memory: {saved_city}", player)
        except Exception as exc:
            print(f"[Location] Memory check failed: {exc}")

    # ── Method 3: IP fallback ────────────────────────────────────────────────
    if not data.get("city"):
        _log("Falling back to IP geolocation (may be approximate).", player)
        ip_data = _ip_location()
        if ip_data:
            data   = ip_data
            source = "IP (approximate)"

    if not data.get("city"):
        msg = (
            "Unable to determine your location. Please enable Location "
            "Services (GNOME Settings → Privacy → Location) or make sure "
            "you're connected to WiFi."
        )
        _log(msg, player)
        return msg

    # ── Cache and return ─────────────────────────────────────────────────────
    _LOC_CACHE = (data, source)
    return _format_location(data, source)


def _format_location(data: dict, source: str) -> str:
    city    = data.get("city", "")
    region  = data.get("region", "")
    country = data.get("country", "")
    lat     = data.get("latitude", "")
    lon     = data.get("longitude", "")

    location_str = city
    if region and region != city:
        location_str += f", {region}"
    if country:
        location_str += f", {country}"

    parts = [f"You are currently in {location_str}."]
    if lat and lon:
        try:
            parts.append(f"Coordinates: {float(lat):.4f}°N, {float(lon):.4f}°E.")
        except (ValueError, TypeError):
            pass
    if "approximate" in source:
        parts.append("This is based on your IP address and may not be exact.")

    msg = " ".join(parts)
    summary = f"Location ({source}): {location_str} | Coords: {lat}, {lon}"
    _log(summary, None)
    return msg


def _log(message: str, player=None) -> None:
    print(f"[Location] {message}")
    if player:
        try:
            player.write_log(f"JARVIS: {message}")
        except Exception:
            pass
