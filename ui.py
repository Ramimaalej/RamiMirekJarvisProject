from __future__ import annotations

import asyncio
import json
import math
import os
import platform
import random
import subprocess
import sys
import threading
import time
from pathlib import Path

import psutil

from PyQt6.QtCore import (
    QEasingCurve, QMimeData, QObject, QPointF, QRectF, QSize, Qt,
    QTimer, QUrl, pyqtSignal,
)
from PyQt6.QtGui import (
    QBrush, QColor, QDragEnterEvent, QDropEvent, QFont, QFontDatabase,
    QKeySequence, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap,
    QRadialGradient, QShortcut,
)
from PyQt6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QFrame, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
    QMainWindow, QPushButton, QScrollArea, QSizePolicy, QSplitter, QStackedWidget, QTextEdit,
    QVBoxLayout, QWidget, QProgressBar, QGridLayout,
)
try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    _HAS_WEBENGINE = True
except ImportError:
    _HAS_WEBENGINE = False

from actions.timer_scheduler import list_timers
from core.llm_client import resolve_llm_url

def request_api_key(service_name: str, key_name: str = "") -> str:
    """Show a modal dialog asking for an API key. Saves to config if provided."""
    app = QApplication.instance()
    if not app:
        return ""
    parent = app.activeWindow()
    key_name = key_name or f"{service_name.lower().replace(' ', '_')}_api_key"
    result, ok = QInputDialog.getText(
        parent,
        f"API Key Required — {service_name}",
        f"{service_name} requires an API key.\nEnter your {service_name} API key:",
        QLineEdit.EchoMode.Password,
    )
    if ok and result.strip():
        from memory.config_manager import save_config
        save_config({key_name: result.strip()})
        return result.strip()
    return ""


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent

BASE_DIR   = _base_dir()

# ── Persistent asyncio event loop (avoids repeated asyncio.run() overhead) ──
_ASYNC_LOOP = asyncio.new_event_loop()
threading.Thread(target=_ASYNC_LOOP.run_forever, daemon=True, name="async-loop").start()

def _run_async(coro):
    """Schedule a coroutine on the persistent loop and block for the result."""
    fut = asyncio.run_coroutine_threadsafe(coro, _ASYNC_LOOP)
    return fut.result()


CONFIG_DIR = BASE_DIR / "config"
API_FILE   = CONFIG_DIR / "api_keys.json"

_DEFAULT_W, _DEFAULT_H = 1200, 780
_MIN_W,     _MIN_H     = 960, 620
_LEFT_W  = 185
_RIGHT_W = 360

_OS = platform.system()  # "Windows" | "Darwin" | "Linux"

_API_SERVICES = [
    ("OpenAI API",     "openai_api_key"),
    ("Google Gemini",  "gemini_api_key"),
    ("ElevenLabs TTS", "elevenlabs_api_key"),
    ("GWS (Gmail)",    "gws_credentials"),
    ("Plaid Finance",  "plaid_client_id"),
    ("GitHub API",     "github_access_token"),
    ("PostgreSQL DB",  "postgres_host"),
    ("Docker Daemon",  "docker_host"),
]


class C:
    BG        = "#0a0a0a"
    PANEL     = "#111111"
    PANEL2    = "#181818"
    BORDER    = "#1e1e1e"
    BORDER_B  = "#2a2a2a"
    BORDER_A  = "#252525"
    PRI       = "#eeeeee"
    PRI_DIM   = "#555555"
    PRI_GHO   = "#141414"
    ACC       = "#6c7bef"
    ACC_DIM   = "#353b6a"
    ACC_GHO   = "#1a1d3a"
    GREEN     = "#7ae07a"
    GREEN_D   = "#3a8a3a"
    RED       = "#e04444"
    MUTED_C   = "#555555"
    TEXT      = "#eeeeee"
    TEXT_DIM  = "#4a4a4a"
    TEXT_MED  = "#7a7a7a"
    WHITE     = "#eeeeee"
    DARK      = "#0a0a0a"
    BAR_BG    = "#151515"

    @classmethod
    def apply_theme(cls, light_mode: bool):
        if light_mode:
            cls.BG        = "#f8f9fa"
            cls.PANEL     = "#ffffff"
            cls.PANEL2    = "#f0f2f5"
            cls.BORDER    = "#e0e0e0"
            cls.BORDER_B  = "#d0d0d0"
            cls.BORDER_A  = "#cccccc"
            cls.PRI       = "#000000"
            cls.PRI_DIM   = "#888888"
            cls.PRI_GHO   = "#e0e0e0"
            cls.TEXT      = "#111111"
            cls.TEXT_DIM  = "#666666"
            cls.TEXT_MED  = "#444444"
            cls.BAR_BG    = "#e0e0e0"
        else:
            cls.BG        = "#000000"
            cls.PANEL     = "#0d0d0d"
            cls.PANEL2    = "#141414"
            cls.BORDER    = "#222222"
            cls.BORDER_B  = "#333333"
            cls.BORDER_A  = "#2a2a2a"
            cls.PRI       = "#ffffff"
            cls.PRI_DIM   = "#666666"
            cls.PRI_GHO   = "#111111"
            cls.TEXT      = "#ffffff"
            cls.TEXT_DIM  = "#555555"
            cls.TEXT_MED  = "#888888"
            cls.BAR_BG    = "#1a1a1a"

_FONT = "Cantarell"
_FONT_SZ = 12
_FONT_SZ_SM = 10
_FONT_SZ_XS = 9


def qcol(h: str, a: int = 255) -> QColor:
    c = QColor(h); c.setAlpha(a); return c

class _SysMetrics:
    def __init__(self):
        self.cpu  = 0.0
        self.mem  = 0.0
        self.net  = 0.0   
        self.gpu  = -1.0  
        self.tmp  = -1.0  
        self._lock = threading.Lock()
        self._last_net = psutil.net_io_counters()
        self._last_net_t = time.time()
        self._running = True
        t = threading.Thread(target=self._loop, daemon=True)
        t.start()

    def stop(self):
        self._running = False

    def _loop(self):
        while self._running:
            try:
                self._update()
            except Exception:
                pass
            time.sleep(1.5)

    def _update(self):
        cpu = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory().percent

        nc  = psutil.net_io_counters()
        now = time.time()
        dt  = now - self._last_net_t
        if dt > 0:
            sent = (nc.bytes_sent - self._last_net.bytes_sent) / dt
            recv = (nc.bytes_recv - self._last_net.bytes_recv) / dt
            net  = (sent + recv) / (1024 * 1024)
        else:
            net = 0.0
        self._last_net   = nc
        self._last_net_t = now

        gpu = self._get_gpu()

        tmp = self._get_temp()

        with self._lock:
            self.cpu = cpu
            self.mem = mem
            self.net = net
            self.gpu = gpu
            self.tmp = tmp

    def _get_gpu(self) -> float:
        # NVIDIA
        try:
            r = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=2
            )
            if r.returncode == 0:
                vals = [float(v.strip()) for v in r.stdout.strip().split("\n") if v.strip()]
                if vals:
                    return sum(vals) / len(vals)
        except Exception:
            pass

        # AMD (Linux) - rocm-smi
        if _OS == "Linux":
            try:
                r = subprocess.run(
                    ["rocm-smi", "--showuse", "--csv"],
                    capture_output=True, text=True, timeout=2
                )
                if r.returncode == 0:
                    for line in r.stdout.strip().split("\n"):
                        parts = line.split(",")
                        if len(parts) >= 2:
                            try:
                                return float(parts[1].strip().replace("%", ""))
                            except ValueError:
                                pass
            except Exception:
                pass

            # Intel GPU - intel_gpu_top
            try:
                r = subprocess.run(
                    ["intel_gpu_top", "-J", "-s", "500"],
                    capture_output=True, text=True, timeout=1
                )
                if r.returncode == 0 and "Render/3D" in r.stdout:
                    import re as _re2
                    m = _re2.search(r'"busy":\s*([\d.]+)', r.stdout)
                    if m:
                        return float(m.group(1))
            except Exception:
                pass

            # Sysfs fallback (no extra tools, no root required)
            # Per card priority:
            #   1) gpu_busy_percent  (amdgpu newer GPUs)
            #   2) Frequency ratio   (Intel i915 UHD - cur/max proxy)
            #   3) VRAM usage %      (AMD fallback when busy% unsupported)
            try:
                drm_root = "/sys/class/drm"
                cards = sorted(
                    c for c in os.listdir(drm_root)
                    if c.startswith("card") and "-" not in c
                )
                for card in cards:
                    base = f"{drm_root}/{card}"

                    # 1) gpu_busy_percent
                    bp = f"{base}/device/gpu_busy_percent"
                    if os.path.exists(bp):
                        try:
                            with open(bp) as fh:
                                return float(fh.read().strip())
                        except (ValueError, OSError):
                            pass

                    # 2) Intel i915 frequency ratio
                    for cur_p, max_p, min_p in [
                        (f"{base}/gt_act_freq_mhz",
                         f"{base}/gt_max_freq_mhz",
                         f"{base}/gt_min_freq_mhz"),
                        (f"{base}/gt/gt0/rps_cur_freq_mhz",
                         f"{base}/gt/gt0/rps_max_freq_mhz",
                         f"{base}/gt/gt0/rps_min_freq_mhz"),
                    ]:
                        if not os.path.exists(cur_p):
                            continue
                        try:
                            cur = float(open(cur_p).read().strip())
                            mx  = float(open(max_p).read().strip()) if os.path.exists(max_p) else cur
                            mn  = float(open(min_p).read().strip()) if os.path.exists(min_p) else 0.0
                            span = mx - mn
                            if span > 0:
                                return max(0.0, min(100.0, (cur - mn) / span * 100.0))
                        except (ValueError, OSError):
                            pass

                    # 3) AMD VRAM usage % (last-resort proxy)
                    tot_p = f"{base}/device/mem_info_vram_total"
                    use_p = f"{base}/device/mem_info_vram_used"
                    if os.path.exists(tot_p) and os.path.exists(use_p):
                        try:
                            tot = float(open(tot_p).read().strip())
                            use = float(open(use_p).read().strip())
                            if tot > 0:
                                return max(0.0, min(100.0, use / tot * 100.0))
                        except (ValueError, OSError):
                            pass
            except Exception:
                pass

        # macOS - powermetrics
        if _OS == "Darwin":
            try:
                r = subprocess.run(
                    ["sudo", "-n", "powermetrics", "-n", "1", "-i", "500",
                     "--samplers", "gpu_power"],
                    capture_output=True, text=True, timeout=2
                )
                if r.returncode == 0 and "GPU" in r.stdout:
                    import re as _re3
                    m = _re3.search(r'GPU\s+Active:\s+([\d.]+)%', r.stdout)
                    if m:
                        return float(m.group(1))
            except Exception:
                pass

        return -1.0

    def _get_temp(self) -> float:
        try:
            temps = psutil.sensors_temperatures()
            candidates = ["coretemp", "k10temp", "cpu_thermal", "acpitz",
                          "cpu-thermal", "zenpower", "it8688"]
            for name in candidates:
                if name in temps:
                    entries = temps[name]
                    if entries:
                        return entries[0].current
            for entries in temps.values():
                if entries:
                    return entries[0].current
        except Exception:
            pass
        if _OS == "Darwin":
            try:
                r = subprocess.run(
                    ["osx-cpu-temp"], capture_output=True, text=True, timeout=2
                )
                if r.returncode == 0:
                    import re
                    m = re.search(r"([\d.]+)", r.stdout)
                    if m:
                        return float(m.group(1))
            except Exception:
                pass

        if _OS == "Windows":
            try:
                r = subprocess.run(
                    ["powershell", "-Command",
                     "(Get-WmiObject MSAcpi_ThermalZoneTemperature -Namespace root/wmi).CurrentTemperature"],
                    capture_output=True, text=True, timeout=3
                )
                if r.returncode == 0 and r.stdout.strip():
                    raw = float(r.stdout.strip().split("\n")[0])
                    return (raw / 10.0) - 273.15
            except Exception:
                pass

        return -1.0

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "cpu": self.cpu,
                "mem": self.mem,
                "net": self.net,
                "gpu": self.gpu,
                "tmp": self.tmp,
            }


_metrics = _SysMetrics()

_BLUE      = "#00bfff"
_BLUE_LIGHT = "#66d9ff"
_BLUE_DIM  = "#006688"
_BLUE_GLOW = "#003344"
_CYAN      = "#00e5ff"

