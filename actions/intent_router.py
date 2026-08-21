"""Intent Router — routes voice/text commands to the right subsystem without LLM.

Architecture:
  Voice Input
      ↓
  Intent Router
   ├── Gmail          (gmail/email matches)
   ├── Browser        (open/go to/search web)
   ├── Calendar       (calendar/schedule/event)
   ├── GitHub         (github/repo/pr/issue)
   ├── Media          (play music/video/spotify)
   ├── System         (open app/settings/volume)
   ├── Obsidian       (note/save/remember)
   └── AI             (everything else → LLM)

Huge speed improvement — simple commands skip LLM entirely.
"""

from __future__ import annotations
from actions.mega_router import mega_route

import json
import logging
import re
import time
from pathlib import Path
from typing import Any

from actions.capability_registry import find_matches

logger = logging.getLogger("intent_router")

# ── Intent definitions ───────────────────────────────────────────────────
# Each intent has: name, patterns (regex list), subsystem, and handler name
# Patterns are matched in order — first match wins.

_INTENTS: list[dict[str, Any]] = [
    {
        "name": "stock_market",
        "subsystem": "tools",
        "patterns": [
            r'stock\s+price\s+of\s+[A-Z0-9.]+',
            r'prix\s+de\s+l\s*action\s+[A-Z0-9.]+',
            r'action\s+[A-Z0-9.]+\s+bourse',
            r'how\s+is\s+[A-Z0-9.]+\s+doing',
        ],
        "handler": "stock_market",
        "requires_ai": False,
    },
    {
        "name": "translator",
        "subsystem": "tools",
        "patterns": [
            r'translate\s+.+?\s+into?\s+\w+',
            r'traduis\s+.+?\s+en\s+\w+',
            r'comment\s+dit\s*on\s+.+?\s+en\s+\w+',
            r'traduction\s+de\s+.+?\s+vers\s+\w+',
        ],
        "handler": "translator",
        "requires_ai": False,
    },
    {
        "name": "media_downloader",
        "subsystem": "tools",
        "patterns": [
            r'download\s+video\s+from\s+https?',
            r'télécharger\s+la\s+vidéo\s+de\s+https?',
            r'save\s+image\s+from\s+https?',
            r'youtube\s+download\s+https?',
        ],
        "handler": "media_downloader",
        "requires_ai": False,
    },
    {
        "name": "speedtest",
        "subsystem": "tools",
        "patterns": [
            r'run\s+speedtest',
            r'test\s+my\s+internet\s+speed',
            r'vitesse\s+internet',
            r'test\s+de\s+débit',
        ],
        "handler": "speedtest",
        "requires_ai": False,
    },
    {
        "name": "process_mgr",
        "subsystem": "tools",
        "patterns": [
            r'list\s+all\s+processes',
            r'liste\s+les\s+processus',
            r'qu\s*est\s+ce\s+qui\s+tourne',
            r'kill\s+process\s+.+',
            r'terminer\s+l\s*application\s+.+',
        ],
        "handler": "process_mgr",
        "requires_ai": False,
    },
    {
        "name": "archive_tools",
        "subsystem": "tools",
        "patterns": [
            r'archive\s+.+?\s+to\s+.+',
            r'compresser\s+.+?\s+en\s+.+',
            r'extract\s+.+?\s+to\s+.+',
            r'décompresser\s+.+?\s+dans\s+.+',
        ],
        "handler": "archive_tools",
        "requires_ai": False,
    },
    {
        "name": "image_edit",
        "subsystem": "tools",
        "patterns": [
            r'resize\s+image\s+.+?\s+to\s+\d+x\d+',
            r'redimensionner\s+l\s*image\s+.+?\s+à\s+\d+x\d+',
            r'grayscale\s+.+',
            r'noir\s+et\s+blanc\s+.+',
        ],
        "handler": "image_edit",
        "requires_ai": False,
    },
    {
        "name": "wiki_tools",
        "subsystem": "tools",
        "patterns": [
            r'wikipedia\s+for\s+.+',
            r'recherche\s+wiki\s+pour\s+.+',
            r'who\s+is\s+.+?\s+on\s+wikipedia',
            r'qui\s+est\s+.+?\s+sur\s+wikipedia',
        ],
        "handler": "wiki_tools",
        "requires_ai": False,
    },
    {
        "name": "system_health",
        "subsystem": "tools",
        "patterns": [
            r'check\s+system\s+health',
            r'santé\s+du\s+système',
            r'état\s+du\s+pc',
            r'how\s+is\s+my\s+pc',
        ],
        "handler": "system_health",
        "requires_ai": False,
    },
    {
        "name": "news_pro",
        "subsystem": "tools",
        "patterns": [
            r'get\s+latest\s+news\s+about\s+.+',
            r'actualités\s+de\s+.+',
            r'tech\s+news',
            r'business\s+news',
        ],
        "handler": "news_pro",
        "requires_ai": False,
    },
    {
        "name": "devices_scan",
        "subsystem": "tools",
        "patterns": [
            r'what\s+is\s+connected',
            r'qu\s*est\s+ce\s+qui\s+est\s+branché',
            r'connected\s+devices',
            r'écrans\s+connectés',
            r'monitors\s+connected',
        ],
        "handler": "devices_scan",
        "requires_ai": False,
    },
    {
        "name": "qr_tools",
        "subsystem": "tools",
        "patterns": [
            r'generate\s+a\s+qr\s*code\s+for\s+.+',
            r'fais\s+un\s+qr\s*code\s+pour\s+.+',
            r'scan\s+qr\s*code',
        ],
        "handler": "qr_tools",
        "requires_ai": False,
    },
    {
        "name": "clipboard_mgr",
        "subsystem": "tools",
        "patterns": [
            r'what\s+is\s+in\s+my\s+clipboard',
            r'lis\s+mon\s+presse-papiers',
            r'copy\s+.+?\s+to\s+clipboard',
            r'copie\s+.+?\s+dans\s+le\s+presse-papiers',
        ],
        "handler": "clipboard_mgr",
        "requires_ai": False,
    },
    {
        "name": "math_solver",
        "subsystem": "tools",
        "patterns": [
            r'calcule\s+.+',
            r'combien\s+fait\s+.+',
            r'solve\s+.+',
        ],
        "handler": "math_solver",
        "requires_ai": False,
    },
    {
        "name": "hash_tools",
        "subsystem": "tools",
        "patterns": [
            r'hash\s+this\s+text\s*:\s*.+',
            r'sha256\s+of\s+file\s+.+',
            r'md5\s+of\s+.+',
        ],
        "handler": "hash_tools",
        "requires_ai": False,
    },
    {
        "name": "random_tools",
        "subsystem": "tools",
        "patterns": [
            r'roll\s+a\s+d\d+',
            r'lance\s+les\s+dés',
            r'pile\s+ou\s+face',
            r'heads\s+or\s+tails',
        ],
        "handler": "random_tools",
        "requires_ai": False,
    },
    {
        "name": "notes_tools",
        "subsystem": "tools",
        "patterns": [
            r'note\s*:\s*.+',
            r'list\s+my\s+notes',
            r'liste\s+mes\s+notes',
        ],
        "handler": "notes_tools",
        "requires_ai": False,
    },
    {
        "name": "system_info_tools",
        "subsystem": "tools",
        "patterns": [
            r'battery\s+level',
            r'what\s+my\s+battery',
            r'check\s+battery',
            r'niveau\s+de\s+batterie',
            r'quelle\s+batterie',
            r'wifi\s+ssid',
            r'disk\s+info',
        ],
        "handler": "system_info_tools",
        "requires_ai": False,
    },
    {
        "name": "screen_ocr",
        "subsystem": "tools",
        "patterns": [
            r'is\s+the\s+word\s+.+?\s+visible',
            r'trouve\s+le\s+mot\s+.+?\s+sur\s+mon\s+écran',
        ],
        "handler": "screen_ocr",
        "requires_ai": False,
    },
    {
        "name": "check_crypto",
        "subsystem": "tools",
        "patterns": [
            r'bitcoin\s+price',
            r'prix\s+du\s+bitcoin',
            r'ethereum\s+value',
            r'btc\s+price',
        ],
        "handler": "check_crypto",
        "requires_ai": False,
    },
    {
        "name": "check_time",
        "subsystem": "tools",
        "patterns": [
            r'what\s+time\s+is\s+it\s+in\s+.+',
            r'quelle\s+heure\s+à\s+.+',
            r'time\s+in\s+.+',
            r'heure\s+à\s+.+',
        ],
        "handler": "check_time",
        "requires_ai": False,
    },
    {
        "name": "create_document",
        "subsystem": "documents",
        "patterns": [
            r'create\s+.+?\s+titled\s+.+',
            r'crée\s+.+?\s+titre\s+.+',
            r'write\s+.+?\s+titled\s+.+',
            r'generate\s+.+?\s+named\s+.+',
        ],
        "handler": "create_document",
        "requires_ai": False,
    },
    {
        "name": "read_pdf",
        "subsystem": "documents",
        "patterns": [
            r'read\s+pdf\s+.+',
            r'lis\s+le\s+pdf\s+.+',
            r'analyse\s+le\s+document\s+.+',
        ],
        "handler": "read_pdf",
        "requires_ai": False,
    },
    {
        "name": "install_tool",
        "subsystem": "tools",
        "patterns": [
            r'install\s+.+',
            r'installe\s+.+',
        ],
        "handler": "install_tool",
        "requires_ai": False,
    },
    {
        "name": "use_tool",
        "subsystem": "tools",
        "patterns": [
            r'run\s+(nmap|ping|traceroute|netstat|dig|whois|curl|ssh|docker)\s*.*',
        ],
        "handler": "use_tool",
        "requires_ai": False,
    },












































































































































































































































    # ── Extra micro-tools / public APIs / opencode ─────────────
























    # ── Extra micro-tools / public APIs / opencode ─────────────


    # ── Extra micro-tools / public APIs / opencode ─────────────
























    # ── Greetings (instant — no LLM) ──────────────────────────────────
    {
        "name": "greeting",
        "subsystem": "general",
        "patterns": [
            r"^(hi|hello|hey|yo|sup|good\s+(morning|afternoon|evening)|howdy|what'?s\s+up)",
        ],
        "handler": "greeting",
        "params": {"response": "Hello! How can I help you?"},
        "requires_ai": False,
    },

    # ── Personal Info (save memory directly, no LLM needed) ──────────
    {
        "name": "save_memory",
        "subsystem": "memory",
        "patterns": [
            r"^(my\s+name\s+is)\s+(.+)",
            r"^(i'?m?\s+called)\s+(.+)",
            r"^(call\s+me)\s+(.+)",
            r"^(you\s+can\s+call\s+me)\s+(.+)",
        ],
        "handler": "save_memory",
        "params": {"category": "identity", "key": "name"},
        "requires_ai": False,
    },
    {
        "name": "save_memory",
        "subsystem": "memory",
        "patterns": [
            r"^my\s+(email|mail)\s+is\s+(.+)",
            r"^my\s+(email|mail)\s+address\s+is\s+(.+)",
        ],
        "handler": "save_memory",
        "params": {"category": "identity", "key": "email"},
        "requires_ai": False,
    },
    {
        "name": "save_memory",
        "subsystem": "memory",
        "patterns": [
            r"^(i\s+live\s+in)\s+(.+)",
            r"^(i'?m?\s+from)\s+(.+)",
            r"^(i\s+am\s+from)\s+(.+)",
            r"^my\s+city\s+is\s+(.+)",
        ],
        "handler": "save_memory",
        "params": {"category": "identity", "key": "city"},
        "requires_ai": False,
    },
    {
        "name": "save_memory",
        "subsystem": "memory",
        "patterns": [
            r"^my\s+(phone|number|cell)\s+is\s+(.+)",
            r"^(call\s+me\s+at)\s+(.+)",
        ],
        "handler": "save_memory",
        "params": {"category": "identity", "key": "phone"},
        "requires_ai": False,
    },
    {
        "name": "save_memory",
        "subsystem": "memory",
        "patterns": [
            r"^my\s+birthday\s+is\s+(.+)",
        ],
        "handler": "save_memory",
        "params": {"category": "identity", "key": "birthday"},
        "requires_ai": False,
    },
    {
        "name": "save_memory",
        "subsystem": "memory",
        "patterns": [
            r"^i'?m?\s+(\d+)\s*(?:years?\s+old)?\s*$",
            r"^i\s+am\s+(\d+)\s*(?:years?\s+old)?\s*$",
            r"^my\s+age\s+is\s+(\d+)",
        ],
        "handler": "save_memory",
        "params": {"category": "identity", "key": "age"},
        "requires_ai": False,
    },

    # ── Gmail / Email ─────────────────────────────────────────────────
    {
        "name": "gmail_get_unread",
        "subsystem": "gmail",
        "patterns": [
            r"^(get|check|show|read|list)\s+(my\s+)?(unread\s+)?(emails?|messages?|inbox|gmail)",
            r"^(any|do I have)\s+(new\s+|any\s+)?(emails?|messages?|mail)",
            r"unread",
            r"inbox",
        ],
        "handler": "gmail_get_unread",
        "params": {"limit": 5},
        "requires_ai": False,
    },
    {
        "name": "gmail_search",
        "subsystem": "gmail",
        "patterns": [
            r"^(search|find|look\s+for)\s+(in\s+)?(gmail|email|mail)",
            r"find\s+.*\s+email",
        ],
        "handler": "gmail_search",
        "params": {},
        "requires_ai": False,
    },

    # ── Email Reader (IMAP — direct Gmail inbox) ──────────────────────
    {
        "name": "read_emails",
        "subsystem": "email",
        "patterns": [
            r"^(read|check|show|get|fetch|list)\s+(my\s+)?(emails|email|inbox|messages|mails|mail)",
            r"^(what'?s?\s+in\s+my\s+inbox)",
            r"^(latest|recent|new)\s+(emails|email|messages|mails|mail)",
            r"^(do\s+I\s+have\s+(any\s+)?(new\s+)?(emails|email|mail|mails|messages))",
            r"^(what\s+(are\s+)?my\s+(latest|recent|new)\s+(emails|mails|email|messages))",
            r"^what\s+(are\s+)?my\s+(latest\s+)?(emails|mails|email|messages)",
            r"^my\s+(latest|recent|new)\s+(emails|mails|email|messages)",
            r"^show\s+(my\s+)?(latest|recent)?\s*(emails|email|mails|mail|messages)",
        ],
        "handler": "read_emails",
        "params": {"hours": 24, "limit": 10},
        "requires_ai": False,  # routes directly with defaults
    },

    {
        "name": "send_message",
        "subsystem": "messaging",
        "patterns": [
            r"^(send|write|text)\s+(a\s+)?(message|dm|text)\s+(to|for)\s+.+\b(on|via)\b\s+(whatsapp|telegram|messenger|signal|discord|sms|imessage)",
            r"^(send|write)\s+(a\s+)?(whatsapp|telegram|signal|sms)\s+(message\s+)?(to|for)",
        ],
        "handler": "send_message",
        "params": {},
        "requires_ai": True,
        "priority": "high",
    },

    {
        "name": "gmail_send",
        "subsystem": "gmail",
        "patterns": [
            r"^(send|compose|write)\s+(an?\s+)?(email|mail)\s+(to|for)",
            r"^(send|compose|write)\s+(a\s+)?message\s+(to|for)\s+(?!.+\b(on|via)\b\s+(whatsapp|telegram|messenger|signal|discord|sms|imessage))",
            r"email\s+.*\s+that",
        ],
        "handler": "gmail_send",
        "params": {},
        "requires_ai": False,
    },

    # ── Calendar ─────────────────────────────────────────────────────
    {
        "name": "calendar_agenda",
        "subsystem": "calendar",
        "patterns": [
            r"^(what('?s| is| do I have)\s+on\s+(my\s+)?)?(calendar|schedule|agenda|plan)",
            r"^(show|list|get|check)\s+(my\s+)?(calendar|schedule|agenda|plan)",
            r"what(\'?s|\s+is)\s+(today|upcoming)(?:\s+on\s+(my\s+)?(calendar|schedule|agenda|plan))?\s*(?:schedule)?$",
            r"what\s+do\s+I\s+have\s+(today|tomorrow)",
            r"am\s+I\s+(free|busy)",
        ],
        "handler": "calendar_agenda",
        "params": {"days": 1},
        "requires_ai": False,
    },
    {
        "name": "calendar_create_event",
        "subsystem": "calendar",
        "patterns": [
            r"^(create|add|schedule|make|set\s+up)\s+(a\s+)?(calendar\s+)?(event|meeting|appointment)",
            r"^(remind|schedule)\s+me\s+",
        ],
        "handler": "calendar_create_event",
        "params": {},
        "requires_ai": True,
    },

    # ── Browser / Web ────────────────────────────────────────────────
    {
        "name": "fast_browser",
        "subsystem": "browser",
        "patterns": [
            r"^(open|go\s+to|visit|navigate\s+to)\s+(https?://|www\.|[a-z0-9\-]+\.[a-z])",
            r"^click\s+.+",
            r"^scroll\s+(up|down)",
            r"^(refresh|reload|back|new\s+tab|close\s+tab)",
            r"^grab\s+(the\s+)?page",
            r"^screenshot",
        ],
        "handler": "fast_browser",
        "params": {},
        "requires_ai": False,
        "priority": "high",
    },
    {
        "name": "open_app",
        "subsystem": "browser",
        "patterns": [
            r"^(open|launch|start|run|go\s+to)\s+",
        ],
        "handler": "open_app",
        "params": {},
        "requires_ai": False,
    },
    {
        "name": "screen_vision",
        "subsystem": "vision",
        "patterns": [
            r"^(see|look\s+at|show\s+me|read|scan)\s+(the\s+|my\s+|your\s+)?(screen|display|monitor)",
            r"^(what('s|\s+is)\s+(on|in)\s+(my\s+)?(screen|display))",
            r"^what\s+am\s+i\s+(looking\s+at|seeing)",
            r"^(lis|montre|montre-?moi|lisez)\b(\s+\S+){0,6}\s+(é|e)?cran",
            r"^(qu('?est|est\s+il)\s+-?ce\s+(qu('?il|il)\s+y\s+a|que\s+(tu|j)e\s+(vois|regard)|je\s+vois)|dis-?moi\s+(ce\s+)?que\s+(tu|j)e\s+(vois|regarde|lis))",
            r"^(lis|montre|lis-?moi|lis\s+moi)\b(?!\s+(moi\s+)?(une?|la|le|des|du))\s*(.*)\s*(é|e)?cran",
            r"^(screen|what\s+text\s+(is\s+on|do\s+you\s+see)|read\s+(the\s+)?text)\b",
        ],
        "priority": "high",
        "handler": "screen_vision",
        "params": {},
        "requires_ai": False,
    },
    {
        "name": "web_search",
        "subsystem": "browser",
        "patterns": [
            r"^(search|google|look\s+up|find\s+(out|on\s+the\s+web)|who\s+is|who\s+was|who\s+are|who\s+were)",
            r"^(what\s+is|what\s+was|what\s+are|what\s+were)\s+(?!my\s+(budget|spending|tasks?|schedule|calendar|agenda))",
            r"^(when|where|why|how)\s+(is|are|was|were|did|do|does|can|could|would|will)",
            r"^(price|bitcoin)",
            r"\?$",
        ],
        "handler": "web_search",
        "params": {},
        "requires_ai": True,
    },
    {
        "name": "auto_register",
        "subsystem": "browser",
        "patterns": [
            r"^(register|sign\s*up|create\s+(an?\s+)?account)\s+(me\s+)?(on|for|at)\s+(.+)",
            r"^(fill\s+(out\s+)?(a\s+)?form|fill\s+this\s+form)\s+(on|for|at)?\s*(.+)",
            r"^(fill\s+(out\s+)?(a\s+)?form|fill\s+this\s+form)\s*$",
        ],
        "handler": "browser_control",
        "params": {"action": "auto_fill"},
        "requires_ai": False,
    },

    # ── GitHub ───────────────────────────────────────────────────────
    {
        "name": "github_list_repos",
        "subsystem": "github",
        "patterns": [
            r"^(list|show)\s+(my\s+)?(repos|repositories|projects)",
            r"^my\s+(repos|repositories|projects)",
            r"github\s+(repos|repositories)",
        ],
        "handler": "github",
        "params": {"action": "list_repos"},
        "requires_ai": False,
    },
    {
        "name": "github_list_issues",
        "subsystem": "github",
        "patterns": [
            r"^(list|show|my|open)\s+(issues?|tickets)",
            r"github\s+(issues?|prs?)",
            r"^(show|check)\s+(my\s+)?(PRs?|pull\s+requests)",
        ],
        "handler": "github",
        "params": {"action": "list_issues"},
        "requires_ai": False,
    },
    {
        "name": "github_clone",
        "subsystem": "github",
        "patterns": [
            r"^(clone|download|pull)\s+(a\s+)?(github\s+)?(repo|repository|project)",
            r"^clone\s+",
            r"^(get|fetch|download)\s+(a\s+)?(github\s+)?(repo|repository)\s+",
            r"clone\s+(it|that|this|the\s+repo)",
        ],
        "handler": "github",
        "params": {"action": "clone"},
        "requires_ai": False,  # repo is parsed directly from the command
    },

    # ── Obsidian ─────────────────────────────────────────────────────

    {
        "name": "obsidian_save",
        "subsystem": "obsidian",
        "patterns": [
            r"^(save|remember|store|write)\s+(this\s+)?(as\s+)?(a\s+)?(note|idea|thought)",
            r"^(take|make)\s+(a\s+)?note",
            r"don'?t\s+(let\s+me\s+)?forget",
        ],
        "handler": "obsidian",
        "params": {"action": "save"},
        "requires_ai": True,
    },

    # ── System / Computer ────────────────────────────────────────────
    {
        "name": "computer_settings",
        "subsystem": "system",
        "patterns": [
            r"^(volume|brightness)\s+(up|down|mute|set|max|min)",
            r"(turn\s+(up|down|on|off))\s+(the\s+)?(volume|sound|brightness)",
            r"(increase|decrease)\s+(the\s+)?(volume|brightness)",
            r"^set\s+(the\s+)?(volume|brightness)\s+to\s+(\d+)",
            r"^(mute|unmute|lock|shutdown|restart|sleep)",
            r"(screenshot|screen\s+shot)",
            r"(speed\s*test|internet\s+speed|check\s+(my\s+)?(internet|connection|network)\s+(speed|connection))",
        ],
        "handler": "computer_settings",
        "params": {},
        "requires_ai": False,
    },
    {
        "name": "computer_settings",
        "subsystem": "system",
        "patterns": [
            r"(check|show)\s+(memory|ram|cpu|disk|system)\s+(usage|status|info)",
            r"^(how\s+much\s+)?(memory|ram)\s+(is\s+)?(used|available|free)",
        ],
        "handler": "computer_settings",
        "params": {"action": "system_info"},
        "requires_ai": False,
    },
    {
        "name": "get_location",
        "subsystem": "system",
        "patterns": [
            r"^(where\s+am\s+I|what'?s\s+my\s+location|my\s+location|current\s+location)",
        ],
        "handler": "get_location",
        "params": {},
        "requires_ai": False,
    },
    {
        "name": "weather_report",
        "subsystem": "system",
        "patterns": [
            r"(weather|temperature|forecast)",
            r"how\s+(cold|hot|warm)\s+(is\s+)?(it\s+)?",
            r"rain\s+(today|tomorrow)",
            r"(what'?s|what\s+is)\s+the\s+weather",
        ],
        "handler": "weather_report",
        "params": {},
        "requires_ai": False,
    },
    {
        "name": "get_datetime",
        "subsystem": "system",
        "patterns": [
            r"^(what\s+(day|time|date))\s+(is\s+)?(it\s+)?",
            r"^(what'?s\s+the\s+(time|date|day))",
            r"^(current\s+)?(date|time|day|hour|minute)",
            r"(today'?s?\s+)?(date|day)(?!\w)",
            r"what(\'?s|\s+is)\s+(the\s+)?date\s+(today|it)",
            r"what(\'?s|\s+is)\s+(the\s+)?day\s+(today|it)",
            r"what\s+(is\s+)?today'?s?\s+date",
            r"what\s+date\s+is\s+(today|it)",
            r"what\s+day\s+is\s+(today|it)",
            r"what(\'?s|\s+is)\s+the\s+date\s*$",
            r"tell\s+(me\s+)?(the\s+)?(date|day|time)",
            r"what(\'?s|\s+is)\s+(it\s+)?(right\s+)?now",
            r"what\s+day\s+of\s+the\s+week",
            r"what\s+(time|day)\s+is\s+it",
        ],
        "handler": "get_datetime",
        "params": {},
        "requires_ai": False,
    },
    # ── Timer / Alarm ────────────────────────────────────────────────
    { "name": "set_timer",
        "subsystem": "system",
        "patterns": [
            r"^(set|start|create|add)\s+(a\s+|an\s+)?(timer|countdown|alarm)",
            r"^(timer|alarm)\s+(for|in|of)",
            r"^remind\s+me\s+in\s+",
        ],
        "handler": "set_timer",
        "params": {},
        "requires_ai": False,
    },
    {
        "name": "stop_timer",
        "subsystem": "system",
        "patterns": [
            r"^(stop|cancel|delete|remove|clear|dismiss)\s+(a|the)?\s*(timer|alarm|countdown)",
            r"(timer|alarm)\s+(stop|cancel|off|disable)",
        ],
        "handler": "set_timer",
        "params": {"action": "stop"},
        "requires_ai": False,
    },
    # ── Calculator / Math ──────────────────────────────────────────────

    # ── Random Number ─────────────────────────────────────────────────
    {
        "name": "random_number",
        "subsystem": "system",
        "patterns": [
            r"^(generate|pick|get|give|create|roll)\s+(a?\s*)?(random\s+)?(number|integer|digit)",
            r"^(random\s+number|random\s+integer)",
            r"(roll|flip)\s+(a\s+)?(dice|coin|die)",
        ],
        "handler": "random_number",
        "params": {},
        "requires_ai": False,
    },
    {
        "name": "system_info",
        "subsystem": "system",
        "patterns": [
            r"^what\s+(is\s+)?(my\s+)?(os|operating\s+system|platform|system)",
            r"^(os|operating\s+system|platform|system)\s+(info|information|name|type)",
            r"(tell|show)\s+(me\s+)?(my\s+)?(os|operating\s+system)",
            r"^what\s+(computer|machine|pc|device|system)\s+(am\s+)?I\s+(using|on|running)",
            r"(what|cpu|processor)\s+(cpu|processor|chip)",
            r"(show|what|tell)\s+(me\s+)?(my\s+)?(hostname|computer\s+name|device\s+name)",
            r"(how\s+much|what)\s+(ram|memory)",
        ],
        "handler": "system_info",
        "params": {},
        "requires_ai": False,
    },
    # ── Unit Converter ────────────────────────────────────────────────
    {
        "name": "convert_units",
        "subsystem": "system",
        "patterns": [
            r"\d+\s*(km|mi|miles|kilometers|kg|lb|lbs|pounds|mph|kmh|celsius|fahrenheit|f|c|gal|l|liter|inch|feet|cm|mm)\s+(to|in|as)\s+",
            r"(convert|change)\s+.*(km|mi|miles|kg|lb|lbs|fahrenheit|celsius|inch|feet)\s+(to|into|in)\s+",
            r"(how\s+many|how\s+much)\s+(is|are)\s+.*(km|mi|kg|lb|f|c|inch|feet|gal|l)\s+",
            r"\d+\s*(degrees?\s*)?(celsius|fahrenheit|centigrade|kelvin)\s+(to|in|as)\s+",
            r"(how\s+many|how\s+much)\s+(km|mi|miles|kg|lb|f|c|celsius|fahrenheit)\s+(is|are)\s+.*(km|mi|miles|kg|lb|f|c)",
        ],
        "handler": "convert_units",
        "params": {},
        "requires_ai": False,
    },
    # ── File Converter ──────────────────────────────────────────────────
    {
        "name": "convert_file",
        "subsystem": "system",
        "patterns": [
            r"^(convert|change|transform)\s+(this\s+)?(file\s+)?(.+?)\s+(to|into)\s+",
            r"^(ocr|extract\s+text)\s+(from\s+)?(this\s+)?(image|picture|photo|screenshot)",
            r"^(turn|make)\s+(this\s+)?(image|picture|photo|pdf|doc|file).+(to|into)\s+",
        ],
        "handler": "convert_file",
        "params": {},
        "requires_ai": True,
    },
    # ── File System Queries ──────────────────────────────────────────
    {
        "name": "filesystem_query",
        "subsystem": "system",
        "patterns": [
            r"(largest|biggest|huge|size)\s+(files|folders|directories)",
            r"(disk|drive|storage)\s+(usage|space|size|free|available)",
            r"top\s+\d+\s+(largest|biggest)\s+(files|folders)",
            r"how\s+(much|many)\s+(space|storage|room|gb)\s+(left|free|available)",
            r"what['']?s?\s+(using|taking)\s+(up\s+)?(all\s+)?(the\s+)?(space|storage|disk)",
        ],
        "handler": "filesystem_query",
        "params": {},
        "requires_ai": False,
    },
    # ── Maps / Location ───────────────────────────────────────────────
    {
        "name": "maps",
        "subsystem": "system",
        "patterns": [
            r"^(where\s+is\s|find\s+|locate\s+|search\s+for\s+)(.+)",
            r"^(how\s+far|distance)\s+(.+)",
            r"(coordinates?|coords?|lat\s*(?:/|and|,)\s*lon)\s+(.+)",
            r"what('?s| is)\s+the\s+distance\s+between\s+(.+)\s+and\s+(.+)",
            r"(?:from\s+)?(.+)\s+to\s+(.+)\s+(?:in\s+)?(?:km|miles|distance)",
        ],
        "handler": "maps",
        "params": {},
        "requires_ai": False,
    },


    {
        "name": "books",
        "subsystem": "system",
        "patterns": [
            r"who\s+wrote\s+",
            r"book\s+(by|about|called|titled|named)",
            r"author\s+of\s+",
            r"search\s+(for\s+)?(a\s+)?book",
            r"(find|look\s+up)\s+(a\s+)?book",
        ],
        "handler": "books",
        "params": {},
        "requires_ai": False,
    },
    {
        "name": "file_controller_list",
        "subsystem": "system",
        "patterns": [
            r"^(list|show)\s+(my\s+)?(files?|desktop|downloads|documents)",
            r"what('?s| is)\s+(on|in)\s+(my\s+)?(desktop|downloads)",
        ],
        "handler": "file_controller",
        "params": {"action": "list"},
        "requires_ai": False,
    },

    # ── Media / Music ────────────────────────────────────────────────
    {
        "name": "play_music",
        "subsystem": "media",
        "patterns": [
            r"^(play|start)\s+(music|song|playlist|some\s+music)",
            r"play\s+.*\s+(by|from)",
        ],
        "handler": "play_music",
        "params": {},
        "requires_ai": True,
    },


    # ── Goals / Tasks ────────────────────────────────────────────────
    {
        "name": "goals_summary",
        "subsystem": "goals",
        "patterns": [
            r"^(what are|show|list|my)\s+(my\s+)?(goals?|progress|objectives)",
            r"how\s+(are|is)\s+(my|the)\s+(goals?|progress|project)",
        ],
        "handler": "goals",
        "params": {"action": "summary"},
        "requires_ai": False,
    },
    {
        "name": "tasks",
        "subsystem": "tasks",
        "patterns": [
            r"^(what are|show|list|get)\s+(my\s+)?(tasks?|todo|to-do|to do)",
            r"what('?s| is)\s+(my\s+)?(tasks?|todo)",
            r"^(any|do I have)\s+(tasks?|todo)",
        ],
        "handler": "tasks",
        "params": {"action": "list"},
        "requires_ai": False,
    },

    # ── Budget ────────────────────────────────────────────────────────
    {
        "name": "budget",
        "subsystem": "finance",
        "patterns": [
            r"(budget|spending|expenses?|transactions?|finance)",
            r"how\s+much\s+(did|have|do)\s+i\s+(spend|spent)",
            r"(add|log|record)\s+(a\s+)?(transaction|expense|spending)",
        ],
        "handler": "budget",
        "params": {"action": "summary"},
        "requires_ai": False,
    },

    # ── Monitor / Display ────────────────────────────────────────────
    {
        "name": "monitors_list",
        "subsystem": "display",
        "patterns": [
            r"^(list|show|what are)\s+(my\s+)?(monitors?|displays?|screens)",
            r"how\s+many\s+(monitors?|displays?|screens)",
        ],
        "handler": "monitors",
        "params": {"action": "summary"},
        "requires_ai": False,
    },

    # ── Package Manager ──────────────────────────────────────────────
    {
        "name": "package_detect",
        "subsystem": "packages",
        "patterns": [
            r"^(what|which)\s+package\s+manager",
        ],
        "handler": "package_manager",
        "params": {"action": "detect"},
        "requires_ai": False,
    },

    # ── Wake Word ────────────────────────────────────────────────────
    {
        "name": "wake_word_stop",
        "subsystem": "wake",
        "patterns": [
            r"^(stop|disable|turn\s+off)\s+(wake\s+word|listening|voice)",
            r"go\s+(to\s+)?sleep",
        ],
        "handler": "wake_word",
        "params": {"action": "stop"},
        "requires_ai": False,
    },
    {
        "name": "wake_word_start",
        "subsystem": "wake",
        "patterns": [
            r"^(start|enable|turn\s+on)\s+(wake\s+word|listening)",
            r"wake\s+up",
            r"^(hey|okay|wake)\s+(jarvis|computer)",
        ],
        "handler": "wake_word",
        "params": {"action": "start"},
        "requires_ai": False,
    },

    # ── Screen Explain (vision — what's on screen) ────────────────────
    {
        "name": "screen_explain",
        "subsystem": "vision",
        "patterns": [
            r"^(what('?s| is| do you see)\s+(on\s+)?(my\s+)?(screen|display|monitor))",
            r"^(what\s+do\s+you\s+see)\b",
            r"^(describe|analyze|look\s+at|read)\s+(my\s+)?(screen|display)",
            r"(what|what'?s)\s+on\s+(my\s+)?(screen|display)",
        ],
        "handler": "screen_explain",
        "params": {},
        "requires_ai": False,
    },

    # ── Capabilities ─────────────────────────────────────────────────
    {
        "name": "capabilities_list",
        "subsystem": "capabilities",
        "patterns": [
            r"^(what can you do|capabilities|help|what are your|what do you|list.*(capabilities?|abilities?|skills?))",
            r"^(show|list)\s+(capabilities?|commands?|features?)",
        ],
        "handler": "capabilities",
        "params": {},
        "requires_ai": False,
    },

    # ── Context ──────────────────────────────────────────────────────
    {
        "name": "context_summary",
        "subsystem": "context",
        "patterns": [
            r"^(what do you know|context|what'?s\s+going\s+on|status|current\s+state)",
            r"(what|how)\s+(is|are)\s+(everything|things|the\s+system)",
        ],
        "handler": "context",
        "params": {"action": "summary"},
        "requires_ai": False,
    },

    # ── Image Generation ─────────────────────────────────────────────
    {
        "name": "generate_image",
        "subsystem": "vision",
        "patterns": [
            r"^(generate|create|make|draw|render|produce)\s+(an?\s+)?(image|picture|photo|illustration|art|drawing|render)\s+(of\s+)?",
            r"^(generate|create|make|draw)\s+(me\s+)?(an?\s+)?(image|picture|photo)\s+",
        ],
        "handler": "generate_image",
        "params": {},
        "requires_ai": False,
    },

    # ── Project Scaffold ─────────────────────────────────────────────
    {
        "name": "scaffold_project",
        "subsystem": "scaffold",
        "patterns": [
            r"^(start|create|scaffold|new|build|make)\s+(a\s+)?(new\s+)?(project|app|application)",
            r"^create\s+(a\s+)?(new\s+)?(pos|point\s+of\s+sale|website|crm|api|backend|frontend)",
            r"i\s+(want\s+to\s+)?(build|create|make|start)\s+(a\s+)?(new\s+)?(project|app)",
            r"let'?s\s+(start|begin|create)\s+(a\s+)?(new\s+)?(project|app|application)",
        ],
        "handler": "scaffold",
        "params": {},
        "requires_ai": True,
    },
    {
        "name": "scaffold_list",
        "subsystem": "scaffold",
        "patterns": [
            r"^(list|show|my)\s+(projects|scaffolds)",
            r"what\s+(projects|apps)\s+(do|have)\s+I",
        ],
        "handler": "scaffold",
        "params": {},
        "requires_ai": False,
    },

    # ── Relationship Graph ───────────────────────────────────────────
    {
        "name": "relationship_deploy",
        "subsystem": "relationship",
        "patterns": [
            r"where\s+is\s+(\w+)\s+(deployed|hosted|running)",
            r"(deploy|host)\s+(info|information|details)\s+(for|about)\s+(\w+)",
            r"where\s+(does|is)\s+(\w+)\s+(live|run)",
        ],
        "handler": "relationship_graph",
        "params": {"action": "resolve_deployment"},
        "requires_ai": False,
    },
    {
        "name": "relationship_summary",
        "subsystem": "relationship",
        "patterns": [
            r"^(show|list|view)\s+(relationship|deployment)\s+(graph|map|diagram)",
            r"what'?s?\s+(connected|linked|related)\s+to\s+",
        ],
        "handler": "relationship_graph",
        "params": {"action": "summary"},
        "requires_ai": False,
    },

    # ── Forensics ────────────────────────────────────────────────────
    {
        "name": "forensics_installed",
        "subsystem": "forensics",
        "patterns": [
            r"what\s+(was\s+|has\s+been\s+|got\s+)?(installed|added|changed|modified)\s+(yesterday|recently|today|last\s+\w+)",
            r"^(what|show)\s+(did|has)\s+(I\s+)?install",
            r"(recent|latest)\s+(installs?|packages?|changes?)",
        ],
        "handler": "forensics",
        "params": {"action": "installed", "days": 1},
        "requires_ai": False,
    },
    {
        "name": "forensics_processes",
        "subsystem": "forensics",
        "patterns": [
            r"^(show|list|what\s+are)\s+(running\s+)?(processes?|apps?|programs?)",
            r"what\s+apps?\s+are\s+(currently\s+)?(running|open)",
            r"what\s+programs?\s+are\s+(currently\s+)?(running|open)",
            r"what'?s?\s+(running|using\s+cpu|using\s+memory)",
            r"(running|active)\s+(processes?|apps?|programs?)",
            r"(top|heavy)\s+(processes?|tasks?)",
        ],
        "handler": "forensics",
        "params": {"action": "processes"},
        "requires_ai": False,
    },
    {
        "name": "forensics_network",
        "subsystem": "forensics",
        "patterns": [
            r"^(show|list|check)\s+(network\s+)?(connections?|ports?|sockets?)",
            r"who'?s?\s+(connected|on\s+my\s+network)",
            r"(check|view)\s+network\s+(traffic|activity|status)",
        ],
        "handler": "forensics",
        "params": {"action": "network"},
        "requires_ai": False,
    },
    {
        "name": "forensics_summary",
        "subsystem": "forensics",
        "patterns": [
            r"^(forensics|system\s+history|activity\s+report|what\s+happened)",
            r"(investigate|audit|check)\s+(system|computer|pc)",
        ],
        "handler": "forensics",
        "params": {"action": "summary"},
        "requires_ai": True,
    },

    # ── Remote Control ───────────────────────────────────────────────
    {
        "name": "remote_start",
        "subsystem": "remote",
        "patterns": [
            r"^(start|begin|launch)\s+(remote\s+)?(control|server|api)",
            r"^(enable|open)\s+(remote\s+)?(access|control)",
        ],
        "handler": "remote_control",
        "params": {"action": "start"},
        "requires_ai": False,
    },
    {
        "name": "remote_stop",
        "subsystem": "remote",
        "patterns": [
            r"^(stop|close|shutdown)\s+(remote\s+)?(control|server|api)",
            r"^(disable|turn\s+off)\s+(remote\s+)?(access|control)",
        ],
        "handler": "remote_control",
        "params": {"action": "stop"},
        "requires_ai": False,
    },
    {
        "name": "remote_status",
        "subsystem": "remote",
        "patterns": [
            r"^(is|check)\s+(remote\s+)?(control|server)\s+(running|active|on)",
            r"remote\s+(control|server)\s+status",
        ],
        "handler": "remote_control",
        "params": {"action": "status"},
        "requires_ai": False,
    },

    # ── Federation ───────────────────────────────────────────────────
    {
        "name": "federation_status",
        "subsystem": "federation",
        "patterns": [
            r"^(federation|instances|cluster)\s+(status|summary|list)",
            r"^(list|show)\s+(federation|instances?|nodes?)",
            r"what\s+instances?\s+(are\s+)?(registered|online|active)",
        ],
        "handler": "federation",
        "params": {"action": "status"},
        "requires_ai": False,
    },
    {
        "name": "federation_share",
        "subsystem": "federation",
        "patterns": [
            r"^(share|sync|distribute)\s+(this\s+)?(memory|info|data|context)\s+(across|to|with)",
            r"^(remember|store)\s+(this\s+)?(across|on)\s+(all|every)\s+instance",
        ],
        "handler": "federation",
        "params": {"action": "share"},
        "requires_ai": True,
    },

    # ── Shutdown / Goodbye ───────────────────────────────────────────
    {
        "name": "shutdown_jarvis",
        "subsystem": "system",
        "patterns": [
            r"^(shut\s*(down|off)|goodbye|bye|exit|quit|stop\s+(yourself|jarvis|it|now))",
            r"(shut\s*(down|off)|exit|quit)\s+(jarvis|the\s+assistant)",
            r"(go\s+(to\s+)?)?(sleep|offline)",
            r"shut\s+(yourself|it)\s+down",
        ],
        "handler": "shutdown_jarvis",
        "params": {},
        "requires_ai": False,
    },

    # ── Hermes Agent (complex multi-step tasks) ──────────────────────
    {
        "name": "hermes_task",
        "subsystem": "hermes",
        "patterns": [
            r"^(research|investigate|analyze|study|examine)\s+",
            r"^(write|draft|compose|create|generate)\s+(a\s+)?(report|document|article|analysis|summary)",
            r"^(compare|contrast)\s+",
            r"^(plan|design|architect)\s+(a\s+)?(system|architecture|solution|workflow)",
            r"^(refactor|restructure|redesign|rewrite)\s+",
            r"^(debug|troubleshoot|fix)\s+(this\s+)?(complex|complicated|multi)",
        ],
        "handler": "agent_task",
        "params": {},
        "requires_ai": False,
    },

    # ── RealTime Tutor (Gemini 2.0 Flash voice/video) ────────────────
    {
        "name": "realtime_tutor",
        "subsystem": "tutor",
        "patterns": [
            r"^(start|open|launch)\s+(the\s+)?(gemini\s+)?(realtutor|tutor)",
            r"^(stop|close|exit)\s+(the\s+)?(gemini\s+)?(realtutor|tutor)",
            r"^(realtutor|tutor)\s+(mode|on|off)",
            r"^(gemini\s+)?(real\s+)?(realtime\s+)?tutor",
            r"^open\s+(the\s+)?(gemini\s+)?realtutor",
        ],
        "handler": "realtime_tutor",
        "params": {},
        "requires_ai": False,
    },

    # ── Habit Tracker ────────────────────────────────────────────────
    {
        "name": "habit_tracker",
        "subsystem": "productivity",
        "patterns": [
            r"^(habit|habits|tracker)",
            r"^(my|check|show|list)\s+(habit|habits|progress)",
            r"^(track|log|record)\s+(a\s+)?(habit|progress)",
            r"^what['']?s?\s+my\s+progress",
            r"^(mark|set)\s+(habit|task)\s+(as\s+)?(done|complete|completed)",
            r"^(create|add|new)\s+(a\s+)?(habit|tracker)",
        ],
        "handler": "habit_tracker",
        "params": {},
        "requires_ai": True,  # LLM extracts action/name/periodicity
    },

    # ── Flight Finder ──────────────────────────────────────────────────
    {
        "name": "find_flights",
        "subsystem": "travel",
        "patterns": [
            r"^(find|search|book|look\s+for|show)\s+(flights?|trips?|airfare|plane\s+tickets)",
            r"(flights?|fly|flying)\s+(to|from|between)",
            r"^(how\s+much|what'?s\s+the\s+price)\s+(to\s+)?(fly|flight)\s+(to|from)",
        ],
        "handler": "flight_finder",
        "params": {},
        "requires_ai": True,
    },
    # ── Package Manager (install/uninstall/update) ─────────────────────
    {
        "name": "package_install",
        "subsystem": "packages",
        "patterns": [
            r"^(install|download|get)\s+(a\s+)?(package|app|program|software|tool|application)",
            r"^(install|download)\s+",
        ],
        "handler": "package_manager",
        "params": {},
        "requires_ai": True,
    },
    {
        "name": "package_uninstall",
        "subsystem": "packages",
        "patterns": [
            r"^(uninstall|remove|delete|get\s+rid\s+of)\s+(a\s+)?(package|app|program|software|tool)",
            r"^(uninstall|remove)\s+",
        ],
        "handler": "package_manager",
        "params": {},
        "requires_ai": True,
    },
    {
        "name": "package_update",
        "subsystem": "packages",
        "patterns": [
            r"^(update|upgrade)\s+(all\s+)?(packages?|apps?|software|system)",
            r"^(check|list)\s+(for\s+)?(updates?|upgrades?)",
            r"(update|upgrade)\s+(everything|all|system)",
        ],
        "handler": "package_manager",
        "params": {"action": "update_all"},
        "requires_ai": False,
    },
    # ── Game Updater ──────────────────────────────────────────────────
    {
        "name": "game_update",
        "subsystem": "games",
        "patterns": [
            r"^(update|check|list)\s+(my\s+)?(games?|steam|epic)",
            r"^(install|download)\s+(a\s+)?(game|steam|epic)",
        ],
        "handler": "game_updater",
        "params": {},
        "requires_ai": True,
    },
    # ── Jobs / Job Search ────────────────────────────────────────────
    {
        "name": "job_search",
        "subsystem": "career",
        "patterns": [
            r"^(find|search|look\s+for)\s+(a\s+)?(job|work|position|role|career|employment)",
            r"^(jobs?|careers?|vacancies?)\s+(in|near|at|for)",
            r"^(what|show)\s+(jobs?|positions?|roles?|vacancies?)",
            r"^(hiring|recruiting)\s+(for\s+)?",
        ],
        "handler": "job_search",
        "params": {},
        "requires_ai": True,
    },
    # ── Security Vault ────────────────────────────────────────────────
    {
        "name": "vault_save",
        "subsystem": "security",
        "patterns": [
            r"^(save|store|remember|keep)\s+(my\s+)?(password|secret|key|credential|token)",
            r"^(add|create|save)\s+(a\s+)?(secret|password|credential)",
        ],
        "handler": "vault",
        "params": {},
        "requires_ai": True,
    },
    {
        "name": "vault_get",
        "subsystem": "security",
        "patterns": [
            r"^(get|show|retrieve|what'?s?\s+my)\s+(password|secret|key|credential|token)",
            r"^(what\s+is|what'?s?)\s+(my\s+)?(password|secret)\s+(for|of)",
        ],
        "handler": "vault",
        "params": {},
        "requires_ai": True,
    },
    # ── Computer Control (keyboard/mouse) ─────────────────────────────
    {
        "name": "computer_type",
        "subsystem": "system",
        "patterns": [
            r"^(type|write|enter)\s+\w+\s+(on\s+)?(the\s+)?(screen|page|field|box)",
            r"^type\s+",
        ],
        "handler": "computer_control",
        "params": {},
        "requires_ai": True,
    },
    {
        "name": "computer_click",
        "subsystem": "system",
        "patterns": [
            r"^(click|tap|press|double.?click)\s+(on\s+)?",
            r"^(scroll|move)\s+(mouse|cursor|pointer)",
        ],
        "handler": "computer_control",
        "params": {},
        "requires_ai": True,
    },
    # ── Run Shell Command ────────────────────────────────────────────
    {
        "name": "run_command",
        "subsystem": "system",
        "patterns": [
            r"^(run|execute)\s+(a\s+)?(shell|terminal|command|script|cmd)",
            r"^(open|launch)\s+terminal\s+(and\s+)?(run|execute|type)",
        ],
        "handler": "run_command",
        "params": {},
        "requires_ai": True,
    },
    # ── Run Python Code ─────────────────────────────────────────────
    {
        "name": "run_python",
        "subsystem": "system",
        "patterns": [
            r"^(run|execute)\s+(python|script)\s+(code|script|file)",
            r"^python\s+",
        ],
        "handler": "run_python",
        "params": {},
        "requires_ai": True,
    },
    # ── Free Claude Code (fcc-server + fcc-claude in a folder) ───────
    {
        "name": "run_fcc",
        "subsystem": "system",
        "patterns": [
            r"^(run|start|launch|open)\s+(free\s+claude\s+code|fcc)",
            r"^(free\s+claude\s+code|fcc)\s+(in|for|at)\s+",
            r"^(run|start)\s+(free\s+)?claude\s+(code\s+)?(in|for|at)\s+",
            r"^(run|start|launch)\s+fcc",
        ],
        "handler": "run_fcc",
        "params": {},
        "requires_ai": False,
    },
    # ── Daily Dashboard (open all daily software at once) ────────────
    {
        "name": "open_dashboard",
        "subsystem": "system",
        "patterns": [
            r"^(open|launch|start|show)\s+(my\s+)?dashboard",
            r"^(open|launch|start|run)\s+(?=(?:all|every|my|daily)\s+)(?:all|every|my|daily)?\s*(?:my\s+)?(?:daily\s+)?(?:apps?|software|programs?|applications?)\s*(?:now|please|at\s+once)?$",
            r"dashboard\s+(time|mode|on|now)",
        ],
        "handler": "open_dashboard",
        "params": {},
        "requires_ai": False,
    },
    {
        "name": "add_dashboard",
        "subsystem": "system",
        "patterns": [
            r"^(add|put|include)\s+.+\s+to\s+(my\s+)?dashboard",
            r"^(add|set)\s+(my\s+)?(daily\s+)?(apps?|software|programs?)\s+",
            r"^my\s+(daily\s+)?(software|apps?|programs?)\s+(is|are)\s+",
        ],
        "handler": "add_dashboard",
        "params": {},
        "requires_ai": False,  # app list is parsed directly
    },
    {
        "name": "remove_dashboard",
        "subsystem": "system",
        "patterns": [
            r"^(remove|delete|take\s+off|drop)\s+.+\s+(from\s+)?(my\s+)?dashboard",
            r"^(remove|delete)\s+(from\s+)?(my\s+)?(daily\s+)?(apps?|software|programs?)\s+",
        ],
        "handler": "remove_dashboard",
        "params": {},
        "requires_ai": False,  # app list is parsed directly
    },
    {
        "name": "list_dashboard",
        "subsystem": "system",
        "patterns": [
            r"^(what'?s?|what\s+is|what\s+are|show|list)\s+(on\s+|in\s+)?(my\s+)?dashboard\??$",
            r"^what\s+(apps?|software)\s+(are|is)\s+(on\s+)?(my\s+)?dashboard",
        ],
        "handler": "list_dashboard",
        "params": {},
        "requires_ai": False,
    },
    # ── Network Scan ─────────────────────────────────────────────────
    {
        "name": "network_scan",
        "subsystem": "network",
        "patterns": [
            r"^(scan|discover|list|find)\s+(my\s+)?(network|devices?|hosts?|machines?)",
            r"^(who'?s?\s+on|what'?s?\s+on)\s+(my\s+)?(network|wifi|lan)",
            r"^(check|show)\s+(network|wifi)\s+(devices?|clients?|connections?)",
        ],
        "handler": "network_scan",
        "params": {},
        "requires_ai": False,
    },
    # ── Task Manager (add/list/delete) ───────────────────────────────
    {
        "name": "task_add",
        "subsystem": "tasks",
        "patterns": [
            r"^(add|create|new|make)\s+(a\s+)?(task|todo|thing|item|reminder)",
            r"\b(at|by|before|on|in)\b\s+.*\b(do|add|create|make|schedule|remind)\s+",
        ],
        "handler": "tasks",
        "params": {"action": "add"},
        "requires_ai": False,
    },
    {
        "name": "task_delete",
        "subsystem": "tasks",
        "patterns": [
            r"^(delete|remove|complete|finish|done)\s+(a\s+)?(task|todo|item)",
            r"^(mark|set)\s+(task|todo|item)\s+(as\s+)?(done|complete|completed|finished)",
        ],
        "handler": "tasks",
        "params": {},
        "requires_ai": True,
    },
    # ── Todo Display (graphical table) ───────────────────────────────
    {
        "name": "todo_display",
        "subsystem": "tasks",
        "patterns": [
            r"^(show|open|display|view|get)\s+(my\s+)?(todo|tasks?|list|to-do)",
            r"^(todo|to-do|tasks?)\s+(list|panel|view|table)",
            r"^(what'?s?\s+on|what\s+do\s+I\s+have)\s+(my\s+)?(todo|list)",
            r"^list\s+(all\s+)?(my\s+)?(tasks?|todos?)",
            r"^(what|show)\s+(?:are\s+)?(?:my\s+)?(?:tasks?|todos?|to-do)",
        ],
        "handler": "todo_display",
        "params": {},
        "requires_ai": False,
    },
]


