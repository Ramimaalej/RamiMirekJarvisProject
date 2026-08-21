"""Ollama Models Page — browse, install and delete Ollama models from the UI.

A simple one-page overlay:
  * left   : your INSTALLED models (delete with one click)
  * right  : MODEL LIBRARY — pick and install with one click
  * bottom : live download progress

Style matches SetupOverlay / ProviderOverlay.
"""
from __future__ import annotations

import json
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit, QPushButton,
    QScrollArea, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QFrame,
)

from core.ollama_models import (
    OLLAMA_LIBRARY, ANY_MODEL_NOTE, delete_model, list_local_models,
    pull_model, is_running, current_model,
)


def _C():
    import ui as _ui
    return _ui.C


def _font():
    import ui as _ui
    return _ui._FONT


def _config() -> dict:
    try:
        return json.loads(Path("config/api_keys.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


class OllamaModelsOverlay(QWidget):
    """No done signal — it acts directly on the Ollama server and config."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        C = _C()
        self.setStyleSheet(f"""
            OllamaModelsOverlay {{
                background: #000000;
                border: 2px solid #ffffff;
                border-radius: 0px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(8)

        # ── Header ────────────────────────────────────────────────────────
        header = QHBoxLayout()
        title = QLabel("OLLAMA MODELS")
        title.setFont(QFont("Courier New", 12, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        self._server_lbl = QLabel("checking Ollama…")
        self._server_lbl.setFont(QFont("Courier New", 8))
        self._server_lbl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self._server_lbl)
        layout.addLayout(header)
        layout.addWidget(_sep())

        # ── Content: installed | library ──────────────────────────────────
        content = QHBoxLayout()
        content.setSpacing(12)

        # Installed (left)
        left = QVBoxLayout()
        left.addWidget(_sub("INSTALLED", C.GREEN))
        self._tbl = QTableWidget()
        self._tbl.setShowGrid(False)
        self._tbl.setColumnCount(3)
        self._tbl.setHorizontalHeaderLabels(["MODEL", "SIZE", "ACTION"])
        self._tbl.verticalHeader().setVisible(False)
        self._tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._tbl.setAlternatingRowColors(True)
        self._tbl.setStyleSheet(f"""
            QTableWidget {{
                background: {C.PANEL}; color: {C.TEXT};
                border: 1px solid {C.BORDER}; border-radius: 0px;
                gridline-color: {C.BORDER}; font-family: '{_font()}';
                font-size: 9pt;
            }}
            QTableWidget::item {{ padding: 4px 8px; }}
            QHeaderView::section {{
                background: {C.PANEL2}; color: {C.TEXT_MED};
                border: none; border-bottom: 1px solid {C.BORDER};
                padding: 4px 8px; font-weight: bold; font-family: 'Courier New';
            }}
        """)
        h = self._tbl.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self._tbl.setColumnWidth(1, 80)
        self._tbl.setColumnWidth(2, 90)
        left.addWidget(self._tbl, stretch=1)
        self._lbl_current = QLabel("")
        self._lbl_current.setFont(QFont("Courier New", 7))
        self._lbl_current.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
        left.addWidget(self._lbl_current)
        content.addLayout(left, stretch=1)

        # Library (right)
        right = QVBoxLayout()
        right.addWidget(_sub("MODEL LIBRARY — ONE-CLICK INSTALL", C.ACC))
        lib_scroll = QScrollArea()
        lib_scroll.setWidgetResizable(True)
        lib_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        lib_scroll.setStyleSheet("background: transparent; border: none;")
        lib_inner = QWidget()
        lib_inner.setStyleSheet("background: transparent;")
        self._lib_lay = QVBoxLayout(lib_inner)
        self._lib_lay.setContentsMargins(0, 0, 0, 0)
        self._lib_lay.setSpacing(4)
        for entry in OLLAMA_LIBRARY:
            self._lib_lay.addWidget(self._lib_row(entry))
        self._lib_lay.addStretch()
        lib_scroll.setWidget(lib_inner)
        right.addWidget(lib_scroll, stretch=1)

        # Any model row
        any_row = QHBoxLayout()
        self._any_input = QLineEdit()
        self._any_input.setPlaceholderText(ANY_MODEL_NOTE)
        self._any_input.setFixedHeight(28)
        self._any_input.setStyleSheet(f"""
            QLineEdit {{
                background: {C.PANEL2}; color: {C.TEXT};
                border: 1px solid {C.BORDER}; border-radius: 0px; padding: 4px 8px;
                font-family: '{_font()}'; font-size: 9pt;
            }}
            QLineEdit:focus {{ border: 1px solid {C.ACC}; }}
        """)
        install_any = QPushButton("INSTALL CUSTOM")
        install_any.setFixedHeight(28)
        install_any.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        install_any.setCursor(Qt.CursorShape.PointingHandCursor)
        install_any.setStyleSheet(_btn_style(C.ACC))
        install_any.clicked.connect(self._install_custom)
        any_row.addWidget(self._any_input, stretch=1)
        any_row.addWidget(install_any)
        right.addLayout(any_row)
        content.addLayout(right, stretch=1)

        layout.addLayout(content, stretch=1)
        layout.addWidget(_sep())

        # ── Progress line ─────────────────────────────────────────────────
        self._progress_lbl = QLabel("Ready.")
        self._progress_lbl.setFont(QFont("Courier New", 8))
        self._progress_lbl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
        layout.addWidget(self._progress_lbl)

        # ── Footer ────────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setFont(QFont(_font(), 10))
        refresh_btn.setFixedHeight(34)
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.setStyleSheet(_btn_style(C.TEXT_MED))
        refresh_btn.clicked.connect(self._refresh)
        btn_row.addWidget(refresh_btn)
        btn_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setFont(QFont(_font(), 10, QFont.Weight.Bold))
        close_btn.setFixedHeight(34)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(_btn_style(C.ACC))
        close_btn.clicked.connect(self.hide)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        self._installing: dict[str, QPushButton] = {}
        self._refresh()

    # ------------------------------------------------------------------ #
    def _refresh(self):
        C = _C()
        up = is_running()
        self._server_lbl.setText("● Ollama online" if up else "○ Ollama offline — start: ollama serve")
        self._server_lbl.setStyleSheet(
            f"color: {C.GREEN if up else C.RED}; background: transparent;")
        models = list_local_models(_config()) if up else []
        cur = current_model(_config())
        self._lbl_current.setText(f"Currently active model: {cur or '—'}")
        self._tbl.setRowCount(len(models))
        for r, m in enumerate(models):
            cell = QTableWidgetItem(m["id"])
            cell.setFont(QFont("Courier New", 9))
            self._tbl.setItem(r, 0, cell)
            size = QTableWidgetItem(f"{m['size_gb']} GB")
            size.setFont(QFont("Courier New", 8))
            size.setForeground(C.TEXT_MED)
            self._tbl.setItem(r, 1, size)
            del_btn = QPushButton("DELETE")
            del_btn.setFixedSize(70, 22)
            del_btn.setFont(QFont("Courier New", 6, QFont.Weight.Bold))
            del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            del_btn.setStyleSheet(_btn_style(C.RED))
            mid = m["id"]
            del_btn.clicked.connect(lambda _, m=mid: self._confirm_delete(m))
            self._tbl.setCellWidget(r, 2, del_btn)

    def _lib_row(self, entry: dict) -> QWidget:
        C = _C()
        mid = entry["id"]
        row = QWidget()
        row.setStyleSheet("background: transparent;")
        lay = QHBoxLayout(row)
        lay.setContentsMargins(8, 4, 8, 4)
        name_lbl = QLabel(entry["name"])
        name_lbl.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        name_lbl.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        desc_lbl = QLabel(entry["desc"])
        desc_lbl.setFont(QFont("Courier New", 7))
        desc_lbl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
        btn = QPushButton("INSTALL")
        btn.setFixedSize(76, 24)
        btn.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(_btn_style(C.ACC))
        btn.clicked.connect(lambda _, m=mid: self._install(m, btn))
        self._installing[mid] = btn
        lay.addWidget(name_lbl)
        lay.addWidget(desc_lbl, stretch=1)
        lay.addWidget(btn)
        return row

    # ------------------------------------------------------------------ #
    def _install(self, mid: str, btn: QPushButton):
        C = _C()
        if mid in self._installing and self._installing[mid].text() == "INSTALLING…":
            return
        btn.setText("INSTALLING…")
        btn.setEnabled(False)
        btn.setStyleSheet(_btn_style(C.ACC_DIM))
        self._progress_lbl.setText(f"Installing {mid}…")

        def on_log(line: str):
            self._progress_lbl.setText(line)

        def on_done(ok: bool, msg: str):
            self._progress_lbl.setText(msg)
            if mid in self._installing:
                self._installing[mid].setText("INSTALLED" if ok else "FAILED")
            self._refresh()

        pull_model(mid, on_log=on_log, on_done=on_done)

    def _install_custom(self):
        mid = self._any_input.text().strip()
        if not mid:
            self._progress_lbl.setText("Type a model name first (e.g. llama3.3:70b)")
            return
        self._progress_lbl.setText(f"Installing {mid}…")

        def on_log(line: str):
            self._progress_lbl.setText(line)

        def on_done(ok: bool, msg: str):
            self._progress_lbl.setText(msg)
            self._refresh()

        pull_model(mid, on_log=on_log, on_done=on_done)
        self._any_input.clear()

    def _confirm_delete(self, mid: str):
        C = _C()
        ok, _ = QInputDialog.getText(
            self, "Delete model",
            f"Type \"{mid}\" to confirm deletion:",
        )
        if ok and ok.strip() == mid:
            ok2, msg = delete_model(mid)
            self._progress_lbl.setText(msg)
            self._refresh()

    # ------------------------------------------------------------------ #

def _sep():
    C = _C()
    s = QFrame(); s.setFrameShape(QFrame.Shape.HLine)
    s.setStyleSheet(f"color: {C.BORDER}; margin: 2px 0;")
    return s


def _sub(text: str, color: str):
    C = _C()
    lbl = QLabel(text)
    lbl.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
    lbl.setStyleSheet(f"color: {color}; background: transparent;")
    return lbl


def _btn_style(color: str, hover: str | None = None):
    C = _C()
    hover = hover or color
    return f"""
        QPushButton {{
            background: {color}; color: {C.WHITE};
            border: none; border-radius: 0px;
        }}
        QPushButton:hover {{ background: {hover}; }}
        QPushButton:disabled {{ background: {C.BORDER}; color: {C.TEXT_MED}; }}
    """
