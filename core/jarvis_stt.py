"""Speech-to-text listeners (Whisper / Vosk)."""
from __future__ import annotations
import traceback
import time
import re
import queue
import threading

import numpy as np
try:
    import sounddevice as sd  # noqa: F401  (lazy: used inside functions only)
except OSError:
    # PortAudio missing (headless server / Windows without lib) — import
    # must not crash startup; failure surfaces later when the mic stream
    # is actually opened (SD_MISSING guard).
    sd = None  # type: ignore[assignment]

from core.vad_buffer import _VADBuffer
from core.audio_consts import SAMPLE_RATE_IN, CHANNELS, BLOCK_SIZE

def _listen_whisper(self) -> None:
    """Mic → VAD → Whisper → LLM loop.

    Latency optimisation: as soon as VAD signals end-of-utterance we kick
    off transcription AND context pre-fetch in parallel.
      A) Whisper transcription  (CPU-bound, ~150-400 ms on 'tiny')
      B) Context pre-fetch      (network-bound: embedding + vector scan)

    Both run concurrently.  _process_message waits for (B) before building
    the system prompt, ensuring vector memory is ready when LLM fires.
    """
    vad = _VADBuffer()
    q: queue.Queue = queue.Queue(maxsize=200)

    def callback(indata, frames, time_info, status):
        with self._speaking_lock:
            is_speaking = self._speaking
        if not is_speaking and not self.ui.muted:
            try:
                q.put_nowait(indata.copy())
            except queue.Full:
                pass

    try:
        with sd.InputStream(
            samplerate=SAMPLE_RATE_IN,
            channels=CHANNELS,
            dtype="float32",
            blocksize=BLOCK_SIZE,
            callback=callback,
        ):
            self.ui.write_log("SYS: Mic active (Whisper STT).")
            while True:
                try:
                    chunk = q.get(timeout=0.1)
                    audio = vad.process(chunk.flatten())
                    if audio is not None:
                        self.ui.set_state("THINKING")
                        _text_result: list[str] = [""]
                        _raw_audio_ref = audio

                        def _do_transcribe():
                            _text_result[0] = self._stt.transcribe(_raw_audio_ref)

                        _t_asr = threading.Thread(target=_do_transcribe, daemon=True)
                        _t_asr.start()
                        _t_asr.join()

                        text = _text_result[0]
                        if text.strip():
                            self._prefetch_thread = threading.Thread(
                                target=self._prefetch_context,
                                args=(text,),
                                daemon=True,
                            )
                            self._prefetch_thread.start()
                            self._process_message(text)
                except queue.Empty:
                    pass
    except Exception as e:
        print(f"[STT-Whisper] Mic error: {e}")
        traceback.print_exc()

def _listen_vosk(self) -> None:
    """Mic → Vosk streaming → LLM loop."""
    q: queue.Queue = queue.Queue(maxsize=200)

    def callback(indata, frames, time_info, status):
        with self._speaking_lock:
            is_speaking = self._speaking
        if not is_speaking and not self.ui.muted:
            try:
                q.put_nowait(indata.copy())
            except queue.Full:
                pass

    try:
        with sd.InputStream(
            samplerate=SAMPLE_RATE_IN,
            channels=CHANNELS,
            dtype="int16",
            blocksize=4096,
            callback=callback,
        ):
            self.ui.write_log("SYS: Mic active (Vosk STT).")
            while True:
                try:
                    chunk = q.get(timeout=0.1)
                    text, is_final = self._stt.process_chunk(chunk.tobytes())
                    if is_final and text.strip():
                        self._process_message(text)
                except queue.Empty:
                    pass
    except Exception as e:
        print(f"[STT-Vosk] Mic error: {e}")
        traceback.print_exc()

# ------------------------------------------------------------------
# Text command loop (UI input box)
# ------------------------------------------------------------------

def _text_command_loop(self) -> None:
    while True:
        try:
            text = self._text_queue.get(timeout=0.5)
            if text.strip():
                with self._processing_lock:
                    self._process_message(text)
        except queue.Empty:
            pass
        except Exception as e:
            short = str(e)[:120]
            self.ui.show_error_state(f"TextCmd — {short}")
            traceback.print_exc()

# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------

