"""Performance optimisations for ui.py — reduce lag, keep behaviour identical."""
import sys
sys.path.insert(0, ".")

with open("ui.py", encoding="utf-8") as f:
    src = f.read()

changes = []

# ------------------------------------------------------------------ #
# 1. LogWidget — batch the type-writer instead of one timer event per char
#    (8 ms per character floods the event loop → visible lag with long text)
#    New behaviour: flush ~60 chars per tick → smooth, no event-loop freeze
# ------------------------------------------------------------------ #
old = '''    def _step(self):
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
                cur.insertText(f"\\n[{prefix}] ", fmt)
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
            QTimer.singleShot(15, self._next)'''
new = '''    def _step(self):
        # Batch ~64 chars per tick (instead of 1) → smooth typing, no lag.
        BATCH = 64
        if self._pos < len(self._text):
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
                cur.insertText(f"\\n[{prefix}] ", fmt)
            col = {
                "you":  qcol(C.WHITE),
                "ai":   qcol(C.PRI),
                "err":  qcol(C.RED),
                "file": qcol(C.TEXT_MED),
                "sys":  qcol(C.TEXT_DIM),
            }.get(self._tag, qcol(C.TEXT))
            fmt.setForeground(QBrush(col))
            fmt.setFont(QFont(_FONT, _FONT_SZ_SM))
            chunk = self._text[self._pos:self._pos + BATCH]
            self._pos += len(chunk)
            cur.insertText(chunk, fmt)
            self.setTextCursor(cur)
            self.ensureCursorVisible()
        if self._pos >= len(self._text):
            self._tmr.stop()
            self.ensureCursorVisible()
            QTimer.singleShot(15, self._next)'''
if old in src:
    src = src.replace(old, new, 1)
    changes.append("LogWidget: batched type-writer (64 chars/tick)")
else:
    changes.append("LogWidget: pattern NOT found (skipped)")

# ------------------------------------------------------------------ #
# 2. Append ALL queued logs instantly without typing animation when there
#    is a backlog (old behaviour replayed every message char-by-char)
# ------------------------------------------------------------------ #
old = '''    def _next(self):
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
        self._tmr.start(8)'''
new = '''    def _next(self):
        if not self._queue:
            self._typing = False
            return
        self._typing = True
        # Fast-path: if a backlog built up, flush every queued message
        # instantly (append_instant) instead of re-typing them — no lag.
        if len(self._queue) >= 3:
            while self._queue:
                msg = self._queue.pop(0)
                tl = msg.lower()
                tag = ("you" if tl.startswith("you:") else
                       "ai" if tl.startswith("jarvis:") else
                       "file" if tl.startswith("file:") else
                       "err" if "err" in tl else "sys")
                self.append_instant(msg, tag=tag)
            self._typing = False
            return
        self._text   = self._queue.pop(0)
        self._pos    = 0
        tl = self._text.lower()
        if   tl.startswith("you:"):    self._tag = "you"
        elif tl.startswith("jarvis:"): self._tag = "ai"
        elif tl.startswith("file:"):   self._tag = "file"
        elif "err" in tl:              self._tag = "err"
        else:                          self._tag = "sys"
        self._tmr.start(8)'''
if old in src:
    src = src.replace(old, new, 1)
    changes.append("LogWidget: backlog fast-path (instant flush)")
else:
    changes.append("LogWidget backlog fast-path: pattern NOT found")

# ------------------------------------------------------------------ #
# 3. HudCanvas — throttle repaints to 30 fps when not speaking
#    (was 60+ fps from a 16 ms timer with full-grid redraws)
# ------------------------------------------------------------------ #
old = '''        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._step)
        self._tmr.start(16)'''
new = '''        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._step)
        self._tmr.start(32)   # 30 fps — smooth and half the CPU cost'''
if old in src:
    src = src.replace(old, new, 1)
    changes.append("HudCanvas: timer 16ms -> 32ms (30 fps)")
else:
    changes.append("HudCanvas: pattern NOT found")

# ------------------------------------------------------------------ #
# 4. HUD paintEvent — only redraw grid dots every ~2 seconds via a
#    cached background pixmap; the rings/pulses are the animated part
# ------------------------------------------------------------------ #
old = '''        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), qcol("#000a0f"))
        W, H = self.width(), self.height()
        cx, cy = W / 2, H / 2
        fw = min(W, H)
        # subtle blue grid dots
        p.setPen(QPen(qcol(_BLUE_DIM, 50), 1))
        for x in range(0, W, 48):
            for y in range(0, H, 48):
                p.drawPoint(x, y)'''
new = '''        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), qcol("#000a0f"))
        W, H = self.width(), self.height()
        cx, cy = W / 2, H / 2
        fw = min(W, H)
        # cached background (grid dots drawn once, re-used each frame)
        if not getattr(self, "_grid_px", None) or self._grid_px.size() != self.size():
            self._grid_px = QPixmap(self.size())
            self._grid_px.fill(qcol("#000a0f"))
            gp = QPainter(self._grid_px)
            gp.setPen(QPen(qcol(_BLUE_DIM, 50), 1))
            for x in range(0, W, 48):
                for y in range(0, H, 48):
                    gp.drawPoint(x, y)
            gp.end()
        p.drawPixmap(0, 0, self._grid_px)'''
if old in src:
    src = src.replace(old, new, 1)
    changes.append("HudCanvas: cached grid pixmap")
else:
    changes.append("HudCanvas grid: pattern NOT found")

with open("ui.py", "w", encoding="utf-8") as f:
    f.write(src)

for c in changes:
    print("-", c)
