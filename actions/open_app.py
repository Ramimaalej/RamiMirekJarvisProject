import re
import time
import subprocess
import platform
import shutil
import urllib.parse
from pathlib import Path

try:
    import psutil
    _PSUTIL = True
except ImportError:
    _PSUTIL = False

_SYSTEM = platform.system()

_APP_ALIASES: dict[str, dict[str, str]] = {

    "chrome":             {"Windows": "chrome",                  "Darwin": "Google Chrome",        "Linux": "google-chrome"},
    "google chrome":      {"Windows": "chrome",                  "Darwin": "Google Chrome",        "Linux": "google-chrome"},
    "firefox":            {"Windows": "firefox",                 "Darwin": "Firefox",              "Linux": "firefox"},
    "edge":               {"Windows": "msedge",                  "Darwin": "Microsoft Edge",       "Linux": "microsoft-edge"},
    "brave":              {"Windows": "brave",                   "Darwin": "Brave Browser",        "Linux": "brave-browser"},
    "safari":             {"Windows": "msedge",                  "Darwin": "Safari",               "Linux": "firefox"},
    "opera":              {"Windows": "opera",                   "Darwin": "Opera",                "Linux": "opera"},
    "whatsapp":           {"Windows": "WhatsApp",                "Darwin": "WhatsApp",             "Linux": "https://web.whatsapp.com"},
    "telegram":           {"Windows": "Telegram",                "Darwin": "Telegram",             "Linux": "telegram"},
    "discord":            {"Windows": "Discord",                 "Darwin": "Discord",              "Linux": "discord"},
    "slack":              {"Windows": "Slack",                   "Darwin": "Slack",                "Linux": "slack"},
    "zoom":               {"Windows": "Zoom",                    "Darwin": "zoom.us",              "Linux": "zoom"},
    "teams":              {"Windows": "msteams",                 "Darwin": "Microsoft Teams",      "Linux": "teams"},
    "skype":              {"Windows": "skype",                   "Darwin": "Skype",                "Linux": "skype"},
    "signal":             {"Windows": "signal",                  "Darwin": "Signal",               "Linux": "signal"},
    "spotify":            {"Windows": "Spotify",                 "Darwin": "Spotify",              "Linux": "spotify"},
    "vlc":                {"Windows": "vlc",                     "Darwin": "VLC",                  "Linux": "vlc"},
    "netflix":            {"Windows": "Netflix",                 "Darwin": "Netflix",              "Linux": "firefox"},
    "vscode":             {"Windows": "code",                    "Darwin": "Visual Studio Code",   "Linux": "code"},
    "visual studio code": {"Windows": "code",                    "Darwin": "Visual Studio Code",   "Linux": "code"},
    "code":               {"Windows": "code",                    "Darwin": "Visual Studio Code",   "Linux": "code"},
    "terminal":           {"Windows": "wt",                      "Darwin": "Terminal",             "Linux": "gnome-terminal"},
    "cmd":                {"Windows": "cmd.exe",                 "Darwin": "Terminal",             "Linux": "bash"},
    "powershell":         {"Windows": "powershell.exe",          "Darwin": "Terminal",             "Linux": "bash"},
    "postman":            {"Windows": "Postman",                 "Darwin": "Postman",              "Linux": "postman"},
    "git":                {"Windows": "git-bash",                "Darwin": "Terminal",             "Linux": "bash"},
    "figma":              {"Windows": "Figma",                   "Darwin": "Figma",                "Linux": "figma"},
    "blender":            {"Windows": "blender",                 "Darwin": "Blender",              "Linux": "blender"},
    "word":               {"Windows": "winword",                 "Darwin": "Microsoft Word",       "Linux": "libreoffice --writer"},
    "excel":              {"Windows": "excel",                   "Darwin": "Microsoft Excel",      "Linux": "libreoffice --calc"},
    "powerpoint":         {"Windows": "powerpnt",                "Darwin": "Microsoft PowerPoint", "Linux": "libreoffice --impress"},
    "libreoffice":        {"Windows": "soffice",                 "Darwin": "LibreOffice",          "Linux": "libreoffice"},
    "notepad":            {"Windows": "notepad.exe",             "Darwin": "TextEdit",             "Linux": "gedit"},
    "textedit":           {"Windows": "notepad.exe",             "Darwin": "TextEdit",             "Linux": "gedit"},
    "explorer":           {"Windows": "explorer.exe",            "Darwin": "Finder",               "Linux": "nautilus"},
    "file explorer":      {"Windows": "explorer.exe",            "Darwin": "Finder",               "Linux": "nautilus"},
    "finder":             {"Windows": "explorer.exe",            "Darwin": "Finder",               "Linux": "nautilus"},
    "task manager":       {"Windows": "taskmgr.exe",             "Darwin": "Activity Monitor",     "Linux": "gnome-system-monitor"},
    "settings":           {"Windows": "ms-settings:",            "Darwin": "System Preferences",   "Linux": "gnome-control-center"},
    "calculator":         {"Windows": "calc.exe",                "Darwin": "Calculator",           "Linux": "gnome-calculator"},
    "paint":              {"Windows": "mspaint.exe",             "Darwin": "Preview",              "Linux": "gimp"},
    "instagram":          {"Windows": "Instagram",               "Darwin": "Instagram",            "Linux": "firefox"},
    "tiktok":             {"Windows": "TikTok",                  "Darwin": "TikTok",               "Linux": "firefox"},
    "notion":             {"Windows": "Notion",                  "Darwin": "Notion",               "Linux": "notion"},
    "obsidian":           {"Windows": "Obsidian",                "Darwin": "Obsidian",             "Linux": "obsidian"},
    "capcut":             {"Windows": "CapCut",                  "Darwin": "CapCut",               "Linux": "capcut"},
    "steam":              {"Windows": "steam",                   "Darwin": "Steam",                "Linux": "steam"},
    "epic":               {"Windows": "EpicGamesLauncher",       "Darwin": "Epic Games Launcher",  "Linux": "legendary"},
    "epic games":         {"Windows": "EpicGamesLauncher",       "Darwin": "Epic Games Launcher",  "Linux": "legendary"},
}

