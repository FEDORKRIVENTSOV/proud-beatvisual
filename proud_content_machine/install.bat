@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"
title PROUD CONTENT MACHINE - установка

echo ==============================================
echo   PROUD CONTENT MACHINE - установка
echo ==============================================
echo.

set "PYEXE="
where py >nul 2>nul
if not errorlevel 1 (
    py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
    if not errorlevel 1 set "PYEXE=py -3"
)
if not defined PYEXE (
    where python >nul 2>nul
    if not errorlevel 1 (
        python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
        if not errorlevel 1 set "PYEXE=python"
    )
)
if not defined PYEXE goto :no_python

echo [1/4] Найден Python:
%PYEXE% --version

if exist ".venv\Scripts\python.exe" goto :venv_ready
echo [2/4] Создаю виртуальное окружение .venv ...
%PYEXE% -m venv ".venv"
if errorlevel 1 goto :fail_venv
goto :venv_done
:venv_ready
echo [2/4] Виртуальное окружение .venv уже существует.
:venv_done

echo [3/4] Устанавливаю зависимости, нужен интернет ...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r "requirements.txt"
if errorlevel 1 goto :fail_pip

echo [4/4] Проверяю установку ...
".venv\Scripts\python.exe" -c "import tkinter, PIL, numpy, imageio_ffmpeg; from pcm.ffmpeg_tools import find_ffmpeg; print('FFmpeg:', find_ffmpeg())"
if errorlevel 1 goto :fail_check

echo.
echo ГОТОВО. Запускайте программу файлом run.bat
if /i not "%~1"=="nopause" pause
exit /b 0

:no_python
echo ОШИБКА: не найден Python 3.10 или новее.
echo Скачайте его с https://www.python.org/downloads/ и при установке отметьте
echo "Add python.exe to PATH". Компонент tcl/tk должен остаться включённым.
if /i not "%~1"=="nopause" pause
exit /b 1

:fail_venv
echo ОШИБКА: не удалось создать виртуальное окружение.
if /i not "%~1"=="nopause" pause
exit /b 1

:fail_pip
echo ОШИБКА: не удалось установить зависимости. Проверьте интернет и повторите.
if /i not "%~1"=="nopause" pause
exit /b 1

:fail_check
echo ОШИБКА: проверка не пройдена. Если сообщение про tkinter, переустановите Python
echo с python.org и оставьте включённым компонент tcl/tk and IDLE.
if /i not "%~1"=="nopause" pause
exit /b 1
