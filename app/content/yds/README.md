# YDS tarzı sorular (🎯 Kendini Test Et → YDS tarzı sınav)

ÖSYM'nin YDS / e-YDS / YÖKDİL formatında **özgün** sorular (gerçek ÖSYM soruları telif altındadır; buraya
kopyalanmaz). Düzey B2–C1; konular YDS'deki gibi genel ve akademik: bilim, teknoloji, sağlık, psikoloji,
ekonomi, çevre, tarih, eğitim, toplum. Her soru türü bir dosya; her sorunun **tek ve tartışmasız** doğru
cevabı ve Türkçe açıklaması var.

Değiştirdikten sonra doğrula (tek dosya ya da hepsi):

```bash
runtime\python\python.exe dev\tests\yds_content_test.py [app\content\yds\vocab.json]
```

## Genel kurallar (her soru için)

| Alan | Açıklama |
|---|---|
| `id` | Kalıcı kimlik (aşağıdaki biçimde). **Asla değiştirme.** |
| `options` | Tam **5** seçenek (YDS gibi A–E), hepsi birbirinden farklı, benzer uzunlukta; doğru cevap göze batmamalı. |
| `answer` | Doğru seçeneğin sırası (0–4). Doğru cevap seçenekler arasında **rastgele** dağılsın (hep 0 ya da 2 olmasın). |
| `explain_tr` | Türkçe açıklama (2–5 cümle): doğru cevap neden doğru; en güçlü 1–2 çeldirici neden yanlış. Dilbilgisi terimleri Türkçe; İngilizce kelime/ifadeler `[en:…]` ile işaretlenir. En fazla 600 karakter. |
| `tags` | İsteğe bağlı, kısa İngilizce etiketler (`["phrasal verb"]`, `["relative clause"]`). |

- Boşluk işareti her yerde `----` (dört tire). Dilbilgisi sorusunda iki boşluk olabilir: `---- / ----`, seçenekler `"has been / was"`.
- Seçeneklerde ve cümlelerde işaretleme (`[en:]`) **yok**; yalnız `explain_tr` içinde.
- İngilizce doğal, hatasız, YDS ciddiyetinde (akademik/gazete dili); cümleler 12–30 kelime.
- **Tek doğru cevap:** çeldiriciler dilbilgisi, anlam ya da bağlam açısından **kesin** yanlış olmalı; "bu da olur"
  denebilecek seçenek koyma. Denetçi her soruda bunu kontrol eder.
- Aynı soru/parça iki kez olmaz; parça konuları çeşitlensin.

## Dosyalar, kimlikler ve adetler