# Web-only apps — opened in the default browser via xdg-open / start / open
_WEB_APPS: dict[str, str] = {
    "youtube":        "https://youtube.com",
    "tradingview":    "https://tradingview.com/chart",
    "trading view":   "https://tradingview.com/chart",
    "trading view":    "https://tradingview.com/chart",
    "gmail":           "https://mail.google.com",
    "google":          "https://google.com",
    "google maps":     "https://maps.google.com",
    "maps":            "https://maps.google.com",
    "google drive":    "https://drive.google.com",
    "drive":           "https://drive.google.com",
    "google docs":     "https://docs.google.com",
    "github":          "https://github.com",
    "chatgpt":         "https://chatgpt.com",
    "twitter":         "https://twitter.com",
    "x":               "https://x.com",
    "facebook":        "https://facebook.com",
    "reddit":          "https://reddit.com",
    "linkedin":        "https://linkedin.com",
    "amazon":          "https://amazon.com",
    "netflix":         "https://netflix.com",
    "twitch":          "https://twitch.tv",
    "binance":         "https://binance.com",
    "coinbase":        "https://coinbase.com",
    "whatsapp web":    "https://web.whatsapp.com",
    "messenger":       "https://messenger.com",
    "facebook messenger": "https://messenger.com",
    "outlook":         "https://outlook.com",
    "onedrive":        "https://onedrive.live.com",
    "wikipedia":       "https://en.wikipedia.org/wiki/",
}

# Words that are context clues, not part of the app name (strip these from input)
_STOP_WORDS = {
    "app", "website", "site", "page", "with", "and", "the", "open",
    "launch", "show", "chart", "screen", "window", "tab", "browser",
    "please", "can", "you", "me", "to", "on", "in", "at", "of",
    "for", "a", "an",
}


def _extract_app_name(raw: str) -> str:
    """Strip context words so 'TradingView with XAUUSD chart' → 'TradingView'."""
    words = raw.split()
    # Take words until we hit a known stop word
    clean = []
    for word in words:
        if word.lower() in _STOP_WORDS:
            break
        clean.append(word)
    return " ".join(clean).strip() if clean else raw


def _extract_wikipedia_topic(raw: str) -> str:
    """Extract the Wikipedia article topic from natural language.
    'wikipedia tunisia page' → 'Tunisia'
    'open tunisia wikipedia article' → 'Tunisia'
    'tunisia page on wikipedia' → 'Tunisia'
    'just wikipedia' → ''
    """
    s = raw.lower().strip()
    # Pattern: "wikipedia <topic> ..." or "wiki <topic> ..."
    m = re.search(r'(?:wikipedia|wiki)\s+(.+?)(?:\s+page|\s+article|$)', s)
    if m:
        topic = m.group(1).strip()
        if topic:
            return topic
    # Pattern: "<topic> page on wikipedia" or "<topic> article on wikipedia"
    m = re.search(r'(.+?)\s+(?:page|article)\s+on\s+(?:wikipedia|wiki)', s)
    if m:
        topic = m.group(1).strip()
        if topic:
            return topic
    # Pattern: "<topic> on wikipedia"
    m = re.search(r'(.+?)\s+on\s+(?:wikipedia|wiki)', s)
    if m:
        topic = m.group(1).strip()
        if topic:
            return topic
    # Just "wikipedia" or "wiki" — no topic
    if s in ("wikipedia", "wiki", "open wikipedia", "open wiki"):
        return ""
    return ""


