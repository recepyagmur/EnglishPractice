"""Speech-to-text with faster-whisper. GPU (CUDA) when possible, CPU fallback."""

import io
import logging
import os
import sys
import threading
import time
from pathlib import Path

import numpy as np

from .config import STT_MODELS_DIR

log = logging.getLogger("stt")


def _add_cuda_dll_dirs() -> None:
    """Windows: cuBLAS comes from the nvidia-cublas-cu12 wheel (cuDNN ships inside ctranslate2)."""
    nvidia = Path(sys.prefix) / "Lib" / "site-packages" / "nvidia"
    for bin_dir in nvidia.glob("*/bin"):
        os.add_dll_directory(str(bin_dir))
        os.environ["PATH"] = f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"


def _preload_cuda_libs() -> None:
    """Linux: cuBLAS and cuDNN come from the nvidia-cublas-cu12 / nvidia-cudnn-cu12 wheels (ctranslate2's Linux
    wheel does not bundle cuDNN). ctranslate2 opens them by name ("libcublas.so.12"), and LD_LIBRARY_PATH is only
    read when a program starts, so load them here first: the loader then reuses the loaded copies. They depend on
    each other, so repeat until nothing more loads. No NVIDIA packages (no NVIDIA GPU): nothing to do."""
    import ctypes
    import sysconfig

    nvidia = Path(sysconfig.get_paths()["purelib"]) / "nvidia"
    pending = sorted(p for p in nvidia.glob("*/lib/lib*.so*") if p.is_file())
    while pending:
        failed = []
        for lib in pending:
            try:
                ctypes.CDLL(str(lib), mode=ctypes.RTLD_GLOBAL)
            except OSError:
                failed.append(lib)
        if len(failed) == len(pending):
            log.info("CUDA libraries not loaded: %s", ", ".join(p.name for p in failed))
            break
        pending = failed


if os.name == "nt":
    _add_cuda_dll_dirs()
else:
    _preload_cuda_libs()


class SpeechToText:
    def __init__(self) -> None:
        self.state = "idle"  # idle | loading | ready | error
        self.message = ""
        self.model_name = None
        self.device = None
        self._model = None
        self._load_lock = threading.Lock()
        self._run_lock = threading.Lock()

    # ---------------------------------------------------------------- loading

    def load_async(self, model_name: str, device: str = "cuda") -> None:
        threading.Thread(target=self.load, args=(model_name, device), daemon=True).start()

    def load(self, model_name: str, device: str = "cuda") -> None:
        with self._load_lock:
            if self.state == "ready" and self.model_name == model_name:
                return
            self.state, self.message = "loading", f"Whisper '{model_name}' yükleniyor…"
            attempts = [("cuda", "int8_float16"), ("cpu", "int8")] if device == "cuda" else [("cpu", "int8")]
            errors = []
            for dev, compute_type in attempts:
                try:
                    model = self._create(model_name, dev, compute_type)
                    self._warm_up(model)
                except Exception as e:  # CUDA problems surface as RuntimeError/OSError
                    log.warning("Whisper on %s failed: %s", dev, e)
                    errors.append(f"{dev}: {e}")
                    continue
                self._model, self.model_name, self.device = model, model_name, dev
                self.state = "ready"
                self.message = f"Whisper hazır: {model_name} ({'GPU' if dev == 'cuda' else 'CPU'})"
                if errors:
                    self.message += " — GPU kullanılamadı, CPU'da çalışıyor"
                log.info(self.message)
                return
            self.state = "error"
            self.message = "Whisper yüklenemedi: " + " | ".join(errors)[:300]

    def _create(self, model_name: str, device: str, compute_type: str):
        from faster_whisper import WhisperModel

        kwargs = dict(device=device, compute_type=compute_type, download_root=str(STT_MODELS_DIR))
        if device == "cpu":
            kwargs["cpu_threads"] = max(2, (os.cpu_count() or 4) // 2)
        local = STT_MODELS_DIR / model_name
        if (local / "model.bin").exists():
            # Installed by the setup wizard as a plain folder (models/stt/<name>/).
            return WhisperModel(str(local), **{k: v for k, v in kwargs.items() if k != "download_root"})
        try:
            return WhisperModel(model_name, local_files_only=True, **kwargs)
        except Exception:
            # Not downloaded yet (first run) — fetch it into models/stt.
            self.message = f"Whisper '{model_name}' indiriliyor (ilk kullanım, internet gerekir)…"
            return WhisperModel(model_name, **kwargs)

    @staticmethod
    def _warm_up(model) -> None:
        # CUDA library errors only appear on the first inference, so run one now.
        segments, _ = model.transcribe(np.zeros(16000, dtype=np.float32), language="en", beam_size=1)
        list(segments)

    # ---------------------------------------------------------- transcribing

    def transcribe(self, audio: bytes) -> dict:
        """Transcribe one recorded utterance (any container PyAV can read, e.g. webm/opus)."""
        if self.state != "ready":
            raise RuntimeError(self.message or "Whisper hazır değil.")
        from faster_whisper.audio import decode_audio

        started = time.perf_counter()
        samples = decode_audio(io.BytesIO(audio), sampling_rate=16000)
        with self._run_lock:
            segments, info = self._model.transcribe(
                samples,
                language="en",  # fixed: otherwise accented English may be detected as Turkish
                beam_size=5,
                vad_filter=True,
                word_timestamps=True,
                condition_on_previous_text=False,
            )
            segments = list(segments)

        words = [
            {"word": w.word.strip(), "start": round(float(w.start), 2), "end": round(float(w.end), 2),
             "probability": round(float(w.probability), 3)}
            for seg in segments for w in (seg.words or [])
        ]
        return {
            "text": " ".join(seg.text.strip() for seg in segments).strip(),
            "words": words,
            "audio_seconds": round(len(samples) / 16000, 2),
            "elapsed_ms": round((time.perf_counter() - started) * 1000),
        }


stt = SpeechToText()
