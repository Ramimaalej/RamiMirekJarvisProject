import logging
import os
import platform
import queue
import struct
import threading
import time
from pathlib import Path
from typing import Callable

import numpy as np

logger = logging.getLogger("wake_word")

_OS = platform.system()

DEFAULT_MODEL = "jarvis"  # one of: jarvis, computer, alexa, hey_jarvis


class WakeWordDetector:
    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        sensitivity: float = 0.5,
        on_wake: Callable[[], None] | None = None,
    ):
        self.model_name = model_name
        self.sensitivity = sensitivity
        self.on_wake = on_wake
        self._running = False
        self._thread: threading.Thread | None = None
        self._audio_queue: queue.Queue = queue.Queue()
        self._oww = None

    def _load_model(self):
        try:
            import openwakeword
            import openwakeword.model as oww_model
        except ImportError:
            logger.error(
                "OpenWakeWord not installed. Run: pip install openwakeword"
            )
            return False

        try:
            self._oww = oww_model.WakeWordModel(
                wakeword_models=[self.model_name],
                inference_framework="onnx",
            )
            return True
        except Exception as e:
            logger.warning("OpenWakeWord model load failed: %s", e)
            return False

    def start(self):
        if self._running:
            return
        if not self._load_model():
            logger.error("Failed to load wake word model")
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("Wake word detector started: '%s'", self.model_name)

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None
        logger.info("Wake word detector stopped")

    def feed_audio(self, audio_chunk: np.ndarray):
        if self._running and self._oww is not None:
            self._audio_queue.put(audio_chunk)

    def _run(self):
        import openwakeword

        while self._running:
            try:
                chunk = self._audio_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            try:
                prediction = self._oww.predict(chunk)
                score = prediction.get(self.model_name, 0.0)
                if score > self.sensitivity:
                    logger.info("Wake word detected! (score=%.3f)", score)
                    if self.on_wake:
                        self.on_wake()
            except Exception as e:
                logger.debug("Wake word inference error: %s", e)

    def is_running(self) -> bool:
        return self._running


# ── Global singleton ──────────────────────────────────────────────────────

_detector: WakeWordDetector | None = None


def get_detector(
    model_name: str = DEFAULT_MODEL,
    sensitivity: float = 0.5,
    on_wake: Callable[[], None] | None = None,
) -> WakeWordDetector:
    global _detector
    if _detector is None:
        _detector = WakeWordDetector(
            model_name=model_name,
            sensitivity=sensitivity,
            on_wake=on_wake,
        )
    return _detector


def start_wake_word(
    model_name: str = DEFAULT_MODEL,
    sensitivity: float = 0.5,
    on_wake: Callable[[], None] | None = None,
) -> str:
    detector = get_detector(
        model_name=model_name,
        sensitivity=sensitivity,
        on_wake=on_wake,
    )
    detector.start()
    if detector._oww is None:
        return "Wake word unavailable — OpenWakeWord model not loaded."
    return f"Wake word '{model_name}' active (sensitivity={sensitivity})."


def stop_wake_word() -> str:
    global _detector
    if _detector:
        _detector.stop()
        _detector = None
        return "Wake word detector stopped."
    return "No wake word detector running."


def feed_audio_chunk(chunk: np.ndarray):
    if _detector and _detector.is_running():
        _detector.feed_audio(chunk)
