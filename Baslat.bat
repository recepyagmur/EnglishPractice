@echo off
chcp 65001 >nul
cd /d "%~dp0"
title English Practice
if not exist "runtime\python\python.exe" (
    echo Kurulum bulunamadi. Once Kurulum.bat dosyasini calistirin.
    pause
    exit /b 1
)
rem Uygulama icinden guncelleme bu dosyayi da degistirebilir: her komut tek satirda (cmd dosyayi satir satir okur).
rem Girdi bos (nul): Ctrl+C ile kapatinca cmd "Terminate batch job (Y/N)?" sorusunda beklemez; uygulama sorularini
rem konsoldan (CONIN$) okur, hata olursa pencereyi kendisi acik tutar.
call :run %* <nul & exit /b
:run
"runtime\python\python.exe" app\launcher.py %* & exit /b
