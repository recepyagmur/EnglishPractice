"""Build the clean folder (and zip) to share with friends: the app without personal data.

    runtime\\python\\python.exe dev\\tools\\make_package.py [target folder, default D:\\EnglishPractice] [--zip]

Copies the files tracked by git (as they are in the working tree), minus development files
and the conversation archive, plus the prebuilt dictionary (saves a 520 MB download during
setup). No runtime, models, data, logs or machine profiles: Kurulum.bat downloads and sets up
everything (embedded Python, packages, Ollama, the language model, Whisper, Kokoro).
"""

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
args = [a for a in sys.argv[1:] if not a.startswith("--")]
TARGET = Path(args[0] if args else r"D:\EnglishPractice")
MAKE_ZIP = "--zip" in sys.argv

sys.path.insert(0, str(ROOT))
from setup.updater import PACKAGE_FILES, VERSION_FILE, shipped  # noqa: E402  (same rules as Guncelle.bat)
EXTRA_FILES = ["data/dictionary.db"]  # built by setup.build_dictionary (Wiktionary, CC BY-SA 4.0)

README_TXT = """English Practice — yerel İngilizce pratik uygulaması
=====================================================

Yapay zekayla İngilizce konuşma (mikrofonla ya da yazarak), anında düzeltme, A1–C1 dersler,
seviye sınavları, senaryolar, yazma değerlendirmesi, kelime defteri ve Türkçe konuşan bir
öğretmen. Her şey kendi bilgisayarında çalışır; kurulumdan sonra internet gerekmez.

GEREKENLER
- Windows 10 veya 11 (64 bit) — ya da 64 bit Linux (aşağıda "LINUX'TA")
- En az 15 GB boş disk alanı, en az 8 GB RAM (16 GB önerilir)
- Kurulum sırasında internet (yaklaşık 8–10 GB indirilir)
- NVIDIA ekran kartı varsa çok daha hızlı çalışır; yoksa da çalışır (daha yavaş).

KURULUM
1. Bu klasörü Türkçe karakter ve boşluk OLMAYAN bir yere koy, ör. C:\\EnglishPractice
   (Değilse kurulum klasörü C:\\EnglishPractice'e kopyalamayı kendisi önerir.)
2. Kurulum.bat dosyasına çift tıkla.
   Windows "Bilgisayarınız korundu" derse: "Ek bilgi" → "Yine de çalıştır".
3. Tarayıcıda kurulum sihirbazı açılır. Bilgisayarın taranır ve ona uygun model
   "Önerilir" diye işaretlenir. Önerilenlerle "İleri" de; "Ek bileşenler" adımında
   istersen "Masaüstüne kısayol oluştur" kutusunu işaretle. Özette "Kur"a bas ve
   "Kurulum başlasın mı?" sorusuna Tamam de.
   Python, Ollama, dil modeli, ses tanıma ve ses dosyaları bu klasörün içine iner;
   sisteme hiçbir şey kurulmaz. Siyah pencereyi kurulum bitene kadar kapatma.
4. Kurulumdan sonra kısa bir test yapılır (hız, mikrofon, ses); bitince uygulama açılır.

KULLANIM
- Masaüstündeki "English Practice" kısayolu ya da bu klasördeki Baslat.bat.
- Uygulama kendi penceresinde açılır (Edge'in uygulama penceresi: sekme ve adres çubuğu yok).
  Pencereyi kapatınca uygulama arkada çalışmaya devam eder; Baslat.bat'a tekrar tıklayınca pencere
  yeniden açılır. Tamamen kapatmak için siyah pencerede Ctrl+C (ya da siyah pencereyi kapat).
- İlk açılışta İngilizce seviyen sorulur (sonra Ayarlar'dan değişir). Ayrıntılı kullanım: README.md
- Takıldığın her şeyi sol menüdeki 🧑‍🏫 Öğretmen'e Türkçe sorabilirsin.

GÜNCELLEME
- Uygulamanın kodu GitHub'da: https://github.com/recepyagmur/EnglishPractice
  Depo özelken (private) güncelleme için bir GitHub hesabın olmalı ve depoya davet edilmiş olmalısın
  (davet e-postasındaki "Accept invitation"); depo herkese açıksa gerekmez.
- Uygulama kapalıyken Guncelle.bat'a çift tıkla. Tarayıcıda GitHub açılır ve güncelleme zip'i
  iner (GitHub'a giriş yapmadıysan önce giriş yap, sonra siyah pencerede Enter'a bas).
  Güncelleyici indirilen dosyayı kendisi bulur, uygulamayı günceller ve zip'i siler.
- Verilerin, modeller ve kurulum olduğu gibi kalır; güncellemeden önce verilerin yedeklenir.

BİLMEN GEREKENLER
- Verilerin (konuşmalar, kelimeler, ilerleme) data klasöründe; her gün otomatik yedek alınır
  (data\\backups).
- Kaldırmak için: bu klasörü ve masaüstündeki kısayolu silmen yeterli.
- Klasörü başka bir bilgisayara taşıyabilirsin; orada Kurulum.bat eksik parçaları tamamlar.

LINUX'TA
- 64 bit Linux (Ubuntu 20.04 ve sonrası gibi), curl ya da wget, en az 15 GB boş alan.
- Klasörü ~/EnglishPractice gibi Türkçe karakter ve boşluk içermeyen bir yere koy.
- Terminalde o klasörde:  bash kurulum.sh   (aynı sihirbaz tarayıcıda açılır; sudo gerekmez)
- Açmak:  bash baslat.sh   (ya da kurulumda seçtiysen uygulama menüsündeki kısayol)
  Kapatmak: o terminalde Ctrl+C.   Güncellemek:  bash guncelle.sh
- Sorun olursa: logs klasöründeki setup.log ve launcher.log dosyalarına bak.
- Sözlük verisi: Wiktionary (kaikki.org), CC BY-SA 4.0 lisansıyla.
- Lisans: kod MIT (LICENSE), içerik CC BY-SA 4.0 (app/content/LICENSE.md); kullanılan bütün yazılım,
  model ve kaynakların atıfları README.md'de "Kaynaklar, lisanslar ve teşekkürler" bölümünde.
"""


def tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [f for f in out.splitlines() if shipped(f)]


def main() -> None:
    if TARGET.exists() and any(TARGET.iterdir()):
        if (TARGET / "runtime").exists() or (TARGET / "data" / "app.db").exists():
            sys.exit(f"{TARGET} kurulu bir kopya gibi görünüyor (runtime/ ya da data/app.db var); silmiyorum.")
        shutil.rmtree(TARGET)
    if subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True).stdout.strip():
        print("⚠ Commit edilmemiş değişiklikler var: paket çalışma ağacından yapılır, GitHub'daki sürümden farklı olabilir.")
    shipped_files = tracked_files()
    files = shipped_files + [f for f in EXTRA_FILES if (ROOT / f).exists()]
    for rel in files:
        dest = TARGET / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, dest)
    # Guncelle.bat: which files the package shipped (to remove ones the repository drops) and from which commit.
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    for path, text in ((PACKAGE_FILES, "\n".join(sorted(shipped_files))), (VERSION_FILE, commit)):
        dest = TARGET / path.relative_to(ROOT)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
    (TARGET / "BENI-OKU.txt").write_bytes(b"\xef\xbb\xbf" + README_TXT.replace("\n", "\r\n").encode("utf-8"))
    size = sum(p.stat().st_size for p in TARGET.rglob("*") if p.is_file())
    print(f"{len(files) + 3} dosya → {TARGET} ({size / 1e6:.1f} MB)")

    if MAKE_ZIP:
        zip_path = TARGET.with_suffix(".zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
            for p in sorted(TARGET.rglob("*")):
                if p.is_file():
                    z.write(p, Path(TARGET.name) / p.relative_to(TARGET))
        print(f"zip → {zip_path} ({zip_path.stat().st_size / 1e6:.1f} MB)")


main()
