@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ===========================================================
echo       BossPDF 원클릭 설치 및 윈도우 우클릭 메뉴 등록
echo ===========================================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install.ps1"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] 설치 중 오류가 발생했습니다.
    pause
    exit /b %ERRORLEVEL%
)

echo.
pause
