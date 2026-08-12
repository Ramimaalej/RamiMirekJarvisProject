import logging
import platform
from typing import Any

logger = logging.getLogger("monitor_manager")


def get_monitors() -> list[dict[str, Any]]:
    try:
        from screeninfo import get_monitors
        monitors = get_monitors()
        return [
            {
                "name": m.name or f"Monitor {i}",
                "index": i,
                "x": m.x,
                "y": m.y,
                "width": m.width,
                "height": m.height,
                "is_primary": m.is_primary,
                "dpi": getattr(m, "dpi", None),
            }
            for i, m in enumerate(monitors)
        ]
    except ImportError:
        logger.info("screeninfo not installed — pip install screeninfo")
        return []
    except Exception as e:
        logger.warning("get_monitors error: %s", e)
        return []


def get_monitor_summary() -> str:
    monitors = get_monitors()
    if not monitors:
        return "No monitor information available."
    parts = [f"Detected {len(monitors)} monitor(s):"]
    for m in monitors:
        primary = " (Primary)" if m["is_primary"] else ""
        parts.append(
            f"  {m['name']}{primary}: {m['width']}x{m['height']} "
            f"at ({m['x']}, {m['y']})"
        )
    return "\n".join(parts)


def _xrandr_output_names() -> list[str]:
    """Parse actual output names from xrandr (e.g. eDP-1, HDMI-1, DP-1)."""
    try:
        import subprocess
        result = subprocess.run(["xrandr", "--query"], capture_output=True, text=True, timeout=5)
        names = []
        for line in result.stdout.splitlines():
            # Lines like: "eDP-1 connected primary 1920x1080+0+0"
            parts = line.split()
            if len(parts) >= 2 and parts[1] in ("connected", "disconnected"):
                names.append(parts[0])
        return names
    except Exception:
        return []


def set_monitor_brightness(monitor_index: int = 0, brightness: float = 1.0) -> bool:
    _OS = platform.system()
    try:
        if _OS == "Linux":
            import subprocess
            output_names = _xrandr_output_names()
            if not output_names:
                logger.warning("Could not detect monitor output names from xrandr")
                return False
            if monitor_index >= len(output_names):
                logger.warning("Monitor index %d out of range (have %d monitors)", monitor_index, len(output_names))
                return False
            output_name = output_names[monitor_index]
            cmd = ["xrandr", "--output", output_name, "--brightness", str(brightness)]
            subprocess.run(cmd, capture_output=True, timeout=5)
            return True
        elif _OS == "Windows":
            import subprocess
            cmd = ["powershell", "-Command",
                   f"(Get-WmiObject -Namespace root/wmi -Class WmiMonitorBrightnessMethods)"
                   f".WmiSetBrightness(1,{int(brightness * 100)})"]
            subprocess.run(cmd, capture_output=True, timeout=10)
            return True
        elif _OS == "Darwin":
            import subprocess
            cmd = ["brightness", str(brightness)]
            subprocess.run(cmd, capture_output=True, timeout=5)
            return True
    except Exception as e:
        logger.warning("set_brightness error: %s", e)
    return False


def get_active_monitor() -> dict[str, Any] | None:
    monitors = get_monitors()
    if not monitors:
        return None
    primary = next((m for m in monitors if m["is_primary"]), monitors[0])
    return primary
