@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Hub

set "PY_CMD="

REM 1. Проверяем py launcher
py -3 -c "import sys" >nul 2>nul && set "PY_CMD=py -3"
if not defined PY_CMD py -c "import sys" >nul 2>nul && set "PY_CMD=py"
if defined PY_CMD goto :run

REM 2. Проверяем python в PATH
python -c "import sys" >nul 2>nul && set "PY_CMD=python"
if defined PY_CMD goto :run

REM 3. Проверяем стандартные каталоги установки Python
call :search_dirs "%LOCALAPPDATA%\Python" "pythoncore-*"
if defined PY_CMD goto :run

call :search_dirs "%LOCALAPPDATA%\Programs\Python" "Python*"
if defined PY_CMD goto :run

if defined ProgramFiles call :search_dirs "%ProgramFiles%\Python" "Python*"
if defined PY_CMD goto :run

if defined ProgramFiles(x86) call :search_dirs "%ProgramFiles(x86)%\Python" "Python*"
if defined PY_CMD goto :run

call :search_dirs "C:\Program Files\Python" "Python*"
if defined PY_CMD goto :run

call :search_dirs "C:\Program Files (x86)\Python" "Python*"
if defined PY_CMD goto :run

call :search_dirs "C:" "Python*"
if defined PY_CMD goto :run

echo.
echo ========================================================
echo  Python не найден!
echo  Установите Python 3.10+ с https://www.python.org/
echo  (обязательно отметьте галочку "Add python.exe to PATH")
echo ========================================================
echo.
pause
exit /b 1

:search_dirs
if not exist "%~1" exit /b 0
for /d %%D in ("%~1\%~2") do (
    if not defined PY_CMD if exist "%%D\python.exe" (
        "%%D\python.exe" -c "import sys" >nul 2>nul && set "PY_CMD=%%D\python.exe"
    )
)
exit /b 0

:run
if "%PY_CMD%"=="py -3" goto :run_py3
"%PY_CMD%" server.py
goto :check_exit

:run_py3
py -3 server.py

:check_exit
if errorlevel 1 (
    echo.
    echo Программа завершилась с ошибкой. Текст выше.
    pause
    exit /b 1
)
exit /b 0
