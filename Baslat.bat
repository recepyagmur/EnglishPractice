@echo off
chcp 65001 >nul
cd /d "%~dp0"
title English Practice
if not exist "runtime\python\python.exe" (
    echo Kurulum bulunamadi. Once Kurulum.bat dosyasini calistirin.
    pause
    exit /b 1
)
"runtime\python\python.exe" app\launcher.py %*
if errorlevel 1 pause