| Dosya | `type` | Kimlik | Adet | Soru yapısı |
|---|---|---|---|---|
| `vocab.json` | `vocab` | `voc-001`… | 24 | Kelime: `q` (boşluklu cümle), seçenekler tek kelime/ifade (aynı türden: 5 isim, 5 fiil, 5 phrasal verb…). |
| `grammar.json` | `grammar` | `gra-001`… | 40 | Dilbilgisi: `q` 1–2 boşluklu cümle; konular: zamanlar, modal, edilgen, bağlaçlar, relative clause, edat, koşul, -ing/to, zarf-bağlaç (however/although…), sayılabilirlik, karşılaştırma. |
| `cloze.json` | `cloze` | parça `clz-01`…`clz-08`, soru `clz-01-1`…`clz-01-5` | 8 parça × 5 soru = 40 | `passage` (90–140 kelime) içinde `(1)----` … `(5)----`; `questions[]`: `id`, `n` (1–5), `options`, `answer`, `explain_tr`. Her parçada 2–3 dilbilgisi + 2–3 kelime/edat/bağlaç boşluğu. |
| `sentence.json` | `sentence` | `sen-001`… | 40 | Cümle tamamlama: `q` = cümlenin yarısı + `----` (başta ya da sonda); seçenekler 5 yan cümle/ana cümle. Yalnız biri hem dilbilgisi hem anlam olarak uyar. |
| `translation.json` | `translation` | `tra-en-001`… (İng→Tr), `tra-tr-001`… (Tr→İng) | 12 + 12 = 24 | `direction`: `"en-tr"` ya da `"tr-en"`; `q` kaynak cümle; seçenekler 5 çeviri. Çeldiriciler: eksik/fazla öğe, yanlış zaman, yanlış özne-nesne, yanlış bağlaç. |
| `reading.json` | `reading` | parça `rea-01`…`rea-20`, soru `rea-01-1`…`rea-01-4` | 20 parça × 4 soru = 80 | `passage` (140–200 kelime, tek paragraf); `questions[]`: `id`, `q`, `options`, `answer`, `explain_tr`. Soru çeşitleri: "According to the passage, …", "It is stated/implied/understood that …", "The main point/purpose …", "The author … to …", "It can be inferred that …" |
| `dialogue.json` | `dialogue` | `dia-001`… | 20 | `lines[]`: `{"speaker", "text"}` 4–6 satır; tam **bir** satırın `text`'i `----`; seçenekler 5 replik. |
| `paraphrase.json` | `paraphrase` | `par-001`… | 16 | Anlamca en yakın cümle: `q` cümle; seçenekler 5 cümle (biri aynı anlam; diğerleri anlamı değiştirir). |
| `paragraph.json` | `paragraph` | `pcm-001`… | 16 | Paragraf tamamlama: `passage` (70–110 kelime) içinde **bir** `----` (başta, ortada ya da sonda); seçenekler 5 cümle. |
| `irrelevant.json` | `irrelevant` | `irr-001`… | 20 | Anlam bütünlüğünü bozan cümle: `sentences[]` tam 5 cümle (I–V, aynı konu); `answer` bozanın sırası (0–4); `options` **yok**. Bozan cümle konuyla ilgili ama paragrafın akışına/odağına uymayan bir cümle olmalı (bariz alakasız olmasın). |

Dosya biçimi:

```json
{"type": "vocab", "sources": [{"title": "...", "site": "...", "url": "https://..."}],
 "items": [ { ... }, ... ]}
```

`sources`: türün dayandığı en az 2 gerçek sayfa (ÖSYM YDS kılavuzu/örnek soru sayfası, British Council,
Cambridge Dictionary grammar vb.). Bağlantılar doğrulanmış olmalı; uydurma bağlantı koyma.

## Örnekler

```json
{"id": "voc-001",
 "q": "The committee's decision to ---- the proposal surprised even its strongest supporters.",
 "options": ["reject", "evaporate", "inhabit", "illustrate", "postpone"],
 "answer": 0,
 "explain_tr": "Anlam: komitenin teklifi [en:reject] (reddetme) kararı destekçileri bile şaşırttı; \"even its strongest supporters\" olumsuz bir karar bekletiyor. [en:postpone] (ertelemek) dilbilgisi olarak uyar ama şaşkınlık ifadesine daha az uygun; [en:evaporate], [en:inhabit], [en:illustrate] anlamca uymaz.",
 "tags": ["verb"]}
```

```json
{"id": "sen-001",
 "q": "Although the new vaccine has proved effective in clinical trials, ----.",
 "options": ["it has already been approved for use in every country",
             "its long-term side effects are still unknown",
             "the researchers were awarded a prize for their work",
             "the trials were carried out in several countries",
             "it was developed much faster than earlier vaccines"],
 "answer": 1,
 "explain_tr": "[en:Although] zıtlık kurar: aşı etkili olduğu hâlde beklenmeyen/olumsuz bir şey gelmeli — uzun vadeli yan etkilerin bilinmemesi. Diğer seçenekler olumlu ya da nötr bilgi verir; zıtlık oluşturmaz."}
```

```json
{"id": "irr-001",
 "sentences": [
   "(I) Urban farming has grown rapidly in many large cities over the past decade.",
   "(II) Rooftop gardens and vertical farms allow residents to grow vegetables close to where they live.",
   "(III) Supporters argue that this reduces transport costs and provides fresher food.",
   "(IV) Traditional farming methods in rural areas date back thousands of years.",
   "(V) Critics, however, point out that the yields are too small to feed a city."],
 "answer": 3,
 "explain_tr": "Paragraf kent tarımının (urban farming) yükselişi ve artı/eksilerini anlatıyor; IV. cümle kırsal geleneksel tarımın tarihine geçerek odağı bozuyor."}
```
