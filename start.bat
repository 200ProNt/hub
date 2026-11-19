@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Hub

set "PYEXE="

REM 1. Пробуем py launcher
py -3 -c "import sys" >nul 2>nul && set "PYEXE=py -3"
if not defined PYEXE py -c "import sys" >nul 2>nul && set "PYEXE=py"

REM 2. Пробуем python в PATH
if not defined PYEXE python -c "import sys" >nul 2>nul && set "PYEXE=python"

REM 3. Пробуем стандартные пути установки Python
if not defined PYEXE (
    for /d %%D in ("%LOCALAPPDATA%\Python\pythoncore-*" "%LOCALAPPDATA%\Programs\Python\Python*") do (
        if not defined PYEXE if exist "%%D\python.exe" (
            "%%D\python.exe" -c "import sys" >nul 2>nul && set "PYEXE=%%D\python.exe"
        )
    )
)

if not defined PYEXE (
    echo Python не найден. Установи Python с python.org и запусти снова.
    pause
    exit /b 1
)

%PYEXE% server.py
if errorlevel 1 (
    echo.
    echo Программа завершилась с ошибкой. Текст выше.
    pause
)
