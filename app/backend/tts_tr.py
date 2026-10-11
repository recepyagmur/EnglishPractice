"""Turkish text to speech for the teacher: EMA Lightning (Apache-2.0, huggingface.co/canberkkkkkk/ema-lightning)
converted to ONNX, so it runs on onnxruntime (already used by Kokoro) without PyTorch. app/tts_tr/README.md
tells how the model files were made.

Same steps as the original package (ema_lightning 1.0.1), on numpy:
  text → normalizer-tr (numbers, dates, money… read aloud) → the model's alphabet → pieces of ≤ ~10 s
  → text.onnx (letters → features + durations) → frame timeline → sound.onnx (aligner + 4 steps from noise)
  → decoder.onnx (latents at 25 Hz → 48 kHz) → 24 kHz WAV.
English is NOT read here: the model reads foreign words with Turkish spelling. The teacher page sends
Turkish parts here and English parts to Kokoro (tts.py).
"""

import json
import logging
import os
import re
import threading
import unicodedata

import numpy as np

from .config import APP_DIR
from .tts import to_wav

log = logging.getLogger(__name__)

MODEL_DIR = APP_DIR / "tts_tr"
RATE = 48000
OUT_RATE = 24000
MAX_WORD_FRAMES = 250
MAX_FRAMES = 3000

# ---------------------------------------------------------------- text (frontend.py, chunker.py)

TURKISH = frozenset("çğıöşüÇĞİÖŞÜ")
TYPOGRAPHY = str.maketrans({"’": "'", "‘": "'", "ʼ": "'", "´": "'", "`": "'", "“": '"', "”": '"', "„": '"',
                            "«": '"', "»": '"', "–": "-", "—": "-", "−": "-", "…": "..."})
UNSAFE = re.compile("[\x00-\x08\x0b-\x1f\x7f-\x9f؜‎‏‪-‮⁦-⁩]")
BLOCK_BYTES = 8 * 1024
LETTERS_PER_SECOND, MAX_SECONDS, MAX_LETTERS = 18.0, 10.0, 250
SENTENCE_PAUSE, CLAUSE_PAUSE = 0.25, 0.12
CUTS = ((re.compile(r"[.!?]+[\"')]*(?= )"), SENTENCE_PAUSE), (re.compile(r"[,;:](?= )"), CLAUSE_PAUSE),
        (re.compile(r"\S(?= )"), CLAUSE_PAUSE))
LETTER = re.compile(r"[^\W\d_]")


def _blocks(text):
    words, block, size = text.split(), [], 0
    for word in words:
        n = len(word.encode("utf-8")) + 1
        if block and size + n > BLOCK_BYTES:
            yield " ".join(block)
            block, size = [], 0
        block.append(word)
        size += n
    if block:
        yield " ".join(block)


def _finish(piece):
    if piece.rstrip("\"')")[-1:] in (".", "!", "?"):
        return piece
    return piece.rstrip(",;:- ") + "."


def chunk(text, speed):
    """[(piece, seconds of silence after it)], each piece ending in terminal punctuation."""
    limit = int(min(MAX_LETTERS, LETTERS_PER_SECOND * MAX_SECONDS * speed))
    pieces, rest = [], text.strip()
    while rest:
        cut, pause = len(rest), 0.0
        if len(rest) > limit:
            cut = limit
            for pattern, gap in CUTS:
                ends = [m.end() for m in pattern.finditer(rest, 0, limit + 1)]
                if ends:
                    cut, pause = ends[-1], gap
                    break
        piece, rest = rest[:cut].strip(), rest[cut:].strip()
        if LETTER.search(piece):
            pieces.append((_finish(piece), pause))
    if pieces:
        pieces[-1] = (pieces[-1][0], 0.0)
    return pieces


# ---------------------------------------------------------------- audio (audio.py Resampler, whole signal)

