# English Practice — Yerel İngilizce Pratik Uygulaması

Tamamen ücretsiz, çevrimdışı ve **taşınabilir** İngilizce konuşma/yazma pratiği uygulaması.
Her şey (Python, Ollama, modeller, veriler) bu klasörün içindedir; sisteme hiçbir şey kurulmaz.

Türkçe konuşan, özellikle çalışan yetişkinler için: yerel bir yapay zekâyla sesli ya da yazılı İngilizce sohbet ve anında
düzeltme; A1–C1 dersler ve seviye sınavları; Türkçe anlatan sesli bir öğretmen; senaryolar (rol yapma), yazma
değerlendirmesi; Kelime Çalış (seviye listeleri ve en sık 3000 kelime), kelime defteri ve aralıklı tekrar; iş ve
günlük hayat kalıpları; YDS tarzı süreli testler; ilerleme takibi; iki bilgisayar arasında eşitleme.
Windows 10/11 ve Linux'ta çalışır. Kurulumdan sonra internet gerekmez; verileriniz bilgisayarınızdan çıkmaz.

Kullanılan bütün yazılım, model ve içerik kaynakları lisanslarıyla birlikte:
[Kaynaklar, lisanslar ve teşekkürler](#kaynaklar-lisanslar-ve-teşekkürler).

## Kurulum

**`Kurulum.bat`'a çift tıklayın** — başka hiçbir şey kurmanız gerekmez (yönetici izni de istenmez).

1. Kısa bir hazırlık: Windows / klasör yolu / internet / disk kontrolü, gömülü Python (~11 MB).
2. Tarayıcıda **kurulum sihirbazı** açılır:
   - **Donanım taraması** (işlemci, RAM, ekran kartı ve VRAM, disk, hızlandırma türü),
   - **Dil modeli seçimi**: her model için bu bilgisayara uygunluk rozeti
     (✓ Önerilir / ✓ Uygun / ⚠ Yavaş olabilir / ✗ Sığmaz), gerçek indirme boyutu, kalite ve hız.
     Bilgisayarınızda başka bir Ollama'nın indirdiği modeller varsa **kopyalanır**, tekrar indirilmez.
   - **Ses**: Whisper modeli ve nerede çalışacağı, Kokoro aksanı ve sesi,
   - **Ek bileşenler**: çevrimdışı sözlük (önerilen), TranslateGemma (cümle çevirisi, isteğe bağlı),
     masaüstü kısayolu (izninizle — sisteme yazılan tek şey),
   - **Özet** (toplam indirme, disk, süre) → **Kur**: her bileşen için ilerleme çubuğu, hız ve kalan süre.
     İndirmeler yarıda kalırsa kaldığı yerden devam eder; sihirbaz kapanırsa yeniden açtığınızda
     **"Kaldığı yerden devam et"** çıkar. Bir bileşen kurulamazsa diğerleri devam eder.
   - **Test**: her dil modelinin hızı (token/sn, ilk kelime süresi), konuşma tanıma ve ses gerçek
     örnekle denenir; yavaşsa daha hızlı bir model önerilir ve varsayılan buradan değiştirilebilir.
3. **Klasörü başka bilgisayara taşıdığınızda** (ör. harici disk ile laptop) `Baslat.bat` bunu fark eder ve
   sihirbazı **"Yeni bilgisayar"** modunda açar: sadece model ve ses seçimi + hız testi; klasördeki
   modeller tekrar indirilmez. Her bilgisayar kendi varsayılan modelini hatırlar.
4. Kurulumdan sonra `Kurulum.bat` **bakım modunda** açılır: model ekle / sil / varsayılan yap, onar
   (eksik/bozuk dosyaları yeniden indirir), güncelle (Ollama + paketler), donanımı yeniden tara, hız testi.
   Her bakım işleminden önce verileriniz yedeklenir.

> Klasör yolu Türkçe karakter ve boşluk içermemeli (ör. `C:\IngilizcePratik`). Klasör
> OneDrive/Google Drive gibi senkronize bir yerdeyse uygulamayı **aynı anda iki bilgisayarda açmayın**
> (uygulama bunu fark edip uyarır).

### Linux'ta kurulum

Linux'ta da aynı uygulama çalışır; yine her şey bu klasöre iner, sisteme bir şey kurulmaz, `sudo` gerekmez.

- **Gerekenler:** 64 bit (x86_64) Linux, glibc 2.28 ve sonrası (Ubuntu 20.04+, Debian 10+, Fedora 29+ …),
  `curl` ya da `wget`, en az 15 GB boş alan. NVIDIA ekran kartında sürücü kurulu olmalı (`nvidia-smi`
  çalışıyorsa tamam); AMD kartlar için Ollama'nın ROCm paketi de iner. Uygulama penceresi için Chrome,
  Chromium, Edge ya da Brave varsa onunla açılır (sekmesiz pencere); yoksa varsayılan tarayıcıda.
- **Kurulum:** klasörü örneğin `~/EnglishPractice` gibi Türkçe karakter ve boşluk içermeyen bir yere koyup
  terminalde o klasörde: `bash kurulum.sh`. Taşınabilir Python (python-build-standalone, ~64 MB) iner ve
  aynı kurulum sihirbazı tarayıcıda açılır. "Ek bileşenler"de kısayol seçilirse uygulama menüsüne ve
  masaüstüne "English Practice" eklenir.
- **Açmak:** `bash baslat.sh` (ya da menüdeki kısayol: bir terminal açar). Kapatmak için o terminalde
  **Ctrl+C** ya da terminali kapatmak; ikisinde de verilerin gönderilir ve Ollama kapanır.
- **Güncellemek:** uygulama kapalıyken `bash guncelle.sh` (zip başka bir yere indiyse:
  `bash guncelle.sh ~/yol/EnglishPractice-main.zip`).
- **İki bilgisayar eşitlemesi:** Linux'un resmi Google Drive programı yok; Drive klasörünü rclone, Insync ya da
  google-drive-ocamlfuse gibi bir araçla bir klasöre bağlayıp Ayarlar → ☁️ İki bilgisayar'da o klasörü
  gösterin (`~/GoogleDrive`, `~/gdrive` gibi bilinen adlar kendiliğinden önerilir).
- Windows ile farkları: `.bat` yerine `.sh` betikleri; Python ve Ollama'nın Linux sürümleri; görev çubuğu
  kimliği (Windows'a özgü) yerine `.desktop` kısayolu. Dersler, içerik, veriler ve ayarlar aynıdır.

## Kullanım

**`Baslat.bat`'a çift tıklayın.** Uygulama içindeki Ollama'yı başlatır, modeli belleğe yükler ve
uygulamayı **kendi penceresinde** açar (Edge'in uygulama penceresi — sekme ve adres çubuğu yok; Edge yoksa
Chrome, ikisi de yoksa varsayılan tarayıcı). Pencereyi kapatınca uygulama arkada çalışmaya devam eder;
`Baslat.bat`'a tekrar tıklamak pencereyi yeniden açar. Tamamen kapatmak için konsol penceresinde `Ctrl+C`
veya konsol penceresini kapatın — Ollama da otomatik kapanır.

> Mikrofon izni için adres `http://localhost:…` olmalı (IP adresiyle değil).

### Konuşma

- 🎤 butonuna **basılı tutup** konuşun, bırakınca gönderilir. Ayarlar'dan "Tıkla-başlat / tıkla-bitir"
  moduna geçebilirsiniz.
- Klavye: metin kutusu dışındayken **Boşluk** tuşu aynı işi görür.
- İlk kullanımda tarayıcı mikrofon izni ister. Mikrofon 2 dakika kullanılmazsa kapatılır.
- Konuşma tanıma (Whisper) dili İngilizce'ye sabittir; hatalarınız düzeltilmeden yazıya dökülür,
  düzeltmeler sağdaki panelde gösterilir (aşağıya bakın).
- Ayarlar'dan farklı bir Whisper modeli seçilirse ilk seferde internetten indirilir (`models/stt/`).
- **Telaffuz göstergesi:** Whisper'ın net anlayamadığı kelimeler (güven < %60) mesajınızda **sarı**
  işaretlenir. Tıklayınca doğru telaffuz çalınır ve kelime penceresi açılır. Bu kaba bir göstergedir,
  tam telaffuz analizi değil: hızlı söylenen kısa kelimeler ve isimler de işaretlenebilir.
  Geçmiş oturumlarda da görünür.
- Yapay zeka **sesli cevap verir**; cevap cümle cümle seslendirildiği için ilk cümle ~1 saniyede başlar.
  - **⏹ Durdur**: sesi keser. Konuşmaya başlamak (🎤 / Boşluk) da sesi otomatik keser.
  - **🔊** (her cevabın yanında): tekrar dinle.
  - **🌐** (her mesajın yanında — seninkiler de): cümlenin tamamının Türkçesini mesajın içinde gösterir;
    tekrar basınca gizler. Yapay zeka çevirisidir, küçük hatalar olabilir. Derslerdeki sorularda da var.
  - **🔊 Sesli cevap** düğmesi: sadece yazılı cevap istiyorsanız kapatın.
  - **🙈 Altyazı gizli**: cevap metni bulanıklaşır, önce dinleyerek anlamaya çalışın; görmek için cevaba tıklayın.
- Ses, aksan (Amerikan/İngiliz) ve konuşma hızı (0.7x–1.2x) Ayarlar'dan seçilir; "▶ Dinle" ile deneyin.

### Düzeltmeler

- Her cümlenizden sonra, cevap verildikten birkaç saniye sonra sağ panelde düzeltme kartı belirir:
  değişen kelimeler renkli (kırmızı: yanlış, yeşil: doğru), hata türü etiketi, kısa açıklama ve
  varsa **💡 daha doğal** bir söyleyiş. Hata yoksa **Perfect! ✓**.
- Mesajınızın köşesindeki **⚠ 2** / **✓** rozetine tıklayınca ilgili kart vurgulanır
  (dar ekranda panel yandan açılır).
- Düzeltmeler sohbeti yavaşlatmaz: sohbet cevabı her zaman önce üretilir.
- Açıklama dili (Türkçe/İngilizce) ve düzeltme modu (her mesajda / oturum sonunda / kapalı) Ayarlar'dan.
- Hata türleri sabit bir listeden seçilir (`app/backend/errors.py`): Zaman, Fiil yapısı,
  Özne-yüklem uyumu, Tanımlık, Edat, Zamir, Çoğul, Kelime sırası, Kelime seçimi, Eksik kelime,
  Fazla kelime, Yazım, Noktalama, Diğer. İstatistikler ve ileride dersler bu listeye dayanır.

### Dersler

- **📘 Dersler**: seviyelere göre (A1–C1) konu anlatımı. Hazır: **A1 (10 ders), A2 (10), B1 (12), B2 (10), C1 (8)**. Her seviyede **💼 iş İngilizcesi** dersleri var (işini tanıtmak, iletişim bilgisi,
  iş e-postası, telefon, toplantı, iş görüşmesi) ve her derste **💼 İş hayatında** bölümü.
- Her dersin sonunda **📚 Kaynaklar**: anlatımın dayandığı güvenilir ücretsiz sayfalar (British Council
  LearnEnglish, Cambridge Dictionary Grammar) — hepsi tek tek açılıp doğrulandı.
- Her derste: ayrıntılı Türkçe anlatım (4–6 bölüm: yapı tabloları, ne zaman kullanılır, sinyal kelimeler,
  Türkçeden farkı ve sık karıştırılanlar, 💼 iş hayatında), 15–25 🔊 dinlenebilen örnek, **Türklerin sık yaptığı
  hatalar**, anında kontrol edilen ~23 **alıştırma** (%80 doğruyla ders tamamlanır): seçmeli, boşluk doldurma,
  düzelt, **dönüştür** (ör. olumsuz yap), **kelimeleri sırala**, **eşleştir**, **dinle-yaz**; **✍️ Kendi cümlelerini kur**
  (yapay zeka soru sorar, cevabın düzeltme motoruyla kontrol edilir) ve **🗣 Konuşarak pratik**
  (konuya odaklı sohbet + rapor).
- **📝 Yazılı göster:** dinleme alıştırmalarında (ders "Dinle ve yaz", Kelime Çalış "Dinle ve kelimeyi yaz")
  🔊'nin yanındaki 📝 duyulan metni gösterir, ikinci tıklama gizler. Sınavlarda yoktur.
- **Çalışman kaybolmaz:** ders sayfasındaki cevapların, yazıp henüz göndermediğin metinler ve
  **Kendi cümlelerini kur**'daki sorular, cevaplar ve sonuçlar sen silene kadar saklanır (🗑 tek tek ya da
  **🗑 Tümünü sil**; alıştırmalar için **↻ Tekrar çöz**). Başka sayfaya gidip dönünce ya da uygulamayı yeniden
  açınca her sayfa kaldığın yerden (kaydırma konumu dahil) açılır.
- **🎯 Sana önerilen**: sık yaptığın hata türlerine göre ilgili dersler ve seviyendeki sıradaki ders.
  İlerleme sayfasındaki "Zayıf noktalarım" kartlarında da **📘 Konuyu öğren** bağlantısı var.
- Anlatımlar elle yazılmıştır (`app/content/lessons/`, format: oradaki README); yerel modelin Türkçesi
  anlatım için güvenilir olmadığından yapay zeka sadece İngilizce soru ve sohbet üretir
  (sorular için 🧑‍🏫 Öğretmen var).

### Öğretmen (Türkçe)

- **🧑‍🏫 Öğretmen** sayfası: İngilizceyle ilgili her şeyi **Türkçe yazarak** sorabilirsin (dilbilgisi,
  "bu cümle doğru mu?", iş e-postası kalıpları…). Öğretmen seviyeni ve son 30 gündeki en sık
  hatalarını bilir; kısa cevap verir, iş hayatından örnekler kullanır.
- Cevaptaki **İngilizce örnekler** ayrı satırda, Türkçe çevirisiyle; **🔊** ile dinlenir, kelimelerine
  tıklanır (sözlük / deftere ekle).
- Sorduğun bir İngilizce cümle (tırnak içinde) ya da İngilizce yazdığın mesaj önce **dilbilgisi
  denetleyicisinden** geçer, öğretmen bu sonuca göre cevap verir — yanlış cümleye "doğru" demez.
  İngilizce yazdığın mesajlar sohbetteki gibi **kırmızı/yeşil** işaretlenir ve istatistiklere girer.
- Başka sayfalardan açmak:
  - **Ders sayfası → 🧑‍🏫 Öğretmene sor**: öğretmen o dersin konusunu bilerek açılır (hazır sorular da var).
  - **Düzeltme kartı → ❓ Neden?**: o hatayı kendi cümlen üzerinden açıklar.
  - **İlerleme → Zayıf noktalarım → 🧑‍🏫 Öğretmenle çalış**: o konuda tek tek alıştırma sorar
    (Türkçeden çevir / yanlış cümleyi düzelt), cevabını kontrol eder, sonrakine geçer.
- Konuşmalar **📚 Geçmiş konuşmalar** listesinde saklanır, 🗑 ile silinir. Pratik istatistiklerine
  (mesaj/kelime sayısı) Türkçe sorular katılmaz; çalışma süresi ve günlük seri sayılır.
- **🔊 Sesli cevap**: öğretmen cevaplarını iki sesle okur — Türkçe kısımları **Türkçe öğretmen sesi**,
  İngilizce örnekleri ve kelimeleri **İngilizce ses** (sohbetteki, Ayarlar'daki aksan/ses). Türkçe ses
  İngilizceyi asla okumaz (yabancı kelimeyi Türkçe okur, yanlış telaffuz öğretirdi). Üst bardaki
  **🔊 Sesli cevap** düğmesi yeni cevapların kendiliğinden okunmasını açar/kapatır; her cevabın köşesindeki 🔊
  o cevabı okur, tekrar basınca durur. Sayılar, tarihler, saatler okunuşuyla söylenir (14:30 → on dört otuz).
  Türkçe ses: EMA Lightning (Apache 2.0), ONNX'e çevrilmiş halde `app/tts_tr` (~35 MB, PyTorch gerekmez,
  işlemcide ~20× gerçek zamandan hızlı). İki dilde de olan kelimeler (son, her, do…) çevresindeki kelimelerin
  diline göre okunur; çok nadiren yanlış seste okunabilir.
- Sesle soru sorma yok (konuşma tanıma şimdilik sadece İngilizce); yapay zeka nadiren hata yapabilir.
- Model: **Gemma 4 E4B** Türkçede belirgin şekilde daha iyi ve 2 kat hızlı olduğu için bu bilgisayarda
  varsayılan yapıldı (karşılaştırma: [docs/model-karsilastirma-turkce.md](docs/model-karsilastirma-turkce.md)).

### Seviye sınavı

- Her seviyenin dersleri bitince Dersler sayfasında **🎓 Seviye Sınavı** açılır (hazır hissediyorsan
  "Yine de gir" ile önce de girebilirsin). **A1–C1 tüm seviyelerin** sınavları hazır.
- 4 bölüm: **Dilbilgisi** (%40, her dersten soru: seçme, boşluk doldurma, düzeltme, dönüştürme,
  kelime sıralama), **Dinleme** (%20: dikte + kısa metinler, her ses en fazla 3 kez), **Konuşma** (%20:
  soruları mikrofona cevaplarsın; mikrofon yoksa yazarak), **Yazma** (%20: kısa mesaj). Bölümler arasında
  geri dönülebilir; değerlendirme sınav bitince yapılır (~20 sn).
- Her bölüm geniş bir soru havuzundan seçilir: sınava tekrar girdiğinde başka sorular gelir. Sınav
  sırasında **🔀 Soruları değiştir** tüm soruları yeniler (o ana kadarki cevaplar silinir); **🗑 Sınavı bırak**
  sınavı iptal eder. Yarım kalan sınav saklanır: sayfadan çıkıp dönünce ya da uygulamayı yeniden açınca
  kaldığın bölümden, cevaplarınla devam eder.
- Geçmek için toplam %70 ve her bölümde %50. Sonuçta: bölüm puanları, her yanlışın doğrusu ve
  açıklaması, konuşma/yazma düzeltmeleri, **tekrar etmen önerilen dersler** ve geçtiysen
  **⬆ Seviyemi yükselt** düğmesi. Sonuçlar saklanır, istenirse silinir.

### Girdi kontrolleri

- **Düzeltmeler paneli** sadece hatalı cümleleri listeler (hatasızlar mesajda ✓). **⟩** ile yana
  kapanır; sağ kenardaki **⟨ Düzeltmeler** sekmesiyle (hata sayısıyla) tekrar açılır, tercih hatırlanır.
- **Konuşma / senaryo:** yazdığın ya da söylediğin cümledeki yanlış kısımlar **mesajının içinde kırmızı**
  işaretlenir, hemen altında doğrusu yazar (değişen kelimeler yeşil). Kırmızı kısma tıklayınca sağdaki
  panelde açıklaması açılır. Türkçe ya da anlamsız bir mesaj "Perfect" sayılmaz: **"İngilizce değil"**
  uyarısı çıkar (çevrimdışı sözlükle kontrol edilir).
- **he/she uyumu:** önceki cümlede (ya da yapay zekanın sorusunda) bir kadından bahsedilip sen "he"
  dersen (ya da tersi) hata olarak yakalanır — bu kontrol yapay zekaya bırakılmadan kuralla yapılır.
- **Dersler → Kendi cümlelerini kur:** cevap üç açıdan kontrol edilir: soruya uygun mu, dersin konusunu
  kullanıyor mu, dilbilgisi doğru mu. İlgisiz ya da anlamsız cevap "yanlış" sayılır.
- **Yazma modu:** İngilizce olmayan metin değerlendirmeye gönderilmez. **Kelime defteri:** sözlükte
  olmayan (muhtemelen yanlış yazılmış) bir kelime eklenmeden önce sorulur.

### Silme

- **Sohbet:** açık sohbeti üst bardaki **🗑 Sil** ile; geçmiş oturumları İlerleme → Oturum geçmişi
  listesindeki 🗑 ya da oturum sayfasındaki **🗑 Oturumu sil** ile (mesajlar, düzeltmeler, rapor ve
  istatistiklerdeki hataları birlikte silinir).
- **Yazılar:** Yazma → Geçmiş yazılarım listesindeki 🗑. **Kelimeler:** Kelime Defteri'ndeki 🗑.
- **Öğretmen konuşmaları:** Öğretmen → 📚 Geçmiş konuşmalar listesindeki 🗑 ya da üstteki **🗑 Sil**.
- **Ders ilerlemesi:** ders sayfasındaki **↺ İlerlemeyi sıfırla**. **Dil modelleri:** Ayarlar → Dil modelleri → Sil.
- Rapor alınmış (bitirilmiş) sohbet de silinebilir: rapor kartındaki **🗑 Bu oturumu sil** ya da üstteki Sil.
- **Hepsini sıfırlama:** Ayarlar → **🔄 Sıfırla**. İşaretlediğin gruplar silinir: *Dersler, sınavlar ve testler*,
  *Kelimeler ve kalıplar* (Kelime Çalış + Kelime Defteri + Kalıplar), *Konuşma geçmişi ve istatistikler* (sohbet, senaryo, öğretmen,
  yazma, hatalar, seri), *Seviye* (ilk açılıştaki soru yeniden gelir). Diğer ayarlar ve modeller kalır; önce
  `data/backups/pre-reset-….db` yedeği alınır.
- Her silme önce onay ister. Yanlışlıkla silinirse `data/backups/` içindeki günlük yedekten dönülebilir.

### Senaryolar (rol yapma)

- **🎭 Senaryolar** sayfasından bir durum seçin: iş görüşmesi, restoran, havalimanı, otel, doktor,
  yeni biriyle tanışma, teknik toplantı, ürün iadesi. Yapay zeka rolünü üstlenir ve **konuşmayı
  kendisi başlatır**.
- Üstteki kutuda o senaryonun **3 görevi** var; yaptıkça işaretleyin.
- **Kendi senaryon**: durumu Türkçe ya da İngilizce yazın (ör. "Patronumdan zam istiyorum");
  roller ve görevler otomatik hazırlanır.
- **🏁 Oturumu bitir** (serbest konuşmada da var): rapor — iyi gidenler, en sık hata türlerin
  (gerçek örneklerinle ve ipucuyla), öğrenilecek 5 ifade (🔊 ile dinlenebilir). Düzeltme modu
  "oturum sonunda" ise tüm düzeltmeler de burada listelenir. Raporlar İlerleme → geçmişte saklanır.

### Yazma

- **✍️ Yazma** sayfasında görev türünü seçin: serbest, e-posta, essay, hikaye, günlük, IELTS/TOEFL.
  Kelime hedefi seviyenize göre ayarlanır; IELTS'te 40 dakikalık geri sayım vardır.
- **🎲 Konu öner**: seviyenize ve ilgi alanlarınıza göre bir konu (Türkçe çevirisiyle).
- Yazdığınız taslak tarayıcıda otomatik saklanır.
- **Değerlendir**: metin cümle cümle kontrol edilir (sonuçlar geldikçe görünür, ~20–30 sn):
  - hatalar metnin üzerinde dalgalı çizgiyle; üzerine gelince/tıklayınca düzeltme ve açıklama,
  - 4 alanda puan (dilbilgisi, kelime çeşitliliği, akıcılık, göreve uygunluk) ve tahmini CEFR seviyesi,
  - **✨ daha doğal versiyon**, orijinalle yan yana (🔊 ile dinlenebilir),
  - kullanabileceğiniz daha ileri ifadeler.
- Gün, ay, ülke, dil adlarının ve "I"nın küçük yazılması kodla kesin olarak yakalanır.
- Yazı hataları da konuşma hatalarıyla aynı kategorilerle kaydedilir (istatistiklerde birlikte görünür).

### Kelime Çalış (seviye listeleri)

- **🧠 Kelime Çalış** sayfası: A1–C1 seviyelerinde en çok kullanılan **7.768 kelime** (CEFR-J Wordlist ve
  Octanove C1 listesi). Her kelimenin Türkçe anlamı (elle kontrol edildi), kelime türü, okunuşu ve 🔊 sesi var.
  Seviye seç, ara, duruma göre süz (yeni / öğreniliyor / öğrenildi); kelimeye tıklayınca kartı açılır.
- **🤖 Örnek cümle üret**: yapay zeka seviyene uygun örnek cümleler yazar. Bir cümle ancak **düzeltme
  motorundan hatasız geçerse**, kelimeyi gerçekten içeriyorsa ve **Türkçe çevirisi ayrı bir kontrolden
  geçerse** gösterilir; doğrulananlar saklanır, bir sonraki seferde beklemeden gelir.
- **🆕 10 yeni kelime öğren**: kartlar (kelime → anlam + örnekler), sonra karışık test:
  anlam seçme (İngilizce→Türkçe ve tersi), **dinle-yaz**, **boşluk doldurma** (örnek cümleyle),
  **kendi cümlen** (yapay zeka dilbilgisini ve kelimenin doğru anlamda kullanılıp kullanılmadığını kontrol eder).
  Yanlış cevaplanan kelime turun sonunda bir kez daha sorulur.
- **🔁 Tekrar et**: zamanı gelen kelimeler aynı soru türleriyle. Öğrenilen kelimeler Kelime Defteri'ne girer;
  ikisi aynı aralıklı tekrar takvimini kullanır.
- **⭐ En sık 3000**: seviyelerin yanında, İngilizcede en sık kullanılan 3000 kelime sıklık sırasıyla
  (New General Service List 1.2 + aynı derlemin sonraki en sık kelimeleri; sayılar, günler, aylar yok). Her
  satırda sıra numarası ve kelimenin seviyesi (A1…) görünür. "🆕 10 yeni kelime öğren" burada en sıktan başlar.
- **➕ Aktif kelimelerime ekle**: her satırdaki ➕ ya da kartındaki düğme kelimeyi öğrenme listene (Kelime Defteri,
  aralıklı tekrar) ekler. **Aynı kelime iki kez eklenmez**: hangi listeden, nasıl yazılmış olursa olsun
  (büyük/küçük harf, café/cafe, ’/') defterde tek kayıttır; seviye listesinde de 3000'de de aynı durum görünür.
- Kaynaklar ve lisanslar: `app/content/vocab/README.md`.

### Kalıplar

- **🧩 Kalıplar** sayfası: A1–C1 seviyelerinde **300 kalıp** (her seviyede 60) dört kategoride: **İş**
  (toplantı, e-posta, telefon, rica, fikir belirtme, pazarlık, sunum…), **Günlük** (selamlaşma, alışveriş,
  yol tarifi, davet, özür…), **Dilbilgisi** (koşul, dilek, tercih, aktarma, edilgen…), **Deyim & phrasal**.
  Her kalıpta Türkçesi, ton (resmi / nötr / samimi), kısa kullanım notu ve iki örnek cümle (🔊) var.
  Seviye ve kategori seçilir; arama ve duruma göre süzme (yeni / öğreniliyor / öğrenildi).
- Satıra tıklayınca kart açılır: **➕ Öğrenmeye başla** (ya da öğrenme listesinden çıkarma).
- **🆕 5 yeni kalıp öğren**: seçili seviye ve kategoriden kartlar (kalıp → anlam, not, örnekler), sonra
  karışık test: anlam seçme (iki yönde), **dinle-yaz** (örnek cümle), **boşluk doldurma** (örnek cümlede
  kalıp silinir), **cümleyi sırala** (örnek cümlenin kelimeleri), **kendi cümlen** (yapay zeka dilbilgisini
  ve kalıbın doğal kullanılıp kullanılmadığını kontrol eder). Yanlışlar turun sonunda bir kez daha sorulur.
- **🔁 Tekrar et**: zamanı gelen kalıplar aynı soru türleriyle (aralıklı tekrar, SM-2). Kalıpların tekrar
  takvimi Kelime Defteri'nden ayrıdır; Ayarlar → Sıfırla → *Kelimeler ve kalıplar* ile silinir.
- İçerik elle yazıldı ve bağımsız denetimden geçti; biçim ve kaynaklar: `app/content/patterns/README.md`.

### Kendini Test Et (YDS tarzı sorular)

- **🎯 Kendini Test Et** sayfası; şimdilik tek kategori: **📝 YDS tarzı sınav**. ÖSYM'nin YDS / e-YDS / YÖKDİL
  formatında **320 özgün soru** (gerçek ÖSYM soruları değil), 10 soru türü: kelime, dilbilgisi, cloze test,
  cümle tamamlama, çeviri (iki yön), paragraf (okuma), diyalog tamamlama, anlamca en yakın cümle, paragraf
  tamamlama, anlam bütünlüğünü bozan cümle. Her sorunun tek doğru cevabı ve Türkçe açıklaması var.
- **Soru türüne göre set**: türü, soru sayısını (5/10/20; okuma 4'er, cloze 5'er) ve süreyi seç → Başla.
  **Mini deneme**: 40 soru, YDS oranında ve sırasında (90 dk). Süre seçenekleri: YDS standardı (soru başına
  2,25 dk = 180 dk / 80 soru), rahat (1,5×), süresiz. Süre bitince test kendiliğinden teslim edilir.
- Çözerken yardım yok (kelime kutucuğu, yazılı gösterme vb. kapalı). Cevapların anında sunucuya kaydedilir;
  sayfadan çıksan ya da uygulama kapansa bile yarım test "▶ Devam et" ile kaldığı yerden, kalan süreyle sürer.
  Klavye: 1–5 seçenek, ← → soru.
- **Sonuç**: doğru / toplam, yüzde (mini denemede YDS puan karşılığı), kullanılan süre, soru türüne göre tablo,
  her sorunun incelemesi (senin cevabın kırmızı, doğrusu yeşil, açıklama). Çözmediğin sorular ve en son yanlış
  yaptıkların sonraki setlerde önce gelir. Geçmiş sonuçlar listelenir; her biri silinebilir.
- İçerik ajanlarla yazıldı ve bağımsız denetimden geçti; biçim ve kaynaklar: `app/content/yds/README.md`.

### Kelimeler ve kelime defteri

- Yapay zekanın cevaplarında, raporlarda ve yazma geri bildiriminde **herhangi bir kelimeye tıklayın**:
  sözlük hali ("went" → go, geçmiş zaman), okunuşu (IPA), 🔊 telaffuzu, Türkçe karşılıkları ve
  İngilizce tanımı görünür.
  - **🤖 Bu cümledeki anlamı?**: yapay zeka kelimenin o cümledeki anlamını söyler (sözlükte
    olmayan kelimelerde otomatik).
  - **➕ Deftere ekle**: kelime, tıkladığınız cümleyle birlikte deftere kaydedilir. Rapor ve
    yazma önerilerindeki ifadelerin yanında da ➕ vardır.
- **📒 Kelime Defteri**: arama, elle ekleme (anlam otomatik doldurulur), anlamı düzenleme, silme.
- **Tekrar (flashcard)**: aralıklı tekrar (SM-2). Düğmenin yanındaki kutudan bu turda kaç kelime
  tekrar edeceğinizi seçersiniz (5, 10, 15… ya da "Hepsi (N kelime)"; en geç kalanlar önce gelir; seçim
  hatırlanır). Kartı çevirmek için **Boşluk**, sonra **1** Bilemedim · **2** Zorlandım · **3** Bildim.
  "Bilemedim" denen kart aynı turda tekrar gelir. Bugün tekrar edilecek kart sayısı menüde rozet olarak görünür.
- **🧪 Test et**: defterdeki kelimelerle Kelime Çalış'taki testin aynısı. Kaç kelime sorulacağını yanındaki
  kutudan seçersiniz ("Hepsi (N kelime)" defterdeki tüm kelimeleri gösterir; varsayılan 15; önce tekrar
  zamanı gelenler): anlamını seç (iki yönde), dinle-yaz, boşluk doldurma (kontrollü örnek cümlesi olan
  kelimelerde), kendi cümlen (yapay zeka kontrol eder). Yanlışlar turun sonunda bir kez daha sorulur;
  cevaplar kelimenin tekrar takvimini günceller.
- Çevrimdışı sözlük: `data/dictionary.db` (~13 MB, ~26.000 kelime + ~53.000 çekim). Yeniden
  oluşturmak için (~520 MB indirir, işler, ham dosyayı siler):

```bash
runtime\python\python.exe -m setup.build_dictionary
```

  Kaynak: [Wiktionary](https://en.wiktionary.org) verisi, [kaikki.org](https://kaikki.org) aracılığıyla,
  [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) lisansıyla.

### İlerleme

- **📈 İlerleme** sayfası: 🔥 günlük seri, pratik süresi, konuştuğun süre, yazılan kelime,
  öğrenilen kelime; son 30 günün aktivite takvimi.
- **Hata türleri** grafiği (7 / 30 gün): konuşma ve yazma hataları kategori kategori; üzerine
  gelince sayılar, "Tablo olarak göster" ile aynı veriler tablo halinde.
- **🎯 Zayıf noktalarım**: en sık hata türlerin, gerçek örneklerin ve bu haftaki gidişat
  (↓ iyileşiyor / ↑). **Bu konuda pratik yap** o konuyu kullandıran bir sohbet başlatır
  (yazım/noktalama için yazma moduna götürür).
- Oturum geçmişi (süre ve mesaj sayısıyla); tıklayınca tüm döküm, düzeltmeler ve rapor.

### Dil modelleri

- **⚙️ Ayarlar → 🧠 Dil modelleri**: bu bilgisayarda kurulu modeller (boyut, son ölçülen hız),
  **Varsayılan yap**, **⏱ Test** (hız testi), **Sil** (varsayılan model silinemez).
- **➕ Yeni model indir**: sihirbazdaki model kartları, aynı uygunluk rozetleriyle (✓ Önerilir /
  ✓ Uygun / ⚠ Yavaş olabilir / ✗ Sığmaz). İndirme ilerlemesi, hız ve kalan süre görünür; **İptal**
  edilen indirme tekrar başlatılınca kaldığı yerden devam eder. Model bilgisayarda başka bir Ollama'da
  varsa indirmek yerine kopyalanabilir. İndirme sürerken uygulama kullanılabilir.
- **⏱ Hız testi yap**: kurulu modelleri sırayla ölçer (token/sn, ilk kelime süresi); sonuç bu
  bilgisayarın profiline kaydedilir. Test sürerken sohbet bekler.
- **Sohbet ekranının üstündeki model seçici** (en az iki model kuruluysa görünür): sadece o oturum için
  modeli değiştirir, varsayılanı değiştirmez; **＋ Yeni sohbet** varsayılana döner.
- Model değişince eski model bellekten boşaltılır, yenisi yüklenir (8 GB ekran kartına iki model
  sığmaz); bu sırada "⏳ Model hazırlanıyor…" görünür ve gönderilen mesaj model hazır olunca cevaplanır.
- Hangi modelin cevap verdiği her mesajla kaydedilir.

## Kaynaklar, lisanslar ve teşekkürler

Bu uygulama, emeklerini açık lisanslarla paylaşan birçok kişi ve kurumun çalışması üzerine kurulu. Aşağıda
kullandığımız **her şey** var: ne için kullandığımız, kimin olduğu, lisansı ve bağlantısı. Lisanslar paketlerin
kendi bilgilerinden ve model kartlarından kontrol edildi (2026-10). Bir eksik ya da yanlış görürseniz lütfen bildirin.

**Depoda olan ve olmayan:** Bu depoda uygulamanın kendi kodu, ders/sınav/kalıp/YDS içerikleri, kelime listeleri
ve Türkçe ses modeli (`app/tts_tr`) var. Python, Ollama, Python paketleri, dil modelleri, Whisper, Kokoro ve sözlük
depoda **yok**; kurulum sırasında her birinin resmî kaynağından bu klasöre indirilir ve kendi lisansıyla gelir.

### Yazılım (kurulumda indirilir)

| Bileşen | Ne için | Kimin | Lisans |
|---|---|---|---|
| [Python 3.12](https://www.python.org) — Windows'ta [embeddable paket](https://www.python.org/downloads/windows/), Linux'ta [python-build-standalone](https://github.com/astral-sh/python-build-standalone) | Uygulamanın çalıştığı dil | Python Software Foundation; derleme betikleri Astral | PSF License 2.0; python-build-standalone betikleri MPL-2.0 |
| [Ollama](https://github.com/ollama/ollama) (içinde [llama.cpp](https://github.com/ggml-org/llama.cpp) / ggml) | Dil modellerini yerelde çalıştırır | Ollama; Georgi Gerganov ve katkıcılar | MIT |
| [FastAPI](https://fastapi.tiangolo.com), [Starlette](https://www.starlette.io), [Uvicorn](https://www.uvicorn.org), [Pydantic](https://docs.pydantic.dev), [HTTPX](https://www.python-httpx.org), websockets, httptools | Uygulamanın web sunucusu ve API'si | Sebastián Ramírez; Encode; Pydantic; Aymeric Augustin; MagicStack | MIT / BSD-3-Clause |
| [faster-whisper](https://github.com/SYSTRAN/faster-whisper) 1.2.1 | Konuşmayı yazıya çevirme | SYSTRAN | MIT |
| [CTranslate2](https://github.com/OpenNMT/CTranslate2) 4.8.2 | Whisper'ı hızlı çalıştıran motor | OpenNMT | MIT |
| [PyAV](https://github.com/PyAV-Org/PyAV) 15.1.0 | Mikrofon sesini çözme | PyAV ekibi | BSD-3-Clause (içindeki FFmpeg kitaplıkları [FFmpeg](https://ffmpeg.org/legal.html)'in kendi lisansıyla) |
| [kokoro-onnx](https://github.com/thewh1teagle/kokoro-onnx) 0.6.1 | İngilizce sesli okuma | thewh1teagle | MIT |
| [ONNX Runtime](https://onnxruntime.ai) 1.30 | Kokoro ve Türkçe ses modellerini çalıştırır | Microsoft | MIT |
| [espeakng-loader](https://github.com/thewh1teagle/espeakng-loader) 0.2.4 (içinde [eSpeak NG](https://github.com/espeak-ng/espeak-ng)) | İngilizce kelimelerin okunuşunu çıkarma | thewh1teagle; eSpeak NG katkıcıları | MIT; eSpeak NG **GPL-3.0-or-later** |
| [phonemizer](https://github.com/bootphon/phonemizer) 3.4.0 | Okunuş çıkarmayı eSpeak NG'ye bağlar | Bootphon (Mathieu Bernard ve ark.) | **GPL-3.0** |
| [normalizer-tr](https://github.com/erdemtuna/normalizer-tr) 0.4.0 | Türkçe sayı, tarih, saat gibi ifadeleri okunuşa çevirir | Erdem Tuna | Apache-2.0 |
| [NumPy](https://numpy.org), [huggingface_hub](https://github.com/huggingface/huggingface_hub), tokenizers, PyYAML, tqdm, protobuf, flatbuffers ve diğer bağımlılıklar | Yardımcı kitaplıklar | Kendi geliştiricileri | BSD / MIT / Apache-2.0 / MPL-2.0 (her paketin kendi lisansı) |
| [zstandard](https://github.com/indygreg/python-zstandard) 0.23.0 (yalnız Linux) | Ollama'nın Linux arşivini açar | Gregory Szorc | BSD-3-Clause |
| [msvc-runtime](https://pypi.org/project/msvc-runtime/) (yalnız Windows) | Microsoft Visual C++ çalışma zamanı dosyaları | Microsoft; paketleyen Christoph Gohlke | Microsoft Visual C++ Redistributable lisansı |
| NVIDIA [cuBLAS](https://pypi.org/project/nvidia-cublas-cu12/), [cuDNN](https://pypi.org/project/nvidia-cudnn-cu12/) (yalnız NVIDIA ekran kartında) | Whisper'ı ekran kartında çalıştırma | NVIDIA | NVIDIA'nın dağıtılabilir yazılım lisansı (özel) |

Uygulama penceresi için bilgisayardaki Microsoft Edge / Google Chrome / Chromium kullanılır (uygulamayla gelmez).
GPL lisanslı phonemizer ve eSpeak NG depoda yoktur; kurulumda PyPI'dan, kendi lisans metinleriyle iner.

### Yapay zekâ ve ses modelleri (kurulumda indirilir)

| Model | Ne için | Kimin | Lisans |
|---|---|---|---|
| [Gemma 4](https://huggingface.co/google/gemma-4-E4B-it) (E4B varsayılan; E2B, [26B](https://huggingface.co/google/gemma-4-26b-a4b-it) isteğe bağlı) | Sohbet, düzeltme, öğretmen | Google DeepMind | Apache-2.0 |
| [Qwen3](https://huggingface.co/Qwen/Qwen3-8B) 4B / 8B, [Qwen3.5](https://huggingface.co/Qwen/Qwen3.5-9B) 4B / 9B (isteğe bağlı) | Seçilebilir dil modelleri | Alibaba Qwen ekibi | Apache-2.0 |
| [TranslateGemma 4B](https://huggingface.co/google/translategemma-4b-it) (isteğe bağlı) | Cümle çevirisi | Google | [Gemma Kullanım Koşulları](https://ai.google.dev/gemma/terms) |
| [Whisper](https://github.com/openai/whisper) (base.en, small.en; distil-large-v3) — [SYSTRAN'ın CTranslate2 dönüşümleri](https://huggingface.co/Systran/faster-whisper-small.en) | Konuşma tanıma | OpenAI; distil-whisper Hugging Face; dönüşüm SYSTRAN | MIT |
| [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) v1.0 ([ONNX dosyaları](https://github.com/thewh1teagle/kokoro-onnx/releases)) | İngilizce ses (yapay zekâ ve okuma) | hexgrad | Apache-2.0 |
| [EMA Lightning](https://huggingface.co/canberkkkkkk/ema-lightning) — `app/tts_tr` içinde ONNX'e çevrilmiş hali | Öğretmenin Türkçe sesi | canberk7 / canberkkkkkk | Apache-2.0 (`app/tts_tr/LICENSE`; değişiklikler `app/tts_tr/README.md`'de) |

Modellerin cevapları yapay zekâ çıktısıdır: uygulama onları kontrolden geçirir ama nadiren hata olabilir.

### Veri ve içerik

| Kaynak | Nerede | Kimin | Lisans / atıf |
|---|---|---|---|
| [Vikisözlük (İngilizce)](https://en.wiktionary.org), [kaikki.org](https://kaikki.org) üzerinden ([Wiktextract](https://github.com/tatuylonen/wiktextract)) | Çevrimdışı sözlük (`data/dictionary.db`, kurulumda üretilir); kelime listelerindeki Türkçe anlam adayları | Vikisözlük katkıcıları; Tatu Ylonen | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) (ve GFDL). Ylonen, T. (2022). *Wiktextract: Wiktionary as Machine-Readable Structured Data.* LREC 2022 |
| [Vikisözlük (Türkçe)](https://tr.wiktionary.org), kaikki.org trwiktionary | Kelime listelerindeki Türkçe anlam adayları | Vikisözlük katkıcıları | CC BY-SA 4.0 |
| [CEFR-J Wordlist 1.5](https://github.com/openlanguageprofiles/olp-en-cefrj) | Kelime Çalış A1–B2 listeleri ve seviyeleri | Tono Laboratory, Tokyo University of Foreign Studies | Atıfla ücretsiz (araştırma ve ticari). *The CEFR-J Wordlist Version 1.5. Compiled by Yukio Tono, Tokyo University of Foreign Studies.* |
| [Octanove Vocabulary Profile C1/C2 1.0](https://github.com/openlanguageprofiles/olp-en-cefrj) | Kelime Çalış C1 listesi | Octanove Labs | CC BY-SA 4.0 |
| [New General Service List 1.2](https://www.newgeneralservicelist.com) | ⭐ En sık 3000 kelime | Browne, C., Culligan, B. & Phillips, J. | CC BY-SA 4.0. *Browne, C., Culligan, B. (2013). The New General Service List.* |
| [British Council LearnEnglish](https://learnenglish.britishcouncil.org) (121 bağlantı), [Cambridge Dictionary](https://dictionary.cambridge.org) (98), [BBC Learning English](https://www.bbc.co.uk/learningenglish) (14), [Cambridge English](https://www.cambridgeenglish.org) (4), [Oxford Learner's Dictionaries](https://www.oxfordlearnersdictionaries.com) (2) | Derslerin, kalıpların ve YDS sorularının "📚 Kaynaklar" bağlantıları | Kendi yayıncıları | Yalnızca bağlantı verilir; metinleri kopyalanmadı, içerik bu sayfalara dayanarak özgün yazıldı |
| [ÖSYM](https://www.osym.gov.tr) YDS / e-YDS / YÖKDİL sınav biçimi (15 bağlantı) | 🎯 Kendini Test Et soru türleri ve süre | ÖSYM | Yalnızca sınavın **biçimi** örnek alındı; ÖSYM'nin soruları kullanılmadı, tüm sorular özgündür |

Kelime listeleri (`app/content/vocab/*.json`) Vikisözlük, Octanove ve NGSL içeriğinden türetildiği için bu
lisansların "aynı lisansla paylaş" (ShareAlike) koşuluyla, yani **CC BY-SA 4.0** ile paylaşılır. Ayrıntılar:
[`app/content/vocab/README.md`](app/content/vocab/README.md).

### Uygulamanın kendi içeriği

- **Dersler, seviye sınavları, kalıplar, YDS tarzı sorular, senaryolar ve Türkçe açıklamalar** yapay zekâ
  yardımıyla ([Claude](https://www.anthropic.com/claude), Anthropic) yazıldı; her içerik, yazandan bağımsız
  ayrı bir yapay zekâ denetiminden ve otomatik içerik testlerinden geçti. Biçim ve kurallar her içerik
  klasörünün `README.md` dosyasında.
- **Kod:** [Claude Code](https://claude.com/claude-code) ile geliştirildi.
- **Logo** (`app/frontend/logo.svg` ve simgeler) bu proje için çizildi.
- **Test ses örneği** (`setup/assets/sample.wav`): "Yesterday I go to the market…" cümlesi, Kokoro-82M
  (Apache-2.0) ile üretildi.

Hepsine teşekkürler. 🙏

## Lisans

- **Kod** (uygulamanın kendi kodu, logo ve simgeler): [MIT](LICENSE). Hangi lisansın neyi kapsadığının özeti: [NOTICE.md](NOTICE.md).
- **İçerik** (`app/content/`: dersler, seviye sınavları, kalıplar, YDS tarzı sorular, kelime listeleri):
  [CC BY-SA 4.0](LICENSES/CC-BY-SA-4.0.txt); kelime listeleri CC BY-SA kaynaklardan türetildiği için zaten bu
  lisansla paylaşılmak zorunda. Atıf ve kaynaklar: [`app/content/LICENSE.md`](app/content/LICENSE.md).
- **Türkçe ses modeli** (`app/tts_tr/`, EMA Lightning'in ONNX'e çevrilmiş hali): [Apache-2.0](app/tts_tr/LICENSE).
- **Kurulumda inen yazılım ve modeller** (Python, Ollama, Python paketleri, Gemma/Qwen, Whisper, Kokoro, sözlük):
  her biri kendi lisansıyla; liste yukarıda, "Kaynaklar, lisanslar ve teşekkürler".

## Yol haritası

| # | Adım | Durum |
|---|---|---|
| 1 | Temel: FastAPI + arayüz + yazılı sohbet + SQLite | ✅ |
| 2 | Taşınabilir yapı: gömülü Python, uygulama içi Ollama, bilgisayar profili, veri geçişi | ✅ |
| 3 | Ses girişi (bas-konuş, faster-whisper) | ✅ |
| 4 | Sesli cevap (Kokoro TTS, cümle cümle) | ✅ |
| 5 | Düzeltme paneli | ✅ |
| 6 | Senaryolar | ✅ |
| 7 | Yazma modu | ✅ |
| 8 | Kelime defteri + çevrimdışı sözlük | ✅ |
| 9 | İlerleme sayfası | ✅ |
| 10 | Kurulum sihirbazı (`Kurulum.bat`): donanım taraması, model kataloğu, indirme, hız testi | ✅ |
| 11 | Yeni bilgisayar modu, bakım modu | ✅ |
| 12 | Uygulama içi model yönetimi (Ayarlar → Dil modelleri, sohbette oturum modeli) | ✅ |
| 13a | Telaffuz göstergesi (Whisper kelime güveni) | ✅ |
| 13b | Telefondan erişim için HTTPS | ertelendi |
| 14 | Dersler (A1–C1, iş İngilizcesi, doğrulanmış kaynaklar) + seviye sınavları | ✅ |
| 15 | Türkçe konuşulabilen öğretmen (model karşılaştırması → Gemma 4 E4B) | ✅ |

## Klasör yapısı

```
Kurulum.bat          Kurulum ve bakım sihirbazı          (Linux: kurulum.sh → setup/bootstrap.sh)
Baslat.bat           Uygulamayı açar                     (Linux: baslat.sh)
Guncelle.bat         GitHub'dan günceller                (Linux: guncelle.sh)
app/
  launcher.py        Kilit/yedek, Ollama, sunucu, tarayıcı; yeni bilgisayarda sihirbazı açar
  ollama_runtime.py  Uygulamaya ait Ollama'yı boş bir portta alt süreç olarak çalıştırır
  backend/           FastAPI uygulaması
  frontend/          Arayüz (HTML/CSS/JS, build adımı yok)
  requirements.txt
setup/               Kurulum sihirbazı (wizard.py, wizard_ui/), görevler (installer.py),
                     model kataloğu (catalog.json), hız testi, sözlük oluşturma, geçiş
runtime/python/      Gömülü Python 3.12 + paketler
runtime/ollama/      Uygulamaya ait Ollama
models/ollama/       Dil modelleri (qwen3:8b …)
models/stt/          Whisper modelleri
models/tts/kokoro/   Kokoro-82M (ONNX, işlemcide çalışır — ekran kartı belleği dil modeline kalır)
data/app.db          Kullanıcı verisi: geçmiş, ayarlar, kelime defteri
data/dictionary.db   Çevrimdışı İngilizce–Türkçe sözlük (Wiktionary)
data/backups/        Günlük yedekler (son 14 gün) + geçiş öncesi yedekler
config/machines/     Her bilgisayarın profili (<BİLGİSAYAR-ADI>.json)
logs/                launcher.log, ollama.log, setup.log
```

- **Kişisel ayarlar** (seviye, ilgi alanları, TTS sesi…) `data/app.db`'de — her bilgisayarda aynı.
- **Donanıma bağlı ayarlar** (dil modeli, Whisper modeli) bilgisayar profilinde — masaüstü ve laptop
  farklı model kullanabilir.

## Portlar

Windows bazı port aralıklarını kendisi ayırabilir (Hyper-V, WSL…) ve bir port başka bir programda açık olabilir.
Bu yüzden portlar sabit değil: başlatıcı her açılışta Ollama ve uygulama için **boş bir port seçer**
(uygulama için önce 8000, sonra 8080, 8765… denenir). Elle bir şey yapmaya gerek yok.

## Bilgisayarda başka bir Ollama varsa

Uygulama kendi klasöründeki Ollama'yı kendi seçtiği boş bir portta çalıştırır; sistemde ayrıca kurulu bir Ollama
varsa onunla çakışmaz ve ona ihtiyaç duymaz. Kurulum sihirbazı, sistemdeki Ollama'nın daha önce indirdiği
modelleri bulursa yeniden indirmek yerine kopyalamayı önerir.

## Geliştirici notları

Paket kurmak için (sanal ortam yok, gömülü Python'a kurulur):

```bash
runtime\python\python.exe -m pip install -r app\requirements.txt
```

Eski sürümden geçiş (yedek alır, kayıt sayılarını doğrular, modelleri kopyalar):

```bash
runtime\python\python.exe -m setup.migrate
```

### Arkadaşlarla paylaşma

Kişisel veri (data/app.db, profil, kayıtlar), geliştirme dosyaları ve sohbet arşivi olmadan temiz bir
kopya + zip üretir (~14 MB; hazır sözlük dahil). Alan kişi zip'i açıp **Kurulum.bat**'a tıklar; Python,
Ollama, dil modeli, Whisper ve ses kendiliğinden iner (~10 GB). Kullanım anlatımı pakette `BENI-OKU.txt`.

```bash
runtime\python\python.exe dev\tools\make_package.py D:\EnglishPractice --zip
```

### GitHub ve güncellemeler

Kodun asıl hali GitHub deposunda: <https://github.com/recepyagmur/EnglishPractice>.
Geliştirme bu klasörde yapılır; her commit'ten sonra `git push` ile depoya gönderilir.

- **Arkadaşların güncellemesi:** uygulama kapalıyken `Guncelle.bat`. Tarayıcıda deponun zip'i iner (depo özelken GitHub
  hesabıyla giriş + depoya davet gerekir; herkese açıkken gerekmez), güncelleyici (`setup/updater.py`) İndirilenler klasöründe zip'i bulur,
  dosyaları değiştirir, depodan silinen dosyaları siler, verilere (`data/`), modellere ve kuruluma dokunmaz,
  önce veriyi yedekler, `requirements` değiştiyse paketleri kurar ve zip'i siler. Zip başka yere indiyse
  `Guncelle.bat`'ın üzerine sürüklenebilir. Geliştirme kopyasında (git deposu) çalışmaz.
- **Arkadaş davet etmek:** GitHub'da depo → Settings → Collaborators → Add people (GitHub kullanıcı adı);
  arkadaş e-postadaki daveti kabul eder.
- Pakette `config/package-files.txt` (paketin dosya listesi) ve `config/package-version.txt` (commit) bulunur;
  güncelleyici silinecek dosyaları ve sürümü bunlarla bilir.

## İki bilgisayarda kullanma (masaüstü + laptop)

Uygulama her bilgisayarda ayrı kurulur; **verilerin** (ilerleme, ders cevapları, kelimeler, sohbetler, sınavlar)
Google Drive üzerinden aynı tutulur:

1. İki bilgisayarda da **Google Drive masaüstü uygulaması** aynı hesapla açık olsun.
2. Verilerin bulunduğu bilgisayarda: **Ayarlar → ☁️ İki bilgisayar → Eşitlemeyi aç** (klasör kendiliğinden
   önerilir, ör. `G:\My Drive\EnglishPractice`).
3. Öbür bilgisayarda aynısını yap ve **"… verilerini al"** de (o bilgisayardaki eski veri yedekte kalır).

Sonrası kendiliğinden: uygulama açılırken öbür bilgisayardaki son çalışmanı alır, açıkken birkaç dakikada bir
ve **kapanırken** (Ctrl+C ya da siyah pencereyi kapatınca) gönderir. **Bir seferde tek bilgisayarda aç:**
öbüründe açıksa uyarır. İkisinde de kapatmadan çalışılırsa birleştirilmez: daha yeni olan kalır, öbürü
`data\backups\cakisma-….db` olarak yedeklenir ve uyarı gösterilir. "Daha yeni", verinin içindeki **son çalışma**
(mesaj, kelime, tamamlanan ders, test, pratik günü) demektir; bir sayfayı açmak sayılmaz. Öbür bilgisayar eski
verisini gönderirse (ör. önce yeni veriyi almadan) bu bilgisayardaki yeni çalışmanın üzerine yazılmaz: eski hali
yedeklenir, uyarı gösterilir. Bir bilgisayarda silinen bir şey öbüründe de silinir. İkinci bilgisayarı ilk
bağlarken iki tarafın son çalışma tarihi gösterilir; eski olanı seçersen onay istenir. Veri değişmeden önce her
zaman yedek alınır.
Uygulamanın kendisi ve modeller eşitlenmez: güncellemeler için laptopta `Guncelle.bat`.
Linux bilgisayarda Drive klasörü için bkz. "Linux'ta kurulum".
Ayrıntı: `app/backend/sync.py`.

## Yedekler ve geri dönme

**Verilerin** (ilerleme, kelimeler, sohbetler, sınavlar) `data/app.db` dosyasındadır ve kendiliğinden yedeklenir;
yedekler `data/backups/` klasöründedir:

- `daily-<tarih>.db`: her gün ilk açılışta.
- `pre-update-…db`: `Guncelle.bat` / `guncelle.sh` dosyaları değiştirmeden önce.
- `pre-schema-v<N>-…db`: yeni bir sürüm veritabanı yapısını değiştirmeden önce.
- `pre-setup-…db` / `pre-maintenance-…db`: kurulum sihirbazının kurulum ve bakım işlemlerinden önce.
- `pre-reset-…db`: Ayarlar → 🔄 Sıfırla'dan önce; `pre-sync-…db`: öbür bilgisayarın verisi alınmadan önce;
  `cakisma-<bilgisayar>-…db`: iki bilgisayarda birden çalışılınca yeni olmayan taraf.

Bir yedeğe dönmek için (uygulama kapalıyken): istediğin yedeği `data/app.db` dosyasının üzerine kopyala, sonra
uygulamayı aç. Kopyalamadan önce şimdiki `data/app.db`'yi de bir kenara almak iyi olur.

**Kod** (git ile çalışıyorsan): her değişiklik bir commit'tir; önceki bir sürümü denemek için uygulama kapalıyken

```bash
git log --oneline
git checkout <commit>
```

ve son sürüme dönmek için `git checkout main`. Kendi kopyanda büyük bir değişiklikten önce bir etiket koyarsan
(`git tag once-<ad>`) oraya `git checkout once-<ad>` ile dönebilirsin. Eski kodla yeni sürümün eklediği
veritabanı sütunları zararsızdır; veriyi geri almak yalnız o değişiklikten sonraki kayıtları silmek istersen gerekir.
`Guncelle.bat` ile kurulan kopyada git yoktur: orada eski bir sürüme dönmek için GitHub'dan o sürümün zip'ini
indirip `Guncelle.bat`'ın üzerine sürükle (veriler ve modeller korunur).

## Sorun giderme

| Belirti | Çözüm |
|---|---|
| Mikrofon butonu soluk / tıklanmıyor | Whisper yükleniyor (⏳) veya hata verdi — üst bardaki Whisper göstergesinin üzerine gelin. |
| "Mikrofon izni verilmedi" | Adres çubuğundaki kilit simgesi → Mikrofon → İzin ver, sayfayı yenileyin. |
| Üst barda **Ollama ✗** | `logs/ollama.log` dosyasına bakın; `Baslat.bat` ile yeniden başlatın. |
| "… bu bilgisayarda kurulu değil" | Ayarlar → Dil modelleri'nden kurulu bir modeli varsayılan yapın ya da bir model indirin. |
| "Uygulama başka bilgisayarda açık görünüyor" | Klasör senkronize ediliyorsa diğer bilgisayarda uygulamayı kapatın. Kapalı olduğundan eminseniz "e" ile devam edin. |
| Veri kaybı şüphesi | `data/backups/` içindeki en son yedeği `data/app.db` yerine kopyalayın (uygulama kapalıyken). |