def _find_desktop_app(name: str) -> str:
    """Search .desktop files for an installed app matching the name."""
    if _SYSTEM != "Linux":
        return name
    key = name.lower().strip()
    search_dirs = [
        Path.home() / ".local" / "share" / "applications",
        Path("/usr") / "share" / "applications",
    ]
    seen: set[str] = set()
    for d in search_dirs:
        if not d.is_dir():
            continue
        for f in d.iterdir():
            if not f.suffix == ".desktop":
                continue
            try:
                content = f.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            app_name = ""
            generic_name = ""
            exec_cmd = ""
            keywords = ""
            no_display = False
            for line in content.splitlines():
                line_s = line.strip()
                if line_s.startswith("Name=") and not app_name and "[" not in line_s:
                    app_name = line_s[5:].strip()
                elif line_s.startswith("GenericName=") and not generic_name and "[" not in line_s:
                    generic_name = line_s[12:].strip()
                elif line_s.startswith("Keywords=") and not keywords and "[" not in line_s:
                    keywords = line_s[9:].strip().lower()
                elif line_s.startswith("Exec=") and not exec_cmd:
                    exec_cmd = line_s[5:].strip()
                    exec_cmd = exec_cmd.split("%")[0].strip()
                elif line_s == "NoDisplay=true":
                    no_display = True
            if no_display or (not app_name and not exec_cmd):
                continue
            # Match: name, generic name, or keywords contain the search key
            haystack = (app_name.lower() + " " + generic_name.lower() + " " + keywords)
            if key in haystack:
                canon = app_name.lower()
                if canon not in seen:
                    seen.add(canon)
                    if exec_cmd:
                        binary = exec_cmd.split()[0] if exec_cmd else ""
                        if binary and shutil.which(binary):
                            return exec_cmd
                    return app_name
    return name


def _normalize(raw: str) -> str:
    """Resolve an app name to a command or URL."""
    key = raw.lower().strip()

    # Direct match in desktop aliases
    if key in _APP_ALIASES:
        return _APP_ALIASES[key].get(_SYSTEM, raw)

    # Partial match in desktop aliases
    for alias_key, os_map in _APP_ALIASES.items():
        if alias_key in key or key in alias_key:
            return os_map.get(_SYSTEM, raw)

    # Direct match in web apps
    if key in _WEB_APPS:
        return _WEB_APPS[key]

    # Partial match in web apps
    for alias_key, url in _WEB_APPS.items():
        if alias_key in key or key in alias_key:
            return url

    # Fallback: search installed .desktop files
    return _find_desktop_app(raw)


