@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"

if exist ".venv\Scripts\pythonw.exe" goto :check
echo Программа ещё не установлена. Запускаю install.bat ...
call "%~dp0install.bat" nopause
if errorlevel 1 exit /b 1

:check
".venv\Scripts\python.exe" -c "import tkinter, PIL, numpy, imageio_ffmpeg" >nul 2>nul
if errorlevel 1 goto :broken
start "" ".venv\Scripts\pythonw.exe" -m pcm %*
exit /b 0

:broken
echo Окружение повреждено или неполное. Запустите install.bat ещё раз.
pause
exit /b 1
