"""
MARK XL — PC Bridge Server
WebSocket bridge that lets the Android app talk to the local Jarvis AI.
Run alongside main.py on the same PC.

Usage:
  python pc_bridge.py

The server prints:
  • Local IP address(es)
  • QR code for the phone to scan
  • Port 8765 WebSocket endpoint
"""
import asyncio
import json
import os
import socket
import sys
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path

try:
    import websockets
except ImportError:
    print("[Bridge] Installing websockets…")
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "websockets", "qrcode"], check=True)
    import websockets

try:
    import qrcode
except ImportError:
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "qrcode"], check=True)
    import qrcode

# ── Project imports ──────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from memory.memory_manager import load_memory, format_memory_for_prompt, update_memory
from memory.vector_memory import store_memory, store_conversation, get_relevant_context, get_memory_count, search_memory
from core.llm_client import call_llm_stream, get_llm_settings, ensure_ollama_running, warmup_model

# Tool imports
from actions.open_app import open_app
from actions.weather_report import weather_action
from actions.send_message import send_message
from actions.reminder import reminder
from actions.computer_settings import computer_settings
from actions.screen_processor import screen_process
from actions.youtube_video import youtube_video
from actions.desktop import desktop_control
from actions.browser_control import browser_control
from actions.file_controller import file_controller
from actions.code_helper import code_helper
from actions.dev_agent import dev_agent
from actions.web_search import web_search as web_search_action
from actions.computer_control import computer_control
from actions.game_updater import game_updater
from actions.get_location import get_location
from actions.file_processor import file_processor
from core.scheduler import get_scheduler
from agent.agent_manager import get_agent_manager
from skills.skill_loader import get_active_skill_context, list_skills, reload_skills

# ── Tool declarations (same as main.py) ──────────────────────────────────────

