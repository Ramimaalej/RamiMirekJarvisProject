import platform
import logging
from typing import Any

logger = logging.getLogger("screen_reader")

_OS = platform.system()


def get_ui_elements() -> list[dict[str, Any]]:
    elements = []
    try:
        if _OS == "Linux":
            return _linux_elements()
        elif _OS == "Windows":
            return _windows_elements()
        elif _OS == "Darwin":
            return _macos_elements()
    except Exception as e:
        logger.warning("screen_reader error: %s", e)
    return elements


def get_active_window_info() -> dict[str, str]:
    info = {"title": "", "app": "", "role": ""}
    try:
        if _OS == "Linux":
            return _linux_active_window()
        elif _OS == "Windows":
            return _windows_active_window()
        elif _OS == "Darwin":
            return _macos_active_window()
    except Exception as e:
        logger.warning("active_window error: %s", e)
    return info


# ── Linux (pyatspi2 / AT-SPI) ─────────────────────────────────────────────

def _linux_elements() -> list[dict]:
    try:
        import pyatspi
    except ImportError:
        logger.info("pyatspi not installed — install with: pip install pyatspi")
        return []

    desktop = pyatspi.Registry.getDesktop(0)
    elements = []
    def walk(node, depth=0):
        if depth > 5:
            return
        try:
            name = node.name or ""
            role = node.getRoleName() or ""
            if name.strip() and role in ("push button", "label", "text", "combo box",
                                         "check box", "radio button", "menu item",
                                         "list item", "heading", "link", "entry"):
                rect = None
                try:
                    ext = node.queryComponent().getExtents(pyatspi.XY_SCREEN)
                    rect = {"x": ext.x, "y": ext.y, "w": ext.width, "h": ext.height}
                except Exception:
                    pass
                elements.append({"name": name, "role": role, "rect": rect})
        except Exception:
            pass
        try:
            for child in node:
                walk(child, depth + 1)
        except Exception:
            pass

    walk(desktop)
    return elements


def _linux_active_window() -> dict:
    try:
        import pyatspi
        desktop = pyatspi.Registry.getDesktop(0)
        for app in desktop:
            try:
                for window in app:
                    if window.getState().contains(pyatspi.STATE_ACTIVE):
                        return {
                            "title": window.name or "",
                            "app": app.name or "",
                            "role": window.getRoleName() or "",
                        }
            except Exception:
                continue
    except ImportError:
        pass
    return {"title": "", "app": "", "role": ""}


# ── Windows (UIAutomation via comtypes) ───────────────────────────────────

def _windows_elements() -> list[dict]:
    try:
        from comtypes import CoInitializeEx, COINIT_MULTITHREADED, CoUninitialize
        from UIAutomation import IUIAutomation
    except ImportError:
        logger.info("UIAutomation not available — pip install UIAutomation")
        return []

    CoInitializeEx(COINIT_MULTITHREADED)
    try:
        auto = IUIAutomation.CreateInstance()
        root = auto.GetRootElement()
        elements = []
        def walk(el, depth=0):
            if depth > 5:
                return
            try:
                name = el.CurrentName or ""
                role_id = el.CurrentControlType
                rect = None
                try:
                    b = el.CurrentBoundingRectangle
                    rect = {"x": b.left, "y": b.top, "w": b.right - b.left, "h": b.bottom - b.top}
                except Exception:
                    pass
                if name.strip():
                    elements.append({"name": name, "role": str(role_id), "rect": rect})
            except Exception:
                pass
            try:
                walker = auto.CreateTreeWalker(auto.ContentViewCondition)
                child = walker.GetFirstChildElement(el)
                while child:
                    walk(child, depth + 1)
                    child = walker.GetNextSiblingElement(child)
            except Exception:
                pass
        walk(root)
        return elements
    finally:
        CoUninitialize()


def _windows_active_window() -> dict:
    try:
        import pygetwindow as gw
        w = gw.getActiveWindow()
        if w:
            return {"title": w.title, "app": w.title, "role": "window"}
    except ImportError:
        pass
    return {"title": "", "app": "", "role": ""}


# ── macOS (PyObjC / accessibility) ────────────────────────────────────────

def _macos_elements() -> list[dict]:
    try:
        import AppKit
        import ApplicationServices
    except ImportError:
        logger.info("PyObjC not available — pip install pyobjc")
        return []

    try:
        sys_pref = ApplicationServices.AXUIElementCreateSystemWide()
        focused_app = ApplicationServices.AXUIElementCreateApplication(
            ApplicationServices.NSWorkspace.sharedWorkspace().frontmostApplication().processIdentifier()
        )
        elements = []
        def walk(el, depth=0):
            if depth > 5:
                return
            try:
                name = ApplicationServices.AXUIElementCopyAttributeValue(el, "AXTitle", None)[0] or ""
                role = ApplicationServices.AXUIElementCopyAttributeValue(el, "AXRole", None)[0] or ""
                rect = None
                try:
                    pos = ApplicationServices.AXUIElementCopyAttributeValue(el, "AXPosition", None)[0]
                    size = ApplicationServices.AXUIElementCopyAttributeValue(el, "AXSize", None)[0]
                    rect = {"x": pos.x, "y": pos.y, "w": size.width, "h": size.height}
                except Exception:
                    pass
                if name.strip():
                    elements.append({"name": name, "role": str(role), "rect": rect})
            except Exception:
                pass
            try:
                children = ApplicationServices.AXUIElementCopyAttributeValue(el, "AXChildren", None)[0]
                for child in children:
                    walk(child, depth + 1)
            except Exception:
                pass
        walk(focused_app)
        return elements
    except Exception:
        return []


def _macos_active_window() -> dict:
    try:
        import AppKit
        ws = AppKit.NSWorkspace.sharedWorkspace()
        app = ws.frontmostApplication()
        return {"title": app.localizedName() or "", "app": app.localizedName() or "", "role": "window"}
    except ImportError:
        pass
    return {"title": "", "app": "", "role": ""}
