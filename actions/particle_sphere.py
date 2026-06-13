"""
ParticleSphereWidget — PyQt6 animated 3D particle sphere.

Pure QPainter implementation. No OpenGL, no external 3D libraries.
~1000 glowing cyan-teal dots on a black background, auto-rotating.
"""

from __future__ import annotations

import math
import random

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QPainter, QPaintEvent
from PyQt6.QtWidgets import QWidget


class ParticleSphereWidget(QWidget):
    """Animated 3D particle sphere widget. Drop into any QLayout."""

    def __init__(
        self,
        parent: QWidget | None = None,
        num_particles: int = 1000,
        color: str = "#00E5CC",
        speed: float = 0.6,
    ):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)

        self._num = max(200, min(2000, num_particles))
        self._color_hex = color
        self._speed = speed
        self._yaw = 0.0
        self._bg_color = QColor(0x0A, 0x0A, 0x0A)

        self._points_3d: list[tuple[float, float, float]] = []
        self._generate_points()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.start(16)

    # ── Public API ────────────────────────────────────────────────────

    def set_color(self, hex_color: str) -> None:
        self._color_hex = hex_color

    def set_speed(self, speed: float) -> None:
        self._speed = max(0.0, speed)

    def set_num_particles(self, n: int) -> None:
        self._num = max(200, min(2000, n))
        self._generate_points()

    # ── Internal ──────────────────────────────────────────────────────

    def _generate_points(self) -> None:
        """Fibonacci sphere: evenly distributes N points on a unit sphere."""
        n = self._num
        pts: list[tuple[float, float, float]] = []
        golden = math.pi * (3.0 - math.sqrt(5.0))
        for i in range(n):
            y = 1.0 - (i / (n - 1)) * 2.0
            radius = math.sqrt(1.0 - y * y)
            theta = golden * i
            x = radius * math.cos(theta)
            z = radius * math.sin(theta)
            pts.append((x, y, z))
        random.shuffle(pts)
        self._points_3d = pts

    def _tick(self) -> None:
        self._yaw += self._speed * 0.02
        if self._yaw > math.tau:
            self._yaw -= math.tau
        self.update()

    def _project(
        self, x: float, y: float, z: float, cx: float, cy: float, scale: float
    ) -> tuple[float, float, float]:
        """Perspective projection: 3D → 2D. Returns (sx, sy, depth_z)."""
        d = 3.0
        factor = d / (d + z)
        sx = cx + x * scale * factor
        sy = cy - y * scale * factor
        return sx, sy, factor

    def paintEvent(self, event: QPaintEvent) -> None:
        w = self.width()
        h = self.height()
        cx = w / 2.0
        cy = h / 2.0
        scale = min(w, h) * 0.38

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.fillRect(self.rect(), self._bg_color)

        cos_y = math.cos(self._yaw)
        sin_y = math.sin(self._yaw)

        color = QColor(self._color_hex)

        for x, y, z in self._points_3d:
            rx = x * cos_y + z * sin_y
            rz = -x * sin_y + z * cos_y

            sx, sy, depth = self._project(rx, y, rz, cx, cy, scale)

            if not (0 <= sx <= w and 0 <= sy <= h):
                continue

            radius = max(0.8, depth * 2.8)
            alpha = int(max(60, min(255, depth * 255)))

            color.setAlpha(alpha)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)

            if radius < 1.5:
                painter.drawRect(int(sx), int(sy), 1, 1)
            else:
                painter.drawEllipse(int(sx), int(sy), int(radius), int(radius))

        painter.end()