TOOL_DECLARATIONS = [
    {
        "name": "open_app",
        "description": "Opens or launches any application, website, or program on the computer.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "app_name": {"type": "STRING", "description": "Name of the application or website to open."}
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
                "query": {"type": "STRING", "description": "Search query"},
                "mode": {"type": "STRING", "description": "search or compare"},
                "items": {"type": "ARRAY", "items": {"type": "STRING"}, "description": "Items to compare"},
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
        "description": "Sends a message via WhatsApp or Telegram.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "receiver": {"type": "STRING", "description": "Recipient contact name"},
                "message_text": {"type": "STRING", "description": "The exact message text to send"},
                "platform": {"type": "STRING", "description": "Platform: WhatsApp, Telegram, etc."}
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
                "date": {"type": "STRING", "description": "Date in YYYY-MM-DD format"},
                "time": {"type": "STRING", "description": "Time in HH:MM format"},
                "message": {"type": "STRING", "description": "Reminder message text"},
                "minutes": {"type": "INTEGER", "description": "Minutes from now for a timer"}
            },
            "required": []
        }
    },
    {
        "name": "youtube_video",
        "description": "Controls YouTube: play, summarize, trending.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "play | summarize | get_info | trending"},
                "query": {"type": "STRING", "description": "Search query"},
                "save": {"type": "BOOLEAN", "description": "Save summary to Notepad"},
                "region": {"type": "STRING", "description": "Country code for trending"},
                "url": {"type": "STRING", "description": "Video URL"}
            },
            "required": []
        }
    },
    {
        "name": "screen_process",
        "description": "Captures and analyzes the screen or webcam.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "angle": {"type": "STRING", "description": "screen or camera"},
                "text": {"type": "STRING", "description": "Question about the captured image"}
            },
            "required": ["text"]
        }
    },
    {
        "name": "computer_settings",
        "description": "Controls computer: volume, brightness, WiFi, notifications, etc.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "Action to perform"},
                "description": {"type": "STRING", "description": "Natural language description"},
                "value": {"type": "STRING", "description": "Optional value"},
                "title": {"type": "STRING", "description": "Notification title"},
                "message": {"type": "STRING", "description": "Notification message"},
                "text": {"type": "STRING", "description": "Text content"},
            },
            "required": []
        }
    },
    {
        "name": "browser_control",
        "description": "Controls web browsers: navigate, click, type, screenshot.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "go_to | search | click | type | scroll | screenshot | etc."},
                "browser": {"type": "STRING", "description": "chrome | edge | firefox | etc."},
                "url": {"type": "STRING", "description": "URL"},
                "query": {"type": "STRING", "description": "Search query"},
                "selector": {"type": "STRING", "description": "CSS selector"},
                "text": {"type": "STRING", "description": "Text to click or type"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "file_controller",
        "description": "Manages files and folders on the computer.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "list | create_file | delete | move | copy | rename | read | write | find | etc."},
                "path": {"type": "STRING", "description": "File/folder path"},
                "content": {"type": "STRING", "description": "File content"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "desktop_control",
        "description": "Controls desktop: wallpaper, organize, clean.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "wallpaper | organize | clean | list | stats"},
                "path": {"type": "STRING", "description": "Image path"},
                "url": {"type": "STRING", "description": "Image URL"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "code_helper",
        "description": "Writes, edits, explains, runs, or builds code.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "write | edit | explain | run | build"},
                "description": {"type": "STRING", "description": "What the code should do"},
                "language": {"type": "STRING", "description": "Programming language"},
                "output_path": {"type": "STRING", "description": "Save path"},
                "file_path": {"type": "STRING", "description": "Path to existing file"},
                "code": {"type": "STRING", "description": "Raw code"},
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
                "description": {"type": "STRING", "description": "Project description"},
                "language": {"type": "STRING", "description": "Programming language"},
                "project_name": {"type": "STRING", "description": "Project folder name"},
            },
            "required": ["description"]
        }
    },
    {
        "name": "agent_task",
        "description": "Executes complex multi-step tasks.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "goal": {"type": "STRING", "description": "What to accomplish"},
                "priority": {"type": "STRING", "description": "low | normal | high"}
            },
            "required": ["goal"]
        }
    },
    {
        "name": "computer_control",
        "description": "Direct mouse/keyboard control.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "type | click | hotkey | press | scroll | move | screenshot | etc."},
                "text": {"type": "STRING", "description": "Text to type"},
                "x": {"type": "INTEGER", "description": "X coordinate"},
                "y": {"type": "INTEGER", "description": "Y coordinate"},
                "keys": {"type": "STRING", "description": "Key combination"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "run_command",
        "description": "Executes arbitrary shell commands on the computer.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "command": {"type": "STRING", "description": "Shell command to execute"},
                "timeout": {"type": "INTEGER", "description": "Timeout in seconds"},
                "workdir": {"type": "STRING", "description": "Working directory"},
            },
            "required": ["command"]
        }
    },
    {
        "name": "run_python",
        "description": "Executes inline Python code.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "code": {"type": "STRING", "description": "Python code to execute"},
                "timeout": {"type": "INTEGER", "description": "Timeout in seconds"},
            },
            "required": ["code"]
        }
    },
    {
        "name": "game_updater",
        "description": "Updates/installs Steam or Epic Games.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "update | install | list"},
                "platform": {"type": "STRING", "description": "steam | epic"},
                "game_name": {"type": "STRING", "description": "Game name"},
            },
            "required": []
        }
    },
    {
        "name": "flight_finder",
        "description": "Searches Google Flights for best options.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "origin": {"type": "STRING", "description": "Departure city"},
                "destination": {"type": "STRING", "description": "Arrival city"},
                "date": {"type": "STRING", "description": "Departure date"},
                "return_date": {"type": "STRING", "description": "Return date"},
                "passengers": {"type": "INTEGER", "description": "Number of passengers"},
                "cabin": {"type": "STRING", "description": "economy | business | first"},
            },
            "required": ["origin", "destination", "date"]
        }
    },
    {
        "name": "get_location",
        "description": "Detects user's current physical location via IP geolocation.",
        "parameters": {"type": "OBJECT", "properties": {}}
    },
    {
        "name": "file_processor",
        "description": "Processes uploaded files: images, PDFs, Word, CSV, audio, video.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "file_path": {"type": "STRING", "description": "Path to the file"},
                "action": {"type": "STRING", "description": "What to do"},
                "instruction": {"type": "STRING", "description": "Free-form instruction"},
            },
            "required": []
        }
    },
    {
        "name": "calculate",
        "description": "Evaluates mathematical expressions.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "expression": {"type": "STRING", "description": "Math expression to evaluate"}
            },
            "required": ["expression"]
        }
    },
    {
        "name": "manage_agents",
        "description": "Manages background agents for autonomous tasks.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "create | list | status | stop | remove"},
                "name": {"type": "STRING", "description": "Agent name"},
                "goal": {"type": "STRING", "description": "Agent goal"},
                "agent_id": {"type": "STRING", "description": "Agent ID"},
                "interval": {"type": "INTEGER", "description": "Loop interval in seconds"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "manage_scheduler",
        "description": "Manages scheduled jobs.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "add | list | remove"},
                "name": {"type": "STRING", "description": "Job name"},
                "command": {"type": "STRING", "description": "Command to run"},
                "schedule": {"type": "STRING", "description": "Schedule string"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "search_memory",
        "description": "Searches Jarvis's semantic memory.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {"type": "STRING", "description": "What to search for"},
                "top_k": {"type": "INTEGER", "description": "Number of results"},
            },
            "required": ["query"]
        }
    },
    {
        "name": "save_memory",
        "description": "Saves a personal fact about the user to permanent memory.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "category": {"type": "STRING", "description": "identity | preferences | projects | relationships | wishes | notes"},
                "key": {"type": "STRING", "description": "Short snake_case key"},
                "value": {"type": "STRING", "description": "Concise value"},
            },
            "required": ["category", "key", "value"]
        }
    },
    {
        "name": "shutdown_jarvis",
        "description": "Shuts down the assistant completely.",
        "parameters": {"type": "OBJECT", "properties": {}}
    },
]

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
        new_params = {
            "type": "object",
            "properties": _convert_props(params.get("properties", {})),
        }
        req = params.get("required")
        if req:
            new_params["required"] = req
        tools.append({
            "type": "function",
            "function": {
                "name": d["name"],
                "description": d["description"],
                "parameters": new_params,
            },
        })
    return tools

