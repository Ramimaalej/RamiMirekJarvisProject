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
    QApplication, QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QPushButton, QScrollArea, QSizePolicy, QStackedWidget, QTextEdit,
    QVBoxLayout, QWidget, QProgressBar,
)

def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent

BASE_DIR   = _base_dir()
CONFIG_DIR = BASE_DIR / "config"
API_FILE   = CONFIG_DIR / "api_keys.json"

_DEFAULT_W, _DEFAULT_H = 980, 700
_MIN_W,     _MIN_H     = 820, 580
_LEFT_W  = 148
_RIGHT_W = 340

_OS = platform.system()  # "Windows" | "Darwin" | "Linux"


class C:
    BG        = "#000000"
    PANEL     = "#0d0d0d"
    PANEL2    = "#141414"
    BORDER    = "#222222"
    BORDER_B  = "#333333"
    BORDER_A  = "#2a2a2a"
    PRI       = "#ffffff"
    PRI_DIM   = "#666666"
    PRI_GHO   = "#111111"
    ACC       = "#7c8aff"
    ACC_DIM   = "#3d4480"
    ACC_GHO   = "#1e2040"
    GREEN     = "#88ff88"
    GREEN_D   = "#44aa44"
    RED       = "#ff4444"
    MUTED_C   = "#666666"
    TEXT      = "#ffffff"
    TEXT_DIM  = "#555555"
    TEXT_MED  = "#888888"
    WHITE     = "#ffffff"
    DARK      = "#000000"
    BAR_BG    = "#1a1a1a"

