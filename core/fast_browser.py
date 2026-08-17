"""Fast Browser Automation — the fastest possible way for MARK XL to control
the user's browser.

Speed-first design choices:
  1. Connects to an ALREADY RUNNING browser via CDP (Chrome DevTools Protocol)
     — no browser startup cost, and your existing sessions/logins are reused.
  2. Uses the NEWEST TAB, so Jarvis works on what you already see.
  3. Zero `slow_mo`, no waits unless strictly needed, direct DOM access.
  4. Persistent asyncio loop + singleton — no reconnect cost between commands.

Usage:
    from core.fast_browser import FastBrowser
    fb = FastBrowser()                 # one-time init
    fb.run("open youtube")             # natural language or direct URL
    fb.run("click the search box and type hello world")

Requires: `playwright` (already in requirements.txt) and on Windows the user
starts Chrome with:  chrome.exe --remote-debugging-port=9222
(see the "Browser" tab in Settings for a one-click helper).
On macOS/Linux, the built-in browser detection takes over automatically.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import platform
import re
import socket
import subprocess
import threading
from typing import Any, Callable

import requests

logger = logging.getLogger("fast_browser")

CDP_PORT = int(os.environ.get("JARVIS_CDP_PORT", "9222"))

_OS = platform.system()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


def _fetch_cdp_targets(base: str, timeout: float = 2.0) -> list[dict]:
    try:
        resp = requests.get(f"{base}/json", timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        data = []
    return [t for t in data if isinstance(t, dict)
            and t.get("type") == "page" and t.get("webSocketDebuggerUrl")]


def list_cdp_browsers() -> list[dict]:
    """Find browsers exposing CDP on common ports."""
    out: list[dict] = []
    for port in (CDP_PORT, 9222, 9223, 9224):
        base = f"http://127.0.0.1:{port}"
        if not _port_open(port):
            continue
        targets = _fetch_cdp_targets(base)
        if targets:
            out.append({"port": port, "base": base,
                        "targets": len(targets),
                        "active_url": next((t.get("url") for t in targets if t.get("active")),
                                           targets[0].get("url", ""))})
    return out


# ---------------------------------------------------------------------------
# Fast Browser automation core
# ---------------------------------------------------------------------------
class FastBrowser:
    """Singleton async browser controller with CDP attach for maximum speed."""

    def __init__(self):
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._browser = None          # playwright Browser (CDP attached)
        self._context = None
        self._page = None
        self._pw = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    def _ensure_loop(self):
        with self._lock:
            if self._loop is not None and not self._loop.is_closed():
                return
            self._loop = asyncio.new_event_loop()
            self._thread = threading.Thread(target=self._loop.run_forever,
                                            daemon=True, name="fast_browser")
            self._thread.start()

    def run(self, command: str, timeout: int = 60) -> str:
        """Run a natural-language or direct browser command. Synchronous."""
        self._ensure_loop()
        fut = asyncio.run_coroutine_threadsafe(self._dispatch(command), self._loop)
        try:
            return fut.result(timeout=timeout)
        except asyncio.TimeoutError:
            return "Browser command timed out."
        except Exception as e:
            return f"Browser error: {e}"

    # ------------------------------------------------------------------ #
    # Connection — prefer attaching to a live browser (fastest), else launch
    # ------------------------------------------------------------------ #
    async def _connect(self):
        """Attach via CDP to an already running browser, or launch Chromium."""
        if self._page is not None and not self._page.is_closed():
            return

        if self._pw is None:
            from playwright.async_api import async_playwright
            self._pw = await async_playwright().start()

        # 1) Try CDP attach on debug ports (reuses live sessions — 0 startup cost)
        for port in (CDP_PORT, 9222, 9223, 9224):
            if not _port_open(port):
                continue
            try:
                self._browser = await self._pw.chromium.connect_over_cdp(
                    f"http://127.0.0.1:{port}", timeout=5000)
                ctxs = self._browser.contexts
                if ctxs:
                    self._context = ctxs[0]
                    pages = [p for p in self._context.pages if not p.is_closed()]
                    # Use the newest page (what the user sees)
                    self._page = pages[-1] if pages else await self._context.new_page()
                    logger.info("FastBrowser attached via CDP port %s", port)
                    return
            except Exception as e:
                logger.debug("CDP attach on %s failed: %s", port, e)

        # 2) Launch Chromium headful with user-visible window (slower, fallback)
        self._context = await self._pw.chromium.launch_persistent_context(
            user_data_dir=os.path.join(os.path.expanduser("~"), ".jarvis_fastbrowser"),
            headless=False,
            slow_mo=0,
            viewport=None,
            no_viewport=True,
            args=["--start-maximized", "--disable-blink-features=AutomationControlled",
                  "--no-first-run", "--disable-default-apps"],
            timeout=60000,
        )
        self._browser = self._context.browser
        pages = [p for p in self._context.pages if not p.is_closed()]
        self._page = pages[-1] if pages else await self._context.new_page()
        logger.info("FastBrowser launched new Chromium window")

    # ------------------------------------------------------------------ #
    # Direct primitives (zero interpretation overhead)
    # ------------------------------------------------------------------ #
    async def go(self, url: str) -> str:
        await self._connect()
        url = url.strip()
        if "://" not in url:
            if "." in url:
                url = "https://" + url
            else:
                url = f"https://www.google.com/search?q={url.replace(' ', '+')}"
        await self._page.goto(url, wait_until="domcontentloaded", timeout=30000)
        return f"Opened {self._page.url}"

    async def click_text(self, text: str) -> str:
        await self._connect()
        ok = await self._page.locator(
            f"text={text}:visible").first.click(timeout=8000, force=False)
        return f"Clicked '{text}'" if ok is not None else f"'{text}' not found"

    async def type_text(self, selector: str, text: str, press_enter: bool = True) -> str:
        await self._connect()
        el = self._page.locator(selector).first
        await el.fill("", timeout=8000)
        await el.type(text, delay=0)      # delay=0 → instant typing
        if press_enter:
            await el.press("Enter")
        return f"Typed '{text}' into {selector}"

    async def press_key(self, key: str) -> str:
        await self._connect()
        await self._page.keyboard.press(key)
        return f"Pressed {key}"

    async def grab_text(self) -> str:
        """Instantly grab page text (up to 4000 chars) — for answering questions."""
        await self._connect()
        text = await self._page.inner_text("body")
        clean = re.sub(r"\s+", " ", text).strip()
        return clean[:4000]

    async def grab_url(self) -> str:
        await self._connect()
        return self._page.url

    async def screenshot(self, path: str = "jarvis_page.png") -> str:
        await self._connect()
        await self._page.screenshot(path=path)
        return f"Screenshot saved: {path}"

    # ------------------------------------------------------------------ #
    # Dispatcher — natural-language → primitives
    # ------------------------------------------------------------------ #
    async def _dispatch(self, command: str) -> str:
        cmd = command.strip()
        lower = cmd.lower()

        # Direct URL / navigation
        m = re.match(r"^(?:open|go to|navigate to|visit)\s+(.+)$", lower)
        if m or cmd.startswith(("http", "www")) or ("." in cmd.split()[-1]):
            url = m.group(1) if m else cmd.split()[-1]
            return await self.go(url)

        if lower.startswith("click "):
            text = cmd[6:].strip().strip("\"'")
            return await self.click_text(text)

        if lower.startswith("type ") or lower.startswith("search "):
            # type "text" / search youtube for music
            m = re.match(r"^(?:type|search(?:\s+(?:on\s+)?\S+)?)\s+(.+?)(?:\s+for\s+(.+))?$", lower)
            if m:
                target, query = m.group(1), m.group(2)
                if query:
                    return await self.go(f"https://www.google.com/search?q={query.replace(' ', '+')}")
                return f"Use: type into FIELD the TEXT — or just say 'search X'"

        if lower.startswith("enter"):
            return await self.press_key("Enter")

        if lower.startswith("grab") or lower.startswith("read page") or lower.startswith("what") or lower.startswith("summarize"):
            return await self.grab_text()

        if lower.startswith("url"):
            return await self.grab_url()

        if lower.startswith("screenshot"):
            return await self.screenshot()

        if lower.startswith("back"):
            await self._connect()
            await self._page.go_back()
            return f"Back → {self._page.url}"

        if lower.startswith("refresh") or lower.startswith("reload"):
            await self._connect()
            await self._page.reload(wait_until="domcontentloaded")
            return f"Refreshed {self._page.url}"

        # Scroll
        if lower.startswith("scroll"):
            await self._connect()
            amount = re.search(r"(\d+)", cmd)
            n = int(amount.group(1)) if amount else 600
            if "up" in lower:
                n = -n
            await self._page.mouse.wheel(0, n)
            return f"Scrolled {n}px"

        # New tab
        m = re.match(r"^new tab(?:\s+(.+))?$", lower)
        if m:
            await self._connect()
            url = m.group(1)
            if url:
                return await self.go(url)
            p = await self._context.new_page()
            self._page = p
            return "New tab opened"

        # Close tab
        if lower.startswith("close tab"):
            await self._connect()
            await self._page.close()
            pages = [p for p in self._context.pages if not p.is_closed()]
            self._page = pages[-1] if pages else None
            return "Tab closed"

        # Generic: treat as a search or URL
        return await self.go(cmd)


# Module-level singleton
_browser: FastBrowser | None = None


def get_fast_browser() -> FastBrowser:
    global _browser
    if _browser is None:
        _browser = FastBrowser()
    return _browser