OLLAMA_TOOLS = _to_ollama_tools(TOOL_DECLARATIONS)

# ── Local IP discovery ───────────────────────────────────────────────────────

def get_local_ips() -> list[str]:
    ips = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.1)
        s.connect(("10.254.254.254", 1))
        ips.append(s.getsockname()[0])
        s.close()
    except Exception:
        pass
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if ip not in ips and not ip.startswith("127."):
                ips.append(ip)
    except Exception:
        pass
    if not ips:
        ips = ["127.0.0.1"]
    return ips

def print_qr(text: str) -> None:
    qr = qrcode.QRCode(box_size=2, border=1)
    qr.add_data(text)
    qr.make()
    print(qr.print_ascii())

# ── Headless Jarvis Engine ───────────────────────────────────────────────────

_GREETINGS = {
    "hi", "hello", "hey", "hiya", "yo", "sup", "howdy", "greetings",
    "how are you", "how are you doing", "how's it going", "what's up",
    "whats up", "good morning", "good afternoon", "good evening",
    "good night", "morning", "evening",
    "bonjour", "salut", "bonsoir",
    "hola", "ciao", "buongiorno",
}

def _is_greeting(text: str) -> bool:
    t = text.lower().strip().rstrip("!?.,").strip()
    return t in _GREETINGS

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
    for code, ranges in _SCRIPT_RANGES.items():
        count = 0
        for lo, hi in ranges:
            for c in text:
                if lo <= ord(c) <= hi:
                    count += 1
        if count > len(text) * 0.15:
            return code
    return None

def _load_system_prompt() -> str:
    prompt_path = BASE_DIR / "core" / "prompt.txt"
    try:
        return prompt_path.read_text(encoding="utf-8")
    except Exception:
        return (
            "You are JARVIS, Tony Stark's AI assistant. "
            "Be concise, direct, and always use the provided tools to complete tasks. "
            "Never simulate or guess results — always call the appropriate tool."
        )

