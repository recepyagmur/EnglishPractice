# Kelime listeleri (Kelime Çalış)

Her seviye bir dosya: `A1.json` … `C1.json` — `{"level", "count", "words": [{"w", "pos", "tr", "ipa"?}]}`.

- `w`: İngilizce kelime, `pos`: kelime türü (CEFR-J'deki gibi: noun, verb, adjective…),
  `tr`: Türkçe anlam(lar) — birden fazla türü olan kelimelerde "fiil: …; isim: …", `ipa`: okunuş (varsa).
- Örnek cümleler dosyada yok: öğrenci istediğinde yapay zeka üretir, düzeltme motorundan hatasız geçen ve
  kelimeyi içeren cümleler gösterilir ve veritabanında (`word_examples`) saklanır (`backend/words.py`).

## En sık 3000 kelime (`top3000.json`)

Kelime Çalış'ta seviyelerin yanındaki **⭐ En sık 3000** listesi: İngilizcede en sık kullanılan 3000 kelime,
sıklık sırasıyla (`rank` 1 = en sık). Biçim: `{"id": "TOP3000", "count", "sources", "words": [{"w", "rank"}, …]}`.

- **Kelimeler:** New General Service List 1.2'nin 2809 kelimesi kendi sıralarıyla (SFI Rank), ardından aynı
  derlemde NGSL dışında kalan en sık kelimeler (SFI'ye göre) 3000'e kadar. Alınmayanlar: NGSL ek listesi (sayılar,
  günler, aylar), kısaltma ve kelime parçaları, küfür, çok teknik terimler, NGSL'deki bir kelimenin yazım varyantı.
  Seviye listelerindeki yazımla aynı olsun diye: okay → OK, café → cafe; headquarter → headquarters,
  sophisticate → sophisticated.
- **Anlamlar:** seviye listelerinde olan kelime (2930 kelime) anlamını, türünü ve okunuşunu oradan alır
  (`backend/words.py`); defterde aynı kayıt olur. Seviye listelerinde olmayan 70 kelimenin `pos`, `tr`, `ipa`
  alanları bu dosyadadır: yapay zeka ajanı yazdı, ayrı bir ajan bağımsız olarak denetledi; elle düzenlenebilir.
- **Yeniden üretmek:** NGSL dosyalarını (`NGSL_12_stats.csv`, `SUP_lemmatized.csv`, `NGSLwithSFI-31K.xlsx`)
  bir klasöre indirip `runtime\python\python.exe dev\tools\build_freq_list.py <klasör>` (dosyadaki 70 anlam korunur).
- **Doğrulama:** `runtime\python\python.exe dev\tests\vocab_freq_test.py` (3000 kelime, tekrar yok, sıra, anlam,
  sayı/gün/ay yok, her kelime öğrenmeye eklenebilir, defterde aynı kelime iki kez olmaz).

## Kaynaklar ve lisanslar

- **Kelimeler ve seviyeleri (A1–B2):** The CEFR-J Wordlist Version 1.5. Compiled by Yukio Tono, Tokyo University
  of Foreign Studies (Tono Laboratory). Atıfla ücretsiz kullanılabilir (araştırma ve ticari).
  <https://github.com/openlanguageprofiles/olp-en-cefrj>
- **En sık 3000:** New General Service List 1.2 — Browne, C., Culligan, B., & Phillips, J.
  <https://www.newgeneralservicelist.com> — CC BY-SA 4.0 (sıra ve kelimeler; 2810–3000 arası aynı derlemin
  NGSLwithSFI-31K sıklık listesinden).
- **C1:** Octanove Vocabulary Profile C1/C2 1.0, Octanove Labs — CC BY-SA 4.0 (sadece C1 kısmı kullanıldı).
- **Türkçe anlam adayları:** İngilizce Vikisözlük (uygulamanın sözlüğü) ve Türkçe Vikisözlük
  (kaikki.org/trwiktionary) — CC BY-SA 4.0. Okunuşlar (IPA) da buradan.
- **İnceleme:** adaylar her kelime için elle kontrol edildi; yanlış/argo/nadir anlamlar, soyadı ve kısaltma
  kayıtları çıkarıldı, eksikler yazıldı. Kaynak listedeki yazım hataları düzeltildi (chauffer → chauffeur),
  uygunsuz bir kelime çıkarıldı.

## Yeniden üretmek

```bash
runtime\python\python.exe dev\tools\build_wordlists.py <indirilenler> <çalışma klasörü>
# … elle inceleme: <çalışma>/review/<parça>.output.json …
runtime\python\python.exe dev\tools\assemble_wordlists.py <çalışma klasörü>
```

Bu dosyalar elle incelendiği için doğrudan düzenlenebilir; yeniden üretmek incelemeyi tekrarlamayı gerektirir.
