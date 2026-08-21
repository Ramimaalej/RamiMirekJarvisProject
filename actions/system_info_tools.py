"""System info tools — battery, disk usage and (where available) WiFi SSID.

Intents: battery_status ("how much battery", "battery level"),
         disk_info ("how much disk space left"), wifi_status ("what wifi am I on")
"""
import logging
import platform
import subprocess

logger = logging.getLogger("system_info")


def battery_status(parameters: dict | None = None, player=None) -> str:
    try:
        import psutil  # noqa: E402
        bat = psutil.sensors_battery()
        if bat is not None:
            state = "charging" if bat.power_plugged else "on battery"
            return (f"Battery: {bat.percent}% ({state}, "
                    f"~{bat.secsleft // 60} min remaining)" if bat.secsleft > 0
                    else f"Battery: {bat.percent}% ({state})")
        
        # Fallback for Linux if psutil fails to detect battery
        if platform.system() == "Linux":
            for path in ["/sys/class/power_supply/BAT0/capacity", "/sys/class/power_supply/BAT1/capacity"]:
                try:
                    with open(path, "r") as f:
                        cap = f.read().strip()
                        return f"Battery: {cap}% (Linux sysfs)"
                except:
                    continue
        
        return "No battery detected on this machine (desktop?)."
    except Exception as exc:  # noqa: BLE001
        logger.warning("battery error: %s", exc)
        return "Could not read battery information."


def disk_info(parameters: dict | None = None, player=None) -> str:
    try:
        import psutil  # noqa: E402
        disk = psutil.disk_usage("/")
        gb = 1024**3
        return (f"Disk: {disk.used / gb:.1f} GB used / {disk.total / gb:.1f} GB total "
                f"({disk.percent}% used), {disk.free / gb:.1f} GB free")
    except Exception as exc:  # noqa: BLE001
        logger.warning("disk error: %s", exc)
        return "Could not read disk information."


def wifi_status(parameters: dict | None = None, player=None) -> str:
    system = platform.system()
    try:
        if system == "Windows":
            out = subprocess.run(
                ["netsh", "wlan", "show", "interfaces"], capture_output=True,
                text=True, timeout=10).stdout
            for line in out.splitlines():
                if "SSID" in line and ":" in line:
                    return f"WiFi SSID: {line.split(':', 1)[1].strip()}"
            return "No WiFi interface found."
        if system == "Darwin":
            out = subprocess.run(
                ["/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/"
                 "Resources/airport", "-I"], capture_output=True, text=True, timeout=10).stdout
            for line in out.splitlines():
                if line.startswith(" SSID:"):
                    return f"WiFi SSID: {line.split(':', 1)[1].strip()}"
            return "No WiFi interface found."
        for tool in ("nmcli", "iwgetid"):
            if subprocess.run(["which", tool], capture_output=True).returncode == 0:
                cmd = [tool, "-r"] if tool == "nmcli" else [tool, "-r"]
                out = subprocess.run(cmd, capture_output=True, text=True, timeout=10).stdout.strip()
                if out:
                    return f"WiFi SSID: {out}"
        return "WiFi detection not available on this Linux setup."
    except Exception as exc:  # noqa: BLE001
        logger.warning("wifi error: %s", exc)
        return "Could not read WiFi information."
