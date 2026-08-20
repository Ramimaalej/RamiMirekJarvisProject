#computer_control.py
import random
import string
import io
import json
import re
import shlex
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path

from core.safe_math import safe_math
from core.llm_client import resolve_llm_url

from actions.file_controller import open_folder as _open_folder

try:
    import pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE    = 0.05
    _PYAUTOGUI = True
except Exception:
    _PYAUTOGUI = False

try:
    import pyperclip
    _PYPERCLIP = True
except ImportError:
    _PYPERCLIP = False

def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


_BASE         = _base_dir()
_CONFIG_PATH  = _BASE / "config" / "api_keys.json"
_MEMORY_PATH  = _BASE / "memory" / "long_term.json"

def _load_config() -> dict:
    try:
        cfg = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        cfg = {}
    if cfg.get("llm_url_local") or cfg.get("llm_url_remote"):
        cfg["llm_url"] = resolve_llm_url(cfg)
    return cfg

def _get_os() -> str:
    import platform
    s = platform.system().lower()
    if s == "darwin":
        return "mac"
    return s  # "windows" or "linux"


_SAFE_SCREENSHOT_ROOTS = (
    Path.home(),
)

def _safe_screenshot_path(requested: str | None) -> Path:
    fallback = Path.home() / "Desktop" / "jarvis_screenshot.png"
    if not requested:
        return fallback
    try:
        p = Path(requested).expanduser().resolve()
        for root in _SAFE_SCREENSHOT_ROOTS:
            if p.is_relative_to(root.resolve()):
                p.parent.mkdir(parents=True, exist_ok=True)
                return p
    except Exception:
        pass
    return fallback

def _require_pyautogui():
    if not _PYAUTOGUI:
        raise RuntimeError("PyAutoGUI not installed. Run: pip install pyautogui")

_FIRST_NAMES = [
    "Alex", "Jordan", "Taylor", "Morgan", "Casey", "Riley", "Drew", "Quinn",
    "Avery", "Blake", "Cameron", "Dakota", "Emerson", "Finley", "Harper",
]
_LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
    "Davis", "Wilson", "Moore", "Taylor", "Anderson", "Thomas", "Jackson",
]
_DOMAINS = ["gmail.com", "yahoo.com", "outlook.com", "proton.me", "mail.com"]


def _random_data(data_type: str) -> str:
    dt = data_type.lower().strip()

    if dt == "first_name":
        return random.choice(_FIRST_NAMES)

    if dt == "last_name":
        return random.choice(_LAST_NAMES)

    if dt == "name":
        return f"{random.choice(_FIRST_NAMES)} {random.choice(_LAST_NAMES)}"

    if dt == "email":
        first = random.choice(_FIRST_NAMES).lower()
        last  = random.choice(_LAST_NAMES).lower()
        num   = random.randint(10, 999)
        return f"{first}.{last}{num}@{random.choice(_DOMAINS)}"

    if dt == "username":
        return f"{random.choice(_FIRST_NAMES).lower()}{random.randint(100, 9999)}"

    if dt == "password":
        chars = string.ascii_letters + string.digits + "!@#$%"
        raw   = (
            random.choice(string.ascii_uppercase)
            + random.choice(string.digits)
            + random.choice("!@#$%")
            + "".join(random.choices(chars, k=9))
        )
        return "".join(random.sample(raw, len(raw)))

    if dt == "phone":
        return f"+1{random.randint(200,999)}{random.randint(1_000_000, 9_999_999)}"

    if dt == "birthday":
        y = random.randint(1980, 2000)
        m = random.randint(1, 12)
        d = random.randint(1, 28)
        return f"{m:02d}/{d:02d}/{y}"

    if dt == "address":
        num    = random.randint(100, 9999)
        street = random.choice(["Main St", "Oak Ave", "Park Blvd", "Elm St", "Cedar Ln"])
        return f"{num} {street}"

    if dt == "zip_code":
        return str(random.randint(10000, 99999))

    if dt == "city":
        return random.choice(["New York", "Los Angeles", "Chicago", "Houston", "Phoenix"])

    return f"random_{data_type}_{random.randint(1000, 9999)}"