class HeadlessJarvis:
    """Headless version of the Jarvis processing pipeline for the bridge."""

    def __init__(self):
        self._conversation = []
        self._log_callback = None

    def set_log_callback(self, cb):
        self._log_callback = cb

    def log(self, msg: str):
        print(f"[Bridge] {msg}")
        if self._log_callback:
            self._log_callback(msg)

    def _build_system_prompt(self, user_text: str = "") -> str:
        sys_p = _load_system_prompt()
        memory = load_memory()
        mem_str = format_memory_for_prompt(memory)
        now = datetime.now()

        vec_context = ""
        if user_text:
            vec_context = get_relevant_context(user_text)
            vec_count = get_memory_count()
            if vec_context:
                vec_context = f"[SEMANTIC MEMORY — {vec_count} stored memories]\n{vec_context}"

        skill_context = ""
        if user_text:
            skill_context = get_active_skill_context(user_text)
            if skill_context:
                skill_context = f"[ACTIVE SKILL]\n{skill_context}"

        time_ctx = (
            f"[CURRENT DATE & TIME]\n"
            f"Right now it is: {now.strftime('%A, %B %d, %Y — %I:%M %p')}\n"
        )
        parts = [sys_p]
        if mem_str:
            parts.append(mem_str)
        if vec_context:
            parts.append(vec_context)
        if skill_context:
            parts.append(skill_context)
        parts.append(time_ctx)
        return "\n\n".join(parts)

    def _execute_tool(self, name: str, args: dict) -> str:
        self.log(f"Tool: {name} {args}")

        if name == "save_memory":
            category = args.get("category", "notes")
            key = args.get("key", "")
            value = args.get("value", "")
            if key and value:
                memory = load_memory()
                existing = memory.get(category, {}).get(key, {}).get("value", "")
                if existing and category in ("notes", "preferences") and any(
                    w in key.lower() for w in ["list", "todo", "grocery", "shopping", "tasks", "items"]
                ):
                    value = existing + "\n- " + value
                update_memory({category: {key: {"value": value}}})
                try:
                    threading.Thread(
                        target=store_memory,
                        args=(f"{key}: {value}", category, "fact"),
                        daemon=True,
                    ).start()
                except Exception:
                    pass
            return "__SILENT__"

        try:
            if name == "open_app":
                r = open_app(parameters=args, response=None, player=None)
                return r or f"Opened {args.get('app_name')}."
            elif name == "weather_report":
                r = weather_action(parameters=args, player=None)
                return r or "Weather delivered."
            elif name == "send_message":
                r = send_message(parameters=args, response=None, player=None, session_memory=None)
                return r or f"Message sent to {args.get('receiver')}."
            elif name == "reminder":
                r = reminder(parameters=args, response=None, player=None)
                return r or "Reminder set."
            elif name == "youtube_video":
                r = youtube_video(parameters=args, response=None, player=None)
                return r or "Done."
            elif name == "screen_process":
                r = screen_process(parameters=args, response=None, player=None, session_memory=None)
                return r if isinstance(r, str) and r else "Screen analyzed."
            elif name == "computer_settings":
                r = computer_settings(parameters=args, response=None, player=None)
                return r or "Done."
            elif name == "desktop_control":
                r = desktop_control(parameters=args, player=None)
                return r or "Done."
            elif name == "code_helper":
                r = code_helper(parameters=args, player=None, speak=None)
                return r or "Done."
            elif name == "dev_agent":
                r = dev_agent(parameters=args, player=None, speak=None)
                return r or "Done."
            elif name == "web_search":
                r = web_search_action(parameters=args, player=None)
                return r or "Done."
            elif name == "file_processor":
                r = file_processor(parameters=args, player=None, speak=None)
                return r or "Done."
            elif name == "computer_control":
                r = computer_control(parameters=args, player=None)
                return r or "Done."
            elif name == "run_command":
                r = computer_control(parameters={
                    "action": "run_command",
                    "command": args.get("command", ""),
                    "timeout": int(args.get("timeout", 60)),
                    "workdir": args.get("workdir"),
                }, player=None)
                return r or "Done."
            elif name == "run_python":
                r = computer_control(parameters={
                    "action": "run_python",
                    "code": args.get("code", ""),
                    "timeout": int(args.get("timeout", 30)),
                }, player=None)
                return r or "Done."
            elif name == "browser_control":
                r = browser_control(parameters=args, player=None)
                return r or "Done."
            elif name == "file_controller":
                r = file_controller(parameters=args, player=None)
                return r or "Done."
            elif name == "game_updater":
                r = game_updater(parameters=args, player=None, speak=None)
                return r or "Done."
            elif name == "flight_finder":
                r = flight_finder(parameters=args, player=None)
                return r or "Done."
            elif name == "get_location":
                r = get_location(parameters=args, player=None)
                return r or "Location retrieved."
            elif name == "agent_task":
                from agent.task_queue import get_queue, TaskPriority
                priority_map = {
                    "low": TaskPriority.LOW,
                    "normal": TaskPriority.NORMAL,
                    "high": TaskPriority.HIGH,
                }
                priority = priority_map.get(args.get("priority", "normal").lower(), TaskPriority.NORMAL)
                task_id = get_queue().submit(goal=args.get("goal", ""), priority=priority, speak=None)
                return f"Task started (ID: {task_id})."
            elif name == "calculate":
                return self._calculate(args)
            elif name == "manage_agents":
                return self._manage_agents(args)
            elif name == "manage_scheduler":
                return self._manage_scheduler(args)
            elif name == "search_memory":
                query = args.get("query", "")
                top_k = int(args.get("top_k", 5))
                if not query:
                    return "No query provided."
                results = search_memory(query, top_k=top_k)
                if not results:
                    return "No relevant memories found."
                lines = [f"Found {len(results)} relevant memories:"]
                for r in results:
                    lines.append(f"  [{r['category']}] {r['text'][:150]}")
                return "\n".join(lines)
            elif name == "shutdown_jarvis":
                self.log("Shutdown requested via phone.")
                threading.Thread(target=lambda: os._exit(0), daemon=True).start()
                return "Shutting down."
            else:
                return f"Unknown tool: {name}"
        except Exception as e:
            self.log(f"Tool '{name}' failed: {e}")
            traceback.print_exc()
            return f"Tool '{name}' failed: {e}"

    def _calculate(self, args: dict) -> str:
        import math as _math
        import re as _re
        expr = (args or {}).get("expression", "").strip()
        if not expr:
            return "No expression provided."
        # Temperature conversion
        m = _re.match(r'([\d.]+)\s*°?\s*(Celsius|C|Fahrenheit|F)\s*(?:to|in|→)\s*(Celsius|C|Fahrenheit|F)', expr, _re.IGNORECASE)
        if m:
            val = float(m.group(1))
            from_u = m.group(2).upper()
            to_u = m.group(3).upper()
            if from_u in ("C", "CELSIUS") and to_u in ("F", "FAHRENHEIT"):
                return f"{expr} = {val * 9/5 + 32}°F"
            elif from_u in ("F", "FAHRENHEIT") and to_u in ("C", "CELSIUS"):
                return f"{expr} = {(val - 32) * 5/9}°C"
        # Percentage
        m = _re.match(r'([\d.]+)\s*%?\s*(?:percent\s+of|of)\s+([\d.]+)', expr, _re.IGNORECASE)
        if m:
            pct = float(m.group(1)); val = float(m.group(2))
            return f"{pct}% of {val} = {val * pct / 100}"
        try:
            safe_globals = {"__builtins__": {}, "sqrt": _math.sqrt, "pi": _math.pi, "e": _math.e}
            s = expr.replace(" ", "").replace("^", "**")
            result = eval(s, safe_globals, {})
            return f"{expr} = {result}"
        except Exception as e:
            return f"Could not calculate: {e}"

    def _manage_agents(self, args: dict) -> str:
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
            return f"Agent '{agent.name}' created (ID: {agent.agent_id})."
        elif action == "stop":
            agent = agent_mgr.get_agent(args.get("agent_id", ""))
            if agent:
                agent.stop()
                return f"Agent '{agent.name}' stopped."
            return "Agent not found."
        elif action == "remove":
            ok = agent_mgr.remove_agent(args.get("agent_id", ""))
            return "Agent removed." if ok else "Agent not found."
        elif action in ("list", "status"):
            agents = agent_mgr.list_agents()
            if not agents:
                return "No background agents."
            lines = [f"Background Agents ({len(agents)}):"]
            for a in agents:
                lines.append(f"  [{a['status']}] {a['name']} ({a['agent_id']}) — {a['goal']}")
            return "\n".join(lines)
        return f"Unknown action: {action}"

    def _manage_scheduler(self, args: dict) -> str:
        action = args.get("action", "").lower()
        sched = get_scheduler()
        if action == "add":
            job_id = sched.add_job(
                name=args.get("name", "Job"),
                command=args.get("command", ""),
                schedule=args.get("schedule", "hourly"),
            )
            return f"Job '{args.get('name')}' scheduled (ID: {job_id})."
        elif action == "remove":
            ok = sched.remove_job(args.get("job_id", ""))
            return "Job removed." if ok else "Job not found."
        elif action == "list":
            jobs = sched.list_jobs()
            if not jobs:
                return "No scheduled jobs."
            lines = ["Scheduled Jobs:"]
            for j in jobs:
                enabled = "✓" if j["enabled"] else "✗"
                lines.append(f"  {enabled} [{j['type']}] {j['name']} — every {j['schedule']} (runs: {j['run_count']})")
            return "\n".join(lines)
        return f"Unknown action: {action}"

    async def process_text(self, user_text: str) -> str:
        """Process user text through the LLM + tool pipeline. Returns the final response."""
        self.log(f"User: {user_text}")

        self._conversation.append({"role": "user", "content": user_text})
        MAX_HISTORY = 10
        if len(self._conversation) > MAX_HISTORY:
            self._conversation = self._conversation[-MAX_HISTORY:]

        messages = [
            {"role": "system", "content": self._build_system_prompt(user_text)}
        ] + list(self._conversation)

        _NEEDS_LLM_ROUND = {"web_search", "screen_process", "agent_task"}
        _INTENT_TOOLS = {
            "open_app", "computer_control", "computer_settings",
            "send_message", "game_updater", "flight_finder",
        }
        MAX_TOOL_ROUNDS = 6
        final_reply = ""

        for _round in range(MAX_TOOL_ROUNDS):
            final_content = ""
            final_tool_calls = []

            try:
                for event in call_llm_stream(messages, OLLAMA_TOOLS):
                    if event["type"] == "sentence":
                        final_reply += event["text"] + " "
                    elif event["type"] == "done":
                        final_content = event["content"]
                        final_tool_calls = event["tool_calls"]
            except RuntimeError as e:
                return f"LLM error: {e}"

            if final_tool_calls and _round == 0 and _is_greeting(user_text):
                final_tool_calls = [
                    tc for tc in final_tool_calls
                    if tc.get("function", {}).get("name") not in _INTENT_TOOLS
                    and tc.get("function", {}).get("name") != "save_memory"
                ]
                if not final_tool_calls and not final_content:
                    final_content = "Hello! How can I help you?"

            if not final_tool_calls:
                if final_content:
                    assistant_msg = {"role": "assistant", "content": final_content}
                    messages.append(assistant_msg)
                    self._conversation.append(assistant_msg)
                    self.log(f"Jarvis: {final_content}")
                    try:
                        threading.Thread(
                            target=store_conversation,
                            args=(user_text, final_content),
                            daemon=True,
                        ).start()
                    except Exception:
                        pass
                    return final_content.strip()
                break

            assistant_msg = {
                "role": "assistant",
                "content": final_content or "",
                "tool_calls": final_tool_calls,
            }
            messages.append(assistant_msg)
            self._conversation.append(assistant_msg)

            _only_memory = all(
                tc.get("function", {}).get("name") == "save_memory"
                for tc in final_tool_calls
            )
            if _only_memory and final_content:
                for tc in final_tool_calls:
                    fn = tc.get("function", {})
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
                self.log(f"Jarvis: {final_content}")
                return final_content.strip()

            all_silent = True
            tool_results = []

            for tc in final_tool_calls:
                fn = tc.get("function", {})
                tname = fn.get("name", "")
                targs = fn.get("arguments", {})
                if isinstance(targs, str):
                    try:
                        targs = json.loads(targs)
                    except Exception:
                        targs = {}

                self.log(f"Executing: {tname}")
                result = self._execute_tool(tname, targs)

                if result != "__SILENT__":
                    all_silent = False
                    tool_results.append((tname, result))

                tool_msg = {
                    "role": "tool",
                    "content": "Done." if result == "__SILENT__" else str(result),
                }
                messages.append(tool_msg)
                self._conversation.append(tool_msg)

            if all_silent:
                continue

            if tool_results and not any(n in _NEEDS_LLM_ROUND for n, _ in tool_results):
                _, reply = tool_results[-1]
                amsg = {"role": "assistant", "content": reply}
                messages.append(amsg)
                self._conversation.append(amsg)
                self.log(f"Jarvis: {reply}")
                try:
                    threading.Thread(
                        target=store_conversation,
                        args=(user_text, reply),
                        daemon=True,
                    ).start()
                except Exception:
                    pass
                return reply.strip()

        return final_reply.strip() or "Done."


