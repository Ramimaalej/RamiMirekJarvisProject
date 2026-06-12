"""
MARK XL — Local LLM Edition
STT (Whisper / Vosk)  +  Ollama LLM  +  TTS (EdgeTTS / Kokoro / ElevenLabs)
All Gemini / Google-AI dependencies removed.
how to run the project                DISPLAY=:0 /usr/bin/python /home/rami/Téléchargements/Mark-XL-main/main.py
"""
# ── Silence verbose logs + block heavy unused backends ─────────────────────
import os as _os
_os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL",  "3")   # TensorFlow C++ noise
_os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")   # oneDNN banner
_os.environ.setdefault("GRPC_VERBOSITY",         "ERROR")
# USE_TF=0 prevents transformers from importing TensorFlow (saves 4-8 s).
# We intentionally do NOT set USE_TORCH or USE_JAX — forcing those values
# breaks transformers' lazy-loader on some versions (AutoModel disappears
# from the namespace).  Let transformers auto-detect the available backends.
_os.environ.setdefault("USE_TF",                 "0")
_os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
# Offline mode — use cached models, no HuggingFace network calls on startup.
# On first run the model isn't cached yet; tts.py / stt.py detect this and
# temporarily clear these flags to allow the one-time download, then they
# stay in effect for every subsequent launch (fully offline).
_os.environ.setdefault("HF_HUB_OFFLINE",      "1")
_os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
_os.environ.setdefault("HF_DATASETS_OFFLINE",  "1")
import warnings as _warnings
_warnings.filterwarnings("ignore", category=UserWarning)
_warnings.filterwarnings("ignore", category=DeprecationWarning)
_warnings.filterwarnings("ignore", category=FutureWarning)
# ───────────────────────────────────────────────────────────────────────────

# ── Bootstrap: auto-install base UI packages before anything else ──────────
# Uses only stdlib so it works even on a completely fresh Python install.
import importlib.util as _ilu
import subprocess      as _sp
import sys             as _sys

_BASE_PKGS = [
    ("PyQt6",       "PyQt6"),
    ("psutil",      "psutil"),
    ("numpy",       "numpy"),
    ("sounddevice", "sounddevice"),
    ("PIL",         "pillow"),
    ("requests",    "requests"),
]

def _bootstrap() -> None:
    need = [pkg for mod, pkg in _BASE_PKGS if _ilu.find_spec(mod) is None]
    if not need:
        return
    print(f"\n[MARK XL] First-run setup — installing: {', '.join(need)}")
    print("[MARK XL] This happens only once.\n")
    _sp.run([_sys.executable, "-m", "pip", "install", *need], check=True)
    print("\n[MARK XL] Base packages ready — restarting…\n")
    # Replace current process with a fresh one (picks up newly installed packages)
    _os.execv(_sys.executable, [_sys.executable] + _sys.argv)

_bootstrap()
# ───────────────────────────────────────────────────────────────────────────

import json
import queue
import re
import sys
import threading
import traceback
from datetime import datetime
from pathlib import Path

import numpy as np
import sounddevice as sd

from ui import JarvisUI
from memory.memory_manager import load_memory, update_memory, format_memory_for_prompt
from core.llm_client import call_llm, call_llm_stream, get_llm_settings

from memory.vector_memory      import store_memory, store_conversation, get_relevant_context, get_memory_count, search_memory
from skills.skill_loader       import get_skill_for_task, get_active_skill_context, list_skills, reload_skills
from agent.agent_manager       import get_agent_manager, AgentStatus
from core.scheduler            import get_scheduler

from actions.file_processor    import file_processor
from actions.flight_finder     import flight_finder
from actions.open_app          import open_app
from actions.weather_report    import weather_action
from actions.send_message      import send_message
from actions.reminder          import reminder
from actions.computer_settings import computer_settings
from actions.screen_processor  import screen_process
from actions.youtube_video     import youtube_video
from actions.desktop           import desktop_control
from actions.browser_control   import browser_control
from actions.file_controller   import file_controller
from actions.code_helper       import code_helper
from actions.dev_agent         import dev_agent
from actions.web_search        import web_search as web_search_action
from actions.computer_control  import computer_control
from actions.game_updater      import game_updater
from actions.get_location      import get_location
from actions.read_email        import read_email


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


BASE_DIR        = _get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"
PROMPT_PATH     = BASE_DIR / "core" / "prompt.txt"

SAMPLE_RATE_IN = 16_000
BLOCK_SIZE     = 1_024
CHANNELS       = 1

# ── Language detection ─────────────────────────────────────────────────────
_SCRIPT_RANGES = {
    "ar": [(0x0600, 0x06FF), (0x0750, 0x077F), (0x08A0, 0x08FF), (0xFB50, 0xFDFF), (0xFE70, 0xFEFF)],
    "ru": [(0x0400, 0x04FF), (0x0500, 0x052F)],
    "zh": [(0x4E00, 0x9FFF), (0x3400, 0x4DBF)],
    "ja": [(0x3040, 0x309F), (0x30A0, 0x30FF)],
    "ko": [(0xAC00, 0xD7AF)],
    "th": [(0x0E00, 0x0E7F)],
    "he": [(0x0590, 0x05FF)],
    "el": [(0x0370, 0x03FF)],
}

def _detect_script_language(text: str) -> str | None:
    """Detect language from Unicode script ranges. Returns ISO code or None for Latin script."""
    for code, ranges in _SCRIPT_RANGES.items():
        count = 0
        for lo, hi in ranges:
            for c in text:
                if lo <= ord(c) <= hi:
                    count += 1
        if count > len(text) * 0.15:
            return code
    return None