def _downsample(x: np.ndarray, factor: int) -> np.ndarray:
    """48 kHz → 48/factor kHz through the same linear-phase windowed-sinc low-pass as the original."""
    if factor == 1:
        return x
    half = 32 * factor
    n = np.arange(-half, half + 1, dtype=np.float64)
    cutoff = 0.45 / factor
    taps = 2 * cutoff * np.sinc(2 * cutoff * n) * np.blackman(2 * half + 1)
    taps /= taps.sum()
    padded = np.concatenate([np.zeros(half), x.astype(np.float64), np.zeros(half + factor)])
    y = np.convolve(padded, taps, mode="valid")  # symmetric taps: correlation = convolution
    return y[::factor][:(len(x) + factor - 1) // factor].astype(np.float32)


# ---------------------------------------------------------------- the model

class TurkishTTS:
    def __init__(self, model_dir=MODEL_DIR):
        self.dir = model_dir
        self.lock = threading.Lock()
        self.sessions = None
        self.normalizer = None

    def available(self) -> bool:
        return all((self.dir / f).exists() for f in ("text.onnx", "sound.onnx", "decoder.onnx", "vocab.json"))

    def _load(self):
        if self.sessions is not None:
            return
        import onnxruntime as ort
        from normalizer_tr import Normalizer

        meta = json.loads((self.dir / "vocab.json").read_text(encoding="utf-8"))
        self.vocab = meta["vocab"]
        self.stoi = {ch: i for i, ch in enumerate(self.vocab)}
        self.alphabet_set = frozenset(self.vocab)
        self.steps, self.latent_dim, self.hop = len(meta["times"]), meta["latent_dim"], meta["hop"]
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = max(1, min(4, (os.cpu_count() or 2) // 2))  # leave the CPU to the rest
        opts.log_severity_level = 3
        self.sessions = {name: ort.InferenceSession(str(self.dir / f"{name}.onnx"), opts,
                                                    providers=["CPUExecutionProvider"])
                         for name in ("text", "sound", "decoder")}
        self.normalizer = Normalizer()
        log.info("Türkçe ses (EMA Lightning, ONNX) yüklendi")

    # text → the model's alphabet (frontend.py)
    def spoken(self, text: str) -> str:
        text = UNSAFE.sub(" ", text.encode("utf-8", "ignore").decode("utf-8"))
        if not text.strip():
            return ""
        parts = []
        for block in _blocks(text):
            try:
                parts.append(self.normalizer.normalize(block, ambiguity_policy="fallback").normalized_text)
            except Exception:  # invalid input or a resource limit: keep the words rather than lose the sentence
                parts.append(block)
        text = " ".join(parts).translate(TYPOGRAPHY).replace("İ", "i").replace("I", "ı").lower()
        out = []
        for ch in text:
            if ch not in TURKISH:
                ch = "".join(c for c in unicodedata.normalize("NFKD", ch) if not unicodedata.combining(c))
            out.append(ch if ch and all(c in self.alphabet_set for c in ch) else " ")
        return re.sub(r"\s+", " ", "".join(out)).strip()

    def _piece(self, text):
        ids = np.array([self.stoi.get(ch, 1) for ch in text], np.int64)
        starts = [i for i, ch in enumerate(text) if ch != " " and (i == 0 or text[i - 1] == " ")] or [0]
        bounds = [0] + starts[1:] + [len(text)]
        cw, wstart = [], []
        for w, (a, b) in enumerate(zip(bounds, bounds[1:])):
            cw += [w] * (b - a)
            wstart += [a] * (b - a)
        return ids, np.array(cw, np.int64), np.array(wstart, np.int64)

    def piece_audio(self, text, speed=1.0, seed=0, noise=None):
        """48 kHz audio for one piece (engine.py plan + think + a whole decode)."""
        ids, cw, wstart = self._piece(text)
        h, dur = self.sessions["text"].run(None, {"ids": ids[None]})
        dur = dur / speed
        counts = np.clip(np.round(np.bincount(cw, weights=dur[0].astype(np.float64), minlength=cw[-1] + 1)
                                  .astype(np.float32)), 1, MAX_WORD_FRAMES).astype(np.int64)
        frames = min(int(counts.sum()), MAX_FRAMES)
        fw = np.repeat(np.arange(len(counts)), counts)[:frames]
        fp = ((np.arange(frames) - (np.cumsum(counts) - counts)[fw]).astype(np.float64) / counts[fw]).astype(np.float32)
        if noise is None:
            noise = np.random.default_rng(seed).standard_normal((self.steps, frames, self.latent_dim)).astype(np.float32)
        (latents,) = self.sessions["sound"].run(None, {
            "h": h, "dur": dur.astype(np.float32), "cw": cw[None], "wstart": wstart[None],
            "fw": fw[None].astype(np.int64), "fp": fp[None], "noise": noise[None]})
        (audio,) = self.sessions["decoder"].run(None, {"z": latents})
        return audio[0]

    def synthesize(self, text: str, speed: float = 1.0, seed: int | None = None) -> bytes:
        """WAV (24 kHz) of Turkish text; silence for text with nothing readable."""
        with self.lock:
            self._load()
            seed = np.random.default_rng().integers(2**31) if seed is None else seed
            out = []
            for i, (piece, pause) in enumerate(chunk(self.spoken(text), speed)):
                out.append(self.piece_audio(piece, speed, seed + i))
                if pause:
                    out.append(np.zeros(round(pause * RATE), np.float32))
        audio = np.concatenate(out) if out else np.zeros(RATE // 10, np.float32)
        return to_wav(_downsample(audio, RATE // OUT_RATE), OUT_RATE)


tts_tr = TurkishTTS()
