"""Device awareness — let Jarvis know everything plugged into the PC.

Detects connected devices (USB, Bluetooth, ADB, monitors) and answers with
natural, human-readable sentences instead of raw terminal output.

Multi-OS:
  - Linux:   lsusb / lsblk / udevadm / bluetoothctl / adb / xrandr
  - macOS:   system_profiler SPUSBDataType / ioreg / adb / system_profiler SPDisplaysDataType
  - Windows: Get-PnpDevice / Get-BluetoothDevice / adb / Get-CimInstance Win32_DesktopMonitor

Handlers:
  - list_devices(parameters, player)  -> overview of all connected devices
  - device_detail(parameters, player) -> detail about one specific category
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from typing import Any


def _run_cmd(cmd: list[str], timeout: float = 12.0) -> str:
    """Run a command safely and return stdout, or empty string on failure."""
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=None,
        )
        return (proc.stdout or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def _ps(cmd: str) -> str:
    """Run a shell command string (platform wrapper)."""
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=12.0,
            shell=True,
        )
        return (proc.stdout or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def _find_tool(names: list[str]) -> str | None:
    for name in names:
        if shutil.which(name):
            return name
    return None


def _os_kind() -> str:
    import platform

    return platform.system().lower()


# ── USB ──────────────────────────────────────────────────────────────────────

def _scan_usb() -> list[str]:
    """Return a short list of USB device descriptions."""
    kind = _os_kind()
    found: list[str] = []
    if kind == "linux":
        if _find_tool(["lsusb"]):
            for line in _ps("lsusb").splitlines():
                m = re.search(r"^\S+\s+\S+\s+(.+?)\s*$", line)
                if m:
                    found.append(m.group(1))
    elif kind == "darwin":
        out = _ps("system_profiler SPUSBDataType 2>/dev/null")
        for line in out.splitlines():
            m = re.match(r"\s{12}(\S[^:]{3,60}):\s*$", line)
            if m and "Class" not in m.group(1) and "Vendor" not in m.group(1):
                found.append(m.group(1).strip())
    elif kind == "windows":
        out = _ps(
            'powershell -NoProfile -Command '
            '"Get-PnpDevice -Class USB | Where-Object Status -eq OK | '
            'Select-Object -ExpandProperty FriendlyName | ConvertTo-Json"'
        )
        try:
            data = json.loads(out)
            if isinstance(data, list):
                found = [str(x) for x in data][:20]
            elif isinstance(data, str):
                found = [data]
        except Exception:  # noqa: BLE001
            pass
    # Fallback generic via OS block devices
    if not found:
        out = _ps("lsblk -dno NAME,MODEL 2>/dev/null")
        for line in out.splitlines():
            if line.strip():
                found.append(line.strip())
    return found


# ── Bluetooth ────────────────────────────────────────────────────────────────

def _scan_bluetooth() -> list[str]:
    kind = _os_kind()
    found: list[str] = []
    if kind == "linux":
        if _find_tool(["bluetoothctl"]):
            for line in _ps("bluetoothctl devices 2>/dev/null").splitlines():
                m = re.search(r"Device\s+[\w:]+\s+(.+?)$", line)
                if m:
                    found.append(m.group(1))
        if not found:
            # fallback: /dev/input / rfcomm / paired list
            for line in _ps("ls /dev/input/by-id/ 2>/dev/null").splitlines():
                if line.lower():
                    found.append(line)
    elif kind == "darwin":
        for line in _ps(
            "system_profiler SPBluetoothDataType 2>/dev/null"
        ).splitlines():
            m = re.match(r"\s{12}(\S[^:]{3,50}):\s*$", line)
            if m:
                found.append(m.group(1).strip())
    elif kind == "windows":
        out = _ps(
            'powershell -NoProfile -Command '
            '"Get-PnpDevice -Class Bluetooth | Where-Object Status -eq OK | '
            'Select-Object -ExpandProperty FriendlyName | ConvertTo-Json"'
        )
        try:
            data = json.loads(out)
            if isinstance(data, list):
                found = [str(x) for x in data][:20]
            elif isinstance(data, str):
                found = [data]
        except Exception:  # noqa: BLE001
            pass
    return found


# ── ADB ──────────────────────────────────────────────────────────────────────

def _scan_adb() -> list[str]:
    adb = _find_tool(["adb"])
    if not adb:
        return []
    out = _ps(f"{adb} devices")
    found: list[str] = []
    for line in out.splitlines():
        m = re.match(r"^(\S+)\s+device\s*$", line)
        if m and m.group(1) != "List":
            found.append(m.group(1))
    return found


# ── Monitors ─────────────────────────────────────────────────────────────────

def _scan_monitors() -> list[str]:
    kind = _os_kind()
    found: list[str] = []
    if kind == "linux":
        if _find_tool(["xrandr"]):
            out = _ps("xrandr --listmonitors 2>/dev/null")
            for line in out.splitlines():
                m = re.search(r"(\S+):\s+.*\s+(\d+x\d+)\s*$", line)
                if m:
                    found.append(f"{m.group(1)} ({m.group(2)})")
        if not found:
            out = _ps("xrandr 2>/dev/null | grep ' connected'")
            for line in out.splitlines():
                name = line.split(" ")[0]
                m = re.search(r"(\d+x\d+)\+", line)
                res = m.group(1) if m else "primary"
                found.append(f"{name} ({res})")
    elif kind == "darwin":
        out = _ps(
            "system_profiler SPDisplaysDataType 2>/dev/null | grep -Ei ' (main|display|monitor)' | head -10"
        )
        for line in out.splitlines():
            if line.strip():
                found.append(line.strip())
    elif kind == "windows":
        out = _ps(
            'powershell -NoProfile -Command '
            '"Get-CimInstance Win32_DesktopMonitor | '
            'Select-Object DeviceID | ConvertTo-Json"'
        )
        try:
            data = json.loads(out)
            items = data if isinstance(data, list) else ([data] if data else [])
            found = [str(x.get("DeviceID", x)) for x in items][:6]
        except Exception:  # noqa: BLE001
            out2 = _ps('powershell -NoProfile -Command "(Get-CimInstance Win32_DesktopMonitor).DeviceID"')
            if out2:
                found = out2.splitlines()
    return found


def _scan_storage() -> list[str]:
    """Basic block/disk devices (quick view)."""
    kind = _os_kind()
    found: list[str] = []
    if kind == "linux":
        for line in _ps("lsblk -dno NAME,SIZE,TYPE 2>/dev/null").splitlines():
            if line.strip():
                found.append(line.strip())
    elif kind == "darwin":
        for line in _ps("diskutil list 2>/dev/null | grep -E '^/dev/' ").splitlines():
            if line.strip():
                found.append(line.strip().split(" ")[0])
    elif kind == "windows":
        out = _ps(
            'powershell -NoProfile -Command '
            '"Get-Volume | Select-Object DriveLetter,FileSystemLabel,Size | '
            'Format-Table -AutoSize | Out-String -Width 200"'
        )
        found = [l.strip() for l in out.splitlines() if l.strip()]
    return found


def _describe() -> dict[str, list[str]]:
    return {
        "usb": _scan_usb(),
        "bluetooth": _scan_bluetooth(),
        "adb": _scan_adb(),
        "monitors": _scan_monitors(),
        "storage": _scan_storage(),
    }


def _human_summary(summary: dict[str, list[str]]) -> str:
    """Build a natural-language report from the scan results."""
    parts: list[str] = []

    def itemize(label: str, items: list[str]) -> None:
        if items:
            names = ", ".join(str(x) for x in items[:6])
            if len(items) > 6:
                names += f" and {len(items) - 6} more"
            parts.append(f"{label}: {names}")
        else:
            parts.append(f"{label}: none detected")

    itemize("USB devices", summary["usb"])
    itemize("Bluetooth devices", summary["bluetooth"])
    if summary["adb"]:
        parts.append("ADB devices: " + ", ".join(summary["adb"][:6]))
    else:
        parts.append("ADB devices: none (no ADB-connected phone/tablet)")
    itemize("Monitors", summary["monitors"])
    if summary["storage"]:
        parts.append("Storage drives: " + ", ".join(str(x) for x in summary["storage"][:6]))
    return " · ".join(parts)


# ── Public handlers ──────────────────────────────────────────────────────────

def list_devices(parameters: dict[str, Any], player: Any | None = None) -> str:
    """List everything plugged into / connected to the PC, natural answer."""
    summary = _describe()
    report = _human_summary(summary)
    # Save full JSON for later queries
    try:
        from pathlib import Path

        (Path(__file__).resolve().parent.parent / "config" / "device_scan.json").parent.mkdir(
            exist_ok=True
        )
        dest = Path(__file__).resolve().parent.parent / "config" / "device_scan.json"
        dest.parent.mkdir(exist_ok=True)
        with open(dest, "w") as fh:
            json.dump(summary, fh, indent=2)
    except Exception:  # noqa: BLE001
        pass
    return (
        f"Here is what I found connected to your PC. {report}"
        if report
        else "I could not detect any devices on this machine."
    )


def device_detail(parameters: dict[str, Any], player: Any | None = None) -> str:
    """Give detail about one specific category (usb / bluetooth / adb / monitors / storage)."""
    category = (parameters.get("category") or "usb").lower().strip()
    summary = _describe()
    mapping = {
        "usb": "USB devices",
        "bluetooth": "Bluetooth devices",
        "adb": "ADB devices",
        "monitors": "Monitors",
        "monitor": "Monitors",
        "screen": "Monitors",
        "display": "Monitors",
        "storage": "Storage drives",
        "disk": "Storage drives",
    }
    label = mapping.get(category, "USB devices")
    items = summary.get("usb" if category not in mapping else category)
    if category in ("monitors", "monitor", "screen", "display"):
        items = summary["monitors"]
    elif category in ("storage", "disk"):
        items = summary["storage"]
    elif category in ("adb",):
        items = summary["adb"]
    elif category in ("bluetooth",):
        items = summary["bluetooth"]
    else:
        items = summary["usb"]
    if items:
        names = ", ".join(str(x) for x in items[:10])
        return f"Your connected {label.lower()} are: {names}."
    return f"I did not find any {label.lower()} connected to this PC."
