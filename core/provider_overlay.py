"""Provider Overlay — simple one-screen LLM provider selector.

Pick a provider (Ollama / Groq / NVIDIA NIM / OpenRouter / OpenAI) and a
model — that's it. Models are auto-detected when the provider is reachable;
a curated short list is always available so the user never sees an empty
dropdown. Optionally enter an API key when the provider needs one.

Style matches SetupOverlay / ConnectionsOverlay in ui.py.
"""
from __future__ import annotations

import json
import logging
import sys
import threading
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea,
    QVBoxLayout, QWidget, QFrame,
)

from core.llm_provider_detector import (
    PROVIDERS, get_provider, list_models, is_reachable, DEFAULT_MODELS,
)

logger = logging.getLogger("provider_overlay")

# ---------------------------------------------------------------------------
# Helpers reusing ui.py design tokens (imported lazily to avoid cycles)
# ---------------------------------------------------------------------------
def _C():
    # C lives in ui.py — import at use time (ProviderOverlay is created from ui.py)
    import ui as _ui
    return _ui.C


def _font():
    import ui as _ui
    return _ui._FONT


class ProviderOverlay(QWidget):
    # Emits JSON: {"llm_provider": ..., "llm_model": ..., "llm_url": ...,
    #             "<key_field>": ..., "llm_api_key": ...}
    done = pyqtSignal(str)

    def __init__(self, parent=None, initial: dict | None = None):
        super().__init__(parent)
        self._init = initial or {}
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        C = _C()
        self.setStyleSheet(f"""
            ProviderOverlay {{
                background: rgba(0, 0, 0, 248);
                border: 1px solid {C.BORDER};
                border-radius: 8px;
            }}
        """)

        self._discovery: dict = {}        # pid -> status dict
        self._selected_pid: str = ""      # currently selected provider
        self._selected_model: str = ""    # currently selected model
        self._combo_models: dict = {}     # pid -> (combo, models list)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(6)

        # ── Header ────────────────────────────────────────────────────────
        header_lay = QHBoxLayout()
        title_lbl = QLabel("AI PROVIDER")
        title_lbl.setFont(QFont("Courier New", 12, QFont.Weight.Bold))
        title_lbl.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        desc_lbl = QLabel("Choose your LLM — models are loaded automatically")
        desc_lbl.setFont(QFont("Courier New", 8))
        desc_lbl.setStyleSheet(f"color: {C.PRI_DIM}; background: transparent;")
        header_lay.addWidget(title_lbl)
        header_lay.addSpacing(8)
        header_lay.addWidget(desc_lbl)
        header_lay.addStretch()
        # Refresh button
        refresh_btn = QPushButton("↻")
        refresh_btn.setFixedSize(26, 26)
        refresh_btn.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.setToolTip("Re-detect providers & models")
        refresh_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 4px;
            }}
            QPushButton:hover {{ color: {C.TEXT}; border: 1px solid {C.ACC}; }}
        """)
        refresh_btn.clicked.connect(self._discover_async)
        header_lay.addWidget(refresh_btn)
        layout.addLayout(header_lay)
        layout.addWidget(_sep())

        # ── Provider cards (scrollable) ───────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("background: transparent; border: none;")
        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        self._cards_layout = QVBoxLayout(inner)
        self._cards_layout.setContentsMargins(0, 0, 0, 0)
        self._cards_layout.setSpacing(8)
        self._card_widgets: dict = {}   # pid -> card QWidget
        for p in PROVIDERS:
            card = self._build_card(p)
            self._card_widgets[p["id"]] = card
            self._cards_layout.addWidget(card)
        self._cards_layout.addStretch()
        scroll.setWidget(inner)
        layout.addWidget(scroll, stretch=1)

        layout.addWidget(_sep())

        # ── Status line ───────────────────────────────────────────────────
        self._status_lbl = QLabel("Detecting providers…")
        self._status_lbl.setFont(QFont("Courier New", 8))
        self._status_lbl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
        layout.addWidget(self._status_lbl)

        # ── Footer buttons ────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFont(QFont(_font(), 10))
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

        apply_btn = QPushButton("Apply Provider")
        apply_btn.setFont(QFont(_font(), 10, QFont.Weight.Bold))
        apply_btn.setFixedHeight(34)
        apply_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        apply_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.ACC}; color: {C.WHITE};
                border: none; border-radius: 6px;
                padding: 4px 16px;
            }}
            QPushButton:hover {{
                background: {C.ACC_DIM};
            }}
        """)
        apply_btn.clicked.connect(self._submit)
        btn_row.addWidget(apply_btn)
        layout.addLayout(btn_row)

        # ── Kick off auto-detection ───────────────────────────────────────
        QTimer.singleShot(120, self._discover_async)

    # ------------------------------------------------------------------ #
    def _build_card(self, p: dict) -> QWidget:
        C = _C()
        pid = p["id"]
        cur_provider = (self._init.get("llm_provider") or "ollama").strip().lower().replace("-", "_")
        is_active = (pid == cur_provider)

        card = QWidget()
        card.setProperty("pid", pid)
        is_local = p["category"] in ("local", "both")
        bg = C.ACC_GHO if is_active else C.PANEL2
        card.setStyleSheet(f"""
            QWidget {{
                background: {bg};
                border: {f'1px solid {C.ACC}' if is_active else f'1px solid {C.BORDER}'};
                border-radius: 6px;
            }}
        """)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(6)

        # Top row: label + status
        top_row = QHBoxLayout()
        lbl = QLabel(p["label"].upper())
        lbl.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        lbl.setStyleSheet(f"color: {C.TEXT if is_active else C.PRI}; background: transparent;")
        tag = QLabel(p["tagline"])
        tag.setFont(QFont("Courier New", 7))
        tag.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
        top_row.addWidget(lbl)
        top_row.addWidget(tag)
        top_row.addStretch()
        status = QLabel("…")
        status.setFont(QFont("Courier New", 7))
        status.setProperty("status", True)
        top_row.addWidget(status)
        lay.addLayout(top_row)

        # Model row: dropdown auto-filled
        model_row = QHBoxLayout()
        model_lbl = QLabel("Model:")
        model_lbl.setFont(QFont("Courier New", 7))
        model_lbl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
        combo = QComboBox()
        combo.setFixedHeight(26)
        combo.setStyleSheet(f"""
            QComboBox {{
                background: {C.PANEL}; color: {C.TEXT};
                border: 1px solid {C.BORDER}; border-radius: 4px; padding: 2px 6px;
                font-family: '{_font()}'; font-size: 9pt;
            }}
            QComboBox:focus {{ border: 1px solid {C.ACC}; }}
            QComboBox::drop-down {{ border: none; width: 16px; }}
            QComboBox QAbstractItemView {{
                background: {C.PANEL}; color: {C.TEXT};
                border: 1px solid {C.BORDER};
                selection-background-color: {C.ACC_GHO};
            }}
        """)
        model_row.addWidget(model_lbl)
        model_row.addWidget(combo, stretch=1)
        lay.addLayout(model_row)

        # API key row (only for cloud providers)
        key_input = None
        key_field = p.get("key_field")
        if key_field:
            key_row = QHBoxLayout()
            key_lbl = QLabel("API key:")
            key_lbl.setFont(QFont("Courier New", 7))
            key_lbl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
            key_input = QLineEdit()
            key_input.setPlaceholderText(f"{p['label']} API key (optional if already set)")
            key_input.setEchoMode(QLineEdit.EchoMode.Password)
            key_input.setFixedHeight(26)
            key_input.setText(self._init.get(key_field, ""))
            key_input.setStyleSheet(f"""
                QLineEdit {{
                    background: {C.PANEL}; color: {C.TEXT};
                    border: 1px solid {C.BORDER}; border-radius: 4px; padding: 2px 8px;
                    font-family: '{_font()}'; font-size: 9pt;
                }}
                QLineEdit:focus {{ border: 1px solid {C.ACC}; }}
            """)
            key_row.addWidget(key_lbl)
            key_row.addWidget(key_input, stretch=1)
            lay.addLayout(key_row)

        # "Use this" button
        use_btn = QPushButton("USE" if not is_active else "CURRENT")
        use_btn.setFixedHeight(24)
        use_btn.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        use_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if is_active:
            use_btn.setEnabled(False)
        use_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.ACC if not is_active else C.ACC_DIM}; color: {C.WHITE};
                border: none; border-radius: 4px;
            }}
            QPushButton:hover {{ background: {C.ACC_DIM}; }}
            QPushButton:disabled {{ background: {C.ACC_DIM}; color: {C.PRI_DIM}; }}
        """)

        def _on_use():
            self._select_provider(pid)
        use_btn.clicked.connect(_on_use)
        btn_row_w = QHBoxLayout()
        btn_row_w.addWidget(use_btn)
        btn_row_w.addStretch()
        lay.addLayout(btn_row_w)

        # keep references
        card._model_combo = combo
        card._key_input = key_input
        card._status_lbl = status
        card._use_btn = use_btn

        # Pre-fill models from defaults right away (instant feedback)
        # NOTE: self._card_widgets is updated AFTER _build_card returns, so pass
        # the card explicitly to avoid a KeyError during construction.
        self._fill_models(pid, DEFAULT_MODELS.get(pid, []), card=card)
        return card

    def _fill_models(self, pid: str, models: list[str], card: QWidget | None = None) -> None:
        card = card or self._card_widgets.get(pid)
        if card is None or not hasattr(card, "_model_combo"):
            return
        combo = card._model_combo
        current_text = combo.currentText()
        combo.clear()
        seen: set = set()
        for m in models:
            if m not in seen:
                seen.add(m)
                combo.addItem(m, userData=m)
        # Select: current selection > provider default > configured model > first
        want = self._selected_model if self._selected_pid == pid else ""
        if not want:
            want = (self._discovery.get(pid, {}).get("default")
                    or self._init.get("llm_model")
                    or (models[0] if models else ""))
        idx = combo.findText(want)
        if idx < 0:
            # try userData match for full model ids
            for i in range(combo.count()):
                if combo.itemData(i) == want:
                    idx = i
                    break
        combo.setCurrentIndex(max(idx, 0))
        if want:
            self._selected_model = want

    def _select_provider(self, pid: str) -> None:
        """Mark a provider card as the active selection."""
        C = _C()
        self._selected_pid = pid
        for other_pid, card in self._card_widgets.items():
            is_active = (other_pid == pid)
            bg = C.ACC_GHO if is_active else C.PANEL2
            card.setStyleSheet(f"""
                QWidget {{
                    background: {bg};
                    border: {f'1px solid {C.ACC}' if is_active else f'1px solid {C.BORDER}'};
                    border-radius: 6px;
                }}
            """)
            card._status_lbl.setStyleSheet(
                f"color: {C.TEXT if is_active else C.TEXT_MED}; background: transparent;"
            )
            card._use_btn.setText("CURRENT" if is_active else "USE")
            card._use_btn.setEnabled(not is_active)
            card._use_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {C.ACC if not is_active else C.ACC_DIM}; color: {C.WHITE};
                    border: none; border-radius: 4px;
                }}
                QPushButton:hover {{ background: {C.ACC_DIM}; }}
                QPushButton:disabled {{ background: {C.ACC_DIM}; color: {C.PRI_DIM}; }}
            """)
        self._selected_model = self._card_widgets[pid]._model_combo.currentText() or ""

    # ------------------------------------------------------------------ #
    # Auto-detection (background thread — never blocks the UI)
    # ------------------------------------------------------------------ #
    def _discover_async(self) -> None:
        C = _C()
        self._status_lbl.setText("Detecting providers & loading models…")
        threading.Thread(target=self._discover_worker, daemon=True).start()

    def _discover_worker(self) -> None:
        from core.llm_provider_detector import discover_all
        self._discovery = discover_all(self._init, on_status=self._on_provider_status)
        # Guarantee: if user's current provider wasn't auto-selected yet,
        # select it now (or the first reachable one)
        if not self._selected_pid:
            cur = (self._init.get("llm_provider") or "ollama").strip().lower().replace("-", "_")
            if cur in self._card_widgets:
                self._select_provider(cur)
            else:
                self._select_provider("ollama")
        # Refresh model combos with discovered models + keep defaults
        for pid, status in self._discovery.items():
            models = status.get("models") or []
            # merge: discovered first, then defaults not already listed
            merged = list(dict.fromkeys(models + DEFAULT_MODELS.get(pid, [])))
            self._fill_models(pid, merged, card=self._card_widgets[pid])
            # pick discovered default model
            default = status.get("default")
            if default and self._selected_pid == pid:
                combo = self._card_widgets[pid]._model_combo
                idx = combo.findText(default)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
                    self._selected_model = default
        # Final status line
        reachable = [pid for pid, s in self._discovery.items() if s.get("reachable")]
        if reachable:
            names = [get_provider(p)["label"] for p in reachable if get_provider(p)]
            self._status_lbl.setText(f"Ready — {', '.join(names)} available. Pick one and click Apply.")
        else:
            self._status_lbl.setText(
                "No provider reachable right now. Set an API key, then click Apply (defaults will be used).")

    def _on_provider_status(self, pid: str, status: dict) -> None:
        """Live per-provider status updates as discovery completes."""
        card = self._card_widgets.get(pid)
        if card is None or not hasattr(card, "_status_lbl"):
            return
        C = _C()
        label = "●" if status.get("reachable") else "○"
        color = C.GREEN if status.get("reachable") else C.TEXT_DIM
        card._status_lbl.setText(label)
        card._status_lbl.setStyleSheet(f"color: {color}; background: transparent;")

    # ------------------------------------------------------------------ #
    def _submit(self) -> None:
        pid = self._selected_pid or "ollama"
        p = get_provider(pid)
        if p is None:
            p = PROVIDERS[0]
        card = self._card_widgets[pid]
        model = card._model_combo.currentText().strip()
        if not model:
            model = DEFAULT_MODELS.get(pid, [""])[0]
        url = p["url"]
        diff: dict = {
            "llm_provider": pid,
            "llm_model":    model,
            "llm_url":      url,
            "llm_api_key":  "",
        }
        key_field = p.get("key_field")
        if key_field and card._key_input is not None:
            key_val = card._key_input.text().strip()
            if key_val:
                diff[key_field] = key_val
        # keep user's existing llm_api_key unless we are clearing the key
        diff["llm_api_key"] = self._init.get("llm_api_key", "")
        self.done.emit(json.dumps(diff))
        self.hide()


def _sep():
    C = _C()
    s = QFrame()
    s.setFrameShape(QFrame.Shape.HLine)
    s.setStyleSheet(f"color: {C.BORDER}; margin: 2px 0;")
    return s
