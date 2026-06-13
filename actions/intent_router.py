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
    # ── Gmail / Email ─────────────────────────────────────────────────
    {
        "name": "gmail_get_unread",
        "subsystem": "gmail",
        "patterns": [
            r"^(get|check|show|read|list)\s+(my\s+)?(unread\s+)?(emails?|messages?|inbox|gmail)",
            r"^(any|do I have)\s+(new\s+)?(emails?|messages?|mail)",
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
        "requires_ai": True,
    },
    {
        "name": "gmail_send",
        "subsystem": "gmail",
        "patterns": [
            r"^(send|compose|write)\s+(an?\s+)?(email|mail|message)\s+(to|for)",
            r"email\s+.*\s+that",
        ],
        "handler": "gmail_send",
        "params": {},
        "requires_ai": True,
    },

    # ── Calendar ─────────────────────────────────────────────────────
    {
        "name": "calendar_agenda",
        "subsystem": "calendar",
        "patterns": [
            r"^(what('?s| is| do I have)\s+on\s+(my\s+)?)?(calendar|schedule|agenda|plan)",
            r"^(show|list|get|check)\s+(my\s+)?(calendar|schedule|agenda|plan)",
            r"what('?s| is)\s+(today|upcoming)",
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
        "name": "web_search",
        "subsystem": "browser",
        "patterns": [
            r"^(search|google|look\s+up|find\s+(out|on\s+the\s+web)|what\s+is|who\s+is)",
            r"^(weather|news|stock|price|bitcoin)",
            r"\?$",
        ],
        "handler": "web_search",
        "params": {},
        "requires_ai": True,
    },

    # ── GitHub ───────────────────────────────────────────────────────
    {
        "name": "github_list_repos",
        "subsystem": "github",
        "patterns": [
            r"^(list|show|my)\s+(repos|repositories|projects)",
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

    # ── Obsidian ─────────────────────────────────────────────────────
    {
        "name": "obsidian_search",
        "subsystem": "obsidian",
        "patterns": [
            r"^(search|find|look\s+up)\s+(in\s+)?(obsidian|notes?|vault)",
            r"(remember|recall)\s+.*(note|idea)",
        ],
        "handler": "obsidian",
        "params": {"action": "search"},
        "requires_ai": True,
    },
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
            r"(turn\s+(up|down|on|off))\s+(volume|sound|brightness)",
            r"(increase|decrease)\s+(volume|brightness)",
            r"^(mute|unmute|lock|shutdown|restart|sleep)",
            r"(screenshot|screen\s+shot)",
        ],
        "handler": "computer_settings",
        "params": {},
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
            r"^(weather|temperature|forecast|how\s+cold|how\s+hot)",
            r"rain\s+(today|tomorrow)",
        ],
        "handler": "weather_report",
        "params": {},
        "requires_ai": False,
    },
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
        "name": "stock_price",
        "subsystem": "system",
        "patterns": [
            r"^(stock\s+price|share\s+price|stock|price)\s+(of\s+)?(.+)",
            r"(what'?s|what\s+is)\s+(.+)\s+(stock|price|share|ticker|trading\s+at)",
            r"how\s+(much|are)\s+(.+)",
        ],
        "handler": "stock_price",
        "params": {},
        "requires_ai": False,
    },
    {
        "name": "news",
        "subsystem": "system",
        "patterns": [
            r"^(news|headlines|latest\s+news|what'?s\s+happening)",
            r"^(tech\s+news|world\s+news|science\s+news|business\s+news)",
            r"(get|fetch|show|read)\s+(me\s+)?(the\s+)?news",
        ],
        "handler": "news",
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
    {
        "name": "youtube_video",
        "subsystem": "media",
        "patterns": [
            r"^(play|search)\s+(a\s+)?(video|youtube)",
            r"play\s+.*\s+on\s+youtube",
            r"youtube\s+(search|find)\s+(.+)",
            r"search\s+youtube\s+for\s+(.+)",
            r"channel\s+(stats?|info|details?)\s+(of\s+)?(.+)",
            r"(subscriber|subscribers?|views?|videos?|stats?)\s+(for\s+)?(.+)",
        ],
        "handler": "youtube_video",
        "params": {},
        "requires_ai": False,
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
            r"what'?s?\s+(running|using\s+cpu|using\s+memory)",
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
        t = text.lower().strip()
        start = time.time()

        # First pass: check capability registry patterns
        try:
            cap_matches = find_matches(t)
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
                    m = re.search(pattern, t)
                    if m:
                        score = len(m.group()) / max(len(t), 1)
                        if intent["name"] == "open_app" and score < 0.3:
                            continue
                        if score > best_score:
                            best_score = score
                            best_match = intent
                            best_params = self._extract_params(t, intent, m)
                except re.error:
                    continue

        elapsed = (time.time() - start) * 1000

        if best_match and best_score > 0.2:
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
                requires_ai=best_match.get("requires_ai", True),
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

        elif intent["name"] == "web_search":
            query = text[match.end():].strip().rstrip("!?., ")
            if query:
                params["query"] = query
            else:
                params["query"] = text

        elif intent["name"] == "weather_report":
            city_match = re.search(r"in\s+(\w[\w\s]*\w)", text)
            if city_match:
                params["city"] = city_match.group(1)

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

        elif intent["name"] == "github_list_issues":
            if re.search(r"(PRs?|pull\s+requests)", text):
                params["action"] = "list_prs"

        elif intent["name"] == "computer_settings":
            if "volume" in text or "sound" in text:
                params["action"] = "volume"
                if "up" in text or "increase" in text:
                    params["description"] = "volume_up"
                elif "down" in text or "decrease" in text or "reduce" in text:
                    params["description"] = "volume_down"
                elif "mute" in text:
                    params["description"] = "volume_mute"
                elif re.search(r"(\d+)", text):
                    level = re.search(r"(\d+)", text)
                    params["description"] = "volume_set"
                    params["value"] = level.group(1) if level else "50"
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
