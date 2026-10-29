@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ===========================================================
echo                 BossPDF 프로그램 제거
echo ===========================================================
echo.

set "SCRIPT_PATH=%~dp0scripts\uninstall.ps1"
if not exist "%SCRIPT_PATH%" (
    set "SCRIPT_PATH=%~dp0uninstall.ps1"
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_PATH%"

echo.
pause
