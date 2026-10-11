# Seviye sınavları

Her seviye bir dosya (`A1.json` …). Sınav, seviyenin tüm dersleri tamamlanınca açılır (istenirse
"yine de gir" ile önce de girilebilir). Değerlendirme sunucuda, sınav bitince yapılır
(`app/backend/exams.py`). Her bölüm bir **havuzdur**: her girişte sorular havuzdan yeniden seçilir
(seçim denemeyle birlikte saklanır), böylece sınava tekrar giren başka sorular görür. Değiştirdikten sonra:

```bash
runtime\python\python.exe dev\tests\lessons_content_test.py
runtime\python\python.exe dev\tests\exam_pool_test.py
```

| Alan | Açıklama |
|---|---|
| `title_tr` | Sınavın adı. |
| `grammar_count` | Her girişte sorulacak dilbilgisi sorusu sayısı. Bankadan her dersten eşit sayıda seçilir; bir dersin içinde o ana kadar en az sorulan tür seçilir (her sınavda tüm türler karışık gelir). |
| `tts_speed` | Dinleme bölümündeki seslerin hızı (A1 için biraz yavaş: 0.9). |
| `grammar[]` | Soru bankası: `id` (kalıcı), `lesson` (dersin id'si — "tekrar et" önerisi için), `type`, `explain_tr` ve türün alanları — ders alıştırmalarıyla aynı biçim (`app/content/lessons/README.md`): `choice` (`q`, `options`, `answer` sırası), `fill` (`q` içinde `___`, `answer[]`), `fix` (`q` hatalı cümle, `answer[]`), `transform` (`instruction_tr`, `q`, `answer[]`), `order` (`q` Türkçe yönerge, `words[]` kutular, `answer[]`; ilk cevap tam olarak kutulardan oluşur). Ders alıştırmalarının ve örneklerinin aynısı olmamalı. Seviyenin her dersinden: 3 klasik (choice/fill/fix) + 2 transform + 2 order. |
| `listening.dictation_count`, `listening.dictation[]` | Her girişte kaç dikte; havuz: `id`, `text` (dinlenip aynen yazılacak cümle; rakam, alışılmadık özel isim ve İngiliz/Amerikan yazım farkı olan kelime yok). |
| `listening.comprehension_count`, `listening.comprehension[]` | Her girişte kaç metin; havuz: `id`, `text` (dinlenen kısa metin), `questions[]` (`id`, `q_tr`, `options`, `answer`). |
| `speaking_count`, `speaking[]` | Her girişte kaç konuşma sorusu; havuz: `id`, `question_en` (sesli okunur), `instruction_tr`, `focus`. Cevap mikrofonla (ya da yazarak). |
| `writing[]` | Her girişte biri seçilir: `id`, `instruction_tr`, `prompt_en`, `focus`, `min_words`. |

Kimlikler kalıcıdır (eski denemeler onlarla saklanır); bir maddeyi silmek yerine düzelt. Havuz biçiminden
önce başlatılmış denemeler her bölümün ilk maddeleriyle değerlendirilir (eski sınavın maddeleri, dosyada başta kalır).

Yeni maddeler ayrı dosyalarda yazılıp `dev/tools/merge_exams.py <klasör>` ile eklenir (biçimi de o korur).

Puanlama: dilbilgisi %40, dinleme %20, konuşma %20, yazma %20. Geçme: toplam ≥ %70 ve her bölüm ≥ %50.
