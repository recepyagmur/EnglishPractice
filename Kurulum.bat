@echo off
chcp 65001 >nul
cd /d "%~dp0"
title English Practice - Kurulum
rem Kurulum ve bakim: tek dosya. Ayrintilar setup\bootstrap.ps1 icinde.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup\bootstrap.ps1" %*
if errorlevel 1 pause