class IntentRouterResult:
    def __init__(
        self,
        matched: bool = False,
        intent_name: str = "",
        subsystem: str = "",
        handler_name: str = "",
        handler_params: dict[str, Any] | None = None,
        requires_ai: bool = True,
        confidence: float = 0.0,
    ):
        self.matched = matched
        self.intent_name = intent_name
        self.subsystem = subsystem
        self.handler_name = handler_name
        self.handler_params = handler_params or {}
        self.requires_ai = requires_ai
        self.confidence = confidence

    def __repr__(self) -> str:
        return (
            f"IntentRouterResult(matched={self.matched}, "
            f"intent='{self.intent_name}', subsystem='{self.subsystem}', "
            f"handler='{self.handler_name}', ai={self.requires_ai}, "
            f"conf={self.confidence:.2f})"
        )


class IntentRouter:
    """Fast intent router — classifies user text into subsystems without LLM."""

    def __init__(self):
        self._intents = _INTENTS

    def route(self, text: str) -> IntentRouterResult:
        """Route user text to the best matching intent.

        Returns IntentRouterResult — check .matched before using.
        If no match, .requires_ai is True (fall back to LLM).
        """
        # Priority: Mega Router for powerful tools
        mega_res = mega_route(text)
        if mega_res:
            intent_name = mega_res["intent"]
            # Find the intent dict for metadata
            intent_dict = next((i for i in self._intents if i["name"] == intent_name), None)
            if intent_dict:
                return IntentRouterResult(
                    matched=True,
                    intent_name=intent_name,
                    subsystem=intent_dict.get("subsystem", "tools"),
                    handler_name=intent_dict.get("handler", intent_name),
                    handler_params=mega_res["params"],
                    requires_ai=intent_dict.get("requires_ai", False),
                    confidence=mega_res["confidence"]
                )

        t_lower = text.lower().strip()
        # Strip wake-word prefix so "jarvis open map" → "open map"
        t_lower = re.sub(r"^(hey\s+)?jarvis[\s,:-]+", "", t_lower).strip()
        start = time.time()

        # First pass: check capability registry patterns
        try:
            cap_matches = find_matches(t_lower)
            if cap_matches:
                cap = cap_matches[0]
                name = cap["name"]
                subsystem = cap.get("category", "general")
                logger.debug(
                    "IntentRouter: capability match '%s' in %.1fms",
                    name, (time.time() - start) * 1000,
                )
                return IntentRouterResult(
                    matched=True,
                    intent_name=name,
                    subsystem=subsystem,
                    handler_name=name,
                    handler_params={},
                    requires_ai=cap.get("requires_ai", False),
                    confidence=0.8,
                )
        except Exception as e:
            logger.debug("IntentRouter capability check error: %s", e)

        # Second pass: hardcoded intent patterns
        best_match = None
        best_score = 0
        best_params = {}

        for intent in self._intents:
            for pattern in intent["patterns"]:
                try:
                    m = re.search(pattern, t_lower, re.IGNORECASE)
                    if m:
                        score = len(m.group()) / max(len(t_lower), 1)
                        if score > best_score:
                            best_score = score
                            best_match = intent
                            best_params = self._extract_params(text, intent, m)
                        # open_app — bump only for simple app launches;
                        # compound requests (and/or/then/register/etc.) go to the LLM.
                        if intent["name"] == "open_app" and score < 0.5:
                            app = text[m.end():].strip().rstrip("!?., ")
                            if app:
                                _compound = any(
                                    kw in app.lower()
                                    for kw in [
                                        " and ", " or ", " then ", " also ",
                                        " to ", " in it", " in the", " for me",
                                        " register", " signup", " sign up",
                                        " create ", " login", " log in",
                                         " make ", " open ",
                                ])
                                if not _compound:
                                    best_score = max(best_score, 0.5)
                                    if best_score == 0.5:
                                        best_match = intent
                except re.error:
                    continue

        elapsed = (time.time() - start) * 1000

        if best_match and best_score > 0.2:
            requires_ai = best_match.get("requires_ai", True)
            # Compound open_app requests (e.g. "open chrome and register...")
            # must go to the LLM even if score is above threshold.
            if not requires_ai and best_match["name"] == "open_app":
                _app_name = best_params.get("app_name", "")
                _compound = any(
                    kw in _app_name.lower()
                    for kw in [
                        " and ", " or ", " then ", " also ",
                        " to ", " in it", " in the", " for me",
                        " register", " signup", " sign up",
                        " create ", " login", " log in",
                        " make ", " open ",
                    ]
                )
                if _compound:
                    requires_ai = True

            logger.debug(
                "IntentRouter: '%s' -> %s (%.1fms, conf=%.2f)",
                text, best_match["name"], elapsed, best_score,
            )
            return IntentRouterResult(
                matched=True,
                intent_name=best_match["name"],
                subsystem=best_match["subsystem"],
                handler_name=best_match["handler"],
                handler_params={**best_match.get("params", {}), **best_params},
                requires_ai=requires_ai,
                confidence=best_score,
            )

        logger.debug("IntentRouter: no match for '%s' (%.1fms)", text, elapsed)
        return IntentRouterResult(
            matched=False,
            requires_ai=True,
            confidence=0.0,
        )

    def _extract_params(
        self, text: str, intent: dict, match: re.Match
    ) -> dict[str, Any]:
        """Extract parameters from the matched text."""
        params: dict[str, Any] = {}

        if intent["name"] == "open_app":
            app = text[match.end():].strip().rstrip("!?., ")
            if app:
                params["app_name"] = app

        elif intent["name"] == "send_message":
            t = text.lower()
            # platform: explicit mention after on/via, or at start
            plat = None
            mplat = re.search(r"\b(on|via)\s+(whatsapp|telegram|messenger|signal|discord|sms|imessage)\b", t)
            if mplat:
                plat = mplat.group(2)
            else:
                mplat2 = re.search(r"\b(whatsapp|telegram|signal|sms)\b", t)
                if mplat2:
                    plat = mplat2.group(1)
            if plat:
                params["platform"] = plat
            # receiver: word(s) right after "to <name>" — naive extraction;
            # the LLM will refine when requires_ai=True.
            mto = re.search(r"\bto\s+([a-z][a-z\s]{0,18}?)\s+(on|via|that|saying|with|about|right|now|,|\.)", t)
            if mto:
                params["receiver"] = mto.group(1).strip()
            params["message_text"] = text

        elif intent["name"] == "auto_register":
            site = ""
            if match.re.groups > 0:
                g = match.group(match.re.groups)
                if g and g not in ("on", "for", "at", "a", "an", "the", "out", "form"):
                    site = g.strip().rstrip("!?., ")
            if not site:
                site = text[match.end():].strip().rstrip("!?., ")
            if site and site.lower() in ("on", "for", "at", "a", "an", "the", "out", "form"):
                site = ""
            params["url"] = site
            params["action"] = "auto_fill"

        elif intent["name"] == "web_search":
            query = text[match.end():].strip().rstrip("!?., ")
            if query:
                params["query"] = query
            else:
                params["query"] = text

        elif intent["name"] == "generate_image":
            prompt = text[match.end():].strip().rstrip("!?., ")
            prompt = re.sub(r"^(of|with|showing|featuring|containing)\s+", "", prompt).strip()
            if prompt:
                params["prompt"] = prompt
            else:
                params["prompt"] = text

        elif intent["name"] == "hermes_task":
            goal = text[match.end():].strip().rstrip("!?., ")
            if goal:
                params["goal"] = goal
            else:
                params["goal"] = text

        elif intent["name"] == "youtube_video":
            query = ""
            # Try capture groups first ("search youtube for X" has X in group(1))
            if match.re.groups > 0:
                g = match.group(match.re.groups)
                if g and g not in ("in", "on", "the", "youtube", "yt"):
                    query = g.strip()
            if not query:
                query = text[match.end():].strip().rstrip("!?., ")
            # "open/play/search X in/on youtube/yt" → extract X from before the preposition
            if not query:
                in_match = re.search(r"\s+(?:in|on)\s+(?:youtube|yt)\s*$", text, re.IGNORECASE)
                if in_match:
                    query = text[:in_match.start()].strip()
            # "open/play/search X in/on youtube/yt" — also try extracting from the text before match end
            if not query and match.group().strip():
                before = text[:match.start()] + text[match.end():]
                in_match2 = re.search(r"\s+(?:in|on)\s+(?:youtube|yt)\s*$", before, re.IGNORECASE)
                if in_match2:
                    query = before[:in_match2.start()].strip()
            if query:
                for prefix in ["play ", "search ", "open ", "a ", "an ", "the "]:
                    if query.lower().startswith(prefix):
                        query = query[len(prefix):].strip()
            if not query:
                query = text
            params["action"] = "play"
            params["query"] = query

        elif intent["name"] == "save_memory":
            value = match.group(match.re.groups).strip().rstrip("!?., ")
            if value:
                # Trim at conjunctions to prevent compound sentences
                value = re.split(r'\s+(and|but|also|then|however)\s+', value, maxsplit=1)[0].strip()
                params["value"] = value

        elif intent["name"] == "weather_report":
            city_match = re.search(r"in\s+(\w[\w\s]*?\w)(?:\s+(today|tomorrow|now|\?|\.))?\s*$", text)
            if city_match:
                params["city"] = city_match.group(1).strip()
            elif re.search(r"(weather|forecast)", text):
                params["city"] = text.split()[-1].strip("?.,!")

        elif intent["name"] == "obsidian_save":
            content = text[match.end():].strip().rstrip("!?., ")
            if content:
                params["content"] = content
                title_match = re.search(r"(?:called|titled|named)\s+['\"]?(.+?)['\"]?$", content)
                if title_match:
                    params["title"] = title_match.group(1)
                    params["content"] = content.replace(
                        f" called {title_match.group(1)}", ""
                    ).replace(f" titled {title_match.group(1)}", "").strip()
                else:
                    params["title"] = content[:50]

        elif intent["name"] == "calendar_agenda":
            if re.search(r"(upcoming|this\s+week|next\s+\w+)", text):
                days_match = re.search(r"(\d+)\s+days?", text)
                params["days"] = int(days_match.group(1)) if days_match else 7

        elif intent["name"] == "get_datetime":
            text_lower = text.lower()
            if re.search(r"\bdate\b", text_lower):
                params["format"] = "date"
            elif re.search(r"day\s+of\s+the\s+week", text_lower):
                params["format"] = "day"
            elif re.search(r"\bday\b", text_lower) and not re.search(r"(time|hour|minute|clock)", text_lower):
                params["format"] = "day"
            elif re.search(r"(time|hour|minute|clock)", text_lower) and not re.search(r"\b(date|day)\b", text_lower):
                params["format"] = "time"

        elif intent["name"] == "budget":
            if re.search(r"(this\s+month|monthly|this month)", text):
                params["period"] = "month"
            elif re.search(r"(today|this day)", text):
                params["period"] = "today"

        elif intent["name"] == "github_list_issues":
            if re.search(r"(PRs?|pull\s+requests)", text):
                params["action"] = "list_prs"

        elif intent["name"] == "github_clone":
            m = re.search(r"\b(?:clone|download|pull)\s+(?:a\s+)?(?:github\s+)?(?:repo|repository|project)?\s*(.+)$", text)
            if m:
                repo = m.group(1).strip().strip("!?., '\"")
                repo = repo.split()[-1] if repo and " " in repo else repo
                if repo and repo.lower() not in (
                    "github", "repo", "repository", "project", "a", "an", "the",
                    "it", "that", "this", "me", "now", "please",
                ):
                    params["repo"] = repo

        elif intent["name"] == "computer_settings":
            if "volume" in text or "sound" in text:
                params["action"] = "volume"
                if re.search(r"(\d+)", text):
                    level = re.search(r"(\d+)", text)
                    target = int(level.group(1))
                    if 0 <= target <= 100:
                        params["description"] = "volume_set"
                        params["value"] = str(target)
                    elif target > 100:
                        pass
                if "description" not in params:
                    if ("microphone" in text or "mic" in text) and "mute" in text:
                        params["action"] = "jarvis_mic"
                        params["description"] = "toggle_mute"
                    elif "up" in text or "increase" in text:
                        params["description"] = "volume_up"
                    elif "down" in text or "decrease" in text or "reduce" in text:
                        params["description"] = "volume_down"
                    elif "mute" in text and "unmute" not in text:
                        params["description"] = "volume_mute"
                    elif "unmute" in text:
                        params["description"] = "volume_mute"
            elif "brightness" in text:
                params["action"] = "brightness"
                if "up" in text or "increase" in text:
                    params["description"] = "brightness_up"
                elif "down" in text or "decrease" in text or "reduce" in text:
                    params["description"] = "brightness_down"
            elif "lock" in text:
                params["action"] = "lock_screen"
            elif "shutdown" in text:
                params["action"] = "shutdown"
            elif "restart" in text or "reboot" in text:
                params["action"] = "restart"
            elif "screenshot" in text:
                params["action"] = "screenshot"
            elif re.search(r"speed\s*test|internet\s+speed|network\s+speed|connection\s+speed", text):
                params["action"] = "speedtest"

        elif intent["name"] == "realtime_tutor":
            if re.search(r"^(start|open|launch)", text):
                params["action"] = "start"
            elif re.search(r"^(stop|close|exit)", text):
                params["action"] = "stop"
            else:
                params["action"] = "start"

        elif intent["name"] == "calculate":
            m = re.search(r"(-?\d+\.?\d*\s*[+\-*/]\s*-?\d+\.?\d*)", text)
            if m:
                params["expression"] = m.group(1).strip()
            if not params.get("expression"):
                m = re.search(r"(\d+)\s*([+\-*/])\s*(\d+)", text)
                if m:
                    params["expression"] = f"{m.group(1)}{m.group(2)}{m.group(3)}"
            if not params.get("expression"):
                m = re.search(r"(\d+\s*[\+\-\*/])+\s*\d+", text)
                if m:
                    params["expression"] = m.group(0).strip()

        elif intent["name"] == "stock_price":
            crypto_map = {
                "bitcoin": "BTC-USD", "btc": "BTC-USD",
                "ethereum": "ETH-USD", "eth": "ETH-USD",
                "solana": "SOL-USD", "sol": "SOL-USD",
                "ripple": "XRP-USD", "xrp": "XRP-USD",
                "cardano": "ADA-USD", "ada": "ADA-USD",
                "dogecoin": "DOGE-USD", "doge": "DOGE-USD",
                "polkadot": "DOT-USD", "dot": "DOT-USD",
                "litecoin": "LTC-USD", "ltc": "LTC-USD",
                "chainlink": "LINK-USD", "link": "LINK-USD",
                "avalanche": "AVAX-USD", "avax": "AVAX-USD",
            }
            for name, symbol in crypto_map.items():
                if name in text.lower():
                    params["symbols"] = symbol
                    break
            if not params.get("symbols"):
                m = re.search(r"(?:stock|price|ticker)\s+(?:of\s+)?(\w+)", text, re.IGNORECASE)
                if m:
                    params["symbols"] = m.group(1).upper()
            if not params.get("symbols"):
                m = re.search(r"(\w{1,5})\s+(?:stock|price|share|ticker)", text, re.IGNORECASE)
                if m:
                    params["symbols"] = m.group(1).upper()

        elif intent["name"] == "set_timer":
            m = re.search(r"(\d+)\s*(min|minute|minutes|sec|second|seconds|hour|hours)", text)
            if m:
                val = int(m.group(1))
                unit = m.group(2).lower()
                if unit.startswith("sec"):
                    params["minutes"] = max(1, val / 60)
                elif unit.startswith("hour"):
                    params["minutes"] = val * 60
                else:
                    params["minutes"] = val
            if re.search(r"remind\s+me\s+in", text):
                params["mode"] = "timer"
                msg_match = re.search(r"(?:to|about|that|of)\s+(.+)$", text)
                if msg_match:
                    params["message"] = msg_match.group(1).strip()
            if not params.get("minutes"):
                params["minutes"] = 10

        elif intent["name"] == "convert_file":
            params["mode"] = "auto"
            m = re.search(r"(convert|change|transform|turn)\s+(this\s+)?(.+?)\s+(?:to|into)\s+(.+)", text)
            if m:
                params["source_description"] = m.group(3).strip()
                params["target_format"] = m.group(4).strip()
            else:
                m = re.search(r"(convert|change)\s+file\s+(.+?)\s+(?:to|into)\s+(.+)", text)
                if m:
                    params["source_path"] = m.group(2).strip()
                    params["target_format"] = m.group(3).strip()

        elif intent["name"] == "random_number":
            lo, hi = 1, 100
            m = re.search(r"(?:between|from)\s+(\d+)\s+(?:and|to)\s+(\d+)", text)
            if m:
                lo, hi = int(m.group(1)), int(m.group(2))
            else:
                m = re.search(r"(?:1[\s-]?to[\s-]?)?(\d+)", text)
                if m and "between" not in text:
                    hi = int(m.group(1))
            params.update({"min": lo, "max": hi})
            if re.search(r"(roll|dice)", text):
                params["mode"] = "dice"
            elif re.search(r"(coin|flip)", text):
                params["mode"] = "coin"

        elif intent["name"] == "system_info":
            if re.search(r"(os|operating\s+system)", text):
                params["query"] = "os"
            elif re.search(r"(cpu|processor|core)", text):
                params["query"] = "cpu"
            elif re.search(r"(ram|memory|gb)", text):
                params["query"] = "ram"
            elif re.search(r"(hostname|name)", text):
                params["query"] = "hostname"
            else:
                params["query"] = "all"

        elif intent["name"] == "convert_units":
            m = re.search(r"(\d+\.?\d*)\s*(km|mi|miles|kilometers?|kg|lb|lbs?|pounds?|mph|kmh|kph|celsius|fahrenheit|f|c|gal|l|liter|inch|inches|feet|foot|cm|mm|g|oz|ounce)", text)
            if m:
                params["value"] = float(m.group(1))
                params["from"] = m.group(2)
                rest = text[m.end():].lower()
                for target in ["km", "mi", "miles", "kg", "lb", "lbs", "f", "c", "celsius", "fahrenheit", "kmh", "mph", "kph", "gal", "l", "liter", "inch", "cm", "mm", "feet", "g", "oz", "pounds"]:
                    if target in rest:
                        params["to"] = target
                        break
                if not params.get("to"):
                    if re.search(r"how\s+(many|much)", text):
                        if params.get("from") in ("mi", "miles"):
                            params["to"] = "km"
                        elif params.get("from") in ("km", "kilometers"):
                            params["to"] = "mi"
                        elif params.get("from") in ("f", "fahrenheit"):
                            params["to"] = "c"
                        elif params.get("from") in ("c", "celsius"):
                            params["to"] = "f"
                        elif params.get("from") in ("lb", "lbs"):
                            params["to"] = "kg"
                        elif params.get("from") in ("kg"):
                            params["to"] = "lb"

        elif intent["name"] == "filesystem_query":
            m = re.search(r"top\s+(\d+)", text)
            params["count"] = int(m.group(1)) if m else 10
            if re.search(r"(disk|drive|storage|usage|space|free|available)", text):
                params["action"] = "disk_usage"
            elif re.search(r"(largest|biggest|size)", text):
                params["action"] = "largest"
            for p in ["home", "downloads?", "documents?", "desktop", "pictures?", "music", "videos?"]:
                if re.search(p, text):
                    params["path"] = p.rstrip("?")
                    break

        elif intent["name"] == "news":
            # Extract topic: "tunisia news" → topic=tunisia, "tech news" → topic=tech
            m = re.search(r"(\w+)\s+news\b", text)
            if m:
                topic = m.group(1).lower()
                if topic not in ("latest", "breaking", "top", "the", "get", "show", "read", "fetch", "news", "headlines", "today", "this", "what", "is", "my"):
                    params["topic"] = topic

        elif intent["name"] == "task_add":
            from actions.todo_display import parse_task_text
            parsed = parse_task_text(text)
            params["title"] = parsed["title"]
            if parsed["due"]:
                params["due"] = parsed["due"]
            if parsed["priority"] != "normal":
                params["priority"] = parsed["priority"]

        elif intent["name"] == "run_fcc":
            # "run free claude code in <folder>" → folder=<folder>
            m = re.search(r"\b(?:in|for|at)\s+(.+?)\s*$", text)
            if m:
                folder = m.group(1).strip().strip("!?., ")
                # Tolerate "the X folder" / "folder called X"
                folder = re.sub(r"^(the|my|this|a|an)\s+", "", folder)
                folder = re.sub(r"\s+(folder|directory|dir|project)\s*$", "", folder)
                if folder and folder.lower() not in (
                    "free claude code", "fcc", "claude code", "claude",
                ):
                    params["folder"] = folder

        elif intent["name"] == "add_dashboard":
            # Try to parse the app list directly so the common case routes
            # without the LLM.
            m = (
                re.search(r"\b(?:add|put|include)\s+(.+?)\s+to\s+(?:my\s+)?dashboard\b", text)      # "add X to my dashboard"
                or re.search(r"(?:my\s+)?(?:daily\s+)?(?:software|apps?|programs?)\s+(?:is|are)\s+(.+)$", text)  # "my daily software is X"
                or re.search(r"\b(?:add|set)\s+(?:my\s+)?(?:daily\s+)?(?:software|apps?|programs?)\s+(.+)$", text)  # "add my daily software X"
            )
            if m:
                raw = m.group(1).strip().strip("!?., ")
                parts = [
                    p.strip().strip("'\"")
                    for p in re.split(r",|\s+and\s+|\s*&\s*|\s+", raw)
                    if p.strip() and p.strip().lower() not in ("and", "or", "&")
                ]
                if parts:
                    params["apps"] = parts

        elif intent["name"] == "remove_dashboard":
            m = (
                re.search(r"\b(?:remove|delete|take\s+off|drop)\s+(.+?)\s+(?:from|off)\s+(?:my\s+)?dashboard\b", text)  # "remove X from my dashboard"
                or re.search(r"\b(?:remove|delete)\s+(?:from\s+)?(?:my\s+)?(?:daily\s+)?(?:software|apps?|programs?)\s+(.+)$", text)  # "remove from my daily apps X"
            )
            if m:
                raw = m.group(1).strip().strip("!?., ")
                parts = [
                    p.strip().strip("'\"")
                    for p in re.split(r",|\s+and\s+|\s*&\s*|\s+", raw)
                    if p.strip() and p.strip().lower() not in ("and", "or", "&")
                ]
                if parts:
                    params["apps"] = parts

        elif intent["name"] == "gmail_send":
            m = re.search(r"to\s+([\w.@+-]+)", text)
            if m:
                params["to"] = m.group(1)
                after = text[m.end():].strip()
                if after:
                    if re.search(r"\bsubject\b|\bsubj\b", after, re.IGNORECASE):
                        m_subj = re.search(r"(?:subject|subj)\s+([^,;]+?)(?:\s*(?:body|desc|description|bdoy|and)\s+|$)", after, re.IGNORECASE)
                        if m_subj:
                            params["subject"] = m_subj.group(1).strip()
                            m_body = re.search(r"(?:body|desc|description|bdoy)\s+(.+)", after, re.IGNORECASE)
                            if m_body:
                                params["body"] = m_body.group(1).strip()
                        else:
                            params["body"] = after
                    elif re.search(r"\band\b|\bdesc\b|\bdescription\b|\bbody\b|\bbdoy\b", after, re.IGNORECASE):
                        m_subj = re.search(r"^(.+?)\s+(?:and|desc|description|body|bdoy)\s+(.+)", after, re.IGNORECASE)
                        if m_subj:
                            params["subject"] = m_subj.group(1).strip()
                            params["body"] = m_subj.group(2).strip()
                        else:
                            params["body"] = after
                    else:
                        params["body"] = after
            if not params.get("subject"):
                params["subject"] = params.get("body", "")[:50] or "No subject"



































































        elif intent["name"] == "stock_market":
            if match and len(match.groups()) >= 3:
                params["symbol"] = match.group(3).strip().upper()
        elif intent["name"] == "translator":
            if match and len(match.groups()) >= 4:
                params["text"] = match.group(2).strip()
                params["target_lang"] = match.group(4).strip()
        elif intent["name"] == "media_downloader":
            if match and len(match.groups()) >= 5:
                params["url"] = match.group(5).strip()
                params["type"] = match.group(3).strip() if match.group(3) else "image"
        elif intent["name"] == "speedtest":
            pass
        elif intent["name"] == "process_mgr":
            low = text.lower()
            if "kill" in low or "stop" in low or "tuer" in low:
                params["action"] = "kill"
                if match: params["name"] = match.group(len(match.groups())).strip()
            else:
                params["action"] = "list"
                params["sort"] = "mem" if "mem" in low else "cpu"
        elif intent["name"] == "archive_tools":
            if match and len(match.groups()) >= 4:
                params["source"] = match.group(2).strip()
                params["output"] = match.group(4).strip()
        elif intent["name"] == "image_edit":
            low = text.lower()
            if match:
                params["path"] = match.group(3).strip() if len(match.groups())>=3 else ""
                if "resize" in low:
                    params["action"] = "resize"
                    if len(match.groups())>=6:
                        params["width"] = match.group(5)
                        params["height"] = match.group(6)
                else:
                    for a in ["grayscale", "flip", "mirror"]:
                        if a in low: params["action"] = a
        elif intent["name"] == "wiki_tools":
            if match: params["query"] = match.group(len(match.groups())).strip()
        elif intent["name"] == "system_health":
            pass
        elif intent["name"] == "news_pro":
            if match: params["topic"] = match.group(len(match.groups())).strip()
        elif intent["name"] == "devices_scan":
            pass
        elif intent["name"] == "qr_tools":
            if match: params["text"] = match.group(len(match.groups())).strip()
        elif intent["name"] == "clipboard_mgr":
            pass
        elif intent["name"] == "math_solver":
            if match: params["expression"] = match.group(len(match.groups())).strip()
        elif intent["name"] == "hash_tools":
            if match: params["text"] = match.group(len(match.groups())).strip()
        elif intent["name"] == "random_tools":
            pass
        elif intent["name"] == "notes_tools":
            if match: params["text"] = match.group(len(match.groups())).strip()
        elif intent["name"] == "system_info_tools":
            pass
        elif intent["name"] == "screen_ocr":
            if match: params["text"] = match.group(len(match.groups())).strip()
        elif intent["name"] == "check_crypto":
            if match: params["crypto"] = match.group(len(match.groups())).strip()
        elif intent["name"] == "check_time":
            if match: params["city"] = match.group(len(match.groups())).strip()
        elif intent["name"] == "create_document":
            if match and len(match.groups()) >= 5:
                params["format"] = match.group(3).strip()
                params["title"] = match.group(5).strip()
        elif intent["name"] == "read_pdf":
            if match: params["path"] = match.group(len(match.groups())).strip()
        elif intent["name"] == "install_tool":
            if match: params["tool"] = match.group(len(match.groups())).strip()
        elif intent["name"] == "use_tool":
            if match and len(match.groups()) >= 2:
                params["tool"] = match.group(2).strip()
                params["args"] = match.group(3).strip()
        return params


# ── Singleton ────────────────────────────────────────────────────────────

_router: IntentRouter | None = None


def get_router() -> IntentRouter:
    global _router
    if _router is None:
        _router = IntentRouter()
    return _router


def route(text: str) -> IntentRouterResult:
    return get_router().route(text)
