# Geliştirme test betikleri

Sohbet sırasında yazılmış manuel/ölçüm betikleri. Hepsi gömülü Python ile çalışır:

```bash
runtime\python\python.exe dev\tests\<betik>.py
```

## Test sunucusu (kullanıcının açık uygulamasını bozmadan)

Kullanıcının uygulaması (port 8000) açıkken test için **ayrı bir sunucu** kullanılır: aynı Ollama'ya
bağlanır, kendi veri klasörünü kullanır, ses modellerini yüklemez (ikinci Whisper VRAM'e sığmaz).

```bash
copy data\app.db <test klasörü>\app.db   (sqlite backup API ile kopyalamak daha güvenli)
cd app
set EP_DATA_DIR=<test klasörü>
set EP_SKIP_SPEECH=1
set OLLAMA_HOST=127.0.0.1:<çalışan ollama portu, logs/launcher.log'da yazar>
..\runtime\python\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8100
```

## Betikler

| Betik | Ne yapar | Sunucu |
|---|---|---|
| `fake_ollama.py` | Model olmadan akış testi için sahte Ollama (`uvicorn fake_ollama:app --port <p>`) | — |
| `ws_test.py` | Örnek WAV'ı webm/opus'a çevirip `/ws/voice` ile sesli tur gönderir; `wav_to_webm()` diğerlerince kullanılır | 8000 / argüman |
| `ws_tts_test.py` | Sesli tur + TTS ses parçaları, iptal, `speak=false` | 8000 |
| `latency_bench.py N` | Konuşma bitişi → ilk ses gecikmesi (medyan/maks) | 8000 |
| `variety_test.py` | Farklı cümlelerle açılış tepkisi çeşitliliği + gecikme | 8000 |
| `corr_ws_test.py` | Düzeltme olaylarının sohbetten sonra gelmesi | 8100 |
| `preempt_test.py` | Düzeltme sürerken gelen sohbetin beklememesi | 8100 |
| `correction_quality.py` | Tipik Türk öğrenci hatalarıyla düzeltme kalitesi (EP_DATA_DIR/OLLAMA_HOST betik içinde) | — |
| `scenario_test.py` | Senaryo açılışı + turlar + rapor + özel senaryo | 8100 |
| `writing_test.py` | Yazma değerlendirmesi SSE akışı, aşama süreleri | 8100 |
| `custom_think_test.py` | Özel senaryo yapılandırma: düşünme modu açık/kapalı karşılaştırma | — |
| `model_switch_test.py <model>` | Oturum modelini değiştirip hemen mesaj gönderir: `status` olayı, süre, VRAM'deki modeller (`OLLAMA_URL` gerekir) | 8000 |
| `model_bench_test.py` | Hız testini başlatır, test sırasında gelen mesajın beklediğini ve sonuçları gösterir (`OLLAMA_URL`) | 8000 |
| `lessons_content_test.py` | Ders ve sınav içeriğini doğrular (yapı, kategori, cevaplar, en az 2 kaynak, sınavın her dersi kapsaması) | — |
| `patterns_content_test.py [dosya]` | Kalıp içeriğini doğrular (alanlar, kimlik, konu, boşluklar, örnekler kalıbı içeriyor mu, seviye başına kategori sayıları, seviyeler arası tekrar) | — |
| `yds_content_test.py [dosya]` | YDS tarzı soru dosyalarını doğrular (alanlar, 5 seçenek, cevap, boşluklar, parça uzunluğu, havuz adetleri, cevapların A–E dağılımı); `parts/` parça dosyaları da verilebilir | — |
| `vocab_freq_test.py` | En sık 3000 listesi (3000 kelime, tekrar yok, sıra, anlam/tür, sayı/gün/ay yok, hepsi öğrenmeye eklenebilir) ve defterde aynı kelimenin iki kez eklenmemesi | — |
| `sources_check.ps1` | Derslerdeki Cambridge/BBC bağlantılarını sayfa başlığıyla kontrol eder (British Council → WebFetch ile) | — |
| `lesson_check_test.py [url]` | İngilizce-değil algılama + "Kendi cümleni kur" cevap değerlendirmesi | 8100 |
| `pronoun_correction_test.py [url]` | he/she hataları (bağlamsız) düzeltme doğruluğu | 8000/8100 |
| `pronoun_rule_test.py` | he/she kuralı çevrimdışı (sunucu/LLM yok): yakalaması gerekenler + isim/cinsiyetsiz kişi geçen cümlelerde yanlış alarm olmaması | — |
| `exam_test.py [url] [seviye]` | Seviye sınavını doğru cevaplarla API'den çözer; geçmeli, alakasız konuşma 0 almalı | 8100 |
| `teacher_speech_test.py` | Öğretmen sesi (çevrimdışı): cevabın Türkçe/İngilizce parçalara doğru ayrılması (İngilizce asla Türkçe sese gitmez; iki dilde de olan kelimeler) + Türkçe ses (app/tts_tr, ONNX) PyTorch'suz 24 kHz üretir, sayıları okur | — |
| `sync_test.py` | İki bilgisayar eşitlemesi (çevrimdışı; iki veri klasörü + iki bilgisayar adı + sahte Drive klasörü): ilk kurulum/seçim (iki tarafın son çalışması), normal geçiş, kilit uyarısı, çakışmada yenisi kalır + öbürü yedek, öbür bilgisayarın eski verisi yeni çalışmanın üzerine yazılmaz (eski/yeni sürüm), ders açmak veriyi "yeni" yapmaz, silme öbürüne geçer, yarım indirilen dosya ve yeni şema reddedilir, bulutta -wal/-shm kalmaz | — |
| `review_content_test.py [SEVİYE]` | Ders özetleri (`app/content/review/`): her dersin özeti var, 3–5 kural, uzunluklar, işaretleme, tablo/hata sıraları geçerli, "siz" dili yok | — |
| `reviews_test.py` | Ders tekrarı (çevrimdışı, geçici veritabanı): ilk tekrar yarın, eski bitirilenler günde 2 yayılır, aralık merdiveni (iyi/orta/zayıf), mini test önce yanlışları sorar, sık hata yapılan konunun dersi öne alınır, sıfırlama takvimi siler | — |
| `update_test.py` | Uygulama içinden güncelleme (çevrimdışı; geçici klasörde sahte kurulum + GitHub biçiminde zip): uygulama, silinen dosyalar, data/ korunur, sürüm kaydı, yedek, bozuk zip, geliştirme kopyası, denetleme ayarı, değişiklik metni. GitHub'dan indirme ve yeniden açılış elle denenir | — |
| `ui_state_test.py` | Saklanan yarım iş (ders cevapları, kendi cümlelerin, yarım sınav; `backend/ui_state.py`): kaydet/oku/sil, sıfırlama, housekeeping kayıtlı sınavı korur (çevrimdışı, geçici veri) | — |
| `frontend_names_test.py` | Ön yüz betikleri tek global alanı paylaşır: iki dosyada aynı adlı üst düzey fonksiyon/sabit birbirini ezer (words.js sınav sayfasını böyle bozmuştu) — çakışma arar | — |
| `exam_pool_test.py` | Sınav havuzları (çevrimdışı, geçici veri): her girişte dengeli seçim (her ders, karışık türler), tekrar girişte farklı sorular, doğru cevaplar (sıralama kutularla) tam puan, eski biçimli denemeler | — |
| `teacher_test.py [url]` | Öğretmen: serbest soru, alıntılanan cümle kontrolü, "Neden?", ders bağlamı, alıştırma (yanlış/doğru cevap), geçmiş | 8000 (kopya veri) |
| `words_test.py [url]` | Kelime Çalış: listeler, öğrenmeye ekleme, kontrollü örnek cümle üretimi, kendi cümlen kontrolü | 8000 (kopya veri) |
| `patterns_test.py [url]` | Kalıplar: genel bakış, seviye listesi, öğrenmeye alma, tekrar (SM-2), listeden çıkarma, kendi cümlen kontrolü | 8100 (kopya veri) |
| `selftest_test.py [url]` | Kendini Test Et: set/mini deneme başlatma, cevapların gizliliği, kaydetme, sürdürme, bitirme, sonuç, geçmiş, silme | 8100 (kopya veri) |
| `teacher_model_compare.py <rapor.md> [model …]` | Modelleri Türkçe öğretmen sorularıyla karşılaştırır (kendi Ollama'sını açar, eksik modeli indirir) | — |
| `model_quality_ab.py <klasör> [url] [model …]` | Uygulamanın tüm LLM işlerini (düzeltme, sohbet, çeviri, ders, sınav, yazma, senaryo) modellerde karşılaştırır | 8000 (kopya veri) |

Not: bazı betiklerde sohbet sırasındaki geçici klasör yolları (scratchpad) ve portlar sabit yazılı;
kullanmadan önce kontrol edin. Örnek ses: `setup/assets/sample.wav`.

## Tarayıcıda arayüz testi (Claude'un tarayıcı paneli)

- Panelde `javascript_tool` sayfanın kendi değişkenlerine erişemez (ayrı dünya): sayfaya
  `<script>` enjekte edilir (`document.body.appendChild(script)`), sonuç `document.body.dataset`'e yazılır.
- Sahte mikrofon: `navigator.mediaDevices.getUserMedia`'yı, `/_test_sample.wav`'ı
  `MediaStreamDestination` üzerinden çalan bir akışla değiştir (dosyayı geçici olarak
  `app/frontend/`'a kopyalayıp sonra sil).
- `confirm`/`alert` paneli kilitler: test için enjekte edilen script ile `window.confirm = () => true`.
- Panel ekranda değilken `requestAnimationFrame` ve CSS geçişleri durur (gösterge/animasyon "takılı" görünür).