_FONT = "Cantarell"
_FONT_SZ = 10
_FONT_SZ_SM = 9
_FONT_SZ_XS = 8


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
        if now - self._last_t > (0.12 if self.speaking else 0.5):
            if self.speaking:
                self._tgt_scale = random.uniform(1.06, 1.14)
                self._tgt_halo  = random.uniform(145, 190)
            elif self.muted:
                self._tgt_scale = random.uniform(0.998, 1.002)
                self._tgt_halo  = random.uniform(15, 28)
            else:
                self._tgt_scale = random.uniform(1.001, 1.008)
                self._tgt_halo  = random.uniform(48, 68)
            self._last_t = now

        sp = 0.38 if self.speaking else 0.15
        self._scale += (self._tgt_scale - self._scale) * sp
        self._halo  += (self._tgt_halo  - self._halo)  * sp

        speeds = [1.3, -0.9, 2.0] if self.speaking else [0.55, -0.35, 0.9]
        for i, spd in enumerate(speeds):
            self._rings[i] = (self._rings[i] + spd) % 360

        self._scan  = (self._scan  + (3.0 if self.speaking else 1.3)) % 360
        self._scan2 = (self._scan2 + (-2.0 if self.speaking else -0.75)) % 360

        fw  = min(self.width(), self.height())
        lim = fw * 0.74
        spd = 4.2 if self.speaking else 2.0
        self._pulses = [r + spd for r in self._pulses if r + spd < lim]
        if len(self._pulses) < 3 and random.random() < (0.07 if self.speaking else 0.025):
            self._pulses.append(0.0)

        if self.speaking and random.random() < 0.28:
            cx, cy = self.width() / 2, self.height() / 2
            ang = random.uniform(0, 2 * math.pi)
            r_s = fw * 0.28
            self._particles.append([
                cx + math.cos(ang) * r_s, cy + math.sin(ang) * r_s,
                math.cos(ang) * random.uniform(0.9, 2.4),
                math.sin(ang) * random.uniform(0.9, 2.4) - 0.4, 1.0,
            ])
        self._particles = [
            [p[0]+p[2], p[1]+p[3], p[2]*0.97, p[3]*0.97, p[4]-0.028]
            for p in self._particles if p[4] > 0
        ]

        self._blink_tick += 1
        if self._blink_tick >= 38:
            self._blink = not self._blink
            self._blink_tick = 0
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), qcol(C.BG))

        W, H = self.width(), self.height()
        cx, cy = W / 2, H / 2
        fw = min(W, H)

        # subtle grid dots
        p.setPen(QPen(qcol(C.PRI_GHO), 1))
        for x in range(0, W, 56):
            for y in range(0, H, 56):
                p.drawPoint(x, y)

        r_face = fw * 0.31

        # halo glow — grayscale rings
        for i in range(6):
            r   = r_face * (1.6 - i * 0.10)
            frc = 1.0 - i / 6
            a   = max(0, min(255, int(self._halo * 0.07 * frc)))
            col = qcol(C.PRI_DIM, a)
            p.setPen(QPen(col, 1.2)); p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))

        # pulse rings
        for pr in self._pulses:
            a   = max(0, int(180 * (1.0 - pr / (fw * 0.74))))
            col = qcol(C.PRI_DIM, a)
            p.setPen(QPen(col, 1.2)); p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QRectF(cx - pr, cy - pr, pr * 2, pr * 2))

        # spinning arc rings — simplified, white/gray
        for idx, (r_frac, w_r, arc_l, gap) in enumerate(
            [(0.48, 2, 100, 85), (0.40, 1, 70, 60)]
        ):
            ring_r = fw * r_frac
            base   = self._rings[idx]
            a_val  = max(0, min(255, int(self._halo * (0.7 - idx * 0.15))))
            col    = qcol(C.PRI_DIM, a_val)
            p.setPen(QPen(col, w_r)); p.setBrush(Qt.BrushStyle.NoBrush)
            angle = base
            rect  = QRectF(cx - ring_r, cy - ring_r, ring_r * 2, ring_r * 2)
            while angle < base + 360:
                p.drawArc(rect, int(angle * 16), int(arc_l * 16))
                angle += arc_l + gap

        # scanner
        sr = fw * 0.50
        sa = min(255, int(self._halo * 1.2))
        ex = 60 if self.speaking else 40
        p.setPen(QPen(qcol(C.PRI_DIM, sa), 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        srect = QRectF(cx - sr, cy - sr, sr * 2, sr * 2)
        p.drawArc(srect, int(self._scan * 16), int(ex * 16))

        # tick marks
        t_out, t_in = fw * 0.497, fw * 0.478
        p.setPen(QPen(qcol(C.PRI_DIM, 100), 1))
        for deg in range(0, 360, 15):
            rad = math.radians(deg)
            inn = t_in if deg % 30 == 0 else t_in + 4
            p.drawLine(
                QPointF(cx + t_out * math.cos(rad), cy - t_out * math.sin(rad)),
                QPointF(cx + inn  * math.cos(rad), cy - inn  * math.sin(rad)),
            )

        # crosshair
        ch_r, gap_h = fw * 0.51, fw * 0.18
        p.setPen(QPen(qcol(C.PRI_DIM, int(self._halo * 0.4)), 1))
        p.drawLine(QPointF(cx - ch_r, cy), QPointF(cx - gap_h, cy))
        p.drawLine(QPointF(cx + gap_h, cy), QPointF(cx + ch_r, cy))
        p.drawLine(QPointF(cx, cy - ch_r), QPointF(cx, cy - gap_h))
        p.drawLine(QPointF(cx, cy + gap_h), QPointF(cx, cy + ch_r))

        # corner brackets
        bl = 18
        bc = qcol(C.PRI_DIM, 160)
        hl, hr = cx - fw // 2, cx + fw // 2
        ht, hb = cy - fw // 2, cy + fw // 2
        p.setPen(QPen(bc, 1.5))
        for bx, by, dx, dy in [(hl,ht,1,1),(hr,ht,-1,1),(hl,hb,1,-1),(hr,hb,-1,-1)]:
            p.drawLine(QPointF(bx, by), QPointF(bx + dx * bl, by))
            p.drawLine(QPointF(bx, by), QPointF(bx, by + dy * bl))

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
            orb_r = int(fw * 0.27 * self._scale)
            for i in range(6, 0, -1):
                r2  = int(orb_r * i / 6)
                frc = i / 6
                v   = min(255, int(80 * frc))
                a   = max(0, min(255, int(self._halo * 0.9 * frc)))
                p.setBrush(QBrush(QColor(v, v, v, a)))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(QRectF(cx - r2, cy - r2, r2 * 2, r2 * 2))
            p.setPen(QPen(qcol(C.TEXT_DIM, 180), 1))
            p.setFont(QFont("Courier New", 11, QFont.Weight.Bold))
            p.drawText(QRectF(cx - 80, cy - 14, 160, 28),
                       Qt.AlignmentFlag.AlignCenter, "J.A.R.V.I.S")

        # particles
        for pt in self._particles:
            a = max(0, min(255, int(pt[4] * 200)))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(qcol(C.TEXT_DIM, a)))
            p.drawEllipse(QPointF(pt[0], pt[1]), 2, 2)

        # status text — monochrome
        sy = cy + fw * 0.40
        if self.muted:
            txt = "⊘  MUTED"
        elif self.speaking:
            txt = "●  SPEAKING"
        elif self.state == "THINKING":
            sym = "◈" if self._blink else "◇"
            txt = f"{sym}  THINKING"
        elif self.state == "PROCESSING":
            sym = "▷" if self._blink else "▶"
            txt = f"{sym}  PROCESSING"
        elif self.state == "LISTENING":
            sym = "●" if self._blink else "○"
            txt = f"{sym}  LISTENING"
        else:
            sym = "●" if self._blink else "○"
            txt = f"{sym}  {self.state}"

        p.setPen(QPen(qcol(C.TEXT), 1))
        p.setFont(QFont("Courier New", 11, QFont.Weight.Bold))
        p.drawText(QRectF(0, sy, W, 26), Qt.AlignmentFlag.AlignCenter, txt)

        # waveform
        wy = sy + 30
        N, bw = 32, 7
        wx0 = (W - N * bw) / 2
        for i in range(N):
            if self.muted:
                hgt, cl = 2, qcol(C.TEXT_DIM)
            elif self.speaking:
                hgt = random.randint(3, 18)
                cl  = qcol(C.TEXT) if hgt > 10 else qcol(C.TEXT_DIM)
            else:
                hgt = int(3 + 2 * math.sin(self._tick * 0.09 + i * 0.6))
                cl  = qcol(C.BORDER)
            p.fillRect(QRectF(wx0 + i * bw, wy + 18 - hgt, bw - 1, hgt), cl)

class MetricBar(QWidget):

    def __init__(self, label: str, color: str = C.PRI, parent=None):
        super().__init__(parent)
        self._label = label
        self._color = color
        self._value = 0.0       # 0–100
        self._text  = "--"
        self.setFixedHeight(38)
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
        p.drawRoundedRect(QRectF(1, 1, W - 2, H - 2), 4, 4)

        bar_h   = 3
        bar_y   = H - bar_h - 5
        bar_w   = W - 12
        bar_x   = 6
        fill_w  = int(bar_w * self._value / 100)

        p.setBrush(QBrush(qcol(C.BAR_BG)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(bar_x, bar_y, bar_w, bar_h), 1.5, 1.5)

        a = max(60, min(255, int(100 + self._value * 1.5)))
        bar_col = qcol(C.WHITE, a)

        if fill_w > 0:
            p.setBrush(QBrush(bar_col))
            p.drawRoundedRect(QRectF(bar_x, bar_y, fill_w, bar_h), 1.5, 1.5)

        p.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.TEXT_DIM), 1))
        p.drawText(QRectF(8, 5, 50, 14), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self._label)

        p.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.TEXT) if self._text != "--" else qcol(C.TEXT_DIM), 1))
        p.drawText(QRectF(0, 4, W - 6, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, self._text)

class LogWidget(QTextEdit):
    _sig = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFont(QFont(_FONT, _FONT_SZ))
        self.setStyleSheet(f"""
            QTextEdit {{
                background: {C.PANEL};
                color: {C.TEXT};
                border: 1px solid {C.BORDER};
                border-radius: 6px;
                padding: 8px;
                selection-background-color: {C.ACC_GHO};
            }}
            QScrollBar:vertical {{
                background: {C.BG};
                width: 6px;
                border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {C.BORDER};
                border-radius: 3px;
                min-height: 20px;
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
        self._tmr.start(6)

    def _step(self):
        if self._pos < len(self._text):
            ch  = self._text[self._pos]
            cur = self.textCursor()
            fmt = cur.charFormat()
            col = {
                "you":  qcol(C.WHITE),
                "ai":   qcol(C.PRI),
                "err":  qcol(C.TEXT_DIM),
                "file": qcol(C.TEXT_MED),
                "sys":  qcol(C.TEXT_DIM),
            }.get(self._tag, qcol(C.TEXT))
            fmt.setForeground(QBrush(col))
            cur.movePosition(cur.MoveOperation.End)
            cur.insertText(ch, fmt)
            self.setTextCursor(cur)
            self.ensureCursorVisible()
            self._pos += 1
        else:
            self._tmr.stop()
            cur = self.textCursor()
            cur.movePosition(cur.MoveOperation.End)
            cur.insertText("\n")
            self.setTextCursor(cur)
            self.ensureCursorVisible()
            QTimer.singleShot(20, self._next)

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
        _init = initial or {}
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
        if mode == "config":
            layout.addWidget(_lbl("CONFIGURATION", 12, True))
            layout.addWidget(_lbl("Update J.A.R.V.I.S. settings and click Apply.", 8, col=C.PRI_DIM))
        else:
            layout.addWidget(_lbl("INITIALISATION REQUIRED", 12, True))
            layout.addWidget(_lbl("Configure J.A.R.V.I.S. before first boot.", 8, col=C.PRI_DIM))
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

        # ── LLM ──────────────────────────────────────────────────────── #
        layout.addWidget(_lbl("LOCAL LLM", 7, col=C.TEXT_DIM,
                               align=Qt.AlignmentFlag.AlignLeft))

        # Provider toggle: Ollama vs LM Studio / OpenAI-compatible vs NVIDIA NIM vs OpenRouter
        llm_prov_row, self._llm_prov_btns = _toggle_row(
            [
                ("ollama",       "Ollama"),
                ("openai",       "OpenAI / LM Studio"),
                ("nvidia_nim",   "NVIDIA NIM"),
                ("openrouter",   "OpenRouter"),
            ],
            lambda: self._sel_llm_provider,
            self._set_llm_provider,
        )
        layout.addLayout(llm_prov_row)

        # Hint label — changes based on provider
        _LLM_HINTS = {
            "ollama":     "ollama.com  ·  run: ollama pull qwen2.5:3b",
            "openai":     "lmstudio.ai  ·  start Local Server first, then pick model",
            "nvidia_nim": "build.nvidia.com  ·  requires NVIDIA API key",
            "openrouter": "openrouter.ai  ·  requires OpenRouter API key",
        }
        self._llm_hint_lbl = _lbl(
            _LLM_HINTS.get(self._sel_llm_provider, ""),
            7, col=C.TEXT_DIM, align=Qt.AlignmentFlag.AlignLeft
        )
        layout.addWidget(self._llm_hint_lbl)

        # LLM API key — shown only for cloud providers
        self._llm_api_key_widget = QWidget()
        self._llm_api_key_widget.setStyleSheet("background: transparent;")
        ak_row = QHBoxLayout(self._llm_api_key_widget)
        ak_row.setContentsMargins(0, 0, 0, 0)
        ak_row.setSpacing(5)
        ak_row.addWidget(_lbl("API Key:", 7, col=C.TEXT_MED,
                               align=Qt.AlignmentFlag.AlignRight))
        self._llm_api_key_input = _input("API key for cloud provider", pw=True)
        self._llm_api_key_input.setText(_init.get("llm_api_key", ""))
        ak_row.addWidget(self._llm_api_key_input)
        layout.addWidget(self._llm_api_key_widget)
        is_cloud_init = self._sel_llm_provider in ("nvidia_nim", "openrouter")
        self._llm_api_key_widget.setVisible(is_cloud_init)

        llm_row = QHBoxLayout(); llm_row.setSpacing(5)
        llm_row.addWidget(_lbl("URL:", 7, col=C.TEXT_MED,
                                align=Qt.AlignmentFlag.AlignRight))
        _LLM_DEFAULT_URLS = {
            "ollama":     "http://localhost:11434",
            "openai":     "http://localhost:1234",
            "nvidia_nim": "https://integrate.api.nvidia.com/v1",
            "openrouter": "https://openrouter.ai/api/v1",
        }
        _default_url = _init.get("llm_url",
                                  _LLM_DEFAULT_URLS.get(self._sel_llm_provider, "http://localhost:11434"))
        self._llm_url_input = _input("http://localhost:11434")
        self._llm_url_input.setText(_default_url)
        llm_row.addWidget(self._llm_url_input, stretch=2)
        llm_row.addWidget(_lbl("Model:", 7, col=C.TEXT_MED,
                                align=Qt.AlignmentFlag.AlignRight))
        self._llm_model_input = _input("e.g.  qwen2.5:3b  /  llama3.2  /  mistral")
        self._llm_model_input.setText(_init.get("llm_model", ""))
        llm_row.addWidget(self._llm_model_input, stretch=2)
        layout.addLayout(llm_row)

        # ── Test LLM connection ─────────────────────────────────────────── #
        test_row = QHBoxLayout(); test_row.setSpacing(5)
        self._test_btn = QPushButton("Test Connection")
        self._test_btn.setFixedHeight(30)
        self._test_btn.setFont(QFont(_FONT, 9, QFont.Weight.Bold))
        self._test_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._test_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 4px;
                padding: 4px 12px;
            }}
            QPushButton:hover {{
                background: {C.ACC_GHO}; border: 1px solid {C.ACC};
                color: {C.ACC};
            }}
            QPushButton:disabled {{
                color: {C.TEXT_DIM}; border: 1px solid {C.BORDER};
            }}
        """)
        self._test_btn.clicked.connect(self._test_connection)
        test_row.addWidget(self._test_btn)
        self._test_status = QLabel("")
        self._test_status.setFont(QFont("Courier New", 7))
        self._test_status.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        test_row.addWidget(self._test_status, stretch=1)
        layout.addLayout(test_row)

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

        # ElevenLabs key — only visible when ElevenLabs is selected
        self._el_key_widget = QWidget()
        self._el_key_widget.setStyleSheet("background: transparent;")
        el_row = QHBoxLayout(self._el_key_widget)
        el_row.setContentsMargins(0, 0, 0, 0)
        el_row.setSpacing(5)
        el_row.addWidget(_lbl("API Key:", 7, col=C.TEXT_MED,
                               align=Qt.AlignmentFlag.AlignRight))
        self._el_key_input = _input("ElevenLabs API key", pw=True)
        self._el_key_input.setText(_init.get("elevenlabs_api_key", ""))
        el_row.addWidget(self._el_key_input)
        layout.addWidget(self._el_key_widget)

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
        if hasattr(self, "_el_key_widget"):
            self._el_key_widget.setVisible(key == "elevenlabs")

    def _set_llm_provider(self, key: str):
        self._sel_llm_provider = key
        if not hasattr(self, "_llm_prov_btns"):
            return
        for k, btn in self._llm_prov_btns.items():
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
        _LLM_HINTS = {
            "ollama":     "ollama.com  ·  run: ollama pull qwen2.5:3b",
            "openai":     "lmstudio.ai  ·  start Local Server first, then pick model",
            "nvidia_nim": "build.nvidia.com  ·  requires NVIDIA API key",
            "openrouter": "openrouter.ai  ·  requires OpenRouter API key",
        }
        _LLM_URLS = {
            "ollama":     "http://localhost:11434",
            "openai":     "http://localhost:1234",
            "nvidia_nim": "https://integrate.api.nvidia.com/v1",
            "openrouter": "https://openrouter.ai/api/v1",
        }
        # Show/hide API key field for cloud providers
        is_cloud = key in ("nvidia_nim", "openrouter")
        if hasattr(self, "_llm_api_key_widget"):
            self._llm_api_key_widget.setVisible(is_cloud)
        # Update URL placeholder and text
        if hasattr(self, "_llm_url_input"):
            new_url = _LLM_URLS.get(key, "http://localhost:11434")
            self._llm_url_input.setPlaceholderText(new_url)
            cur = self._llm_url_input.text().strip()
            if not cur or cur in _LLM_URLS.values():
                self._llm_url_input.setText(new_url)
        if hasattr(self, "_llm_hint_lbl"):
            self._llm_hint_lbl.setText(_LLM_HINTS.get(key, ""))

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
        self._test_btn.setEnabled(False)
        self._test_status.setText("Testing…")
        self._test_status.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        QApplication.processEvents()
        threading.Thread(target=self._do_test, daemon=True).start()

    def _do_test(self):
        url  = self._llm_url_input.text().strip().rstrip("/")
        provider = getattr(self, "_sel_llm_provider", "ollama")
        msg = ""

        try:
            import requests as _req
            if provider == "ollama":
                resp = _req.get(f"{url}/api/tags", timeout=8)
                if resp.status_code == 200:
                    models = (resp.json().get("models") or [])
                    model = self._llm_model_input.text().strip()
                    found = any(
                        model in (m.get("name") or m.get("model") or "")
                        for m in models
                    )
                    if found:
                        msg = f"✅  Connected · '{model}' available"
                    else:
                        names = [m.get("name", "?") for m in models][:6]
                        hint = ", ".join(names) if names else "none pulled"
                        msg = f"⚠️  Connected · '{model}' not found · pulled: {hint}"
                else:
                    msg = f"❌  Server returned {resp.status_code}"
            else:
                headers = {}
                key = self._llm_api_key_input.text().strip() if hasattr(self, "_llm_api_key_input") else ""
                if key:
                    headers["Authorization"] = f"Bearer {key}"
                if provider == "openrouter":
                    headers["HTTP-Referer"] = "https://github.com/anomalyco/opencode"
                    headers["X-Title"] = "MARK XL"
                ep = f"{url}/v1/models" if "/v1" in url else f"{url}/v1/models"
                resp = _req.get(ep, headers=headers, timeout=8)
                if resp.status_code in (200, 401):
                    if resp.status_code == 200:
                        models = resp.json().get("data", [])
                        model = self._llm_model_input.text().strip()
                        found = any(
                            model in (m.get("id") or "")
                            for m in models
                        )
                        if found:
                            msg = f"✅  Connected · '{model}' available"
                        else:
                            msg = f"⚠️  Connected · model list returned ({len(models)} available)"
                    else:
                        msg = "✅  Server reachable (auth required — key format looks right)"
                else:
                    msg = f"❌  Server returned {resp.status_code}"
        except Exception as e:
            msg = f"❌  {type(e).__name__}: {e}"

        self._test_status.setText(msg)
        is_ok = msg.startswith("✅")
        self._test_status.setStyleSheet(
            f"color: {C.TEXT if is_ok else C.TEXT_DIM}; background: transparent;"
        )
        self._test_btn.setEnabled(True)

    def _submit(self):
        llm_model = self._llm_model_input.text().strip()
        if not llm_model:
            self._llm_model_input.setStyleSheet(
                self._llm_model_input.styleSheet() +
                f" QLineEdit {{ border: 1px solid {C.TEXT_DIM}; }}"
            )
            return

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

        _provider = getattr(self, "_sel_llm_provider", "ollama")
        _LLM_DEFAULT_URLS = {
            "ollama":     "http://localhost:11434",
            "openai":     "http://localhost:1234",
            "nvidia_nim": "https://integrate.api.nvidia.com/v1",
            "openrouter": "https://openrouter.ai/api/v1",
        }
        _default_url = _LLM_DEFAULT_URLS.get(_provider, "http://localhost:11434")
        cfg = {
            "stt_engine":         self._sel_stt,
            "stt_model":          stt_model,
            "stt_language":       self._stt_lang_input.text().strip() or "auto",
            "llm_provider":       _provider,
            "llm_url":            self._llm_url_input.text().strip() or _default_url,
            "llm_model":          llm_model,
            "llm_api_key":        self._llm_api_key_input.text().strip() if hasattr(self, "_llm_api_key_input") else "",
            "tts_engine":         self._sel_tts,
            "tts_voice":          tts_voice,
            "tts_speed":          tts_speed,
            "elevenlabs_api_key": self._el_key_input.text().strip(),
        }
        if self._sel_stt == "vosk" and stt_model:
            cfg["vosk_model_path"] = stt_model
        self.done.emit(json.dumps(cfg))


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
        self._loading.setText(text)
        QApplication.processEvents()

    def _loading_off(self):
        self._loading.setText("")

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
            emails = asyncio.run(gws_bridge.get_unread_emails(limit=10))
            if not isinstance(emails, list):
                emails = []
            self._main_window._log_sig.emit(f"GWS: {len(emails)} unread emails")
        except Exception as e:
            emails = []
            self._main_window._log_sig.emit(f"GWS: email fetch failed — {e}")
        self._update_gmail_ui(emails)

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
            events = asyncio.run(gws_bridge.get_todays_agenda())
            if not isinstance(events, list):
                events = []
            self._main_window._log_sig.emit(f"GWS: {len(events)} agenda items")
        except Exception as e:
            events = []
            self._main_window._log_sig.emit(f"GWS: calendar fetch failed — {e}")
        self._update_cal_ui(events)

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
            files = asyncio.run(gws_bridge.search_files(query=query))
            if not isinstance(files, list):
                files = []
            self._main_window._log_sig.emit(f"GWS: {len(files)} drive files found")
        except Exception as e:
            files = []
            self._main_window._log_sig.emit(f"GWS: drive search failed — {e}")
        self._update_drive_ui(files)

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
                ev = asyncio.run(gws_bridge.create_meet(
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
                self._loading_off()
            except Exception as e:
                self._main_window._log_sig.emit(f"GWS: Meet creation failed — {e}")
                self._loading_off()
        threading.Thread(target=_do, daemon=True).start()

    def _open_meet(self, url: str):
        import webbrowser
        webbrowser.open(url)

    def _delete_event(self, event_id: str):
        def _do():
            try:
                import gws_bridge
                asyncio.run(gws_bridge.delete_event(event_id=event_id))
                self._main_window._log_sig.emit(f"GWS: Event {event_id} deleted")
                self._refresh_calendar()
            except Exception as e:
                self._main_window._log_sig.emit(f"GWS: delete failed — {e}")
        threading.Thread(target=_do, daemon=True).start()


class MainWindow(QMainWindow):
    _log_sig     = pyqtSignal(str)
    _state_sig   = pyqtSignal(str)
    _loc_sig     = pyqtSignal(str)
    _startup_sig = pyqtSignal(str, str)  # action, data — thread-safe startup panel control

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

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        self._left_panel = self._build_left_panel()
        body.addWidget(self._left_panel, stretch=0)

        self.hud = HudCanvas(face_path)
        self.hud.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.hud.clicked.connect(self._on_hud_clicked)
        body.addWidget(self.hud, stretch=5)

        self._right_panel = self._build_right_panel()
        body.addWidget(self._right_panel, stretch=0)

        if hasattr(self, '_ws_panel'):
            self._ws_panel.set_main_window(self)

        root.addLayout(body, stretch=1)
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

        self._log_sig.connect(self._log.append_log)
        self._state_sig.connect(self._apply_state)
        self._loc_sig.connect(self._update_location)
        self._startup_sig.connect(self._on_startup_sig)

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


    def _build_header(self) -> QWidget:
        w = QWidget()
        w.setObjectName("header_widget")
        w.setFixedHeight(44)
        w.setStyleSheet(f"background: {C.PANEL}; border-bottom: 1px solid {C.BORDER};")
        lay = QHBoxLayout(w)
        lay.setContentsMargins(14, 0, 14, 0)

        title = QLabel("J.A.R.V.I.S")
        title.setFont(QFont("Courier New", 12, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {C.WHITE}; background: transparent;")
        lay.addWidget(title)
        lay.addStretch()

        right_col = QVBoxLayout(); right_col.setSpacing(2)
        self._clock_lbl = QLabel("00:00")
        self._clock_lbl.setFont(QFont("Courier New", 12, QFont.Weight.Bold))
        self._clock_lbl.setStyleSheet(f"color: {C.WHITE}; background: transparent;")
        self._clock_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        right_col.addWidget(self._clock_lbl)
        self._date_lbl = QLabel("")
        self._date_lbl.setFont(QFont("Courier New", 7))
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
        w.setFixedWidth(_LEFT_W)
        w.setStyleSheet(f"background: {C.BG}; border-right: 1px solid {C.BORDER};")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 10, 8, 10)
        lay.setSpacing(5)

        self._bar_cpu = MetricBar("CPU")
        self._bar_mem = MetricBar("MEM")
        self._bar_net = MetricBar("NET")
        self._bar_gpu = MetricBar("GPU")
        self._bar_tmp = MetricBar("TMP")

        for bar in [self._bar_cpu, self._bar_mem, self._bar_net,
                    self._bar_gpu, self._bar_tmp]:
            lay.addWidget(bar)

        lay.addSpacing(6)

        info_panel = QWidget()
        info_panel.setStyleSheet(
            f"background: {C.PANEL2}; border: 1px solid {C.BORDER}; border-radius: 4px;"
        )
        ip_lay = QVBoxLayout(info_panel)
        ip_lay.setContentsMargins(6, 5, 6, 5)
        ip_lay.setSpacing(3)

        self._uptime_lbl = QLabel("UP  --:--")
        self._uptime_lbl.setFont(QFont("Courier New", 8))
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

        lay.addWidget(info_panel)
        lay.addStretch()

        return w
    def _build_right_panel(self) -> QWidget:
        w = QWidget()
        w.setFixedWidth(_RIGHT_W)
        w.setStyleSheet(f"background: {C.BG}; border-left: 1px solid {C.BORDER};")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        # ── Mode toggle bar ─────────────────────────────────────────────
        mode_row = QHBoxLayout(); mode_row.setSpacing(4)
        self._mode_log_btn = QPushButton("Log")
        self._mode_log_btn.setFixedHeight(26)
        self._mode_log_btn.setFont(QFont(_FONT, _FONT_SZ_SM))
        self._mode_log_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._mode_log_btn.clicked.connect(lambda: self._set_right_mode(0))
        self._mode_log_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 4px;
                padding: 2px 10px;
            }}
            QPushButton:hover {{ color: {C.ACC}; border: 1px solid {C.ACC}; }}
        """)
        mode_row.addWidget(self._mode_log_btn)

        self._mode_ws_btn = QPushButton("Workspace")
        self._mode_ws_btn.setFixedHeight(26)
        self._mode_ws_btn.setFont(QFont(_FONT, _FONT_SZ_SM))
        self._mode_ws_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._mode_ws_btn.clicked.connect(lambda: self._set_right_mode(1))
        self._mode_ws_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 4px;
                padding: 2px 10px;
            }}
            QPushButton:hover {{ color: {C.ACC}; border: 1px solid {C.ACC}; }}
        """)
        mode_row.addWidget(self._mode_ws_btn)

        mode_row.addStretch()
        lay.addLayout(mode_row)

        # ── Stack: LOG ↔ WORKSPACE ─────────────────────────────────────
        self._right_stack = QStackedWidget()
        self._right_stack.setStyleSheet("background: transparent;")

        self._log = LogWidget()
        self._right_stack.addWidget(self._log)

        self._ws_panel = WorkspacePanel()
        self._right_stack.addWidget(self._ws_panel)

        lay.addWidget(self._right_stack, stretch=1)

        # ── Input ──────────────────────────────────────────────────────
        self._input = QLineEdit()
        self._input.setPlaceholderText("Type a command or question…")
        self._input.setFont(QFont(_FONT, _FONT_SZ))
        self._input.setFixedHeight(38)
        self._input.setStyleSheet(f"""
            QLineEdit {{
                background: {C.PANEL2}; color: {C.WHITE};
                border: 1px solid {C.BORDER}; border-radius: 6px; padding: 4px 10px;
            }}
            QLineEdit:focus {{ border: 1px solid {C.ACC}; }}
        """)
        self._input.returnPressed.connect(self._send)
        lay.addWidget(self._input)

        # ── Buttons ────────────────────────────────────────────────────
        btn_row = QHBoxLayout(); btn_row.setSpacing(4)
        self._mute_btn = QPushButton("Mic")
        self._mute_btn.setFixedHeight(30)
        self._mute_btn.setFont(QFont(_FONT, _FONT_SZ_SM))
        self._mute_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._mute_btn.clicked.connect(self._toggle_mute)
        self._style_mute_btn()
        btn_row.addWidget(self._mute_btn)

        for label, cb in [
            ("Fullscreen", self._toggle_fullscreen),
            ("Settings", self._show_config),
            ("Island", self._toggle_island),
        ]:
            btn = QPushButton(label)
            btn.setFixedHeight(30)
            btn.setFont(QFont(_FONT, _FONT_SZ_SM))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {C.TEXT_DIM};
                    border: 1px solid {C.BORDER}; border-radius: 4px;
                    padding: 2px 10px;
                }}
                QPushButton:hover {{ color: {C.ACC}; border: 1px solid {C.ACC}; }}
            """)
            btn.clicked.connect(cb)
            btn_row.addWidget(btn)

        btn_row.addStretch()
        lay.addLayout(btn_row)

        self._set_right_mode(0)
        return w

    def _set_right_mode(self, idx: int):
        self._right_stack.setCurrentIndex(idx)
        active = f"background: {C.PANEL2}; color: {C.TEXT}; border: 1px solid {C.TEXT_DIM}; border-radius: 3px;"
        inactive = f"background: transparent; color: {C.TEXT_DIM}; border: 1px solid {C.BORDER}; border-radius: 3px;"
        self._mode_log_btn.setStyleSheet(f"QPushButton {{ {active if idx == 0 else inactive} }}")
        self._mode_ws_btn.setStyleSheet(f"QPushButton {{ {active if idx == 1 else inactive} }}")

    def _build_input_row(self) -> QHBoxLayout:
        row = QHBoxLayout(); row.setSpacing(5)
        self._input = QLineEdit()
        self._input.setPlaceholderText("Type a command or question…")
        self._input.setFont(QFont("Courier New", 9))
        self._input.setFixedHeight(30)
        self._input.setStyleSheet(f"""
            QLineEdit {{
                background: {C.PANEL2}; color: {C.TEXT};
                border: 1px solid {C.BORDER}; border-radius: 3px; padding: 3px 7px;
            }}
            QLineEdit:focus {{ border: 1px solid {C.TEXT_DIM}; }}
        """)
        self._input.returnPressed.connect(self._send)
        row.addWidget(self._input)

        send = QPushButton("▸")
        send.setFixedSize(30, 30)
        send.setFont(QFont("Courier New", 11, QFont.Weight.Bold))
        send.setCursor(Qt.CursorShape.PointingHandCursor)
        send.setStyleSheet(f"""
            QPushButton {{
                background: {C.PANEL}; color: {C.PRI};
                border: 1px solid {C.PRI_DIM}; border-radius: 3px;
            }}
            QPushButton:hover {{ background: {C.PRI_GHO}; border: 1px solid {C.PRI}; }}
        """)
        send.clicked.connect(self._send)
        row.addWidget(send)
        return row

    def _build_footer(self) -> QWidget:
        w = QWidget()
        w.setObjectName("footer_widget")
        w.setFixedHeight(20)
        w.setStyleSheet(f"background: {C.BG}; border-top: 1px solid {C.BORDER};")
        lay = QHBoxLayout(w); lay.setContentsMargins(14, 0, 14, 0)
        l = QLabel("MARK XL  ·  [F4] Mute  ·  [F11] FS  ·  [F12] Island")
        l.setFont(QFont("Courier New", 7))
        l.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        lay.addWidget(l)
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

    def _send(self):
        txt = self._input.text().strip()
        if not txt: return
        self._input.clear()
        if self.on_text_command:
            threading.Thread(target=self.on_text_command, args=(txt,), daemon=True).start()

    def _apply_state(self, state: str):
        self.hud.state    = state
        self.hud.speaking = (state == "SPEAKING")

    def _check_config(self) -> bool:
        if not API_FILE.exists(): return False
        try:
            d = json.loads(API_FILE.read_text(encoding="utf-8"))
            return (
                bool(d.get("llm_model")) and
                bool(d.get("stt_engine")) and
                bool(d.get("tts_engine"))
            )
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

    def write_log(self, text: str):
        self._win._log_sig.emit(text)

    def set_location(self, loc_text: str):
        self._win._loc_sig.emit(loc_text)

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
