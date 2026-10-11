"""Text-to-speech with Kokoro-82M (ONNX, CPU) — keeps the VRAM for the LLM and Whisper."""

import io
import logging
import os
import re
import threading
import time
import wave

import numpy as np

from .config import TTS_MODELS_DIR, script

log = logging.getLogger("tts")

KOKORO_DIR = TTS_MODELS_DIR / "kokoro"
MODEL_FILE = KOKORO_DIR / "kokoro-v1.0.onnx"
VOICES_FILE = KOKORO_DIR / "voices-v1.0.bin"
LANGS = {"a": "en-us", "b": "en-gb"}
# LLMs like curly quotes and dashes; the phonemizer is happier with plain ASCII.
_TYPOGRAPHY = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"', "—": ", ", "–": ", ", "…": "..."})
DEFAULT_VOICES = {"a": "af_heart", "b": "bf_emma"}


class TextToSpeech:
    def __init__(self) -> None:
        self.state = "idle"  # idle | loading | ready | error
        self.message = ""
        self.voices: list[str] = []
        self._kokoro = None
        self._lock = threading.Lock()

    def load_async(self) -> None:
        threading.Thread(target=self.load, daemon=True).start()

    def load(self) -> None:
        if not (MODEL_FILE.exists() and VOICES_FILE.exists()):
            self.state = "error"
            self.message = f"Kokoro model dosyaları yok (models/tts/kokoro). {script('setup')} ile indirin."
            return
        self.state, self.message = "loading", "Kokoro yükleniyor…"
        try:
            import onnxruntime as ort
            from kokoro_onnx import Kokoro

            opts = ort.SessionOptions()
            # Leave a few cores for the web server, Whisper decoding and the OS.
            opts.intra_op_num_threads = max(2, (os.cpu_count() or 4) // 2)
            session = ort.InferenceSession(str(MODEL_FILE), opts, providers=["CPUExecutionProvider"])
            kokoro = Kokoro.from_session(session, str(VOICES_FILE))
            kokoro.create("Ready.", voice="af_heart", lang="en-us")  # warm-up
        except Exception as e:
            log.exception("Kokoro failed to load")
            self.state, self.message = "error", f"Kokoro yüklenemedi: {e}"
            return
        self._kokoro = kokoro
        self.voices = sorted(v for v in kokoro.get_voices() if v[:2] in ("af", "am", "bf", "bm"))
        self.state, self.message = "ready", "Kokoro hazır (CPU)"

    def synthesize(self, text: str, accent: str = "a", voice: str | None = None, speed: float = 1.0) -> bytes:
        """Return a 16-bit mono WAV for `text`."""
        if self.state != "ready":
            raise RuntimeError(self.message or "TTS hazır değil.")
        accent = accent if accent in LANGS else "a"
        if voice not in self.voices or voice[0] != accent:
            voice = DEFAULT_VOICES[accent]
        speed = min(1.2, max(0.7, float(speed)))
        text = text.translate(_TYPOGRAPHY)
        with self._lock:  # one ONNX run at a time; it already uses several cores
            started = time.perf_counter()
            samples, rate = self._kokoro.create(text, voice=voice, speed=speed, lang=LANGS[accent])
        log.debug("tts %.0f ms: %s", (time.perf_counter() - started) * 1000, text[:40])
        return to_wav(samples, rate)


def to_wav(samples: np.ndarray, rate: int) -> bytes:
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


# ------------------------------------------------------- sentence splitting

_ABBREVIATIONS = {"mr", "mrs", "ms", "dr", "prof", "st", "vs", "etc", "e.g", "i.e", "jr", "sr", "no"}
_SENTENCE_END = re.compile(r"[.!?]+[\"')\]]*(?=\s)")
# Time to first audio ≈ synthesis time of the first chunk (~0.3 s per second of speech on
# this CPU), so a long first sentence is split at a comma. Never at other words: that
# would break the intonation (e.g. of questions).
FIRST_CHUNK_MIN_CHARS = 30


class SentenceSplitter:
    """Turns streamed LLM text into speakable chunks as early as possible."""

    def __init__(self) -> None:
        self.buffer = ""
        self.emitted = 0

    def feed(self, text: str) -> list[str]:
        self.buffer += text
        out = []
        while True:
            chunk = self._next_chunk()
            if chunk is None:
                break
            out.append(chunk)
        return out

    def flush(self) -> list[str]:
        rest, self.buffer = self.buffer.strip(), ""
        return [rest] if _speakable(rest) else []

    def _next_chunk(self) -> str | None:
        for m in _SENTENCE_END.finditer(self.buffer):
            last_word = self.buffer[: m.start()].rsplit(None, 1)[-1].lower() if self.buffer[: m.start()].strip() else ""
            if m.group().startswith(".") and last_word.rstrip(".") in _ABBREVIATIONS:
                continue
            return self._take(m.end())
        # The first chunk decides the latency: start speaking at a comma if it is long.
        if self.emitted == 0 and len(self.buffer) >= FIRST_CHUNK_MIN_CHARS:
            comma = self.buffer.rfind(", ")
            if comma >= 15:
                return self._take(comma + 1)
        return None

    def _take(self, end: int) -> str | None:
        chunk, self.buffer = self.buffer[:end].strip(), self.buffer[end:]
        if not _speakable(chunk):
            return None if not self.buffer else self._next_chunk()
        self.emitted += 1
        return chunk


def _speakable(text: str) -> bool:
    return any(c.isalnum() for c in text)


tts = TextToSpeech()
