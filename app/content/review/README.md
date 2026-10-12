# Ders özetleri (tekrar kartları)

Bitirilen bir dersin aralıklı tekrarında (📘 Dersler → "Bugün tekrar zamanı gelenler") ve ders sayfasındaki
"📌 Özet"te gösterilen kısa kart. Her seviye bir dosya: `A1.json` … `C1.json`; her dersin bir özeti olmalı.
Kod: `app/backend/reviews.py` (doğrulama `validate_content`, takvim, mini test).

Değiştirdikten sonra doğrula:

```bash
runtime\python\python.exe dev\tests\review_content_test.py            # hepsi
runtime\python\python.exe dev\tests\review_content_test.py B1        # tek seviye
```

## Biçim

```json
{
  "_comment": "…",
  "reviews": {
    "a1-there-is": {
      "rules_tr": [
        "Bir yerde bir şeyin bulunduğunu söylemek için [en:There is] + tekil ya da sayılamayan isim, [en:There are] + çoğul isim kullanılır.",
        "…"
      ],
      "remember_tr": "Türkçede [tr:var] sonda, İngilizcede [en:there is] başta.",
      "table": 0,
      "mistakes": [0, 1, 5]
    }
  }
}
```

| Alan | Kural |
|---|---|
| `rules_tr` | **3–5 madde**, her biri 40–260 karakter, Türkçe. Dersin en önemli kuralları; tekrar eden biri 1 dakikada okuyup hatırlamalı. |
| `remember_tr` | **Tek cümle**, 20–160 karakter: akılda kalıcı bir ipucu ("Aklında kalsın"). |
| `table` | Kartta gösterilecek yapı tablosunun **bölüm sırası** (`sections[i].table`, 0'dan başlar; en çok 9 satır) ya da tablo uygun değilse `null`. |
| `mistakes` | Dersin `mistakes[]` listesinden en tipik **2–3** hatanın sırası (0'dan başlar, tekrarsız). Kartta yanlış → doğru olarak gösterilir. |

Kartta ayrıca dersin başlığı, seviyesi ve tekrar sayısı görünür; örnek cümleler ve alıştırmalar dersten gelir
(mini test = dersin kendi alıştırmaları). Yani **yeni yazılan yalnız `rules_tr` ve `remember_tr`**.

## Doğruluk kuralları (en önemli kısım)

1. **Dersin söylemediği hiçbir şeyi söyleme.** Her madde dersin `intro_tr` / `sections` / `mistakes` içeriğinde
   açıkça bulunan bir kuralın kısaltmasıdır. Yeni kural, istisna, sayı ya da genelleme ekleme. Ders "genellikle"
   diyorsa sen de "genellikle" de; "her zaman"a çevirme.
2. **Kısaltırken yanlışlaştırma.** "İngilizcede X kullanılmaz" gibi mutlak cümleler ancak ders öyle diyorsa.
   Kısa olsun diye istisnayı silip kuralı yanlış hale getirme; gerekirse maddeyi daha dar yaz.
3. İngilizce örnekler **dersin kendi örneklerinden** (birebir) ya da dersin tablosundan alınsın; uydurma örnek
   yazma. Her İngilizce parça dilbilgisi olarak doğru olmalı.
4. `remember_tr` doğru olmalı (abartılı bir benzetme yanlış öğretir). Emin değilsen dersin "Türkçeden farkı"
   bölümündeki ana fikri tek cümleye indir.
5. Türkçe doğal ve sade olsun, "sen" diliyle (dersler gibi); "siz" kullanma.
6. Maddeler birbirini tekrar etmesin; en önemli kural ilk sırada. `💼 İş hayatında` bölümü kural değil kullanım
   örneğidir — madde yazmak gerekmez.

## Terim işaretleme

Ders anlatımlarındaki gibi (`app/content/lessons/README.md` → "Terim işaretleme"): İngilizce `[en:…]`, Türkçe
örnek `[tr:…]`, tuş `[key:…]`. **Tırnak (`"` “ ”) kullanma.** `[en:…]` içinde Türkçe harf olmaz. Dilbilgisi terimleri
(present simple, passive, V3, fiil, isim) işaretlenmez.
