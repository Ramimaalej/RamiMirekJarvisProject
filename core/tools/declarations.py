"""Tool declarations (Gemini format) + Ollama conversion utilities."""
from __future__ import annotations


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