def _user_profile() -> dict:
    """Read identity fields from long-term memory + static user profile."""
    prof: dict = {}
    try:
        if _MEMORY_PATH.exists():
            data     = json.loads(_MEMORY_PATH.read_text(encoding="utf-8"))
            identity = data.get("identity", {})
            prof.update({k: v.get("value", "") for k, v in identity.items()})
    except Exception:
        pass
    # Static profile (config/user_profile.json) fills anything not in memory
    try:
        _upath = Path(__file__).resolve().parent.parent / "config" / "user_profile.json"
        if _upath.exists():
            _data = json.loads(_upath.read_text(encoding="utf-8"))
            if not prof.get("name") and _data.get("name"):
                prof["name"] = _data["name"]
            if not prof.get("email") and _data.get("email"):
                prof["email"] = _data["email"]
            if not prof.get("city") and (_data.get("city") or _data.get("location")):
                prof["city"] = _data.get("city") or _data.get("location")
            if not prof.get("phone") and _data.get("phone"):
                prof["phone"] = _data["phone"]
    except Exception:
        pass
    return prof

def _type(text: str, interval: float = 0.03) -> str:
    _require_pyautogui()
    time.sleep(0.3)
    pyautogui.typewrite(text, interval=interval)
    return f"Typed: {text[:60]}{'…' if len(text) > 60 else ''}"


def _smart_type(text: str, clear_first: bool = True) -> str:
    _require_pyautogui()
    if clear_first:
        _clear_field()
        time.sleep(0.1)

    if len(text) > 20 and _PYPERCLIP:
        pyperclip.copy(text)
        time.sleep(0.1)
        pyautogui.hotkey("ctrl", "v")
        return f"Smart-typed (clipboard): {text[:60]}{'…' if len(text) > 60 else ''}"

    pyautogui.typewrite(text, interval=0.04)
    return f"Smart-typed: {text[:60]}{'…' if len(text) > 60 else ''}"


def _is_math(text: str) -> bool:
    s = text.strip()
    if not s or len(s) > 80:
        return False
    # Pure math: 561+215, 20*5, (10+2)/3
    if re.match(r'^[\d\s+\-*/().,%^]+$', s.replace(" ", "")):
        return True
    # Percentage: "20% of 10000", "15 percent of 200", "10% out of 50"
    if re.match(r'^[\d.]+\s*%?\s*(?:percent\s+of|percent|of|out\s+of)\s+[\d.]+', s, re.IGNORECASE):
        return True
    return False

def _calculate(text: str) -> str:
    s = text.strip()
    try:
        # Percentage: "20% of 10000" or "20 percent of 200" or "10% out of 50"
        m = re.match(r'([\d.]+)\s*%?\s*(?:percent\s+of|percent|of|out\s+of)\s+([\d.]+)', s, re.IGNORECASE)
        if m:
            pct = float(m.group(1))
            val = float(m.group(2))
            result = val * pct / 100
            return f"{pct}% of {val} = {result}"
        # Pure math
        result = safe_math(s)
        return f"{s} = {result}"
    except Exception:
        return text


def _click(x=None, y=None, button: str = "left", clicks: int = 1) -> str:
    _require_pyautogui()
    if x is not None and y is not None:
        pyautogui.click(x, y, button=button, clicks=clicks)
        return f"{'Double-c' if clicks == 2 else 'C'}licked ({x}, {y}) [{button}]"
    pyautogui.click(button=button, clicks=clicks)
    return f"Clicked at current position [{button}]"


def _hotkey(*keys) -> str:
    _require_pyautogui()
    pyautogui.hotkey(*keys)
    return f"Hotkey: {'+'.join(keys)}"


