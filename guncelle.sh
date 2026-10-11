#!/usr/bin/env bash
# English Practice'i GitHub'dan günceller (Linux). Çalıştırmak için bu klasörde:  bash guncelle.sh [zip]
# Güncelleme bu dosyayı da değiştirebilir: bash betiği satır satır okur, bu yüzden her şey önce tamamen
# okunan bir fonksiyonun içinde (Windows karşılığı: Guncelle.bat).
main() {
    cd "$(dirname "$0")" || exit 1
    if [ ! -x runtime/python/bin/python3 ]; then
        echo "Kurulum bulunamadı. Önce kurulumu çalıştırın:  bash kurulum.sh"
        [ -t 0 ] && read -r -p "Kapatmak için Enter'a bas…" _
        exit 1
    fi
    runtime/python/bin/python3 -m setup.updater "$@"
    code=$?
    [ -t 0 ] && read -r -p "Kapatmak için Enter'a bas…" _
    exit "$code"
}
main "$@"