class HudCanvas(QWidget):
    clicked = pyqtSignal()

    def __init__(self, face_path: str, parent=None):
        self.muted    = False
        self.speaking = False
        self.state    = "INITIALISING"

        self._tick       = 0
        self._scale      = 1.0
        self._tgt_scale  = 1.0
        self._halo       = 55.0
        self._tgt_halo   = 55.0
        self._last_t     = time.time()
        self._scan       = 0.0
        self._scan2      = 180.0
        self._rings      = [0.0, 120.0, 240.0]
        self._pulses: list[float] = [0.0, 50.0, 100.0]
        self._blink      = True
        self._blink_tick = 0
        self._particles: list[list[float]] = []
        self._face_px: QPixmap | None = None

        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setMinimumSize(300, 300)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._load_face(face_path)

        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._step)
        self._tmr.start(16)

    def mousePressEvent(self, event):
        self.clicked.emit()
        super().mousePressEvent(event)

    def _load_face(self, path: str):
        try:
            from PIL import Image, ImageDraw
            import io
            img = Image.open(path).convert("RGBA")
            sz  = min(img.size)
            img = img.resize((sz, sz), Image.LANCZOS)
            mk  = Image.new("L", (sz, sz), 0)
            ImageDraw.Draw(mk).ellipse((2, 2, sz - 2, sz - 2), fill=255)
            img.putalpha(mk)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            px = QPixmap(); px.loadFromData(buf.getvalue())
            self._face_px = px
        except Exception:
            self._face_px = None

    def _step(self):
        self._tick += 1
        now = time.time()
        sp = 0.38 if self.speaking else 0.15
        if now - self._last_t > (0.08 if self.speaking else 0.3):
            if self.speaking:
                self._tgt_scale = random.uniform(1.06, 1.16)
                self._tgt_halo  = random.uniform(160, 210)
            elif self.muted:
                self._tgt_scale = random.uniform(0.998, 1.002)
                self._tgt_halo  = random.uniform(15, 28)
            else:
                self._tgt_scale = random.uniform(1.002, 1.012)
                self._tgt_halo  = random.uniform(55, 80)
            self._last_t = now

        self._scale += (self._tgt_scale - self._scale) * sp
        self._halo  += (self._tgt_halo  - self._halo)  * sp

        speeds = [1.8, -1.2, 2.5] if self.speaking else [0.7, -0.4, 1.1]
        for i, spd in enumerate(speeds):
            self._rings[i] = (self._rings[i] + spd) % 360

        self._scan  = (self._scan  + (4.0 if self.speaking else 1.5)) % 360
        self._scan2 = (self._scan2 + (-2.5 if self.speaking else -0.8)) % 360

        fw  = min(self.width(), self.height())
        lim = fw * 0.78
        spd = 5.0 if self.speaking else 2.5
        self._pulses = [r + spd for r in self._pulses if r + spd < lim]
        if len(self._pulses) < 4 and random.random() < (0.10 if self.speaking else 0.03):
            self._pulses.append(0.0)

        if random.random() < (0.35 if self.speaking else 0.05):
            cx, cy = self.width() / 2, self.height() / 2
            ang = random.uniform(0, 2 * math.pi)
            r_s = fw * 0.28
            self._particles.append([
                cx + math.cos(ang) * r_s, cy + math.sin(ang) * r_s,
                math.cos(ang) * random.uniform(1.0, 3.0),
                math.sin(ang) * random.uniform(1.0, 3.0) - 0.3, 1.0,
            ])
        self._particles = [
            [p[0]+p[2], p[1]+p[3], p[2]*0.97, p[3]*0.97, p[4]-0.022]
            for p in self._particles if p[4] > 0
        ]

        self._blink_tick += 1
        if self._blink_tick >= 30:
            self._blink = not self._blink
            self._blink_tick = 0
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), qcol("#000a0f"))

        W, H = self.width(), self.height()
        cx, cy = W / 2, H / 2
        fw = min(W, H)

        # subtle blue grid dots
        p.setPen(QPen(qcol(_BLUE_DIM, 50), 1))
        for x in range(0, W, 48):
            for y in range(0, H, 48):
                p.drawPoint(x, y)

        r_face = fw * 0.31

        # blue energy halo rings
        for i in range(8):
            r   = r_face * (1.8 - i * 0.08)
            frc = 1.0 - i / 8
            a   = max(0, min(255, int(self._halo * 0.09 * frc)))
            col = qcol(_BLUE if i % 2 == 0 else _BLUE_DIM, a)
            p.setPen(QPen(col, 1.5 - i * 0.12)); p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))

        # blue pulse rings
        for pr in self._pulses:
            a   = max(0, int(200 * (1.0 - pr / (fw * 0.78))))
            col = qcol(_CYAN, a)
            wd  = 2.0 if a > 100 else 1.0
            p.setPen(QPen(col, wd)); p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QRectF(cx - pr, cy - pr, pr * 2, pr * 2))

        # spinning arc rings — blue
        for idx, (r_frac, w_r, arc_l, gap) in enumerate(
            [(0.48, 3, 120, 75), (0.40, 2, 90, 50), (0.55, 1, 60, 90)]
        ):
            ring_r = fw * r_frac
            base   = self._rings[idx] if idx < 3 else 0
            a_val  = max(0, min(255, int(self._halo * (0.8 - idx * 0.12))))
            col    = qcol(_CYAN if idx == 0 else _BLUE, a_val)
            p.setPen(QPen(col, w_r)); p.setBrush(Qt.BrushStyle.NoBrush)
            angle = base
            rect  = QRectF(cx - ring_r, cy - ring_r, ring_r * 2, ring_r * 2)
            while angle < base + 360:
                p.drawArc(rect, int(angle * 16), int(arc_l * 16))
                angle += arc_l + gap

        # scanner with blue glow
        sr = fw * 0.50
        sa = min(255, int(self._halo * 1.5))
        ex = 70 if self.speaking else 45
        p.setPen(QPen(qcol(_BLUE_LIGHT, sa), 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        srect = QRectF(cx - sr, cy - sr, sr * 2, sr * 2)
        p.drawArc(srect, int(self._scan * 16), int(ex * 16))
        # scanner trail
        trail_a = max(0, sa - 120)
        p.setPen(QPen(qcol(_BLUE_DIM, trail_a), 1))
        p.drawArc(srect, int((self._scan - ex * 0.5) * 16), int(ex * 16))

        # tick marks — blue
        t_out, t_in = fw * 0.497, fw * 0.478
        for deg in range(0, 360, 15):
            active_sector = abs(deg - self._scan) < 60 or abs(deg - self._scan + 360) < 60
            a_val = 180 if active_sector else 60
            p.setPen(QPen(qcol(_BLUE_LIGHT if active_sector else _BLUE_DIM, a_val), 1))
            rad = math.radians(deg)
            inn = t_in if deg % 30 == 0 else t_in + 4
            p.drawLine(
                QPointF(cx + t_out * math.cos(rad), cy - t_out * math.sin(rad)),
                QPointF(cx + inn  * math.cos(rad), cy - inn  * math.sin(rad)),
            )

        # crosshair — blue
        ch_r, gap_h = fw * 0.51, fw * 0.18
        ha = int(self._halo * 0.5)
        p.setPen(QPen(qcol(_CYAN, ha), 1))
        p.drawLine(QPointF(cx - ch_r, cy), QPointF(cx - gap_h, cy))
        p.drawLine(QPointF(cx + gap_h, cy), QPointF(cx + ch_r, cy))
        p.drawLine(QPointF(cx, cy - ch_r), QPointF(cx, cy - gap_h))
        p.drawLine(QPointF(cx, cy + gap_h), QPointF(cx, cy + ch_r))
        # center dot
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(qcol(_CYAN, ha)))
        p.drawEllipse(QPointF(cx, cy), 2, 2)

        # corner brackets — blue
        bl = 22
        bc = qcol(_CYAN, 180)
        hl, hr = cx - fw // 2 + 4, cx + fw // 2 - 4
        ht, hb = cy - fw // 2 + 4, cy + fw // 2 - 4
        for bx, by, dx, dy in [(hl,ht,1,1),(hr,ht,-1,1),(hl,hb,1,-1),(hr,hb,-1,-1)]:
            p.setPen(QPen(bc, 2))
            p.drawLine(QPointF(bx, by), QPointF(bx + dx * bl, by))
            p.drawLine(QPointF(bx, by), QPointF(bx, by + dy * bl))
            # second parallel line
            p.setPen(QPen(qcol(_BLUE_DIM, 80), 1))
            p.drawLine(QPointF(bx + dx * 2, by + dy * 2), QPointF(bx + dx * (bl + 2), by + dy * 2))
            p.drawLine(QPointF(bx + dx * 2, by + dy * 2), QPointF(bx + dx * 2, by + dy * (bl + 2)))

        # face
        if self._face_px:
            fsz    = int(fw * 0.62 * self._scale)
            scaled = self._face_px.scaled(
                fsz, fsz,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            p.drawPixmap(int(cx - fsz / 2), int(cy - fsz / 2), scaled)
        else:
            orb_r = int(fw * 0.29 * self._scale)
            for i in range(8, 0, -1):
                r2  = int(orb_r * i / 8)
                frc = i / 8
                a   = max(0, min(255, int(self._halo * 0.8 * frc)))
                grad = QRadialGradient(cx, cy, r2)
                grad.setColorAt(0.0, qcol(_BLUE_LIGHT, a))
                grad.setColorAt(0.5, qcol(_BLUE, a))
                grad.setColorAt(1.0, qcol(_BLUE_DIM, 0))
                p.setBrush(QBrush(grad))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(QRectF(cx - r2, cy - r2, r2 * 2, r2 * 2))
            p.setPen(QPen(qcol(_CYAN, 220), 1))
            p.setFont(QFont("Courier New", 12, QFont.Weight.Bold))
            p.drawText(QRectF(cx - 90, cy - 16, 180, 32),
                       Qt.AlignmentFlag.AlignCenter, "J.A.R.V.I.S")

        # blue glow particles
        for pt in self._particles:
            a = max(0, min(255, int(pt[4] * 220)))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(qcol(_BLUE_LIGHT, a)))
            p.drawEllipse(QPointF(pt[0], pt[1]), 3, 3)
            if a > 100:
                p.setBrush(QBrush(qcol(_BLUE, a // 3)))
                p.drawEllipse(QPointF(pt[0], pt[1]), 6, 6)

        # status text — blue
        sy = cy + fw * 0.40
        if self.muted:
            txt = "◉  MUTED"
        elif self.speaking:
            txt = "◉  SPEAKING"
        elif self.state == "THINKING":
            sym = "◈" if self._blink else "◇"
            txt = f"{sym}  THINKING"
        elif self.state == "PROCESSING":
            sym = "▷" if self._blink else "▶"
            txt = f"{sym}  PROCESSING"
        elif self.state == "LISTENING":
            sym = "◉" if self._blink else "○"
            txt = f"{sym}  LISTENING"
        elif self.state == "ERROR":
            sym = "▲" if self._blink else "⚠"
            txt = f"{sym}  ERROR"
            p.setPen(QPen(qcol(C.RED), 1))
            p.setFont(QFont("Courier New", 11, QFont.Weight.Bold))
            p.drawText(QRectF(0, sy, W, 26), Qt.AlignmentFlag.AlignCenter, txt)
            # red waveform
            wy = sy + 30
            N, bw = 48, 5
            wx0 = (W - N * bw) / 2
            for i in range(N):
                hgt = int(2 + 3 * math.sin(self._tick * 0.15 + i * 0.8))
                cl  = qcol(C.RED, 120)
                p.fillRect(QRectF(wx0 + i * bw, wy + 18 - hgt, bw - 1, hgt), cl)
            return
        else:
            sym = "◉" if self._blink else "○"
            txt = f"{sym}  {self.state}"

        p.setPen(QPen(qcol(_BLUE_LIGHT), 1))
        p.setFont(QFont("Courier New", 11, QFont.Weight.Bold))
        p.drawText(QRectF(0, sy, W, 26), Qt.AlignmentFlag.AlignCenter, txt)

        # enhanced blue waveform
        wy = sy + 30
        N, bw = 48, 5
        gap = 2
        wx0 = (W - N * (bw + gap)) / 2
        for i in range(N):
            if self.muted:
                hgt, cl = 2, qcol(_BLUE_DIM, 80)
            elif self.speaking:
                hgt = random.randint(4, 24)
                if hgt > 14:
                    cl = qcol(_BLUE_LIGHT, 200)
                elif hgt > 8:
                    cl = qcol(_BLUE, 160)
                else:
                    cl = qcol(_BLUE_DIM, 100)
            else:
                phase = self._tick * 0.12 + i * 0.5
                hgt = int(4 + 4 * math.sin(phase))
                cl = qcol(_BLUE_DIM if hgt < 6 else _BLUE, 100)
            p.fillRect(QRectF(wx0 + i * (bw + gap), wy + 20 - hgt, bw, hgt), cl)

class MetricBar(QWidget):

    def __init__(self, label: str, color: str = C.PRI, parent=None):
        super().__init__(parent)
        self._label = label
        self._color = color
        self._value = 0.0       # 0–100
        self._text  = "--"
        self.setFixedHeight(44)
        self.setMinimumWidth(80)

    def set_value(self, pct: float, text: str):
        self._value = max(0.0, min(100.0, pct))
        self._text  = text
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()

        p.setBrush(QBrush(qcol(C.PANEL2)))
        p.setPen(QPen(qcol(C.BORDER), 1))
        p.drawRoundedRect(QRectF(1, 1, W - 2, H - 2), 6, 6)

        bar_h   = 4
        bar_y   = H - bar_h - 8
        bar_w   = W - 16
        bar_x   = 8
        fill_w  = int(bar_w * self._value / 100)

        p.setBrush(QBrush(qcol(C.BAR_BG)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(bar_x, bar_y, bar_w, bar_h), 2, 2)

        a = max(60, min(255, int(100 + self._value * 1.5)))
        bar_col = qcol(C.WHITE, a)

        if fill_w > 0:
            p.setBrush(QBrush(bar_col))
            p.drawRoundedRect(QRectF(bar_x, bar_y, fill_w, bar_h), 2, 2)

        p.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.TEXT_DIM), 1))
        p.drawText(QRectF(10, 6, 50, 16), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self._label)

        p.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.TEXT) if self._text != "--" else qcol(C.TEXT_DIM), 1))
        p.drawText(QRectF(0, 5, W - 10, 18), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, self._text)

class LogWidget(QTextEdit):
    _sig = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFont(QFont(_FONT, _FONT_SZ_SM))
        self.setStyleSheet(f"""
            QTextEdit {{
                background: {C.PANEL};
                color: {C.TEXT};
                border: 1px solid {C.BORDER};
                border-radius: 8px;
                padding: 10px;
                selection-background-color: {C.ACC_GHO};
                font-size: 13px;
                line-height: 1.5;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 5px;
                border: none;
                margin: 2px 0;
            }}
            QScrollBar::handle:vertical {{
                background: {C.BORDER};
                border-radius: 3px;
                min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {C.BORDER_B};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}
        """)
        self._queue: list[str] = []
        self._typing  = False
        self._text    = ""
        self._pos     = 0
        self._tag     = "sys"
        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._step)
        self._sig.connect(self._enqueue)

    def append_log(self, text: str):
        self._sig.emit(text)

    def append_instant(self, text: str, tag: str = "ai"):
        """Append text instantly without typing animation."""
        cur = self.textCursor()
        cur.movePosition(cur.MoveOperation.End)
        fmt = cur.charFormat()

        # Tag-based prefix + coloring
        prefix_map = {
            "you":  ("You",  qcol(C.WHITE)),
            "ai":   ("Jarvis", qcol(C.ACC)),
            "err":  ("Error", qcol(C.RED)),
            "file": ("File",  qcol(C.TEXT_MED)),
            "sys":  ("System", qcol(C.TEXT_DIM)),
        }
        prefix, col = prefix_map.get(tag, ("", qcol(C.TEXT)))

        fmt.setForeground(QBrush(qcol(C.TEXT_DIM)))
        fmt.setFont(QFont(_FONT, 8, QFont.Weight.Bold))
        cur.insertText(f"\n[{prefix}] ", fmt)

        fmt.setForeground(QBrush(col))
        fmt.setFont(QFont(_FONT, _FONT_SZ_SM))
        cur.insertText(text, fmt)
        self.setTextCursor(cur)
        self.ensureCursorVisible()

    def _enqueue(self, text: str):
        self._queue.append(text)
        if not self._typing:
            self._next()

    def _next(self):
        if not self._queue:
            self._typing = False
            return
        self._typing = True
        self._text   = self._queue.pop(0)
        self._pos    = 0
        tl = self._text.lower()
        if   tl.startswith("you:"):    self._tag = "you"
        elif tl.startswith("jarvis:"): self._tag = "ai"
        elif tl.startswith("file:"):   self._tag = "file"
        elif "err" in tl:              self._tag = "err"
        else:                          self._tag = "sys"
        self._tmr.start(8)

    def _step(self):
        if self._pos < len(self._text):
            ch  = self._text[self._pos]
            cur = self.textCursor()
            cur.movePosition(cur.MoveOperation.End)
            fmt = cur.charFormat()

            if self._pos == 0:
                # Insert tag prefix at start of line
                prefix_map = {
                    "you":  ("You",  qcol(C.WHITE)),
                    "ai":   ("Jarvis", qcol(C.ACC)),
                    "err":  ("Error", qcol(C.RED)),
                    "file": ("File",  qcol(C.TEXT_MED)),
                    "sys":  ("System", qcol(C.TEXT_DIM)),
                }
                prefix, _ = prefix_map.get(self._tag, ("", qcol(C.TEXT)))
                fmt.setForeground(QBrush(qcol(C.TEXT_DIM)))
                fmt.setFont(QFont(_FONT, 8, QFont.Weight.Bold))
                cur.insertText(f"\n[{prefix}] ", fmt)

            col = {
                "you":  qcol(C.WHITE),
                "ai":   qcol(C.PRI),
                "err":  qcol(C.RED),
                "file": qcol(C.TEXT_MED),
                "sys":  qcol(C.TEXT_DIM),
            }.get(self._tag, qcol(C.TEXT))
            fmt.setForeground(QBrush(col))
            fmt.setFont(QFont(_FONT, _FONT_SZ_SM))
            cur.insertText(ch, fmt)
            self.setTextCursor(cur)
            self.ensureCursorVisible()
            self._pos += 1
        else:
            self._tmr.stop()
            self.ensureCursorVisible()
            QTimer.singleShot(15, self._next)

_FILE_ICONS = {
    "image":   ("🖼", "#00d4ff"), "video":   ("🎬", "#ff6b00"),
    "audio":   ("🎵", "#cc44ff"), "pdf":     ("📄", "#ff4444"),
    "word":    ("📝", "#4488ff"), "excel":   ("📊", "#44bb44"),
    "code":    ("💻", "#ffcc00"), "archive": ("📦", "#ff8844"),
    "pptx":    ("📊", "#ff6622"), "text":    ("📃", "#aaaaaa"),
    "data":    ("🔧", "#88ddff"), "unknown": ("📎", "#888888"),
}
_EXT_TO_CAT = {
    **dict.fromkeys(["jpg","jpeg","png","gif","webp","bmp","tiff","svg","ico"], "image"),
    **dict.fromkeys(["mp4","avi","mov","mkv","wmv","flv","webm","m4v"],         "video"),
    **dict.fromkeys(["mp3","wav","ogg","m4a","aac","flac","wma","opus"],        "audio"),
    **dict.fromkeys(["pdf"],                                                     "pdf"),
    **dict.fromkeys(["doc","docx"],                                              "word"),
    **dict.fromkeys(["xls","xlsx","ods"],                                        "excel"),
    **dict.fromkeys(["ppt","pptx"],                                              "pptx"),
    **dict.fromkeys(["py","js","ts","jsx","tsx","html","css","java","c","cpp",
                     "cs","go","rs","rb","php","swift","kt","sh","sql","lua"],   "code"),
    **dict.fromkeys(["zip","rar","tar","gz","7z","bz2","xz"],                   "archive"),
    **dict.fromkeys(["txt","md","rst","log"],                                    "text"),
    **dict.fromkeys(["csv","tsv","json","xml"],                                  "data"),
}

def _file_category(path: Path) -> str:
    return _EXT_TO_CAT.get(path.suffix.lower().lstrip("."), "unknown")

def _fmt_size(size: int) -> str:
    if   size < 1024:    return f"{size} B"
    elif size < 1024**2: return f"{size/1024:.1f} KB"
    elif size < 1024**3: return f"{size/1024**2:.1f} MB"
    else:                return f"{size/1024**3:.1f} GB"


class FileDropZone(QWidget):
    file_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(100)
        self._current_file: str | None = None
        self._hovering  = False
        self._drag_over = False
        self._dash_offset = 0.0
        self._anim_tmr = QTimer(self)
        self._anim_tmr.timeout.connect(self._animate)
        self._anim_tmr.start(40)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._canvas = _DropCanvas(self)
        layout.addWidget(self._canvas)

    def _animate(self):
        self._dash_offset = (self._dash_offset + 0.8) % 20
        self._canvas.update()

    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self._drag_over = True; self._canvas.update()

    def dragLeaveEvent(self, e):
        self._drag_over = False; self._canvas.update()

    def dropEvent(self, e: QDropEvent):
        self._drag_over = False
        urls = e.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if Path(path).is_file():
                self._set_file(path)
        self._canvas.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._browse()

    def enterEvent(self, e):
        self._hovering = True; self._canvas.update()

    def leaveEvent(self, e):
        self._hovering = False; self._canvas.update()

    def current_file(self) -> str | None:
        return self._current_file

    def clear_file(self):
        self._current_file = None; self._canvas.update()

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select a file for JARVIS", str(Path.home()),
            "All Files (*.*);;"
            "Images (*.jpg *.jpeg *.png *.gif *.webp *.bmp *.svg);;"
            "Documents (*.pdf *.docx *.txt *.md *.pptx);;"
            "Data (*.csv *.xlsx *.json *.xml);;"
            "Code (*.py *.js *.ts *.html *.css *.java *.cpp *.go);;"
            "Audio (*.mp3 *.wav *.ogg *.m4a *.aac *.flac);;"
            "Video (*.mp4 *.avi *.mov *.mkv *.wmv *.webm);;"
            "Archives (*.zip *.rar *.tar *.gz *.7z)",
        )
        if path:
            self._set_file(path)

    def _set_file(self, path: str):
        self._current_file = path
        self._canvas.update()
        self.file_selected.emit(path)