def _press(key: str) -> str:
    _require_pyautogui()
    pyautogui.press(key)
    return f"Pressed: {key}"


def _scroll(direction: str = "down", amount: int = 3) -> str:
    _require_pyautogui()
    vertical   = direction in ("up", "down")
    clicks     = amount if direction in ("up", "right") else -amount
    pyautogui.scroll(clicks) if vertical else pyautogui.hscroll(clicks)
    return f"Scrolled {direction} ×{amount}"


def _move(x: int, y: int, duration: float = 0.3) -> str:
    _require_pyautogui()
    pyautogui.moveTo(x, y, duration=duration)
    return f"Mouse → ({x}, {y})"


def _drag(x1: int, y1: int, x2: int, y2: int, duration: float = 0.5) -> str:
    _require_pyautogui()
    pyautogui.moveTo(x1, y1, duration=0.2)
    pyautogui.dragTo(x2, y2, duration=duration, button="left")
    return f"Dragged ({x1},{y1}) → ({x2},{y2})"


def _clipboard_get() -> str:
    if _PYPERCLIP:
        return pyperclip.paste()
    _hotkey("ctrl", "c")
    time.sleep(0.2)
    return "(copied — pyperclip unavailable for read)"


def _clipboard_paste(text: str) -> str:
    if _PYPERCLIP:
        pyperclip.copy(text)
        time.sleep(0.1)
        _require_pyautogui()
        pyautogui.hotkey("ctrl", "v")
        return f"Pasted: {text[:60]}{'…' if len(text) > 60 else ''}"
    return "pyperclip not available"


def _screenshot(save_path: str | None = None) -> str:
    _require_pyautogui()
    path = _safe_screenshot_path(save_path)
    img  = pyautogui.screenshot()
    img.save(str(path))
    return f"Screenshot saved: {path}"


_DANGEROUS_PATTERNS = [
    # OS-agnostic destructive commands
    r"^rm\s+-rf?\s+/",                 # rm -rf on absolute paths
    r"^format\s+[cd]:",                # format C: / D:
    r"^(del|deltree)\b.*\*",           # del/deltree with any wildcard
    r"^(del|deltree)\b.*[cd]:\\?",     # del/deltree targeting a drive root
    r"^dd\s+.*\bof=/dev/(sda|sd[b-z]|nvme|disk0|disk1)\b",
    r"^mkfs\.",                        # format any partition
    r"^shutdown\s+(-[sS]|/[sS]|/p)",   # immediate shutdown (Win+Unix)
    r"^powercfg",                      # power config abuse
]

def _is_safe_command(command: str, os_name: str) -> str | None:
    """Return a rejection reason if the command is destructive, else None."""
    flat = command.strip().lower()
    if flat.startswith("history"):
        return "Command rejected: 'history' is a shell builtin — use my memory instead."
    for pat in _DANGEROUS_PATTERNS:
        if re.search(pat, flat):
            return f"Command rejected for your safety (destructive): '{command.strip()}'"
    return None

def _adapt_command(command: str, os_name: str) -> str:
    """Translate common shell commands to the native OS equivalent."""
    if os_name == "windows":
        t = command.strip().lower()
        if t.startswith("ls ") or t == "ls":
            return "dir " + command[3:].strip()
        if t.startswith("cat "):
            return "type " + command[4:].strip()
        if t.startswith("rm "):
            return "del " + command[3:].strip()
        if t.startswith("mkdir "):
            return "mkdir " + command[6:].strip()
        if t.startswith("cp "):
            return "copy " + command[3:].replace(" ", " ")
        if t.startswith("mv "):
            return "move " + command[3:].strip()
        if t.startswith("grep "):
            # grep word file -> findstr /i "word" file
            m = re.match(r"grep\s+(?:(?:-[a-zA-Z]+)\s+)*\"?([^\s\"])\"?\s+(.+)", command.strip())
            if m:
                return f'findstr /i "{m.group(1)}" {m.group(2)}'
        if t.startswith("ps ") or t == "ps":
            return "tasklist"
        if t.startswith("kill "):
            return "taskkill /PID " + command[5:].strip()
        if t == "pwd":
            return "cd"
        if t == "clear":
            return "cls"
        if t == "whoami":
            return "whoami"
        if t == "ifconfig" or t == "ip addr":
            return "ipconfig"
    elif os_name == "mac":
        if command.strip().lower() == "ls":
            return command  # already native
    return command

