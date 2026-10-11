#!/usr/bin/env bash
# English Practice'i başlatır (Linux). Çalıştırmak için bu klasörde:  bash baslat.sh
# Kapatmak için bu terminalde Ctrl+C. (Windows karşılığı: Baslat.bat.)
cd "$(dirname "$0")" || exit 1
if [ ! -x runtime/python/bin/python3 ]; then
    echo "Kurulum bulunamadı. Önce kurulumu çalıştırın:  bash kurulum.sh"
    [ -t 0 ] && read -r -p "Kapatmak için Enter'a bas…" _
    exit 1
fi
runtime/python/bin/python3 app/launcher.py "$@"
code=$?
if [ "$code" -ne 0 ] && [ -t 0 ]; then
    read -r -p "Kapatmak için Enter'a bas…" _
fi
exit "$code"
