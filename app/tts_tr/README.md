# Türkçe ses (öğretmen) — EMA Lightning, ONNX

Öğretmenin Türkçe cevaplarını sesli okuyan model. İngilizce kısımlar bu modelle **okunmaz** (yabancı
kelimeleri Türkçe yazım kurallarıyla okur); onları İngilizce ses (Kokoro) okur — `backend/teacher_speech.py`.

- Kaynak: [canberkkkkkk/ema-lightning](https://huggingface.co/canberkkkkkk/ema-lightning) (paket
  `ema-lightning` 1.0.1, kod: github.com/canberk7/ema-lightning), **Apache License 2.0** (`LICENSE`).
  8,6 M parametre (5,6 M akustik model + 3 M ses çözücü), tek ses, 48 kHz.
- Değişiklik: ağırlıklar ONNX'e dönüştürüldü (`text.onnx` metin + süre, `sound.onnx` hizalama + 4 adım,
  `decoder.onnx` ses çözücü; `vocab.json` alfabe ve adımlar). Ağırlıklar ve hesap aynıdır; tek fark ONNX'te
  olmayan `expm1(x)` yerine `exp(x) - 1`. Böylece uygulama PyTorch'suz, zaten kurulu onnxruntime ile çalışır
  (PyTorch işlemci sürümü kurulunca ~700 MB; bu dosyalar ~35 MB).
- Doğrulama (2026-10-07): aynı gürültüyle orijinal PyTorch çıktısına göre en büyük fark 1,4e-4, bağıl hata
  5e-5 (duyulmaz), ses uzunluğu birebir; işlemcide ~21× gerçek zaman (orijinal PyTorch ~6×).
- Metin: `normalizer-tr` (sayı, tarih, saat, para… okunuşa çevirir; Rust, bağımlılıksız) +
  `backend/tts_tr.py` (orijinal `frontend.py`, `chunker.py`, `engine.py` adımlarının numpy karşılığı).

Yeniden dönüştürmek gerekirse: orijinal paketi ve ağırlıkları indir, PyTorch'u geçici bir klasöre kur,
`model.text_stage`, `model.sound_stage` (batch 1, maske hep dolu) ve `Decoder(z, None)`'u
`torch.onnx.export(..., opset_version=18, dynamo=False)` ile dışa aktar (L, T dinamik), sonra çıktıyı
orijinalle karşılaştır.