# ── WebSocket Server ─────────────────────────────────────────────────────────

class BridgeServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 8765):
        self.host = host
        self.port = port
        self.jarvis = HeadlessJarvis()
        self.clients = set()
        self._startup_done = False

    async def _init_jarvis(self):
        """Warm up the LLM on startup."""
        self.jarvis.log("Initializing headless Jarvis…")
        try:
            self.jarvis.log("Checking Ollama…")
            if ensure_ollama_running():
                self.jarvis.log("Ollama OK. Warming up model…")
                try:
                    warmup_model(system_prompt=_load_system_prompt())
                except Exception as e:
                    self.jarvis.log(f"Warmup skipped (non-fatal): {e}")
                self.jarvis.log("Model ready.")
            else:
                self.jarvis.log("WARNING: Ollama not reachable. Start it with: ollama serve")
        except Exception as e:
            self.jarvis.log(f"Init error: {e}")
        self._startup_done = True

    async def handle_client(self, websocket):
        self.clients.add(websocket)
        client_ip = websocket.remote_address
        self.jarvis.log(f"Phone connected from {client_ip}")
        try:
            async for raw in websocket:
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    await websocket.send(json.dumps({"type": "error", "text": "Invalid JSON"}))
                    continue

                msg_type = data.get("type", "")

                if msg_type == "ping":
                    await websocket.send(json.dumps({"type": "pong"}))
                    continue

                elif msg_type == "command":
                    text = data.get("text", "").strip()
                    if not text:
                        await websocket.send(json.dumps({"type": "error", "text": "Empty command"}))
                        continue

                    # Process the command
                    response = await self.jarvis.process_text(text)
                    await websocket.send(json.dumps({
                        "type": "response",
                        "text": response,
                        "done": True,
                    }))

                elif msg_type == "get_status":
                    await websocket.send(json.dumps({
                        "type": "status",
                        "llm_connected": self._startup_done,
                    }))

                else:
                    await websocket.send(json.dumps({
                        "type": "error",
                        "text": f"Unknown message type: {msg_type}",
                    }))

        except websockets.exceptions.ConnectionClosed:
            self.jarvis.log(f"Phone disconnected ({client_ip})")
        except Exception as e:
            self.jarvis.log(f"Client error: {e}")
        finally:
            self.clients.discard(websocket)

    async def start(self):
        await self._init_jarvis()
        ips = get_local_ips()

        print("=" * 56)
        print("  MARK XL — PC Bridge Server")
        print("=" * 56)
        print()
        print(f"  WebSocket endpoint:")
        for ip in ips:
            print(f"    ws://{ip}:{self.port}")
        print()
        print("  Scan the QR code below with your phone:")
        print()

        # Print QR for the first non-local IP
        qr_ip = next((ip for ip in ips if not ip.startswith("127.")), ips[0])
        print_qr(f"ws://{qr_ip}:{self.port}")
        print()
        print("  Or type this IP into the MARK XL app settings.")
        print()
        print("=" * 56)
        print("  Waiting for phone connection…")
        print()

        async with websockets.serve(self.handle_client, self.host, self.port):
            await asyncio.Future()


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="MARK XL PC Bridge Server")
    parser.add_argument("--port", type=int, default=8765, help="WebSocket port (default: 8765)")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Bind address (default: 0.0.0.0)")
    args = parser.parse_args()

    server = BridgeServer(host=args.host, port=args.port)
    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        print("\n[Bridge] Shutting down…")


if __name__ == "__main__":
    main()
