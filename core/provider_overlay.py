"""Provider Overlay — admin-style provider tab.

Grid of provider cards (like an admin panel), each card shows:
  - Provider name + status badge (Configured / Missing key / Offline / Current)
  - API key field (cloud providers) or base URL (local providers)
  - Model dropdown — models are loaded AUTOMATICALLY when the provider is
    reachable; curated defaults are always present so the list is never empty
  - "Refresh models" button (re-queries /models for that provider)
  - "Test" button (local providers: LM Studio, llama.cpp, Ollama) or "Use" (cloud)
  - "USE" — make this provider active

Selecting a provider highlights its card. Models are pre-loaded in parallel
in a background thread — the UI never blocks.

Style: flat design (no border-radius), matches ConnectionsOverlay in ui.py.
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
    QVBoxLayout, QWidget, QFrame, QGridLayout,
)

from core.llm_provider_detector import (
    PROVIDERS, get_provider, list_models, is_reachable, DEFAULT_MODELS,
)

logger = logging.getLogger("provider_overlay")

# ---------------------------------------------------------------------------
# Helpers reusing ui.py design tokens (imported lazily to avoid cycles)
# ---------------------------------------------------------------------------
def _C():
    import ui as _ui
    return _ui.C

def _font():
    import ui as _ui
    return _ui._FONT

# Status badge text mapping
def _badge(pid: str, status: dict, cfg: dict) -> tuple[str, str]:
    """Return (badge_text, badge_color) for a provider card."""
    p = get_provider(pid)
    is_local = p and p["category"] in ("local", "both")
    has_key = bool((cfg.get(p["key_field"]) or "").strip()) if p and p.get("key_field") else True
    reachable = bool(status.get("reachable", False))
    cur = (cfg.get("llm_provider") or "ollama").strip().lower().replace("-", "_")
    if pid == cur:
        return ("Current", "#7ae07a")   # green
    if p and p.get("key_field") and not has_key:
        return ("Missing key", "#e8a838")  # amber
    if is_local:
        return ("Offline" if not reachable else ("Configured" if reachable else "Offline"),
                "#7ae07a" if reachable else "#e04444")
    if reachable:
        return ("Configured", "#7ae07a")
    if has_key:
        return ("Unreachable", "#e04444")
    return ("Missing key", "#e8a838")

class ProviderOverlay(QWidget):
    # Emits JSON: {"llm_provider": ..., "llm_model": ..., "llm_url": ...,
    #             "<key_field>": ..., "llm_api_key": ...}
    done = pyqtSignal(str)

    def __init__(self, parent=None, initial: dict | None = None):
        super().__init__(parent)
        self._init = initial or {}
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        C = _C()

        bg_color = "rgba(240, 242, 245, 248)" if C.BG.lower() in ("#ffffff", "#f8f9fa") else "rgba(10, 10, 10, 248)"
        self.setStyleSheet(f"""
            ProviderOverlay {{
                background: {bg_color};
                border: 1px solid {C.BORDER};
            }}
        """)

        self._discovery: dict = {}
        self._selected_pid: str = ""
        self._selected_model: str = ""
        self._cards: dict = {}          # pid -> card widget
        self._locks: dict = {}          # pid -> bool (refresh in progress)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 24, 30, 24)
        layout.setSpacing(16)

        # ── Header ────────────────────────────────────────────────────────
        header_lay = QHBoxLayout()
        header_lay.setSpacing(15)
        title_lbl = QLabel("AI PROVIDERS")
        title_lbl.setFont(QFont(_font(), 16, QFont.Weight.Bold))
        title_lbl.setStyleSheet(f"color: {C.TEXT}; background: transparent; border: none;")
        desc_lbl = QLabel("Manage providers & API keys — models load automatically")
        desc_lbl.setFont(QFont(_font(), 10))
        desc_lbl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent; border: none;")
        header_lay.addWidget(title_lbl)
        header_lay.addWidget(desc_lbl)
        header_lay.addStretch()
        refresh_all_btn = QPushButton("↻ Refresh all")
        refresh_all_btn.setFont(QFont(_font(), 8, QFont.Weight.Bold))
        refresh_all_btn.setFixedHeight(24)
        refresh_all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_all_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER};
                padding: 0px 8px;
            }}
            QPushButton:hover {{ color: {C.TEXT}; border: 1px solid {C.ACC}; background: {C.PRI_GHO}; }}
        """)
        refresh_all_btn.clicked.connect(self._discover_async)
        header_lay.addWidget(refresh_all_btn)
        layout.addLayout(header_lay)

        # ── Grid of provider cards ────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("background: transparent; border: none;")
        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        grid = QGridLayout(inner)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(16)
        row = col = 0
        per_row = 2
        for p in PROVIDERS:
            card = self._build_card(p)
            self._cards[p["id"]] = card
            grid.addWidget(card, row, col)
            col += 1
            if col >= per_row:
                col = 0
                row += 1
        # fill empty trailing cells
        inner._grid = grid
        scroll.setWidget(inner)
        layout.addWidget(scroll, stretch=1)

        # ── Status line ───────────────────────────────────────────────────
        self._status_lbl = QLabel("Detecting providers…")
        self._status_lbl.setFont(QFont("Courier New", 8))
        self._status_lbl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent; border: none;")
        layout.addWidget(self._status_lbl)

        # ── Footer ────────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFont(QFont(_font(), 10))
        cancel_btn.setFixedHeight(34)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER};
                padding: 4px 16px;
            }}
            QPushButton:hover {{ color: {C.TEXT}; border: 1px solid {C.TEXT_MED}; }}
        """)
        cancel_btn.clicked.connect(self.hide)
        btn_row.addWidget(cancel_btn)
        btn_row.addStretch()
        apply_btn = QPushButton("APPLY PROVIDER")
        apply_btn.setFont(QFont(_font(), 10, QFont.Weight.Bold))
        apply_btn.setFixedHeight(34)
        apply_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        apply_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.ACC}; color: {C.WHITE};
                border: none;
                padding: 4px 16px;
            }}
            QPushButton:hover {{ background: {C.ACC_DIM}; }}
        """)
        apply_btn.clicked.connect(self._submit)
        btn_row.addWidget(apply_btn)
        layout.addLayout(btn_row)

        QTimer.singleShot(120, self._discover_async)

    # ------------------------------------------------------------------ #
    def _build_card(self, p: dict) -> QWidget:
        C = _C()
        pid = p["id"]
        cur_provider = (self._init.get("llm_provider") or "ollama").strip().lower().replace("-", "_")
        is_active = (pid == cur_provider)
        is_local = p["category"] in ("local", "both")
        key_field = p.get("key_field")
        has_key = bool((self._init.get(key_field) or "").strip()) if key_field else True
        badge_text, badge_color = _badge(pid, {}, self._init)

        card = QWidget()
        card.setProperty("pid", pid)
        card.setStyleSheet(f"""
            QWidget {{
                background: {C.ACC_GHO if is_active else C.PANEL2};
                border: 2px solid {C.ACC if is_active else C.BORDER};
            }}
        """)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(15, 12, 15, 12)
        lay.setSpacing(10)

        # Top row: label + badge
        top_row = QHBoxLayout()
        top_row.setSpacing(10)
        top_row.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel(p["label"].upper())
        lbl.setFont(QFont("Courier New", 11, QFont.Weight.Bold))
        lbl.setStyleSheet(f"color: {C.PRI}; background: transparent; border: none;")
        top_row.addWidget(lbl)
        top_row.addStretch()
        badge = QLabel(badge_text)
        badge.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        badge.setStyleSheet(f"""
            QLabel {{
                color: {badge_color};
                background: transparent; border: none;
            }}
        """)
        top_row.addWidget(badge)
        lay.addLayout(top_row)

        # URL/key field row
        if key_field:
            key_row = QHBoxLayout()
            key_row.setContentsMargins(0, 2, 0, 0)
            key_row.setSpacing(6)
            key_lbl = QLabel("API key")
            key_lbl.setFont(QFont("Courier New", 7))
            key_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; border: none;")
            key_input = QLineEdit()
            key_input.setPlaceholderText("Enter your API key…")
            key_input.setEchoMode(QLineEdit.EchoMode.Password)
            key_input.setFixedHeight(26)
            key_input.setText(self._init.get(key_field, ""))
            key_input.setStyleSheet(f"""
                QLineEdit {{
                    background: {C.PANEL}; color: {C.TEXT};
                    border: 1px solid {C.BORDER}; padding: 2px 8px;
                    font-family: '{_font()}'; font-size: 9pt;
                }}
                QLineEdit:focus {{ border: 1px solid {C.ACC}; }}
                QLineEdit:disabled {{ color: {C.TEXT_MED}; }}
            """)
            # show "Configured - enter new value…" when a key already exists
            if has_key:
                key_input.setPlaceholderText("Configured — enter a new value to overwrite")
            key_row.addWidget(key_lbl)
            key_row.addWidget(key_input, stretch=1)
            lay.addLayout(key_row)
        else:
            # local provider: show editable base URL
            url_row = QHBoxLayout()
            url_row.setContentsMargins(0, 2, 0, 0)
            url_row.setSpacing(6)
            url_lbl = QLabel("Base URL")
            url_lbl.setFont(QFont("Courier New", 7))
            url_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; border: none;")
            url_input = QLineEdit()
            url_input.setFixedHeight(26)
            url_input.setText(p["url"])
            url_input.setStyleSheet(f"""
                QLineEdit {{
                    background: {C.PANEL}; color: {C.TEXT};
                    border: 1px solid {C.BORDER}; padding: 2px 8px;
                    font-family: '{_font()}'; font-size: 9pt;
                }}
                QLineEdit:focus {{ border: 1px solid {C.ACC}; }}
            """)
            url_row.addWidget(url_lbl)
            url_row.addWidget(url_input, stretch=1)
            lay.addLayout(url_row)

        # Model row: label + combo (stretch)
        model_row = QHBoxLayout()
        model_row.setContentsMargins(0, 2, 0, 0)
        model_row.setSpacing(6)
        combo_lbl = QLabel("Models")
        combo_lbl.setFont(QFont("Courier New", 7))
        combo_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; border: none;")
        combo = QComboBox()
        combo.setFixedHeight(26)
        combo.setStyleSheet(f"""
            QComboBox {{
                background: {C.PANEL}; color: {C.TEXT};
                border: 1px solid {C.BORDER}; padding: 2px 6px;
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
        model_row.addWidget(combo_lbl)
        model_row.addWidget(combo, stretch=1)
        lay.addLayout(model_row)
        # Pre-fill with curated defaults so the combo is never empty —
        # even when the provider server is unreachable at startup.
        cur_model = (self._init.get("llm_model", "").strip()
                     if cur_provider == pid else "")
        for m in DEFAULT_MODELS.get(pid, []):
            if m:
                combo.addItem(m, userData=m)
        if cur_model and combo.findText(cur_model) >= 0:
            combo.setCurrentText(cur_model)
        elif combo.count():
            combo.setCurrentIndex(0)
            if is_active:
                self._selected_model = combo.currentText() or cur_model
        if is_active:
            self._selected_pid = cur_provider

        # Buttons row: Refresh models + (Test | USE)
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 2, 0, 0)
        btn_row.setSpacing(6)
        refresh_btn = QPushButton("Refresh models")
        refresh_btn.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        refresh_btn.setFixedHeight(24)
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; padding: 0px 6px;
            }}
            QPushButton:hover {{ color: {C.TEXT}; border: 1px solid {C.ACC}; background: {C.PRI_GHO}; }}
            QPushButton:disabled {{ color: {C.TEXT_DIM}; }}
        """)
        btn_row.addWidget(refresh_btn)
        if is_local:
            # Local providers get a "Test" button (ping) + USE
            test_btn = QPushButton("Test")
            test_btn.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
            test_btn.setFixedHeight(24)
            test_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            test_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {C.TEXT_MED};
                    border: 1px solid {C.BORDER}; padding: 0px 10px;
                }}
                QPushButton:hover {{ color: {C.GREEN}; border: 1px solid {C.GREEN}; background: {C.PRI_GHO}; }}
            """)
            btn_row.addWidget(test_btn)
        btn_row.addStretch()
        use_btn = QPushButton("USE" if not is_active else "CURRENT")
        use_btn.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        use_btn.setFixedHeight(24)
        use_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if is_active:
            use_btn.setEnabled(False)
        use_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.ACC if not is_active else C.ACC_DIM}; color: {C.WHITE};
                border: none; padding: 0px 12px;
            }}
            QPushButton:hover {{ background: {C.ACC_DIM}; }}
            QPushButton:disabled {{ background: {C.ACC_DIM}; color: {C.PRI_DIM}; }}
        """)
        btn_row.addWidget(use_btn)
        lay.addLayout(btn_row)

        # ── Actions ───────────────────────────────────────────────────────
        def _on_use():
            self._select_provider(pid)
        def _on_refresh():
            self._refresh_models(pid)
        def _on_test():
            self._test_provider(pid)
        use_btn.clicked.connect(_on_use)
        refresh_btn.clicked.connect(_on_refresh)
        if is_local:
            test_btn.clicked.connect(_on_test)

        card._model_combo = combo
        card._key_input = key_input if key_field else None
        card._url_input = None if key_field else url_input
        card._badge_lbl = badge
        card._use_btn = use_btn
        return card

    def _fill_models(self, pid: str, models: list[str], card: QWidget | None = None) -> None:
        card = card or self._cards.get(pid)
        if card is None or not hasattr(card, "_model_combo"):
            return
        combo = card._model_combo
        combo.clear()
        seen: set = set()
        for m in models:
            if m not in seen:
                seen.add(m)
                combo.addItem(m, userData=m)
        want = self._selected_model if self._selected_pid == pid else ""
        if not want:
            want = (self._discovery.get(pid, {}).get("default")
                    or self._init.get("llm_model")
                    or (models[0] if models else ""))
        idx = combo.findText(want)
        if idx < 0:
            for i in range(combo.count()):
                if combo.itemData(i) == want:
                    idx = i
                    break
        combo.setCurrentIndex(max(idx, 0))
        if want:
            self._selected_model = want

    def _select_provider(self, pid: str) -> None:
        C = _C()
        self._selected_pid = pid
        for other_pid, card in self._cards.items():
            is_active = (other_pid == pid)
            card.setStyleSheet(f"""
                QWidget {{
                    background: {C.ACC_GHO if is_active else C.PANEL2};
                    border: 2px solid {C.ACC if is_active else C.BORDER};
                }}
            """)
            card._use_btn.setText("CURRENT" if is_active else "USE")
            card._use_btn.setEnabled(not is_active)
        self._selected_model = self._cards[pid]._model_combo.currentText() or ""

    def _test_provider(self, pid: str) -> None:
        """Ping a local provider and show a one-line result in the status bar."""
        C = _C()
        card = self._cards.get(pid)
        if card is None:
            return
        p = get_provider(pid)
        url = (card._url_input.text().strip() or p["url"]).rstrip("/")
        threading.Thread(target=self._test_worker, args=(pid, url, card), daemon=True).start()

    def _test_worker(self, pid: str, url: str, card: QWidget) -> None:
        C = _C()
        p = get_provider(pid)
        ok = False
        try:
            if p["protocol"] == "ollama":
                import requests
                ok = requests.get(f"{url}/api/tags", timeout=3).status_code == 200
            else:
                import requests
                headers = {}
                key = card._key_input.text().strip() if card._key_input else ""
                if key:
                    headers["Authorization"] = f"Bearer {key}"
                resp = requests.get(f"{url}/models", headers=headers, timeout=3)
                ok = resp.status_code < 400
        except Exception as e:
            logger.debug("test %s: %s", pid, e)
        txt = f"{p['label']} @ {url} — ONLINE" if ok else f"{p['label']} @ {url} — OFFLINE"
        QTimer.singleShot(0, lambda: self._status_lbl.setText(txt))

    def _refresh_models(self, pid: str) -> None:
        """Re-query models for ONE provider (background, non-blocking)."""
        if self._locks.get(pid):
            return
        self._locks[pid] = True
        card = self._cards.get(pid)
        p = get_provider(pid)
        threading.Thread(target=self._refresh_worker, args=(pid, card, p), daemon=True).start()

    def _refresh_worker(self, pid: str, card: QWidget, p: dict) -> None:
        try:
            models = list_models(pid, timeout=15)
            reachable = bool(models)
        except Exception as e:
            logger.debug("refresh %s: %s", pid, e)
            models, reachable = [], False
        default = models[0] if models else DEFAULT_MODELS.get(pid, [""])[0]
        self._discovery[pid] = {"models": models, "default": default, "reachable": reachable}
        # Merge with curated defaults so the combo is never empty, even when
        # the provider server is unreachable (offline badge keeps working).
        merged = list(dict.fromkeys(models + DEFAULT_MODELS.get(pid, [])))
        self._fill_models(pid, merged, card=card)
        finally_done = (lambda: self._locks.update({pid: False}))
        QTimer.singleShot(0, finally_done)
        # safety release so a stuck QTimer (threadless owner) never deadlocks
        threading.Timer(1.0, finally_done).start()

    # ------------------------------------------------------------------ #
    def _discover_async(self) -> None:
        self._status_lbl.setText("Detecting providers & loading models…")
        threading.Thread(target=self._discover_worker, daemon=True).start()

    def _discover_worker(self) -> None:
        from core.llm_provider_detector import discover_all
        self._discovery = discover_all(self._init, on_status=self._on_provider_status)
        if not self._selected_pid:
            cur = (self._init.get("llm_provider") or "ollama").strip().lower().replace("-", "_")
            if cur in self._cards:
                self._select_provider(cur)
            else:
                self._select_provider("ollama")
        for pid, status in self._discovery.items():
            card = self._cards[pid]
            # refresh model combos: discovered + curated defaults
            models = status.get("models") or []
            merged = list(dict.fromkeys(models + DEFAULT_MODELS.get(pid, [])))
            self._fill_models(pid, merged, card=card)
            # update badge
            text, color = _badge(pid, status, self._init)
            card._badge_lbl.setText(text)
            card._badge_lbl.setStyleSheet(f"""
                QLabel {{
                    color: {color};
                    background: transparent; border: none;
                    font-family: 'Courier New'; font-size: 8pt; font-weight: bold;
                }}
            """)
            default = status.get("default")
            if default and self._selected_pid == pid:
                combo = card._model_combo
                idx = combo.findText(default)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
                    self._selected_model = default
        reachable = [pid for pid, s in self._discovery.items() if s.get("reachable")]
        if reachable:
            names = [get_provider(p)["label"] for p in reachable if get_provider(p)]
            self._status_lbl.setText(f"Ready — {', '.join(names)} available. Pick one and click Apply.")
        else:
            self._status_lbl.setText(
                "No provider reachable right now. Set an API key, then click Apply (defaults will be used).")

    def _on_provider_status(self, pid: str, status: dict) -> None:
        """Live per-provider status updates as discovery completes."""
        card = self._cards.get(pid)
        if card is None:
            return
        text, color = _badge(pid, status, self._init)
        card._badge_lbl.setText(text)
        card._badge_lbl.setStyleSheet(f"""
            QLabel {{
                color: {color};
                background: transparent; border: none;
                font-family: 'Courier New'; font-size: 8pt; font-weight: bold;
            }}
        """)
        # if models arrived, fill the combo right away
        models = status.get("models") or []
        if models:
            self._fill_models(pid, models, card=card)

    # ------------------------------------------------------------------ #
    def _submit(self) -> None:
        pid = self._selected_pid or "ollama"
        p = get_provider(pid)
        if p is None:
            p = PROVIDERS[0]
        card = self._cards[pid]
        model = card._model_combo.currentText().strip()
        if not model:
            model = DEFAULT_MODELS.get(pid, [""])[0]
        # URL: for local providers use the card's (possibly edited) URL
        if p["category"] in ("local", "both") and card._url_input is not None:
            url = card._url_input.text().strip() or p["url"]
        else:
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
        diff["llm_api_key"] = self._init.get("llm_api_key", "")
        self.done.emit(json.dumps(diff))
        self.hide()