class _DropCanvas(QWidget):
    def __init__(self, zone: FileDropZone):
        super().__init__(zone)
        self._z = zone

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        z    = self._z
        W, H = self.width(), self.height()
        pad  = 6
        rect = QRectF(pad, pad, W - pad * 2, H - pad * 2)

        bg_col = qcol("#001a24" if z._drag_over else ("#001218" if z._hovering else C.PANEL))
        p.setBrush(QBrush(bg_col)); p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(rect, 6, 6)

        if z._current_file:   border_col = qcol(C.TEXT_MED, 200)
        elif z._drag_over:    border_col = qcol(C.PRI, 230)
        elif z._hovering:     border_col = qcol(C.BORDER, 200)
        else:                 border_col = qcol(C.BORDER, 160)

        pen = QPen(border_col, 1.5, Qt.PenStyle.DashLine)
        pen.setDashOffset(z._dash_offset)
        p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rect, 6, 6)

        if z._current_file:   self._paint_file(p, W, H)
        elif z._drag_over:    self._paint_drag_over(p, W, H)
        else:                 self._paint_idle(p, W, H, z._hovering)

    def _paint_idle(self, p, W, H, hover):
        cx, cy = W / 2, H / 2
        col = qcol(C.PRI_DIM if not hover else C.PRI)
        p.setPen(QPen(col, 2)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(QPointF(cx, cy - 14), QPointF(cx, cy + 4))
        p.drawLine(QPointF(cx - 8, cy - 6), QPointF(cx, cy - 14))
        p.drawLine(QPointF(cx + 8, cy - 6), QPointF(cx, cy - 14))
        p.drawLine(QPointF(cx - 14, cy + 4), QPointF(cx + 14, cy + 4))
        p.setFont(QFont("Courier New", 8))
        p.setPen(QPen(qcol(C.PRI_DIM if not hover else C.TEXT), 1))
        p.drawText(QRectF(0, cy + 8, W, 16), Qt.AlignmentFlag.AlignCenter,
                   "Drop file here  or  Click to Browse")
        p.setFont(QFont("Courier New", 7))
        p.setPen(QPen(qcol("#1a4a5a"), 1))
        p.drawText(QRectF(0, cy + 24, W, 14), Qt.AlignmentFlag.AlignCenter,
                   "Images · Video · Audio · PDF · Docs · Code · Data")

    def _paint_drag_over(self, p, W, H):
        cx, cy = W / 2, H / 2
        p.setFont(QFont("Courier New", 20))
        p.setPen(QPen(qcol(C.PRI), 1))
        p.drawText(QRectF(0, cy - 24, W, 32), Qt.AlignmentFlag.AlignCenter, "⬇")
        p.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.PRI), 1))
        p.drawText(QRectF(0, cy + 12, W, 16), Qt.AlignmentFlag.AlignCenter, "Release to load")

    def _paint_file(self, p, W, H):
        path = Path(self._z._current_file)
        cat  = _file_category(path)
        icon, icon_col = _FILE_ICONS.get(cat, _FILE_ICONS["unknown"])
        size_str = _fmt_size(path.stat().st_size)
        ext_str  = path.suffix.upper().lstrip(".") or "FILE"

        block_x, block_w = 10, 60
        p.setFont(QFont("Segoe UI Emoji", 22) if _OS == "Windows" else QFont("Arial", 22))
        p.setPen(QPen(qcol(icon_col), 1))
        p.drawText(QRectF(block_x, 0, block_w, H), Qt.AlignmentFlag.AlignCenter, icon)

        tx = block_x + block_w + 6
        tw = W - tx - 38

        p.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.WHITE), 1))
        name = path.name if len(path.name) <= 34 else path.name[:31] + "..."
        p.drawText(QRectF(tx, H * 0.18, tw, 16),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, name)

        p.setFont(QFont("Courier New", 7))
        p.setPen(QPen(qcol(C.TEXT_DIM), 1))
        p.drawText(QRectF(tx, H * 0.18 + 18, tw, 14),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   f"{ext_str}  ·  {size_str}")

        p.setFont(QFont("Courier New", 6))
        p.setPen(QPen(qcol("#1e5c6a"), 1))
        par = str(path.parent)
        if len(par) > 42: par = "…" + par[-41:]
        p.drawText(QRectF(tx, H * 0.18 + 34, tw, 12),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, par)

        p.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.TEXT_DIM, 180), 1))
        p.drawText(QRectF(W - 34, 0, 28, H), Qt.AlignmentFlag.AlignCenter, "✕")

    def mousePressEvent(self, e):
        z = self._z
        if z._current_file and e.pos().x() > self.width() - 34:
            z.clear_file()
        else:
            z.mousePressEvent(e)


class SetupOverlay(QWidget):
    # Emits a JSON string containing the full config dict
    done = pyqtSignal(str)

    # ------------------------------------------------------------------ #
    _INPUT_STYLE = ""  # filled in __init__ after C is available

    def __init__(self, parent=None, initial: dict | None = None, mode: str = "init"):
        super().__init__(parent)
        self._mode = mode
        self._init = initial or {}
        _init = self._init
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            SetupOverlay {{
                background: rgba(0, 0, 0, 248);
                border: 1px solid {C.BORDER};
                border-radius: 6px;
            }}
        """)

        _INPUT = f"""
            QLineEdit {{
                background: {C.PANEL2}; color: {C.TEXT};
                border: 1px solid {C.BORDER}; border-radius: 4px; padding: 4px 8px;
                font-family: '{_FONT}'; font-size: 11pt;
            }}
            QLineEdit:focus {{ border: 1px solid {C.ACC}; }}
        """

        self._sel_stt          = _init.get("stt_engine",    "whisper")
        self._sel_tts          = _init.get("tts_engine",    "edgetts")
        self._sel_llm_provider = _init.get("llm_provider",  "ollama")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 16, 22, 16)
        layout.setSpacing(6)

        def _lbl(txt, sz=9, bold=False, col=C.PRI, align=Qt.AlignmentFlag.AlignCenter):
            w = QLabel(txt); w.setAlignment(align)
            w.setFont(QFont("Courier New", sz,
                            QFont.Weight.Bold if bold else QFont.Weight.Normal))
            w.setStyleSheet(f"color: {col}; background: transparent;")
            return w

        def _sep():
            s = QFrame(); s.setFrameShape(QFrame.Shape.HLine)
            s.setStyleSheet(f"color: {C.BORDER}; margin: 2px 0;")
            return s

        def _input(placeholder="", pw=False, fixed_h=32):
            w = QLineEdit()
            w.setPlaceholderText(placeholder)
            w.setFixedHeight(fixed_h)
            if pw:
                w.setEchoMode(QLineEdit.EchoMode.Password)
            w.setStyleSheet(_INPUT)
            return w

        def _toggle_row(keys_labels: list, getter, setter):
            row = QHBoxLayout(); row.setSpacing(5)
            btns: dict[str, QPushButton] = {}
            def _click(k):
                setter(k)
                for bk, b in btns.items():
                    _style_btn(b, bk == k)
            for k, lbl in keys_labels:
                b = QPushButton(lbl)
                b.setFixedHeight(26)
                b.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
                b.setCursor(Qt.CursorShape.PointingHandCursor)
                b.clicked.connect(lambda _, kk=k: _click(kk))
                row.addWidget(b)
                btns[k] = b
            _click(getter())
            return row, btns

        def _style_btn(btn: QPushButton, active: bool):
            if active:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {C.ACC}; color: {C.WHITE};
                        border: none; border-radius: 4px; font-weight: bold;
                        padding: 4px 10px;
                    }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: transparent; color: {C.TEXT_MED};
                        border: 1px solid {C.BORDER}; border-radius: 4px;
                        padding: 4px 10px;
                    }}
                    QPushButton:hover {{ color: {C.TEXT}; border: 1px solid {C.TEXT_MED}; }}
                """)

        # ── Header ──────────────────────────────────────────────────── #
        header_layout = QHBoxLayout()
        text_layout = QVBoxLayout()
        if mode == "config":
            text_layout.addWidget(_lbl("CONFIGURATION", 12, True, align=Qt.AlignmentFlag.AlignLeft))
            text_layout.addWidget(_lbl("Update J.A.R.V.I.S. settings and click Apply.", 8, col=C.PRI_DIM, align=Qt.AlignmentFlag.AlignLeft))
        else:
            text_layout.addWidget(_lbl("INITIALISATION REQUIRED", 12, True, align=Qt.AlignmentFlag.AlignLeft))
            text_layout.addWidget(_lbl("Configure J.A.R.V.I.S. before first boot.", 8, col=C.PRI_DIM, align=Qt.AlignmentFlag.AlignLeft))
        header_layout.addLayout(text_layout)
        
        self._theme_combo = QComboBox()
        self._theme_combo.setFixedHeight(26)
        self._theme_combo.addItem("Dark", userData="dark")
        self._theme_combo.addItem("Light", userData="light")
        _cur_theme = _init.get("theme", "dark")
        self._theme_combo.setCurrentIndex(1 if _cur_theme == "light" else 0)
        self._theme_combo.setStyleSheet(f"""
            QComboBox {{
                background: {C.PANEL2}; color: {C.TEXT};
                border: 1px solid {C.BORDER}; border-radius: 4px; padding: 2px 6px;
                font-family: '{_FONT}'; font-size: 9pt;
            }}
            QComboBox::drop-down {{ border: none; width: 16px; }}
        """)
        header_layout.addWidget(self._theme_combo, alignment=Qt.AlignmentFlag.AlignRight)
        layout.addLayout(header_layout)
        
        layout.addWidget(_sep())

        # ── STT ──────────────────────────────────────────────────────── #
        layout.addWidget(_lbl("SPEECH-TO-TEXT ENGINE", 7, col=C.TEXT_DIM,
                               align=Qt.AlignmentFlag.AlignLeft))
        stt_row, self._stt_btns = _toggle_row(
            [("whisper","Whisper"), ("vosk","Vosk")],
            lambda: self._sel_stt,
            self._set_stt,
        )
        layout.addLayout(stt_row)

        _COMBO_STYLE = f"""
            QComboBox {{
                background: {C.PANEL2}; color: {C.TEXT};
                border: 1px solid {C.BORDER}; border-radius: 4px; padding: 4px 8px;
                font-family: '{_FONT}'; font-size: 10pt;
            }}
            QComboBox:focus {{ border: 1px solid {C.ACC}; }}
            QComboBox::drop-down {{ border: none; width: 20px; }}
            QComboBox QAbstractItemView {{
                background: {C.PANEL2}; color: {C.TEXT};
                border: 1px solid {C.BORDER};
                selection-background-color: {C.ACC_GHO};
                font-family: '{_FONT}'; font-size: 10pt;
            }}
        """

        stt_detail = QHBoxLayout(); stt_detail.setSpacing(5)
        stt_detail.addWidget(_lbl("Model:", 7, col=C.TEXT_MED,
                                   align=Qt.AlignmentFlag.AlignRight))

        # Whisper: dropdown with predefined sizes
        self._whisper_combo = QComboBox()
        self._whisper_combo.setFixedHeight(28)
        self._whisper_combo.setStyleSheet(_COMBO_STYLE)
        for m in ["tiny", "base", "small", "medium", "large-v3"]:
            self._whisper_combo.addItem(m)
        _cur_model = _init.get("stt_model", "base")
        _idx = self._whisper_combo.findText(_cur_model)
        self._whisper_combo.setCurrentIndex(_idx if _idx >= 0 else 1)
        stt_detail.addWidget(self._whisper_combo)

        # Vosk: free-text path input
        self._vosk_model_input = _input("model dir path  (leave empty for auto-download)")
        self._vosk_model_input.setText(_init.get("vosk_model_path", ""))
        stt_detail.addWidget(self._vosk_model_input)

        layout.addLayout(stt_detail)

        # Initial visibility
        self._whisper_combo.setVisible(self._sel_stt == "whisper")
        self._vosk_model_input.setVisible(self._sel_stt == "vosk")

        stt_lang_row = QHBoxLayout(); stt_lang_row.setSpacing(5)
        stt_lang_row.addWidget(_lbl("Language:", 7, col=C.TEXT_MED,
                                    align=Qt.AlignmentFlag.AlignRight))
        self._stt_lang_input = _input("auto  (or: tr / en / de / fr / es / zh …)")
        self._stt_lang_input.setText(_init.get("stt_language", "auto"))
        stt_lang_row.addWidget(self._stt_lang_input)
        layout.addLayout(stt_lang_row)
        layout.addWidget(_sep())

        # ── TTS ──────────────────────────────────────────────────────── #
        layout.addWidget(_lbl("TEXT-TO-SPEECH ENGINE", 7, col=C.TEXT_DIM,
                               align=Qt.AlignmentFlag.AlignLeft))
        tts_row, self._tts_btns = _toggle_row(
            [("edgetts","EdgeTTS"), ("kokoro","Kokoro"), ("elevenlabs","ElevenLabs")],
            lambda: self._sel_tts,
            self._set_tts,
        )
        layout.addLayout(tts_row)

        voice_row = QHBoxLayout(); voice_row.setSpacing(5)
        self._voice_lbl = QLabel("Voice:")
        self._voice_lbl.setFont(QFont("Courier New", 7))
        self._voice_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._voice_lbl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
        voice_row.addWidget(self._voice_lbl)

        self._tts_voice_input = _input("en-US-GuyNeural")
        self._tts_voice_input.setText(_init.get("tts_voice", "en-US-GuyNeural"))
        voice_row.addWidget(self._tts_voice_input)

        # Kokoro: dropdown with predefined voices (hidden unless Kokoro selected)
        self._kokoro_combo = QComboBox()
        self._kokoro_combo.setFixedHeight(28)
        self._kokoro_combo.setStyleSheet(_COMBO_STYLE)
        _KOKORO_VOICES = [
            ("af_heart",    "af_heart  — EN-F warm (recommended)"),
            ("af_sky",      "af_sky  — EN-F clear"),
            ("af_bella",    "af_bella  — EN-F bella"),
            ("af_sarah",    "af_sarah  — EN-F sarah"),
            ("am_adam",     "am_adam  — EN-M adam"),
            ("am_michael",  "am_michael  — EN-M michael"),
            ("bf_emma",     "bf_emma  — UK-F emma"),
            ("bf_isabella", "bf_isabella  — UK-F isabella"),
            ("bm_george",   "bm_george  — UK-M george"),
            ("bm_lewis",    "bm_lewis  — UK-M lewis"),
            ("jf_alpha",    "jf_alpha  — Japanese Female"),
            ("jm_kumo",     "jm_kumo  — Japanese Male"),
        ]
        for val, display in _KOKORO_VOICES:
            self._kokoro_combo.addItem(display, userData=val)
        _cur_voice = _init.get("tts_voice", "af_heart")
        for i in range(self._kokoro_combo.count()):
            if self._kokoro_combo.itemData(i) == _cur_voice:
                self._kokoro_combo.setCurrentIndex(i)
                break
        self._kokoro_combo.setVisible(False)  # shown only when Kokoro active
        voice_row.addWidget(self._kokoro_combo)

        layout.addLayout(voice_row)

        # Kokoro speed — only visible when Kokoro is selected
        self._kokoro_speed_widget = QWidget()
        self._kokoro_speed_widget.setStyleSheet("background: transparent;")
        ks_row = QHBoxLayout(self._kokoro_speed_widget)
        ks_row.setContentsMargins(0, 0, 0, 0)
        ks_row.setSpacing(5)
        ks_row.addWidget(_lbl("Speed:", 7, col=C.TEXT_MED,
                               align=Qt.AlignmentFlag.AlignRight))
        self._kokoro_speed_combo = QComboBox()
        self._kokoro_speed_combo.setFixedHeight(28)
        self._kokoro_speed_combo.setStyleSheet(_COMBO_STYLE)
        for val, label in [
            ("0.8",  "0.8×  — Slow"),
            ("1.0",  "1.0×  — Normal"),
            ("1.1",  "1.1×  — Slightly fast"),
            ("1.2",  "1.2×  — Fast (recommended)"),
            ("1.3",  "1.3×  — Faster"),
            ("1.5",  "1.5×  — Very fast"),
        ]:
            self._kokoro_speed_combo.addItem(label, userData=val)
        _cur_speed = str(_init.get("tts_speed", "1.2"))
        for i in range(self._kokoro_speed_combo.count()):
            if self._kokoro_speed_combo.itemData(i) == _cur_speed:
                self._kokoro_speed_combo.setCurrentIndex(i)
                break
        ks_row.addWidget(self._kokoro_speed_combo)
        layout.addWidget(self._kokoro_speed_widget)

        # ElevenLabs key input moved to Providers Overlay

        layout.addWidget(_sep())

        # Set correct initial state for TTS UI
        self._update_tts_ui(self._sel_tts)

        # ── Action buttons ─────────────────────────────────────────────── #
        btn_row = QHBoxLayout(); btn_row.setSpacing(8)

        if mode == "config":
            cancel_btn = QPushButton("Cancel")
            cancel_btn.setFont(QFont(_FONT, 10))
            cancel_btn.setFixedHeight(36)
            cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            cancel_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {C.TEXT_MED};
                    border: 1px solid {C.BORDER}; border-radius: 6px;
                    padding: 4px 16px;
                }}
                QPushButton:hover {{
                    color: {C.TEXT}; border: 1px solid {C.TEXT_MED};
                }}
            """)
            cancel_btn.clicked.connect(self.hide)
            btn_row.addWidget(cancel_btn)

        btn_label = "Apply Changes" if mode == "config" else "Initialise Systems"
        init_btn = QPushButton(btn_label)
        init_btn.setFont(QFont(_FONT, 11, QFont.Weight.Bold))
        init_btn.setFixedHeight(36)
        init_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        init_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.ACC}; color: {C.WHITE};
                border: none; border-radius: 6px;
                padding: 4px 16px;
            }}
            QPushButton:hover {{
                background: {C.ACC_DIM};
            }}
        """)
        init_btn.clicked.connect(self._submit)
        btn_row.addWidget(init_btn)
        layout.addLayout(btn_row)

    # ------------------------------------------------------------------ #
    def _update_tts_ui(self, key: str) -> None:
        """Show/hide and relabel TTS fields based on selected engine."""
        if not hasattr(self, "_voice_lbl"):
            return

        is_kokoro = (key == "kokoro")

        # Kokoro uses a dropdown; other engines use a text input
        if hasattr(self, "_tts_voice_input"):
            self._tts_voice_input.setVisible(not is_kokoro)
        if hasattr(self, "_kokoro_combo"):
            self._kokoro_combo.setVisible(is_kokoro)

        if key == "elevenlabs":
            self._voice_lbl.setText("Voice ID:")
            if hasattr(self, "_tts_voice_input"):
                self._tts_voice_input.setPlaceholderText("ElevenLabs voice ID")
        elif key == "kokoro":
            self._voice_lbl.setText("Voice:")
        else:  # edgetts
            self._voice_lbl.setText("Voice:")
            if hasattr(self, "_tts_voice_input"):
                self._tts_voice_input.setPlaceholderText(
                    "en-US-GuyNeural  /  en-GB-RyanNeural  /  tr-TR-AhmetNeural  …"
                )

        if hasattr(self, "_kokoro_speed_widget"):
            self._kokoro_speed_widget.setVisible(is_kokoro)

    def _set_llm_provider(self, key: str):
        self._sel_llm_provider = key

    def _set_stt(self, key: str):
        self._sel_stt = key
        if not hasattr(self, "_stt_btns"):
            return
        for k, btn in self._stt_btns.items():
            active = (k == key)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {'transparent' if not active else C.PANEL2};
                    color: {C.TEXT if active else C.TEXT_DIM};
                    border: {f'1px solid {C.TEXT_MED}' if active else f'1px solid {C.BORDER}'};
                    border-radius: 3px;
                }}
                QPushButton:hover {{ color: {C.TEXT}; border: 1px solid {C.TEXT_DIM}; }}
            """)
        # Toggle model selector widgets
        if hasattr(self, "_whisper_combo"):
            self._whisper_combo.setVisible(key == "whisper")
        if hasattr(self, "_vosk_model_input"):
            self._vosk_model_input.setVisible(key == "vosk")

    def _set_tts(self, key: str):
        self._sel_tts = key
        if not hasattr(self, "_tts_btns"):
            return
        for k, btn in self._tts_btns.items():
            active = (k == key)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {'transparent' if not active else C.PANEL2};
                    color: {C.TEXT if active else C.TEXT_DIM};
                    border: {f'1px solid {C.TEXT_MED}' if active else f'1px solid {C.BORDER}'};
                    border-radius: 3px;
                }}
                QPushButton:hover {{ color: {C.TEXT}; border: 1px solid {C.TEXT_DIM}; }}
            """)
        self._update_tts_ui(key)

    def _test_connection(self):
        pass

    def _submit(self):
        # STT model: combo for Whisper, text input for Vosk
        if self._sel_stt == "whisper":
            stt_model = self._whisper_combo.currentText()
        else:
            stt_model = self._vosk_model_input.text().strip()

        # Voice: Kokoro uses dropdown, others use text input
        if self._sel_tts == "kokoro":
            tts_voice = self._kokoro_combo.currentData() or "af_heart"
            tts_speed = self._kokoro_speed_combo.currentData() or "1.2"
        else:
            tts_voice = self._tts_voice_input.text().strip() or "en-US-GuyNeural"
            tts_speed = "1.0"
        
        cfg = dict(self._init)
        cfg.update({
            "theme":              self._theme_combo.currentData(),
            "stt_engine":         self._sel_stt,
            "stt_model":          stt_model,
            "stt_language":       self._stt_lang_input.text().strip() or "auto",
            "tts_engine":         self._sel_tts,
            "tts_voice":          tts_voice,
            "tts_speed":          tts_speed,
        })
        if self._sel_stt == "vosk" and stt_model:
            cfg["vosk_model_path"] = stt_model
            
        # Update current theme immediately if changed
        if cfg["theme"] != self._init.get("theme"):
            C.apply_theme(cfg["theme"] == "light")
            
        self.done.emit(json.dumps(cfg))


