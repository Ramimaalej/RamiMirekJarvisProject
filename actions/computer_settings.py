#computer_settings.py
import json
import re
import sys
import time
import subprocess
import platform
from pathlib import Path

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

_OS = platform.system()  # "Windows" | "Darwin" | "Linux"


def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

def _get_macos_wifi_interface() -> str:
    try:
        result = subprocess.run(
            ["networksetup", "-listallhardwareports"],
            capture_output=True, text=True, timeout=5
        )
        lines = result.stdout.splitlines()
        for i, line in enumerate(lines):
            if "Wi-Fi" in line or "AirPort" in line:
                for j in range(i, min(i + 4, len(lines))):
                    if lines[j].startswith("Device:"):
                        return lines[j].split(":", 1)[1].strip()
    except Exception:
        pass
    return "en0" 

def volume_up(value: int = 10):
    pct = f"+{value}%"
    if _OS == "Windows":
        for _ in range(max(1, value // 2)): pyautogui.press("volumeup")
    elif _OS == "Darwin":
        subprocess.run(["osascript", "-e",
            "set volume output volume (output volume of (get volume settings) + " + str(value) + ")"],
            capture_output=True)
    else:
        subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", pct],
            capture_output=True)

def volume_down(value: int = 10):
    pct = f"-{value}%"
    if _OS == "Windows":
        for _ in range(max(1, value // 2)): pyautogui.press("volumedown")
    elif _OS == "Darwin":
        subprocess.run(["osascript", "-e",
            "set volume output volume (output volume of (get volume settings) - " + str(value) + ")"],
            capture_output=True)
    else:
        subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", pct],
            capture_output=True)

def volume_mute():
    if _OS == "Windows":
        pyautogui.press("volumemute")
    elif _OS == "Darwin":
        subprocess.run(["osascript", "-e", "set volume with output muted"],
            capture_output=True)
    else:
        subprocess.run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"],
            capture_output=True)

def volume_set(value: int):
    value = max(0, min(100, int(value)))
    if _OS == "Windows":
        try:
            import math
            from ctypes import cast, POINTER
            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            devices   = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            vol       = cast(interface, POINTER(IAudioEndpointVolume))
            vol_db    = -65.25 if value == 0 else max(-65.25, 20 * math.log10(value / 100))
            vol.SetMasterVolumeLevel(vol_db, None)
            return
        except Exception as e:
            print(f"[Settings] pycaw failed, using keypress fallback: {e}")
            pyautogui.press("volumemute")
            pyautogui.press("volumemute")
    elif _OS == "Darwin":
        subprocess.run(["osascript", "-e", f"set volume output volume {value}"],
            capture_output=True)
        return
    else:
        subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{value}%"],
            capture_output=True)
        return

def _xrandr_brightness(delta: float):
    """Adjust screen brightness via xrandr using pure Python (no shell)."""
    try:
        out = subprocess.run(["xrandr", "--verbose"], capture_output=True, text=True, timeout=5).stdout
        for line in out.splitlines():
            if " connected" in line:
                output = line.split()[0]
                break
        else:
            return
        for line in out.splitlines():
            if "Brightness:" in line:
                b = float(line.split(":")[1].strip())
                break
        else:
            return
        new_b = max(0.1, min(1.0, b + delta))
        subprocess.run(["xrandr", "--output", output, "--brightness", f"{new_b}"],
                       capture_output=True, timeout=5)
    except Exception as e:
        print(f"[Settings] xrandr brightness failed: {e}")

def brightness_up():
    if _OS == "Darwin":
        subprocess.run(["osascript", "-e",
            'tell application "System Events" to key code 144'],
            capture_output=True)
    elif _OS == "Linux":
        if subprocess.run(["which", "brightnessctl"],
                capture_output=True).returncode == 0:
            subprocess.run(["brightnessctl", "set", "10%+"], capture_output=True)
        else:
            _xrandr_brightness(0.1)
    else:
        try:
            subprocess.run(
                ["powershell", "-Command",
                 "(Get-WmiObject -Namespace root/wmi -Class WmiMonitorBrightnessMethods)"
                 ".WmiSetBrightness(1, [math]::Min(100, "
                 "(Get-WmiObject -Namespace root/wmi -Class WmiMonitorBrightness).CurrentBrightness + 10))"],
                capture_output=True, timeout=5
            )
        except Exception as e:
            print(f"[Settings] Brightness up failed on Windows: {e}")

def brightness_down():
    if _OS == "Darwin":
        subprocess.run(["osascript", "-e",
            'tell application "System Events" to key code 145'],
            capture_output=True)
    elif _OS == "Linux":
        if subprocess.run(["which", "brightnessctl"],
                capture_output=True).returncode == 0:
            subprocess.run(["brightnessctl", "set", "10%-"], capture_output=True)
        else:
            _xrandr_brightness(-0.1)
    else:
        try:
            subprocess.run(
                ["powershell", "-Command",
                 "(Get-WmiObject -Namespace root/wmi -Class WmiMonitorBrightnessMethods)"
                 ".WmiSetBrightness(1, [math]::Max(0, "
                 "(Get-WmiObject -Namespace root/wmi -Class WmiMonitorBrightness).CurrentBrightness - 10))"],
                capture_output=True, timeout=5
            )
        except Exception as e:
            print(f"[Settings] Brightness down failed on Windows: {e}")