def _run_command(command: str, timeout: int = 60, workdir: str | None = None) -> str:
    """Run an arbitrary shell command, adapted to the detected OS."""
    command = command.strip()
    if not command:
        return "No command given."
    os_name = _get_os()
    reject = _is_safe_command(command, os_name)
    if reject:
        return reject
    command = _adapt_command(command, os_name)
    try:
        cwd = Path(workdir).expanduser().resolve() if workdir else None
        if os_name == "windows":
            # Windows: some commands are shell builtins (dir, cls, tasklist)
            # Use cmd.exe /c so builtins work exactly like the real terminal.
            result = subprocess.run(
                ["cmd.exe", "/c", command],
                capture_output=True,
                timeout=timeout,
                cwd=cwd,
                text=True,
            )
        else:
            # bash -c supports pipes, redirections, &&, variables and builtins
            result = subprocess.run(
                ["bash", "-c", command],
                capture_output=True,
                timeout=timeout,
                cwd=cwd,
                text=True,
            )
        out = result.stdout.strip()
        err = result.stderr.strip()
        rc = result.returncode
        parts = [f"[{os_name}] Exit code: {rc}"]
        if out:
            parts.append(f"STDOUT:\n{out[:2000]}")
        if err:
            parts.append(f"STDERR:\n{err[:1000]}")
        if rc != 0 and not err and not out:
            parts.append("(command produced no output)")
        return "\n".join(parts)
    except subprocess.TimeoutExpired:
        return f"Command timed out after {timeout}s"
    except Exception as e:
        return f"run_command failed: {e}"


def _run_python(code: str, timeout: int = 30) -> str:
    """Run inline Python code and return stdout/stderr."""
    try:
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            timeout=timeout,
            text=True,
        )
        out = result.stdout.strip()
        err = result.stderr.strip()
        rc = result.returncode
        parts = [f"Exit code: {rc}"]
        if out:
            parts.append(f"STDOUT:\n{out[:2000]}")
        if err:
            parts.append(f"STDERR:\n{err[:1000]}")
        return "\n".join(parts)
    except subprocess.TimeoutExpired:
        return f"Python code timed out after {timeout}s"
    except Exception as e:
        return f"run_python failed: {e}"


def _clear_field() -> str:
    _require_pyautogui()
    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.1)
    pyautogui.press("delete")
    return "Field cleared"

def _focus_window(title: str) -> str:
    os_name = _get_os()

    if os_name == "windows":
        try:
            script = f'(New-Object -ComObject WScript.Shell).AppActivate("{title}")'
            subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True, timeout=5,
            )
            time.sleep(0.3)
            return f"Focused window: {title}"
        except Exception as e:
            return f"focus_window (Windows) failed: {e}"

    if os_name == "mac":
        script = (
            f'tell application "System Events" to '
            f'set frontmost of (first process whose name contains "{title}") to true'
        )
        try:
            subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, timeout=5,
            )
            time.sleep(0.3)
            return f"Focused window: {title}"
        except Exception as e:
            return f"focus_window (macOS) failed: {e}"

    if os_name == "linux":
        try:
            result = subprocess.run(
                ["wmctrl", "-a", title],
                capture_output=True, timeout=5,
            )
            if result.returncode == 0:
                time.sleep(0.3)
                return f"Focused window: {title}"
        except FileNotFoundError:
            pass
        try:
            result = subprocess.run(
                ["xdotool", "search", "--name", title, "windowactivate"],
                capture_output=True, timeout=5,
            )
            time.sleep(0.3)
            return f"Focused window: {title}"
        except FileNotFoundError:
            return "focus_window (Linux) requires wmctrl or xdotool"
        except Exception as e:
            return f"focus_window (Linux) failed: {e}"

    return f"focus_window: unknown OS '{os_name}'"

