"""The teacher's voice, offline: replies split into Turkish / English parts correctly (English never goes to the
Turkish voice) and the Turkish voice (app/tts_tr, ONNX) makes speech without PyTorch.
Usage: python teacher_speech_test.py   (needs data/dictionary.db; uses a temporary data folder)"""

import io
import os
import shutil
import sys
import tempfile
import time
import wave
sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # ✓ on a Windows (cp1254) console

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
os.environ["EP_DATA_DIR"] = tempfile.mkdtemp()  # never the real data
shutil.copy(os.path.join(ROOT, "data", "dictionary.db"), os.environ["EP_DATA_DIR"])
sys.path.insert(0, os.path.join(ROOT, "app"))

from backend.teacher_speech import segments  # noqa: E402
from backend.tts_tr import tts_tr  # noqa: E402

problems = []


def parts(reply):
    return [(s["lang"], s["text"]) for s in segments(reply)]


def expect(reply, wanted):
    got = parts(reply)
    ok = got == wanted
    print(("✓ " if ok else "✗ ") + reply.replace("\n", " ⏎ ")[:70])
    if not ok:
        problems.append(f"{reply!r}\n   got:  {got}\n   want: {wanted}")


expect("- I have worked here since 2020. (2020'den beri burada çalışıyorum.)",
       [("en", "I have worked here since 2020."), ("tr", "2020'den beri burada çalışıyorum.")])
expect("- I have finished the report. (Raporu bitirdim.) - Bu, şu anla bağlantılıdır.",
       [("en", "I have finished the report."), ("tr", "Raporu bitirdim. Bu, şu anla bağlantılıdır.")])
expect('Hayır, burada bir hata var. Doğrusu "I **have been working** here since 2020".',
       [("tr", "Hayır, burada bir hata var. Doğrusu"), ("en", "I have been working here since 2020.")])
expect("**since** bir başlangıç noktası, **for** ise süre belirtir.",
       [("en", "since"), ("tr", "bir başlangıç noktası,"), ("en", "for"), ("tr", "ise süre belirtir.")])
# Words both languages have stay Turkish among Turkish words, English among English words.
expect("Bu program her gün çalışır, on dakika sürer; son toplantıda da öyleydi.",
       [("tr", "Bu program her gün çalışır, on dakika sürer; son toplantıda da öyleydi.")])
expect("Evet, doğru: make a decision, do your homework.",
       [("tr", "Evet, doğru:"), ("en", "make a decision, do your homework.")])
# Inflected Turkish the dictionary does not know is Turkish, also right after English.
expect('"I have been working here" demelisin.', [("en", "I have been working here"), ("tr", "demelisin.")])
expect("İpucu: \"Make\" genellikle bir çıktı (output) yaratmayı ifade eder.",
       [("tr", "İpucu:"), ("en", "Make"), ("tr", "genellikle bir çıktı"), ("en", "output"), ("tr", "yaratmayı ifade eder.")])
expect("> Şu cümleyi İngilizceye çevir: Raporu henüz göndermedim.",
       [("tr", "Şu cümleyi İngilizceye çevir: Raporu henüz göndermedim.")])

# The Turkish voice: ONNX on onnxruntime, no PyTorch, 24 kHz WAV, numbers read aloud.
if not tts_tr.available():
    problems.append("app/tts_tr model files missing")
else:
    t0 = time.perf_counter()
    wav = tts_tr.synthesize("Toplantı 14:30'da başlıyor; 3 rapor hazır.", seed=1)
    took = time.perf_counter() - t0
    with wave.open(io.BytesIO(wav)) as w:
        rate, seconds = w.getframerate(), w.getnframes() / w.getframerate()
    ok = rate == 24000 and seconds > 1.5 and "torch" not in sys.modules
    spoken = tts_tr.spoken("Toplantı 14:30'da başlıyor; 3 rapor hazır.")
    print(("✓ " if ok else "✗ ") + f"Türkçe ses: {seconds:.1f} s ses, {took:.2f} s (ilk yükleme dahil), {rate} Hz — “{spoken}”")
    if not ok:
        problems.append(f"Turkish voice: rate {rate}, {seconds:.2f}s, torch loaded: {'torch' in sys.modules}")
    if "on dört otuz" not in spoken or "üç rapor" not in spoken:
        problems.append(f"numbers not read aloud: {spoken}")

print("Sorun yok ✓" if not problems else "\n".join(problems))
sys.exit(1 if problems else 0)