def close_app():
    if _OS == "Darwin": pyautogui.hotkey("command", "q")
    else:               pyautogui.hotkey("alt", "f4")

def close_window():
    if _OS == "Darwin": pyautogui.hotkey("command", "w")
    else:               pyautogui.hotkey("ctrl", "w")

def full_screen():
    if _OS == "Darwin": pyautogui.hotkey("ctrl", "command", "f")
    else:               pyautogui.press("f11")

def minimize_window():
    if _OS == "Darwin": pyautogui.hotkey("command", "m")
    else:               pyautogui.hotkey("win", "down")

def maximize_window():
    if _OS == "Darwin":
        subprocess.run(["osascript", "-e",
            'tell application "System Events" to keystroke "f" '
            'using {control down, command down}'],
            capture_output=True)
    elif _OS == "Windows":
        pyautogui.hotkey("win", "up")
    else:
        try:
            subprocess.run(["wmctrl", "-r", ":ACTIVE:", "-b", "add,maximized_vert,maximized_horz"],
                capture_output=True)
        except Exception:
            pyautogui.hotkey("super", "up")

def snap_left():
    if _OS == "Windows":
        pyautogui.hotkey("win", "left")
    elif _OS == "Linux":
        try:
            subprocess.run(["wmctrl", "-r", ":ACTIVE:", "-e", "0,0,0,960,1080"],
                capture_output=True)
        except Exception:
            pass

def snap_right():
    if _OS == "Windows":
        pyautogui.hotkey("win", "right")
    elif _OS == "Linux":
        try:
            subprocess.run(["wmctrl", "-r", ":ACTIVE:", "-e", "0,960,0,960,1080"],
                capture_output=True)
        except Exception:
            pass

def switch_window():
    if _OS == "Darwin": pyautogui.hotkey("command", "tab")
    else:               pyautogui.hotkey("alt", "tab")

def show_desktop():
    if _OS == "Darwin":   pyautogui.hotkey("fn", "f11")
    elif _OS == "Windows": pyautogui.hotkey("win", "d")
    else:                  pyautogui.hotkey("super", "d")

def open_task_manager():
    if _OS == "Windows":
        pyautogui.hotkey("ctrl", "shift", "esc")
    elif _OS == "Darwin":
        subprocess.Popen(["open", "-a", "Activity Monitor"])
    else:
        for cmd in [["gnome-system-monitor"], ["xfce4-taskmanager"], ["htop"]]:
            if subprocess.run(["which", cmd[0]], capture_output=True).returncode == 0:
                subprocess.Popen(cmd)
                break


def focus_search():
    if _OS == "Darwin": pyautogui.hotkey("command", "l")
    else:               pyautogui.hotkey("ctrl", "l")

def pause_video():      pyautogui.press("space")

def refresh_page():
    if _OS == "Darwin": pyautogui.hotkey("command", "r")
    else:               pyautogui.press("f5")

def close_tab():
    if _OS == "Darwin": pyautogui.hotkey("command", "w")
    else:               pyautogui.hotkey("ctrl", "w")

def new_tab():
    if _OS == "Darwin": pyautogui.hotkey("command", "t")
    else:               pyautogui.hotkey("ctrl", "t")

def next_tab():
    if _OS == "Darwin": pyautogui.hotkey("command", "shift", "bracketright")
    else:               pyautogui.hotkey("ctrl", "tab")

def prev_tab():
    if _OS == "Darwin": pyautogui.hotkey("command", "shift", "bracketleft")
    else:               pyautogui.hotkey("ctrl", "shift", "tab")

def go_back():
    if _OS == "Darwin": pyautogui.hotkey("command", "left")
    else:               pyautogui.hotkey("alt", "left")

def go_forward():
    if _OS == "Darwin": pyautogui.hotkey("command", "right")
    else:               pyautogui.hotkey("alt", "right")

def zoom_in():
    if _OS == "Darwin": pyautogui.hotkey("command", "equal")
    else:               pyautogui.hotkey("ctrl", "equal")

def zoom_out():
    if _OS == "Darwin": pyautogui.hotkey("command", "minus")
    else:               pyautogui.hotkey("ctrl", "minus")

def zoom_reset():
    if _OS == "Darwin": pyautogui.hotkey("command", "0")
    else:               pyautogui.hotkey("ctrl", "0")

def find_on_page():
    if _OS == "Darwin": pyautogui.hotkey("command", "f")
    else:               pyautogui.hotkey("ctrl", "f")

def reload_page_n(n: int):
    for _ in range(max(1, n)):
        refresh_page()
        time.sleep(0.8)