def _screen_find(description: str) -> tuple[int, int] | None:
    try:
        import base64
        import requests as _req
        import json as _json

        cfg_path = Path(__file__).resolve().parent.parent / "config" / "api_keys.json"
        try:
            cfg = _json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception:
            cfg = {}

        ollama_url   = cfg.get("llm_url", "http://localhost:11434").rstrip("/")
        vision_model = cfg.get("vision_model") or cfg.get("llm_model", "llava")

        _require_pyautogui()
        w, h  = pyautogui.size()
        img   = pyautogui.screenshot()
        buf   = io.BytesIO()
        img.save(buf, format="PNG")
        b64   = base64.b64encode(buf.getvalue()).decode("ascii")

        prompt = (
            f"This is a screenshot of a {w}×{h} pixel screen. "
            f"Locate the UI element described as: '{description}'. "
            f"Reply with ONLY the center coordinates as: x,y "
            f"If the element is not visible, reply: NOT_FOUND"
        )

        resp = _req.post(
            f"{ollama_url}/api/chat",
            json={
                "model":  vision_model,
                "stream": False,
                "messages": [{"role": "user", "content": prompt, "images": [b64]}],
            },
            timeout=30,
        )
        resp.raise_for_status()
        text = (resp.json().get("message", {}).get("content") or "").strip()

        if "NOT_FOUND" in text.upper():
            return None

        match = re.search(r"(\d+)\s*,\s*(\d+)", text)
        if match:
            return int(match.group(1)), int(match.group(2))

    except Exception as e:
        print(f"[ComputerControl] ⚠️ screen_find failed: {e}")

    return None

