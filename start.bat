@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Hub

set "PYEXE="
where py >nul 2>nul && set "PYEXE=py"
if not defined PYEXE where python >nul 2>nul && set "PYEXE=python"

if not defined PYEXE (
    echo Python не найден. Установи Python с python.org и запусти снова.
    pause
    exit /b 1
)

"%PYEXE%" server.py
if errorlevel 1 (
    echo.
    echo Программа завершилась с ошибкой. Текст выше.
    pause
)
