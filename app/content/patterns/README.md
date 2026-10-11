# Kalıplar (🧩 Kalıplar sayfası)

Her seviye bir dosya: `A1.json` … `C1.json` — `{"level", "count", "sources": [...], "patterns": [...]}`.
Toplam 300 kalıp (her seviyede 60). Dosyalar elle yazılır ve bağımsız denetimden geçer; yapay zeka yalnız
"kendi cümlen" testinde cümleyi kontrol eder.

Değiştirdikten sonra doğrula (tek dosya ya da hepsi):

```bash
runtime\python\python.exe dev\tests\patterns_content_test.py [app\content\patterns\B1.json]
```

## Bir kalıbın alanları

| Alan | Açıklama |
|---|---|
| `id` | Kalıcı kimlik: `<seviye>-<kategori>-<sıra>`: `b1-biz-007`, `a1-day-012`, `c1-gra-003`, `b2-idi-010`. **Asla değiştirme.** |
| `p` | Kalıp. Değişen yer `___` (üç alt çizgi) ile gösterilir, en fazla 2 boşluk, boşluk **tam kelime** yerine gelir ("Would you mind ___?" doğru, "___ing" yanlış). Sabit kısımlar örnek cümlelerde **aynen** geçmeli. |
| `tr` | Kalıbın Türkçesi; boşluk "…" ile: "… yapabilir misiniz, lütfen?" |
| `cat` | `business` (iş), `daily` (günlük konuşma), `grammar` (dilbilgisi kalıbı), `idiom` (deyim + phrasal verb). |
| `topic` | Konu (aşağıdaki listeden; kategoriye göre). |
| `register` | `formal`, `neutral`, `informal`. |
| `note_tr` | 1–2 cümle Türkçe kullanım notu: ne zaman kullanılır, Türkçeden farkı, sık yapılan hata, yakın kalıpla farkı. İngilizce kelimeler `[en:…]` ile işaretlenir (uygulamada mavi kutucuk). En fazla 300 karakter. |
| `examples` | Tam **2** örnek: `{"en", "tr"}`. `en` tek cümle, en fazla 16 kelime, doğal ve **hatasız** İngilizce, kalıbın sabit kısımlarını aynen ve sırayla içerir, nokta/soru/ünlem ile biter. `tr` doğal Türkçe çeviri. |

İşaretleme (`[en:…]`) yalnız `note_tr` içinde. `p`, `tr`, `examples` içinde işaretleme **yok**.

## Konular (`topic`)

| Kategori | Konular |
|---|---|
| `business` | `meetings` toplantı · `email` e-posta · `phone` telefon · `requests` rica · `opinions` fikir belirtme · `agreeing` katılma/katılmama · `presentations` sunum · `negotiation` pazarlık · `scheduling` randevu/zaman planı · `problems` sorun bildirme/çözme · `smalltalk_work` iş yerinde sohbet · `clarifying` anlamadığını söyleme/netleştirme |
| `daily` | `greetings` selamlaşma/tanışma · `shopping` alışveriş · `directions` yol tarifi · `restaurant` restoran/kafe · `travel` seyahat · `appointments` randevu/zaman · `feelings` duygular · `invitations` davet · `apologies` özür/teşekkür · `help` yardım isteme/teklif etme · `phone_daily` telefon (günlük) · `health` sağlık |
| `grammar` | `conditionals` koşul · `wishes` dilek/pişmanlık · `preferences` tercih · `habits` alışkanlık · `comparison` karşılaştırma · `suggestions` öneri · `obligation` zorunluluk/izin · `reported` aktarma · `passive` edilgen · `questions` soru kalıpları · `time` zaman ifadeleri · `purpose` amaç/sebep/sonuç |
| `idiom` | `idioms` deyimler · `phrasal_verbs` phrasal verb'ler |

## Seviyelere göre dağılım (tam sayılar; içerik testi kontrol eder)

| Seviye | business | daily | grammar | idiom | toplam |
|---|---|---|---|---|---|
| A1 | 10 | 28 | 14 | 8 | 60 |
| A2 | 14 | 22 | 14 | 10 | 60 |
| B1 | 20 | 14 | 14 | 12 | 60 |
| B2 | 22 | 10 | 14 | 14 | 60 |
| C1 | 22 | 8 | 14 | 16 | 60 |

## İçerik kuralları

- Hedef kullanıcı: **çalışan bir Türk yetişkin**; iş İngilizcesi ağırlıklı, gerçekten kullanılan kalıplar.
  A1–A2'de kısa ve en temel kalıplar; B2–C1'de toplantı, e-posta, pazarlık, sunum, deyimler.
- Her kalıp **bir** kalıptır; aynı kalıbın küçük varyantları ayrı kalıp olmaz. Bir kalıp iki seviyede olmaz
  (test, `p` benzersizliğini bütün dosyalar arasında kontrol eder).
- Türkçe metinler doğal, kısa, "sen" diliyle. Dilbilgisi terimleri işaretlenmez; yalnız İngilizce
  kelime/ifadeler `[en:…]`.
- Örnekler kalıbı gerçek bir bağlamda gösterir (iş: rapor, toplantı, müşteri, teslim tarihi…).
- Kaynaklar (`sources`): kalıpların dayandığı **gerçek** sayfalar (British Council LearnEnglish "Business
  English"/"Speaking", Cambridge Dictionary, BBC Learning English…): `{"title", "site", "url"}`; en az 3,
  bağlantılar doğrulanmış olmalı (uydurma bağlantı koyma).

## Örnek

```json
{"id": "b1-biz-001", "p": "Could you ___, please?", "tr": "… yapabilir misiniz, lütfen?",
 "cat": "business", "topic": "requests", "register": "formal",
 "note_tr": "İş ortamında kibar rica. [en:Can you] daha samimi, [en:Could you] daha nazik; sonuna [en:please] eklemek yumuşatır.",
 "examples": [
   {"en": "Could you send me the report by Friday, please?", "tr": "Raporu cuma gününe kadar bana gönderebilir misiniz, lütfen?"},
   {"en": "Could you call the client back this afternoon, please?", "tr": "Müşteriyi bu öğleden sonra geri arayabilir misiniz, lütfen?"}
 ]}
```