def scroll_up(amount: int = 500):    pyautogui.scroll(amount)
def scroll_down(amount: int = 500):  pyautogui.scroll(-amount)

def scroll_top():
    if _OS == "Darwin": pyautogui.hotkey("command", "up")
    else:               pyautogui.hotkey("ctrl", "home")

def scroll_bottom():
    if _OS == "Darwin": pyautogui.hotkey("command", "down")
    else:               pyautogui.hotkey("ctrl", "end")

def page_up():   pyautogui.press("pageup")
def page_down(): pyautogui.press("pagedown")


def copy():
    if _OS == "Darwin": pyautogui.hotkey("command", "c")
    else:               pyautogui.hotkey("ctrl", "c")

def paste():
    if _OS == "Darwin": pyautogui.hotkey("command", "v")
    else:               pyautogui.hotkey("ctrl", "v")

def cut():
    if _OS == "Darwin": pyautogui.hotkey("command", "x")
    else:               pyautogui.hotkey("ctrl", "x")

def undo():
    if _OS == "Darwin": pyautogui.hotkey("command", "z")
    else:               pyautogui.hotkey("ctrl", "z")

def redo():
    if _OS == "Darwin": pyautogui.hotkey("command", "shift", "z")
    else:               pyautogui.hotkey("ctrl", "y")

def select_all():
    if _OS == "Darwin": pyautogui.hotkey("command", "a")
    else:               pyautogui.hotkey("ctrl", "a")

def save_file():
    if _OS == "Darwin": pyautogui.hotkey("command", "s")
    else:               pyautogui.hotkey("ctrl", "s")

def press_enter():   pyautogui.press("enter")
def press_escape():  pyautogui.press("escape")
def press_key(key: str): pyautogui.press(key)

def type_text(text: str, press_enter_after: bool = False):
    if not text:
        return
    if _PYPERCLIP:
        pyperclip.copy(str(text))
        time.sleep(0.15)
        paste()
    else:
        pyautogui.write(str(text), interval=0.03)
    if press_enter_after:
        time.sleep(0.1)
        pyautogui.press("enter")

def take_screenshot():
    if _OS == "Windows":
        pyautogui.hotkey("win", "shift", "s")
    elif _OS == "Darwin":
        pyautogui.hotkey("command", "shift", "3")
    else:
        for cmd in [["scrot"], ["gnome-screenshot"], ["import", "-window", "root", "screenshot.png"]]:
            if subprocess.run(["which", cmd[0]], capture_output=True).returncode == 0:
                subprocess.Popen(cmd)
                return
        pyautogui.hotkey("ctrl", "print_screen")

def lock_screen():
    if _OS == "Windows":
        pyautogui.hotkey("win", "l")
    elif _OS == "Darwin":
        subprocess.run(["pmset", "displaysleepnow"], capture_output=True)
    else:
        for cmd in [
            ["gnome-screensaver-command", "-l"],
            ["xdg-screensaver", "lock"],
            ["loginctl", "lock-session"],
        ]:
            if subprocess.run(["which", cmd[0]], capture_output=True).returncode == 0:
                subprocess.run(cmd, capture_output=True)
                return

def open_system_settings():
    if _OS == "Windows":
        pyautogui.hotkey("win", "i")
    elif _OS == "Darwin":
        subprocess.Popen(["open", "-a", "System Preferences"])
    else:
        for cmd in [["gnome-control-center"], ["xfce4-settings-manager"], ["kcmshell5"]]:
            if subprocess.run(["which", cmd[0]], capture_output=True).returncode == 0:
                subprocess.Popen(cmd)
                return

def open_terminal():
    if _OS == "Windows":
        pyautogui.hotkey("win", "r")
        time.sleep(0.3)
        pyautogui.write("cmd")
        pyautogui.press("enter")
    elif _OS == "Darwin":
        subprocess.Popen(["open", "-a", "Terminal"])
    else:
        for term in ["gnome-terminal", "konsole", "xfce4-terminal", "lxterminal", "xterm", "foot"]:
            if subprocess.run(["which", term], capture_output=True).returncode == 0:
                subprocess.Popen([term])
                return

def open_file_explorer():
    if _OS == "Windows":
        pyautogui.hotkey("win", "e")
    elif _OS == "Darwin":
        subprocess.Popen(["open", str(Path.home())])
    else:
        for cmd in [["nautilus"], ["thunar"], ["dolphin"], ["nemo"]]:
            if subprocess.run(["which", cmd[0]], capture_output=True).returncode == 0:
                subprocess.Popen(cmd)
                return
        subprocess.Popen(["xdg-open", str(Path.home())])

def sleep_display():
    if _OS == "Windows":
        try:
            import ctypes
            ctypes.windll.user32.SendMessageW(0xFFFF, 0x0112, 0xF170, 2)
        except Exception as e:
            print(f"[Settings] sleep_display failed: {e}")
    elif _OS == "Darwin":
        subprocess.run(["pmset", "displaysleepnow"], capture_output=True)
    else:
        subprocess.run(["xset", "dpms", "force", "off"], capture_output=True)

