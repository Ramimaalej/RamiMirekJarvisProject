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

import asyncio
import json
import logging
import queue
import re
import sys
import threading
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import sounddevice as sd

logger = logging.getLogger(__name__)

from ui import JarvisUI
from memory.memory_manager import load_memory, update_memory, format_memory_for_prompt
from core.llm_client import call_llm_stream, invalidate_config_cache

from memory.vector_memory      import store_memory, store_conversation, get_relevant_context, get_memory_count, search_memory
from skills.skill_loader       import get_active_skill_context, list_skills, reload_skills
from agent.agent_manager       import get_agent_manager
from core.scheduler            import get_scheduler
from core.safe_math            import safe_math

from actions.file_processor    import file_processor
from actions.flight_finder     import flight_finder
from actions.open_app          import open_app
from actions.fcc_runner        import run_fcc_in_folder
from actions.dashboard         import (
    add_to_dashboard,
    remove_from_dashboard,
    list_dashboard,
    open_dashboard,
    log_usage as dashboard_log_usage,
)
from actions.weather_report    import weather_action
from actions.maps              import maps_action
from actions.stock_prices      import stock_price_action
from actions.news_reader       import news_action
from actions.get_datetime      import get_datetime
from actions.send_message      import send_message
from actions.reminder          import reminder
from actions.computer_settings import computer_settings
from actions.screen_processor  import screen_process
from actions.youtube_video     import youtube_video
from actions.desktop           import desktop_control
from actions.browser_control   import browser_control
from actions.books            import book_controller
from actions.jobs             import job_search_action
from actions.file_controller   import file_controller
from actions.code_helper       import code_helper
from actions.dev_agent         import dev_agent
from actions.web_search        import web_search as web_search_action
from actions.computer_control  import computer_control
from actions.game_updater      import game_updater
from actions.get_location      import get_location
from actions.browser_use_agent import run_browser_use_task
from actions.screen_reader     import get_ui_elements, get_active_window_info
from actions.face_recognition  import detect_faces, analyze_camera_feed
from actions.wake_word         import start_wake_word, stop_wake_word
from actions.github_integration import _get_client as _get_gh_client
from actions.github_integration import clone_and_run
from actions.file_search       import search_files
from actions.finance_tracker   import _get_client as _get_finance_client
from actions.network_discovery import discover_services, get_local_ips
from actions.voice_calls       import _get_client as _get_lk_client
from actions.monitor_manager   import get_monitors, get_monitor_summary, set_monitor_brightness, get_active_monitor
from actions.obsidian_vault    import save_note, search_notes, list_notes, create_knowledge_graph, set_vault_path, get_all_tags
from actions.package_manager   import install_package, uninstall_package, list_installed, update_all, detect_os_package_manager
from actions.goal_engine       import create_goal, list_goals, get_goal, update_goal_progress, complete_step, delete_goal, get_goal_summary
from actions.task_manager     import task_manager, budget_manager, add_task, complete_task, delete_task, list_tasks, add_transaction, list_transactions, budget_summary
from actions.screen_explain   import screen_explain
from actions.comfyui          import generate_image
from actions.file_converter    import convert_file
from actions.random_number     import random_number
from actions.system_info       import system_info
from actions.unit_converter    import convert_units
from actions.timer_scheduler  import handle as timer_handle, set_on_fire as timer_set_callback
from actions.task_graph        import create_task, complete_task, get_available_tasks, get_task_graph_summary, get_critical_path, delete_task, reset_graph
from actions.security_vault    import store_secret, get_secret, list_secrets, delete_secret
from actions.context_bus       import get_bus, get_context, get_all_context
from actions.project_scaffold import scaffold_project
from actions.project_init     import handle as project_init_handle
from actions.projectinitializer import handle as project_initializer_handle
from actions.relationship_graph import (
    add_node, remove_node, add_edge, remove_edge,
    get_related, resolve_deployment, get_graph_summary,
)
from actions.realtime_tutor    import realtime_tutor, stop_tutor
from actions.email_reader      import read_emails
from actions.habit_actions     import handle as handle_habit
from actions.forensics         import file_history, process_history, network_history, what_installed_since, get_forensics_summary
from actions.google_workspace import google_workspace_action
from actions.remote_control    import remote_control
from actions.federation        import federation
from actions.intent_router     import route as route_intent
from actions.hermes_agent     import hermes_task as hermes_agent_task
from gws_bridge                import (
    get_unread_emails as gws_get_unread_emails,
    search_emails as gws_search_emails,
    send_email as gws_send_email,
    reply_email as gws_reply_email,
    get_todays_agenda,
    get_upcoming_events,
    create_event,
    delete_event,
    search_files,
    upload_file,
    create_doc,
    create_meet,
    is_authenticated as gws_is_authenticated,
    GwsError,
)


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
        "description": "CRITICAL: Use for ANY real-world, factual, or current-information question. Sports scores, match results, news, history, science, definitions, people, prices, live events, statistics. NEVER answer factual questions from memory — always call web_search. Examples: 'Tunisia vs Japan match', 'bitcoin price', 'who won the Nobel Prize', 'capital of France', 'Beethoven symphonies'. NOT for weather (use weather_report) or books (use books tool).",
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
        "description": "Gives the weather report for one or more cities. For single city: 'weather in London'. For comparison: 'compare weather in London and Paris' or 'weather in London vs Paris'.",
        "parameters": {
            "type": "OBJECT",
            "properties": {"city": {"type": "STRING", "description": "City name, or multiple cities separated by 'vs', 'and', or commas for comparison (e.g. 'London' or 'London vs Paris')"}},
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
        "name": "timer",
        "description": (
            "In-app timer and task scheduler. Use for: "
            "'set a timer for 15 min', 'remind me in 10 minutes', "
            "'shutdown at 10pm', 'schedule restart at 6am'. "
            "Supports timer (minutes from now) and schedule (at specific time)."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "mode":    {"type": "STRING", "description": "timer | schedule | list | cancel"},
                "minutes": {"type": "INTEGER", "description": "Minutes from now (for timer mode)"},
                "message": {"type": "STRING", "description": "Timer message (for timer mode)"},
                "time":    {"type": "STRING", "description": "Time in HH:MM format (for schedule mode)"},
                "action":  {"type": "STRING", "description": "shutdown | restart | run_command | speak (for schedule mode)"},
                "name":    {"type": "STRING", "description": "Task name (for schedule mode)"},
                "task_id": {"type": "STRING", "description": "Task/timer ID to cancel (for cancel mode)"},
                "repeat":  {"type": "STRING", "description": "Repeat interval: 'daily', 'hourly', or empty for one-shot"}
            },
            "required": ["mode"]
        }
    },
    {
        "name": "youtube_video",
        "description": (
            "Controls YouTube. Use for: playing videos, summarizing a video's content, "
            "getting video info, showing trending videos, searching videos, "
            "getting channel stats, or downloading videos."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "play | summarize | get_info | trending | search | channel_stats | download"},
                "query":  {"type": "STRING", "description": "Search query for play/search action"},
                "channel": {"type": "STRING", "description": "Channel name or handle for channel_stats action"},
                "max_results": {"type": "INTEGER", "description": "Number of results for search (default 8)"},
                "save":   {"type": "BOOLEAN", "description": "Save summary to Notepad"},
                "region": {"type": "STRING", "description": "Country code for trending e.g. TR, US"},
                "url":    {"type": "STRING", "description": "Video URL for get_info or download action"},
                "format": {"type": "STRING", "description": "Download format: mp4 (default), mp3, best, or a specific extension like webm, mkv"},
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
        "name": "screen_explain",
        "description": (
            "FREE local screen explainer. Describes what is on screen using "
            "Ollama + accessibility + image analysis. No API key needed. "
            "Faster than screen_process. Use when user asks 'what do you see'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "generate_image",
        "description": (
            "Generates an image from a text prompt. "
            "Tries ComfyUI (local), then NVIDIA NIM (cloud), then local diffusers. "
            "Returns path to saved image."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "prompt":   {"type": "STRING", "description": "Text description of image to generate"},
                "negative": {"type": "STRING", "description": "Things to avoid in the image (optional)"}
            },
            "required": ["prompt"]
        }
    },
    {
        "name": "computer_settings",
        "description": (
            "Controls the computer: volume, brightness, window management, keyboard shortcuts, "
            "typing text on screen, closing apps, fullscreen, dark mode, WiFi toggle, restart, shutdown, "
            "scrolling, tab management, zoom, taking screenshots, lock screen, refresh/reload page. "
            "Also can change TTS language/voice, send desktop notifications, "
            "read/write clipboard, check battery or WiFi status."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "The action to perform. Actions: volume_up/down/mute/set, brightness_up/down, lock_screen, open_settings, sleep_display, toggle_wifi, wifi_list, wifi_status, battery_status, notify, clipboard_read, clipboard_write, restart, shutdown, dark_mode, type_text, press_key, screenshot, speedtest. Use action='language' with value='tr/en/fr/de...' to change TTS voice language. action='speak' is NOT for telling jokes or speaking — use that only to change the assistant's speaking language."},
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
            "clicking elements, filling forms (auto_fill auto-detects form fields and fills with generated data), "
            "scrolling, navigation. "
            "NOT for checking Gmail/emails — use gmail_get_unread instead. "
            "NOT for checking the weather — use weather_action instead. "
            "NOT for taking screenshots — use computer_settings instead. "
            "For TradingView charts use URL like: https://www.tradingview.com/chart/?symbol=XAUUSD&interval=1"
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "go_to | search | click | type | scroll | fill_form | detect_form | auto_fill | smart_click | smart_type | get_text | get_url | press | new_tab | close_tab | back | forward | reload | switch | list_browsers | close | close_all"},
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
        "name": "browser_use",
        "description": (
            "Uses an AI agent to perform complex multi-step browser automation tasks. "
            "Use this for things like: filling out web forms, scraping data from multiple pages, "
            "logging into websites, searching for information across sites, "
            "completing online purchases, booking appointments, or any task that requires "
            "multiple browser interactions. The agent can see the page, click, type, scroll, "
            "and navigate. For simple single actions like 'go to a URL' use browser_control instead."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "task":     {"type": "STRING",  "description": "The task to complete in the browser. Be specific about what to do and what information to extract."},
                "headless": {"type": "BOOLEAN", "description": "Run browser invisibly (default: true). Set to false for debugging."},
                "max_steps":{"type": "INTEGER", "description": "Maximum number of agent steps (default: 30)."},
                "timeout":  {"type": "INTEGER", "description": "Overall timeout in seconds (default: 180)."}
            },
            "required": ["task"]
        }
    },
    {
        "name": "file_controller",
        "description": "Manages LOCAL files and folders only: list, create, delete, move, copy, rename, read, write, find, disk usage, compress/extract archives, organize desktop. Does NOT search the web or the internet. For online documents or manuals, use web_search or browser_control instead.",
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
            "Returns stdout, stderr, and exit code. "
            "DO NOT use for shell builtins like 'history', 'alias', 'export' — those are not subprocess commands."
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
        "name": "run_fcc",
        "description": (
            "Runs Free Claude Code in a folder. Opens the system terminal in the "
            "chosen folder and starts BOTH fcc-server (background) and fcc-claude "
            "(foreground). ALWAYS use this when the user says 'run free claude code', "
            "'start fcc', or 'free claude code in <folder>'. "
            "Pass the folder name or path; Jarvis finds it automatically. "
            "If no folder is given, it reuses the last used folder."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "folder": {"type": "STRING", "description": "Folder name or path, e.g. 'Jarvis', '~/MyProjects/Jarvis', 'my portfolio'"}
            },
            "required": []
        }
    },
    {
        "name": "open_dashboard",
        "description": (
            "Opens ALL of the user's daily software at once (their 'dashboard'). "
            "ALWAYS use this when the user says 'open my dashboard', 'open all my apps', "
            "or 'open my daily software'. Jarvis learns which apps are daily from usage."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "add_dashboard",
        "description": (
            "Adds an app (or list of apps) to the user's daily dashboard. "
            "Use when the user says 'add chrome to my dashboard', 'my daily software is "
            "chrome, vscode and whatsapp', or 'add X to my daily apps'. "
            "Pass apps as a list of app names."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "apps": {"type": "ARRAY", "items": {"type": "STRING"}, "description": "List of app names to add"}
            },
            "required": ["apps"]
        }
    },
    {
        "name": "remove_dashboard",
        "description": (
            "Removes an app (or list of apps) from the user's daily dashboard. "
            "Use when the user says 'remove chrome from my dashboard' or 'delete X from my daily apps'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "apps": {"type": "ARRAY", "items": {"type": "STRING"}, "description": "List of app names to remove"}
            },
            "required": ["apps"]
        }
    },
    {
        "name": "list_dashboard",
        "description": (
            "Lists the apps currently on the user's daily dashboard. "
            "Use when the user asks 'what is on my dashboard' or 'what are my daily apps'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
            "required": []
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
        "name": "maps",
        "description": (
            "Geocoding, distance, coordinates, and timezone lookup using OpenStreetMap Nominatim + free APIs. "
            "Call this to find a place's coordinates, get an address, calculate distance, or find what time/timezone it is in a city. "
            "Examples: where is ISIMS, how far is Sfax from Tunis, what is the time zone in Tokyo, what time is it in Paris."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "geocode | distance | coords | timezone"},
                "query":  {"type": "STRING", "description": "Place name to search (for geocode/coords/timezone) or 'A to B' string (for distance)"},
                "origin": {"type": "STRING", "description": "Starting place name (for distance with separate params)"},
                "destination": {"type": "STRING", "description": "Destination place name (for distance with separate params)"},
            },
            "required": []
        }
    },
    {
        "name": "stock_price",
        "description": (
            "Look up current stock OR crypto prices, change percentages, and company info via Yahoo Finance. "
            "Call this when the user asks about stock prices, crypto prices (bitcoin, BTC, ethereum, ETH), "
            "share prices, market data, ticker symbols. "
            "Examples: what is AAPL stock, TSLA price, BTC price, how is the market doing."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "symbols": {"type": "STRING", "description": "Stock ticker symbols or crypto names separated by spaces or commas (e.g. AAPL TSLA MSFT or bitcoin BTC ethereum)"},
            },
            "required": ["symbols"]
        }
    },
    {
        "name": "news",
        "description": (
            "Fetch latest news headlines by topic using RSS feeds. "
            "Call this when the user asks for news, headlines, current events. "
            "Topics: top, world, tech, science, business. Default: top."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "topic": {"type": "STRING", "description": "News topic: top | world | tech | science | business"},
                "count": {"type": "INTEGER", "description": "Number of headlines to return (default 5)"},
            },
            "required": []
        }
    },
    {
        "name": "get_datetime",
        "description": (
            "Returns the current date, time, day of week, or all three. "
            "Zero latency — no API call needed. "
            "Use for: what day is it, what time is it, today's date, what's the date, "
            "what day of the week, current time, unix timestamp."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "format": {"type": "STRING", "description": "full | date | time | day | unix (default: full)"},
            },
            "required": []
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
            "Evaluates ONLY mathematical expressions and conversions. "
            "Use ONLY for pure math: arithmetic, percentages, algebra, conversions (temperature, units, data storage), Roman numerals. "
            "NEVER use this for factual questions, history, recent events, or news. "
            "For factual information use web_search instead."
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
        "name": "gmail_get_unread",
        "description": "Retrieves unread emails from Gmail and returns sender, subject, and date. Use this to read the user's latest emails aloud. Do NOT use browser_control for email queries — use this tool instead.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "limit": {"type": "INTEGER", "description": "Max emails to fetch (default: 10)"}
            },
            "required": []
        }
    },
    {
        "name": "gmail_search",
        "description": "Searches Gmail with a query string. Use for finding specific emails.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {"type": "STRING", "description": "Gmail search query (e.g. 'from:boss', 'subject:report')"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "gmail_send",
        "description": "Sends an email via Gmail.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "to":      {"type": "STRING", "description": "Recipient email address"},
                "subject": {"type": "STRING", "description": "Email subject"},
                "body":    {"type": "STRING", "description": "Email body text"}
            },
            "required": ["to", "subject", "body"]
        }
    },
    {
        "name": "gmail_reply",
        "description": "Replies to an existing Gmail message.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "message_id": {"type": "STRING", "description": "Gmail message ID to reply to"},
                "body":       {"type": "STRING", "description": "Reply body text"}
            },
            "required": ["message_id", "body"]
        }
    },
    {
        "name": "calendar_agenda",
        "description": "Gets today's agenda or upcoming events from Google Calendar.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "days": {"type": "INTEGER", "description": "Number of days ahead to fetch (default: 1 for today only)"}
            },
            "required": []
        }
    },
    {
        "name": "calendar_create_event",
        "description": "Creates a new event on Google Calendar. Optionally adds a Google Meet link.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "title":           {"type": "STRING",  "description": "Event title/name"},
                "date":            {"type": "STRING",  "description": "Date in YYYY-MM-DD format"},
                "time":            {"type": "STRING",  "description": "Time in HH:MM format (24h)"},
                "duration_minutes": {"type": "INTEGER", "description": "How long the event lasts in minutes"},
                "description":     {"type": "STRING",  "description": "Optional description or notes"},
                "meet":            {"type": "BOOLEAN", "description": "Add a Google Meet video link (default: false)"}
            },
            "required": ["title", "date", "time", "duration_minutes"]
        }
    },
    {
        "name": "calendar_delete_event",
        "description": "Deletes a Google Calendar event by its event ID.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "event_id": {"type": "STRING", "description": "The event ID to delete"}
            },
            "required": ["event_id"]
        }
    },
    {
        "name": "drive_search",
        "description": "Searches Google Drive for files matching a query.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {"type": "STRING", "description": "Drive search query (e.g. 'name contains Q1')"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "drive_upload",
        "description": "Uploads a local file to Google Drive.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "local_path": {"type": "STRING", "description": "Full path to the local file to upload"},
                "folder_id":  {"type": "STRING", "description": "Optional Drive folder ID to upload into"}
            },
            "required": ["local_path"]
        }
    },
    {
        "name": "drive_create_doc",
        "description": "Creates a new Google Doc with a title and optional content.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "title":   {"type": "STRING", "description": "Document title"},
                "content": {"type": "STRING", "description": "Optional text content to add to the document"}
            },
            "required": ["title"]
        }
    },
    {
        "name": "meet_create",
        "description": "Creates a Google Meet meeting with a calendar event. Use for 'create a Google Meet' / 'schedule a video call'.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "title":           {"type": "STRING",  "description": "Meeting title"},
                "date":            {"type": "STRING",  "description": "Date in YYYY-MM-DD format"},
                "time":            {"type": "STRING",  "description": "Time in HH:MM format (24h)"},
                "duration_minutes": {"type": "INTEGER", "description": "Duration in minutes (default: 60)"}
            },
            "required": ["title", "date", "time"]
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
    {
        "name": "screen_read",
        "description": "Reads UI elements from the active window using accessibility APIs. Returns buttons, labels, menus, and text visible on screen — no OCR needed. Works on Linux (pyatspi2), Windows (UIAutomation), and macOS (PyObjC).",
        "parameters": {
            "type": "OBJECT",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "active_window",
        "description": "Returns the title, app name, and role of the currently focused window.",
        "parameters": {
            "type": "OBJECT",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "detect_faces",
        "description": "Detects faces in the camera feed using OpenCV Haar cascades. Returns face positions and count. Also detects smiles and eyes if faces are found.",
        "parameters": {
            "type": "OBJECT",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "wake_word",
        "description": "Starts or stops local wake word detection (OpenWakeWord). When active, JARVIS listens for a wake word before processing speech. Supported models: jarvis, computer, alexa.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "start | stop"},
                "model_name":  {"type": "STRING", "description": "Wake word model: jarvis (default), computer, alexa"},
                "sensitivity": {"type": "NUMBER", "description": "Detection threshold 0.0–1.0 (default: 0.5). Lower = more sensitive."}
            },
            "required": ["action"]
        }
    },
    {
        "name": "github",
        "description": "GitHub integration. Create/list repos, manage issues and pull requests, view workflows, and clone a public repo into ~/MyProjects (clone needs no token). Requires GITHUB_TOKEN for API operations.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":     {"type": "STRING", "description": "clone | list_repos | create_repo | get_repo | list_issues | create_issue | close_issue | list_prs | get_pr | create_pr | merge_pr | list_workflows | list_runs"},
                "repo":       {"type": "STRING", "description": "Repo to clone (URL or 'user/repo'), or full repo name for repo/issue/PR operations"},
                "name":       {"type": "STRING", "description": "Repo name for create_repo, or issue/PR title"},
                "description":{"type": "STRING", "description": "Repo description for create_repo"},
                "private":    {"type": "BOOLEAN", "description": "Make repo private (default: false)"},
                "body":       {"type": "STRING", "description": "Issue/PR body text"},
                "number":     {"type": "INTEGER", "description": "Issue or PR number"},
                "head":       {"type": "STRING", "description": "Head branch name for create_pr"},
                "base":       {"type": "STRING", "description": "Base branch name for create_pr (default: main)"},
                "state":      {"type": "STRING", "description": "Filter state: open (default), closed, all"},
                "user":       {"type": "STRING", "description": "GitHub username for listing repos"},
                "branch":     {"type": "STRING", "description": "Branch name for workflow runs"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "search_files_fast",
        "description": "Extremely fast file search. Uses Everything SDK on Windows and locate/glob on Linux. Finds files by name in milliseconds.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query":       {"type": "STRING", "description": "Filename or pattern to search for"},
                "root":        {"type": "STRING", "description": "Root directory (Linux only; default: home dir)"},
                "max_results": {"type": "INTEGER", "description": "Maximum results (default: 20)"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "finance",
        "description": "Plaid finance dashboard. Track spending, transactions, budgets, and account balances. Requires PLAID_CLIENT_ID, PLAID_SECRET, PLAID_ACCESS_TOKEN environment variables.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":     {"type": "STRING", "description": "accounts | transactions | spending_summary | balances"},
                "days":       {"type": "INTEGER", "description": "Look back days for spending_summary (default: 30)"},
                "start_date": {"type": "STRING", "description": "Start date YYYY-MM-DD for transactions"},
                "end_date":   {"type": "STRING", "description": "End date YYYY-MM-DD for transactions"},
                "limit":      {"type": "INTEGER", "description": "Max transactions (default: 50)"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "network_scan",
        "description": "Discovers devices and services on the local network via mDNS/Zeroconf. Finds printers, NAS, smart TVs, Chromecasts, and other network services. Also returns local IP addresses.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "discover | local_ips"},
                "timeout":{"type": "INTEGER", "description": "Discovery timeout in seconds (default: 3)"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "voice_call",
        "description": "Create and manage LiveKit voice/video call rooms. Generate access tokens, create rooms, list active rooms. Requires LIVEKIT_API_KEY, LIVEKIT_API_SECRET, LIVEKIT_HOST environment variables.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":    {"type": "STRING", "description": "create_room | list_rooms | generate_token"},
                "room_name": {"type": "STRING", "description": "Room name for create_room or generate_token"},
                "identity":  {"type": "STRING", "description": "User identity for token generation (default: jarvis)"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "monitors",
        "description": "Multi-monitor awareness. List all connected monitors with resolutions and positions, get active monitor info, or set brightness.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":    {"type": "STRING", "description": "list | summary | active | brightness"},
                "monitor":   {"type": "INTEGER", "description": "Monitor index for brightness action"},
                "brightness":{"type": "NUMBER", "description": "Brightness level 0.0–1.0 (default: 1.0)"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "obsidian",
        "description": "Obsidian vault integration. Save ideas as notes, search existing notes, list notes by folder, create knowledge graph (wiki-link relationships), or set vault path. Set OBSIDIAN_VAULT env var.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":    {"type": "STRING", "description": "save | search | list | graph | tags | set_vault"},
                "title":     {"type": "STRING", "description": "Note title for save action"},
                "content":   {"type": "STRING", "description": "Note content for save action"},
                "query":     {"type": "STRING", "description": "Search query for search action"},
                "folder":    {"type": "STRING", "description": "Subfolder within JARVIS/ for save/list"},
                "max_results":{"type": "INTEGER", "description": "Max results (default: 10)"},
                "vault_path":{"type": "STRING", "description": "Path to Obsidian vault root (for set_vault)"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "package_manager",
        "description": "Install, uninstall, list, or update software packages. Auto-detects OS and uses the appropriate package manager (apt, dnf, pacman, brew, winget, pip, poetry, uv).",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":  {"type": "STRING", "description": "install | uninstall | list | update_all | detect"},
                "package": {"type": "STRING", "description": "Package name to install/uninstall"},
                "manager": {"type": "STRING", "description": "Package manager: auto (default), pip, apt, dnf, brew, winget, poetry, uv, pacman"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "goals",
        "description": "Goal engine — track complex multi-step goals. Create goals with steps, mark steps complete, track progress percentage, list active/completed goals.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "create | list | get | progress | complete_step | delete | summary"},
                "title":       {"type": "STRING", "description": "Goal title for create action"},
                "description": {"type": "STRING", "description": "Goal description for create action"},
                "goal_id":     {"type": "STRING", "description": "Goal ID for get/progress/complete_step/delete"},
                "steps":       {"type": "ARRAY", "items": {"type": "STRING"}, "description": "Step descriptions for create action"},
                "step_title":  {"type": "STRING", "description": "Step title for complete_step action"},
                "status":      {"type": "STRING", "description": "Filter: active (default), completed, paused"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "task_graph",
        "description": "Dependency task graph using NetworkX. Create tasks with dependencies, mark tasks complete, find available (unblocked) tasks, view critical path.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "create | complete | available | summary | critical_path | delete | reset"},
                "task_id":     {"type": "STRING", "description": "Task ID for create/complete/delete"},
                "description": {"type": "STRING", "description": "Task description for create action"},
                "depends_on":  {"type": "ARRAY", "items": {"type": "STRING"}, "description": "Task IDs this task depends on"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "tasks",
        "description": "Local day-to-day task manager. Add, list, complete, or delete tasks. Automatically shown when calendar is unavailable.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":   {"type": "STRING", "description": "add | list | complete | delete"},
                "title":    {"type": "STRING", "description": "Task title for add action"},
                "priority": {"type": "STRING", "description": "low | normal | high | critical"},
                "due":      {"type": "STRING", "description": "Due date string (e.g. 'tomorrow', '2025-12-31')"},
                "task_id":  {"type": "STRING", "description": "Task ID for complete/delete"},
                "status":   {"type": "STRING", "description": "pending | done — filter for list action"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "todo_display",
        "description": "Shows the todo list as a graphical table with stats, due dates, and priorities. Use for: show todo, display tasks, open todo list, view my tasks.",
        "parameters": {
            "type": "OBJECT",
            "properties": {}
        }
    },
    {
        "name": "budget",
        "description": "Local budget tracker. Add income/expense transactions, view summary by period (all/month/today) or category.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "add | summary | list"},
                "description": {"type": "STRING", "description": "Transaction description for add action"},
                "amount":      {"type": "NUMBER", "description": "Transaction amount for add action"},
                "category":    {"type": "STRING", "description": "food | transport | housing | utilities | entertainment | health | education | shopping | salary | freelance | investment | other"},
                "type":        {"type": "STRING", "description": "income | expense (default: expense)"},
                "period":      {"type": "STRING", "description": "all | month | today — for summary action"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "vault",
        "description": "Security layer — store, retrieve, list, or delete secrets. Uses local encrypted JSON file by default. Optionally connects to HashiCorp Vault for professional secret management.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "store | get | list | delete"},
                "key":    {"type": "STRING", "description": "Secret key/name"},
                "value":  {"type": "STRING", "description": "Secret value for store action"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "context",
        "description": "LOCAL system context only — shows what JARVIS knows about current app, battery, meeting status, git status, and other real-time plugin data. Does NOT search the web or answer factual questions. Use web_search for questions about APIs, documentation, or any external topic.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "summary | get | search | keys"},
                "key":    {"type": "STRING", "description": "Context key for get action"},
                "query":  {"type": "STRING", "description": "Search query for search action"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "scaffold",
        "description": "Scaffolds a new software project. Creates project folder in workspace, starts opencode sessions as Project Manager, Backend Developer, Frontend Developer, and QA Engineer sequentially. Use for 'start new project', 'create new app', 'scaffold project'.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "project_name": {"type": "STRING", "description": "Name of the project to create"},
                "description":  {"type": "STRING", "description": "Brief project description"},
                "tech_stack":   {"type": "STRING", "description": "Technology stack (e.g. python, react, node)"},
                "roles":        {"type": "ARRAY", "items": {"type": "STRING"}, "description": "Roles to start: project_manager, backend, frontend, tester (default: all four)"}
            },
            "required": ["project_name"]
        }
    },
    {
        "name": "project_init",
        "description": (
            "Creates new projects of any type or clones git repos. "
            "Use for: 'create a react app', 'make a python project', "
            "'clone repo', 'init nextjs project', 'start a web project'. "
            "Supports: python, react, react-ts, nextjs, nextjs-ts, web, "
            "node, express, fastapi, flask, vanilla, vue, svelte, rust, go. "
            "Handles Vite, create-next-app, cargo, and manual scaffolding. "
            "Auto-detects project type when cloning. "
            "Installs dependencies and initializes git."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "mode":         {"type": "STRING", "description": "create | clone | list | types"},
                "project_name": {"type": "STRING", "description": "Project name (for create mode)"},
                "project_type": {"type": "STRING", "description": "python | react | react-ts | nextjs | nextjs-ts | web | node | express | fastapi | flask | vanilla | vue | svelte | rust | go (default: web)"},
                "description":  {"type": "STRING", "description": "Project description"},
                "git_url":      {"type": "STRING", "description": "Git URL to clone (for clone mode)"},
                "target_dir":   {"type": "STRING", "description": "Target directory for clone"},
                "install_deps": {"type": "BOOLEAN", "description": "Auto-install dependencies (default: true)"},
                "git_init":     {"type": "BOOLEAN", "description": "Initialize git repo (default: true)"},
                "workspace":    {"type": "STRING", "description": "Workspace directory (default: workspace/)"}
            },
            "required": ["mode"]
        }
    },
    {
        "name": "projectinitializer",
        "description": (
            "Universal Project Initializer. Creates new folders and scaffolds project structures. "
            "Use for: 'initialize a react project', 'initialize any project', 'scaffold python/go/rust/laravel etc.' "
            "Supports: python, fastapi, django, flask, data-science, cli, node, express, react, react-ts, nextjs, vue, nuxt, angular, svelte, electron, graphql, monorepo, flutter, dart, react-native, go, rust, rust-lib, cpp, c, swift, kotlin, java-maven, java-gradle, csharp, aspnet, unity, laravel, symfony, php, rails, ruby, mysql, postgres, mongodb, redis, sqlite, docker, terraform, ansible."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "project_name": {"type": "STRING", "description": "Name of the project folder"},
                "project_type": {"type": "STRING", "description": "The type of project (e.g. react, python, docker, rails, etc.)"},
                "workspace":    {"type": "STRING", "description": "The workspace directory where project should be created (default: .)"}
            },
            "required": ["project_name", "project_type"]
        }
    },
    {
        "name": "relationship_graph",
        "description": "Tracks relationships between projects, repositories, servers, databases, and credentials. Link them together and ask where anything is deployed. Supports add/list/resolve/deployment queries.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":     {"type": "STRING", "description": "add_node | remove_node | add_edge | remove_edge | get_related | resolve_deployment | summary"},
                "node_id":    {"type": "STRING", "description": "Node ID for add_node/remove_node/add_edge"},
                "node_type":  {"type": "STRING", "description": "Node type: project | repository | server | database | credentials"},
                "name":       {"type": "STRING", "description": "Node display name"},
                "target_id":  {"type": "STRING", "description": "Target node ID for add_edge"},
                "relation":   {"type": "STRING", "description": "Relationship label for edge"},
                "project":    {"type": "STRING", "description": "Project name for resolve_deployment"},
                "properties": {"type": "STRING", "description": "JSON string of additional properties"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "forensics",
        "description": "Computer forensics layer. Check recent file changes, running processes, network connections, and package install history. Example: 'what installed yesterday', 'show me recent processes', 'check network connections'.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "files | processes | network | installed | summary"},
                "days":   {"type": "INTEGER", "description": "Look back days (default: 1)"},
                "path":   {"type": "STRING", "description": "Directory path for file search (default: home)"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "remote_control",
        "description": "Start or stop the JARVIS remote control server. Exposes a FastAPI REST API and WebSocket endpoint for controlling JARVIS from phone, tablet, or smartwatch. REST at http://host:port, WebSocket at ws://host:port/ws.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "start | stop | status"},
                "host":   {"type": "STRING", "description": "Bind address (default: 0.0.0.0)"},
                "port":   {"type": "INTEGER", "description": "Port number (default: 8765)"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "federation",
        "description": "JARVIS multi-instance federation. Share memory, query memories across instances, register instances, sync data between JARVIS instances (laptop, desktop, home server). All instances share memory via JSON files.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":   {"type": "STRING", "description": "share | query | register | instances | sync | status"},
                "key":      {"type": "STRING", "description": "Memory key for share/query"},
                "value":    {"type": "STRING", "description": "Memory value for share action"},
                "instance": {"type": "STRING", "description": "Instance name for sync action"},
                "name":     {"type": "STRING", "description": "Instance name for register action"},
                "ttl_hours":{"type": "INTEGER", "description": "TTL in hours for shared memory (0 = no expiry)"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "books",
        "description": "Searches books by title, author, or query using the OpenLibrary API. Use for: who wrote X, find books by Y, search for books about Z, get info about a specific book.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "search (default) | info | query"},
                "query":  {"type": "STRING", "description": "General search query (e.g. 'Brave New World')"},
                "title":  {"type": "STRING", "description": "Book title to search"},
                "author": {"type": "STRING", "description": "Author name to search"},
                "key":    {"type": "STRING", "description": "OpenLibrary key (e.g. /works/OL123W) for info action"}
            },
            "required": []
        }
    },
    {
        "name": "jobs",
        "description": "Searches job listings using Fantastic.jobs API. Use for: find jobs, search for positions, look for work, job openings. Requires a valid API key in config.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query":  {"type": "STRING", "description": "Job title or keyword search (e.g. 'software engineer', 'data scientist')"},
                "title":  {"type": "STRING", "description": "Specific job title filter"},
                "location": {"type": "STRING", "description": "Location filter (e.g. 'United States', 'London, England, United Kingdom')"},
                "limit":  {"type": "INTEGER", "description": "Max results (default: 10, max: 50)"},
                "remote": {"type": "STRING", "description": "Work arrangement: Remote Solely, Remote OK, Hybrid, On-site"}
            },
            "required": []
        }
    },
    {
        "name": "realtime_tutor",
        "description": "Opens the Gemini 2.0 Flash RealTime Tutor — a voice/video/screen tutor inside the Jarvis GUI. Use for: start tutor, open tutor, gemini tutor, real-time tutor, stop tutor, close tutor.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "'start' to launch the tutor, 'stop' to close it",
                    "enum": ["start", "stop"]
                }
            },
            "required": ["action"]
        }
    },
    {
        "name": "read_emails",
        "description": "Fetches recent emails from Gmail. Use for: read my emails, check inbox, latest email, new messages, show emails from today.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "hours":  {"type": "INTEGER", "description": "How many hours back to search (default 24)"},
                "keyword": {"type": "STRING", "description": "Optional keyword to filter emails"},
                "limit":  {"type": "INTEGER", "description": "Max emails to return (default 10)"}
            },
            "required": []
        }
    },
    {
        "name": "habit_tracker",
        "description": "Track and analyze habits. Supports: list habits, create a habit, mark habit complete, show progress/streaks, weekly/monthly reports. Use for: habit tracker, my habits, track habits, habit progress, log habit, habit streak.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "Action to perform: list, create, complete, progress, report, delete",
                    "enum": ["list", "create", "complete", "progress", "report", "delete"]
                },
                "name":     {"type": "STRING", "description": "Habit name (for create, complete, progress, delete)"},
                "periodicity": {"type": "STRING", "description": "daily or weekly (default: daily)"},
                "category": {"type": "STRING", "description": "Category like health, education, fitness (default: general)"},
                "id":       {"type": "INTEGER", "description": "Habit ID (for complete, progress, delete)"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "set_timer",
        "description": "Sets a countdown timer for a specified duration. Use for: set a timer for X minutes, remind me in Y minutes, timer for cooking, create an alarm.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "minutes": {"type": "INTEGER", "description": "Duration in minutes"},
                "message": {"type": "STRING", "description": "Optional message when timer fires"},
            },
            "required": ["minutes"]
        }
    },
    {
        "name": "convert_file",
        "description": "Converts files between formats: images (png/jpg/webp/gif/bmp/tiff/ico), PDF, Word, Excel, PowerPoint, Markdown, HTML, CSV, JSON, XML, TXT, audio (mp3/wav/ogg/flac/m4a/aac), video (mp4/avi/mkv/mov/webm/gif), and OCR (image to text). Use for: convert X to Y, change format, turn into, OCR this image.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "source_path":    {"type": "STRING", "description": "Full path to the source file"},
                "target_format":  {"type": "STRING", "description": "Target format e.g. pdf, png, docx, mp3, gif, txt (for OCR)"},
                "mode":           {"type": "STRING", "description": "auto (default) — convert based on file extension"},
            },
            "required": ["source_path", "target_format"]
        }
    },
    {
        "name": "random_number",
        "description": "Generates a random number, rolls dice, or flips a coin. Use for: random number, roll dice, flip coin, pick a number.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "min":  {"type": "INTEGER", "description": "Minimum value (default 1)"},
                "max":  {"type": "INTEGER", "description": "Maximum value (default 100)"},
                "mode": {"type": "STRING", "description": "number (default), dice, or coin"},
            },
            "required": []
        }
    },
    {
        "name": "system_info",
        "description": "Returns information about the computer: OS, CPU, RAM, hostname, architecture. Use for: what is my OS, system info, computer specs, show operating system.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {"type": "STRING", "description": "What to query: os, cpu, ram, hostname, or all (default)"},
            },
            "required": []
        }
    },
    {
        "name": "convert_units",
        "description": "Converts between units of measurement: length (km/mi/cm/in/ft), weight (kg/lb/g/oz), temperature (C/F/K), volume (L/gal/ml), speed (kmh/mph/knot), time, data (GB/MB), area. Use for: convert miles to km, how many kg in 10 pounds, 100f to celsius.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "value": {"type": "NUMBER", "description": "The numeric value to convert"},
                "from":  {"type": "STRING", "description": "Source unit (km, mi, kg, lb, f, c, etc.)"},
                "to":    {"type": "STRING", "description": "Target unit (km, mi, kg, lb, f, c, etc.)"},
            },
            "required": ["value", "from", "to"]
        }
    },
    {
        "name": "filesystem_query",
        "description": "Queries the file system: largest files, disk usage, storage space. Use for: largest files in downloads, disk usage, top 10 biggest files, how much space is free.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "largest (default) or disk_usage"},
                "path":   {"type": "STRING", "description": "Directory to scan: home, downloads, desktop, documents (default: home)"},
                "count":  {"type": "INTEGER", "description": "Number of files to list (default 10)"},
            },
            "required": []
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
        nv: dict = {"type": _convert_type(v.get("type", "string"))}
        if "items" in v and isinstance(v["items"], dict):
            nv["items"] = {"type": _convert_type(v["items"].get("type", "string"))}
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
        desc = d.get("description", "")
        tools.append({
            "type": "function",
            "function": {
                "name":        d["name"],
                "description": desc,
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
    """Return True only if the user's message is purely a greeting with no query."""
    t = text.lower().strip().rstrip("!?.,").strip()
    if t in _GREETINGS:
        return True
    first_word = t.split()[0] if t.split() else ""
    if first_word in _GREETINGS:
        remaining = t[len(first_word):].strip().rstrip("!?.,").strip()
        if not remaining or remaining in _GREETINGS:
            return True
    return False


def calculate(parameters: dict = None) -> str:
    import math as _math
    import re as _re
    expr = (parameters or {}).get("expression", "").strip()
    if not expr:
        return "No expression provided."
    s = expr
    # Roman numeral conversion
    roman_match = _re.match(r'^[IVXLCDM]+$', s.strip(), _re.IGNORECASE)
    if roman_match:
        roman = s.strip().upper()
        roman_map = {'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100, 'D': 500, 'M': 1000}
        total = 0
        prev = 0
        for ch in reversed(roman):
            val = roman_map.get(ch, 0)
            if val < prev:
                total -= val
            else:
                total += val
            prev = val
        return f"{roman} = {total}"
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
    # Hex color to RGB: "#FF5733 to RGB" or "hex #FF5733"
    hex_m = _re.match(r'(?:convert\s+)?(?:the\s+)?(?:hex\s+(?:color\s+)?)?#?([0-9a-fA-F]{6})\s*(?:to\s+)?(?:rgb|RGB)', s, _re.IGNORECASE)
    if hex_m:
        h = hex_m.group(1)
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return f"#{h} = RGB({r}, {g}, {b})"
    # Unit conversion patterns
    _unit_re = r'(gallons?|liters?|litres?|pounds?|kg|kilograms?|miles?|kilometers?|km|bytes?|kilobytes?|megabytes?|gigabytes?|terabytes?|KB|MB|GB|TB)'
    # Normalize unit: strip trailing 's', handle abbreviations
    def _norm_u(u):
        u = u.lower().rstrip("s")
        if u == "kilogram": return "kg"
        if u == "kilometer": return "km"
        return u
    # Pattern 1: "convert 5 miles to km", "3.5 gallons to liters", "75 kg in pounds"
    m = _re.match(r'(?:convert\s+)?([\d.]+)\s*' + _unit_re + r'\s*(?:to|in|→)\s*' + _unit_re, s, _re.IGNORECASE)
    # Pattern 2: "how many X is Y Z" e.g. "how many kilometers is 26.2 miles"
    if not m:
        m = _re.match(r'how\s+many\s+' + _unit_re + r'\s+(?:is|are)\s+([\d.]+)\s+' + _unit_re, s, _re.IGNORECASE)
        if m:
            src_u = _norm_u(m.group(3))
            tgt_u = _norm_u(m.group(1))
            val = float(m.group(2))
        else:
            src_u = tgt_u = None
    else:
        src_u = _norm_u(m.group(2))
        tgt_u = _norm_u(m.group(3))
        val = float(m.group(1))
    if src_u and tgt_u:
        data_units = {"byte": 1, "kilobyte": 1024, "megabyte": 1024**2, "gigabyte": 1024**3, "terabyte": 1024**4,
                      "kb": 1024, "mb": 1024**2, "gb": 1024**3, "tb": 1024**4}
        if src_u in data_units and tgt_u in data_units:
            bytes_val = val * data_units[src_u]
            result = bytes_val / data_units[tgt_u]
            return f"{s} = {result:,.4f}"
        conversions = {
            ("gallon", "liter"): val * 3.78541,
            ("liter", "gallon"): val / 3.78541,
            ("pound", "kg"): val * 0.453592,
            ("kg", "pound"): val / 0.453592,
            ("mile", "km"): val * 1.60934,
            ("km", "mile"): val / 1.60934,
        }
        result = conversions.get((src_u, tgt_u))
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
            left_expr = left_side.replace(' ', '').replace('x', '*x').replace('X', '*x')
            if left_expr.startswith('*x'):
                left_expr = 'x' + left_expr[2:]
            right_val = safe_math(right_side)
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
    # "how many bytes in 2.5 gigabytes" or "how many megabytes in 1024 kilobytes"
    howmany_match = _re.match(r'how\s+many\s+(bytes?|kilobytes?|megabytes?|gigabytes?|terabytes?|KB|MB|GB|TB)\s+(?:are\s+)?(?:in|is)\s+([\d.]+)\s+(bytes?|kilobytes?|megabytes?|gigabytes?|terabytes?|KB|MB|GB|TB)', s, _re.IGNORECASE)
    if howmany_match:
        target_unit = howmany_match.group(1).lower().rstrip("s")
        val = float(howmany_match.group(2))
        source_unit = howmany_match.group(3).lower().rstrip("s")
        data_units = {"byte": 1, "kilobyte": 1024, "megabyte": 1024**2, "gigabyte": 1024**3, "terabyte": 1024**4,
                      "kb": 1024, "mb": 1024**2, "gb": 1024**3, "tb": 1024**4}
        if source_unit in data_units and target_unit in data_units:
            bytes_val = val * data_units[source_unit]
            result = bytes_val / data_units[target_unit]
            return f"{val} {howmany_match.group(3)} = {result:,.4f} {howmany_match.group(1)}"
    try:
        result = safe_math(s_clean)
        if isinstance(result, float):
            result = round(result, 10)
            s_result = f"{result:g}"
            return f"{s_clean} = {s_result}"
        return f"{s_clean} = {result}"
    except Exception as e:
        return f"Could not calculate: {e}"


# ── System-prompt cache ──────────────────────────────────────────────────────
# The prompt file is read once and cached for the process lifetime.
# This avoids repeated disk I/O on every LLM call (saves ~1-3 ms per turn).
_SYSTEM_PROMPT_CACHE: str | None = None
# Full combined system prompt cache (static parts) — re-built at most once per minute
_SYS_PROMPT_COMBINED_CACHE: str = ""
_SYS_PROMPT_COMBINED_CACHE_MIN: int = -1

def _load_system_prompt() -> str:
    global _SYSTEM_PROMPT_CACHE
    if _SYSTEM_PROMPT_CACHE is not None:
        return _SYSTEM_PROMPT_CACHE
    try:
        _SYSTEM_PROMPT_CACHE = PROMPT_PATH.read_text(encoding="utf-8")
    except Exception:
        _SYSTEM_PROMPT_CACHE = (
            "You are JARVIS, Tony Stark's AI assistant. "
            "Be concise, direct, and helpful. You support both executing computer tasks via tools "
            "and engaging in general friendly chat / conversation. Keep responses under 3 sentences."
        )
    return _SYSTEM_PROMPT_CACHE


# ---------------------------------------------------------------------------
# Voice Activity Detection (used for Whisper listen loop)
# ---------------------------------------------------------------------------

class _VADBuffer:
    """Energy-based VAD: buffers audio until end of utterance."""

    def __init__(
        self,
        sample_rate:    int   = 16_000,
        silence_sec:    float = 0.18,  # ↓300ms→180ms: shaves ~120ms off every turn
        speech_thresh:  float = 0.008,  # RMS above this = speech  (0.008 catches voice at 3-4 m; raise if mic picks up too much room noise)
        silence_thresh: float = 0.004,  # RMS below this = silence (half of speech_thresh — hysteresis prevents mid-sentence cuts)
        min_speech_sec: float = 0.25,   # ↓0.3→0.25 s: accept slightly shorter utterances
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
        self._conv_lock = threading.Lock()
        self._generation = 0
        self._processing_lock = threading.Lock()

        self.ui.on_text_command = self._on_text_command
        self._current_language = "en"

        # ── GWS logging ───────────────────────────────────────────────────
        _gws_log_dir = BASE_DIR / "logs"
        _gws_log_dir.mkdir(parents=True, exist_ok=True)
        _gws_log_path = str(_gws_log_dir / "gws.log")
        _gws_handler = logging.FileHandler(_gws_log_path)
        _gws_handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        ))
        logging.getLogger("gws_bridge").addHandler(_gws_handler)
        logging.getLogger("gws_bridge").setLevel(logging.DEBUG)
        logging.getLogger("gws_bridge").propagate = False

        # ── Timer / Scheduler callback ──────────────────────────────────────
        def _timer_fired(name_or_msg: str, action: str = "", params: dict = None):
            self.speak(f"{name_or_msg}")
            self.ui.log(f"[Timer] {name_or_msg}")
            p = params or {}
            act = p.get("action", action or "")
            if act in ("shutdown", "restart", "sleep"):
                logger.info("Timer triggered system action: %s", act)
                self.ui.log(f"[Timer] executing: {act}")
                import subprocess
                import shlex
                cmds = {"shutdown": "shutdown -h now", "restart": "shutdown -r now",
                        "sleep": "systemctl suspend"}
                subprocess.Popen(shlex.split(cmds[act]))
            elif act and act not in ("", "speak"):
                logger.info("Running scheduled action: %s", act)

        timer_set_callback(_timer_fired)

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

    # ── Cached time-context: re-built at most once per minute ────────────
    _time_ctx_cache:      str   = ""
    _time_ctx_cache_min:  int   = -1

    def _build_system_prompt(self, user_text: str = "") -> str:
        # ── ORDER MATTERS for Ollama KV prefix caching ─────────────────────
        # Ollama caches the KV attention state of any stable prompt prefix.
        # By putting the STATIC JARVIS protocol text FIRST, Ollama reuses its
        # cached KV for all those tokens on every request.  Only the small
        # dynamic tail (memory + time, ~50-80 tokens) needs re-evaluation.
        # This turns a 17-second first-token into a sub-second one after warmup.
        #
        # Rule: static content first → semi-static memory middle → dynamic time LAST.
        sys_p   = _load_system_prompt()               # cached in-process after first call
        memory  = load_memory()
        mem_str = format_memory_for_prompt(memory)    # semi-static
        now     = datetime.now()

        # ── Time context: cached per-minute (avoids regenerating tokens) ───
        cur_min = now.hour * 60 + now.minute
        if cur_min != JarvisLocal._time_ctx_cache_min:
            JarvisLocal._time_ctx_cache = (
                f"[CURRENT DATE & TIME]\n"
                f"Right now it is: {now.strftime('%A, %B %d, %Y — %I:%M %p')}\n"
                f"Use this to calculate exact times for reminders."
            )
            JarvisLocal._time_ctx_cache_min = cur_min
        time_ctx = JarvisLocal._time_ctx_cache

        # ── Vector memory + skills: use pre-fetched result if available ─────
        vec_context   = getattr(self, "_prefetched_vec",   None)
        skill_context = getattr(self, "_prefetched_skill", None)

        if vec_context is None and user_text:
            vec_context = get_relevant_context(user_text)
        if isinstance(vec_context, str) and vec_context:
            vec_count   = get_memory_count()
            vec_context = f"[SEMANTIC MEMORY — {vec_count} stored memories]\n{vec_context}"
        else:
            vec_context = ""

        if skill_context is None and user_text:
            skill_context = get_active_skill_context(user_text)
        if isinstance(skill_context, str) and skill_context:
            skill_context = f"[ACTIVE SKILL]\n{skill_context}"
        else:
            skill_context = ""

        # Background agents status
        agent_mgr  = get_agent_manager()
        running    = agent_mgr.get_running_count()
        agent_info = f"[BACKGROUND AGENTS: {running} running]" if running > 0 else ""

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
        self.speak("I cannot do that.")

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
        old_stt_model  = self._config.get("stt_model", "tiny").lower()
        old_tts_engine = self._config.get("tts_engine", "edgetts").lower()
        old_tts_voice  = self._config.get("tts_voice", "")
        old_llm_model  = self._config.get("llm_model", "")
        new_stt_engine = new_config.get("stt_engine", "whisper").lower()
        new_stt_model  = new_config.get("stt_model", "tiny").lower()
        new_tts_engine = new_config.get("tts_engine", "edgetts").lower()
        new_tts_voice  = new_config.get("tts_voice", "")
        self._config = new_config
        invalidate_config_cache()

        # Install any packages required by the new config (fast if already installed)
        try:
            from core.installer import install_for_config
            install_for_config(new_config, log=self.ui.write_log)
        except Exception as e:
            self.ui.write_log(f"ERR: Dependency install — {e}")

        # TTS: only reload if engine or voice changed
        tts_changed = (
            new_tts_engine != old_tts_engine
            or new_tts_voice != old_tts_voice
        )
        if tts_changed:
            try:
                from core.tts import create_tts_player
                self._tts = create_tts_player(new_config)
                self._tts_ready.set()
                self.ui.write_log("SYS: TTS reconfigured.")
            except Exception as e:
                self.ui.write_log(f"ERR: TTS reconfigure — {e}")

        # STT: only reload if engine type or model changed
        stt_changed = (
            old_stt_engine != new_stt_engine
            or old_stt_model != new_stt_model
        )
        if stt_changed and old_stt_engine == new_stt_engine:
            try:
                stt_language = new_config.get("stt_language", "auto")
                if new_stt_engine == "vosk":
                    from core.stt import VoskSTT
                    self._stt = VoskSTT(new_config.get("vosk_model_path"), language=stt_language)
                else:
                    from core.stt import WhisperSTT
                    self._stt = WhisperSTT(new_stt_model, language=stt_language)
                self.ui.write_log("SYS: STT reconfigured.")
            except Exception as e:
                self.ui.write_log(f"ERR: STT reconfigure — {e}")
        elif stt_changed:
            self.ui.write_log("SYS: STT engine changed — restart required.")

        # LLM warmup if model changed
        if new_config.get("llm_model", "") != old_llm_model:
            self.ui.write_log("SYS: Warming up new LLM model…")
            from core.llm_client import warmup_model
            warmup_model()
            self.ui.write_log("SYS: New LLM model ready.")

        if stt_changed and old_stt_engine != new_stt_engine:
            self.speak("LLM and TTS updated. Restart for speech engine change.")
        elif tts_changed or stt_changed:
            self.speak("Configuration applied.")

    # ------------------------------------------------------------------
    # Text command (from UI input box)
    # ------------------------------------------------------------------

    def _on_text_command(self, text: str) -> None:
        self._generation += 1  # invalidates any in-flight _process_message with old gen
        self._text_queue.put(text)

    # ------------------------------------------------------------------
    # Tool execution (routing unchanged from original)
    # ------------------------------------------------------------------

    def _execute_tool(self, name: str, args: dict) -> str:
        print(f"[JARVIS] 🔧 {name}  {args}")
        self.ui.set_state("THINKING")

        if name == "greeting":
            return args.get("response", "Hello!")

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
                # Feed the dashboard: successful app launches teach Jarvis
                # which software is used daily.
                if r and not any(w in r for w in ("Could not", "Failed", "Unsupported")):
                    try:
                        dashboard_log_usage(args.get("app_name", ""))
                    except Exception:
                        pass

            elif name == "run_fcc":
                r = run_fcc_in_folder(parameters=args, response=None, player=self.ui)
                result = r or "Free Claude Code launched."

            elif name == "open_dashboard":
                r = open_dashboard(parameters=args, response=None, player=self.ui)
                result = r or "Dashboard opened."

            elif name == "add_dashboard":
                apps = args.get("apps") or []
                msgs = [add_to_dashboard(a) for a in apps]
                result = " ".join(msgs) if msgs else add_to_dashboard("")

            elif name == "remove_dashboard":
                apps = args.get("apps") or []
                msgs = [remove_from_dashboard(a) for a in apps]
                result = " ".join(msgs) if msgs else remove_from_dashboard("")

            elif name == "list_dashboard":
                result = list_dashboard()

            elif name == "weather_report":
                r = weather_action(parameters=args, player=self.ui)
                result = r or "Weather delivered."

            elif name == "browser_control":
                r = browser_control(parameters=args, player=self.ui)
                result = r or "Done."

            elif name == "browser_use":
                task = args.get("task", "")
                headless = args.get("headless", True)
                max_steps = int(args.get("max_steps", 30))
                timeout = int(args.get("timeout", 180))
                result = run_browser_use_task(
                    task=task, headless=headless,
                    max_steps=max_steps, timeout=timeout,
                )

            elif name == "file_controller":
                r = file_controller(parameters=args, player=self.ui)
                result = r or "Done."

            elif name == "send_message":
                r = send_message(parameters=args, response=None, player=self.ui, session_memory=None)
                result = r or f"Message sent to {args.get('receiver')}."

            elif name == "reminder":
                r = reminder(parameters=args, response=None, player=self.ui)
                result = r or "Reminder set."

            elif name == "timer":
                r = timer_handle(parameters=args)
                result = r

            elif name == "youtube_video":
                r = youtube_video(parameters=args, response=None, player=self.ui)
                result = r or "Done."

            elif name == "screen_process":
                # Synchronous call — returns analysis text which the LLM can speak
                r = screen_process(parameters=args, response=None, player=self.ui, session_memory=None)
                result = r if isinstance(r, str) and r else "Screen analyzed."

            elif name == "screen_explain":
                r = screen_explain(parameters=args)
                result = r if isinstance(r, str) and r else "I cannot do that."

            elif name == "generate_image":
                r = generate_image(parameters=args)
                result = r if isinstance(r, str) and r else "Image generation failed."

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
                goal = args.get("goal", "")
                # Try Hermes Agent first; fall back to task queue
                try:
                    r = hermes_agent_task(goal)
                    result = r or "Done."
                except Exception:
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
                        goal=goal, priority=priority, speak=self.speak
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
                if r:
                    import re
                    m = re.search(r'currently in ([^,]+)', r)
                    if m:
                        self.ui.set_location(m.group(1).strip())
                    else:
                        parts = r.split(".")
                        if parts:
                            self.ui.set_location(parts[0].replace("You are currently in ", ""))
                result = r or "Location retrieved."

            elif name == "maps":
                r = maps_action(parameters=args, player=self.ui)
                result = r or "Done."

            elif name == "stock_price":
                r = stock_price_action(parameters=args, player=self.ui)
                result = r or "Done."

            elif name == "news":
                r = news_action(parameters=args, player=self.ui)
                result = r or "Done."

            elif name == "get_datetime":
                result = get_datetime(parameters=args)
                if result:
                    self.speak(result)

            elif name == "shutdown_jarvis":
                self.ui.write_log("SYS: Shutdown requested.")

                def _shutdown():
                    import time
                    self.speak("Goodbye.")
                    time.sleep(2.5)
                    self.ui._win._quit_sig.emit()

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

            # ── Google Workspace tools ──────────────────────────────────────
            elif name == "gmail_get_unread":
                limit = int(args.get("limit", 10))
                emails = self._run_async(gws_get_unread_emails(limit=limit))
                if isinstance(emails, list) and emails:
                    lines = [f"Unread emails ({len(emails)}):"]
                    for e in emails:
                        subject = e.get("subject", e.get("Subject", "(no subject)"))
                        sender = e.get("from", e.get("From", "?"))
                        date = e.get("date", e.get("Date", ""))
                        lines.append(f"  From: {sender} | {subject} | {date}")
                    result = "\n".join(lines)
                else:
                    result = "No unread emails found."

            elif name == "gmail_search":
                query = args.get("query", "")
                emails = self._run_async(gws_search_emails(query=query))
                if isinstance(emails, list) and emails:
                    lines = [f"Gmail search results ({len(emails)}):"]
                    for e in emails:
                        subject = e.get("subject", e.get("Subject", "(no subject)"))
                        sender = e.get("from", e.get("From", "?"))
                        date = e.get("date", e.get("Date", ""))
                        lines.append(f"  From: {sender} | {subject} | {date}")
                    result = "\n".join(lines)
                else:
                    result = "No emails found matching that query."

            elif name == "gmail_send":
                to = args.get("to", "")
                subject = args.get("subject", "")
                body = args.get("body", "")
                self._run_async(gws_send_email(to=to, subject=subject, body=body))
                result = f"Email sent to {to}."

            elif name == "gmail_reply":
                message_id = args.get("message_id", "")
                body = args.get("body", "")
                self._run_async(gws_reply_email(message_id=message_id, body=body))
                result = "Reply sent."

            elif name == "calendar_agenda":
                days = int(args.get("days", 1))
                try:
                    if days == 1:
                        events = self._run_async(get_todays_agenda())
                    else:
                        events = self._run_async(get_upcoming_events(days=days))
                except Exception:
                    events = None
                if isinstance(events, list) and events:
                    lines = [f"Calendar ({'today' if days == 1 else f'next {days} days'}):"]
                    for e in events:
                        summary = e.get("summary", e.get("Summary", "(no title)"))
                        start = e.get("start", e.get("Start", ""))
                        end = e.get("end", e.get("End", ""))
                        meet_link = e.get("hangoutLink", e.get("meet", ""))
                        extra = ""
                        lines.append(f"  {summary}  ({start} - {end}){extra}")
                    result = "\n".join(lines)
                else:
                    from actions.task_manager import task_manager
                    result = task_manager({"action": "list", "status": "pending"})

            elif name == "calendar_create_event":
                title = args.get("title", "")
                date = args.get("date", "")
                time = args.get("time", "")
                duration = int(args.get("duration_minutes", 60))
                description = args.get("description", "")
                meet = args.get("meet", False)
                ev = self._run_async(create_event(
                    title=title, date=date, time=time,
                    duration_minutes=duration, description=description, meet=meet,
                ))
                result = f"Event '{title}' created on {date} at {time}."
                if meet:
                    link = ev.get("hangoutLink", ev.get("meet", ""))
                    if link:
                        result += f" Meet link: {link}"

            elif name == "calendar_delete_event":
                event_id = args.get("event_id", "")
                self._run_async(delete_event(event_id=event_id))
                result = "Event deleted."

            elif name == "drive_search":
                query = args.get("query", "")
                files = self._run_async(search_files(query=query))
                if isinstance(files, list) and files:
                    lines = [f"Drive files ({len(files)}):"]
                    for f in files:
                        fname = f.get("name", f.get("Name", "?"))
                        ftype = f.get("mimeType", "")
                        modified = f.get("modifiedTime", f.get("Modified", ""))
                        icon = "📄"
                        if "folder" in ftype: icon = "📁"
                        elif "sheet" in ftype: icon = "📊"
                        elif "doc" in ftype: icon = "📝"
                        elif "pdf" in ftype: icon = "📕"
                        lines.append(f"  {icon} {fname}  ({modified})")
                    result = "\n".join(lines)
                else:
                    result = "No files found."

            elif name == "drive_upload":
                local_path = args.get("local_path", "")
                folder_id = args.get("folder_id")
                self._run_async(upload_file(local_path=local_path, folder_id=folder_id))
                result = f"File uploaded to Drive."

            elif name == "drive_create_doc":
                title = args.get("title", "")
                content = args.get("content", "")
                doc = self._run_async(create_doc(title=title, content=content))
                doc_id = doc.get("documentId") or doc.get("id", "")
                result = f"Document '{title}' created. ID: {doc_id}"

            elif name == "meet_create":
                title = args.get("title", "")
                date = args.get("date", "")
                time = args.get("time", "")
                duration = int(args.get("duration_minutes", 60))
                ev = self._run_async(create_meet(
                    title=title, date=date, time=time, duration_minutes=duration,
                ))
                result = f"Google Meet '{title}' created for {date} at {time}."
                link = ev.get("hangoutLink", ev.get("meet", ""))
                if link:
                    result += f" Join: {link}"

            # ── New Feature Tools ─────────────────────────────────────────
            elif name == "screen_read":
                elems = get_ui_elements()
                if elems:
                    lines = [f"Screen elements ({len(elems)}):"]
                    for e in elems[:30]:
                        rect = e.get("rect") or {}
                        pos = f" [{rect.get('x',0)},{rect.get('y',0)}]" if rect else ""
                        lines.append(f"  {e['role']}: {e['name'][:80]}{pos}")
                    result = "\n".join(lines)
                else:
                    result = "No UI elements found (accessibility API may need permissions)."

            elif name == "active_window":
                info = get_active_window_info()
                result = f"Window: {info['title']} | App: {info['app']} | Role: {info['role']}"

            elif name == "detect_faces":
                r = analyze_camera_feed()
                if "error" in r:
                    result = r["error"]
                else:
                    people = r.get("people", [])
                    parts = [f"Detected {r['faces']} face(s):"]
                    for p in people:
                        parts.append(f"  Face at ({p['x']},{p['y']}) size {p['width']}x{p['height']}")
                    if r.get("expressions", {}).get("smiling"):
                        parts.append("  Smiling: Yes")
                    if r.get("expressions", {}).get("eyes_detected", 0) > 0:
                        parts.append(f"  Eyes: {r['expressions']['eyes_detected']}")
                    result = "\n".join(parts)

            elif name == "wake_word":
                action = args.get("action", "start")
                if action == "start":
                    model = args.get("model_name", "jarvis")
                    sens = float(args.get("sensitivity", 0.5))
                    result = start_wake_word(model_name=model, sensitivity=sens)
                elif action == "stop":
                    result = stop_wake_word()
                else:
                    result = f"Unknown wake word action: {action}"

            elif name == "github":
                action = args.get("action", "")
                gh = _get_gh_client()
                try:
                    if action == "clone":
                        result = clone_and_run(args.get("repo", ""), player=self.ui)
                    elif action == "list_repos":
                        repos = gh.list_repos(user=args.get("user"))
                        lines = [f"Repos ({len(repos)}):"]
                        for r in repos:
                            lines.append(f"  {r['full_name']} ({r['language']}) {'⭐'+str(r['stars']) if r['stars'] else ''}")
                        result = "\n".join(lines)
                    elif action == "create_repo":
                        r = gh.create_repo(name=args["name"], description=args.get("description", ""), private=args.get("private", False))
                        result = f"Repo created: {r['url']}"
                    elif action == "get_repo":
                        r = gh.get_repo(repo_full_name=args["repo"])
                        result = f"{r['full_name']}: {r['description']} ({r['language']}, {r['stars']}⭐)" if r else "Repo not found."
                    elif action == "list_issues":
                        issues = gh.list_issues(repo_full_name=args["repo"], state=args.get("state", "open"))
                        lines = [f"Issues ({len(issues)}):"]
                        for i in issues:
                            lines.append(f"  #{i['number']} {i['title']} [{i['state']}]")
                        result = "\n".join(lines)
                    elif action == "create_issue":
                        i = gh.create_issue(repo_full_name=args["repo"], title=args["name"], body=args.get("body", ""))
                        result = f"Issue #{i['number']} created: {i['url']}"
                    elif action == "close_issue":
                        i = gh.close_issue(repo_full_name=args["repo"], issue_number=int(args["number"]))
                        result = f"Issue #{i['number']} closed."
                    elif action == "list_prs":
                        prs = gh.list_prs(repo_full_name=args["repo"], state=args.get("state", "open"))
                        lines = [f"PRs ({len(prs)}):"]
                        for pr in prs:
                            lines.append(f"  #{pr['number']} {pr['title']} ({pr['author']})")
                        result = "\n".join(lines)
                    elif action == "get_pr":
                        pr = gh.get_pr(repo_full_name=args["repo"], pr_number=int(args["number"]))
                        result = f"PR #{pr['number']}: {pr['title']} ({pr['state']}) by {pr['author']} — +{pr['additions']}/-{pr['deletions']} in {pr['changed_files']} files"
                    elif action == "create_pr":
                        pr = gh.create_pr(repo_full_name=args["repo"], title=args["name"], head=args["head"], base=args.get("base", "main"), body=args.get("body", ""))
                        result = f"PR #{pr['number']} created: {pr['url']}"
                    elif action == "merge_pr":
                        r = gh.merge_pr(repo_full_name=args["repo"], pr_number=int(args["number"]))
                        result = f"PR merged: {r['message']}" if r['merged'] else f"Merge failed: {r['message']}"
                    elif action == "list_workflows":
                        flows = gh.list_workflows(repo_full_name=args["repo"])
                        lines = [f"Workflows ({len(flows)}):"]
                        for f in flows:
                            lines.append(f"  {f['name']} ({f['state']})")
                        result = "\n".join(lines)
                    elif action == "list_runs":
                        runs = gh.list_workflow_runs(repo_full_name=args["repo"], branch=args.get("branch", ""))
                        lines = [f"Workflow runs ({len(runs)}):"]
                        for r in runs:
                            lines.append(f"  {r['name']}: {r['status']} / {r['conclusion']}")
                        result = "\n".join(lines)
                    else:
                        result = f"Unknown GitHub action: {action}"
                except ImportError as e:
                    result = f"PyGithub not installed: {e}"
                except ValueError as e:
                    result = str(e)
                except Exception as e:
                    result = f"GitHub error: {e}"

            elif name == "search_files_fast":
                query = args.get("query", "")
                root = args.get("root")
                max_results = int(args.get("max_results", 20))
                files = search_files(query=query, root=root, max_results=max_results)
                if files:
                    lines = [f"Found {len(files)} files:"]
                    for f in files:
                        size = f.get("size", 0)
                        size_str = f"{size/1024:.1f}KB" if size > 0 else ""
                        lines.append(f"  {f['path']} {size_str}")
                    result = "\n".join(lines)
                else:
                    result = "No files found matching that name."

            elif name == "finance":
                fc = _get_finance_client()
                action = args.get("action", "")
                try:
                    if action == "accounts":
                        accs = fc.get_accounts()
                        lines = [f"Accounts ({len(accs)}):"]
                        for a in accs:
                            lines.append(f"  {a['name']} ({a['type']}): ${a['balance']:.2f}")
                        result = "\n".join(lines) if lines[1:] else "No accounts linked."
                    elif action == "transactions":
                        txns = fc.get_transactions(
                            start_date=args.get("start_date", ""),
                            end_date=args.get("end_date", ""),
                            limit=int(args.get("limit", 50)),
                        )
                        lines = [f"Transactions ({len(txns)}):"]
                        for t in txns:
                            lines.append(f"  {t['date']} ${t['amount']:.2f} — {t['name']}")
                        result = "\n".join(lines) if lines[1:] else "No transactions."
                    elif action in ("spending_summary", "summary"):
                        s = fc.get_spending_summary(days=int(args.get("days", 30)))
                        lines = [f"Spending (last {s['period_days']} days): Total ${s['total']} ({s['count']} txns)"]
                        for cat, amt in s.get("categories", {}).items():
                            lines.append(f"  {cat}: ${amt}")
                        result = "\n".join(lines)
                    elif action == "balances":
                        result = getattr(fc, "get_account_balances")()
                    else:
                        result = f"Unknown finance action: {action}"
                except ImportError as e:
                    result = f"Plaid not installed: {e}"
                except ValueError as e:
                    result = str(e)
                except Exception as e:
                    result = f"Finance error: {e}"

            elif name == "network_scan":
                action = args.get("action", "discover")
                if action == "discover":
                    timeout = int(args.get("timeout", 3))
                    devices = discover_services(timeout=timeout)
                    if devices:
                        lines = [f"Discovered {len(devices)} devices/services:"]
                        for d in devices:
                            addr = d.get("address", "")
                            name = d.get("name", "").replace("._tcp.local.", "")
                            svc = d.get("type", "").replace("._tcp.local.", "")
                            lines.append(f"  {name} ({svc}) @ {addr}")
                        result = "\n".join(lines)
                    else:
                        result = "No devices discovered on network."
                elif action == "local_ips":
                    ips = get_local_ips()
                    result = f"Local IPs: {', '.join(ips)}" if ips else "No local IPs found."
                else:
                    result = f"Unknown action: {action}"

            elif name == "voice_call":
                lk = _get_lk_client()
                action = args.get("action", "")
                try:
                    if action == "create_room":
                        r = lk.create_room(room_name=args.get("room_name", "jarvis-room"))
                        result = f"Room '{r['name']}' created (SID: {r['sid']})"
                    elif action == "list_rooms":
                        rooms = lk.list_rooms()
                        if rooms:
                            lines = [f"Active rooms ({len(rooms)}):"]
                            for r in rooms:
                                lines.append(f"  {r['name']} ({r['num_participants']} participants)")
                            result = "\n".join(lines)
                        else:
                            result = "No active rooms."
                    elif action == "generate_token":
                        token = lk.generate_token(
                            identity=args.get("identity", "jarvis"),
                            room_name=args.get("room_name", "jarvis-room"),
                        )
                        result = f"Token: {token}"
                    else:
                        result = f"Unknown action: {action}"
                except ImportError as e:
                    result = f"LiveKit not installed: {e}"
                except ValueError as e:
                    result = str(e)
                except Exception as e:
                    result = f"LiveKit error: {e}"

            elif name == "monitors":
                action = args.get("action", "list")
                if action == "list":
                    monitors = get_monitors()
                    if monitors:
                        lines = [f"Monitors ({len(monitors)}):"]
                        for m in monitors:
                            p = " (Primary)" if m["is_primary"] else ""
                            lines.append(f"  {m['name']}{p}: {m['width']}x{m['height']} @ ({m['x']},{m['y']})")
                        result = "\n".join(lines)
                    else:
                        result = "No monitor information available."
                elif action == "summary":
                    result = get_monitor_summary()
                elif action == "active":
                    m = get_active_monitor()
                    result = f"Active: {m['name']} ({m['width']}x{m['height']})" if m else "No monitor info."
                elif action == "brightness":
                    ok = set_monitor_brightness(
                        monitor_index=int(args.get("monitor", 0)),
                        brightness=float(args.get("brightness", 1.0)),
                    )
                    result = f"Brightness set to {args.get('brightness', '1.0')}" if ok else "Brightness control not supported."
                else:
                    result = f"Unknown monitors action: {action}"

            # ── Obsidian Vault ────────────────────────────────────────────
            elif name == "obsidian":
                action = args.get("action", "")
                try:
                    if action == "save":
                        r = save_note(
                            title=args.get("title", "Untitled"),
                            content=args.get("content", ""),
                            folder=args.get("folder", ""),
                        )
                        result = f"Note saved: {r['path']}"
                    elif action == "search":
                        notes = search_notes(
                            query=args.get("query", ""),
                            max_results=int(args.get("max_results", 10)),
                        )
                        if notes:
                            lines = [f"Notes ({len(notes)}):"]
                            for n in notes:
                                lines.append(f"  {n['title']} ({n['modified'][:10]})")
                            result = "\n".join(lines)
                        else:
                            result = "No matching notes found."
                    elif action == "list":
                        notes = list_notes(
                            folder=args.get("folder", ""),
                            max_results=int(args.get("max_results", 50)),
                        )
                        if notes:
                            lines = [f"Notes ({len(notes)}):"]
                            for n in notes:
                                lines.append(f"  {n['title']} ({n['modified'][:10]})")
                            result = "\n".join(lines)
                        else:
                            result = "No notes found."
                    elif action == "graph":
                        g = create_knowledge_graph()
                        result = f"Knowledge graph: {g['node_count']} notes, {g['edge_count']} wiki-link edges"
                    elif action == "tags":
                        tags = get_all_tags()
                        result = f"Tags ({len(tags)}): {', '.join(tags)}" if tags else "No tags found."
                    elif action == "set_vault":
                        result = set_vault_path(args.get("vault_path", ""))
                    else:
                        result = f"Unknown obsidian action: {action}"
                except Exception as e:
                    result = f"Obsidian error: {e}"

            # ── Package Manager ───────────────────────────────────────────
            elif name == "package_manager":
                action = args.get("action", "")
                pkg = args.get("package", "")
                mgr = args.get("manager", "auto")
                try:
                    if action == "install":
                        r = install_package(package=pkg, manager=mgr)
                        result = f"Installed {pkg} via {r['manager']}" if r.get("success") else f"Install failed: {r.get('output', '')}"
                    elif action == "uninstall":
                        r = uninstall_package(package=pkg, manager=mgr)
                        result = f"Uninstalled {pkg}" if r.get("success") else f"Uninstall failed: {r.get('output', '')}"
                    elif action == "list":
                        pkgs = list_installed(manager=mgr)
                        lines = [f"Packages via {mgr} ({len(pkgs)}):"]
                        for p in pkgs[:50]:
                            lines.append(f"  {p['name']} {p.get('version', '')}")
                        result = "\n".join(lines) if pkgs else f"No packages found via {mgr}."
                    elif action == "update_all":
                        r = update_all(manager=mgr)
                        result = "Packages updated." if r.get("success") else f"Update failed: {r.get('output', '')}"
                    elif action == "detect":
                        pm = detect_os_package_manager()
                        result = f"Detected package manager: {pm}"
                    else:
                        result = f"Unknown package action: {action}"
                except Exception as e:
                    result = f"Package manager error: {e}"

            # ── Goal Engine ───────────────────────────────────────────────
            elif name == "goals":
                action = args.get("action", "")
                try:
                    if action == "create":
                        g = create_goal(
                            title=args.get("title", ""),
                            description=args.get("description", ""),
                            steps=args.get("steps", []),
                        )
                        step_count = len(g["steps"])
                        result = f"Goal '{g['title']}' created ({step_count} steps, ID: {g['id']})"
                    elif action == "list":
                        goals = list_goals(status=args.get("status", ""))
                        if goals:
                            lines = [f"Goals ({len(goals)}):"]
                            for g in goals:
                                lines.append(f"  [{g['status']}] {g['title']} ({g['progress']}%)")
                            result = "\n".join(lines)
                        else:
                            result = "No goals found."
                    elif action == "get":
                        g = get_goal(goal_id=args.get("goal_id", ""))
                        if g:
                            lines = [f"Goal: {g['title']} ({g['progress']}%)"]
                            for i, s in enumerate(g["steps"]):
                                mark = "✓" if s["done"] else "○"
                                lines.append(f"  {mark} {s['title']}")
                            result = "\n".join(lines)
                        else:
                            result = "Goal not found."
                    elif action == "progress":
                        g = update_goal_progress(
                            goal_id=args.get("goal_id", ""),
                            step_index=int(args["step_index"]) if "step_index" in args else None,
                            status=args.get("status", ""),
                        )
                        result = f"Progress: {g['title']} at {g['progress']}%" if g else "Goal not found."
                    elif action == "complete_step":
                        g = complete_step(goal_id=args.get("goal_id", ""), step_title=args.get("step_title", ""))
                        result = f"Step completed. Progress: {g['progress']}%" if g else "Goal/step not found."
                    elif action == "delete":
                        ok = delete_goal(goal_id=args.get("goal_id", ""))
                        result = "Goal deleted." if ok else "Goal not found."
                    elif action == "summary":
                        result = get_goal_summary()
                    else:
                        result = f"Unknown goals action: {action}"
                except Exception as e:
                    result = f"Goal engine error: {e}"

            # ── Task Graph ────────────────────────────────────────────────
            elif name == "task_graph":
                action = args.get("action", "")
                try:
                    if action == "create":
                        t = create_task(
                            task_id=args.get("task_id", ""),
                            description=args.get("description", ""),
                            depends_on=args.get("depends_on", []),
                        )
                        result = f"Task '{t['id']}' created (deps: {t.get('dependencies', [])})"
                    elif action == "complete":
                        t = complete_task(task_id=args.get("task_id", ""))
                        result = f"Task '{t['id']}' completed." if t.get("done") else t.get("error", "Failed")
                    elif action == "available":
                        tasks = get_available_tasks()
                        if tasks:
                            lines = [f"Available tasks ({len(tasks)}):"]
                            for t in tasks:
                                lines.append(f"  {t['id']}: {t['description']}")
                            result = "\n".join(lines)
                        else:
                            result = "No available tasks (all done or waiting on dependencies)."
                    elif action == "summary":
                        result = get_task_graph_summary()
                    elif action == "critical_path":
                        path = get_critical_path()
                        result = f"Critical path: {' → '.join(path)}" if path else "No tasks in graph."
                    elif action == "delete":
                        ok = delete_task(task_id=args.get("task_id", ""))
                        result = "Task deleted." if ok else "Task not found."
                    elif action == "reset":
                        reset_graph()
                        result = "Task graph reset."
                    else:
                        result = f"Unknown task_graph action: {action}"
                except ImportError:
                    result = "NetworkX required — pip install networkx"
                except Exception as e:
                    result = f"Task graph error: {e}"

            # ── Tasks ──────────────────────────────────────────────────────
            elif name == "tasks":
                action = args.get("action", "list").strip().lower()
                try:
                    if action == "add":
                        title = args.get("title", "").strip()
                        if not title:
                            result = "Please provide a task title."
                        else:
                            result = add_task(title, args.get("priority", "normal"), args.get("due", ""))
                    elif action == "complete":
                        result = complete_task(args.get("task_id", ""))
                    elif action == "delete":
                        result = delete_task(args.get("task_id", ""))
                    else:
                        result = list_tasks(args.get("status", ""))
                except Exception as e:
                    result = f"Task manager error: {e}"

            # ── Todo Display ───────────────────────────────────────────────
            elif name == "todo_display":
                from actions.todo_display import show_todo_panel
                result = show_todo_panel(parameters=args, player=self.ui)

            # ── Budget Tracker ──────────────────────────────────────────────
            elif name == "budget":
                action = args.get("action", "summary").strip().lower()
                try:
                    if action == "add":
                        desc = args.get("description", "").strip()
                        if not desc:
                            result = "Please provide a description."
                        else:
                            result = add_transaction(desc, float(args.get("amount", 0)),
                                                     args.get("category", "other"),
                                                     args.get("type", "expense"))
                    elif action == "list":
                        result = list_transactions(args.get("category", ""), args.get("type", ""))
                    else:
                        result = budget_summary(args.get("period", "all"), args.get("category", ""))
                except Exception as e:
                    result = f"Budget error: {e}"

            # ── Security Vault ────────────────────────────────────────────
            elif name == "vault":
                action = args.get("action", "")
                key = args.get("key", "")
                try:
                    if action == "store":
                        result = store_secret(key=key, value=args.get("value", ""))
                    elif action == "get":
                        val = get_secret(key=key)
                        result = f"{key}: {val}" if val else f"Secret '{key}' not found."
                    elif action == "list":
                        keys = list_secrets()
                        result = f"Secrets ({len(keys)}): {', '.join(keys)}" if keys else "No secrets stored."
                    elif action == "delete":
                        result = delete_secret(key=key)
                    else:
                        result = f"Unknown vault action: {action}"
                except Exception as e:
                    result = f"Vault error: {e}"

            # ── Context Bus ───────────────────────────────────────────────
            elif name == "context":
                action = args.get("action", "summary")
                try:
                    if action == "summary":
                        result = get_bus().get_summary()
                    elif action == "get":
                        val = get_context(key=args.get("key", ""))
                        result = f"{args['key']}: {val}" if val else f"Key '{args.get('key')}' not found."
                    elif action == "search":
                        entries = get_bus().search(query=args.get("query", ""))
                        if entries:
                            lines = [f"Context history ({len(entries)}):"]
                            for e in entries:
                                lines.append(f"  [{e['timestamp'][:19]}] {e['key']}: {e['value']}")
                            result = "\n".join(lines)
                        else:
                            result = "No matching context entries."
                    elif action == "keys":
                        ctx = get_all_context()
                        result = f"Context keys ({len(ctx)}): {', '.join(sorted(ctx.keys()))}" if ctx else "No context data."
                    else:
                        result = f"Unknown context action: {action}"
                except Exception as e:
                    result = f"Context bus error: {e}"

            # ── Project Scaffold ────────────────────────────────────────────
            elif name == "scaffold":
                r = scaffold_project(parameters=args, speak=self.speak, player=self.ui)
                result = r or "Project scaffolded."

            # ── Project Init ────────────────────────────────────────────────
            elif name == "project_init":
                r = project_init_handle(parameters=args)
                result = r

            # ── Project Initializer (Universal) ─────────────────────────────
            elif name == "projectinitializer":
                r = project_initializer_handle(parameters=args)
                result = r

            # ── Relationship Graph ─────────────────────────────────────────
            elif name == "relationship_graph":
                action = args.get("action", "")
                try:
                    if action == "add_node":
                        props = {}
                        if args.get("properties"):
                            try:
                                props = json.loads(args["properties"])
                            except Exception:
                                props = {"note": args["properties"]}
                        n = add_node(
                            node_id=args.get("node_id", args.get("name", "").lower().replace(" ", "_")),
                            node_type=args.get("node_type", "project"),
                            name=args.get("name", ""),
                            properties=props,
                        )
                        result = f"Node '{n['name']}' ({n['type']}) created."
                    elif action == "remove_node":
                        ok = remove_node(node_id=args.get("node_id", ""))
                        result = "Node removed." if ok else "Node not found."
                    elif action == "add_edge":
                        e = add_edge(
                            source_id=args.get("node_id", ""),
                            target_id=args.get("target_id", ""),
                            relation=args.get("relation", ""),
                        )
                        result = f"Edge: {e['source']} → {e['target']} ({e['relation']})"
                    elif action == "remove_edge":
                        ok = remove_edge(
                            source_id=args.get("node_id", ""),
                            target_id=args.get("target_id", ""),
                        )
                        result = "Edge removed." if ok else "Edge not found."
                    elif action == "get_related":
                        rels = get_related(node_id=args.get("node_id", ""))
                        if rels:
                            lines = [f"Related to '{args['node_id']}':"]
                            for r in rels:
                                arrow = "→" if r["direction"] == "outbound" else "←"
                                lines.append(f"  {arrow} {r['node']['name']} ({r['relation'] or 'related'})")
                            result = "\n".join(lines)
                        else:
                            result = "No related nodes found."
                    elif action == "resolve_deployment":
                        result = resolve_deployment(project_name=args.get("project", args.get("name", "")))
                    elif action == "summary":
                        result = get_graph_summary()
                    else:
                        result = f"Unknown relationship_graph action: {action}"
                except Exception as e:
                    result = f"Relationship graph error: {e}"

            # ── Forensics ──────────────────────────────────────────────────
            elif name == "forensics":
                action = args.get("action", "summary")
                days = int(args.get("days", 1))
                try:
                    if action == "files":
                        files = file_history(days=days, path=args.get("path", ""))
                        if files:
                            lines = ["Recent file changes:"]
                            for f in files[:20]:
                                lines.append(f"  [{f['modified'][:19]}] {f['name']} ({f['path'][:80]})")
                            result = "\n".join(lines)
                        else:
                            result = "No recent file changes."
                    elif action == "processes":
                        procs = process_history(days=days)
                        if procs:
                            lines = [f"Top processes ({len(procs)}):"]
                            for p in procs[:20]:
                                cmd = p.get("command", p.get("name", p.get("pid", "?")))
                                lines.append(f"  PID {p['pid']}: {cmd}")
                            result = "\n".join(lines)
                        else:
                            result = "No process data."
                    elif action == "network":
                        nets = network_history(days=days)
                        if nets:
                            lines = [f"Network connections ({len(nets)}):"]
                            for n in nets[:20]:
                                peer = n.get("peer", n.get("local", ""))
                                state = n.get("state", "")
                                extra = f" [{state}]" if state else ""
                                lines.append(f"  {peer}{extra}")
                            result = "\n".join(lines)
                        else:
                            result = "No network connections."
                    elif action == "installed":
                        result = what_installed_since(days=days)
                    elif action == "summary":
                        result = get_forensics_summary(days=days)
                    else:
                        result = f"Unknown forensics action: {action}"
                except Exception as e:
                    result = f"Forensics error: {e}"

            # ── Remote Control ─────────────────────────────────────────────
            elif name == "remote_control":
                result = remote_control(parameters=args, player=self.ui)

            # ── Federation ─────────────────────────────────────────────────
            elif name == "federation":
                result = federation(parameters=args, player=self.ui)

            elif name == "google_workspace":
                result = google_workspace_action(parameters=args, player=self.ui)

            elif name == "books":
                result = book_controller(parameters=args, player=self.ui)

            elif name == "jobs":
                result = job_search_action(parameters=args, player=self.ui)

            elif name == "realtime_tutor":
                if args.get("action") == "stop":
                    result = stop_tutor()
                else:
                    result = realtime_tutor(parameters=args, player=self.ui)

            elif name == "read_emails":
                result = read_emails(parameters=args, player=self.ui)

            elif name == "habit_tracker":
                result = handle_habit(parameters=args, player=self.ui)

            elif name == "set_timer":
                result = timer_handle(parameters=args, player=self.ui)

            elif name == "convert_file":
                result = convert_file(parameters=args, player=self.ui)

            elif name == "random_number":
                result = random_number(parameters=args, player=self.ui)

            elif name == "system_info":
                result = system_info(parameters=args, player=self.ui)

            elif name == "convert_units":
                result = convert_units(parameters=args, player=self.ui)

            elif name == "filesystem_query":
                from actions.file_controller import get_largest_files, get_disk_usage
                a = (args or {}).get("action", "largest")
                path = (args or {}).get("path", "home")
                count = int((args or {}).get("count", 10))
                if a == "disk_usage":
                    result = get_disk_usage(path=path)
                else:
                    result = get_largest_files(path=path, count=count)

            else:
                result = "I cannot do that."
                self.ui.show_error_state(f"Unknown tool — {name}")

        except Exception as e:
            result = "I cannot do that."
            short = str(e)[:120]
            self.ui.show_error_state(f"{name} — {short}")
            traceback.print_exc()

        print(f"[JARVIS] 📤 {name} → {str(result)[:80]}")
        return result

    # ------------------------------------------------------------------
    # Async helper for Google Workspace tools
    # ------------------------------------------------------------------

    @staticmethod
    def _run_async(coro) -> Any:
        """Run an async coroutine synchronously. Safe because this runs in a background thread."""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    # ------------------------------------------------------------------
    # LLM processing loop
    # ------------------------------------------------------------------

    def _prefetch_context(self, user_text: str) -> None:
        try:
            self._prefetched_vec   = get_relevant_context(user_text)
            self._prefetched_skill = get_active_skill_context(user_text)
        except Exception:
            self._prefetched_vec   = ""
            self._prefetched_skill = ""

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

        Cancellation: snapshots self._generation at entry.  If the counter
        advances (new text command from the UI), this call winds down at the
        next safe checkpoint so the new message can be processed immediately.
        """
        _gen = self._generation
        def _cancelled() -> bool:
            return _gen != self._generation

        # Wait for background prefetch to complete (started in _listen_whisper)
        pf_thread = getattr(self, "_prefetch_thread", None)
        if pf_thread and pf_thread.is_alive():
            pf_thread.join(timeout=2.0)
        # If it didn't finish in time, _build_system_prompt falls through to inline load
        self._prefetch_thread = None

        self._auto_switch_language(user_text)
        self.ui.set_state("THINKING")
        self.ui.write_log(f"You: {user_text}")

        with self._conv_lock:
            self._conversation.append({"role": "user", "content": user_text})

        MAX_HISTORY = 10
        if len(self._conversation) > MAX_HISTORY:
            self._conversation = self._conversation[-MAX_HISTORY:]

        messages = [
            {"role": "system", "content": self._build_system_prompt(user_text)}
        ] + list(self._conversation)

        # ── Intent Router: bypass LLM for common commands ─────────────────
        self._last_intent = route_intent(user_text)
        if self._last_intent.matched and not self._last_intent.requires_ai:
            # Route directly — no LLM call needed
            tool_params = self._last_intent.handler_params
            self.ui.write_log(f"INTENT: {self._last_intent.intent_name} → {tool_params}")
            result = self._execute_tool(self._last_intent.handler_name, tool_params)
            if result == "__SILENT__":
                # Silent tools (save_memory) — don't speak, don't store
                return
            if result:
                self.speak(result)
                self.ui.write_log_instant(f"Jarvis: {result}")
            assistant_msg = {"role": "assistant", "content": result or ""}
            with self._conv_lock:
                self._conversation.append(assistant_msg)
            threading.Thread(target=store_conversation, args=(user_text, result or ""), daemon=True).start()
            return

        if _cancelled():
            self.ui.write_log("SYS: Cancelled — new input received")
            return

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
            if _cancelled():
                self.ui.write_log("SYS: Cancelled — new input received")
                break

            final_content    = ""
            final_tool_calls: list = []
            _streamed: list[str] = []

            # Skip sending ~50 tool definitions for simple greetings
            try:
                from core.llm_client import get_llm_provider
                _provider = get_llm_provider()
            except Exception:
                _provider = "ollama"

            # Ollama, Groq, NVIDIA NIM, OpenRouter, and OpenAI-compatible
            # providers all support tool calling — send tools unless it's
            # a greeting on the first round.
            _tools = None
            if not (_round == 0 and _is_greeting(user_text)):
                _tools = OLLAMA_TOOLS

            # ── Apply per-intent model override if configured ──────────
            override = None
            if self._last_intent.matched:
                ov = _load_config().get("model_overrides", {}).get(self._last_intent.intent_name)
                if ov:
                    override = (ov.get("provider"), ov.get("model"))
            try:
                for event in call_llm_stream(messages, _tools, model_override=override):
                    if event["type"] == "sentence":
                        # ── Overlap TTS with LLM generation ─────────────────
                        # Queue this sentence immediately; the TTS worker
                        # synthesises it while the LLM is still generating
                        # the next one. Write to log at the same time.
                        _streamed.append(event["text"])
                        self.speak(event["text"])
                        if len(_streamed) == 1:
                            self.ui.write_log_instant(f"Jarvis: {event['text']}")
                        else:
                            self.ui.write_log_instant(event["text"])
                    elif event["type"] == "done":
                        final_content    = event["content"]
                        final_tool_calls = event["tool_calls"]
            except RuntimeError as e:
                short = str(e)[:120]
                self.ui.write_log(f"ERR: LLM — {short}")
                self.speak("I cannot do that.")
                fallback = {"role": "assistant", "content": f"I'm sorry, I encountered an error: {short}"}
                with self._conv_lock:
                    self._conversation.append(fallback)
                return

            # ── Greeting guard ────────────────────────────────────────────────
            # Small models hallucinate action tool calls for greetings.
            # Strip ALL tool calls if user just said hello — the prompt already
            # tells the model not to run tools for general chat.
            if final_tool_calls and _round == 0 and _is_greeting(user_text):
                final_tool_calls = []
                if not final_content:
                    final_content = "Hello! How can I help you?"

            # ── No tool calls: pure conversational reply ─────────────────────
            if not final_tool_calls:
                if _streamed:
                    # Text already written to log during streaming — just update history.
                    assistant_msg = {"role": "assistant", "content": final_content}
                    messages.append(assistant_msg)
                    with self._conv_lock:
                        self._conversation.append(assistant_msg)
                elif final_content:
                    # Very short response (no sentence boundary) — speak now.
                    assistant_msg = {"role": "assistant", "content": final_content}
                    messages.append(assistant_msg)
                    with self._conv_lock:
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
            with self._conv_lock:
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
                with self._conv_lock:
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
                with self._conv_lock:
                    self._conversation.append(tool_msg)

            if _cancelled():
                self.ui.write_log("SYS: Cancelled after tool execution")
                break

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
                with self._conv_lock:
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
        """Mic → VAD → Whisper → LLM loop.

        Latency optimisation: as soon as VAD signals end-of-utterance we kick
        off transcription AND context pre-fetch in parallel.
          A) Whisper transcription  (CPU-bound, ~150-400 ms on 'tiny')
          B) Context pre-fetch      (network-bound: embedding + vector scan)

        Both run concurrently.  _process_message waits for (B) before building
        the system prompt, ensuring vector memory is ready when LLM fires.
        """
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
                            _text_result: list[str] = [""]
                            _raw_audio_ref = audio

                            def _do_transcribe():
                                _text_result[0] = self._stt.transcribe(_raw_audio_ref)

                            _t_asr = threading.Thread(target=_do_transcribe, daemon=True)
                            _t_asr.start()
                            _t_asr.join()

                            text = _text_result[0]
                            if text.strip():
                                self._prefetch_thread = threading.Thread(
                                    target=self._prefetch_context,
                                    args=(text,),
                                    daemon=True,
                                )
                                self._prefetch_thread.start()
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
                    with self._processing_lock:
                        self._process_message(text)
            except queue.Empty:
                pass
            except Exception as e:
                short = str(e)[:120]
                self.ui.show_error_state(f"TextCmd — {short}")
                traceback.print_exc()

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
            _warmup_done.wait(timeout=15)
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

            # ── Fetch location in background (cached for later use) ───────
            _loc_set = False

            def _init_location():
                nonlocal _loc_set
                try:
                    from actions.get_location import get_location
                    r = get_location(player=self.ui, force_refresh=True)
                    import re
                    m = re.search(r'currently in ([^,]+)', r)
                    if m:
                        self.ui.set_location(m.group(1).strip())
                        _loc_set = True
                except Exception:
                    pass
                if not _loc_set:
                    try:
                        from actions.get_location import _ip_location
                        ip_data = _ip_location()
                        if ip_data and ip_data.get("city"):
                            self.ui.set_location(ip_data["city"])
                    except Exception:
                        pass
            threading.Thread(target=_init_location, daemon=True).start()

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
