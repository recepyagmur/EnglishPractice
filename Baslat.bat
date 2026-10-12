@echo off
chcp 65001 >nul
cd /d "%~dp0"
title English Practice
if not exist "runtime\python\python.exe" (
    echo Kurulum bulunamadi. Once Kurulum.bat dosyasini calistirin.
    pause
    exit /b 1
)
rem Uygulama icinden guncelleme bu dosyayi da degistirebilir: komut, pause ve cikis ayni satirda
rem (cmd dosyayi satir satir okur).
"runtime\python\python.exe" app\launcher.py %* & (if errorlevel 1 pause) & exit /b