def open_run():
    if _OS == "Windows":
        pyautogui.hotkey("win", "r")

def dark_mode():
    if _OS == "Darwin":
        subprocess.run(["osascript", "-e",
            'tell app "System Events" to tell appearance preferences '
            'to set dark mode to not dark mode'],
            capture_output=True)
    elif _OS == "Windows":
        try:
            import winreg
            key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Themes\Personalize"
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS)
            current, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            winreg.SetValueEx(key, "AppsUseLightTheme", 0, winreg.REG_DWORD, 1 - current)
            winreg.SetValueEx(key, "SystemUsesLightTheme", 0, winreg.REG_DWORD, 1 - current)
            winreg.CloseKey(key)
        except Exception as e:
            print(f"[Settings] dark_mode registry failed: {e}")
    else:
        try:
            result = subprocess.run(
                ["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
                capture_output=True, text=True
            )
            current = result.stdout.strip()
            new_scheme = "'default'" if "dark" in current else "'prefer-dark'"
            subprocess.run(
                ["gsettings", "set", "org.gnome.desktop.interface", "color-scheme", new_scheme],
                capture_output=True
            )
        except Exception as e:
            print(f"[Settings] dark_mode Linux failed: {e}")

def toggle_wifi():
    if _OS == "Darwin":
        iface = _get_macos_wifi_interface()
        result = subprocess.run(
            ["networksetup", "-getairportpower", iface],
            capture_output=True, text=True
        )
        state = "off" if "On" in result.stdout else "on"
        subprocess.run(["networksetup", "-setairportpower", iface, state],
            capture_output=True)
    elif _OS == "Windows":
        try:
            subprocess.run(
                ["powershell", "-Command",
                 "$adapter = Get-NetAdapter | Where-Object {$_.PhysicalMediaType -eq 'Native 802.11'};"
                 "if ($adapter.Status -eq 'Up') { Disable-NetAdapter -Name $adapter.Name -Confirm:$false }"
                 "else { Enable-NetAdapter -Name $adapter.Name -Confirm:$false }"],
                capture_output=True, timeout=10
            )
        except Exception as e:
            print(f"[Settings] toggle_wifi Windows failed: {e}")
    else:
        try:
            result = subprocess.run(["nmcli", "radio", "wifi"], capture_output=True, text=True)
            state  = "off" if "enabled" in result.stdout else "on"
            subprocess.run(["nmcli", "radio", "wifi", state], capture_output=True)
        except Exception as e:
            print(f"[Settings] toggle_wifi Linux failed: {e}")

def notify(title: str = "Jarvis", message: str = "", urgency: str = "normal"):
    """Send a desktop notification."""
    if _OS == "Linux":
        try:
            subprocess.run(
                ["notify-send", "-a", "Jarvis", "-u", urgency, title, message],
                capture_output=True, timeout=5
            )
        except FileNotFoundError:
            # Fallback: try dbus directly
            try:
                import dbus
                bus = dbus.SessionBus()
                notifications = bus.get_object(
                    "org.freedesktop.Notifications",
                    "/org/freedesktop/Notifications"
                )
                interface = dbus.Interface(notifications, "org.freedesktop.Notifications")
                interface.Notify("Jarvis", 0, "", title, message, [], [], -1)
            except Exception:
                print(f"[Settings] notify failed: no notify-send or dbus")
    elif _OS == "Darwin":
        subprocess.run(
            ["osascript", "-e",
             f'display notification "{message}" with title "{title}"'],
            capture_output=True
        )
    elif _OS == "Windows":
        try:
            from win10toast import ToastNotifier
            ToastNotifier().show_toast(title, message, duration=5)
        except ImportError:
            print("[Settings] notify: install win10toast for Windows notifications")


def clipboard_read() -> str:
    """Read current clipboard contents."""
    if _PYPERCLIP:
        return pyperclip.paste()
    return "pyperclip not available for clipboard read"


def clipboard_write(text: str) -> str:
    """Write text to clipboard."""
    if _PYPERCLIP:
        pyperclip.copy(text)
        return f"Copied to clipboard: {text[:80]}"
    return "pyperclip not available for clipboard write"


def battery_status() -> str:
    """Get battery status and percentage."""
    if _OS == "Linux":
        try:
            result = subprocess.run(
                ["upower", "-i", "/org/freedesktop/UPower/devices/DisplayDevice"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                lines = result.stdout.splitlines()
                pct = "N/A"
                state = "N/A"
                for line in lines:
                    if "percentage" in line.lower():
                        pct = line.split(":", 1)[1].strip()
                    if "state" in line.lower():
                        state = line.split(":", 1)[1].strip()
                return f"Battery: {pct} ({state})"
            # Fallback: /sys/class/power_supply
            bats = sorted(Path("/sys/class/power_supply").glob("BAT*"))
            if bats:
                info = []
                for b in bats:
                    try:
                        cap = (b / "capacity").read_text().strip()
                        status = (b / "status").read_text().strip()
                        info.append(f"{b.name}: {cap}% ({status})")
                    except Exception:
                        pass
                if info:
                    return "Battery: " + ", ".join(info)
            return "Battery info not available (no upower or BAT*)"
        except Exception as e:
            return f"Battery check failed: {e}"
    elif _OS == "Darwin":
        try:
            result = subprocess.run(
                ["pmset", "-g", "batt"],
                capture_output=True, text=True, timeout=5
            )
            return result.stdout.strip() or "Battery info not available"
        except Exception as e:
            return f"Battery check failed: {e}"
    elif _OS == "Windows":
        try:
            import psutil
            batt = psutil.sensors_battery()
            if batt:
                pct = batt.percent
                plug = "plugged in" if batt.power_plugged else "on battery"
                return f"Battery: {pct}% ({plug})"
            return "No battery detected"
        except Exception:
            return "Battery info not available (install psutil)"
    return "Battery check not supported on this OS"


def wifi_status() -> str:
    """Get current WiFi status."""
    if _OS == "Linux":
        try:
            result = subprocess.run(
                ["nmcli", "-t", "-f", "TYPE,STATE,DEVICE", "device", "status"],
                capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.splitlines():
                if line.startswith("wifi:"):
                    state = line.split(":")[1]
                    if state == "connected":
                        conn = subprocess.run(
                            ["nmcli", "-t", "-f", "NAME", "connection", "show", "--active"],
                            capture_output=True, text=True, timeout=5
                        )
                        name = conn.stdout.strip().split("\n")[0] if conn.stdout else "unknown"
                        return f"WiFi: connected to {name}"
                    return "WiFi: disconnected"
            return "WiFi: disconnected"
        except FileNotFoundError:
            try:
                result = subprocess.run(
                    ["iwgetid"], capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    return f"WiFi: connected ({result.stdout.strip()})"
                return "WiFi: disconnected"
            except Exception:
                return "WiFi status: unknown (install nmcli or iwgetid)"
        except Exception as e:
            return f"WiFi status failed: {e}"
    elif _OS == "Darwin":
        iface = _get_macos_wifi_interface()
        try:
            result = subprocess.run(
                ["networksetup", "-getairportnetwork", iface],
                capture_output=True, text=True, timeout=5
            )
            return result.stdout.strip() or "WiFi: disconnected"
        except Exception as e:
            return f"WiFi status failed: {e}"
    elif _OS == "Windows":
        try:
            result = subprocess.run(
                ["netsh", "wlan", "show", "interfaces"],
                capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.splitlines():
                if "SSID" in line and "BSSID" not in line:
                    ssid = line.split(":", 1)[1].strip()
                    if ssid:
                        return f"WiFi: connected to {ssid}"
            return "WiFi: disconnected"
        except Exception as e:
            return f"WiFi status failed: {e}"
    return "WiFi status not supported on this OS"


def wifi_list() -> str:
    """List available WiFi networks."""
    if _OS == "Linux":
        try:
            result = subprocess.run(
                ["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY", "device", "wifi", "list"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode != 0 or not result.stdout.strip():
                return "No WiFi networks found or nmcli not available."
            lines = result.stdout.strip().split("\n")
            nets = []
            for line in lines:
                parts = line.split(":")
                if len(parts) >= 3 and parts[0]:
                    ssid = parts[0]
                    signal = parts[1] + "%"
                    sec = parts[2] if parts[2] else "open"
                    nets.append(f"  {ssid}  ({signal}, {sec})")
            if not nets:
                return "No WiFi networks found."
            return "Available WiFi networks:\n" + "\n".join(nets[:20])
        except FileNotFoundError:
            return "WiFi scanning requires nmcli (NetworkManager)."
        except Exception as e:
            return f"WiFi scan failed: {e}"
    elif _OS == "Darwin":
        try:
            result = subprocess.run(
                ["/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport", "-s"],
                capture_output=True, text=True, timeout=10
            )
            if result.stdout.strip():
                lines = result.stdout.strip().split("\n")[1:11]
                return "Available WiFi networks:\n" + "\n".join(f"  {l}" for l in lines)
            return "No WiFi networks found."
        except Exception as e:
            return f"WiFi scan failed: {e}"
    elif _OS == "Windows":
        try:
            result = subprocess.run(
                ["netsh", "wlan", "show", "networks"],
                capture_output=True, text=True, timeout=10
            )
            if result.stdout.strip():
                lines = result.stdout.strip().split("\n")
                nets = [l.strip() for l in lines if "SSID" in l or l.strip().startswith("SSID")]
                if not nets:
                    nets = [l.strip() for l in lines if l.strip() and not l.startswith(" ") and ":" not in l]
                return "Available WiFi networks:\n" + "\n".join(f"  {n}" for n in nets[:20])
            return "No WiFi networks found."
        except Exception as e:
            return f"WiFi scan failed: {e}"
    return "WiFi scanning not supported on this OS"


def restart_computer():
    if _OS == "Windows":
        subprocess.run(["shutdown", "/r", "/t", "10"], capture_output=True)
    elif _OS == "Darwin":
        subprocess.run(["osascript", "-e",
            'tell application "System Events" to restart'],
            capture_output=True)
    else:
        subprocess.run(["systemctl", "reboot"], capture_output=True)

def shutdown_computer():
    if _OS == "Windows":
        subprocess.run(["shutdown", "/s", "/t", "10"], capture_output=True)
    elif _OS == "Darwin":
        subprocess.run(["osascript", "-e",
            'tell application "System Events" to shut down'],
            capture_output=True)
    else:
        subprocess.run(["systemctl", "poweroff"], capture_output=True)

def check_webcam() -> str:
    try:
        import glob as _glob
        video_devs = _glob.glob("/dev/video*")
        if not video_devs:
            return "No webcam detected on this system."
        in_use = []
        for dev in video_devs:
            try:
                r = subprocess.run(["lsof", dev], capture_output=True, text=True, timeout=5)
                if r.stdout.strip():
                    for line in r.stdout.strip().split("\n")[1:]:
                        parts = line.split()
                        if len(parts) >= 1:
                            proc = parts[0]
                            in_use.append(f"{dev}: {proc}")
            except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
                pass
        if in_use:
            return f"Webcam is in use by:\n" + "\n".join(in_use)
        return "Webcam is not currently in use by any app."
    except Exception as e:
        return f"Could not check webcam status: {e}"

def generate_password(length: int = 16) -> str:
    """Generate a secure alphanumeric password and copy to clipboard."""
    import secrets as _secrets
    import string as _string
    chars = _string.ascii_letters + _string.digits
    pw = ''.join(_secrets.choice(chars) for _ in range(length))
    clipboard_write(pw)
    return f"{pw}"


def run_speedtest() -> str:
    """Run internet speed test (fast mode) and return ping, download, upload."""
    try:
        import speedtest
        st = speedtest.Speedtest()
        st.get_servers()
        st.get_best_server()
        ping = st.results.ping
        download = st.download(threads=2) / 1_000_000
        upload = st.upload(threads=2) / 1_000_000
        return (
            f"Ping: {ping:.0f} ms · "
            f"Download: {download:.1f} Mbps · "
            f"Upload: {upload:.1f} Mbps"
        )
    except Exception as e:
        return f"Speed test failed: {e}"

ACTION_MAP: dict[str, callable] = {
    "volume_up":           volume_up,
    "volume_down":         volume_down,
    "mute":                volume_mute,
    "unmute":              volume_mute,
    "toggle_mute":         volume_mute,
    "brightness_up":       brightness_up,
    "brightness_down":     brightness_down,
    "sleep_display":       sleep_display,
    "screen_off":          sleep_display,
    "pause_video":         pause_video,
    "play_pause":          pause_video,
    "close_app":           close_app,
    "close_window":        close_window,
    "full_screen":         full_screen,
    "fullscreen":          full_screen,
    "minimize":            minimize_window,
    "maximize":            maximize_window,
    "snap_left":           snap_left,
    "snap_right":          snap_right,
    "switch_window":       switch_window,
    "show_desktop":        show_desktop,
    "task_manager":        open_task_manager,
    "focus_search":        focus_search,
    "refresh_page":        refresh_page,
    "reload":              refresh_page,
    "close_tab":           close_tab,
    "new_tab":             new_tab,
    "next_tab":            next_tab,
    "prev_tab":            prev_tab,
    "go_back":             go_back,
    "go_forward":          go_forward,
    "zoom_in":             zoom_in,
    "zoom_out":            zoom_out,
    "zoom_reset":          zoom_reset,
    "find_on_page":        find_on_page,
    "scroll_up":           scroll_up,
    "scroll_down":         scroll_down,
    "scroll_top":          scroll_top,
    "scroll_bottom":       scroll_bottom,
    "page_up":             page_up,
    "page_down":           page_down,
    "copy":                copy,
    "paste":               paste,
    "cut":                 cut,
    "undo":                undo,
    "redo":                redo,
    "select_all":          select_all,
    "save":                save_file,
    "enter":               press_enter,
    "escape":              press_escape,
    "screenshot":          take_screenshot,
    "lock_screen":         lock_screen,
    "open_settings":       open_system_settings,
    "file_explorer":       open_file_explorer,
    "terminal":            open_terminal,
    "open_terminal":       open_terminal,
    "open_run":            open_run,
    "dark_mode":           dark_mode,
    "toggle_wifi":         toggle_wifi,
    "notify":              notify,
    "clipboard_read":      clipboard_read,
    "clipboard_write":     clipboard_write,
    "battery":             battery_status,
    "battery_status":      battery_status,
    "wifi_status":         wifi_status,
    "wifi_list":           wifi_list,
    "list_wifi":           wifi_list,
    "restart":             restart_computer,
    "shutdown":            shutdown_computer,
    "check_webcam":        check_webcam,
    "webcam":              check_webcam,
    "generate_password":   generate_password,
    "password":            generate_password,
    "random_data":         generate_password,
    "random_password":     generate_password,
    "speedtest":           run_speedtest,
    "speed_test":          run_speedtest,
    "internet_speed":      run_speedtest,
}

_DANGEROUS_ACTIONS = {"restart", "shutdown"}

_LANGUAGE_MAP = {
    "arabic": "ar", "العربية": "ar", "عربي": "ar",
    "german": "de", "deutsch": "de",
    "english": "en", "english us": "en", "english uk": "en",
    "spanish": "es", "español": "es",
    "persian": "fa", "farsi": "fa", "فارسی": "fa",
    "french": "fr", "français": "fr",
    "hindi": "hi", "हिन्दी": "hi",
    "indonesian": "id", "bahasa": "id",
    "italian": "it", "italiano": "it",
    "japanese": "ja", "日本語": "ja",
    "korean": "ko", "한국어": "ko",
    "dutch": "nl", "nederlands": "nl",
    "polish": "pl", "polski": "pl",
    "portuguese": "pt", "português": "pt",
    "romanian": "ro", "română": "ro",
    "russian": "ru", "русский": "ru",
    "thai": "th", "ไทย": "th",
    "turkish": "tr", "türkçe": "tr",
    "ukrainian": "uk", "українська": "uk",
    "urdu": "ur", "اردو": "ur",
    "vietnamese": "vi", "tiếng việt": "vi",
    "chinese": "zh", "中文": "zh", "mandarin": "zh",
}

_LANG_CODE_NAMES = {
    "ar": "Arabic", "de": "German", "en": "English", "es": "Spanish",
    "fa": "Persian", "fr": "French", "hi": "Hindi", "id": "Indonesian",
    "it": "Italian", "ja": "Japanese", "ko": "Korean", "nl": "Dutch",
    "pl": "Polish", "pt": "Portuguese", "ro": "Romanian", "ru": "Russian",
    "th": "Thai", "tr": "Turkish", "uk": "Ukrainian", "ur": "Urdu",
    "vi": "Vietnamese", "zh": "Chinese",
}


def _resolve_language(text: str) -> tuple[str | None, str | None]:
    """Resolve a language name/code to (iso_code, display_name)."""
    t = text.strip().lower().replace("_", " ").replace("-", " ")
    # Direct match
    if t in _LANGUAGE_MAP:
        code = _LANGUAGE_MAP[t]
        return code, _LANG_CODE_NAMES.get(code)
    # ISO code match
    if len(t) == 2 and t in _LANG_CODE_NAMES:
        return t, _LANG_CODE_NAMES[t]
    # Partial match
    for name, code in _LANGUAGE_MAP.items():
        if name in t or t in name:
            return code, _LANG_CODE_NAMES.get(code)
    return None, None


def _get_tts_voice_for_language(lang_code: str) -> str | None:
    """Get the best TTS voice for a language code based on current engine."""
    try:
        cfg_path = _get_base_dir() / "config" / "api_keys.json"
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception:
        cfg = {}
    engine = cfg.get("tts_engine", "edgetts").lower()
    if engine == "kokoro":
        try:
            from core.tts import LANG_TO_KOKORO_VOICE
            return LANG_TO_KOKORO_VOICE.get(lang_code)
        except Exception:
            return None
    else:
        try:
            from core.tts import LANG_TO_EDGETTS_VOICE
            return LANG_TO_EDGETTS_VOICE.get(lang_code)
        except Exception:
            return None


def _set_language_action(lang_name: str, lang_code: str, player=None) -> str:
    """Update config with the new language and TTS voice."""
    cfg_path = _get_base_dir() / "config" / "api_keys.json"
    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception:
        cfg = {}
    cfg["tts_language"] = lang_code
    voice = _get_tts_voice_for_language(lang_code)
    if voice:
        cfg["tts_voice"] = voice
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(json.dumps(cfg, indent=4), encoding="utf-8")
    display = _LANG_CODE_NAMES.get(lang_code, lang_code)
    if player and hasattr(player, "on_reconfigure") and player.on_reconfigure:
        try:
            player.on_reconfigure(cfg)
        except Exception as e:
            print(f"[Settings] Reconfigure after language change failed: {e}")
    return f"Language set to {display}. I will now speak {display}."



def _detect_action(description: str) -> dict:
    from core.llm_client import call_llm_text

    available = ", ".join(sorted(ACTION_MAP.keys())) + \
                ", volume_set, type_text, press_key, reload_n"

    system = (
        "You are an intent detector. Return ONLY a valid JSON object — "
        "no explanation, no markdown."
    )
    prompt = (
        f'User command (any language): "{description}"\n\n'
        f"Available actions: {available}\n\n"
        f'Return: {{"action": "action_name", "value": null_or_value}}\n'
        f"Rules: volume_set→int 0-100; type_text→exact text; press_key→key name; reload_n→int."
    )
    try:
        text = call_llm_text(prompt, system=system)
        text = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
        return json.loads(text)
    except Exception as e:
        print(f"[Settings] Intent detection failed: {e}")
        return {"action": description.lower().replace(" ", "_"), "value": None}

def computer_settings(
    parameters: dict = None,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    if not _PYAUTOGUI:
        return "pyautogui is not installed. Run: pip install pyautogui"

    params      = parameters or {}
    raw_action  = params.get("action", "").strip()
    description = params.get("description", "").strip()
    value       = params.get("value", None)

    if not raw_action and description:
        detected   = _detect_action(description)
        raw_action = detected.get("action", "")
        if value is None:
            value = detected.get("value")

    action = raw_action.lower().strip().replace(" ", "_").replace("-", "_")

    if not action:
        return "No action could be determined."

    # Mic mute detection — catches "mute the microphone" etc.
    desc_lower = (description or "").lower()
    if action == "mute" and any(w in desc_lower for w in ("microphone", " mic ")):
        action = "jarvis_mic"
    if action == "mute" and desc_lower.startswith("mute the microphone"):
        action = "jarvis_mic"

    print(f"[Settings] Action: {action}  Value: {value}  OS: {_OS}")
    if player:
        player.write_log(f"[Settings] {action}")

    if action in _DANGEROUS_ACTIONS:
        confirmed = str(params.get("confirmed", "")).lower()
        if confirmed not in ("yes", "true", "1", "confirm"):
            return (
                f"This will {action} the computer. "
                f"Please confirm by calling again with confirmed=yes."
            )

    if action == "volume_set":
        try:
            volume_set(int(value or 50))
            return f"Volume set to {value}%."
        except Exception as e:
            return f"Could not set volume: {e}"

    if action in ("type_text", "write_on_screen", "type", "write"):
        text = str(value or params.get("text", "")).strip()
        if not text:
            return "No text provided to type."
        enter_after = str(params.get("press_enter", "false")).lower() in ("true", "1", "yes")
        type_text(text, press_enter_after=enter_after)
        return f"Typed: {text[:80]}"

    if action == "press_key":
        key = str(value or params.get("key", "")).strip()
        if not key:
            return "No key specified."
        press_key(key)
        return f"Pressed: {key}"

    if action in ("reload_n", "refresh_n", "reload_page_n"):
        try:
            reload_page_n(int(value or 1))
            return f"Reloaded {value or 1} time(s)."
        except Exception as e:
            return f"Reload failed: {e}"

    if action == "scroll_up":
        scroll_up(int(value or 500))
        return "Scrolled up."

    if action == "scroll_down":
        scroll_down(int(value or 500))
        return "Scrolled down."

    if action in ("language", "change_language", "speak"):
        lang_text = value or description or raw_action
        lang_code, lang_name = _resolve_language(lang_text)
        if not lang_code:
            available = ", ".join(sorted(_LANG_CODE_NAMES.values()))
            return f"Unsupported language. Available: {available}"
        return _set_language_action(lang_name or lang_code, lang_code, player)

    if action == "notify":
        title = str(params.get("title", "Jarvis"))
        message = str(value or params.get("message", ""))
        urgency = str(params.get("urgency", "normal"))
        if not message:
            return "No notification message provided."
        notify(title, message, urgency)
        return f"Notification sent: {message[:80]}"

    if action == "clipboard_read":
        content = clipboard_read()
        return f"Clipboard: {content[:200]}"

    if action == "clipboard_write":
        text = str(value or params.get("text", "")).strip()
        if not text:
            return "No text provided to copy."
        clipboard_write(text)
        return f"Copied: {text[:80]}"

    if action == "battery_status":
        return battery_status()

    if action == "wifi_status":
        return wifi_status()

    if action == "jarvis_mic":
        if player and hasattr(player, '_win') and hasattr(player._win, '_toggle_mute'):
            try:
                player._win._toggle_mute()
            except Exception:
                pass
            muted = getattr(player._win, '_muted', False)
            return f"Microphone {'muted' if muted else 'unmuted'}."
        return "Mic control not available."

    if action in ("speedtest", "speed_test", "internet_speed"):
        if player:
            player.write_log("[Speedtest] Running…")
        return run_speedtest()

    if action in ("generate_password", "password", "random_data", "random_password"):
        length = int(value or params.get("length", 16))
        pw = generate_password(length)
        return f"Password generated and copied to clipboard: {pw}"

    func = ACTION_MAP.get(action)
    if not func:
        return f"Unknown action: '{raw_action}'."

    try:
        if action in ("volume_up", "volume_down") and value is not None:
            func(int(value))
        else:
            func()
        return f"Done: {action}."
    except Exception as e:
        print(f"[Settings] Action failed ({action}): {e}")
        return f"Action failed ({action}): {e}"