#!/usr/bin/env bash
# kurulum.sh önyüklemesi (Linux, macOS): taşınabilir Python'u hazırlar ve kurulum sihirbazını açar.
# Sisteme hiçbir şey kurmaz, yönetici (sudo) izni gerekmez; her şey bu klasörün içine iner.
# kurulum.sh'a verilen argümanlar sihirbaza iletilir (ör. --no-browser, --mode maintenance).
# Windows karşılığı: setup/bootstrap.ps1.

set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYDIR="$ROOT/runtime/python"
PY="$PYDIR/bin/python3"
LOGS="$ROOT/logs"
mkdir -p "$LOGS"
LOG="$LOGS/setup.log"
# python-build-standalone: a self-contained CPython (also in setup/catalog.json, "python_linux" / "python_mac").
# Written for macOS's own bash 3.2 too (no bash 4 features).
if [ "$(uname -s)" = "Darwin" ]; then
    PLATFORM="macOS"
    PY_URL="https://github.com/astral-sh/python-build-standalone/releases/download/20260924/cpython-3.12.14%2B20260924-aarch64-apple-darwin-install_only.tar.gz"
    PY_SHA256="9763f43db2481a6af36af82ec40302aab7a73632f880129d07a6e81aec846277"
    PY_MB=25
else
    PLATFORM="Linux"
    PY_URL="https://github.com/astral-sh/python-build-standalone/releases/download/20260924/cpython-3.12.14%2B20260924-x86_64-unknown-linux-gnu-install_only.tar.gz"
    PY_SHA256="5eae8cf79dd47fc2496a4fccc892936be831ce7a84d984b2299dfb1cdb592682"
    PY_MB=64
fi

step() { echo; printf '\033[36m[%s/6] %s\033[0m\n' "$1" "$2"; echo "$(date +%FT%T) [$1/6] $2" >> "$LOG"; }
info() { echo "      $1"; echo "$(date +%FT%T)   $1" >> "$LOG"; }
fail() {
    echo
    printf '\033[31mHATA: %s\033[0m\n' "$1"
    echo "Ayrıntılar: $LOG"
    echo "$(date +%FT%T) HATA: $1" >> "$LOG"
    exit 1
}

# Download with curl or wget (one of them is on every desktop Linux; macOS has curl); an interrupted download
# continues.
fetch() {
    if command -v curl >/dev/null 2>&1; then
        curl -fL --retry 5 -C - -sS -o "$2" "$1"
    elif command -v wget >/dev/null 2>&1; then
        wget -q -c -O "$2" "$1"
    else
        return 127
    fi
}

online() {
    if command -v curl >/dev/null 2>&1; then
        curl -fsI --max-time 15 https://www.python.org >/dev/null 2>&1
    else
        wget -q --spider --timeout=15 https://www.python.org >/dev/null 2>&1
    fi
}

# The SHA256 check: sha256sum on Linux, shasum on macOS.
sha_ok() {
    if command -v sha256sum >/dev/null 2>&1; then
        echo "$1  $2" | sha256sum -c --status
    elif command -v shasum >/dev/null 2>&1; then
        echo "$1  $2" | shasum -a 256 -c -s
    else
        return 0
    fi
}

printf '\033[32mEnglish Practice — Kurulum (%s)\033[0m\n' "$PLATFORM"

step 1 "Sistem kontrol ediliyor…"
if [ "$PLATFORM" = "macOS" ]; then
    # Apple Silicon (M1–M4) only; macOS 14 (Sonoma) or newer: the Python packages (onnxruntime) need it.
    [ "$(uname -m)" = "arm64" ] || fail "Apple Silicon (M1, M2, M3, M4) işlemcili bir Mac gerekli; bu Mac: $(uname -m) (Intel Mac'ler desteklenmiyor)."
    MACOS="$(sw_vers -productVersion 2>/dev/null)"
    if [ "${MACOS%%.*}" -lt 14 ] 2>/dev/null; then
        fail "macOS 14 (Sonoma) ya da daha yenisi gerekli; bu Mac: macOS $MACOS. Sistem Ayarları → Genel → Yazılım Güncelleme."
    fi
    info "macOS $MACOS, Apple Silicon ✓"
else
    [ "$(uname -s)" = "Linux" ] || fail "Bu betik Linux ve macOS içindir. Windows'ta Kurulum.bat'ı çalıştırın."
    [ "$(uname -m)" = "x86_64" ] || fail "64 bit (x86_64) Linux gerekli; bu bilgisayar: $(uname -m)."
    GLIBC="$(ldd --version 2>/dev/null | head -1 | grep -oE '[0-9]+\.[0-9]+$')"
    if [ -n "$GLIBC" ]; then
        # The Python packages need glibc 2.28 or newer (Ubuntu 20.04, Debian 10, Fedora 29 and later).
        if [ "$(printf '%s\n2.28\n' "$GLIBC" | sort -V | head -1)" != "2.28" ]; then
            fail "Linux sürümü çok eski (glibc $GLIBC); en az glibc 2.28 gerekli (ör. Ubuntu 20.04 ve sonrası)."
        fi
        info "Linux $(uname -r) x86_64, glibc $GLIBC ✓"
    else
        info "Linux $(uname -r) x86_64 ✓ (glibc sürümü okunamadı)"
    fi