def _launch_windows(app_name: str) -> bool:

    if shutil.which(app_name) or shutil.which(app_name.split(".")[0]):
        try:
            subprocess.Popen(
                app_name,
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            time.sleep(1.5)
            return True
        except Exception as e:
            print(f"[open_app] subprocess failed: {e}")

    if ":" in app_name:
        try:
            subprocess.Popen(f"start {app_name}", shell=True)
            time.sleep(1.0)
            return True
        except Exception:
            pass

    try:
        import pyautogui
        pyautogui.PAUSE = 0.1
        pyautogui.press("win")
        time.sleep(0.7)
        pyautogui.write(app_name, interval=0.05)
        time.sleep(0.9)
        pyautogui.press("enter")
        time.sleep(2.5)
        return True
    except Exception as e:
        print(f"[open_app] Start Menu search failed: {e}")

    return False


def _launch_macos(app_name: str) -> bool:

    try:
        result = subprocess.run(
            ["open", "-a", app_name],
            capture_output=True, timeout=8
        )
        if result.returncode == 0:
            time.sleep(1.0)
            return True
    except Exception:
        pass

    try:
        result = subprocess.run(
            ["open", "-a", f"{app_name}.app"],
            capture_output=True, timeout=8
        )
        if result.returncode == 0:
            time.sleep(1.0)
            return True
    except Exception:
        pass

    binary = shutil.which(app_name) or shutil.which(app_name.lower())
    if binary:
        try:
            subprocess.Popen(
                [binary],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            time.sleep(1.0)
            return True
        except Exception:
            pass

    try:
        import pyautogui
        pyautogui.hotkey("command", "space")
        time.sleep(0.6)
        pyautogui.write(app_name, interval=0.05)
        time.sleep(0.8)
        pyautogui.press("enter")
        time.sleep(1.5)
        return True
    except Exception as e:
        print(f"[open_app] Spotlight failed: {e}")

    return False


def _launch_linux(app_name: str) -> bool:

    binary = (
        shutil.which(app_name) or
        shutil.which(app_name.lower()) or
        shutil.which(app_name.lower().replace(" ", "-")) or
        shutil.which(app_name.lower().replace(" ", "_"))
    )
    if binary:
        try:
            subprocess.Popen(
                [binary],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            time.sleep(1.0)
            return True
        except Exception:
            pass

    if app_name.startswith("http"):
        try:
            subprocess.run(
                ["xdg-open", app_name],
                capture_output=True, timeout=5
            )
            return True
        except Exception:
            pass

    for desktop_name in [
        app_name.lower(),
        app_name.lower().replace(" ", "-"),
        app_name.lower().replace(" ", ""),
    ]:
        try:
            result = subprocess.run(
                ["gtk-launch", desktop_name],
                capture_output=True, timeout=5
            )
            if result.returncode == 0:
                return True
        except Exception:
            pass

    return False


_OS_LAUNCHERS = {
    "Windows": _launch_windows,
    "Darwin":  _launch_macos,
    "Linux":   _launch_linux,
}

_INTERVAL_MAP = {
    "1m": "1", "3m": "3", "5m": "5", "15m": "15", "30m": "30",
    "1h": "60", "2h": "120", "3h": "180", "4h": "240",
    "1d": "D", "1w": "W", "1M": "M",
}

_TV_KEYWORDS = {"tradingview", "trading", "view", "tv", "chart"}

def _parse_tradingview_params(text: str) -> tuple[str, str | None]:
    """Extract symbol and interval from e.g. 'xauusd 1m' or 'btcusd 4h'."""
    parts = text.lower().split()
    symbol = None
    interval = None
    for p in parts:
        if p in _INTERVAL_MAP:
            interval = _INTERVAL_MAP[p]
        elif p not in _STOP_WORDS and p not in _TV_KEYWORDS and not p.startswith("http"):
            symbol = p.upper()
    if symbol:
        url = f"https://www.tradingview.com/chart/?symbol={symbol}"
        if interval:
            url += f"&interval={interval}"
        return url, symbol
    return "", None

def _open_url(url: str) -> bool:
    """Open a URL in the default browser, cross-platform."""
    try:
        if _SYSTEM == "Linux":
            subprocess.Popen(["xdg-open", url],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif _SYSTEM == "Darwin":
            subprocess.Popen(["open", url])
        else:
            subprocess.Popen(["start", url], shell=True)
        time.sleep(1.5)
        return True
    except Exception as e:
        print(f"[open_app] URL open failed: {e}")
        return False


def open_app(
    parameters=None,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    raw_name = (parameters or {}).get("app_name", "").strip()

    if not raw_name:
        return "No application name provided."

    # Strip context words: 'TradingView with XAUUSD chart' → 'TradingView'
    app_name = _extract_app_name(raw_name)

    launcher = _OS_LAUNCHERS.get(_SYSTEM)
    if launcher is None:
        return f"Unsupported operating system: {_SYSTEM}"

    normalized = _normalize(app_name)
    print(f"[open_app] '{raw_name}' → clean='{app_name}' resolved='{normalized}' ({_SYSTEM})")

    if player:
        player.write_log(f"[open_app] {app_name}")

    # Check if this is TradingView with extra parameters (symbol, interval)
    if "tradingview" in raw_name.lower() or "tradingview" in normalized:
        # Use full raw text to extract symbol/interval from remaining words
        tv_url, symbol = _parse_tradingview_params(raw_name)
        if tv_url:
            # Strip the app name prefix so only params remain
            rest = raw_name.lower()
            for prefix in ("tradingview", "trading view", "tv"):
                rest = rest.replace(prefix, "").strip()
            tv_url2, symbol2 = _parse_tradingview_params(rest)
            final_url = tv_url2 or tv_url
            if _open_url(final_url):
                label = f"TradingView"
                if symbol2:
                    label += f" {symbol2}"
                return f"Opened {label} in your browser."
            return f"Could not open TradingView."

    # Check if this is a Wikipedia request with a topic
    if wikipedia_topic := _extract_wikipedia_topic(raw_name):
        url = f"https://en.wikipedia.org/wiki/{urllib.parse.quote(wikipedia_topic.replace(' ', '_'))}"
        if _open_url(url):
            label = f"Wikipedia - {wikipedia_topic}"
            if player:
                player.write_log(f"[open_app] {label}")
            return f"Opened {label} in your browser."
        return "Could not open Wikipedia."

    try:
        # If resolved to a URL, open directly in browser
        if normalized.startswith("http"):
            if _open_url(normalized):
                return f"Opened {app_name} in your browser."
            return f"Could not open {app_name}."

        # Otherwise try to launch as a native app
        if launcher(normalized):
            return f"Opened {app_name}."
        if normalized.lower() != app_name.lower():
            if launcher(app_name):
                return f"Opened {app_name}."
        return (
            f"Could not open '{app_name}'. "
            "It may not be installed or the name may be different."
        )
    except Exception as e:
        print(f"[open_app] Error: {e}")
        return f"Failed to open {app_name}: {e}"