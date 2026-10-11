#!/usr/bin/env bash
# English Practice — kurulum ve bakım (Linux). Çalıştırmak için bu klasörde:  bash kurulum.sh
# Ayrıntılar setup/bootstrap.sh içinde (Windows karşılığı: Kurulum.bat).
cd "$(dirname "$0")" || exit 1
bash setup/bootstrap.sh "$@"
code=$?
if [ "$code" -ne 0 ] && [ -t 0 ]; then
    read -r -p "Kapatmak için Enter'a bas…" _
fi
exit "$code"
