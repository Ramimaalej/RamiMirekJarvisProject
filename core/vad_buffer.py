"""Voice Activity Detection buffer."""
from __future__ import annotations

import numpy as np

class _VADBuffer:
    """Energy-based VAD: buffers audio until end of utterance."""

    def __init__(
        self,
        sample_rate:    int   = 16_000,
        silence_sec:    float = 0.18,  # ↓300ms→180ms: shaves ~120ms off every turn
        speech_thresh:  float = 0.008,  # RMS above this = speech  (0.008 catches voice at 3-4 m; raise if mic picks up too much room noise)
        silence_thresh: float = 0.004,  # RMS below this = silence (half of speech_thresh — hysteresis prevents mid-sentence cuts)
        min_speech_sec: float = 0.25,   # ↓0.3→0.25 s: accept slightly shorter utterances
        max_speech_sec: float = 30.0,
    ):
        self._sr            = sample_rate
        self._sil_n         = int(silence_sec * sample_rate)
        self._speech_thresh = speech_thresh
        self._sil_thresh    = silence_thresh
        self._min_n         = int(min_speech_sec * sample_rate)
        self._max_n         = int(max_speech_sec * sample_rate)
        self._buf:          list[np.ndarray] = []
        self._in_spch       = False
        self._sil_cnt       = 0
    def process(self, chunk: np.ndarray) -> np.ndarray | None:
        """
        Feed one audio chunk (float32 mono).
        Returns complete utterance when speech ends, otherwise None.

        Uses hysteresis thresholds so the detector doesn't flicker:
          - speech starts when RMS > speech_thresh  (0.008 = ~3-4 m range)
          - speech ends only when RMS < silence_thresh  (0.004 = half of start)
        The gap between the two thresholds prevents mid-sentence cuts on
        natural pauses and quiet consonants.
        """
        rms     = float(np.sqrt(np.mean(chunk ** 2)))
        total_n = sum(len(c) for c in self._buf)

        if rms > self._speech_thresh:
            self._in_spch = True
            self._sil_cnt = 0
            self._buf.append(chunk.copy())
        elif self._in_spch:
            self._buf.append(chunk.copy())
            if rms < self._sil_thresh:
                self._sil_cnt += len(chunk)

            if self._sil_cnt >= self._sil_n or total_n >= self._max_n:
                audio         = np.concatenate(self._buf)
                self._buf     = []
                self._in_spch = False
                self._sil_cnt = 0
                if len(audio) >= self._min_n:
                    return audio
        return None



