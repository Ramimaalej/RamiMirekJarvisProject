"""Second pass of UI optimisation patches (targeted)."""
import re

with open("ui.py", encoding="utf-8") as f:
    lines = f.readlines()

# --------------------------------------------------------------- #
# A. LogWidget._step — batch 64 chars/tick
# --------------------------------------------------------------- #
# find "def _step(self):" after line 850 (LogWidget), then rewrite until
# the "else: self._tmr.stop()" block.
idx = None
for i, ln in enumerate(lines):
    if i > 850 and "def _step(self):" in ln:
        idx = i
        break
assert idx is not None, "LogWidget._step not found"

# collect the current body until we see "self._tmr.stop()" followed by
# "self.ensureCursorVisible()" followed by "QTimer.singleShot"
start = idx + 1
stop = None
for j in range(start, min(start + 60, len(lines))):
    if "QTimer.singleShot" in lines[j]:
        stop = j + 1  # keep this line (replaced below)
        break
assert stop is not None, "_step end not found"

new_step = '''        # Batch ~64 chars per tick (instead of 1) -> smooth typing, no lag.
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
'''
lines[start:stop] = [new_step]
print(f"LogWidget._step rewritten at lines {idx+1}-{stop}")

# --------------------------------------------------------------- #
# B. HudCanvas paintEvent — cached grid pixmap
# --------------------------------------------------------------- #
grid_old = '''        # subtle blue grid dots
        p.setPen(QPen(qcol(_BLUE_DIM, 50), 1))
        for x in range(0, W, 48):
            for y in range(0, H, 48):
                p.drawPoint(x, y)'''
grid_new = '''        # cached background (grid dots drawn once, reused every frame)
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
text = "".join(lines)
if grid_old in text:
    text = text.replace(grid_old, grid_new, 1)
    print("HudCanvas grid: cached pixmap applied")
else:
    print("HudCanvas grid: pattern NOT found")

# --------------------------------------------------------------- #
# C. Ensure QPixmap import exists
# --------------------------------------------------------------- #
if "from PyQt6.QtGui import" in text and "QPixmap" not in text.split("from PyQt6.QtGui import")[1].split("\n")[0]:
    print("QPixmap import: needs check")

with open("ui.py", "w", encoding="utf-8") as f:
    f.write(text)