class ConnectionsOverlay(QWidget):
    done = pyqtSignal(str)
    _auth_result_sig = pyqtSignal(bool, str)  # success, msg — emitted from background auth thread

    def __init__(self, parent=None, initial: dict | None = None, active_tab_key: str | None = None):
        super().__init__(parent)
        self._init = initial or {}
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        
        bg_color = "rgba(240, 242, 245, 245)" if C.BG.lower() in ("#ffffff", "#f8f9fa") else "rgba(10, 10, 10, 245)"
        self.setStyleSheet(f"""
            ConnectionsOverlay {{
                background: {bg_color};
                border: 1px solid {C.BORDER};
                border-radius: 8px;
            }}
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 14, 18, 14)
        main_layout.setSpacing(12)

        # Header Row
        header_lay = QHBoxLayout()
        title_lbl = QLabel("CONNECTION CENTER")
        title_lbl.setFont(QFont(_FONT, 12, QFont.Weight.Bold))
        title_lbl.setStyleSheet(f"color: {C.TEXT}; background: transparent; border: none;")
        desc_lbl = QLabel("Manage AI credentials, databases, local APIs, and workspace tokens")
        desc_lbl.setFont(QFont(_FONT, 8))
        desc_lbl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent; border: none;")
        
        header_lay.addWidget(title_lbl)
        header_lay.addSpacing(10)
        header_lay.addWidget(desc_lbl)
        header_lay.addStretch()
        main_layout.addLayout(header_lay)

        # Content horizontal layout (Sidebar + Stack)
        content_lay = QHBoxLayout()
        content_lay.setSpacing(16)
        
        # Sidebar widget
        sidebar = QWidget()
        sidebar.setFixedWidth(190)
        sidebar.setStyleSheet("background: transparent; border: none;")
        sidebar_lay = QVBoxLayout(sidebar)
        sidebar_lay.setContentsMargins(0, 0, 0, 0)
        sidebar_lay.setSpacing(6)

        self.stack = QStackedWidget()
        self.inputs = {}

        def _card(title: str, fields: list[tuple[str, str, bool, str]], check_keys: list[str]) -> QWidget:
            card = QWidget()
            card.setStyleSheet(f"""
                QWidget {{
                    background: {C.PANEL2};
                    border: 1px solid {C.BORDER};
                    border-radius: 6px;
                }}
            """)
            card_lay = QVBoxLayout(card)
            card_lay.setContentsMargins(12, 10, 12, 10)
            card_lay.setSpacing(6)

            header = QWidget()
            header.setStyleSheet("background: transparent; border: none;")
            h_lay = QHBoxLayout(header)
            h_lay.setContentsMargins(0, 0, 0, 0)
            h_lay.setSpacing(6)

            dot = QLabel("●")
            dot.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
            
            lbl = QLabel(title)
            lbl.setFont(QFont(_FONT, 9, QFont.Weight.Bold))
            lbl.setStyleSheet(f"color: {C.TEXT}; background: transparent; border: none;")

            status_lbl = QLabel("Disconnected")
            status_lbl.setFont(QFont("Courier New", 7))
            
            h_lay.addWidget(dot)
            h_lay.addWidget(lbl)
            h_lay.addStretch()
            h_lay.addWidget(status_lbl)
            card_lay.addWidget(header)

            form = QWidget()
            form.setStyleSheet("background: transparent; border: none;")
            form_lay = QGridLayout(form)
            form_lay.setContentsMargins(0, 4, 0, 0)
            form_lay.setSpacing(6)

            card_inputs = []
            for idx, (f_label, f_key, is_pw, desc) in enumerate(fields):
                f_lbl = QLabel(f_label)
                f_lbl.setFont(QFont(_FONT, 8))
                f_lbl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent; border: none;")
                
                inp = QLineEdit()
                inp.setPlaceholderText(desc)
                inp.setFixedHeight(26)
                if is_pw:
                    inp.setEchoMode(QLineEdit.EchoMode.Password)
                inp.setStyleSheet(f"""
                    QLineEdit {{
                        background: {C.PANEL}; color: {C.TEXT};
                        border: 1px solid {C.BORDER}; border-radius: 4px; padding: 4px 8px;
                        font-family: '{_FONT}'; font-size: 9pt;
                    }}
                    QLineEdit:focus {{ border: 1px solid {C.ACC}; }}
                """)
                val = self._init.get(f_key, "")
                if not val and f_key == "llm_url_local":
                    val = self._init.get("ollama_url", "http://localhost:11434")
                inp.setText(val)
                
                form_lay.addWidget(f_lbl, idx, 0)
                form_lay.addWidget(inp, idx, 1)
                
                self.inputs[f_key] = inp
                card_inputs.append((f_key, inp))

            card_lay.addWidget(form)

            def update_status():
                is_set = True
                for ck in check_keys:
                    val = self.inputs[ck].text().strip()
                    if ck == "gws_credentials":
                        from pathlib import Path
                        path_to_check = Path(val) if val else (CONFIG_DIR.parent / "gws" / "credentials.json")
                        if not path_to_check.exists():
                            is_set = False
                            break
                    elif not val:
                        is_set = False
                        break
                
                col = C.GREEN if is_set else C.RED
                dot.setStyleSheet(f"color: {col}; background: transparent; border: none;")
                status_lbl.setText("Connected" if is_set else "Disconnected")
                status_lbl.setStyleSheet(f"color: {col}; background: transparent; border: none;")

            for _, inp in card_inputs:
                inp.textChanged.connect(update_status)
            
            update_status()
            return card

        categories = [
            ("🤖 AI Engines", 0),
            ("🎙️ Voice & Media", 1),
            ("💼 Workspace & SaaS", 2),
            ("🗄️ Databases", 3),
            ("🐳 Infrastructure", 4),
        ]

        sidebar_items = []
        for cat_name, cat_id in categories:
            btn = QPushButton(cat_name)
            btn.setFixedHeight(32)
            btn.setFont(QFont(_FONT, 9))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            
            # Create page
            page = QWidget()
            page.setStyleSheet("background: transparent;")
            page_lay = QVBoxLayout(page)
            page_lay.setContentsMargins(0, 0, 0, 0)
            
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
            
            scroll_content = QWidget()
            scroll_content.setStyleSheet("background: transparent;")
            scroll_lay = QVBoxLayout(scroll_content)
            scroll_lay.setContentsMargins(0, 0, 10, 0)
            scroll_lay.setSpacing(10)
            
            if cat_id == 0:
                scroll_lay.addWidget(_card("Ollama", [("Local URL  (LAN / 192.168.x)", "llm_url_local", False, "http://localhost:11434"), ("Remote URL  (home / public)", "llm_url_remote", False, "https://…")], ["llm_url_local"]))
                scroll_lay.addWidget(_card("OpenAI", [("API Key", "openai_api_key", True, "sk-...")], ["openai_api_key"]))
                scroll_lay.addWidget(_card("Google Gemini", [("API Key", "gemini_api_key", True, "AIzaSy...")], ["gemini_api_key"]))
                scroll_lay.addWidget(_card("Anthropic Claude", [("API Key", "anthropic_api_key", True, "sk-ant-...")], ["anthropic_api_key"]))
                scroll_lay.addWidget(_card("DeepSeek", [("API Key", "deepseek_api_key", True, "sk-...")], ["deepseek_api_key"]))
                scroll_lay.addWidget(_card("Groq", [("API Key", "groq_api_key", True, "gsk_...")], ["groq_api_key"]))
                scroll_lay.addWidget(_card("OpenRouter", [("API Key", "openrouter_api_key", True, "sk-or-...")], ["openrouter_api_key"]))
                scroll_lay.addWidget(_card("Mistral", [("API Key", "mistral_api_key", True, "Mistral Key")], ["mistral_api_key"]))
                scroll_lay.addWidget(_card("LM Studio", [("Base URL", "lmstudio_url", False, "http://localhost:1234/v1")], ["lmstudio_url"]))
            elif cat_id == 1:
                scroll_lay.addWidget(_card("ElevenLabs TTS", [("API Key", "elevenlabs_api_key", True, "ElevenLabs Key")], ["elevenlabs_api_key"]))
                scroll_lay.addWidget(_card("LiveKit Voice", [("API Key", "livekit_api_key", True, "API Key"), ("API Secret", "livekit_api_secret", True, "API Secret")], ["livekit_api_key", "livekit_api_secret"]))
                scroll_lay.addWidget(_card("Spotify Integration", [("Client ID", "spotify_client_id", False, "Client ID"), ("Client Secret", "spotify_client_secret", True, "Client Secret")], ["spotify_client_id", "spotify_client_secret"]))
                scroll_lay.addWidget(_card("YouTube API", [("API Key", "youtube_api_key", True, "YouTube API Key")], ["youtube_api_key"]))
            elif cat_id == 2:
                # ── Google Workspace with OAuth ────────────────────────────
                gws_card = _card("Google Workspace (Gmail/Calendar/Drive)",
                                 [("Client ID", "gws_client_id", False, "OAuth Client ID from Google Cloud"),
                                  ("Client Secret", "gws_client_secret", True, "OAuth Client Secret")],
                                 ["gws_client_id", "gws_client_secret"])
                # Add Sign in with Google button
                from actions.google_workspace import is_authenticated, start_oauth_flow, has_credentials_json, revoke_auth, save_credentials_json, on_auth_change
                gws_btn_row = QHBoxLayout()
                gws_btn_row.setContentsMargins(10, 0, 10, 8)
                gws_signin_btn = QPushButton("Sign in with Google")
                gws_signin_btn.setFixedHeight(30)
                gws_signin_btn.setFont(QFont(_FONT, 8, QFont.Weight.Bold))
                gws_signin_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                gws_signin_btn.setStyleSheet(f"""
                    QPushButton {{ background: {C.ACC}; color: #fff; border: none; border-radius: 4px; padding: 4px 12px; }}
                    QPushButton:hover {{ background: {C.ACC_GHO}; }}
                    QPushButton:disabled {{ background: {C.PANEL2}; color: {C.TEXT_DIM}; }}
                """)
                gws_status = QLabel("")
                gws_status.setFont(QFont("Courier New", 7))
                gws_status.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
                gws_btn_row.addWidget(gws_signin_btn)
                gws_btn_row.addWidget(gws_status, stretch=1)

                # Revoke button
                gws_revoke_btn = QPushButton("Revoke")
                gws_revoke_btn.setFixedHeight(26)
                gws_revoke_btn.setFont(QFont(_FONT, 7))
                gws_revoke_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                gws_revoke_btn.setStyleSheet(f"""
                    QPushButton {{ background: transparent; color: {C.TEXT_DIM}; border: 1px solid {C.BORDER}; border-radius: 4px; padding: 2px 8px; }}
                    QPushButton:hover {{ background: {C.RED}; color: #fff; border: 1px solid {C.RED}; }}
                """)
                gws_revoke_btn.setVisible(False)
                gws_btn_row.addWidget(gws_revoke_btn)

                def _gws_update_auth_status():
                    ok = is_authenticated()
                    gws_signin_btn.setEnabled(has_credentials_json() and not ok)
                    gws_revoke_btn.setVisible(ok)
                    gws_status.setText("✓ Authenticated" if ok else "")
                    gws_status.setStyleSheet(f"color: {C.GREEN if ok else C.TEXT_DIM}; background: transparent;")

                self._auth_result_sig.connect(lambda s, m: (_gws_update_auth_status(), gws_status.setText(m) or True))

                def _gws_do_signin():
                    gws_signin_btn.setEnabled(False)
                    gws_status.setText("Opening browser…")
                    def _on_result(success: bool, msg: str):
                        self._auth_result_sig.emit(success, msg)
                    # Save credentials from inputs before auth
                    gws_client_id = self.inputs.get("gws_client_id", QLineEdit()).text().strip()
                    gws_client_secret = self.inputs.get("gws_client_secret", QLineEdit()).text().strip()
                    if gws_client_id and gws_client_secret:
                        save_credentials_json(gws_client_id, gws_client_secret)
                    start_oauth_flow(on_result=_on_result)

                gws_signin_btn.clicked.connect(_gws_do_signin)
                gws_revoke_btn.clicked.connect(lambda: (revoke_auth(), _gws_update_auth_status()))
                on_auth_change(lambda _: _gws_update_auth_status())

                # Watch credential inputs for sign-in button state
                def _gws_watch_creds(*_):
                    cid = self.inputs.get("gws_client_id", QLineEdit()).text().strip()
                    sec = self.inputs.get("gws_client_secret", QLineEdit()).text().strip()
                    gws_signin_btn.setEnabled(bool(cid and sec) and not is_authenticated())
                for k in ("gws_client_id", "gws_client_secret"):
                    if k in self.inputs:
                        self.inputs[k].textChanged.connect(_gws_watch_creds)

                # Add the button row below the card
                gws_card.layout().addLayout(gws_btn_row)
                scroll_lay.addWidget(gws_card)
                _gws_update_auth_status()
                scroll_lay.addWidget(_card("Plaid Finance", [("Client ID", "plaid_client_id", False, "Plaid Client ID"), ("Secret", "plaid_secret", True, "Plaid Secret"), ("Access Token", "plaid_access_token", True, "Access Token")], ["plaid_client_id", "plaid_secret", "plaid_access_token"]))
                scroll_lay.addWidget(_card("GitHub API", [("Personal Access Token", "github_access_token", True, "ghp_...")], ["github_access_token"]))
                scroll_lay.addWidget(_card("Fantastic Jobs", [("API Key", "fantastic_jobs_api_key", True, "Job Search API Key")], ["fantastic_jobs_api_key"]))
                scroll_lay.addWidget(_card("Slack Bot", [("Bot User OAuth Token", "slack_bot_token", True, "xoxb-...")], ["slack_bot_token"]))
                scroll_lay.addWidget(_card("Discord Bot", [("Bot Token", "discord_bot_token", True, "Discord Bot Token")], ["discord_bot_token"]))
            elif cat_id == 3:
                scroll_lay.addWidget(_card("PostgreSQL Database", [
                    ("Host", "postgres_host", False, "localhost"),
                    ("Port", "postgres_port", False, "5432"),
                    ("Username", "postgres_user", False, "postgres"),
                    ("Password", "postgres_password", True, "Password"),
                    ("Database Name", "postgres_db", False, "postgres")
                ], ["postgres_host", "postgres_user"]))
                scroll_lay.addWidget(_card("MySQL Database", [
                    ("Host", "mysql_host", False, "localhost"),
                    ("Port", "mysql_port", False, "3306"),
                    ("Username", "mysql_user", False, "root"),
                    ("Password", "mysql_password", True, "Password"),
                    ("Database Name", "mysql_db", False, "mysql")
                ], ["mysql_host", "mysql_user"]))
                scroll_lay.addWidget(_card("MongoDB", [("Connection URI", "mongodb_uri", True, "mongodb://localhost:27017")], ["mongodb_uri"]))
                scroll_lay.addWidget(_card("Redis", [
                    ("Host", "redis_host", False, "localhost"),
                    ("Port", "redis_port", False, "6379"),
                    ("Password", "redis_password", True, "Password")
                ], ["redis_host"]))
            elif cat_id == 4:
                scroll_lay.addWidget(_card("Docker Daemon", [("Docker Host", "docker_host", False, "unix:///var/run/docker.sock or localhost:2375")], ["docker_host"]))
                scroll_lay.addWidget(_card("Kubernetes", [("Kubeconfig Path", "kubeconfig_path", False, "~/.kube/config")], ["kubeconfig_path"]))
                scroll_lay.addWidget(_card("AWS Cloud", [
                    ("AWS Access Key ID", "aws_access_key_id", False, "AKIA..."),
                    ("AWS Secret Access Key", "aws_secret_access_key", True, "Secret Key"),
                    ("AWS Region", "aws_region", False, "us-east-1")
                ], ["aws_access_key_id", "aws_secret_access_key"]))
                scroll_lay.addWidget(_card("Google Cloud Platform (GCP)", [
                    ("Project ID", "gcp_project_id", False, "my-gcp-project"),
                    ("Service Account Credentials Path", "gcp_credentials_path", False, "/path/to/credentials.json")
                ], ["gcp_project_id", "gcp_credentials_path"]))
            
            scroll_lay.addStretch()
            scroll.setWidget(scroll_content)
            page_lay.addWidget(scroll)
            self.stack.addWidget(page)

            # Bind sidebar switch
            def bind_click(idx=cat_id):
                return lambda: self._switch_tab(idx)
            btn.clicked.connect(bind_click())
            sidebar_lay.addWidget(btn)
            sidebar_items.append((btn, cat_id))

        self.sidebar_items = sidebar_items
        sidebar_lay.addStretch()
        content_lay.addWidget(sidebar)
        content_lay.addWidget(self.stack, 1)
        main_layout.addLayout(content_lay, 1)

        def refresh_sidebar_styles(active_idx):
            for btn, cid in self.sidebar_items:
                if cid == active_idx:
                    btn.setStyleSheet(f"""
                        QPushButton {{
                            background: {C.ACC}; color: {C.WHITE};
                            border: none; border-radius: 6px;
                            padding: 8px 12px; font-weight: bold; text-align: left;
                        }}
                    """)
                else:
                    btn.setStyleSheet(f"""
                        QPushButton {{
                            background: transparent; color: {C.TEXT_MED};
                            border: 1px solid transparent; border-radius: 6px;
                            padding: 8px 12px; text-align: left;
                        }}
                        QPushButton:hover {{
                            background: {C.PANEL2}; color: {C.TEXT};
                            border: 1px solid {C.BORDER};
                        }}
                    """)
        self.refresh_sidebar_styles = refresh_sidebar_styles

        # Initial selection mapping or tab
        initial_idx = 0
        if active_tab_key:
            if active_tab_key in ("elevenlabs_api_key", "livekit_api_key", "spotify_client_id", "youtube_api_key"):
                initial_idx = 1
            elif active_tab_key in ("gws_credentials", "plaid_client_id", "github_access_token", "fantastic_jobs_api_key", "slack_bot_token", "discord_bot_token"):
                initial_idx = 2
            elif active_tab_key in ("postgres_host", "mysql_host", "mongodb_uri", "redis_host"):
                initial_idx = 3
            elif active_tab_key in ("docker_host", "kubeconfig_path", "aws_access_key_id", "gcp_project_id"):
                initial_idx = 4
        
        self.stack.setCurrentIndex(initial_idx)
        self.refresh_sidebar_styles(initial_idx)

        # Footer Action Bar
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        status_tip = QLabel("Settings are saved locally to config/api_keys.json")
        status_tip.setFont(QFont(_FONT, 8))
        status_tip.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; border: none;")
        btn_row.addWidget(status_tip)
        btn_row.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFont(QFont(_FONT, 10))
        cancel_btn.setFixedHeight(34)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 6px;
                padding: 4px 16px;
            }}
            QPushButton:hover {{
                color: {C.TEXT}; border: 1px solid {C.TEXT_MED};
            }}
        """)
        cancel_btn.clicked.connect(self.hide)
        btn_row.addWidget(cancel_btn)

        save_btn = QPushButton("Save & Apply")
        save_btn.setFont(QFont(_FONT, 10, QFont.Weight.Bold))
        save_btn.setFixedHeight(34)
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.ACC}; color: {C.WHITE};
                border: none; border-radius: 6px;
                padding: 4px 16px;
            }}
            QPushButton:hover {{
                background: {C.ACC_DIM};
            }}
        """)
        save_btn.clicked.connect(self._submit)
        btn_row.addWidget(save_btn)

        main_layout.addLayout(btn_row)

    def _switch_tab(self, idx):
        self.stack.setCurrentIndex(idx)
        self.refresh_sidebar_styles(idx)

    def _submit(self):
        cfg = {k: v.text().strip() for k, v in self.inputs.items()}
        self.done.emit(json.dumps(cfg))

ProvidersOverlay = ConnectionsOverlay


class StartupPanel(QWidget):
    """Animated startup progress overlay — shown while components initialize."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            StartupPanel {{
                background: rgba(0, 0, 0, 240);
                border: 1px solid {C.BORDER};
                border-radius: 8px;
            }}
        """)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 20, 28, 20)
        lay.setSpacing(10)

        title = QLabel("SYSTEMS INITIALISING")
        title.setFont(QFont("Courier New", 11, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"color: {C.TEXT}; background: transparent;")
        lay.addWidget(title)

        lay.addSpacing(2)

        self._rows: dict[str, dict] = {}
        _COMPS = ["SPEECH RECOGNITION", "LANGUAGE MODEL", "VOICE SYNTHESIS"]
        for key, label in zip(["stt", "llm", "tts"], _COMPS):
            box = QWidget()
            box.setStyleSheet(
                f"background: {C.PANEL2}; border: 1px solid {C.BORDER}; border-radius: 4px;"
            )
            box_lay = QVBoxLayout(box)
            box_lay.setContentsMargins(10, 6, 10, 6)
            box_lay.setSpacing(4)

            top = QHBoxLayout()
            nm = QLabel(label)
            nm.setFont(QFont("Courier New", 8))
            nm.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent; border: none;")
            top.addWidget(nm)
            top.addStretch()

            st = QLabel("LOADING…")
            st.setFont(QFont("Courier New", 7))
            st.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; border: none;")
            top.addWidget(st)
            box_lay.addLayout(top)

            bar = QProgressBar()
            bar.setFixedHeight(3)
            bar.setRange(0, 0)
            bar.setTextVisible(False)
            bar.setStyleSheet(f"""
                QProgressBar {{
                    background: {C.BAR_BG}; border: none; border-radius: 2px;
                }}
                QProgressBar::chunk {{
                    background: {C.TEXT_DIM};
                    border-radius: 2px; width: 60px; margin: 0px;
                }}
            """)
            box_lay.addWidget(bar)
            lay.addWidget(box)
            self._rows[key] = {"bar": bar, "status": st, "color": C.TEXT}

        lay.addSpacing(4)

        self._status_lbl = QLabel("Initialising components…")
        self._status_lbl.setFont(QFont("Courier New", 7))
        self._status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        self._status_lbl.setWordWrap(True)
        lay.addWidget(self._status_lbl)

    # Called only from the main thread (via MainWindow._startup_sig)
    def update_component(self, key: str, status: str) -> None:
        if key not in self._rows:
            return
        row = self._rows[key]
        ok     = status == "ready"
        color  = row["color"] if ok else C.TEXT_DIM
        label  = "READY" if ok else "ERROR"

        bar = row["bar"]
        bar.setRange(0, 100)
        bar.setValue(100)
        bar.setStyleSheet(f"""
            QProgressBar {{
                background: {C.BAR_BG}; border: none; border-radius: 2px;
            }}
            QProgressBar::chunk {{
                background: {color}; border-radius: 2px;
            }}
        """)
        st = row["status"]
        st.setText(label)
        st.setStyleSheet(f"color: {color}; background: transparent; border: none;")

    def set_status(self, text: str) -> None:
        self._status_lbl.setText(text)
        col = C.TEXT if "online" in text.lower() else C.TEXT_DIM
        self._status_lbl.setStyleSheet(f"color: {col}; background: transparent;")


class _AuthBanner(QWidget):
    _clicked = pyqtSignal()
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(60)
        self.setStyleSheet(f"background: {C.PANEL2}; border: 1px solid {C.BORDER}; border-radius: 4px;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 4, 8, 4)
        l1 = QLabel("Google not authenticated")
        l1.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        l1.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
        lay.addWidget(l1)
        self._btn = QPushButton("SETUP AUTH")
        self._btn.setFixedHeight(22)
        self._btn.setFont(QFont("Courier New", 7))
        self._btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT};
                border: 1px solid {C.TEXT_DIM}; border-radius: 3px;
            }}
            QPushButton:hover {{ background: {C.PANEL2}; }}
        """)
        self._btn.clicked.connect(self._clicked.emit)
        lay.addWidget(self._btn)