# Allow pyautogui / X11 tools to connect without authorization errors on Linux
import platform as _platform, subprocess as _subprocess
if _platform.system() == "Linux":
    try:
        _subprocess.run(["xhost", "+local:"], capture_output=True, timeout=3)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Tool declarations (Gemini format kept for readability;
# converted to OpenAI/Ollama format by _to_ollama_tools())
# ---------------------------------------------------------------------------

TOOL_DECLARATIONS = [
    {
        "name": "open_app",
        "description": (
            "Opens or launches any application, website, or program on the computer. "
            "ALWAYS use this when the user says: open, launch, start, run, pull up, "
            "or 'open X real quick'. Examples: 'open WhatsApp', 'open Chrome', "
            "'launch Spotify', 'open calculator', 'pull up WhatsApp'. "
            "For TradingView charts pass full app_name like 'tradingview xauusd 1m' "
            "to automatically go to the XAUUSD 1-minute chart. "
            "Supported intervals: 1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w, 1M. "
            "Do NOT use send_message just because the app is a messaging app — "
            "if the user only says to open it, call open_app."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "app_name": {"type": "STRING", "description": "Name of the application or website to open. For TradingView include symbol and timeframe e.g. 'tradingview xauusd 1m'"}
            },
            "required": ["app_name"]
        }
    },
    {
        "name": "web_search",
        "description": "Searches the web for any information.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query":  {"type": "STRING", "description": "Search query"},
                "mode":   {"type": "STRING", "description": "search (default) or compare"},
                "items":  {"type": "ARRAY", "items": {"type": "STRING"}, "description": "Items to compare"},
                "aspect": {"type": "STRING", "description": "price | specs | reviews"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "weather_report",
        "description": "Gives the weather report to user",
        "parameters": {
            "type": "OBJECT",
            "properties": {"city": {"type": "STRING", "description": "City name"}},
            "required": ["city"]
        }
    },
    {
        "name": "send_message",
        "description": (
            "Sends a message to a specific person via WhatsApp, Telegram, or similar. "
            "ONLY use this when the user explicitly provides BOTH a recipient AND message content. "
            "Example triggers: 'text John saying I am late', 'send a WhatsApp to mom that dinner is ready'. "
            "Do NOT call this if the user only wants to open the app without sending a message."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "receiver":     {"type": "STRING", "description": "Recipient contact name"},
                "message_text": {"type": "STRING", "description": "The exact message text to send"},
                "platform":     {"type": "STRING", "description": "Platform: WhatsApp, Telegram, etc."}
            },
            "required": ["receiver", "message_text", "platform"]
        }
    },
    {
        "name": "reminder",
        "description": "Sets a timed reminder using Task Scheduler.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "date":    {"type": "STRING", "description": "Date in YYYY-MM-DD format (not needed for timers)"},
                "time":    {"type": "STRING", "description": "Time in HH:MM format (24h) (not needed for timers)"},
                "message": {"type": "STRING", "description": "Reminder message text"},
                "minutes": {"type": "INTEGER", "description": "Minutes from now for a timer (e.g. 12 = 12 minutes). Use this instead of date/time for timers."}
            },
            "required": []
        }
    },
    {
        "name": "youtube_video",
        "description": (
            "Controls YouTube. Use for: playing videos, summarizing a video's content, "
            "getting video info, or showing trending videos."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "play | summarize | get_info | trending"},
                "query":  {"type": "STRING", "description": "Search query for play action"},
                "save":   {"type": "BOOLEAN", "description": "Save summary to Notepad"},
                "region": {"type": "STRING", "description": "Country code for trending e.g. TR, US"},
                "url":    {"type": "STRING", "description": "Video URL for get_info action"},
            },
            "required": []
        }
    },
    {
        "name": "screen_process",
        "description": (
            "Captures and analyzes the screen or webcam image. "
            "MUST be called when user asks what is on screen, what you see, "
            "analyze my screen, look at camera, etc. "
            "You have NO visual ability without this tool."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "angle": {"type": "STRING", "description": "'screen' or 'camera'. Default: 'screen'"},
                "text":  {"type": "STRING", "description": "The question about the captured image"}
            },
            "required": ["text"]
        }
    },
    {
        "name": "computer_settings",
        "description": (
            "Controls the computer: volume, brightness, window management, keyboard shortcuts, "
            "typing text on screen, closing apps, fullscreen, dark mode, WiFi toggle, restart, shutdown, "
            "scrolling, tab management, zoom, screenshots, lock screen, refresh/reload page, "
            "change language, switch TTS voice, speak in a different language, "
            "send desktop notifications, read/write clipboard, check battery status, check WiFi status."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "The action to perform. Actions: volume_up/down/mute/set, brightness_up/down, lock_screen, sleep_display, toggle_wifi, wifi_status, battery_status, notify, clipboard_read, clipboard_write, restart, shutdown, dark_mode, language/speak, type_text, press_key. Use action='language' or action='speak' to change the TTS voice/language."},
                "description": {"type": "STRING", "description": "Natural language description"},
                "value":       {"type": "STRING", "description": "Optional value — language name/ISO code for language/speak action, or message for notify, or text for clipboard_write"},
                "title":       {"type": "STRING", "description": "Notification title for notify action"},
                "message":     {"type": "STRING", "description": "Notification message for notify action"},
                "urgency":     {"type": "STRING", "description": "Notification urgency: low, normal, or critical (default: normal)"},
                "text":        {"type": "STRING", "description": "Text content for type_text or clipboard_write actions"},
            },
            "required": []
        }
    },
    {
        "name": "browser_control",
        "description": (
            "Controls any web browser. Use for: opening websites, searching the web, "
            "clicking elements, filling forms, scrolling, screenshots, navigation. "
            "For TradingView charts use URL like: https://www.tradingview.com/chart/?symbol=XAUUSD&interval=1"
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "go_to | search | click | type | scroll | fill_form | smart_click | smart_type | get_text | get_url | press | new_tab | close_tab | screenshot | back | forward | reload | switch | list_browsers | close | close_all"},
                "browser":     {"type": "STRING", "description": "chrome | edge | firefox | opera | operagx | brave | vivaldi | safari"},
                "url":         {"type": "STRING", "description": "URL for go_to / new_tab action. For TradingView charts use: https://www.tradingview.com/chart/?symbol=XAUUSD&interval=1 (interval values: 1=1m, 5=5m, 15=15m, 60=1h, 240=4h, D=1d, W=1w, M=1M)"},
                "query":       {"type": "STRING", "description": "Search query"},
                "engine":      {"type": "STRING", "description": "google | bing | duckduckgo | yandex"},
                "selector":    {"type": "STRING", "description": "CSS selector for click/type"},
                "text":        {"type": "STRING", "description": "Text to click or type"},
                "description": {"type": "STRING", "description": "Element description for smart_click/smart_type"},
                "direction":   {"type": "STRING", "description": "up | down for scroll"},
                "amount":      {"type": "INTEGER", "description": "Scroll amount in pixels"},
                "key":         {"type": "STRING", "description": "Key name for press"},
                "path":        {"type": "STRING", "description": "Save path for screenshot"},
                "incognito":   {"type": "BOOLEAN", "description": "Open in private/incognito mode"},
                "clear_first": {"type": "BOOLEAN", "description": "Clear field before typing"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "file_controller",
        "description": "Manages files and folders: list, create, delete, move, copy, rename, read, write, find, disk usage, compress/extract archives, download files from URLs, edit files by string replacement.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "list | create_file | create_folder | delete | move | copy | rename | read | write | find | largest | disk_usage | organize_desktop | info | compress | extract | download | edit"},
                "path":        {"type": "STRING", "description": "File/folder path or shortcut: desktop, downloads, documents, home, or URL for download action"},
                "destination": {"type": "STRING", "description": "Destination path for move/copy, or extract destination"},
                "new_name":    {"type": "STRING", "description": "New name for rename"},
                "content":     {"type": "STRING", "description": "Content for create_file/write"},
                "name":        {"type": "STRING", "description": "File name to search for"},
                "extension":   {"type": "STRING", "description": "File extension to search"},
                "count":       {"type": "INTEGER", "description": "Number of results for largest"},
                "url":         {"type": "STRING", "description": "URL to download from (for download action)"},
                "file_name":   {"type": "STRING", "description": "Output filename for download action"},
                "format":      {"type": "STRING", "description": "Archive format for compress: zip, tar, tar.gz, tgz (default: zip)"},
                "archive_name":{"type": "STRING", "description": "Output archive name for compress action"},
                "old_string":  {"type": "STRING", "description": "Text to replace (for edit action)"},
                "new_string":  {"type": "STRING", "description": "Replacement text (for edit action)"},
                "replace_all": {"type": "BOOLEAN", "description": "Replace all occurrences (for edit action, default: false)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "desktop_control",
        "description": "Controls the desktop: wallpaper, organize, clean, list, stats.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "wallpaper | wallpaper_url | organize | clean | list | stats | task"},
                "path":   {"type": "STRING", "description": "Image path for wallpaper"},
                "url":    {"type": "STRING", "description": "Image URL for wallpaper_url"},
                "mode":   {"type": "STRING", "description": "by_type or by_date for organize"},
                "task":   {"type": "STRING", "description": "Natural language desktop task"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "code_helper",
        "description": "Writes, edits, explains, runs, or builds code files.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "write | edit | explain | run | build | auto"},
                "description": {"type": "STRING", "description": "What the code should do"},
                "language":    {"type": "STRING", "description": "Programming language"},
                "output_path": {"type": "STRING", "description": "Where to save the file"},
                "file_path":   {"type": "STRING", "description": "Path to existing file"},
                "code":        {"type": "STRING", "description": "Raw code string for explain"},
                "args":        {"type": "STRING", "description": "CLI arguments"},
                "timeout":     {"type": "INTEGER", "description": "Execution timeout in seconds"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "dev_agent",
        "description": "Builds complete multi-file projects from scratch.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "description":  {"type": "STRING", "description": "What the project should do"},
                "language":     {"type": "STRING", "description": "Programming language"},
                "project_name": {"type": "STRING", "description": "Optional project folder name"},
                "timeout":      {"type": "INTEGER", "description": "Run timeout in seconds"},
            },
            "required": ["description"]
        }
    },
    {
        "name": "agent_task",
        "description": (
            "Executes complex multi-step tasks requiring multiple different tools. "
            "Examples: 'research X and save to file', 'find and organize files'. "
            "DO NOT use for single commands."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "goal":     {"type": "STRING", "description": "Complete description of what to accomplish"},
                "priority": {"type": "STRING", "description": "low | normal | high"}
            },
            "required": ["goal"]
        }
    },
    {
        "name": "computer_control",
        "description": "Direct computer control: type text INTO A FIELD ON SCREEN, click, hotkeys, scroll, move mouse, screenshots, find elements on screen. NEVER use this to answer questions — only for physical screen actions.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "type | smart_type | click | double_click | right_click | hotkey | press | scroll | move | copy | paste | screenshot | wait | clear_field | focus_window | screen_find | screen_click | random_data | user_data | list_processes | running_apps"},
                "text":        {"type": "STRING", "description": "Text to type or paste"},
                "x":           {"type": "INTEGER", "description": "X coordinate"},
                "y":           {"type": "INTEGER", "description": "Y coordinate"},
                "keys":        {"type": "STRING", "description": "Key combination e.g. 'ctrl+c'"},
                "key":         {"type": "STRING", "description": "Single key e.g. 'enter'"},
                "direction":   {"type": "STRING", "description": "up | down | left | right"},
                "amount":      {"type": "INTEGER", "description": "Scroll amount"},
                "seconds":     {"type": "NUMBER",  "description": "Seconds to wait"},
                "title":       {"type": "STRING",  "description": "Window title for focus_window"},
                "description": {"type": "STRING",  "description": "Element description"},
                "type":        {"type": "STRING",  "description": "Data type for random_data"},
                "field":       {"type": "STRING",  "description": "Field for user_data"},
                "clear_first": {"type": "BOOLEAN", "description": "Clear field before typing"},
                "path":        {"type": "STRING",  "description": "Save path for screenshot"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "run_command",
        "description": (
            "Executes arbitrary shell commands on the user's computer. "
            "Use this for: running terminal commands, installing packages, "
            "managing processes, system administration, git operations, "
            "executing scripts, checking system info. "
            "Can also run inline Python code by passing python3 -c. "
            "Returns stdout, stderr, and exit code."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "command": {"type": "STRING", "description": "Shell command to execute"},
                "timeout": {"type": "INTEGER", "description": "Timeout in seconds (default 60)"},
                "workdir": {"type": "STRING", "description": "Working directory for the command"},
            },
            "required": ["command"]
        }
    },
    {
        "name": "run_python",
        "description": (
            "Executes inline Python code and returns stdout/stderr. "
            "Use this for: running Python scripts, testing code snippets, "
            "data analysis, file operations with Python. "
            "Returns exit code, stdout, and stderr."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "code": {"type": "STRING", "description": "Python code to execute"},
                "timeout": {"type": "INTEGER", "description": "Timeout in seconds (default 30)"},
            },
            "required": ["code"]
        }
    },
    {
        "name": "game_updater",
        "description": (
            "THE ONLY tool for ANY Steam or Epic Games request. "
            "Use for: installing, downloading, updating games, listing installed games."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":    {"type": "STRING",  "description": "update | install | list | download_status | schedule | cancel_schedule | schedule_status"},
                "platform":  {"type": "STRING",  "description": "steam | epic | both"},
                "game_name": {"type": "STRING",  "description": "Game name"},
                "app_id":    {"type": "STRING",  "description": "Steam AppID"},
                "hour":      {"type": "INTEGER", "description": "Hour for scheduled update 0-23"},
                "minute":    {"type": "INTEGER", "description": "Minute for scheduled update 0-59"},
                "shutdown_when_done": {"type": "BOOLEAN", "description": "Shut down PC when done"},
            },
            "required": []
        }
    },
    {
        "name": "flight_finder",
        "description": "Searches Google Flights and speaks the best options.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "origin":      {"type": "STRING",  "description": "Departure city or airport code"},
                "destination": {"type": "STRING",  "description": "Arrival city or airport code"},
                "date":        {"type": "STRING",  "description": "Departure date"},
                "return_date": {"type": "STRING",  "description": "Return date for round trips"},
                "passengers":  {"type": "INTEGER", "description": "Number of passengers"},
                "cabin":       {"type": "STRING",  "description": "economy | premium | business | first"},
                "save":        {"type": "BOOLEAN", "description": "Save results to Notepad"},
            },
            "required": ["origin", "destination", "date"]
        }
    },
    {
        "name": "get_location",
        "description": (
            "Detects and returns the user's current physical location using IP geolocation. "
            "Returns city, region, country, timezone, and coordinates. "
            "Call this when the user asks: where am I, what is my location, detect my location, "
            "find my city, what city am I in, what country am I in, my current location, etc."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {}
        }
    },
    {
        "name": "shutdown_jarvis",
        "description": (
            "Shuts down the assistant completely. "
            "Call this when the user expresses intent to end the conversation, "
            "close the assistant, say goodbye, or stop Jarvis."
        ),
        "parameters": {"type": "OBJECT", "properties": {}}
    },
    {
        "name": "file_processor",
        "description": (
            "Processes any file that the user has uploaded or dropped onto the interface. "
            "Supports: images, PDFs, Word docs, CSV/Excel, JSON, code files, audio, video, archives."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "file_path":   {"type": "STRING",  "description": "Full path to the uploaded file"},
                "action":      {"type": "STRING",  "description": "What to do with the file"},
                "instruction": {"type": "STRING",  "description": "Free-form instruction"},
                "format":      {"type": "STRING",  "description": "Target format for conversion"},
                "width":       {"type": "INTEGER", "description": "Target width for image resize"},
                "height":      {"type": "INTEGER", "description": "Target height for image resize"},
                "scale":       {"type": "NUMBER",  "description": "Scale factor"},
                "quality":     {"type": "INTEGER", "description": "Quality 1-100"},
                "start":       {"type": "STRING",  "description": "Start time for trim"},
                "end":         {"type": "STRING",  "description": "End time for trim"},
                "timestamp":   {"type": "STRING",  "description": "Timestamp for video frame extraction"},
                "column":      {"type": "STRING",  "description": "Column name for CSV filter/sort"},
                "value":       {"type": "STRING",  "description": "Filter value"},
                "condition":   {"type": "STRING",  "description": "Filter condition"},
                "ascending":   {"type": "BOOLEAN", "description": "Sort order"},
                "save":        {"type": "BOOLEAN", "description": "Save result to file"},
                "destination": {"type": "STRING",  "description": "Output folder for archive extract"},
            },
            "required": []
        }
    },
    {
        "name": "calculate",
        "description": (
            "Evaluates any mathematical expression and returns the result. "
            "Use for ALL math questions: arithmetic, percentages, algebra, conversions. "
            "NEVER do math yourself — always call this tool."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "expression": {"type": "STRING", "description": "Math expression to evaluate, e.g. '561+215', '20% of 10000', '15 percent of 200', 'sqrt(144)'"},
            },
            "required": ["expression"]
        }
    },
    {
        "name": "manage_agents",
        "description": (
            "Manages background agents that run autonomously. "
            "Create agents for long-running tasks, monitoring, or scheduled work. "
            "Agents run in the background 24/7. Use: create, list, status, stop, remove."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":       {"type": "STRING", "description": "create | list | status | stop | remove"},
                "name":         {"type": "STRING", "description": "Agent name (required for create)"},
                "goal":         {"type": "STRING", "description": "What the agent should accomplish (required for create)"},
                "instructions": {"type": "STRING", "description": "Special instructions for the agent"},
                "agent_id":     {"type": "STRING", "description": "Agent ID for status/stop/remove"},
                "interval":     {"type": "INTEGER", "description": "Loop interval in seconds (0 = run once, default: 0)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "manage_scheduler",
        "description": (
            "Manages scheduled jobs that run automatically on a timer. "
            "Schedule commands, scripts, or reminders to run at specific times. "
            "Supports: every N seconds/minutes/hours/days, daily at HH:MM, hourly."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":   {"type": "STRING", "description": "add | list | remove"},
                "name":     {"type": "STRING", "description": "Job name (required for add)"},
                "command":  {"type": "STRING", "description": "Command to run (required for add)"},
                "schedule": {"type": "STRING", "description": "Schedule: 'every 5 minutes', 'daily at 09:00', 'hourly', 'every 2 hours'"},
                "job_type": {"type": "STRING", "description": "shell (default) | agent"},
                "job_id":   {"type": "STRING", "description": "Job ID for remove"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "manage_skills",
        "description": (
            "Lists and manages installed skills. Skills provide domain-specific "
            "expertise for complex tasks like project creation, chart analysis, "
            "automation, research, and system administration."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "list | reload"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "search_memory",
        "description": (
            "Searches Jarvis's semantic (vector) memory for relevant past "
            "conversations and stored facts. Use this when you need to recall "
            "something the user said earlier that isn't in the current context."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {"type": "STRING", "description": "What to search for in memory"},
                "top_k": {"type": "INTEGER", "description": "Number of results (default: 5)"},
            },
            "required": ["query"]
        }
    },
    {
        "name": "save_memory",
        "description": (
            "Save a personal fact about the user to permanent long-term memory. "
            "ONLY call this tool if the user EXPLICITLY states a new personal fact about themselves "
            "(like their name, age, city, job, preferences, or goals). "
            "Do NOT call this tool for casual greetings (like 'hi', 'how are you'), questions, or general conversation. "
            "Call SILENTLY alongside your verbal reply — never announce that you are saving."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "category": {
                    "type": "STRING",
                    "description": (
                        "identity (name/age/city/job/school/nationality) | "
                        "preferences (likes/dislikes/habits) | "
                        "projects (active work/goals) | "
                        "relationships (people in their life) | "
                        "wishes (future plans/wants) | "
                        "notes (anything else)"
                    )
                },
                "key":   {"type": "STRING", "description": "Short snake_case key, e.g. 'name', 'age', 'favorite_color'"},
                "value": {"type": "STRING", "description": "Concise value in English"},
            },
            "required": ["category", "key", "value"]
        }
    },
]


# ---------------------------------------------------------------------------
# Convert Gemini-style declarations to OpenAI/Ollama format
# ---------------------------------------------------------------------------

_TYPE_MAP = {
    "OBJECT": "object", "STRING": "string", "ARRAY": "array",
    "INTEGER": "integer", "BOOLEAN": "boolean", "NUMBER": "number",
}


def _convert_type(t: str) -> str:
    return _TYPE_MAP.get(t, t.lower()) if isinstance(t, str) else t


def _convert_props(props: dict) -> dict:
    out = {}
    for k, v in props.items():
        nv = dict(v)
        if "type" in nv:
            nv["type"] = _convert_type(nv["type"])
        if "items" in nv and isinstance(nv["items"], dict):
            nv["items"] = {"type": _convert_type(nv["items"].get("type", "string"))}
        out[k] = nv
    return out


def _to_ollama_tools(decls: list) -> list:
    tools = []
    for d in decls:
        params = d.get("parameters", {})
        new_params: dict = {
            "type":       "object",
            "properties": _convert_props(params.get("properties", {})),
        }
        req = params.get("required")
        if req:
            new_params["required"] = req
        tools.append({
            "type": "function",
            "function": {
                "name":        d["name"],
                "description": d["description"],
                "parameters":  new_params,
            },
        })
    return tools


OLLAMA_TOOLS = _to_ollama_tools(TOOL_DECLARATIONS)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_config() -> dict:
    try:
        with open(API_CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}



_GREETINGS = {
    # English
    "hi", "hello", "hey", "hiya", "yo", "sup", "howdy", "greetings",
    "how are you", "how are you doing", "how's it going", "what's up",
    "whats up", "good morning", "good afternoon", "good evening",
    "good night", "morning", "evening",
    # French
    "bonjour", "salut", "bonsoir",
    # Arabic
    "مرحبا", "أهلا", "السلام عليكم", "اهلا", "هلا", "صباح الخير", "مساء الخير",
    # Spanish / Italian
    "hola", "ciao", "buongiorno",
}

def _is_greeting(text: str) -> bool:
    """Return True if the user's message is a simple greeting with no action intent."""
    t = text.lower().strip().rstrip("!?.,").strip()
    if t in _GREETINGS:
        return True


def calculate(parameters: dict = None) -> str:
    import math as _math
    import re as _re
    expr = (parameters or {}).get("expression", "").strip()
    if not expr:
        return "No expression provided."
    s = expr
    # Temperature conversion: "50 Celsius to Fahrenheit"
    m = _re.match(r'([\d.]+)\s*°?\s*(Celsius|C|Fahrenheit|F)\s*(?:to|in|→)\s*(Celsius|C|Fahrenheit|F)', s, _re.IGNORECASE)
    if m:
        val = float(m.group(1))
        from_unit = m.group(2).upper()
        to_unit = m.group(3).upper()
        if from_unit in ("C", "CELSIUS") and to_unit in ("F", "FAHRENHEIT"):
            return f"{s} = {val * 9/5 + 32}°F"
        elif from_unit in ("F", "FAHRENHEIT") and to_unit in ("C", "CELSIUS"):
            return f"{s} = {(val - 32) * 5/9}°C"
    # Percentage: "20% of 10000", "15 percent of 200"
    m = _re.match(r'([\d.]+)\s*%?\s*(?:percent\s+of|percent|of|out\s+of)\s+([\d.]+)', s, _re.IGNORECASE)
    if m:
        pct = float(m.group(1)); val = float(m.group(2))
        return f"{pct}% of {val} = {val * pct / 100}"
    # Unit conversion: "3.5 gallons to liters"
    m = _re.match(r'([\d.]+)\s*(gallons|liters|pounds|kg|miles|km)\s*(?:to|in|→)\s*(gallons|liters|pounds|kg|miles|km)', s, _re.IGNORECASE)
    if m:
        val = float(m.group(1))
        from_u = m.group(2).lower()
        to_u = m.group(3).lower()
        conversions = {
            ("gallons", "liters"): val * 3.78541,
            ("liters", "gallons"): val / 3.78541,
            ("pounds", "kg"): val * 0.453592,
            ("kg", "pounds"): val / 0.453592,
            ("miles", "km"): val * 1.60934,
            ("km", "miles"): val / 1.60934,
        }
        result = conversions.get((from_u, to_u))
        if result:
            return f"{s} = {result:.4f}"
    # Compound interest: "compound interest on 10000 at 5% for 10 years"
    ci_match = _re.match(r'compound\s+interest\s+(?:on\s+)?(\d+[.,]?\d*)\s*(?:at|of)\s+(\d+[.,]?\d*)\s*%?\s*(?:for|over)\s+(\d+)\s*(?:years?|yrs?)', s, _re.IGNORECASE)
    if ci_match:
        principal = float(ci_match.group(1).replace(',', ''))
        rate = float(ci_match.group(2)) / 100
        years = int(ci_match.group(3))
        total = principal * (1 + rate) ** years
        return f"Compound interest: ${principal:,.2f} at {ci_match.group(2)}% for {years} years = ${total:,.2f}"
    # Strip common prefixes: "Solve for x:", "Solve:", "Calculate:", "What is", etc.
    s_clean = _re.sub(r'^(?:solve|calculate|find|compute|what\s+is)\s+(?:for\s+)?(?:\w+\s*[:.])?\s*', '', s, flags=_re.IGNORECASE).strip().rstrip('?.,;:!')
    # Equation solving: "3x + 7 = 22"
    eq_match = _re.match(r'^([\d\s+\-*/().xX^]+)\s*=\s*([\d\s+\-*/().^]+)$', s_clean)
    if eq_match:
        left_side = eq_match.group(1).strip()
        right_side = eq_match.group(2).strip()
        try:
            # Solve for x: rearrange ax + b = c → x = (c - b) / a
            # Replace x with a variable placeholder for parsing
            left_expr = left_side.replace(' ', '').replace('x', '*x').replace('X', '*x')
            # If it starts with *, remove the leading *
            if left_expr.startswith('*x'):
                left_expr = 'x' + left_expr[2:]
            # Try to evaluate the right side
            safe_globals = {"__builtins__": {}, "sqrt": _math.sqrt, "pi": _math.pi, "e": _math.e}
            right_val = eval(right_side.replace(' ', '').replace('^', '**'), safe_globals, {})
            # Simple linear: ax + b = c → x = (c - b) / a
            # Parse terms: find coefficient of x and constant
            import ast as _ast
            tree = _ast.parse(left_expr, mode='eval')
            # For simple case like "3*x + 7", just substitute and solve
            # Try direct approach: evaluate without x first to find constant
            no_x = left_expr.replace('*x', '*0').replace(' x', ' 0').replace('x', '0')
            # Better: parse coefficients manually
            # Pattern: (a)*x + (b) or (a)x + (b)
            coef_match = _re.match(r'^([\d.]+)\s*(?:\*\s*)?[xX]\s*([+\-])\s*([\d.]+)$|^([\d.]+)\s*([+\-])\s*([\d.]+)\s*(?:\*\s*)?[xX]$', left_side.replace(' ', ''))
            if coef_match:
                groups = coef_match.groups()
                if groups[0] and groups[1] and groups[2]:
                    a, op, b = float(groups[0]), groups[1], float(groups[2])
                    b = -b if op == '-' else b
                    x_val = (right_val - b) / a
                elif groups[3] and groups[4] and groups[5]:
                    b, op, a = float(groups[3]), groups[4], float(groups[5])
                    b = -b if op == '-' else b
                    x_val = (right_val - b) / a
                else:
                    raise ValueError("Unparseable")
                return f"x = {x_val}"
        except Exception:
            pass
    try:
        safe_globals = {"__builtins__": {}, "sqrt": _math.sqrt, "sin": _math.sin, "cos": _math.cos, "tan": _math.tan, "log": _math.log, "log10": _math.log10, "pi": _math.pi, "e": _math.e}
        s_safe = s_clean.replace(" ", "").replace("^", "**")
        # Only replace x with * if between digit and x (e.g., "3x" → "3*x"), not standalone x
        s_safe = _re.sub(r'(\d)x', r'\1*x', s_safe)
        s_safe = _re.sub(r'x(\d)', r'x*\1', s_safe)
        result = eval(s_safe, safe_globals, {})
        return f"{s_clean} = {result}"
    except Exception as e:
        return f"Could not calculate: {e}"


def _load_system_prompt() -> str:
    try:
        return PROMPT_PATH.read_text(encoding="utf-8")
    except Exception:
        return (
            "You are JARVIS, Tony Stark's AI assistant. "
            "Be concise, direct, and always use the provided tools to complete tasks. "
            "Never simulate or guess results — always call the appropriate tool."
        )


# ---------------------------------------------------------------------------
# Voice Activity Detection (used for Whisper listen loop)
# ---------------------------------------------------------------------------

class _VADBuffer:
    """Energy-based VAD: buffers audio until end of utterance."""

    def __init__(
        self,
        sample_rate:    int   = 16_000,
        silence_sec:    float = 0.7,    # silence after last word → send to STT
        speech_thresh:  float = 0.008,  # RMS above this = speech  (0.008 catches voice at 3-4 m; raise if mic picks up too much room noise)
        silence_thresh: float = 0.004,  # RMS below this = silence (half of speech_thresh — hysteresis prevents mid-sentence cuts)
        min_speech_sec: float = 0.3,
        max_speech_sec: float = 30.0,
    ):
        self._sr            = sample_rate
        self._sil_n         = int(silence_sec * sample_rate)
        self._speech_thresh = speech_thresh
        self._sil_thresh    = silence_thresh
        self._min_n         = int(min_speech_sec * sample_rate)
        self._max_n         = int(max_speech_sec * sample_rate)
        self._buf:          list[np.ndarray] = []
        self._in_spch       = False
        self._sil_cnt       = 0
    def process(self, chunk: np.ndarray) -> np.ndarray | None:
        """
        Feed one audio chunk (float32 mono).
        Returns complete utterance when speech ends, otherwise None.

        Uses hysteresis thresholds so the detector doesn't flicker:
          - speech starts when RMS > speech_thresh  (0.008 = ~3-4 m range)
          - speech ends only when RMS < silence_thresh  (0.004 = half of start)
        The gap between the two thresholds prevents mid-sentence cuts on
        natural pauses and quiet consonants.
        """
        rms     = float(np.sqrt(np.mean(chunk ** 2)))
        total_n = sum(len(c) for c in self._buf)

        if rms > self._speech_thresh:
            self._in_spch = True
            self._sil_cnt = 0
            self._buf.append(chunk.copy())
        elif self._in_spch:
            self._buf.append(chunk.copy())
            if rms < self._sil_thresh:
                self._sil_cnt += len(chunk)

            if self._sil_cnt >= self._sil_n or total_n >= self._max_n:
                audio         = np.concatenate(self._buf)
                self._buf     = []
                self._in_spch = False
                self._sil_cnt = 0
                if len(audio) >= self._min_n:
                    return audio
        return None


# ---------------------------------------------------------------------------
# JarvisLocal
# ---------------------------------------------------------------------------

class JarvisLocal:
    """
    Main assistant class.
    Replaces JarvisLive (Gemini Live API) with:
      STT (Whisper/Vosk) → Ollama LLM (tool calling) → TTS (Edge/Kokoro/ElevenLabs)
    """

    def __init__(self, ui: JarvisUI):
        self.ui               = ui
        self._config          = _load_config()
        self._stt             = None
        self._tts             = None
        self._tts_ready       = threading.Event()   # set when TTS engine is loaded
        self._speaking        = False
        self._speaking_lock   = threading.Lock()
        self._text_queue:     queue.Queue = queue.Queue()
        self._tts_queue:      queue.Queue = queue.Queue()
        self._conversation:   list[dict]  = []

        self.ui.on_text_command = self._on_text_command
        self._current_language = "en"

    # ------------------------------------------------------------------
    # Auto-detect and switch TTS language
    # ------------------------------------------------------------------

    def _auto_switch_language(self, text: str) -> None:
        """Detect user language and switch TTS voice if needed."""
        detected = _detect_script_language(text)
        if detected is None:
            return
        if detected == self._current_language:
            return
        if self._tts and hasattr(self._tts, "set_language"):
            ok = self._tts.set_language(detected)
            if ok:
                self._current_language = detected
                lang_name = {
                    "ar": "Arabic", "ru": "Russian", "zh": "Chinese",
                    "ja": "Japanese", "ko": "Korean", "th": "Thai",
                    "he": "Hebrew", "el": "Greek",
                }.get(detected, detected)
                self.ui.write_log(f"SYS: TTS auto-switched to {lang_name}")

    # ------------------------------------------------------------------
    # System prompt
    # ------------------------------------------------------------------

    def _build_system_prompt(self, user_text: str = "") -> str:
        # ── ORDER MATTERS for Ollama KV prefix caching ─────────────────────
        # Ollama caches the KV attention state of any stable prompt prefix.
        # By putting the STATIC JARVIS protocol text FIRST, Ollama reuses its
        # cached KV for all those tokens on every request.  Only the small
        # dynamic tail (memory + time, ~50-80 tokens) needs re-evaluation.
        # This turns a 17-second first-token into a sub-second one after warmup.
        #
        # Rule: static content first → semi-static memory middle → dynamic time LAST.
        sys_p   = _load_system_prompt()               # static — never changes mid-session
        memory  = load_memory()
        mem_str = format_memory_for_prompt(memory)    # semi-static — changes only when user tells facts
        now     = datetime.now()

        # Vector memory — semantically relevant past context
        vec_context = ""
        if user_text:
            vec_context = get_relevant_context(user_text)
            vec_count = get_memory_count()
            if vec_context:
                vec_context = f"[SEMANTIC MEMORY — {vec_count} stored memories]\n{vec_context}"

        # Skills — domain-specific instructions for the current task
        skill_context = ""
        if user_text:
            skill_context = get_active_skill_context(user_text)
            if skill_context:
                skill_context = f"[ACTIVE SKILL]\n{skill_context}"

        # Background agents status
        agent_mgr = get_agent_manager()
        running = agent_mgr.get_running_count()
        agent_info = f"[BACKGROUND AGENTS: {running} running]" if running > 0 else ""

        time_ctx = (
            f"[CURRENT DATE & TIME]\n"
            f"Right now it is: {now.strftime('%A, %B %d, %Y — %I:%M %p')}\n"
            f"Use this to calculate exact times for reminders."
        )
        parts = [sys_p]
        if mem_str:
            parts.append(mem_str)
        if vec_context:
            parts.append(vec_context)
        if skill_context:
            parts.append(skill_context)
        if agent_info:
            parts.append(agent_info)
        parts.append(time_ctx)
        return "\n\n".join(parts)

    # ------------------------------------------------------------------
    # Speaking state & TTS
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # TTS queue worker — plays sentences sequentially, no overlaps
    # ------------------------------------------------------------------

    def _tts_worker(self) -> None:
        # Block until TTS engine is loaded.  Queued items are preserved
        # and played immediately once loading completes — nothing is lost.
        self._tts_ready.wait(timeout=120)

        while True:
            text = self._tts_queue.get()
            try:
                if text and self._tts:
                    with self._speaking_lock:
                        self._speaking = True
                    self.ui.set_state("SPEAKING")
                    self._tts.speak(text)
            except Exception as e:
                print(f"[TTS] speak error: {e}")
            finally:
                self._tts_queue.task_done()
                if self._tts_queue.empty():
                    with self._speaking_lock:
                        self._speaking = False
                    if not self.ui.muted:
                        self.ui.set_state("LISTENING")

    def set_speaking(self, value: bool) -> None:
        with self._speaking_lock:
            self._speaking = value
        if value:
            self.ui.set_state("SPEAKING")
        elif not self.ui.muted:
            self.ui.set_state("LISTENING")

    def speak(self, text: str) -> None:
        if not text or not self._tts:
            return
        with self._speaking_lock:
            self._speaking = True
        self._tts_queue.put(text)

    def speak_error(self, tool_name: str, error) -> None:
        short = str(error)[:120]
        self.ui.write_log(f"ERR: {tool_name} — {short}")
        self.speak(f"{tool_name} encountered an error.")

    # ------------------------------------------------------------------
    # Live reconfigure (called when user clicks Apply in Configure panel)
    # ------------------------------------------------------------------

    def reconfigure(self, new_config: dict) -> None:
        """Non-blocking: spawns a background thread to install + reload."""
        threading.Thread(
            target=self._do_reconfigure, args=(new_config,), daemon=True
        ).start()

    def _do_reconfigure(self, new_config: dict) -> None:
        old_stt_engine = self._config.get("stt_engine", "whisper").lower()
        old_llm_model  = self._config.get("llm_model", "")
        new_stt_engine = new_config.get("stt_engine", "whisper").lower()
        self._config = new_config

        # Install any packages required by the new config
        try:
            from core.installer import install_for_config
            install_for_config(new_config, log=self.ui.write_log)
        except Exception as e:
            self.ui.write_log(f"ERR: Dependency install — {e}")

        # TTS: always hot-reload (runs in queue worker, safe to swap)
        try:
            from core.tts import create_tts_player
            self._tts = create_tts_player(new_config)
            self._tts_ready.set()   # ensure worker isn't blocked
            self.ui.write_log("SYS: TTS reconfigured.")
        except Exception as e:
            self.ui.write_log(f"ERR: TTS reconfigure — {e}")

        # STT: hot-reload if same engine type; full restart needed if engine changed
        if old_stt_engine == new_stt_engine:
            try:
                stt_language = new_config.get("stt_language", "auto")
                if new_stt_engine == "vosk":
                    from core.stt import VoskSTT
                    self._stt = VoskSTT(new_config.get("vosk_model_path"), language=stt_language)
                else:
                    from core.stt import WhisperSTT
                    self._stt = WhisperSTT(new_config.get("stt_model", "base"), language=stt_language)
                self.ui.write_log("SYS: STT reconfigured.")
            except Exception as e:
                self.ui.write_log(f"ERR: STT reconfigure — {e}")
        else:
            self.ui.write_log("SYS: STT engine changed — restart required.")

        # LLM warmup if model changed
        if new_config.get("llm_model", "") != old_llm_model:
            self.ui.write_log("SYS: Warming up new LLM model…")
            from core.llm_client import warmup_model
            warmup_model()
            self.ui.write_log("SYS: New LLM model ready.")

        if old_stt_engine == new_stt_engine:
            self.speak("Configuration applied.")
        else:
            self.speak("LLM and TTS updated. Restart for speech engine change.")

    # ------------------------------------------------------------------
    # Text command (from UI input box)
    # ------------------------------------------------------------------

    def _on_text_command(self, text: str) -> None:
        self._text_queue.put(text)

    # ------------------------------------------------------------------
    # Tool execution (routing unchanged from original)
    # ------------------------------------------------------------------

    def _execute_tool(self, name: str, args: dict) -> str:
        print(f"[JARVIS] 🔧 {name}  {args}")
        self.ui.set_state("THINKING")

        # save_memory is handled silently
        if name == "save_memory":
            category = args.get("category", "notes")
            key      = args.get("key", "")
            value    = args.get("value", "")
            if key and value:
                # Append mode for lists — merge with existing value
                memory  = load_memory()
                existing = memory.get(category, {}).get(key, {}).get("value", "")
                if existing and category in ("notes", "preferences") and any(w in key.lower() for w in ["list", "todo", "grocery", "shopping", "tasks", "items"]):
                    value = existing + "\n- " + value
                    print(f"[Memory] 📋 Appended to {category}/{key}")
                update_memory({category: {key: {"value": value}}})
                print(f"[Memory] 💾 {category}/{key} = {value}")
                # Also store in vector memory for semantic search
                try:
                    threading.Thread(
                        target=store_memory,
                        args=(f"{key}: {value}", category, "fact"),
                        daemon=True
                    ).start()
                except Exception:
                    pass
            if not self.ui.muted:
                self.ui.set_state("LISTENING")
            return "__SILENT__"

        result = "Done."
        try:
            if name == "open_app":
                r = open_app(parameters=args, response=None, player=self.ui)
                result = r or f"Opened {args.get('app_name')}."

            elif name == "weather_report":
                r = weather_action(parameters=args, player=self.ui)
                result = r or "Weather delivered."

            elif name == "browser_control":
                r = browser_control(parameters=args, player=self.ui)
                result = r or "Done."

            elif name == "file_controller":
                r = file_controller(parameters=args, player=self.ui)
                result = r or "Done."

            elif name == "send_message":
                r = send_message(parameters=args, response=None, player=self.ui, session_memory=None)
                result = r or f"Message sent to {args.get('receiver')}."

            elif name == "reminder":
                r = reminder(parameters=args, response=None, player=self.ui)
                result = r or "Reminder set."

            elif name == "youtube_video":
                r = youtube_video(parameters=args, response=None, player=self.ui)
                result = r or "Done."

            elif name == "screen_process":
                # Synchronous call — returns analysis text which the LLM can speak
                r = screen_process(parameters=args, response=None, player=self.ui, session_memory=None)
                result = r if isinstance(r, str) and r else "Screen analyzed."

            elif name == "computer_settings":
                r = computer_settings(parameters=args, response=None, player=self.ui)
                result = r or "Done."

            elif name == "desktop_control":
                r = desktop_control(parameters=args, player=self.ui)
                result = r or "Done."

            elif name == "code_helper":
                r = code_helper(parameters=args, player=self.ui, speak=self.speak)
                result = r or "Done."

            elif name == "dev_agent":
                r = dev_agent(parameters=args, player=self.ui, speak=self.speak)
                result = r or "Done."

            elif name == "agent_task":
                from agent.task_queue import get_queue, TaskPriority
                priority_map = {
                    "low": TaskPriority.LOW,
                    "normal": TaskPriority.NORMAL,
                    "high": TaskPriority.HIGH,
                }
                priority = priority_map.get(
                    args.get("priority", "normal").lower(), TaskPriority.NORMAL
                )
                task_id = get_queue().submit(
                    goal=args.get("goal", ""), priority=priority, speak=self.speak
                )
                result = f"Task started (ID: {task_id})."

            elif name == "web_search":
                r = web_search_action(parameters=args, player=self.ui)
                result = r or "Done."

            elif name == "file_processor":
                if not args.get("file_path") and self.ui.current_file:
                    args["file_path"] = self.ui.current_file
                r = file_processor(parameters=args, player=self.ui, speak=self.speak)
                result = r or "Done."

            elif name == "computer_control":
                r = computer_control(parameters=args, player=self.ui)
                result = r or "Done."

            elif name == "run_command":
                r = computer_control(parameters={
                    "action": "run_command",
                    "command": args.get("command", args.get("text", "")),
                    "timeout": int(args.get("timeout", 60)),
                    "workdir": args.get("workdir"),
                }, player=self.ui)
                result = r or "Done."

            elif name == "run_python":
                r = computer_control(parameters={
                    "action": "run_python",
                    "code": args.get("code", ""),
                    "timeout": int(args.get("timeout", 30)),
                }, player=self.ui)
                result = r or "Done."

            elif name == "game_updater":
                r = game_updater(parameters=args, player=self.ui, speak=self.speak)
                result = r or "Done."

            elif name == "flight_finder":
                r = flight_finder(parameters=args, player=self.ui)
                result = r or "Done."

            elif name == "calculate":
                r = calculate(parameters=args)
                result = r or "Done."

            elif name == "get_location":
                r = get_location(parameters=args, player=self.ui)
                result = r or "Location retrieved."

            elif name == "shutdown_jarvis":
                self.ui.write_log("SYS: Shutdown requested.")

                def _shutdown():
                    import time, os
                    self.speak("Goodbye.")
                    time.sleep(2.5)
                    os._exit(0)

                threading.Thread(target=_shutdown, daemon=True).start()
                return "Shutting down."

            elif name == "manage_agents":
                action = args.get("action", "").lower()
                agent_mgr = get_agent_manager()
                if action == "create":
                    agent = agent_mgr.create_agent(
                        name=args.get("name", "Agent"),
                        goal=args.get("goal", ""),
                        instructions=args.get("instructions", ""),
                    )
                    interval = int(args.get("interval", 0))
                    if interval > 0:
                        agent.start(interval=interval)
                    result = f"Agent '{agent.name}' created (ID: {agent.agent_id}). {'Running every ' + str(interval) + 's.' if interval > 0 else 'Use manage_agents with action=start to run.'}"
                elif action == "start":
                    agent = agent_mgr.get_agent(args.get("agent_id", ""))
                    if agent:
                        agent.start(interval=int(args.get("interval", 0)))
                        result = f"Agent '{agent.name}' started."
                    else:
                        result = "Agent not found."
                elif action == "stop":
                    agent = agent_mgr.get_agent(args.get("agent_id", ""))
                    if agent:
                        agent.stop()
                        result = f"Agent '{agent.name}' stopped."
                    else:
                        result = "Agent not found."
                elif action == "remove":
                    ok = agent_mgr.remove_agent(args.get("agent_id", ""))
                    result = "Agent removed." if ok else "Agent not found."
                elif action in ("list", "status"):
                    agents = agent_mgr.list_agents()
                    if not agents:
                        result = "No background agents."
                    else:
                        lines = [f"Background Agents ({len(agents)}):"]
                        for a in agents:
                            lines.append(f"  [{a['status']}] {a['name']} ({a['agent_id']}) — {a['goal']}")
                        result = "\n".join(lines)
                else:
                    result = f"Unknown action: {action}"

            elif name == "manage_scheduler":
                action = args.get("action", "").lower()
                sched = get_scheduler()
                if action == "add":
                    job_id = sched.add_job(
                        name=args.get("name", "Job"),
                        command=args.get("command", ""),
                        schedule=args.get("schedule", "hourly"),
                        job_type=args.get("job_type", "shell"),
                    )
                    result = f"Job '{args.get('name')}' scheduled (ID: {job_id})."
                elif action == "remove":
                    ok = sched.remove_job(args.get("job_id", ""))
                    result = "Job removed." if ok else "Job not found."
                elif action == "list":
                    jobs = sched.list_jobs()
                    if not jobs:
                        result = "No scheduled jobs."
                    else:
                        lines = ["Scheduled Jobs:"]
                        for j in jobs:
                            enabled = "✓" if j["enabled"] else "✗"
                            lines.append(f"  {enabled} [{j['type']}] {j['name']} — every {j['schedule']} (runs: {j['run_count']})")
                        result = "\n".join(lines)
                else:
                    result = f"Unknown action: {action}"

            elif name == "manage_skills":
                action = args.get("action", "").lower()
                if action == "list":
                    skills = list_skills()
                    if not skills:
                        result = "No skills installed."
                    else:
                        lines = ["Installed Skills:"]
                        for s in skills:
                            lines.append(f"  {s['name']} v{s['version']} — {s['description'][:80]}")
                        result = "\n".join(lines)
                elif action == "reload":
                    skills = reload_skills()
                    result = f"Reloaded {len(skills)} skills."
                else:
                    result = f"Unknown action: {action}"

            elif name == "search_memory":
                query = args.get("query", "")
                top_k = int(args.get("top_k", 5))
                if not query:
                    result = "No query provided."
                else:
                    results = search_memory(query, top_k=top_k)
                    if not results:
                        result = "No relevant memories found."
                    else:
                        lines = [f"Found {len(results)} relevant memories:"]
                        for r in results:
                            lines.append(f"  [{r['category']}] {r['text'][:150]}")
                        result = "\n".join(lines)

            else:
                result = f"Unknown tool: {name}"

        except Exception as e:
            result = f"Tool '{name}' failed: {e}"
            traceback.print_exc()
            self.speak_error(name, e)

        if not self.ui.muted:
            self.ui.set_state("LISTENING")

        print(f"[JARVIS] 📤 {name} → {str(result)[:80]}")
        return result

    # ------------------------------------------------------------------
    # LLM processing loop
    # ------------------------------------------------------------------

    def _process_message(self, user_text: str) -> None:
        """
        Full turn: user_text → LLM stream → TTS (overlapped) → tool execution

        Streaming TTS: sentence events are piped to the TTS queue AS they
        arrive from the LLM, so Kokoro starts synthesising sentence 1 while
        the LLM is still generating sentence 2.  This cuts perceived latency
        from (LLM_total + TTS_total) down to roughly max(LLM_total, TTS_total).

        Tool-call responses never emit sentence events, so the TTS overlap
        only kicks in for pure conversational replies — which is exactly when
        it matters most.
        """
        self._auto_switch_language(user_text)
        self.ui.set_state("THINKING")
        self.ui.write_log(f"You: {user_text}")

        self._conversation.append({"role": "user", "content": user_text})

        MAX_HISTORY = 10
        if len(self._conversation) > MAX_HISTORY:
            self._conversation = self._conversation[-MAX_HISTORY:]

        messages = [
            {"role": "system", "content": self._build_system_prompt(user_text)}
        ] + list(self._conversation)

        # Tools whose output needs a second LLM round to summarise/interpret.
        # Everything else returns a user-ready string → speak directly.
        _NEEDS_LLM_ROUND = {"web_search", "screen_process", "agent_task"}

        # Tools that require clear user intent — never run them for greetings
        _INTENT_TOOLS = {
            "open_app", "computer_control", "computer_settings",
            "send_message", "play_music", "game_updater", "flight_finder",
        }

        MAX_TOOL_ROUNDS = 6
        for _round in range(MAX_TOOL_ROUNDS):
            final_content    = ""
            final_tool_calls: list = []
            # Sentences already queued to TTS during streaming (may be empty
            # for tool-call rounds where the model emits no content).
            _streamed: list[str] = []

            try:
                for event in call_llm_stream(messages, OLLAMA_TOOLS):
                    if event["type"] == "sentence":
                        # ── Overlap TTS with LLM generation ─────────────────
                        # Queue this sentence immediately; the TTS worker
                        # synthesises it while the LLM is still generating
                        # the next one.
                        _streamed.append(event["text"])
                        self.speak(event["text"])
                    elif event["type"] == "done":
                        final_content    = event["content"]
                        final_tool_calls = event["tool_calls"]
            except RuntimeError as e:
                self.speak_error("LLM", e)
                return

            # ── Greeting guard ────────────────────────────────────────────────
            # Small models hallucinate action tool calls for greetings.
            # Strip any intent-requiring tools AND save_memory if user just said hello.
            if final_tool_calls and _round == 0 and _is_greeting(user_text):
                final_tool_calls = [
                    tc for tc in final_tool_calls
                    if tc.get("function", {}).get("name") not in _INTENT_TOOLS
                    and tc.get("function", {}).get("name") != "save_memory"
                ]
                if not final_tool_calls and not final_content:
                    final_content = "Hello! How can I help you?"

            # ── No tool calls: pure conversational reply ─────────────────────
            if not final_tool_calls:
                if _streamed:
                    # Sentences already queued to TTS — just update history/log.
                    assistant_msg = {"role": "assistant", "content": final_content}
                    messages.append(assistant_msg)
                    self._conversation.append(assistant_msg)
                    self.ui.write_log(f"Jarvis: {final_content}")
                elif final_content:
                    # Very short response (no sentence boundary) — speak now.
                    assistant_msg = {"role": "assistant", "content": final_content}
                    messages.append(assistant_msg)
                    self._conversation.append(assistant_msg)
                    self.ui.write_log(f"Jarvis: {final_content}")
                    self.speak(final_content)
                # Store in vector memory
                if final_content:
                    threading.Thread(target=store_conversation, args=(user_text, final_content), daemon=True).start()
                break

            # ── Tool calls present ────────────────────────────────────────────
            assistant_msg = {
                "role":       "assistant",
                "content":    final_content or "",
                "tool_calls": final_tool_calls,
            }
            messages.append(assistant_msg)
            self._conversation.append(assistant_msg)

            # ── Fast path: save_memory + verbal content in same round ────────
            _only_memory = all(
                tc.get("function", {}).get("name") == "save_memory"
                for tc in final_tool_calls
            )
            if _only_memory and final_content:
                for tc in final_tool_calls:
                    fn    = tc.get("function", {})
                    targs = fn.get("arguments", {})
                    if isinstance(targs, str):
                        try:
                            targs = json.loads(targs)
                        except Exception:
                            targs = {}
                    self._execute_tool("save_memory", targs)
                assistant_msg2 = {"role": "assistant", "content": final_content}
                messages.append(assistant_msg2)
                self._conversation.append(assistant_msg2)
                self.ui.write_log(f"Jarvis: {final_content}")
                if not _streamed:
                    self.speak(final_content)
                break

            # ── Execute tools ─────────────────────────────────────────────────
            all_silent    = True
            _tool_results: list[tuple[str, str]] = []

            for tc in final_tool_calls:
                fn    = tc.get("function", {})
                tname = fn.get("name", "")
                targs = fn.get("arguments", {})
                if isinstance(targs, str):
                    try:
                        targs = json.loads(targs)
                    except Exception:
                        targs = {}

                tc_id = tc.get("id", "")
                self.ui.write_log(f"SYS: ▶ {tname}")
                result = self._execute_tool(tname, targs)

                if result != "__SILENT__":
                    all_silent = False
                    _tool_results.append((tname, result))

                tool_msg: dict = {
                    "role":    "tool",
                    "content": "Done." if result == "__SILENT__" else str(result),
                }
                if tc_id:
                    tool_msg["tool_call_id"] = tc_id

                messages.append(tool_msg)
                self._conversation.append(tool_msg)

            # ── Fast-ack: every call was save_memory (silent) ────────────────
            # Instead of saying "Noted.", do a real conversational follow-up.
            if all_silent:
                # Continue the loop — model will now reply conversationally
                # since tool results are already appended to messages.
                continue

            # ── Direct-result: speak tool output, skip LLM round ────────────
            if _tool_results and not any(n in _NEEDS_LLM_ROUND for n, _ in _tool_results):
                _, _reply = _tool_results[-1]
                _amsg = {"role": "assistant", "content": _reply}
                messages.append(_amsg)
                self._conversation.append(_amsg)
                self.ui.write_log(f"Jarvis: {_reply}")
                self.speak(_reply)
                # Store in vector memory
                threading.Thread(target=store_conversation, args=(user_text, _reply), daemon=True).start()
                break

        if not self.ui.muted:
            self.ui.set_state("LISTENING")

    # ------------------------------------------------------------------
    # STT listening loops
    # ------------------------------------------------------------------

    def _listen_whisper(self) -> None:
        """Mic → VAD → Whisper → LLM loop."""
        vad = _VADBuffer()
        q: queue.Queue = queue.Queue(maxsize=200)

        def callback(indata, frames, time_info, status):
            with self._speaking_lock:
                is_speaking = self._speaking
            if not is_speaking and not self.ui.muted:
                try:
                    q.put_nowait(indata.copy())
                except queue.Full:
                    pass

        try:
            with sd.InputStream(
                samplerate=SAMPLE_RATE_IN,
                channels=CHANNELS,
                dtype="float32",
                blocksize=BLOCK_SIZE,
                callback=callback,
            ):
                self.ui.write_log("SYS: Mic active (Whisper STT).")
                while True:
                    try:
                        chunk = q.get(timeout=0.1)
                        audio = vad.process(chunk.flatten())
                        if audio is not None:
                            self.ui.set_state("THINKING")
                            text = self._stt.transcribe(audio)
                            if text.strip():
                                self._process_message(text)
                    except queue.Empty:
                        pass
        except Exception as e:
            print(f"[STT-Whisper] Mic error: {e}")
            traceback.print_exc()

    def _listen_vosk(self) -> None:
        """Mic → Vosk streaming → LLM loop."""
        q: queue.Queue = queue.Queue(maxsize=200)

        def callback(indata, frames, time_info, status):
            with self._speaking_lock:
                is_speaking = self._speaking
            if not is_speaking and not self.ui.muted:
                try:
                    q.put_nowait(indata.copy())
                except queue.Full:
                    pass

        try:
            with sd.InputStream(
                samplerate=SAMPLE_RATE_IN,
                channels=CHANNELS,
                dtype="int16",
                blocksize=4096,
                callback=callback,
            ):
                self.ui.write_log("SYS: Mic active (Vosk STT).")
                while True:
                    try:
                        chunk = q.get(timeout=0.1)
                        text, is_final = self._stt.process_chunk(chunk.tobytes())
                        if is_final and text.strip():
                            self._process_message(text)
                    except queue.Empty:
                        pass
        except Exception as e:
            print(f"[STT-Vosk] Mic error: {e}")
            traceback.print_exc()

    # ------------------------------------------------------------------
    # Text command loop (UI input box)
    # ------------------------------------------------------------------

    def _text_command_loop(self) -> None:
        while True:
            try:
                text = self._text_queue.get(timeout=0.5)
                if text.strip():
                    self._process_message(text)
            except queue.Empty:
                pass

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def run(self) -> None:
        """
        Startup strategy — optimised for minimum time-to-interactive:

        1. LLM warmup + STT load  →  parallel, fast (~3s)
        2. TTS load               →  parallel, slow (~20s for Kokoro)
        3. Wait only for (1)      →  go online immediately
        4. TTS finishes in BG     →  queued speech plays automatically
        """
        try:
            self.ui.on_reconfigure = self.reconfigure

            # ── LLM Server ───────────────────────────────────────────────
            from core.llm_client import ensure_ollama_running, warmup_model, get_llm_provider
            provider = get_llm_provider()
            self.ui.write_log(f"SYS: Checking {provider}…")
            if ensure_ollama_running():
                self.ui.write_log(f"SYS: {provider} OK.")
            else:
                self.ui.write_log(f"ERR: {provider} unavailable.")

            # ── Config ────────────────────────────────────────────────────
            stt_engine   = self._config.get("stt_engine",   "whisper").lower()
            stt_language = self._config.get("stt_language", "auto")
            stt_model    = self._config.get("stt_model",    "base")
            tts_engine   = self._config.get("tts_engine",   "edgetts").lower()

            # ── Startup progress panel ────────────────────────────────────
            self.ui.show_startup_panel()

            _warmup_done = threading.Event()
            _stt_done    = threading.Event()

            # ── LLM warmup thread ─────────────────────────────────────────
            def _do_warmup():
                try:
                    # Pass the STATIC system prompt so Ollama evaluates and caches
                    # its KV state during startup.  Real requests start with the same
                    # static prefix → Ollama reuses cached KV → first token <1 s
                    # instead of the ~17 s it takes to re-evaluate 300+ tokens cold.
                    warmup_model(system_prompt=_load_system_prompt())
                    self.ui.write_log("SYS: LLM ready.")
                    self.ui.mark_startup_ready("llm")
                except Exception as e:
                    self.ui.write_log(f"ERR: LLM warmup — {e}")
                    self.ui.mark_startup_ready("llm", error=True)
                finally:
                    _warmup_done.set()

            # ── STT load thread ───────────────────────────────────────────
            def _do_stt():
                try:
                    self.ui.write_log(f"SYS: Loading {stt_engine.upper()} STT…")
                    if stt_engine == "vosk":
                        from core.stt import VoskSTT
                        self._stt = VoskSTT(
                            self._config.get("vosk_model_path"),
                            language=stt_language,
                        )
                    else:
                        from core.stt import WhisperSTT
                        self._stt = WhisperSTT(stt_model, language=stt_language)
                    self.ui.write_log("SYS: STT ready.")
                    self.ui.mark_startup_ready("stt")
                except Exception as e:
                    self.ui.write_log(f"ERR: STT — {e}")
                    self.ui.mark_startup_ready("stt", error=True)
                finally:
                    _stt_done.set()

            # ── TTS load thread — does NOT block going online ─────────────
            def _do_tts():
                try:
                    self.ui.write_log(f"SYS: Loading {tts_engine.upper()} TTS…")
                    if tts_engine == "kokoro":
                        self.ui.write_log("SYS: Kokoro — loading model + compiling JIT…")
                    from core.tts import create_tts_player
                    self._tts = create_tts_player(self._config)
                    self._tts_ready.set()          # unblock _tts_worker
                    self.ui.write_log("SYS: TTS ready.")
                    self.ui.mark_startup_ready("tts")
                    self.ui.set_startup_status("● All systems ready.")
                    self.ui.hide_startup_panel()
                    self.speak("Jarvis fully online.")
                except Exception as e:
                    import traceback as _tb; _tb.print_exc()
                    self.ui.write_log(f"ERR: TTS — {e}")
                    self.ui.mark_startup_ready("tts", error=True)
                    self._tts_ready.set()

            # Launch all three simultaneously
            self.ui.write_log("SYS: Loading systems in parallel…")
            threading.Thread(target=_do_warmup, daemon=True).start()
            threading.Thread(target=_do_stt,    daemon=True).start()
            threading.Thread(target=_do_tts,    daemon=True).start()

            # ── Wait ONLY for STT + LLM (fast) ────────────────────────────
            _warmup_done.wait(timeout=60)
            _stt_done.wait(timeout=60)

            # ── Start background services ──────────────────────────────────
            def _scheduler_executor(name: str, command: str, job_type: str):
                if job_type == "shell":
                    r = computer_control(parameters={"action": "run_command", "command": command}, player=self.ui)
                    self.ui.write_log(f"SCHED: {name} → {r[:80]}")
                elif job_type == "agent":
                    from agent.executor import AgentExecutor
                    try:
                        r = AgentExecutor().execute(goal=command, speak=self.speak)
                        self.ui.write_log(f"SCHED-AGENT: {name} → {str(r)[:80]}")
                    except Exception as e:
                        self.ui.write_log(f"SCHED-AGENT: {name} failed: {e}")
                else:
                    self.ui.write_log(f"SCHED: Unknown job type '{job_type}' for '{name}'")
            get_scheduler().set_executor(_scheduler_executor)
            get_scheduler().start()
            self.ui.write_log("SYS: Scheduler started.")

            # ── Go online immediately ──────────────────────────────────────
            self.ui.write_log("SYS: JARVIS online.")
            self.ui.set_state("LISTENING")
            self.ui.set_startup_status("● JARVIS online · Voice loading in background…")

            threading.Thread(target=self._tts_worker,        daemon=True).start()
            threading.Thread(target=self._text_command_loop,  daemon=True).start()

            # STT loop — blocks this thread forever
            if stt_engine == "vosk":
                self._listen_vosk()
            else:
                self._listen_whisper()

        except Exception as e:
            self.ui.write_log(f"ERR: Init failed — {e}")
            traceback.print_exc()


# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------

def main() -> None:
    # ── Pre-import torch in background immediately ─────────────────────────
    # By the time the TTS thread starts (~5s from now), torch will already
    # be in sys.modules — removing it from the TTS critical path entirely.
    def _preload_torch():
        try:
            import torch  # noqa: F401  (side-effect import only)
        except Exception:
            pass
    threading.Thread(target=_preload_torch, daemon=True).start()
    # ───────────────────────────────────────────────────────────────────────

    ui = JarvisUI("face.png")

    def runner():
        # 1. Wait until the user completes the setup overlay (first run)
        #    or config already exists (subsequent runs).
        ui.wait_for_api_key()

        # 2. Install any missing engine packages before loading engines.
        #    Progress is streamed to the log panel in real time.
        ui.write_log("SYS: Checking dependencies…")
        cfg = _load_config()
        _install_done = threading.Event()

        def _do_install():
            try:
                from core.installer import install_for_config
                install_for_config(cfg, log=ui.write_log)
            except Exception as e:
                ui.write_log(f"ERR: Dependency install — {e}")
            finally:
                _install_done.set()

        threading.Thread(target=_do_install, daemon=True).start()
        _install_done.wait()   # blocks runner thread; UI remains responsive

        # 3. Start the assistant (loads STT / TTS / LLM).
        jarvis = JarvisLocal(ui)
        try:
            jarvis.run()
        except KeyboardInterrupt:
            print("\n[MARK XL] Shutting down…")

    threading.Thread(target=runner, daemon=True).start()
    ui.root.mainloop()

if __name__ == "__main__":
    main()