fi
command -v curl >/dev/null 2>&1 || command -v wget >/dev/null 2>&1 \
    || fail "İndirme için curl ya da wget gerekli. Ör. Ubuntu/Debian: sudo apt install curl"

step 2 "Klasör yolu kontrol ediliyor…"
if printf '%s' "$ROOT" | LC_ALL=C grep -q '[^ -~]' || [[ "$ROOT" == *" "* ]]; then
    fail "Klasör yolunda Türkçe karakter veya boşluk var: $ROOT
      Klasörü örneğin ~/EnglishPractice gibi bir yere taşıyıp kurulum.sh'ı yeniden çalıştırın."
fi
info "$ROOT ✓"
# Files from a zip lose their "executable" mark: make the scripts runnable (bash kurulum.sh works anyway).
chmod +x "$ROOT"/*.sh "$ROOT"/setup/*.sh 2>/dev/null
if [ "$PLATFORM" = "macOS" ]; then
    # A zip downloaded with a browser marks every file "from the internet" (quarantine); this folder is the
    # learner's own copy of the app: take the mark off, so nothing in it is stopped by Gatekeeper.
    xattr -dr com.apple.quarantine "$ROOT" 2>/dev/null
fi

step 3 "İnternet ve disk alanı kontrol ediliyor…"
FREE_GB="$(df -Pk "$ROOT" | awk 'NR==2 {printf "%.1f", $4 / 1048576}')"
info "Boş disk: $FREE_GB GB"
if awk -v f="$FREE_GB" 'BEGIN { exit !(f < 12) }'; then
    printf '\033[33m      UYARI: Kurulum için en az ~12 GB boş alan önerilir.\033[0m\n'
fi
if online; then
    info "İnternet bağlantısı ✓"
elif [ ! -x "$PY" ]; then
    fail "İnternet bağlantısı yok. Kurulum için internet gerekli (sonra çevrimdışı çalışır)."
else
    info "İnternet yok — sadece bakım işlemleri yapılabilir."
fi

step 4 "Python hazırlanıyor…"
if [ ! -x "$PY" ]; then
    ARCHIVE="$ROOT/models/_downloads/python.tar.gz"
    mkdir -p "$(dirname "$ARCHIVE")" "$ROOT/runtime"
    info "İndiriliyor (~$PY_MB MB)…"
    fetch "$PY_URL" "$ARCHIVE" >> "$LOG" 2>&1 || fail "Python indirilemedi."
    sha_ok "$PY_SHA256" "$ARCHIVE" \
        || { rm -f "$ARCHIVE"; fail "İndirilen Python dosyası bozuk (SHA256 tutmadı); kurulum.sh'ı yeniden çalıştırın."; }
    rm -rf "$PYDIR"
    tar -xzf "$ARCHIVE" -C "$ROOT/runtime" >> "$LOG" 2>&1 || fail "Python açılamadı."
    rm -f "$ARCHIVE"
    [ -x "$PY" ] || fail "Python açıldı ama $PY bulunamadı."
    info "Python $("$PY" -c 'import platform; print(platform.python_version())') ✓"
else
    info "Python zaten hazır ✓"
fi
# Like the ._pth file of Windows' embedded Python: the app's folders on sys.path (relative, so the folder can move).
"$PY" - <<'PYEOF' >> "$LOG" 2>&1 || fail "Python yolları ayarlanamadı."
import os, sysconfig
site = sysconfig.get_paths()["purelib"]
root = os.path.abspath(os.path.join(os.path.dirname(os.path.realpath(os.sys.executable)), "..", "..", ".."))
lines = [os.path.relpath(os.path.join(root, "app"), site), os.path.relpath(root, site)]
with open(os.path.join(site, "englishpractice.pth"), "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
print("englishpractice.pth:", lines)
PYEOF
if ! "$PY" -m pip --version >/dev/null 2>&1; then
    info "pip kuruluyor…"
    "$PY" -m ensurepip --upgrade >> "$LOG" 2>&1 || fail "pip kurulamadı."
fi
info "pip ✓"

step 5 "Sihirbaz bileşenleri kuruluyor…"
"$PY" -m pip install -q --disable-pip-version-check --no-warn-script-location --no-cache-dir \
    -r "$ROOT/setup/requirements-wizard.txt" >> "$LOG" 2>&1 || fail "Sihirbaz bileşenleri kurulamadı."
info "✓"

step 6 "Kurulum sihirbazı açılıyor…"
info "Tarayıcıda açılacak. Bu pencereyi kurulum bitene kadar kapatmayın."
cd "$ROOT" || fail "$ROOT klasörüne geçilemedi."
exec "$PY" -m setup.wizard "$@"