class WorkspacePanel(QWidget):
    _gmail_ready = pyqtSignal(list)
    _cal_ready = pyqtSignal(list)
    _drive_ready = pyqtSignal(list)
    _loading_sig = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._auth_banner = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"background: transparent; border: none;")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        ilay = QVBoxLayout(inner)
        ilay.setContentsMargins(0, 0, 0, 0)
        ilay.setSpacing(6)

        # ── Gmail ──────────────────────────────────────────────────────
        ilay.addWidget(self._sec_label("GMAIL"))
        self._gmail_list = QWidget()
        self._gmail_list.setStyleSheet("background: transparent;")
        self._gmail_list_lay = QVBoxLayout(self._gmail_list)
        self._gmail_list_lay.setContentsMargins(0, 0, 0, 0)
        self._gmail_list_lay.setSpacing(2)
        ilay.addWidget(self._gmail_list)

        gmail_btns = QHBoxLayout(); gmail_btns.setSpacing(4)
        refresh_gmail = QPushButton("REFRESH")
        refresh_gmail.setFixedHeight(22)
        refresh_gmail.setFont(QFont("Courier New", 7))
        refresh_gmail.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_gmail.setStyleSheet(self._btn_style())
        refresh_gmail.clicked.connect(self._refresh_gmail)
        gmail_btns.addWidget(refresh_gmail)

        compose_btn = QPushButton("COMPOSE")
        compose_btn.setFixedHeight(22)
        compose_btn.setFont(QFont("Courier New", 7))
        compose_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        compose_btn.setStyleSheet(self._btn_style())
        compose_btn.clicked.connect(self._show_compose)
        gmail_btns.addWidget(compose_btn)
        gmail_btns.addStretch()
        ilay.addLayout(gmail_btns)

        ilay.addWidget(self._sep())

        # ── Calendar ───────────────────────────────────────────────────
        ilay.addWidget(self._sec_label("CALENDAR"))
        self._cal_list = QWidget()
        self._cal_list.setStyleSheet("background: transparent;")
        self._cal_list_lay = QVBoxLayout(self._cal_list)
        self._cal_list_lay.setContentsMargins(0, 0, 0, 0)
        self._cal_list_lay.setSpacing(2)
        ilay.addWidget(self._cal_list)

        cal_btns = QHBoxLayout(); cal_btns.setSpacing(4)
        refresh_cal = QPushButton("REFRESH")
        refresh_cal.setFixedHeight(22)
        refresh_cal.setFont(QFont("Courier New", 7))
        refresh_cal.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_cal.setStyleSheet(self._btn_style())
        refresh_cal.clicked.connect(self._refresh_calendar)
        cal_btns.addWidget(refresh_cal)

        newevent_btn = QPushButton("NEW EVENT")
        newevent_btn.setFixedHeight(22)
        newevent_btn.setFont(QFont("Courier New", 7))
        newevent_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        newevent_btn.setStyleSheet(self._btn_style())
        newevent_btn.clicked.connect(self._show_new_event)
        cal_btns.addWidget(newevent_btn)
        cal_btns.addStretch()
        ilay.addLayout(cal_btns)

        ilay.addWidget(self._sep())

        # ── Meet ───────────────────────────────────────────────────────
        ilay.addWidget(self._sec_label("MEET"))
        meet_btns = QHBoxLayout(); meet_btns.setSpacing(4)
        meetnow = QPushButton("MEET NOW")
        meetnow.setFixedHeight(22)
        meetnow.setFont(QFont("Courier New", 7))
        meetnow.setCursor(Qt.CursorShape.PointingHandCursor)
        meetnow.setStyleSheet(self._btn_style())
        meetnow.clicked.connect(self._create_meet_now)
        meet_btns.addWidget(meetnow)

        schedmeet = QPushButton("SCHEDULE")
        schedmeet.setFixedHeight(22)
        schedmeet.setFont(QFont("Courier New", 7))
        schedmeet.setCursor(Qt.CursorShape.PointingHandCursor)
        schedmeet.setStyleSheet(self._btn_style())
        schedmeet.clicked.connect(self._show_schedule_meet)
        meet_btns.addWidget(schedmeet)
        meet_btns.addStretch()
        ilay.addLayout(meet_btns)

        self._meet_link_lbl = QLabel("")
        self._meet_link_lbl.setFont(QFont("Courier New", 7))
        self._meet_link_lbl.setWordWrap(True)
        self._meet_link_lbl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent; padding: 2px 4px;")
        ilay.addWidget(self._meet_link_lbl)

        ilay.addWidget(self._sep())

        # ── Drive ──────────────────────────────────────────────────────
        ilay.addWidget(self._sec_label("DRIVE"))
        drive_search_row = QHBoxLayout(); drive_search_row.setSpacing(4)
        self._drive_search = QLineEdit()
        self._drive_search.setPlaceholderText("Search Drive…")
        self._drive_search.setFont(QFont("Courier New", 7))
        self._drive_search.setFixedHeight(24)
        self._drive_search.setStyleSheet(f"""
            QLineEdit {{
                background: {C.PANEL2}; color: {C.TEXT};
                border: 1px solid {C.BORDER}; border-radius: 3px; padding: 2px 6px;
            }}
            QLineEdit:focus {{ border: 1px solid {C.TEXT_DIM}; }}
        """)
        self._drive_search.returnPressed.connect(self._search_drive)
        drive_search_row.addWidget(self._drive_search)
        srch = QPushButton("GO")
        srch.setFixedSize(28, 24)
        srch.setFont(QFont("Courier New", 7))
        srch.setCursor(Qt.CursorShape.PointingHandCursor)
        srch.setStyleSheet(self._btn_style())
        srch.clicked.connect(self._search_drive)
        drive_search_row.addWidget(srch)
        ilay.addLayout(drive_search_row)

        self._drive_list = QWidget()
        self._drive_list.setStyleSheet("background: transparent;")
        self._drive_list_lay = QVBoxLayout(self._drive_list)
        self._drive_list_lay.setContentsMargins(0, 0, 0, 0)
        self._drive_list_lay.setSpacing(2)
        ilay.addWidget(self._drive_list)

        drive_btns = QHBoxLayout(); drive_btns.setSpacing(4)
        upload = QPushButton("UPLOAD")
        upload.setFixedHeight(22)
        upload.setFont(QFont("Courier New", 7))
        upload.setCursor(Qt.CursorShape.PointingHandCursor)
        upload.setStyleSheet(self._btn_style())
        upload.clicked.connect(self._upload_file)
        drive_btns.addWidget(upload)

        newdoc = QPushButton("NEW DOC")
        newdoc.setFixedHeight(22)
        newdoc.setFont(QFont("Courier New", 7))
        newdoc.setCursor(Qt.CursorShape.PointingHandCursor)
        newdoc.setStyleSheet(self._btn_style())
        newdoc.clicked.connect(self._show_new_doc)
        drive_btns.addWidget(newdoc)
        drive_btns.addStretch()
        ilay.addLayout(drive_btns)

        ilay.addStretch()
        scroll.setWidget(inner)
        lay.addWidget(scroll, stretch=1)

        self._loading = QLabel("")
        self._loading.setFont(QFont("Courier New", 7))
        self._loading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._loading.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        lay.addWidget(self._loading)

        # ── State ─────────────────────────────────────────────────────
        self._main_window: MainWindow | None = None
        self._timer = QTimer()
        self._timer.timeout.connect(self._auto_refresh)
        self._timer.start(60000)

        self._gmail_ready.connect(self._update_gmail_ui)
        self._cal_ready.connect(self._update_cal_ui)
        self._drive_ready.connect(self._update_drive_ui)
        self._loading_sig.connect(self._set_loading_text)

    def set_main_window(self, mw):
        self._main_window = mw

    def _sec_label(self, txt):
        l = QLabel(txt)
        l.setFont(QFont("Courier New", 6, QFont.Weight.Bold))
        l.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; padding: 1px 0;")
        return l

    def _btn_style(self):
        return f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_DIM};
                border: 1px solid {C.BORDER}; border-radius: 3px;
            }}
            QPushButton:hover {{ color: {C.TEXT}; border: 1px solid {C.TEXT_DIM}; }}
        """

    def _sep(self):
        s = QFrame()
        s.setFrameShape(QFrame.Shape.HLine)
        s.setStyleSheet(f"color: {C.BORDER}; margin: 2px 0;")
        return s

    def _loading_on(self, text="Loading…"):
        self._loading_sig.emit(text)

    def _loading_off(self):
        self._loading_sig.emit("")

    def _set_loading_text(self, text: str):
        self._loading.setText(text)

    def _show_banner(self):
        if not self._auth_banner:
            self._auth_banner = _AuthBanner()
            self._auth_banner._clicked.connect(self._run_setup)
            self.layout().insertWidget(0, self._auth_banner)

    def _hide_banner(self):
        if self._auth_banner:
            self._auth_banner.hide()
            self.layout().removeWidget(self._auth_banner)
            self._auth_banner.deleteLater()
            self._auth_banner = None

    def _run_setup(self):
        subprocess.Popen(["bash", str(Path(__file__).resolve().parent / "setup_google.sh")])

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _add_gmail_row(self, layout, email: dict):
        subject = email.get("subject") or email.get("Subject", "(no subject)")
        sender = email.get("from") or email.get("From", "?")
        snippet = email.get("snippet") or email.get("Snippet", "")
        msg_id = email.get("id") or email.get("Id", "")

        card = QWidget()
        card.setStyleSheet(f"background: {C.PANEL2}; border: 1px solid {C.BORDER}; border-radius: 3px;")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(6, 3, 6, 3)
        cl.setSpacing(1)

        top = QHBoxLayout(); top.setSpacing(4)
        subj = QLabel(subject[:50])
        subj.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        subj.setStyleSheet(f"color: {C.TEXT}; background: transparent;")
        subj.setWordWrap(False)
        top.addWidget(subj, stretch=1)

        if msg_id:
            rp = QPushButton("REPLY")
            rp.setFixedSize(40, 18)
            rp.setFont(QFont("Courier New", 6))
            rp.setCursor(Qt.CursorShape.PointingHandCursor)
            rp.setStyleSheet(self._btn_style())
            rp.clicked.connect(lambda _, mid=msg_id: self._reply_email(mid))
            top.addWidget(rp)

        cl.addLayout(top)

        sn = QLabel(f"{sender}  ·  {snippet[:60]}")
        sn.setFont(QFont("Courier New", 6))
        sn.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        sn.setWordWrap(True)
        cl.addWidget(sn)

        layout.addWidget(card)

    def _add_cal_row(self, layout, event: dict):
        summary = event.get("summary") or event.get("Summary", "(no title)")
        start = event.get("start") or event.get("Start", "")
        end = event.get("end") or event.get("End", "")
        ev_id = event.get("id") or event.get("Id", "")
        meet_link = event.get("hangoutLink") or event.get("meet", "")

        card = QWidget()
        card.setStyleSheet(f"background: {C.PANEL2}; border: 1px solid {C.BORDER}; border-radius: 3px;")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(6, 3, 6, 3)
        cl.setSpacing(1)

        top = QHBoxLayout(); top.setSpacing(4)
        title = QLabel(summary[:40])
        title.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {C.TEXT}; background: transparent;")
        top.addWidget(title, stretch=1)

        if meet_link:
            jn = QPushButton("JOIN")
            jn.setFixedSize(36, 18)
            jn.setFont(QFont("Courier New", 6))
            jn.setCursor(Qt.CursorShape.PointingHandCursor)
            jn.setStyleSheet(self._btn_style())
            jn.clicked.connect(lambda _, ml=meet_link: self._open_meet(ml))
            top.addWidget(jn)

        if ev_id:
            dl = QPushButton("DEL")
            dl.setFixedSize(30, 18)
            dl.setFont(QFont("Courier New", 6))
            dl.setCursor(Qt.CursorShape.PointingHandCursor)
            dl.setStyleSheet(self._btn_style())
            dl.clicked.connect(lambda _, eid=ev_id: self._delete_event(eid))
            top.addWidget(dl)

        cl.addLayout(top)
        ti = QLabel(f"{start} - {end}")
        ti.setFont(QFont("Courier New", 6))
        ti.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        cl.addWidget(ti)

        layout.addWidget(card)

    def _add_drive_row(self, layout, file: dict):
        fname = file.get("name") or file.get("Name", "?")
        ftype = file.get("mimeType", "")
        modified = file.get("modifiedTime") or file.get("Modified", "")
        icon = "📄"
        if "folder" in ftype: icon = "📁"
        elif "sheet" in ftype: icon = "📊"
        elif "doc" in ftype: icon = "📝"
        elif "pdf" in ftype: icon = "📕"

        card = QWidget()
        card.setStyleSheet(f"background: {C.PANEL2}; border: 1px solid {C.BORDER}; border-radius: 3px;")
        cl = QHBoxLayout(card)
        cl.setContentsMargins(6, 3, 6, 3)
        nm = QLabel(f"{icon} {fname[:50]}")
        nm.setFont(QFont("Courier New", 7))
        nm.setStyleSheet(f"color: {C.TEXT}; background: transparent;")
        cl.addWidget(nm, stretch=1)
        dt = QLabel(modified[:10])
        dt.setFont(QFont("Courier New", 6))
        dt.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        cl.addWidget(dt)
        layout.addWidget(card)

    # ── API calls (threaded) ───────────────────────────────────────────
    def _refresh_gmail(self):
        self._loading_on("Fetching emails…")
        threading.Thread(target=self._do_refresh_gmail, daemon=True).start()

    def _do_refresh_gmail(self):
        try:
            import gws_bridge
            creds_path = Path(__file__).resolve().parent / "gws" / "credentials.json"
            if not creds_path.exists():
                self._loading_sig.emit("")
                return
            emails = _run_async(gws_bridge.get_unread_emails(limit=10))
            if not isinstance(emails, list):
                emails = []
            self._main_window._log_sig.emit(f"GWS: {len(emails)} unread emails")
        except Exception as e:
            emails = []
        self._gmail_ready.emit(emails)

    def _update_gmail_ui(self, emails: list):
        self._gmail_list_lay.setUpdatesEnabled(False)
        self._clear_layout(self._gmail_list_lay)
        if not emails:
            lbl = QLabel("No unread emails")
            lbl.setFont(QFont("Courier New", 7))
            lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; padding: 4px;")
            self._gmail_list_lay.addWidget(lbl)
        else:
            for e in emails:
                self._add_gmail_row(self._gmail_list_lay, e)
        self._gmail_list_lay.setUpdatesEnabled(True)
        self._loading_off()

    def _refresh_calendar(self):
        self._loading_on("Fetching agenda…")
        threading.Thread(target=self._do_refresh_calendar, daemon=True).start()

    def _do_refresh_calendar(self):
        try:
            import gws_bridge
            creds_path = Path(__file__).resolve().parent / "gws" / "credentials.json"
            if not creds_path.exists():
                self._loading_sig.emit("")
                return
            events = _run_async(gws_bridge.get_todays_agenda())
            if not isinstance(events, list):
                events = []
            self._main_window._log_sig.emit(f"GWS: {len(events)} agenda items")
        except Exception as e:
            events = []
        self._cal_ready.emit(events)

    def _update_cal_ui(self, events: list):
        self._cal_list_lay.setUpdatesEnabled(False)
        self._clear_layout(self._cal_list_lay)
        if not events:
            lbl = QLabel("No events today")
            lbl.setFont(QFont("Courier New", 7))
            lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; padding: 4px;")
            self._cal_list_lay.addWidget(lbl)
        else:
            for e in events:
                self._add_cal_row(self._cal_list_lay, e)
        self._cal_list_lay.setUpdatesEnabled(True)
        self._loading_off()

    def _search_drive(self):
        query = self._drive_search.text().strip()
        if not query:
            return
        self._loading_on("Searching Drive…")
        threading.Thread(target=self._do_search_drive, args=(query,), daemon=True).start()

    def _do_search_drive(self, query: str):
        try:
            import gws_bridge
            files = _run_async(gws_bridge.search_files(query=query))
            if not isinstance(files, list):
                files = []
            self._main_window._log_sig.emit(f"GWS: {len(files)} drive files found")
        except Exception as e:
            files = []
            self._main_window._log_sig.emit(f"GWS: drive search failed — {e}")
        self._drive_ready.emit(files)

    def _update_drive_ui(self, files: list):
        self._drive_list_lay.setUpdatesEnabled(False)
        self._clear_layout(self._drive_list_lay)
        if not files:
            lbl = QLabel("No files found")
            lbl.setFont(QFont("Courier New", 7))
            lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; padding: 4px;")
            self._drive_list_lay.addWidget(lbl)
        else:
            for f in files:
                self._add_drive_row(self._drive_list_lay, f)
        self._drive_list_lay.setUpdatesEnabled(True)
        self._loading_off()

    def _auto_refresh(self):
        mw = self._main_window
        if not mw or not mw.isVisible():
            return
        threading.Thread(target=self._do_refresh_gmail, daemon=True).start()
        threading.Thread(target=self._do_refresh_calendar, daemon=True).start()

    # ── Actions ────────────────────────────────────────────────────────
    def _reply_email(self, msg_id: str):
        if self._main_window and self._main_window.on_text_command:
            self._main_window.on_text_command(f"Reply to Gmail message {msg_id}")

    def _show_compose(self):
        if self._main_window and self._main_window.on_text_command:
            self._main_window.on_text_command("I want to compose a new email")

    def _show_new_event(self):
        if self._main_window and self._main_window.on_text_command:
            self._main_window.on_text_command("I want to create a new calendar event")

    def _show_schedule_meet(self):
        if self._main_window and self._main_window.on_text_command:
            self._main_window.on_text_command("I want to schedule a Google Meet")

    def _show_new_doc(self):
        if self._main_window and self._main_window.on_text_command:
            self._main_window.on_text_command("I want to create a new Google Doc")

    def _upload_file(self):
        if self._main_window and self._main_window.on_text_command:
            self._main_window.on_text_command("I want to upload a file to Google Drive")

    def _create_meet_now(self):
        from datetime import datetime
        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H:%M")
        self._loading_on("Creating Meet…")
        def _do():
            try:
                import gws_bridge
                ev = _run_async(gws_bridge.create_meet(
                    title="Instant Meeting",
                    date=date_str,
                    time=time_str,
                    duration_minutes=60,
                ))
                link = ev.get("hangoutLink") or ev.get("meet", "")
                if link:
                    from PyQt6.QtCore import QMetaObject, Qt as _Qt, Q_ARG
                    QMetaObject.invokeMethod(
                        self._meet_link_lbl, "setText",
                        _Qt.ConnectionType.QueuedConnection,
                        Q_ARG(str, f"Meet link: {link}"),
                    )
                    self._main_window._log_sig.emit(f"GWS: Meet created — {link}")
                self._loading_sig.emit("")
            except Exception as e:
                self._main_window._log_sig.emit(f"GWS: Meet creation failed — {e}")
                self._loading_sig.emit("")
        threading.Thread(target=_do, daemon=True).start()

    def _open_meet(self, url: str):
        import webbrowser
        webbrowser.open(url)

    def _delete_event(self, event_id: str):
        def _do():
            try:
                import gws_bridge
                _run_async(gws_bridge.delete_event(event_id=event_id))
                self._main_window._log_sig.emit(f"GWS: Event {event_id} deleted")
                self._refresh_calendar()
            except Exception as e:
                self._main_window._log_sig.emit(f"GWS: delete failed — {e}")
        threading.Thread(target=_do, daemon=True).start()


class MainWindow(QMainWindow):
    write_log     = pyqtSignal(str)
    write_log_instant = pyqtSignal(str, str)
    _log_sig = write_log
    _state_sig     = pyqtSignal(str)
    _error_sig     = pyqtSignal(str)  # message — thread-safe error state display
    _loc_sig       = pyqtSignal(str)
    _startup_sig   = pyqtSignal(str, str)  # action, data — thread-safe startup panel control
    _quit_sig      = pyqtSignal()
    _open_tutor_sig = pyqtSignal(str)
    _open_todo_sig = pyqtSignal(str)
    _close_tutor_sig = pyqtSignal()
    _api_key_sig   = pyqtSignal(str, str)  # service_name, key_name

    def __init__(self, face_path: str):
        super().__init__()
        self.setWindowTitle("J.A.R.V.I.S — MARK XL")
        self.setMinimumSize(_MIN_W, _MIN_H)
        self.resize(_DEFAULT_W, _DEFAULT_H)

        screen = QApplication.primaryScreen().availableGeometry()
        self.move(
            (screen.width()  - _DEFAULT_W) // 2,
            (screen.height() - _DEFAULT_H) // 2,
        )

        self.on_text_command  = None
        self._muted           = False
        self._current_file: str | None = None
        self._island_mode     = False
        self._normal_geometry = None
        self._header_widget   = None
        self._footer_widget   = None

        central = QWidget()
        central.setStyleSheet(f"background: {C.BG};")
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self._header_widget = self._build_header()
        root.addWidget(self._header_widget)

        body = QSplitter(Qt.Orientation.Horizontal)
        body.setHandleWidth(4)
        body.setChildrenCollapsible(False)
        body.setStyleSheet(f"""
            QSplitter::handle {{
                background: {C.BORDER};
                margin: 4px 0;
            }}
            QSplitter::handle:hover {{
                background: {C.ACC};
            }}
        """)

        self._left_panel = self._build_left_panel()
        body.addWidget(self._left_panel)

        # Center area: stacked widget for HUD or tutor web view
        self._center_stack = QStackedWidget()
        self._center_stack.setStyleSheet("background: transparent; border: none;")

        self.hud = HudCanvas(face_path)
        self.hud.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.hud.clicked.connect(self._on_hud_clicked)
        self._center_stack.addWidget(self.hud)  # page 0

        self._tutor_view = None
        self._center_stack.setCurrentIndex(0)
        body.addWidget(self._center_stack)

        self._right_panel = self._build_right_panel()
        body.addWidget(self._right_panel)

        body.setStretchFactor(0, 0)
        body.setStretchFactor(1, 1)
        body.setStretchFactor(2, 0)
        body.setSizes([_LEFT_W, 800, _RIGHT_W])

        if hasattr(self, '_ws_panel'):
            self._ws_panel.set_main_window(self)

        root.addWidget(body, stretch=1)
        self._footer_widget = self._build_footer()
        root.addWidget(self._footer_widget)

        self._clock_tmr = QTimer(self)
        self._clock_tmr.timeout.connect(self._tick_clock)
        self._clock_tmr.start(1000)
        self._tick_clock()

        # Metrik güncelleme timer'ı
        self._metric_tmr = QTimer(self)
        self._metric_tmr.timeout.connect(self._update_metrics)
        self._metric_tmr.start(2000)
        self._update_metrics()

        QApplication.instance().aboutToQuit.connect(_metrics.stop)

        self._log_sig.connect(self._log.append_log)
        self.write_log_instant.connect(self._log.append_instant)
        self._state_sig.connect(self._apply_state)
        self._error_sig.connect(self._show_error_state)
        self._loc_sig.connect(self._update_location)
        self._startup_sig.connect(self._on_startup_sig)

        self._quit_sig.connect(self.close)
        self._open_tutor_sig.connect(self.open_tutor_panel)
        self._open_todo_sig.connect(self.open_todo_panel)
        self._close_tutor_sig.connect(self.close_tutor_panel)

        self._api_key_event = threading.Event()
        self._api_key_result = ""
        self._api_key_sig.connect(self._on_api_key_request)

        self._overlay: SetupOverlay | None = None
        self._startup_panel: StartupPanel | None = None
        self._on_reconfigure_cb = None
        self._ready = self._check_config()
        if not self._ready:
            self._show_setup()

        sc_mute = QShortcut(QKeySequence("F4"), self)
        sc_mute.activated.connect(self._toggle_mute)
        sc_full = QShortcut(QKeySequence("F11"), self)
        sc_full.activated.connect(self._toggle_fullscreen)
        sc_island = QShortcut(QKeySequence("F12"), self)
        sc_island.activated.connect(self._toggle_island)

    def _update_location(self, loc_text: str):
        self._loc_lbl.setText(f"LOC  {loc_text}")

    def _on_api_key_request(self, service_name: str, key_name: str):
        from PyQt6.QtWidgets import QInputDialog, QLineEdit
        k = key_name or f"{service_name.lower().replace(' ', '_')}_api_key"
        result, ok = QInputDialog.getText(
            self,
            f"API Key Required — {service_name}",
            f"{service_name} requires an API key.\nEnter your {service_name} API key:",
            QLineEdit.EchoMode.Password,
        )
        self._api_key_result = result.strip() if ok and result.strip() else ""
        self._api_key_event.set()

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def _toggle_island(self):
        self._island_mode = not self._island_mode
        if self._island_mode:
            self._normal_geometry = self.geometry()
            self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
            self.showNormal()
            if self._left_panel: self._left_panel.hide()
            if self._right_panel: self._right_panel.hide()
            if self._header_widget: self._header_widget.hide()
            if self._footer_widget: self._footer_widget.hide()
            self.setMinimumSize(0, 0)
            self.setMaximumSize(16777215, 16777215)
            if self.centralWidget():
                self.centralWidget().layout().setContentsMargins(0, 0, 0, 0)
            screen = QApplication.primaryScreen().availableGeometry()
            iw, ih = 280, 80
            self.setGeometry(
                (screen.width() - iw) // 2,
                screen.bottom() - ih - 40,
                iw, ih,
            )
            self.hud.setMinimumSize(260, 60)
            self.setWindowTitle("J.A.R.V.I.S  ●")
            self._island_btn.setText("◈  EXPAND  [F12]")
        else:
            self.hud.setMinimumSize(300, 300)
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowStaysOnTopHint)
            self.showNormal()
            if self._left_panel: self._left_panel.show()
            if self._right_panel: self._right_panel.show()
            if self._header_widget: self._header_widget.show()
            if self._footer_widget: self._footer_widget.show()
            self.setMinimumSize(_MIN_W, _MIN_H)
            self.setMaximumSize(16777215, 16777215)
            if self._normal_geometry:
                self.setGeometry(self._normal_geometry)
            self.setWindowTitle("J.A.R.V.I.S — MARK XL")
            self._island_btn.setText("◈  DYNAMIC ISLAND  [F12]")

    def _on_hud_clicked(self):
        if self._island_mode:
            self._toggle_island()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cw = self.centralWidget()
        if self._overlay and self._overlay.isVisible():
            ow, oh = 520, 580
            self._overlay.setGeometry(
                (cw.width()  - ow) // 2,
                (cw.height() - oh) // 2,
                ow, oh,
            )
        if getattr(self, "_overlay_prov", None) and self._overlay_prov.isVisible():
            ow, oh = min(cw.width() - 20, 850), min(cw.height() - 20, 600)
            self._overlay_prov.setGeometry(
                (cw.width()  - ow) // 2,
                (cw.height() - oh) // 2,
                ow, oh,
            )
        if self._startup_panel and self._startup_panel.isVisible():
            pw, ph = 400, 310
            self._startup_panel.setGeometry(
                (cw.width()  - pw) // 2,
                (cw.height() - ph) // 2,
                pw, ph,
            )

    # ── Startup panel (thread-safe via _startup_sig) ────────────────────
    def _on_startup_sig(self, action: str, data: str) -> None:
        """Runs on main thread — handles all startup panel state changes."""
        if action == "show":
            self._create_startup_panel()
        elif action in ("ready", "error"):
            if self._startup_panel:
                self._startup_panel.update_component(data, action)
        elif action == "status":
            if self._startup_panel:
                self._startup_panel.set_status(data)
        elif action == "hide":
            if self._startup_panel:
                # Fade out after a short pause so "READY ✓" is visible
                QTimer.singleShot(1200, self._destroy_startup_panel)

    def _create_startup_panel(self) -> None:
        if self._startup_panel and self._startup_panel.isVisible():
            return
        cw = self.centralWidget()
        pw, ph = 400, 310
        panel = StartupPanel(cw)
        panel.setGeometry(
            (cw.width()  - pw) // 2,
            (cw.height() - ph) // 2,
            pw, ph,
        )
        panel.show()
        panel.raise_()
        self._startup_panel = panel

    def _destroy_startup_panel(self) -> None:
        if self._startup_panel:
            self._startup_panel.hide()
            self._startup_panel.deleteLater()
            self._startup_panel = None

    def _update_metrics(self):
        snap = _metrics.snapshot()

        # CPU
        cpu = snap["cpu"]
        self._bar_cpu.set_value(cpu, f"{cpu:.0f}%")

        # MEM
        mem = snap["mem"]
        self._bar_mem.set_value(mem, f"{mem:.0f}%")

        # NET
        net = snap["net"]
        if net < 1.0:
            net_str = f"{net*1024:.0f}KB/s"
        else:
            net_str = f"{net:.1f}MB/s"
        net_pct = min(100, net * 10)  # 10 MB/s = %100
        self._bar_net.set_value(net_pct, net_str)

        # GPU
        gpu = snap["gpu"]
        if gpu >= 0:
            self._bar_gpu.set_value(gpu, f"{gpu:.0f}%")
        else:
            self._bar_gpu.set_value(0, "N/A")

        # TMP
        tmp = snap["tmp"]
        if tmp >= 0:
            tmp_pct = min(100, (tmp / 100) * 100)
            self._bar_tmp.set_value(tmp_pct, f"{tmp:.0f}°C")
        else:
            self._bar_tmp.set_value(0, "N/A")

        try:
            boot_t  = psutil.boot_time()
            elapsed = time.time() - boot_t
            h = int(elapsed // 3600)
            m = int((elapsed % 3600) // 60)
            self._uptime_lbl.setText(f"UP  {h:02d}:{m:02d}")
        except Exception:
            self._uptime_lbl.setText("UP  --:--")

        try:
            proc_count = len(psutil.pids())
            self._proc_lbl.setText(f"PROC  {proc_count}")
        except Exception:
            self._proc_lbl.setText("PROC  --")

        self._update_status_bar()
        self._update_connections()
        self._update_timer_display()

    def _update_timer_display(self):
        try:
            timers = list_timers()
            if timers:
                sec = int(timers[0]["remaining_sec"])
                m, s = divmod(sec, 60)
                if len(timers) > 1:
                    self._status_timer.setText(f"⏱ {m:02d}:{s:02d} +{len(timers)-1}")
                else:
                    self._status_timer.setText(f"⏱ {m:02d}:{s:02d}")
                self._status_timer.setVisible(True)
            else:
                self._status_timer.setVisible(False)
        except Exception:
            self._status_timer.setVisible(False)

    def _build_header(self) -> QWidget:
        w = QWidget()
        w.setObjectName("header_widget")
        w.setFixedHeight(48)
        w.setStyleSheet(f"""
            #header_widget {{
                background: {C.PANEL};
                border-bottom: 1px solid {C.BORDER};
            }}
        """)
        lay = QHBoxLayout(w)
        lay.setContentsMargins(16, 0, 16, 0)

        title = QLabel("J.A.R.V.I.S")
        title.setFont(QFont("Courier New", 13, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {C.ACC}; background: transparent;")
        lay.addWidget(title)

        lay.addSpacing(20)

        self._status_mic   = QLabel("●  MIC")
        self._status_ai    = QLabel("●  AI")
        self._status_net   = QLabel("●  NET")
        self._status_cam   = QLabel("●  CAM")
        self._status_mem   = QLabel("●  MEM")
        self._status_timer = QLabel("")
        self._status_timer.setFont(QFont("Courier New", 9))
        self._status_timer.setStyleSheet(f"color: {C.GREEN}; background: transparent; padding: 0 8px;")

        for lbl in (self._status_mic, self._status_ai, self._status_net,
                     self._status_cam, self._status_mem):
            lbl.setFont(QFont("Courier New", 9))
            lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; padding: 0 8px;")
            lay.addWidget(lbl)

        lay.addWidget(self._status_timer)

        lay.addStretch()

        right_col = QVBoxLayout(); right_col.setSpacing(1)
        self._clock_lbl = QLabel("00:00")
        self._clock_lbl.setFont(QFont("Courier New", 14, QFont.Weight.Bold))
        self._clock_lbl.setStyleSheet(f"color: {C.WHITE}; background: transparent;")
        self._clock_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        right_col.addWidget(self._clock_lbl)
        self._date_lbl = QLabel("")
        self._date_lbl.setFont(QFont("Courier New", 8))
        self._date_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        self._date_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        right_col.addWidget(self._date_lbl)
        lay.addLayout(right_col)
        return w

    def _tick_clock(self):
        self._clock_lbl.setText(time.strftime("%H:%M"))
        self._date_lbl.setText(time.strftime("%a %d %b"))

    def _build_left_panel(self) -> QWidget:
        w = QWidget()
        w.setObjectName("left_panel")
        w.setFixedWidth(_LEFT_W)
        w.setStyleSheet(f"""
            #left_panel {{
                background: {C.PANEL};
                border-right: 1px solid {C.BORDER};
            }}
        """)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # ── Metrics section ──
        metrics_wrap = QWidget()
        metrics_wrap.setStyleSheet(f"background: transparent;")
        m_wrap_lay = QVBoxLayout(metrics_wrap)
        m_wrap_lay.setContentsMargins(10, 12, 10, 8)
        m_wrap_lay.setSpacing(5)

        self._bar_cpu = MetricBar("CPU")
        self._bar_mem = MetricBar("MEM")
        self._bar_net = MetricBar("NET")
        self._bar_gpu = MetricBar("GPU")
        self._bar_tmp = MetricBar("TMP")

        for bar in [self._bar_cpu, self._bar_mem, self._bar_net,
                    self._bar_gpu, self._bar_tmp]:
            m_wrap_lay.addWidget(bar)

        m_wrap_lay.addSpacing(4)

        # ── Section header for system info ──
        sec = QLabel("SYSTEM")
        sec.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        sec.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; padding: 2px 0; letter-spacing: 1px;")
        m_wrap_lay.addWidget(sec)

        m_wrap_lay.addSpacing(2)

        info_panel = QWidget()
        info_panel.setObjectName("info_panel")
        info_panel.setStyleSheet(f"""
            #info_panel {{
                background: {C.PANEL2};
                border: 1px solid {C.BORDER};
                border-radius: 6px;
            }}
        """)
        ip_lay = QVBoxLayout(info_panel)
        ip_lay.setContentsMargins(8, 7, 8, 7)
        ip_lay.setSpacing(4)

        self._uptime_lbl = QLabel("UP  --:--")
        self._uptime_lbl.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        self._uptime_lbl.setStyleSheet(f"color: {C.TEXT}; background: transparent; border: none;")
        ip_lay.addWidget(self._uptime_lbl)

        self._proc_lbl = QLabel("PROC  --")
        self._proc_lbl.setFont(QFont("Courier New", 8))
        self._proc_lbl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent; border: none;")
        ip_lay.addWidget(self._proc_lbl)

        os_name = {"Windows": "WIN", "Darwin": "macOS", "Linux": "LINUX"}.get(_OS, _OS.upper())
        os_lbl = QLabel(f"OS  {os_name}")
        os_lbl.setFont(QFont("Courier New", 8))
        os_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; border: none;")
        ip_lay.addWidget(os_lbl)

        self._loc_lbl = QLabel("LOC  --")
        self._loc_lbl.setFont(QFont("Courier New", 8))
        self._loc_lbl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent; border: none;")
        ip_lay.addWidget(self._loc_lbl)

        try:
            import json
            cfg = json.loads(Path("config/api_keys.json").read_text(encoding="utf-8"))
            cur_llm = cfg.get("llm_model", "")
        except Exception:
            cur_llm = ""
        self._llm_lbl = QLabel(f"LLM  {cur_llm if cur_llm else '--'}")
        self._llm_lbl.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        self._llm_lbl.setStyleSheet(f"color: {C.ACC}; background: transparent; border: none;")
        ip_lay.addWidget(self._llm_lbl)

        m_wrap_lay.addWidget(info_panel)
        lay.addWidget(metrics_wrap)

        # ── Separator ──
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"background: transparent; border: none; border-top: 1px solid {C.BORDER}; margin: 0 10px; max-height: 1px;")
        lay.addWidget(sep)

        # ── Connections section ──
        conn_wrap = QWidget()
        conn_wrap.setStyleSheet("background: transparent;")
        conn_lay = QVBoxLayout(conn_wrap)
        conn_lay.setContentsMargins(10, 8, 10, 8)
        conn_lay.setSpacing(2)

        header_lay = QHBoxLayout()
        header_lay.setSpacing(0)
        title = QLabel("SERVICES")
        title.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; border: none; letter-spacing: 1px;")
        header_lay.addWidget(title)
        header_lay.addStretch()
        add_btn = QPushButton("+")
        add_btn.setFixedSize(20, 20)
        add_btn.setFont(QFont("Courier New", 11))
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {C.TEXT_DIM}; "
            f"border: 1px solid {C.BORDER}; border-radius: 4px; }}"
            f"QPushButton:hover {{ color: {C.GREEN}; border: 1px solid {C.GREEN}; "
            f"background: {C.PANEL2}; }}"
        )
        add_btn.clicked.connect(self._on_add_connection)
        header_lay.addWidget(add_btn)
        conn_lay.addLayout(header_lay)

        conn_lay.addSpacing(4)

        self._conn_rows: list[tuple[QLabel, QLabel, str, str]] = []
        for svc, key in _API_SERVICES:
            dot = QLabel("●")
            dot.setFont(QFont("Courier New", 9))
            lbl = QLabel(svc)
            lbl.setFont(QFont(_FONT, 9))
            lbl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent; border: none;")

            row = QWidget()
            row.setObjectName(f"conn_row_{svc.lower().replace(' ', '_')}")
            row.setCursor(Qt.CursorShape.PointingHandCursor)
            row.setStyleSheet(
                f"QWidget {{ background: transparent; border-radius: 4px; padding: 2px 4px; }}"
                f"QWidget:hover {{ background: {C.PRI_GHO}; }}"
            )
            rlay = QHBoxLayout(row)
            rlay.setContentsMargins(4, 3, 4, 3)
            rlay.setSpacing(6)
            rlay.addWidget(dot)
            rlay.addWidget(lbl, 1)

            row.mousePressEvent = lambda e, s=svc, k=key: self._on_conn_click(s, k)

            conn_lay.addWidget(row)
            self._conn_rows.append((dot, lbl, svc, key))

        self._conn_panel = conn_wrap
        lay.addWidget(conn_wrap)
        lay.addStretch()

        return w
    def _build_right_panel(self) -> QWidget:
        w = QWidget()
        w.setObjectName("right_panel")
        w.setMinimumWidth(280)
        w.resize(_RIGHT_W, w.height())
        w.setStyleSheet(f"""
            #right_panel {{
                background: {C.BG};
                border-left: 1px solid {C.BORDER};
            }}
        """)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        # ── Chat header ──
        chat_header = QLabel("CHAT")
        chat_header.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        chat_header.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; letter-spacing: 1px; padding: 0 2px;")
        lay.addWidget(chat_header)

        # ── Chat log ──
        self._log = LogWidget()
        lay.addWidget(self._log, stretch=1)

        # ── Input + send ──
        input_row = QHBoxLayout(); input_row.setSpacing(6)
        self._input = QLineEdit()
        self._input.setPlaceholderText("Type a command or question…")
        self._input.setFont(QFont(_FONT, _FONT_SZ_SM))
        self._input.setFixedHeight(40)
        self._input.setStyleSheet(f"""
            QLineEdit {{
                background: {C.PANEL2}; color: {C.WHITE};
                border: 1px solid {C.BORDER}; border-radius: 8px;
                padding: 4px 14px;
                font-size: 13px;
            }}
            QLineEdit:focus {{ border: 1px solid {C.ACC}; }}
        """)
        self._input.returnPressed.connect(self._send)
        input_row.addWidget(self._input, stretch=1)

        self._send_btn = QPushButton("➤")
        self._send_btn.setFixedSize(40, 40)
        self._send_btn.setFont(QFont(_FONT, 13, QFont.Weight.Bold))
        self._send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._send_btn.setToolTip("Send (Enter)")
        self._send_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.ACC_DIM}; color: {C.ACC};
                border: 1px solid {C.ACC_DIM}; border-radius: 8px;
            }}
            QPushButton:hover {{ background: {C.ACC}; color: #ffffff; border: 1px solid {C.ACC}; }}
        """)
        self._send_btn.clicked.connect(self._send)
        input_row.addWidget(self._send_btn)
        lay.addLayout(input_row)

        # ── Quick commands ──
        lay.addWidget(self._build_quick_chips())

        # ── Buttons ──
        btn_row = QHBoxLayout(); btn_row.setSpacing(6)
        self._mute_btn = QPushButton("Mic")
        self._mute_btn.setFixedHeight(32)
        self._mute_btn.setFont(QFont(_FONT, _FONT_SZ_SM))
        self._mute_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._mute_btn.clicked.connect(self._toggle_mute)
        self._style_mute_btn()
        btn_row.addWidget(self._mute_btn)

        for label, cb in [
            ("Fullscreen", self._toggle_fullscreen),
            ("Settings", self._show_config),
            ("Connections", self._show_connections),
            ("Island", self._toggle_island),
        ]:
            btn = QPushButton(label)
            btn.setFixedHeight(32)
            btn.setFont(QFont(_FONT, _FONT_SZ_SM))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {C.TEXT_DIM};
                    border: 1px solid {C.BORDER}; border-radius: 5px;
                    padding: 2px 12px;
                }}
                QPushButton:hover {{ color: {C.TEXT}; border: 1px solid {C.ACC}; background: {C.PRI_GHO}; }}
            """)
            btn.clicked.connect(cb)
            btn_row.addWidget(btn)

        btn_row.addStretch()
        lay.addLayout(btn_row)

        return w

    def _build_quick_chips(self) -> QWidget:
        """One-click shortcuts that fire common commands (dashboard, email, …)."""
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        for label, cmd in [
            ("Dashboard", "open my dashboard"),
            ("Email",     "check my emails"),
            ("Weather",   "what's the weather"),
            ("Tasks",     "show my tasks"),
            ("Music",     "play some music"),
            ("Terminal",  "open terminal"),
        ]:
            b = QPushButton(label)
            b.setFixedHeight(26)
            b.setFont(QFont(_FONT, _FONT_SZ_XS))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setToolTip(f"Say: {cmd}")
            b.setStyleSheet(f"""
                QPushButton {{
                    background: {C.PANEL2}; color: {C.TEXT_MED};
                    border: 1px solid {C.BORDER}; border-radius: 13px;
                    padding: 0 10px;
                }}
                QPushButton:hover {{
                    color: {C.ACC}; border: 1px solid {C.ACC};
                    background: {C.ACC_GHO};
                }}
            """)
            b.clicked.connect(lambda _=False, c=cmd: self._run_quick_cmd(c))
            lay.addWidget(b)
        lay.addStretch()
        return w

    def _run_quick_cmd(self, command: str):
        self._input.setText(command)
        self._send()

    def _build_footer(self) -> QWidget:
        w = QWidget()
        w.setObjectName("footer_widget")
        w.setFixedHeight(24)
        w.setStyleSheet(f"""
            #footer_widget {{
                background: {C.PANEL};
                border-top: 1px solid {C.BORDER};
            }}
        """)
        lay = QHBoxLayout(w); lay.setContentsMargins(16, 0, 16, 0)
        l = QLabel("MARK XL  ·  [F4] Mute  ·  [F11] Fullscreen  ·  [F12] Island")
        l.setFont(QFont("Courier New", 8))
        l.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        lay.addWidget(l)

        lay.addStretch()
        self._footer_llm = QLabel("ollama · qwen2.5:0.5b")
        self._footer_llm.setFont(QFont("Courier New", 8))
        self._footer_llm.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        lay.addWidget(self._footer_llm)
        return w

    def _on_file_selected(self, path: str):
        self._current_file = path
        p    = Path(path)
        cat  = _file_category(p)
        icon, _ = _FILE_ICONS.get(cat, _FILE_ICONS["unknown"])
        size = _fmt_size(p.stat().st_size)
        self._file_hint.setText(f"{icon}  {p.name}  ·  {size}  ·  Tell JARVIS what to do with it")
        self._log.append_log(f"FILE: {p.name} ({size}) loaded")
        if self.on_text_command:
            msg = (
                f"[FILE_UPLOADED] path={path} | name={p.name} | "
                f"type={p.suffix.lstrip('.')} | size={size} | "
                f"Briefly tell the user you can see the file '{p.name}' "
                f"({size}) has been uploaded and ask what they'd like to do with it."
            )
            threading.Thread(target=self.on_text_command, args=(msg,), daemon=True).start()

    def _toggle_mute(self):
        self._muted = not self._muted
        self.hud.muted = self._muted
        self._style_mute_btn()
        self._update_status_bar()
        if self._muted:
            self._apply_state("MUTED")
            self._log.append_log("SYS: Microphone muted.")
        else:
            self._apply_state("LISTENING")
            self._log.append_log("SYS: Microphone active.")

    def _style_mute_btn(self):
        if self._muted:
            self._mute_btn.setText("Muted")
            self._mute_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {C.TEXT_DIM};
                    border: 1px solid {C.BORDER}; border-radius: 4px;
                    padding: 2px 10px;
                }}
            """)
        else:
            self._mute_btn.setText("Mic")
            self._mute_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {C.TEXT};
                    border: 1px solid {C.ACC}; border-radius: 4px;
                    padding: 2px 10px;
                }}
                QPushButton:hover {{ background: {C.ACC_GHO}; }}
            """)

    def open_tutor_panel(self, url: str):
        if not _HAS_WEBENGINE:
            import webbrowser
            webbrowser.open(url)
            return
        if self._tutor_view is None:
            self._tutor_view = QWebEngineView()
            self._tutor_view.setStyleSheet("background: transparent; border: none;")
            self._center_stack.addWidget(self._tutor_view)  # page 1
        self._tutor_view.load(QUrl(url))
        self._center_stack.setCurrentIndex(1)
        self._log.append_log(f"SYS: Gemini Tutor opened.")

    def close_tutor_panel(self):
        if self._tutor_view is not None and self._center_stack.currentIndex() == 1:
            self._center_stack.setCurrentIndex(0)
            self._log.append_log("SYS: Gemini Tutor closed.")

    def open_todo_panel(self, url: str):
        if not _HAS_WEBENGINE:
            import webbrowser
            webbrowser.open(url)
            return
        if self._tutor_view is None:
            self._tutor_view = QWebEngineView()
            self._tutor_view.setStyleSheet("background: transparent; border: none;")
            self._center_stack.addWidget(self._tutor_view)
        self._tutor_view.load(QUrl(url))
        self._center_stack.setCurrentIndex(1)
        self._log.append_log("SYS: Todo list opened.")

    def _send(self):
        txt = self._input.text().strip()
        if not txt: return
        self._input.clear()
        if self.on_text_command:
            threading.Thread(target=self.on_text_command, args=(txt,), daemon=True).start()

    def _apply_state(self, state: str):
        self.hud.state    = state
        self.hud.speaking = (state == "SPEAKING")
        self._update_status_bar()

    def _show_error_state(self, message: str):
        self.hud.state    = "ERROR"
        self.hud.speaking = False
        self._update_status_bar()
        self._log.append_log(f"ERR: {message}")
        QTimer.singleShot(2500, self._clear_error)

    def _clear_error(self):
        if self.hud.state == "ERROR":
            self.hud.state = "LISTENING"
            self.hud.speaking = False
            self._update_status_bar()

    def _set_status_lbl(self, lbl: QLabel, color: str, text: str):
        lbl.setText(f"●  {text}")
        lbl.setStyleSheet(f"color: {color}; background: transparent; padding: 0 6px;")

    def _update_status_bar(self):
        mic_col = C.GREEN if not self._muted else C.RED
        self._set_status_lbl(self._status_mic, mic_col, "MIC")

        state = getattr(self.hud, 'state', 'INITIALISING')
        if state in ("THINKING", "SPEAKING"):
            ai_col = C.GREEN
        elif state in ("LISTENING", "PROCESSING"):
            ai_col = "#ffcc00"
        elif state == "MUTED":
            ai_col = C.RED
        elif state == "ERROR":
            ai_col = C.RED
        else:
            ai_col = C.TEXT_DIM
        self._set_status_lbl(self._status_ai, ai_col, "AI")

        try:
            import socket
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.5)
            s.connect(("8.8.8.8", 53))
            s.close()
            self._set_status_lbl(self._status_net, C.GREEN, "NET")
        except Exception:
            self._set_status_lbl(self._status_net, C.RED, "NET")

        try:
            import subprocess
            r = subprocess.run(["lsof", "/dev/video*"], capture_output=True, text=True, timeout=1)
            cam_ok = bool(r.stdout.strip())
        except Exception:
            cam_ok = False
        self._set_status_lbl(self._status_cam, C.GREEN if cam_ok else C.MUTED_C, "CAM")

        try:
            from memory.vector_memory import get_memory_count
            cnt = get_memory_count()
        except Exception:
            cnt = 0
        mem_col = C.GREEN if cnt > 0 else C.MUTED_C
        lbl = f"MEM  {cnt}"
        self._status_mem.setText(f"●  {lbl}")
        self._status_mem.setStyleSheet(f"color: {mem_col}; background: transparent; padding: 0 6px;")

    def _load_config_dict(self) -> dict:
        try:
            return json.loads(API_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _key_is_set(self, key: str) -> bool:
        if key == "gws_credentials":
            return (CONFIG_DIR.parent / "gws" / "credentials.json").exists()
        cfg = self._load_config_dict()
        val = cfg.get(key, "")
        return bool(val) and val.strip() != ""

    def _update_connections(self):
        import os
        cfg = self._load_config_dict()
        for dot, lbl, svc, key in self._conn_rows:
            is_set = self._key_is_set(key)
            col = C.GREEN if is_set else C.RED
            dot.setStyleSheet(f"color: {col}; background: transparent; border: none;")
            lbl.setStyleSheet(
                f"color: {C.TEXT if is_set else C.TEXT_DIM}; background: transparent; border: none;"
            )

    def _on_conn_click(self, svc_name: str, key_name: str):
        self._show_connections(active_tab_key=key_name)

    def _on_add_connection(self):
        self._show_connections()

    def _check_config(self) -> bool:
        if not API_FILE.exists(): return False
        try:
            d = json.loads(API_FILE.read_text(encoding="utf-8"))
            return bool(d.get("stt_engine")) and bool(d.get("tts_engine"))
        except Exception:
            return False

    def _show_setup(self):
        ov = SetupOverlay(self.centralWidget())
        cw = self.centralWidget()
        ow, oh = 520, 580
        ov.setGeometry(
            (cw.width()  - ow) // 2,
            (cw.height() - oh) // 2,
            ow, oh,
        )
        ov.done.connect(self._on_setup_done)
        ov.show()
        self._overlay = ov

    def _on_setup_done(self, config_json: str):
        try:
            cfg = json.loads(config_json)
        except Exception:
            cfg = {}
        os.makedirs(CONFIG_DIR, exist_ok=True)
        API_FILE.write_text(
            json.dumps(cfg, indent=4),
            encoding="utf-8",
        )
        self._ready = True
        if self._overlay:
            self._overlay.hide()
            self._overlay = None
        self._apply_state("LISTENING")
        llm = cfg.get("llm_model", "")
        stt = cfg.get("stt_engine", "")
        tts = cfg.get("tts_engine", "")
        self._log.append_log(
            f"SYS: Initialised. LLM={llm} | STT={stt} | TTS={tts}"
        )

    def _show_config(self):
        if self._overlay and self._overlay.isVisible():
            return
        current: dict = {}
        try:
            current = json.loads(API_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
        ov = SetupOverlay(self.centralWidget(), initial=current, mode="config")
        cw = self.centralWidget()
        ow, oh = 520, 600
        ov.setGeometry(
            (cw.width()  - ow) // 2,
            (cw.height() - oh) // 2,
            ow, oh,
        )
        ov.done.connect(self._on_config_done)
        ov.show()
        self._overlay = ov

    def _on_config_done(self, config_json: str):
        try:
            cfg = json.loads(config_json)
        except Exception:
            cfg = {}
        os.makedirs(CONFIG_DIR, exist_ok=True)
        API_FILE.write_text(json.dumps(cfg, indent=4), encoding="utf-8")
        if self._overlay:
            self._overlay.hide()
            self._overlay = None
        llm = cfg.get("llm_model", "")
        stt = cfg.get("stt_engine", "")
        tts = cfg.get("tts_engine", "")
        self._log.append_log(f"SYS: Config updated. LLM={llm} | STT={stt} | TTS={tts}")
        if self._on_reconfigure_cb:
            self._on_reconfigure_cb(cfg)
        # Update left-panel LLM label
        try:
            self._update_llm_label(cfg)
        except Exception:
            pass

    def _show_connections(self, active_tab_key: str | None = None):
        if getattr(self, "_overlay_prov", None) and self._overlay_prov.isVisible():
            return
        import json
        from pathlib import Path
        current = {}
        try:
            current = json.loads(Path("config/api_keys.json").read_text(encoding="utf-8"))
        except Exception:
            pass
        ov = ConnectionsOverlay(self.centralWidget(), initial=current, active_tab_key=active_tab_key)
        cw = self.centralWidget()
        ow, oh = min(cw.width() - 20, 850), min(cw.height() - 20, 600)
        ov.setGeometry(
            (cw.width()  - ow) // 2,
            (cw.height() - oh) // 2,
            ow, oh,
        )
        ov.done.connect(self._on_providers_done)
        ov.show()
        self._overlay_prov = ov

    def _show_providers(self):
        self._show_connections()

    def _on_providers_done(self, diff_json: str):
        import json
        import os
        from pathlib import Path
        try:
            diff = json.loads(diff_json)
        except Exception:
            diff = {}
        
        current = {}
        API_FILE = Path("config/api_keys.json")
        try:
            current = json.loads(API_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
        
        current.update(diff)
        
        # Auto-resolve LLM URL based on current network
        if current.get("llm_url_local") or current.get("llm_url_remote"):
            current["llm_url"] = resolve_llm_url(current)
        
        # Clean up old dead key
        current.pop("ollama_url", None)
        
        os.makedirs("config", exist_ok=True)
        API_FILE.write_text(json.dumps(current, indent=4), encoding="utf-8")
        if getattr(self, "_overlay_prov", None):
            self._overlay_prov.hide()
            self._overlay_prov = None
            
        self._log.append_log("SYS: Providers updated.")
        if self._on_reconfigure_cb:
            self._on_reconfigure_cb(current)
        # Refresh LLM label after providers change
        try:
            self._update_llm_label(current)
        except Exception:
            pass

    def _update_llm_label(self, cfg: dict | None = None):
        try:
            if cfg is None:
                import json
                cfg = json.loads(Path("config/api_keys.json").read_text(encoding="utf-8"))
            model = cfg.get("llm_model", "")
            provider = cfg.get("llm_provider", "")
            text = f"LLM  {model}" if model else f"LLM  ({provider})"
            if hasattr(self, '_llm_lbl'):
                self._llm_lbl.setText(text)
        except Exception:
            pass


class _RootShim:
    def __init__(self, app: QApplication):
        self._app = app
    def mainloop(self):
        self._app.exec()
    def protocol(self, *_):
        pass


class JarvisUI:
    def __init__(self, face_path: str, size=None):
        self._app = QApplication.instance() or QApplication(sys.argv)
        self._app.setStyle("Fusion")
        try:
            import json
            cfg = json.loads(Path("config/api_keys.json").read_text(encoding="utf-8"))
            C.apply_theme(cfg.get("theme", "dark") == "light")
        except Exception:
            pass
        self._win = MainWindow(face_path)
        self._win.show()
        self.root = _RootShim(self._app)

    @property
    def muted(self) -> bool:
        return self._win._muted

    @muted.setter
    def muted(self, v: bool):
        if v != self._win._muted:
            self._win._toggle_mute()

    @property
    def current_file(self) -> str | None:
        dz = getattr(self._win, '_drop_zone', None)
        if dz and hasattr(dz, 'current_file'):
            return dz.current_file()
        return getattr(self._win, '_current_file', None)

    @property
    def on_text_command(self):
        return self._win.on_text_command

    @on_text_command.setter
    def on_text_command(self, cb):
        self._win.on_text_command = cb

    @property
    def on_reconfigure(self):
        return self._win._on_reconfigure_cb

    @on_reconfigure.setter
    def on_reconfigure(self, cb):
        self._win._on_reconfigure_cb = cb

    def set_state(self, state: str):
        self._win._state_sig.emit(state)

    def show_error_state(self, message: str = ""):
        self._win._error_sig.emit(message)

    def open_tutor_panel(self, url: str):
        self._win._open_tutor_sig.emit(url)

    def close_tutor_panel(self):
        self._win._close_tutor_sig.emit()

    def write_log(self, text: str):
        self._win._log_sig.emit(text)

    def write_log_instant(self, text: str, tag: str = "ai"):
        self._win.write_log_instant.emit(text, tag)

    def set_location(self, loc_text: str):
        self._win._loc_sig.emit(loc_text)

    def request_api_key(self, service_name: str, key_name: str = "") -> str:
        """Thread-safe — asks user for an API key via modal dialog."""
        self._win._api_key_result = ""
        self._win._api_key_event.clear()
        self._win._api_key_sig.emit(service_name, key_name)
        self._win._api_key_event.wait()
        result = self._win._api_key_result
        if result:
            k = key_name or f"{service_name.lower().replace(' ', '_')}_api_key"
            from memory.config_manager import save_config
            save_config({k: result})
        return result

    # ── Startup panel (all thread-safe) ──────────────────────────────────
    def show_startup_panel(self) -> None:
        self._win._startup_sig.emit("show", "")

    def mark_startup_ready(self, key: str, error: bool = False) -> None:
        self._win._startup_sig.emit("error" if error else "ready", key)

    def set_startup_status(self, text: str) -> None:
        self._win._startup_sig.emit("status", text)

    def hide_startup_panel(self) -> None:
        self._win._startup_sig.emit("hide", "")

    def wait_for_api_key(self):
        while not self._win._ready:
            time.sleep(0.1)

    def start_speaking(self):
        self.set_state("SPEAKING")

    def stop_speaking(self):
        if not self.muted:
            self.set_state("LISTENING")
