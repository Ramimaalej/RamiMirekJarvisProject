"""Text-to-speech worker + speak helpers."""
from __future__ import annotations
import traceback
import logging
import queue

def _tts_worker(self) -> None:
    # Block until TTS engine is loaded.  Queued items are preserved
    # and played immediately once loading completes — nothing is lost.
    self._tts_ready.wait(timeout=120)

    while True:
        text = self._tts_queue.get()
        try:
            if text and self._tts:
                with self._speaking_lock:
                    self._speaking = True
                self.ui.set_state("SPEAKING")
                self._tts.speak(text)
        except Exception as e:
            print(f"[TTS] speak error: {e}")
        finally:
            self._tts_queue.task_done()
            if self._tts_queue.empty():
                with self._speaking_lock:
                    self._speaking = False
                if not self.ui.muted:
                    self.ui.set_state("LISTENING")

def set_speaking(self, value: bool) -> None:
    with self._speaking_lock:
        self._speaking = value
    if value:
        self.ui.set_state("SPEAKING")
    elif not self.ui.muted:
        self.ui.set_state("LISTENING")

def speak(self, text: str) -> None:
    if not text or not self._tts:
        return
    with self._speaking_lock:
        self._speaking = True
    self._tts_queue.put(text)

def speak_error(self, tool_name: str, error) -> None:
    short = str(error)[:120]
    self.ui.write_log(f"ERR: {tool_name} — {short}")
    self.speak("I cannot do that.")

