# Ders içerikleri

Her seviye bir dosya: `A1.json`, `A2.json`, `B1.json`, `B2.json`, `C1.json` (olmayan seviye arayüzde
"yakında" görünür). Dosyadaki sıra, derslerin sırasıdır. Anlatımlar elle yazılır (yerel modelin
Türkçesi güvenilir değil); yapay zeka sadece İngilizce soru üretir ve sohbet eder.

Değiştirdikten sonra doğrula:

```bash
runtime\python\python.exe dev\tests\lessons_content_test.py
```

## Bir dersin alanları

| Alan | Açıklama |
|---|---|
| `id` | Kalıcı kimlik (ilerleme bununla saklanır). **Asla değiştirme / başka derse verme.** |
| `title_tr`, `title_en` | Başlık. `title_en` yapay zekaya konu adı olarak gider. |
| `categories` | Dersin öğrettiği hata kategorileri (`app/backend/errors.py` kimlikleri). Zayıf noktalar bu eşleşmeyle derse yönlendirilir. |
| `intro_tr` | Kısa giriş: ne işe yarar, Türkçeden farkı. |
| `sections[]` | `title_tr`, `text_tr`, isteğe bağlı `table` (`head`, `rows`), `examples[]` (`en`, `tr`). |
| `mistakes[]` | Türklerin sık yaptığı hatalar: `wrong`, `right`, `note_tr`. |
| `exercises[]` | Anında kontrol edilen alıştırmalar (aşağıda). |
| `practice` | Sohbet pratiği: `focus` (İngilizce, yapay zekaya konuşma konusu), `tasks` ([Türkçe görev, İngilizce görev]). |

## Alıştırma türleri

- `choice`: `q`, `options[]`, `answer` (doğru seçeneğin sırası, 0'dan başlar), `explain_tr`.
- `fill`: `q` içinde `___` boşluğu; `answer[]` kabul edilen cevaplar; `explain_tr`.
- `fix`: `q` hatalı cümle; `answer[]` kabul edilen doğru cümleler; `explain_tr`.
- `transform`: `instruction_tr` (ör. "Olumsuz yap", "Soru cümlesi yap", "Past simple'a çevir"), `q` kaynak
  cümle, `answer[]` kabul edilen cümleler; `explain_tr`.
- `order`: `words[]` karıştırılmış gösterilecek kelime kutuları (birden fazla kelime içerebilir: "since 2020"),
  `answer[]` doğru cümle(ler) — **ilk cevap tam olarak bu kutulardan oluşmalı** (içerik testi kontrol eder);
  isteğe bağlı `q` (yönerge); `explain_tr`.
- `match`: `pairs[]` = [[İngilizce, Türkçe], …] en az 3 çift, iki taraf da benzersiz; isteğe bağlı `q`; `explain_tr`.
  Hepsi hatasız eşleşirse doğru sayılır.
- `listen`: `text` (sesli okunan İngilizce cümle), `answer[]` kabul edilen yazımlar (genelde `[text]`); `explain_tr`.

Cevap karşılaştırması büyük/küçük harf, fazla boşluk, virgül, sondaki noktalama, yaygın kısaltmalar
(don't = do not, I'm = I am, I'd have = I would have…) ve kısaltma noktalarına (2 p.m. = 2pm) duyarsızdır;
zamirden sonra gelen 's = is, ardından V3 gelirse has da (She's finished = She has finished); 'd = would,
ardından V3 ya da "better" gelirse had da (I'd gone = I had gone). Başka her fark yanlış sayılır. Bu yüzden **doğru olan her yaygın varyant `answer[]`'a yazılmalıdır**.

## Terim işaretleme (tırnak yerine)

Türkçe metinlerde geçen İngilizce, Türkçe örnek ve semboller tırnakla değil işaretle yazılır; uygulama bunları
görsel olarak ayırır (`text.js` `Text.MARK`):

- `[en:does]`, `[en:I'm an engineer]`, `[en:-ing]` → mavi İngilizce kutucuk (kelimeleri sözlük için tıklanır),
- `[tr:bilgiler]` → italik Türkçe, `[key:.]`, `[key:@]` → klavye tuşu görünümü.

Örnek: `[key:@] = [en:at]`, `[en:you] ile [en:do]; [en:does] sadece [en:he/she/it] ile`,
`[en:informations] gibi`, `[en:Good]'daki`. Dilbilgisi terimleri (present simple, passive, V3, fiil) işaretlenmez.

Yalnız şu alanlarda: `intro_tr`, bölüm `title_tr` ve `text_tr`, `note_tr`, `explain_tr`, `instruction_tr`, `q_tr`,
choice/order/match sorularının `q`'su, sınavda dinleme sorularının seçenekleri. Cevaplarda, örneklerde, tablolarda,
başlıklarda ve karşılaştırılan/seslendirilen metinlerde **asla** (içerik testi kontrol eder). Modele giden metinler
`lessons.plain()` ile tırnaklı düz metne çevrilir.

## Bir dersin kapsamı (hedef)

- Anlatım: 4–6 bölüm, toplam ~400–700 kelime Türkçe; yapı tabloları (olumlu / olumsuz / soru), kullanım
  durumları, Türkçeden farkı, sık karıştırılanlar, **💼 İş hayatında** bölümü (`"work": true`).
- 15–25 örnek (`en` + doğal Türkçe `tr`), 5–8 sık hata, ~20–24 alıştırma (her türden).
- En az 2 doğrulanmış kaynak (açılıp başlığı kontrol edilmiş sayfa).
