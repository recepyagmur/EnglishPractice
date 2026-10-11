@echo off
chcp 65001 >nul
cd /d "%~dp0"
title English Practice - Guncelleme
if not exist "runtime\python\python.exe" (
    echo Kurulum bulunamadi. Once Kurulum.bat dosyasini calistirin.
    pause
    exit /b 1
)
rem Guncelleme bu dosyayi da degistirebilir: komut, pause ve cikis ayni satirda (cmd dosyayi satir satir okur).
"runtime\python\python.exe" -m setup.updater %* & pause & exit /b
