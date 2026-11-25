@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Сначала запустите install.bat
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m unittest discover -s tests -v
set "RESULT=%ERRORLEVEL%"
echo.
if "%RESULT%"=="0" (echo ТЕСТЫ ПРОЙДЕНЫ) else (echo ЕСТЬ ОШИБКИ В ТЕСТАХ)
pause
exit /b %RESULT%