def computer_control(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    """
    Dispatch table for all computer control actions.

    parameters keys (all optional unless noted):
      action        : (required) one of the actions listed below
      text          : text to type or paste
      x, y          : screen coordinates
      button        : 'left' | 'right' (default: left)
      keys          : hotkey string, e.g. 'ctrl+c'
      key           : single key name, e.g. 'enter'
      direction     : 'up' | 'down' | 'left' | 'right'
      amount        : scroll amount (default: 3)
      seconds       : wait duration
      title         : window title fragment for focus_window
      description   : natural-language element description for screen_find/click
      type          : data type for random_data
      field         : memory field name for user_data
      clear_first   : bool, clear field before typing (default: true)
      path          : save path for screenshot (must be inside home dir)

    Actions:
      type          — type text at cursor
      smart_type    — clear field + type (clipboard-backed)
      click         — left click
      double_click  — double left click
      right_click   — right click
      move          — move mouse
      drag          — click-drag between two points
      hotkey        — key combination
      press         — single key
      scroll        — scroll the wheel
      copy          — read clipboard
      paste         — write + paste clipboard
      screenshot    — capture screen (safe path only)
      wait          — sleep N seconds
      clear_field   — select-all + delete
      focus_window  — bring window to foreground
      screen_find   — AI element finder (returns x,y)
      screen_click  — AI element finder + click
      random_data   — generate fake form data
      user_data     — pull real data from memory
      run_command   — execute arbitrary shell command (use 'command' param)
      run_python    — execute inline Python code (use 'code' param)
    """
    params = parameters or {}
    action = params.get("action", "").lower().strip()

    if not action:
        return "No action specified for computer_control."

    if player:
        player.write_log(f"[Computer] {action}")

    print(f"[ComputerControl] ▶ {action}  {params}")

    try:

        if action in ("type", "smart_type"):
            text = params.get("text", "")
            # Catch misrouted math questions → calculate instead of typing
            if _is_math(text):
                return _calculate(text)
            if action == "type":
                return _type(text)
            return _smart_type(text, clear_first=params.get("clear_first", True))

        if action in ("click", "left_click"):
            return _click(params.get("x"), params.get("y"), "left", 1)

        if action == "double_click":
            return _click(params.get("x"), params.get("y"), "left", 2)

        if action == "right_click":
            return _click(params.get("x"), params.get("y"), "right", 1)

        if action == "move":
            return _move(int(params.get("x", 0)), int(params.get("y", 0)))

        if action == "drag":
            return _drag(
                int(params.get("x1", 0)), int(params.get("y1", 0)),
                int(params.get("x2", 0)), int(params.get("y2", 0)),
            )

        if action == "hotkey":
            raw  = params.get("keys", "")
            keys = [k.strip() for k in raw.split("+")] if isinstance(raw, str) else raw
            return _hotkey(*keys)

        if action == "press":
            return _press(params.get("key", "enter"))

        if action == "scroll":
            return _scroll(
                direction=params.get("direction", "down"),
                amount=int(params.get("amount", 3)),
            )

        if action == "copy":
            return _clipboard_get()

        if action == "paste":
            return _clipboard_paste(params.get("text", ""))

        if action == "screenshot":
            return _screenshot(params.get("path"))

        if action == "screen_find":
            coords = _screen_find(params.get("description", ""))
            return f"{coords[0]},{coords[1]}" if coords else "NOT_FOUND"

        if action == "screen_click":
            desc   = params.get("description", "")
            coords = _screen_find(desc)
            if coords:
                time.sleep(0.2)
                _click(x=coords[0], y=coords[1])
                return f"Clicked '{desc}' at {coords}"
            return f"Element not found on screen: '{desc}'"

        if action == "wait":
            secs = float(params.get("seconds", 1.0))
            secs = min(secs, 30.0)
            time.sleep(secs)
            return f"Waited {secs}s"

        if action == "clear_field":
            return _clear_field()

        if action == "focus_window":
            return _focus_window(params.get("title", ""))

        if action == "random_data":
            dt     = params.get("type", "name")
            result = _random_data(dt)
            print(f"[ComputerControl] 🎲 random {dt} → {result}")
            return result

        if action == "user_data":
            field   = params.get("field", "name")
            profile = _user_profile()
            value   = profile.get(field, "")
            if not value:
                value = _random_data(field)
                print(f"[ComputerControl] ⚠️ No '{field}' in memory, using random: {value}")
            return value

        if action in ("open", "open_folder", "reveal", "show"):
            return _open_folder(
                params.get("path") or params.get("text") or params.get("value", ""),
                name=params.get("name", ""),
            )

        if action in ("run_command", "shell", "terminal", "bash", "sh"):
            return _run_command(
                command=params.get("command") or params.get("text", ""),
                timeout=int(params.get("timeout", 60)),
                workdir=params.get("workdir"),
            )

        if action in ("run_python", "python", "exec_python"):
            return _run_python(
                code=params.get("code") or params.get("text", ""),
                timeout=int(params.get("timeout", 30)),
            )

        if action in ("list_processes", "running_apps", "list_apps", "processes"):
            return "list_processes is not yet implemented. Use run_command with 'ps aux' instead."

        # Catch common misroutes from the LLM
        text_val = params.get("text", "") or params.get("value", "")
        if action in ("get_text", "read_text", "read_screen"):
            return "I think you meant to ask me directly — please rephrase as a question."

        if _is_math(text_val):
            return _calculate(text_val)

        return f"Unknown action: '{action}'"

    except Exception as e:
        print(f"[ComputerControl] ❌ {action}: {e}")
        return f"computer_control '{action}' failed: {e}"